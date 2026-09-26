# Contratos compartidos

Punto de acuerdo obligatorio entre `engine/` (Haskell) y `pipeline/` (Python). Si cambiás algo acá, avisá a los otros dos desarrolladores antes de tocar código que dependa de ello.

| Archivo | Qué define | Lo produce | Lo consume |
|---|---|---|---|
| [`ast-schema.json`](./ast-schema.json) | Programa STLC que emite el LLM (grupo Tratamiento) | LLM (*structured output*) | `engine/` |
| [`engine-verdict-schema.json`](./engine-verdict-schema.json) | Línea que el engine escribe en `stdout` | `engine/` | orquestador |
| [`output-record-schema.json`](./output-record-schema.json) | Registro JSON Lines, uno por caso y grupo | orquestador y baselines | experimento posterior |
| [`fixtures/`](./fixtures/) | Casos de punta a punta compartidos | — | tests de los tres carriles |

## 1. El DSL

### Forma

La raíz es siempre `{"expr": <Expr>}` (simétrica a `{"code": "..."}` de los baselines). Cada nodo lleva un discriminador `"type"` con el nombre del constructor:

| Nodo | Campos |
|---|---|
| `Literal` | `value` (entero, booleano o cadena), `value_type` (`"Int"`, `"Bool"`, `"String"`) |
| `Var` | `name` (`^[a-z_][A-Za-z0-9_]*$`) |
| `BinaryOp` | `op` (`>` `<` `>=` `<=` `==` `AND` `OR`), `left`, `right` |
| `IfThenElse` | `condition`, `then`, `else` |
| `Lam` | `param`, `param_type`, `body` |
| `App` | `fn`, `arg` |

Tipos: `"Int"`, `"Bool"`, `"String"` o `{"from": τ, "to": τ}` para `τ → τ`.

Ningún nodo admite claves extra. El schema solo usa `anyOf`/`enum`/`$ref` para ser compatible con el modo estricto de *structured output*; por eso la consistencia entre `value` y `value_type` no está en el schema y la valida el engine.

### Reglas de tipado

Γ es el entorno de tipos de las variables libres (ver §2, `--env`). Cada regla fallida produce un código de error estable:

| Construcción | Regla | Código si falla | Etapa |
|---|---|---|---|
| Entrada | es JSON | `MALFORMED_JSON` | `parse` |
| Entrada | respeta `ast-schema.json` | `INVALID_AST` | `parse` |
| `Literal` | `value` coincide con `value_type` | `LITERAL_TYPE_MISMATCH` | `parse` |
| `Var` | x ∈ Γ o ligada por un `Lam` que la encierra | `UNBOUND_VARIABLE` | `scope` |
| `>` `<` `>=` `<=` | `Int × Int → Bool` | `OPERAND_MISMATCH` | `typecheck` |
| `==` | `τ × τ → Bool`, τ tipo base | `OPERAND_MISMATCH` | `typecheck` |
| `AND` `OR` | `Bool × Bool → Bool` | `OPERAND_MISMATCH` | `typecheck` |
| `IfThenElse` | condición `Bool` | `CONDITION_NOT_BOOL` | `typecheck` |
| `IfThenElse` | `then` y `else` del mismo tipo | `BRANCH_MISMATCH` | `typecheck` |
| `Lam` | el cuerpo tipa en Γ, x:τ (x oculta a una x externa) | — | — |
| `App` | `fn : τ → σ` | `NOT_A_FUNCTION` | `typecheck` |
| `App` | `arg : τ` | `ARGUMENT_MISMATCH` | `typecheck` |
| Programa | el tipo final es `Int`, `Bool` o `String` | `NON_BASE_RESULT` | `typecheck` |

Si hay varios errores, se reporta el primero en el orden de las etapas y, dentro de una etapa, en el orden de recorrido del árbol (izquierda a derecha). El `message` es texto libre para humanos; el campo estable es `code`.

## 2. Contrato CLI del engine

```
engine [--env '<objeto JSON>']                   < respuesta_cruda_del_llm
engine [--env '<objeto JSON>'] --print-gamma
```

### `--env`: los datos del caso y la deducción de Γ

Objeto plano `{nombre: valor}`; si se omite, `{}`. **El engine deduce Γ de los valores** (el orquestador nunca decide tipos):

| Valor JSON | Tipo en Γ |
|---|---|
| entero que entra en 64 bits | `Int` |
| `true` / `false` | `Bool` |
| cadena | `String` |
| decimal, `null`, array, objeto, o nombre fuera de `^[a-z_][A-Za-z0-9_]*$` | error de uso (exit 64) |

Γ sale de los datos, no de la regla: el engine nunca infiere el tipo de una variable libre a partir de cómo la usa el LLM.

### Modo validación (por defecto)

- **stdin:** los bytes exactos de la respuesta del LLM, sin reparar ni reenvolver. El orquestador no parsea la salida del grupo Tratamiento; el engine es la única frontera de parseo.
- **stdout:** exactamente una línea JSON conforme a [`engine-verdict-schema.json`](./engine-verdict-schema.json), por ejemplo:

  ```json
  {"outcome":"executed","stage":"execution","result":{"type":"Bool","value":true},"error":null}
  {"outcome":"blocked","stage":"typecheck","result":null,"error":{"code":"BRANCH_MISMATCH","message":"then: Int, else: String"}}
  ```

### Modo `--print-gamma`

No lee stdin. Imprime en stdout una línea con Γ deducido de `--env`, claves en orden alfabético, y sale con 0. Es lo que usa el orquestador para listar las variables disponibles en el prompt del LLM:

```json
{"credit_score":"Int","customer_tier":"String","has_defaults":"Bool"}
```

### stderr

Diagnóstico libre. El orquestador no lo parsea.

### Códigos de salida

| Código | Significado | stdout |
|---|---|---|
| 0 | ejecutado (o Γ impreso con `--print-gamma`) | veredicto (o Γ) |
| 1 | bloqueado en `parse` | veredicto |
| 2 | bloqueado en `scope` | veredicto |
| 3 | bloqueado en `typecheck` | veredicto |
| 64 | error de uso: argumentos o `--env` inválidos. Es un bug del orquestador: abortar la corrida | vacío |
| 70 | error interno del engine (no debería ocurrir si el sistema de tipos es sano) | vacío |

### Garantías

- **Determinismo:** mismo stdin + mismo `--env` ⇒ mismo stdout byte a byte. Sin timestamps ni tiempos en la salida.
- **Aislamiento:** sin red y sin leer archivos.
- **Timeout:** lo aplica el orquestador; si vence, registra `outcome: "timeout"`.

## 3. Registro de salida

Un objeto por línea en [`output-record-schema.json`](./output-record-schema.json). Es registro, no medición: no incluye el resultado esperado ni comparaciones.

- **Tratamiento:** el orquestador copia `outcome`, `stage`, `result` y `error` del veredicto sin transformarlos. Exit 70 ⇒ `outcome: "runtime_error"`, `stage: "execution"`, `error.code: "ENGINE_INTERNAL"`.
- **Baselines:** mismo vocabulario de etapas. Baseline 1 llega siempre a `execution`; Baseline 2 recorre `parse` (`ast.parse`) → `typecheck` (mypy) → `execution`. `error.code` es el nombre de la excepción o herramienta (`SyntaxError`, `KeyError`, `mypy`). Un resultado que no es `int`/`bool`/`str` se registra como `{"type": "Other", "value": repr(x)}`.
- **`llm_raw`:** la respuesta cruda del LLM; `null` solo si `outcome = "llm_error"`.
- **`duration_ms`:** medido por el orquestador desde que lanza el subproceso (engine o sandbox) hasta que termina; excluye la llamada al LLM. `null` solo si `outcome = "llm_error"`.

## 4. Fixtures

Un archivo por caso en [`fixtures/`](./fixtures/):

| Campo | Contenido |
|---|---|
| `case_id` | identificador (`RULE-00N`) |
| `description` | la regla en lenguaje natural |
| `env` | datos del caso, tal como se pasan a `--env` |
| `llm_raw` | respuesta del LLM como *string* (para poder representar JSON roto) |
| `python_code` | código equivalente para los baselines |
| `expected_verdict` | `outcome`, `stage`, `exit_code` y `result` o `error_code` del engine |

| Caso | Qué prueba | Veredicto esperado del engine |
|---|---|---|
| `rule-001` | regla válida | `executed`, `Bool true`, exit 0 |
| `rule-002` | `"left": "credit_score"` | `parse`, `INVALID_AST`, exit 1 |
| `rule-003` | `Int > String` | `typecheck`, `OPERAND_MISMATCH`, exit 3 |
| `rule-004` | `risk_level ∉ Γ` | `scope`, `UNBOUND_VARIABLE`, exit 2 |
| `rule-005` | ramas `Int` / `String` | `typecheck`, `BRANCH_MISMATCH`, exit 3 |
| `rule-006` | `(λs:Int. s > 700) credit_score` | `executed`, `Bool true`, exit 0 |
| `rule-007` | JSON truncado | `parse`, `MALFORMED_JSON`, exit 1 |

Los casos 001–005 vienen de [`prototype/guia_fixtures_pruebas.md`](../prototype/guia_fixtures_pruebas.md). `python_code` se copió tal cual de esa guía; el carril de baselines decide si le agrega la firma tipada que exige Baseline 2.
