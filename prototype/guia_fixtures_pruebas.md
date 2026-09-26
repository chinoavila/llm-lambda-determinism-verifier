# Guía de Fixtures Punta a Punta para el Modelo Computacional Neuro-Simbólico
**Basado en:** *DI_PF_TFI_ENTREGA1_v5.pdf*  
**Dominio:** Verificación formal de reglas de negocio determinísticas mediante Cálculo Lambda Simplemente Tipado (STLC) y Programación Funcional.

---

## 1. Introducción y Marco Metodológico

Esta guía define el conjunto estandarizado de **5 *fixtures* de prueba de punta a punta** diseñadas para evaluar empíricamente el modelo computacional neuro-simbólico propuesto en el trabajo de investigación *DI_PF_TFI_ENTREGA1_v5.pdf*.

El objetivo principal de estas *fixtures* es verificar el comportamiento del **orquestador del pipeline**, la capacidad de intercepción del **motor de validación simbólico** (implementado en Haskell sobre un Lenguaje de Dominio Específico - DSL con Tipos de Datos Algebraicos - ADT) y contrastar su desempeño frente a los dos grupos de control (*Baselines*).

### Taxonomía de Errores
Las *fixtures* adaptan la clasificación de errores del benchmark $\lambda\text{Repair}$ (*Zhang et al., 2026*) y organizan los escenarios de decisión mediante esquemas JSON inspirados en las tablas de decisión DMN (*Cherednichenko y Maliarenko, 2025*):
1. **Éxito (`SUCCESS`):** Reglas válidas que satisfacen el sistema de tipos y la semántica del dominio.
2. **Errores Sintácticos/Estructurales (`SYNTAX_ERROR`):** Malformaciones en la estructura JSON del AST o violaciones del léxico del lenguaje.
3. **Errores de Tipos y Alcance (`TYPE_ERROR`):** Incompatibilidad de tipos entre operandos o invocación de variables no declaradas en el entorno ($\Gamma$).
4. **Inconsistencias Lógicas / Estructura STLC (`LOGIC_ERROR`):** Divergencia de tipos en ramas condicionales (`IfThenElse`) o fallos semánticos durante la ejecución.

---

## 2. Grupos Experimentales Evaluados

El pipeline somete cada *fixture* a tres configuraciones en paralelo:

1. **Grupo Tratamiento (Guardrail Funcional STLC - Haskell):**
   * El LLM serializa la regla en un Árbol de Sintaxis Abstracta (AST) en formato JSON.
   * El motor simbólico en Haskell ejecuta comprobación de tipos (*typechecking*) y de ámbito (*scope checking*) estático sobre el STLC antes de autorizar cualquier ejecución.
2. **Baseline 1 (Control Libre en Python):**
   * El LLM genera directamente un script imperativo en Python sin capa de validación.
   * La regla se evalúa dinámicamente mediante `exec()`. Las alucinaciones se manifiestan directamente como excepciones en tiempo de ejecución (*runtime errors*).
3. **Baseline 2 (Control Estructurado en Python / Analizadores Estáticos):**
   * El LLM genera código Python imperativo, pero este es auditado estáticamente antes de su ejecución mediante herramientas estándar del ecosistema Python (inspección de AST y verificador MyPy).
   * Permite aislar si los beneficios provienen de cualquier validación estática o específicamente de las restricciones del cálculo lambda.

---

## 3. Especificación Detallada de las Fixtures de Prueba

### Fixture 1: `RULE-001` — Regla Válida de Aprobación Crediticia
* **Categoría $\lambda\text{Repair}$:** `SUCCESS`
* **Descripción del Dominio:** Aprobar un préstamo si el puntaje crediticio (`credit_score`) es mayor a 700 Y el cliente no posee morosidades previas (`has_defaults == False`).
* **Entorno de Datos ($\Gamma$):**
  ```json
  {
    "credit_score": 750,
    "monthly_income": 5000,
    "has_defaults": false,
    "customer_tier": "Gold"
  }
  ```
* **Resultado Esperado (*Ground Truth*):** `True`

#### Representación AST JSON (Tratamiento STLC)
```json
{
  "type": "BinaryOp",
  "op": "AND",
  "left": {
    "type": "BinaryOp", "op": ">",
    "left": {"type": "Var", "name": "credit_score"},
    "right": {"type": "Literal", "value": 700, "value_type": "Int"}
  },
  "right": {
    "type": "BinaryOp", "op": "==",
    "left": {"type": "Var", "name": "has_defaults"},
    "right": {"type": "Literal", "value": false, "value_type": "Bool"}
  }
}
```

#### Código Generado (Baselines 1 y 2)
```python
def evaluate_rule(data):
    return data['credit_score'] > 700 and not data['has_defaults']
```

#### Comportamiento Esperado por Grupo
* **Tratamiento (STLC Haskell):** Infiere el tipo `Bool`. Invariablemente aprobado en verificación estática. Se ejecuta determinísticamente retornando `True` ($pass@1 = 1.0$).
* **Baseline 1 (Python Libre):** Se ejecuta dinámicamente y retorna `True` ($pass@1 = 1.0$).
* **Baseline 2 (Python Estructurado):** Valida la sintaxis e inferencia de tipos correctamente. Retorna `True`.

---

### Fixture 2: `RULE-002` — Error Sintáctico / Estructural
* **Categoría $\lambda\text{Repair}$:** `SYNTAX_ERROR`
* **Descripción del Dominio:** Alucinación del LLM donde se omiten tokens estructurales esenciales del lenguaje o la estructura del JSON del AST está malformada.
* **Entorno de Datos ($\Gamma$):** `{"credit_score": 750}`
* **Resultado Esperado:** Intercepción estática previa a la ejecución.

#### Representación AST JSON (Tratamiento STLC)
```json
{
  "type": "BinaryOp",
  "op": ">",
  "left": "credit_score", 
  "right": {"type": "Literal", "value": 700, "value_type": "Int"}
}
```
*Nota: `left` es una cadena directa en lugar de un objeto primitivo `{"type": "Var", "name": "credit_score"}`.*

#### Código Generado (Baselines 1 y 2)
```python
def evaluate_rule(data) # Error sintáctico: falta el delimitador ':'
    return data['credit_score'] > 700
```

#### Comportamiento Esperado por Grupo
* **Tratamiento (STLC Haskell):** El deserializador del AST JSON falla inmediatamente marcando nodo no válido. Interceptado en validación estática (0 fallos en runtime).
* **Baseline 1 (Python Libre):** Intenta compilar con `exec()` y colapsa lanzando una excepción `SyntaxError` en tiempo de ejecución.
* **Baseline 2 (Python Estructurado):** El módulo `ast.parse()` de Python detecta la falla de sintaxis estáticamente e impide la ejecución.

---

### Fixture 3: `RULE-003` — Error de Tipos (Incompatibilidad STLC)
* **Categoría $\lambda\text{Repair}$:** `TYPE_ERROR`
* **Descripción del Dominio:** Alucinación en la que el LLM intenta comparar una variable numérica entera (`credit_score`) con una constante alfanumérica (`"High"`).
* **Entorno de Datos ($\Gamma$):** `{"credit_score": 750}`
* **Resultado Esperado:** Intercepción en el typechecker estático.

#### Representación AST JSON (Tratamiento STLC)
```json
{
  "type": "BinaryOp",
  "op": ">",
  "left": {"type": "Var", "name": "credit_score"},
  "right": {"type": "Literal", "value": "High", "value_type": "String"}
}
```

#### Código Generado (Baselines 1 y 2)
```python
def evaluate_rule(data):
    return data['credit_score'] > 'High'
```

#### Comportamiento Esperado por Grupo
* **Tratamiento (STLC Haskell):** El verificador de tipos detecta `BinaryOp(>)` aplicado sobre `(Int, String)`. Rechaza la operación lanzando: `Type Mismatch: Cannot compare Int with String`.
* **Baseline 1 (Python Libre):** Inicia la ejecución y falla en runtime lanzando `TypeError: '>' not supported between instances of 'int' and 'str'`.
* **Baseline 2 (Python Estructurado):** El verificador estático (MyPy / AST Inspector) analiza los tipos del diccionario y bloquea la ejecución.

---

### Fixture 4: `RULE-004` — Variable No Declarada / Alcance
* **Categoría $\lambda\text{Repair}$:** `TYPE_ERROR` (Unbound Variable)
* **Descripción del Dominio:** El LLM alucina e inventa una variable (`risk_level`) que no existe en el esquema/diccionario oficial del sistema.
* **Entorno de Datos ($\Gamma$):** `{"credit_score": 750, "monthly_income": 5000}`
* **Resultado Esperado:** Intercepción en la comprobación de ámbito (*scope checking*).

#### Representación AST JSON (Tratamiento STLC)
```json
{
  "type": "BinaryOp",
  "op": "==",
  "left": {"type": "Var", "name": "risk_level"},
  "right": {"type": "Literal", "value": "Low", "value_type": "String"}
}
```

#### Código Generado (Baselines 1 y 2)
```python
def evaluate_rule(data):
    return data['risk_level'] == 'Low'
```

#### Comportamiento Esperado por Grupo
* **Tratamiento (STLC Haskell):** El *scope checker* valida $risk\_level \in \text{dom}(\Gamma)$. Al no encontrarla, rechaza el AST con: `Type Error: Unbound variable 'risk_level' in environment`.
* **Baseline 1 (Python Libre):** Se ejecuta e intenta acceder al diccionario, produciendo una excepción dinámica no controlada `KeyError: 'risk_level'`.
* **Baseline 2 (Python Estructurado):** El analizador de claves del entorno de Python identifica la variable no definida y bloquea la ejecución estáticamente.

---

### Fixture 5: `RULE-005` — Inconsistencia Lógica / Divergencia de Tipos en Ramas `IfThenElse`
* **Categoría $\lambda\text{Repair}$:** `LOGIC_ERROR` / Branch Type Mismatch (Específico de STLC)
* **Descripción del Dominio:** Expresión condicional donde la rama `then` retorna un entero (`500`) y la rama `else` retorna un texto (`"Rejected"`).
* **Entorno de Datos ($\Gamma$):** `{"credit_score": 650}` (Satisface la rama `else`)
* **Monto Esperado del Negocio:** `100` (El esperado correcto según regla)

#### Representación AST JSON (Tratamiento STLC)
```json
{
  "type": "IfThenElse",
  "condition": {
    "type": "BinaryOp", "op": ">",
    "left": {"type": "Var", "name": "credit_score"},
    "right": {"type": "Literal", "value": 700, "value_type": "Int"}
  },
  "then": {"type": "Literal", "value": 500, "value_type": "Int"},
  "else": {"type": "Literal", "value": "Rejected", "value_type": "String"}
}
```

#### Código Generado (Baselines 1 y 2)
```python
def evaluate_rule(data):
    if data['credit_score'] > 700:
        return 500
    else:
        return "Rejected"
```

#### Comportamiento Esperado por Grupo
* **Tratamiento (STLC Haskell):** La regla tipada del cálculo lambda para condicionales exige que $\text{type}(then) == \text{type}(else)$. Al detectar `Int` vs `String`, rechaza el código estáticamente por heterogeneidad de tipos en ramas.
* **Baseline 1 (Python Libre):** Se ejecuta dinámicamente y retorna `"Rejected"`. Provoca una falla de lógica silenciosa o un colapso posterior (*downstream*) cuando otros sistemas intentan procesar matemáticamente el valor de retorno.
* **Baseline 2 (Python Estructurado):** Python soporta retornos de tipo unión (`Union[int, str]`). La herramienta de análisis estático considera que la sintaxis y los tipos son válidos en Python, por lo que **permite la ejecución**, derivando en una **falla lógica silenciosa**.

---

## 4. Matriz Comparativa de Resultados de Ejecución

| Fixture ID | Categoría $\lambda\text{Repair}$ | Tratamiento (STLC Haskell) | Baseline 2 (Python Estructurado) | Baseline 1 (Python Libre) | Migración de Error Lograda |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **`RULE-001`** | `SUCCESS` | **Aprobado** (`Bool`) | **Aprobado** | **Aprobado** | N/A (Éxito de Negocio) |
| **`RULE-002`** | `SYNTAX_ERROR` | **Interceptado** (AST Validation) | **Interceptado** (AST Python) | Falla Runtime (`SyntaxError`) | **Runtime $\rightarrow$ Validación Estática** |
| **`RULE-003`** | `TYPE_ERROR` | **Interceptado** (`Int` vs `String`) | **Interceptado** (MyPy / Types) | Falla Runtime (`TypeError`) | **Runtime $\rightarrow$ Validación Estática** |
| **`RULE-004`** | `TYPE_ERROR` | **Interceptado** (Variable $\notin \Gamma$) | **Interceptado** (Scope Check) | Falla Runtime (`KeyError`) | **Runtime $\rightarrow$ Validación Estática** |
| **`RULE-005`** | `LOGIC_ERROR` | **Interceptado** (Branch Mismatch) | **Leakeado** (Permite `Union[int, str]`) | Falla Lógica / Runtime | **Runtime $\rightarrow$ Validación Estática (Exclusivo STLC)** |

---

## 5. Guía de Integración en el Pipeline Computacional

Estas 5 *fixtures* están codificadas y listas para su ejecución automatizada dentro del prototipo `pipeline_prototype-v2.py`.

Para ejecutar la suite de pruebas y reproducir la cuantificación de métricas ($pass@1$, tasa de intercepción estática y tiempo de latencia):

```bash
python3 /workspace/scratch/pipeline_prototype_v5.py
```

El script imprimirá por pantalla el reporte detallado por cada caso de prueba junto con la matriz agregada de migración de errores.
