# Guía Metodológica para la Construcción del Corpus de Entrada para la Evaluación del Pipeline Neuro-Simbólico

## Resumen Ejecutivo
Esta guía establece la metodología paso a paso para la selección, estructuración, curaduría y auditoría del **corpus de entrada** destinado a la evaluación empírica del pipeline neuro-simbólico definido en **DI_PF_TFI_ENTREGA1_v5.pdf**. 

El objetivo fundamental es evaluar cómo un **capa de validación estática basada en Cálculo Lambda Simplemente Tipado (STLC)** y Tipos de Datos Algebraicos (ADT) en Haskell mitiga las alucinaciones y los errores de ejecución en comparación con entornos imperativos en Python.

---

## Diagrama de Flujo Metodológico

```
[Fase 1: Esquema Γ y Dominio] ──> [Fase 2: Taxonomía λRepair] ──> [Fase 3: Curaduría de Prompts]
                                                                            │
[Fase 6: Evaluación en 3 Grupos] <── [Fase 5: Auditoría Mecánica] <── [Fase 4: Fixtures JSON/AST]
```

---

## Fase 1: Definición del Esquema del Dominio y Entorno de Variables ($\Gamma$)

### Descripción de la Actividad
Establecer el marco formal y la tabla de símbolos del entorno ($\Gamma$) para las reglas de negocio determinísticas. Define las entidades, campos y tipos estáticos finitos (`Int`, `Bool`, `String`) aceptados por el Lenguaje de Dominio Específico (DSL).

### Pasos Operativos
1. **Modelado del Contexto DMN:** Definir la estructura de las tablas de decisión (*Decision Model and Notation*) para el dominio de evaluación (ej. aprobación crediticia, exenciones impositivas, triaje farmacológico).
2. **Definición de Tipos Finitos:** Declarar el tipo estático de cada variable en el entorno $\Gamma = \{x_1: T_1, x_2: T_2, \dots, x_n: T_n\}$.
3. **Esquema de Datos de Entrada (*Payload*):** Crear el contrato JSON contra el cual se evaluará en runtime la regla generada.

### Recursos y Datasets Necesarios
* **Datasets y Esquemas de Referencia:**
  * **DMN XML Schemas (OMG Standard):** Para modelado estandarizado de reglas de decisión.
  * **NL4Opt / ComplexOR Datasets:** Para la extracción de entidades, parámetros y variables reales con tipos estrictos en problemas de optimización y decisión.
* **Herramientas de Software:**
  * **Pydantic / JSON Schema Validator:** Para la definición de la tabla de símbolos y validación de tipos del payload.
  * **Módulo `ast` de Python:** Para la inspección de variables declaradas e identificación de identificadores no reconocidos.

---

## Fase 2: Clasificación según la Taxonomía de Fallos $\lambda\text{Repair}$

### Descripción de la Actividad
Estructurar la distribución de casos del corpus según la categorización sintáctica, de tipos y lógica respaldada por la literatura de evaluación de LLMs.

### Pasos Operativos
1. **Estratificación del Corpus:** Categorizar los casos de prueba en 4 clases disjuntas:
   * **Categoría 0 — Éxito (`SUCCESS`):** Casos donde la regla en lenguaje natural se traduce en un AST/código 100% válido y funcional.
   * **Categoría 1 — Errores Sintácticos (`λRepairSyntax`):** Malformaciones estructurales en la salida del LLM (ej. llaves faltantes en JSON, bloques Python incompletos).
   * **Categoría 2 — Errores de Tipos y Alcance (`λRepairType`):** Operaciones entre tipos incompatibles (ej. `Int` vs `String`) o llamadas a variables no declaradas ($x \notin \Gamma$).
   * **Categoría 3 — Inconsistencias Lógicas y Divergencia de Ramas (`λRepairProg`):** Expresiones condicionales `IfThenElse` con retorno de tipos heterogéneos entre ramas (`then: T1` vs `else: T2`) o contradicciones semánticas.

### Recursos y Datasets Necesarios
* **Datasets y Benchmarks de Referencia:**
  * **Benchmark $\lambda\text{Repair}$ (Zhang et al., 2026):** Para adaptar la clasificación empírica de errores sintácticos, de tipos e inconsistencias lógicas.
  * **HaluEval 2.0 / FELM (Factuality Evaluation for LLMs):** Para extraer patrones comunes de alucinación contextual y de facticidad.
* **Herramientas de Software:**
  * **Pipeline de Logging y Clasificación Automatizada:** Scripts para etiquetar eventos de compilación y excepciones.

---

## Fase 3: Curaduría de Prompts en Lenguaje Natural y *Ground Truth*

### Descripción de la Actividad
Redactar los enunciados de entrada en lenguaje natural (simulando requerimientos del usuario) y construir los pares de referencia (*ground truth*) tanto en el AST funcional como en código Python imperativo.

### Pasos Operativos
1. **Redacción de Prompts Ambiguos y Directos:** Crear solicitudes que pongan a prueba los límites de comprensión del modelo.
2. **Construcción del AST Canónico (Tratamiento STLC):** Diseñar el árbol de sintaxis abstracta en JSON correspondiente al cálculo lambda tipado.
3. **Construcción del Código Python Canónico (Baselines):** Escribir la función de referencia `evaluate_rule(data)` equivalente.
4. **Balanceo de Respuestas:** Garantizar un equilibrio 50/50 en los resultados de salida (`True`/`False` o montos específicos) para evitar sesgos de medición.

### Recursos y Datasets Necesarios
* **Datasets y Benchmarks de Referencia:**
  * **GSM8K / MATH-500 / FormalStep (Liu et al., 2025):** Para formulaciones analíticas y deducciones matemáticas paso a paso.
  * **MindGames / ToMBench:** Para la construcción de enunciados con equilibrio estricto en la distribución de respuestas verdaderas/falsas.
  * **BLInD (Bayesian Linguistic Inference Dataset - Nafar et al., 2025):** Para enunciados con especificaciones de incertidumbre y reglas condicionales.
* **Modelos LLM Generadores (Sujetos a Evaluación):**
  * OpenAI GPT-4o, o3-mini, Claude 3.7 Sonnet, DeepSeek-V3 / DeepSeek-Prover, Llama 3.1.

---

## Fase 4: Normalización en Formato de Fixtures (Esquema JSON / AST)

### Descripción de la Actividad
Encapsular cada escenario de prueba en una *fixture* estandarizada consumable por el orquestador del experimento.

### Pasos Operativos
1. **Estructuración del Objeto JSON:** Unificar id, descripción, categoría, entorno $\Gamma$, salida esperada, AST del DSL y código Python en un único archivo de prueba.
2. **Validación del Esqueleto AST:** Verificar que la sintaxis JSON interna cumpla con las especificaciones BNF del DSL funcional.

### Recursos y Datasets Necesarios
* **Marco Teórico de Referencia:**
  * **Cálculo Lambda Simplemente Tipado (STLC):** Reglas formales de juicio de tipos $\Gamma \vdash e : \tau$.
  * **Notación BNF / Grammatical Framework (GF):** Para la gramática libre de contexto del DSL.
* **Herramientas de Software:**
  * Módulos `json` y `dataclasses` de Python 3.12 para serialización y firma estricta de objetos de prueba.

---

## Fase 5: Auditoría Mecánica y Verificación del Corpus

### Descripción de la Actividad
Someter los casos de prueba a verificadores formales y demostradores automáticos para asegurar que los pares de *ground truth* sean formalmente correctos y libres de filtraciones (*data leakage*).

### Pasos Operativos
1. **Typechecking Estático en Haskell:** Pasar las *fixtures* válidas por el verificador en GHC para certificar validez derivacional ($dv = 1$).
2. **Satisfechabilidad Lógica:** Verificar con solvers SMT que las reglas no contengan tautologías vacías o contradicciones irresolubles.

### Recursos y Datasets Necesarios
* **Compiladores y Verificadores Formales:**
  * **GHC Haskell Compiler (v9.4+):** Para compilar y ejecutar el typechecker/scopechecker sobre el DSL basado en ADTs.
  * **Lean 4 Proof Assistant (Liu et al., 2025; Chojecki, 2025):** Para la verificación de pruebas formales paso a paso.
* **Solvers SMT y Grafos de Conocimiento:**
  * **Z3 SMT Solver (Microsoft Research):** Para comprobación de satisfacibilidad y consistencia lógica de las reglas.
  * **Neo4j (v5.0.0+ - Veeramani et al., 2026):** Para modelado y auditoría en grafos de conocimiento normativos.

---

## Fase 6: Automatización de la Evaluación en los 3 Grupos Experimentales

### Descripción de la Actividad
Ejecutar la suite de pruebas completa a través del orquestador experimental para recopilar métricas comparativas entre el grupo de Tratamiento y los dos Baselines de Control.

### Pasos Operativos
1. **Carga en el Orquestador:** Cargar el corpus procesado en `pipeline_prototype-v2.py`.
2. **Evaluación de los 3 Brazos:**
   * **Tratamiento (STLC Haskell):** Verificación de tipos estática previa a la evaluación determinística.
   * **Baseline 1 (Python Libre):** Generación e interpretación directa con `exec()`.
   * **Baseline 2 (Python Estructurado):** Inspección estática previa mediante AST de Python y MyPy.
3. **Cálculo de Métricas:** Computar $pass@1$, Tasa de Intercepción Estática y Tasa de Fallos en Runtime.

### Recursos y Datasets Necesarios
* **Herramientas para Baseline 2:**
  * **MyPy / Pyright:** Verificadores estáticos de tipos para código Python.
* **Frameworks de Pruebas y Orquestación:**
  * **Pytest Framework:** Para la automatización de aserciones.
  * **Orquestador del Modelo:** Script ejecutable `pipeline_prototype-v2.py`.
  * **Métrica Pass@1:** Estándar de corrección funcional en primera generación.

---

## Matriz Resumen de Recursos por Fase

| Fase | Dataset / Referencia Principal | Herramienta / Software Clave | Compilador / Verificador |
| :--- | :--- | :--- | :--- |
| **1. Esquema $\Gamma$** | NL4Opt, DMN Schemas | Pydantic, Python `ast` | N/A |
| **2. Taxonomía** | $\lambda\text{Repair}$, HaluEval | Logging Pipeline | N/A |
| **3. Prompts & GT** | GSM8K, MATH-500, BLInD | OpenAI API, Claude API | LLMs Evaluados |
| **4. Fixtures JSON** | Cálculo Lambda (STLC) | Python `json`, `dataclasses` | N/A |
| **5. Auditoría** | FormalStep, Lean 4 | Z3 SMT Solver, Neo4j | **GHC Haskell Compiler**, Lean 4 |
| **6. Evaluación** | Metric Pass@1 | `pytest`, `pipeline_prototype-v2.py` | MyPy, Python 3.12 Runtime |
