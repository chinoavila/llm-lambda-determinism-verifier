# Guía del motor Haskell (`engine/`)

El motor recibe la respuesta del LLM (un AST en JSON, ver [`guia-ast-schema.md`](guia-ast-schema.md)) y los datos del caso (`--env`). Verifica que la regla tenga sentido y, solo si pasa todas las verificaciones, la ejecuta.

## El recorrido

La respuesta del LLM pasa por cuatro etapas, en este orden. Si una etapa encuentra un error, el programa se bloquea ahí y no sigue.

| Etapa | Archivo | Qué revisa |
|-------|---------|------------|
| 1. parse | `Json.hs` | Que la respuesta sea JSON válido y tenga la forma del schema |
| 2. scope | `TypeCheck.hs` | Que todas las variables existan en los datos del caso |
| 3. typecheck | `TypeCheck.hs` | Que los tipos encajen (por ejemplo, no sumar un número con un texto) |
| 4. execution | `Eval.hs` | Calcula el resultado con los valores reales |

`Cli.hs` une las cuatro etapas, y `Main.hs` es la puerta de entrada del programa.

## Los archivos, en orden de uso

### `src/Engine/Types.hs`: las piezas

Define en Haskell las mismas reglas que [`contracts/ast-schema.json`](../contracts/ast-schema.json): los cuatro tipos básicos (`Int`, `Decimal`, `Bool`, `String`), el tipo función y las 8 formas de expresión (`Literal`, `Var`, `BinaryOp`, `UnaryOp`, `In`, `IfThenElse`, `Lam`, `App`). Todos los demás archivos trabajan con estas piezas.

### `src/Engine/Env.hs`: el entorno

Un entorno es una lista de pares (nombre de variable, dato). Se usa de dos formas, las dos armadas a partir del `env` del caso:

- `Env Type`: nombre y tipo, por ejemplo `credit_score` es `Int`. Lo usa `TypeCheck.hs`.
- `Env LiteralValue`: nombre y valor, por ejemplo `credit_score` vale `750`. Lo usa `Eval.hs`.

### `src/Engine/Number.hs`: los números

Controla los límites (Int de 64 bits, Decimal de hasta 28 dígitos), lee los números del JSON en forma exacta y escribe los Decimal como texto. No usa `Double` (punto flotante), porque aproxima: `0.1 + 0.2` daría `0.30000000000000004`. Usa `Rational`, que es una fracción exacta.

### `src/Engine/Json.hs`: etapa 1, parse

Convierte el texto JSON del LLM en las piezas de `Types.hs`. Además de las reglas del schema, controla lo que el schema no puede: que `value` coincida con `value_type`, los límites numéricos y que las opciones de `In` no estén vacías.

Errores: `MALFORMED_JSON`, `INVALID_AST`, `LITERAL_TYPE_MISMATCH`.

### `src/Engine/TypeCheck.hs`: etapas 2 y 3, scope y typecheck

Revisa la regla sin ejecutarla. Primero, que toda variable usada exista en el entorno (`scopeCheck`). Después calcula el tipo de cada expresión y verifica que encajen (`typeOf`). Por último exige que el resultado final sea un tipo básico (`checkProgram`).

Errores: `UNBOUND_VARIABLE` (scope); `OPERAND_MISMATCH`, `CONDITION_NOT_BOOL`, `BRANCH_MISMATCH`, `NOT_A_FUNCTION`, `ARGUMENT_MISMATCH`, `NON_BASE_RESULT` (typecheck).

### `src/Engine/Eval.hs`: etapa 4, execution

Ejecuta la regla con los valores del caso (`eval`, `evalProgram`) y hace las cuentas de cada operador (`applyOp`). Las cuentas son exactas.

Errores: `DIVISION_BY_ZERO`, `NUMERIC_OVERFLOW`. Los errores internos `Stuck...` no deberían ocurrir nunca: si aparecen, es un bug del motor.

### `src/Engine/Cli.hs`: une las etapas

`validate` pasa la respuesta por las cuatro etapas. `run` lee los argumentos (`--env`, `--print-gamma`), llama a `validate` y arma la salida: una línea JSON con el veredicto y un código de salida.

| Código | Significado |
|--------|-------------|
| 0 | Ejecutado |
| 1 | Bloqueado en parse |
| 2 | Bloqueado en scope |
| 3 | Bloqueado en typecheck |
| 4 | Error al ejecutar (división por cero, desborde) |
| 64 | Error de uso (argumentos o `--env` inválidos) |
| 70 | Error interno del motor |

### `app/Main.hs`: la puerta de entrada

Es el único archivo con efectos: lee los argumentos y la entrada estándar, llama a `run` y escribe el resultado. Todo el resto del motor son funciones puras, que reciben datos y devuelven datos. Separar la parte pura de la parte con efectos es una idea central de la programación funcional.

## Ejemplo de recorrido

Caso [`contracts/fixtures/rule-001.json`](../contracts/fixtures/rule-001.json): "Aprobar el préstamo si el puntaje crediticio es mayor a 700 y el cliente no tiene morosidades previas". Los datos son `credit_score = 750` y `has_defaults = false`. El LLM responde con un AST que equivale a `credit_score > 700 AND has_defaults == false`.

1. **parse** (`Json.hs`): el JSON es válido y tiene la forma del schema.
2. **scope** (`TypeCheck.hs`): `credit_score` y `has_defaults` existen en los datos.
3. **typecheck** (`TypeCheck.hs`): `credit_score > 700` es `Bool`, `has_defaults == false` es `Bool`, y el `AND` de dos `Bool` es `Bool`.
4. **execution** (`Eval.hs`): `750 > 700` da `true`, `false == false` da `true`, y `true AND true` da `true`.

Veredicto: `executed`, resultado `Bool true`, código de salida 0.