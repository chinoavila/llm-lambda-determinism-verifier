# Guía para leer `contracts/ast-schema.json`

El archivo [`contracts/ast-schema.json`](../contracts/ast-schema.json) describe la forma que tiene que tener la respuesta del LLM. El pipeline le envía este schema al LLM como parte de sus instrucciones.

## La raíz (líneas 6 a 9)

- `"type": "object"`: el LLM tiene que responder con un objeto JSON, es decir, algo entre llaves `{ }`.
- `"properties": { "expr": ... }`: el objeto tiene una única propiedad, llamada `expr`. Su valor tiene que ser una expresión, cuya forma se define más adelante en `$defs/Expr` (`$ref` significa "ver la definición tal"). Esa expresión puede contener otras expresiones adentro, y así se forma el árbol (AST).
- `"required": ["expr"]`: la propiedad `expr` es obligatoria. Una respuesta vacía `{}` es inválida.
- `"additionalProperties": false`: no se permiten propiedades extra. Si el LLM agrega, por ejemplo, `"explicacion": "..."`, la respuesta es inválida.



## Las definiciones (`$defs`, líneas 10 a 121)

`$defs` es un glosario: cada pieza se define una vez y en el resto del archivo se la nombra con `"$ref": "#/$defs/Nombre"`.

### Definiciones de apoyo

- **`Name`** (línea 11): regla para los nombres de variables. Un nombre tiene que ser un texto que empiece con minúscula o `_`, seguido de letras, números o `_`. Cumple la regla: `credit_score`. No la cumplen: `CreditScore`, `2monto`.
- **`BaseType`** (línea 12): regla para los tipos básicos. Un tipo básico solo puede ser `"Int"` (entero), `"Decimal"`, `"Bool"` (verdadero o falso) o `"String"` (texto).
- **`Type`** (líneas 13 a 26): regla para los tipos. Un tipo tiene que cumplir una de dos opciones (`anyOf`):
  1. ser un tipo básico, es decir, cumplir la regla `BaseType`; o
  2. ser un tipo de función, `{ "from": ..., "to": ... }`, donde `from` es el tipo de lo que la función recibe y `to` el de lo que devuelve. Ejemplo: `{ "from": "Int", "to": "Bool" }` describe una función que recibe un entero y devuelve verdadero o falso.

  Como `from` y `to` tienen que cumplir a su vez la regla `Type` (recursividad), una función puede recibir o devolver otra función. Esta regla solo se usa en `Lam`.



### `Expr`: las 8 formas de una expresión (líneas 27 a 38)


### 1. `Literal` (líneas 39 a 48)

Regla para los valores fijos. Un literal tiene que ser un objeto con exactamente tres campos obligatorios:

- `type`: tiene que valer `"Literal"`. Indica qué forma de expresión es.
- `value`: el valor; tiene que ser un número, un booleano o un texto.
- `value_type`: el tipo del valor; tiene que cumplir la regla `BaseType`.

Ejemplo: `{ "type": "Literal", "value": 700, "value_type": "Int" }`.

Hace falta `value_type` porque JSON no distingue entre entero y decimal. El schema no puede comprobar que `value` y `value_type` coincidan; eso lo controla el motor (`LITERAL_TYPE_MISMATCH`).




### 2. `Var` (líneas 49 a 57)

Regla para usar una variable. Tiene que ser un objeto con exactamente dos campos obligatorios:

- `type`: tiene que valer `"Var"`.
- `name`: el nombre de la variable; tiene que cumplir la regla `Name`.

Ejemplo: `{ "type": "Var", "name": "credit_score" }`.

No lleva valor: el valor sale de los datos del caso (`env`). El schema no puede comprobar que la variable exista en esos datos; eso lo controla el motor (`UNBOUND_VARIABLE`).





### 3. `BinaryOp` (líneas 58 a 68)

Regla para las operaciones entre dos expresiones. Tiene que ser un objeto con exactamente cuatro campos obligatorios:

- `type`: tiene que valer `"BinaryOp"`.
- `op`: el operador; tiene que ser uno de estos 13: aritméticos (`+ - * / %`), comparaciones (`> < >= <= == !=`) o lógicos (`AND OR`).
- `left` y `right`: los dos lados de la operación; cada uno tiene que cumplir la regla `Expr`.

Ejemplo: `credit_score > 700` es `{ "type": "BinaryOp", "op": ">", "left": { "type": "Var", "name": "credit_score" }, "right": { "type": "Literal", "value": 700, "value_type": "Int" } }`.

Como `left` y `right` son expresiones, pueden ser otros `BinaryOp` (recursividad). Así se arman reglas compuestas, como `credit_score > 700 AND has_defaults == false`.

El schema no puede comprobar que la operación tenga sentido (por ejemplo, comparar un número con un texto); eso lo controla el motor (`OPERAND_MISMATCH`).






### 4. `UnaryOp` (líneas 69 a 78)

Regla para las operaciones sobre una sola expresión. Tiene que ser un objeto con exactamente tres campos obligatorios:

- `type`: tiene que valer `"UnaryOp"`.
- `op`: el operador; el único permitido es `NOT` (negación).
- `operand`: la expresión a la que se aplica el operador; tiene que cumplir la regla `Expr`.

Ejemplo: "no tiene morosidades" es `{ "type": "UnaryOp", "op": "NOT", "operand": { "type": "Var", "name": "has_defaults" } }`.

El schema no puede comprobar que `operand` sea verdadero o falso (por ejemplo, acepta `NOT 700`); eso lo controla el motor (`OPERAND_MISMATCH`).





### 5. `In` (líneas 79 a 88)

Regla para preguntar si un valor está en una lista de opciones. El resultado es verdadero o falso. Tiene que ser un objeto con exactamente tres campos obligatorios:

- `type`: tiene que valer `"In"`.
- `value`: lo que se busca; tiene que cumplir la regla `Expr`.
- `options`: la lista donde se busca (`"type": "array"`); cada elemento (`items`) tiene que cumplir la regla `Expr`.

Ejemplo: "¿el nivel del cliente es Gold o Platinum?" es `{ "type": "In", "value": { "type": "Var", "name": "customer_tier" }, "options": [ { "type": "Literal", "value": "Gold", "value_type": "String" }, { "type": "Literal", "value": "Platinum", "value_type": "String" } ] }`.

Es un atajo de varios `==` unidos con `OR`.

El schema no puede comprobar que la lista no esté vacía (lo controla el motor con `INVALID_AST`) ni que el valor y las opciones sean del mismo tipo (lo controla el motor con `OPERAND_MISMATCH`).










### 6. `IfThenElse` (líneas 89 a 99)

Regla para elegir entre dos resultados según una condición ("si... entonces... si no..."). Tiene que ser un objeto con exactamente cuatro campos obligatorios:

- `type`: tiene que valer `"IfThenElse"`.
- `condition`: la condición; tiene que cumplir la regla `Expr`.
- `then`: el resultado si la condición es verdadera; tiene que cumplir la regla `Expr`.
- `else`: el resultado si la condición es falsa; tiene que cumplir la regla `Expr`.

Ejemplo: "si el ingreso mensual supera 10000, la tasa es 5; si no, es 3" es `{ "type": "IfThenElse", "condition": { "type": "BinaryOp", "op": ">", "left": { "type": "Var", "name": "monthly_income" }, "right": { "type": "Literal", "value": 10000, "value_type": "Int" } }, "then": { "type": "Literal", "value": 5, "value_type": "Int" }, "else": { "type": "Literal", "value": 3, "value_type": "Int" } }`.

El schema no puede comprobar que la condición sea verdadera o falsa (lo controla el motor con `CONDITION_NOT_BOOL`) ni que `then` y `else` sean del mismo tipo (lo controla el motor con `BRANCH_MISMATCH`).












### 7. `Lam` (líneas 100 a 110)

Regla para definir una función de un solo parámetro. El nombre viene de "lambda" (cálculo lambda). Tiene que ser un objeto con exactamente cuatro campos obligatorios:

- `type`: tiene que valer `"Lam"`.
- `param`: el nombre del parámetro; tiene que cumplir la regla `Name`.
- `param_type`: el tipo del parámetro; tiene que cumplir la regla `Type`. Es obligatorio: el LLM tiene que declarar el tipo.
- `body`: el cuerpo de la función, es decir, lo que calcula usando el parámetro; tiene que cumplir la regla `Expr`.

Ejemplo: la función "x → x > 18" (recibe un entero `x` y dice si es mayor a 18) es `{ "type": "Lam", "param": "x", "param_type": "Int", "body": { "type": "BinaryOp", "op": ">", "left": { "type": "Var", "name": "x" }, "right": { "type": "Literal", "value": 18, "value_type": "Int" } } }`.

Una función sola no da un resultado: hay que aplicarla con `App`. Si el programa completo termina siendo una función, el motor lo rechaza (`NON_BASE_RESULT`). Ninguna regla del corpus ni de las fixtures usa `Lam`.













### 8. `App` (líneas 111 a 120)

Regla para aplicar una función a un argumento, es decir, usarla con un valor concreto. Tiene que ser un objeto con exactamente tres campos obligatorios:

- `type`: tiene que valer `"App"`.
- `fn`: la función que se aplica (normalmente un `Lam`); tiene que cumplir la regla `Expr`.
- `arg`: el argumento que se le pasa; tiene que cumplir la regla `Expr`.

Ejemplo: aplicar la función "x → x > 18" a la variable `edad` equivale a preguntar "¿`edad` > 18?": `{ "type": "App", "fn": <el Lam del ejemplo anterior>, "arg": { "type": "Var", "name": "edad" } }`.

El schema no puede comprobar que `fn` sea realmente una función (lo controla el motor con `NOT_A_FUNCTION`) ni que el argumento sea del tipo que la función espera (lo controla el motor con `ARGUMENT_MISMATCH`).

La línea 121 cierra `$defs`, y la 123 cierra el schema.