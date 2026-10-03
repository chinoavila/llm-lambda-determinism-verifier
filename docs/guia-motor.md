# Guía del motor Haskell (`engine/`)

## La idea en una frase

El LLM traduce una regla de negocio a un árbol en JSON. El motor revisa ese árbol con varios filtros y **solo si pasa todos** lo ejecuta. Si algo está mal, la regla se bloquea antes de ejecutarse y queda registrado en qué filtro falló.

## Conceptos previos

### Regla de negocio y datos del caso

- La **regla de negocio** es el texto en lenguaje natural que el LLM traduce. Ejemplo: "Aprobar el préstamo si el puntaje crediticio es mayor a 700 y el cliente no tiene morosidades previas".
- Los **datos del caso** (`env`) son los valores concretos de un cliente. Ejemplo: `credit_score = 750`, `has_defaults = false`.

### Qué es un AST

AST significa *Abstract Syntax Tree* (árbol de sintaxis abstracta): una expresión escrita como un árbol. Cada operación es un nodo, y sus partes cuelgan debajo. La regla de arriba, `credit_score > 700 AND has_defaults == false`, queda así:

```text
                AND
              /     \
            >         ==
          /   \      /    \
credit_score  700  has_defaults  false
```

- La **raíz** es la operación principal (`AND`).
- Las **hojas** son variables (`credit_score`) y valores fijos (`700`). No se dividen más.

El árbol deja claro el orden de las operaciones: la regla tiene un solo significado posible. La respuesta del LLM es este árbol escrito en JSON, con objetos dentro de objetos (ver [`guia-ast-schema.md`](guia-ast-schema.md)).

## El recorrido

| Paso | Archivo | Qué hace |
|------|---------|----------|
| 1. parse | `Json.hs` | Convierte el JSON en piezas de Haskell y controla que cumpla con el schema |
| 2. scope | `TypeCheck.hs` | Controla que las variables usadas existan en el `env` |
| 3. typecheck | `TypeCheck.hs` | Controla que las operaciones sean coherentes con los tipos |
| 4. execution | `Eval.hs` | Ejecuta la regla con los valores reales |

Los pasos 1 a 3 son **filtros**: si uno falla, la regla se bloquea y los siguientes no se ejecutan. Recién el paso 4 ejecuta algo.

Además hay archivos que no son pasos: `Types.hs` (el molde), `Env.hs` y `Number.hs` (ayudantes), `Cli.hs` (el coordinador) y `Main.hs` (la puerta de entrada y salida).

## Los archivos

### `src/Engine/Types.hs`: el molde

Define las piezas del motor a partir de lo establecido en [`contracts/ast-schema.json`](../contracts/ast-schema.json): los cuatro tipos básicos (`Int`, `Decimal`, `Bool`, `String`), el tipo función y las 8 formas de expresión (`Literal`, `Var`, `BinaryOp`, `UnaryOp`, `In`, `IfThenElse`, `Lam`, `App`).

No es un paso que se ejecuta: es el vocabulario que usan todos los demás archivos. Está escrito de antemano y es el mismo para cualquier respuesta del LLM.

Las dos describen lo mismo en distinto idioma: `ast-schema.json` le dice al LLM qué forma tiene que tener el JSON, y `Types.hs` le dice a Haskell qué piezas existen. Por ejemplo, el nodo JSON `{"type": "Var", "name": "credit_score"}` corresponde a la pieza `Var "credit_score"`.

### `src/Engine/Env.hs`: la libreta de variables

Un entorno es una lista de pares (nombre de variable, dato). La misma libreta sirve para dos cosas, según qué dato guarde:

- **Con tipos**, la usa `TypeCheck.hs`: `credit_score` es `Int`.
- **Con valores**, la usa `Eval.hs`: `credit_score` vale `750`.

Las dos versiones salen del `env` del caso. Operaciones: `emptyEnv` (libreta vacía), `extend` (agrega un nombre y devuelve una libreta nueva, sin modificar la original), `lookupVar` (busca un nombre) y `names` (lista de nombres).

### `src/Engine/Number.hs`: los números exactos

Controla los límites (Int de 64 bits, Decimal de hasta 28 dígitos), lee los números del JSON en forma exacta y escribe los Decimal como texto. No usa `Double` (punto flotante), porque aproxima: `0.1 + 0.2` daría `0.30000000000000004`. Usa `Rational`, una fracción exacta.

### `src/Engine/Json.hs`: paso 1, parse

Convierte cada nodo del JSON del LLM en la pieza correspondiente de `Types.hs`, y así arma el árbol completo en Haskell.

El control se hace **mientras convierte**: en cada nodo revisa que cumpla con `ast-schema.json`. Si un nodo no cumple, se detiene y no arma ninguna pieza. Nunca llega a los pasos siguientes una pieza mal armada.

Además controla tres cosas que el schema no puede expresar: que `value` coincida con `value_type`, que los números no sean demasiado grandes y que las opciones de un `In` no estén vacías.

| Error | Ejemplo |
|-------|---------|
| `MALFORMED_JSON` | Falta una llave de cierre: no es JSON válido |
| `INVALID_AST` | Tipo de nodo inexistente (`"Variable"`), campo faltante o de más, nombre inválido (`"Credit Score"`), operador inventado |
| `LITERAL_TYPE_MISMATCH` | `"value": "700"` (texto) con `"value_type": "Int"` |

`Json.hs` no controla si la regla tiene sentido: una variable bien escrita pero inexistente, como `edad_del_perro`, pasa este paso.

### `src/Engine/TypeCheck.hs`: pasos 2 y 3, scope y typecheck

Revisa el árbol **sin ejecutar nada**: no mira los valores, solo los tipos.

**Scope.** Controla que cada variable del árbol exista en el `env`. No hace falta que sean las mismas variables: el `env` puede tener variables de más que la regla no usa. En `rule-001`, el `env` tiene `credit_score`, `monthly_income`, `has_defaults` y `customer_tier`, y la regla usa solo dos. Falla si la regla usa una variable que **no** está, por ejemplo `puntaje`: `UNBOUND_VARIABLE`.

**Typecheck.** Controla que las operaciones sean coherentes con los tipos. El LLM **no declara** el tipo de las variables: solo escribe su nombre. Los tipos salen de dos lugares:

- las variables, del `env` (`credit_score` es `Int` porque vale `750`);
- los valores fijos, del `value_type` que escribe el LLM (`700` es `Int`).

Calcula el tipo de cada nodo, de las hojas hacia la raíz. `credit_score > 700` está bien: compara dos números y da `Bool`. `credit_score AND true` está mal, porque `AND` necesita dos `Bool`: `OPERAND_MISMATCH`.

Errores de typecheck: `OPERAND_MISMATCH`, `CONDITION_NOT_BOOL`, `BRANCH_MISMATCH`, `NOT_A_FUNCTION`, `ARGUMENT_MISMATCH`, `NON_BASE_RESULT`.

### `src/Engine/Eval.hs`: paso 4, execution

Ejecuta la regla. Recorre **el mismo árbol** que armó `Json.hs` y que ya revisó `TypeCheck.hs`, pero ahora con los **valores** del `env`. Es el único paso que los usa.

Al ejecutar:

- **Hace las cuentas exactas**, con `Number.hs`.
- **No evalúa lo innecesario.** En un `AND`, si el lado izquierdo da `false`, no mira el derecho; en un `OR`, lo mismo si da `true`. Así, en `cuotas != 0 AND ingreso / cuotas > 1000`, si `cuotas` vale `0` nunca se divide. En un `IfThenElse`, solo ejecuta la rama elegida.
- **Detecta los errores que solo aparecen con valores reales:** `DIVISION_BY_ZERO` y `NUMERIC_OVERFLOW`.
- **Tiene una alarma de seguridad:** los errores internos `Stuck...` no deberían ocurrir nunca, porque los filtros anteriores ya descartaron esos casos. Si aparecen, es un bug del motor (código 70), no del LLM.

### `src/Engine/Cli.hs`: el coordinador

1. **Prepara:** lee los argumentos (`--env`, `--print-gamma`) y arma la libreta de valores. Si los argumentos están mal, corta con el código 64.
2. **Llama a cada paso en orden** (función `validate`): `Json.hs`, `TypeCheck.hs`, `Eval.hs`. Si uno falla, no llama a los siguientes. El árbol se arma una sola vez y se le pasa a los demás.
3. **Arma la respuesta final, sea cual sea el desenlace:** una línea JSON con el veredicto y un código de salida.

Ejemplo de veredicto:

```json
{"outcome":"executed","stage":"execution","result":{"type":"Bool","value":true},"error":null}
```

| Qué pasó | `outcome` | `stage` | Código |
|----------|-----------|---------|--------|
| Se ejecutó bien | `executed` | `execution` | 0 |
| Bloqueada por `Json.hs` | `blocked` | `parse` | 1 |
| Bloqueada por una variable inexistente | `blocked` | `scope` | 2 |
| Bloqueada por los tipos | `blocked` | `typecheck` | 3 |
| Falló al ejecutarse | `runtime_error` | `execution` | 4 |
| Argumentos o `--env` inválidos | | | 64 |
| Error interno del motor | | | 70 |

### `app/Main.hs`: la puerta de entrada y salida

Es el único archivo que interactúa con el exterior:

- **Lee** los argumentos y la respuesta del LLM que llega por la entrada estándar.
- Se los pasa a `run` de `Cli.hs`.
- **Escribe** la línea JSON del veredicto y termina con el código de salida.

No le pasa la respuesta a Python directamente: la escribe en la salida estándar. El orquestador de Python (`pipeline/`) ejecuta el motor como un programa aparte y lee lo que escribió. Si algo falla de forma inesperada, `Main.hs` termina con el código 70.

Todos los demás archivos son **funciones puras**: reciben datos y devuelven datos, sin leer ni escribir nada. Separar la parte pura de la parte con efectos es una idea central de la programación funcional.

## Ejemplo completo: `rule-001`

Caso [`contracts/fixtures/rule-001.json`](../contracts/fixtures/rule-001.json). Datos: `credit_score = 750`, `has_defaults = false`. El LLM responde con el árbol de `credit_score > 700 AND has_defaults == false`.

1. **parse** (`Json.hs`): cada nodo cumple con el schema, y el árbol queda armado en Haskell.
2. **scope** (`TypeCheck.hs`): `credit_score` y `has_defaults` existen en el `env`.
3. **typecheck** (`TypeCheck.hs`): `credit_score > 700` es `Bool`, `has_defaults == false` es `Bool`, y el `AND` de dos `Bool` es `Bool`.
4. **execution** (`Eval.hs`): `750 > 700` da `true`, `false == false` da `true`, y `true AND true` da `true`.

`Cli.hs` arma el veredicto `executed` con resultado `Bool true` y código 0, y `Main.hs` lo escribe para que lo lea el orquestador de Python.

## Por qué importa

En el baseline 1 (Python sin validación), el código que genera el LLM se ejecuta directamente, aunque esté mal. En el motor Haskell, una regla mal armada **se bloquea antes de ejecutarse**, por tres filtros (parse, scope, typecheck), y queda registrado en cuál falló. Esa diferencia es lo que mide el experimento.