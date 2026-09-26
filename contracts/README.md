# Contratos compartidos

Punto de acuerdo obligatorio entre `engine/` (Haskell) y `pipeline/` (Python). Si cambiás algo acá, avisá a los otros dos desarrolladores antes de tocar código que dependa de ello.

| Archivo | Qué define | Lo produce | Lo consume |
|---|---|---|---|
| [`ast-schema.json`](./ast-schema.json) | Programa STLC que emite el LLM (grupo Tratamiento) | LLM (*structured output*) | `engine/` |
| [`engine-verdict-schema.json`](./engine-verdict-schema.json) | Línea que el engine escribe en `stdout` | `engine/` | orquestador |
| [`case-schema.json`](./case-schema.json) | Caso de entrada: una regla con sus escenarios de validación | corpus del experimento | orquestador |
| [`output-record-schema.json`](./output-record-schema.json) | Registro JSON Lines, uno por escenario de cada generación | orquestador y baselines | experimento posterior |
| [`fixtures/`](./fixtures/) | Casos de punta a punta compartidos (tests del engine y del pipeline) | — | tests de los tres carriles |

## 1. El DSL

### Forma

La raíz es siempre `{"expr": <Expr>}` (simétrica a `{"code": "..."}` de los baselines). Cada nodo lleva un discriminador `"type"` con el nombre del constructor:

| Nodo | Campos |
|---|---|
| `Literal` | `value` (número, booleano o cadena), `value_type` (`"Int"`, `"Decimal"`, `"Bool"`, `"String"`) |
| `Var` | `name` (`^[a-z_][A-Za-z0-9_]*$`) |
| `UnaryOp` | `op` (`NOT`), `operand` |
| `BinaryOp` | `op` (`+` `-` `*` `/` `%` `>` `<` `>=` `<=` `==` `!=` `AND` `OR`), `left`, `right` |
| `In` | `value`, `options` (lista no vacía de expresiones) |
| `IfThenElse` | `condition`, `then`, `else` |
| `Lam` | `param`, `param_type`, `body` |
| `App` | `fn`, `arg` |

Tipos: `"Int"`, `"Decimal"`, `"Bool"`, `"String"` o `{"from": τ, "to": τ}` para `τ → τ`. Los tipos base son los cuatro primeros; los numéricos, `Int` y `Decimal`.

Ningún nodo admite claves extra. El schema solo usa `anyOf`/`enum`/`$ref` para ser compatible con el modo estricto de *structured output*. Por eso el engine valida lo que el schema no expresa: la consistencia entre `value` y `value_type`, los límites numéricos y que `options` no esté vacía.

### Números

- **`Int`:** entero de 64 bits con signo.
- **`Decimal`:** número decimal exacto. El engine calcula con racionales exactos: `0.1 + 0.2 == 0.3` es `true`.
- **Literales:** `value` es un número JSON. Con `value_type: "Int"`, tiene que ser entero y entrar en 64 bits. Con `value_type: "Decimal"`, puede ser entero o no (`5000` y `0.30` son válidos), con valor absoluto menor a 10^28 y a lo sumo 28 decimales. Un número fuera de esos límites es `INVALID_AST`; uno no entero con `value_type: "Int"` es `LITERAL_TYPE_MISMATCH`.
- **Promoción:** solo dentro de operadores (aritmética, comparaciones, `==`, `!=` e `In`), un `Int` que se combina con un `Decimal` se trata como `Decimal`. En `App` y en `param_type` no hay promoción: pasar un `Int` donde se espera `Decimal` es `ARGUMENT_MISMATCH`.
- **Resultado `Decimal`:** se escribe como texto decimal canónico (ver §3).

### Reglas de tipado

Γ es el entorno de tipos de las variables libres (ver §2, `--env`). Cada regla fallida produce un código de error estable:

| Construcción | Regla | Código si falla | Etapa |
|---|---|---|---|
| Entrada | es JSON | `MALFORMED_JSON` | `parse` |
| Entrada | respeta `ast-schema.json` | `INVALID_AST` | `parse` |
| `Literal` | `value` coincide con `value_type` | `LITERAL_TYPE_MISMATCH` | `parse` |
| Entrada | números dentro de los límites de §1, `options` no vacía | `INVALID_AST` | `parse` |
| `Var` | x ∈ Γ o ligada por un `Lam` que la encierra | `UNBOUND_VARIABLE` | `scope` |
| `+` `-` `*` | `Int × Int → Int`; si algún operando es `Decimal`, `→ Decimal` | `OPERAND_MISMATCH` | `typecheck` |
| `/` | numérico × numérico → `Decimal` (siempre, también entre dos `Int`) | `OPERAND_MISMATCH` | `typecheck` |
| `%` | `Int × Int → Int` (sin `Decimal`) | `OPERAND_MISMATCH` | `typecheck` |
| `>` `<` `>=` `<=` | numérico × numérico → `Bool` | `OPERAND_MISMATCH` | `typecheck` |
| `==` `!=` | `τ × τ → Bool`, τ tipo base; `Int` y `Decimal` se pueden comparar entre sí | `OPERAND_MISMATCH` | `typecheck` |
| `AND` `OR` | `Bool × Bool → Bool` | `OPERAND_MISMATCH` | `typecheck` |
| `NOT` | `Bool → Bool` | `OPERAND_MISMATCH` | `typecheck` |
| `In` | `value : τ` y cada opción `: τ`, τ tipo base (con promoción numérica) `→ Bool` | `OPERAND_MISMATCH` | `typecheck` |
| `IfThenElse` | condición `Bool` | `CONDITION_NOT_BOOL` | `typecheck` |
| `IfThenElse` | `then` y `else` del mismo tipo | `BRANCH_MISMATCH` | `typecheck` |
| `Lam` | el cuerpo tipa en Γ, x:τ (x oculta a una x externa) | — | — |
| `App` | `fn : τ → σ` | `NOT_A_FUNCTION` | `typecheck` |
| `App` | `arg : τ` | `ARGUMENT_MISMATCH` | `typecheck` |
| Programa | el tipo final es un tipo base | `NON_BASE_RESULT` | `typecheck` |

Si hay varios errores, se reporta el primero en el orden de las etapas y, dentro de una etapa, en el orden de recorrido del árbol (izquierda a derecha). El `message` es texto libre para humanos; el campo estable es `code`.

### Semántica de la evaluación

- **Orden:** llamada por valor, de izquierda a derecha. `AND` y `OR` cortocircuitan como en Python: si `left` ya decide el resultado, `right` no se evalúa, así que `x != 0 AND 10 / x > 2` no falla con `x = 0`. `IfThenElse` evalúa solo la rama elegida. `In` evalúa `value` y después las opciones en orden, hasta la primera igual.
- **`/`:** división exacta. `%`: resto con el signo del divisor, igual que `%` de Python entre enteros (`-7 % 3 == 2`).
- **`==` e `In`:** igualdad exacta de valores; `1 == 1.0` es `true`.

Un programa bien tipado todavía puede fallar al ejecutarse. Esos errores son del programa, no del engine:

| Error | Cuándo | Código | Etapa |
|---|---|---|---|
| División por cero | divisor `0` en `/` o `%` | `DIVISION_BY_ZERO` | `execution` |
| Desborde | un resultado `Int` fuera de 64 bits, o un `Decimal` con valor absoluto ≥ 10^28 o denominador (reducido) mayor que 10^28 | `NUMERIC_OVERFLOW` | `execution` |

El límite de `Decimal` existe porque el STLC con funciones de orden superior puede generar cuentas de tamaño exponencial; con el límite, el engine nunca agota la memoria.

## 2. Contrato CLI del engine

```
engine [--env '<objeto JSON>']                   < respuesta_cruda_del_llm
engine [--env '<objeto JSON>'] --print-gamma
```

### `--env`: los datos del caso y la deducción de Γ

Objeto plano `{nombre: valor}`; si se omite, `{}`. **El engine deduce Γ de los valores** (el orquestador nunca decide tipos):

| Valor JSON | Tipo en Γ |
|---|---|
| número entero que entra en 64 bits (`5000`, también `5000.0`) | `Int` |
| número no entero, con valor absoluto menor a 10^28 y a lo sumo 28 decimales (`0.30`, `1250.75`) | `Decimal` |
| `true` / `false` | `Bool` |
| cadena | `String` |
| entero fuera de 64 bits, número fuera de esos límites, `null`, array, objeto, o nombre fuera de `^[a-z_][A-Za-z0-9_]*$` | error de uso (exit 64) |

Γ sale de los datos, no de la regla: el engine nunca infiere el tipo de una variable libre a partir de cómo la usa el LLM. El tipo depende del valor, no de cómo está escrito: `5000.0` es `Int`. Si una variable tiene que ser `Decimal` en todos los escenarios de una regla, sus valores tienen que ser no enteros o la regla tiene que funcionar con cualquiera de los dos tipos (la promoción de §1 lo permite en operadores).

### Modo validación (por defecto)

- **stdin:** los bytes exactos de la respuesta del LLM, sin reparar ni reenvolver. El orquestador no parsea la salida del grupo Tratamiento; el engine es la única frontera de parseo.
- **stdout:** exactamente una línea JSON conforme a [`engine-verdict-schema.json`](./engine-verdict-schema.json), por ejemplo:

  ```json
  {"outcome":"executed","stage":"execution","result":{"type":"Bool","value":true},"error":null}
  {"outcome":"blocked","stage":"typecheck","result":null,"error":{"code":"BRANCH_MISMATCH","message":"then: Int, else: String"}}
  {"outcome":"executed","stage":"execution","result":{"type":"Decimal","value":"1500.5"},"error":null}
  {"outcome":"runtime_error","stage":"execution","result":null,"error":{"code":"DIVISION_BY_ZERO","message":"división por cero"}}
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
| 4 | error del programa al ejecutarse (`DIVISION_BY_ZERO`, `NUMERIC_OVERFLOW`) | veredicto |
| 64 | error de uso: argumentos o `--env` inválidos. Es un bug del orquestador: abortar la corrida | vacío |
| 70 | error interno del engine (no debería ocurrir si el sistema de tipos es sano) | vacío |

### Garantías

- **Determinismo:** mismo stdin + mismo `--env` ⇒ mismo stdout byte a byte. Sin timestamps ni tiempos en la salida.
- **Aislamiento:** sin red y sin leer archivos.
- **Timeout:** lo aplica el orquestador; si vence, registra `outcome: "timeout"`.

## 3. Registro de salida

Un objeto por línea en [`output-record-schema.json`](./output-record-schema.json) (versión `2.0`). Es registro, no medición: no incluye el resultado esperado ni comparaciones. `pass@1` lo calcula el experimento cruzando cada registro con el `expected` de su escenario en el corpus.

- **Generación:** una llamada al LLM para un caso, un grupo y una repetición. Se identifica por `(run_id, case_id, group, repetition)`. `repetition` empieza en 1 y cuenta las llamadas de ese caso y grupo dentro de la corrida; cuántas repeticiones se hacen es configuración de la corrida, no del contrato.
- **Un registro por escenario:** cada generación produce exactamente un registro por escenario del caso, en el orden del caso, con su `scenario_id`. La **misma** respuesta del LLM (`llm_raw`) se ejecuta contra el `env` de cada escenario: nunca se vuelve a llamar al LLM por escenario.
- **Bloqueos repetidos:** `llm_error` y `blocked` no dependen de los valores del escenario (`parse`, `scope` y `typecheck` solo miran el texto y Γ, que es el mismo en todos los escenarios, §5). Por eso se repiten iguales en todos los registros de la generación. Para contar por generación hay que agrupar por la clave de arriba.
- **`duration_ms` por escenario:** tiempo de lo que produjo ese registro. En el Tratamiento, la invocación del engine con el `env` de ese escenario. En Baseline 1, la ejecución en el sandbox. En Baseline 2, el análisis estático (se hace una vez por generación y se suma en cada escenario) más la ejecución de ese escenario.

- **Tratamiento:** el orquestador copia `outcome`, `stage`, `result` y `error` del veredicto sin transformarlos. Exit 4 trae su propio veredicto `runtime_error`, que también se copia. Exit 70 ⇒ `outcome: "runtime_error"`, `stage: "execution"`, `error.code: "ENGINE_INTERNAL"`.
- **Baselines:** mismo vocabulario de etapas. Los números no enteros de `env` les llegan como `decimal.Decimal` exactos y los enteros como `int`; el prompt se lo dice. Baseline 1 llega siempre a `execution`; Baseline 2 recorre `parse` (`ast.parse`) → `typecheck` (mypy) → `execution`. `error.code` es el nombre de la excepción o herramienta (`SyntaxError`, `KeyError`, `mypy`). Un `decimal.Decimal` se registra como `Decimal` con su texto canónico; cualquier otro resultado que no sea `int`, `bool` o `str` (incluido `float`) se registra como `{"type": "Other", "value": repr(x)}`.
- **Texto canónico de `Decimal`:** notación posicional sin exponente, sin ceros finales ni punto final, con `-` solo si el valor es negativo (`"1500.5"`, `"0.3"`, `"-2"`, `"0"`). Si el valor exacto no termina en decimal (`10 / 3`), se redondea a 28 dígitos significativos con *half-even*, como el contexto por defecto de `decimal` en Python: `"3.333333333333333333333333333"`. El redondeo ocurre solo al escribir el resultado; los cálculos y las comparaciones son exactos.
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
| `rule-008` | `cuota <= ingreso * 0.30` (promoción Int → Decimal) | `executed`, `Bool true`, exit 0 |
| `rule-009` | `NOT` y `!=` | `executed`, `Bool true`, exit 0 |
| `rule-010` | `IN ["Gold", "Platinum"]` | `executed`, `Bool true`, exit 0 |
| `rule-011` | `deuda / ingreso` con `ingreso = 0` | `runtime_error`, `DIVISION_BY_ZERO`, exit 4 |
| `rule-012` | la misma división con guarda `ingreso != 0 AND ...` (cortocircuito) | `executed`, `Bool false`, exit 0 |
| `rule-013` | `%` sobre `Decimal` | `typecheck`, `OPERAND_MISMATCH`, exit 3 |
| `rule-014` | `monto / 12`, resultado `Decimal` que no termina | `executed`, `Decimal "833.3333333333333333333333333"`, exit 0 |
| `rule-015` | literal `700.5` con `value_type: "Int"` | `parse`, `LITERAL_TYPE_MISMATCH`, exit 1 |

Los casos 001–005 vienen de [`prototype/guia_fixtures_pruebas.md`](../prototype/guia_fixtures_pruebas.md); los 008–015 prueban la extensión del DSL ([`docs/dsl-extension.md`](../docs/dsl-extension.md)). `python_code` se copió tal cual de esa guía; el carril de baselines decide si le agrega la firma tipada que exige Baseline 2.

## 5. Casos de entrada

Lo que el orquestador recibe por cada regla del corpus, en [`case-schema.json`](./case-schema.json). Sigue la idea de las pruebas de decisión DMN: la regla viene con sus escenarios de validación.

| Campo | Contenido | Lo usa |
|---|---|---|
| `case_id` | identificador de la regla | orquestador (va al registro) |
| `description` | la regla en lenguaje natural (lo que recibe el LLM) | orquestador |
| `scenarios[].scenario_id` | identificador del escenario, único dentro del caso | orquestador (va al registro) |
| `scenarios[].env` | datos del escenario, tal como se pasan a `--env` y al sandbox | orquestador |
| `scenarios[].expected` | resultado esperado, con la forma de `Result` | experimento |
| otros (`category`, `domain`, `source`, `gamma`, `canonical_ast`, `canonical_python`) | los define el corpus ([`docs/corpus.md`](../docs/corpus.md)) | experimento |

Antes de llamar al LLM, el orquestador valida lo que el schema no expresa, y si algo falla aborta la corrida (es un error del corpus, no del modelo):

- los `scenario_id` no se repiten dentro del caso;
- Γ, deducido por el engine (`--print-gamma`) del `env` de cada escenario, es **el mismo** en todos los escenarios. Ese Γ común es el que va en el prompt.

Las fixtures de §4 son otra cosa: prueban el engine y el pipeline con una respuesta del LLM ya escrita (`llm_raw`) y un solo `env`.
