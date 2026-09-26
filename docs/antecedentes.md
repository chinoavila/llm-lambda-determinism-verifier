# Antecedentes para el corpus

Lo que aporta cada referencia del proyecto (DI_PF_TFI_ENTREGA1_v5) a la construcción del corpus, y dónde conseguir sus datos. Los PDFs están en `prototype/referencias/` pero **no se versionan**: este documento conserva lo necesario. Diseño del corpus: [`corpus.md`](corpus.md).

Los números entre corchetes siguen la bibliografía del proyecto. Las cifras vienen del texto de cada paper, salvo en la sección "Contexto", donde se indica que salen del resumen del proyecto (sección 7).

## Las tres referencias que fijan el diseño (sección 8 del proyecto)

**[18] Zhang, Pientka y Si (2026). λRepair.**
- **Tres benchmarks:**
  - λCodeGen: 10 tareas con 53 subtareas;
  - **λRepair**: 150 programas OCaml de un curso de programación funcional en McGill (otoño 2022);
  - λExplain: 50 preguntas.
- **Origen de λRepair:** 169 de 320 estudiantes dieron consentimiento, y se registraron más de 270.000 eventos de programación en Learn-OCaml.
- **Taxonomía y balance:** 50 programas con error sintáctico, 50 de tipos y 50 lógicos. Son programas de una sola función, distribuidos de forma pareja entre las 10 tareas para balancear dificultad.
- **Protocolo:**
  - 9 LLMs, consultados por las APIs de OpenAI y OpenRouter con sus parámetros por defecto;
  - **5 consultas por problema**, *zero-shot*;
  - en los errores de sintaxis y tipos, el prompt incluye el mensaje del compilador; en los lógicos, la descripción de la tarea.
- **Resultados** (mejores modelos, nivel "Mastery"): 78–82 % en sintaxis, 72–80 % en tipos, 67–72 % en lógica. La corrección de errores lógicos es la más difícil.
- **Amenazas a la validez que declaran:**
  - los datos son de 2022 y pudieron entrar en el entrenamiento de los modelos;
  - no penalizan los errores nuevos que introduce la reparación.

**[2] Cherednichenko y Maliarenko (2025). The Dispatcher (DMN).**
- **Arquitectura *test-first*:** primero se generan casos de prueba en JSON, que se validan contra el esquema. Después se genera la tabla DMN apoyada en esos casos.
- **Validador en tres etapas:**
  1. XML Schema (XSD);
  2. tipos de las expresiones FEEL;
  3. ejecución en Camunda contra los casos.
- **Configuración:** temperatura entre 0 y 0,3. Explican que DMN exige reglas mutuamente excluyentes y completas (*hit policies*).
- **Experimento:** 200 ciclos de generación, con hasta 5 reintentos. La estrategia A logró 95,5 % de éxito y la B, 100 %, con 6,06 % menos de costo y 8,44 % menos de tokens.
- **No publica reglas ni casos.**

**[10] Mündler et al. (2025). pass@1.**
- **`pass@1`:** porcentaje de generaciones que pasan los tests unitarios en un solo intento.
- **Tareas:** *synthesis* (descripción + encabezado de la función → código, la que corresponde a nuestro experimento), *translation* y *repair*.
- **Datos:** HumanEval (159 problemas) y MBPP (384) en TypeScript, vía MultiPL-E. En HumanEval, 4 *seeds* por problema con temperatura 1.
- **Hallazgos:**
  - **el 94 % de los errores de compilación son de tipos** y solo el 6 % sintácticos;
  - restringir la generación por tipos reduce los errores de compilación un 75,3 % en HumanEval y un 52,1 % en MBPP.

## Diseños de benchmark que conviene imitar

**[16] Veeramani et al. (2026). Reglas fiscales (India, Income Tax Act 1961).**
- **20 escenarios** validados por expertos, estratificados por categoría y dificultad:
  - ingresos empresariales: 8 (1 fácil, 4 medios, 3 difíciles);
  - deducciones 80C/80D: 10 (7 fáciles, 3 medios);
  - tributación presunta 44AD: 2 (1 fácil, 1 medio).
- **Tres brazos:** LLM solo, 75 % (15 de 20); RAG, 60 % (12 de 20); neuro-simbólico, 80 % (16 de 20).
- **Criterio de acierto:** igualdad numérica exacta con el valor legal esperado, con tolerancia cero.
- **Errores del LLM solo:** se concentran en umbrales condicionales, como el tope de la sección 80D para mayores. Es justo lo que miden nuestras reglas.

**[4] Cuconato (2026). ISA, dominio clínico.**
- **Gold standard calculado de antemano** con una semántica decidible, sin que ningún humano etiquete.
- **Batería estratificada en tres familias:**
  - prohibiciones derivables;
  - afirmaciones no derivables, con contramodelo;
  - interacciones cruzadas entre bases de conocimiento.
- **Métricas fijadas antes del experimento**, para que no se ajusten a los resultados: sensibilidad, especificidad, validez de pasos (*dv*) y tasa de alucinación formal (*fh*).

**[15] Tang (2026), capítulo 4. LTLBench.**
- **Generación:** convierte fórmulas LTL a lenguaje natural con plantillas; el resultado esperado lo calcula el verificador NuSMV.
- **Variables controladas por separado:** cantidad de eventos (n) y cantidad de operadores (m), con **300 problemas por combinación** y etiquetas **balanceadas 50 % verdadero / 50 % falso**.
- **Evaluación:** 12 LLMs, medidos por *accuracy*.
- **En MindGames:** evalúa con 200 ítems balanceados 50/50, y reporta una "tasa de ejecución" de 78 % contra 99,5 % de los baselines.

**[11] Nafar, Venable y Kordjamshidi (2025). BLInD.**
- **Generación:** redes bayesianas generadas (árboles de hasta 10 variables) y convertidas a texto con plantillas.
- **Niveles de complejidad:** V2 a V10, **100 instancias por nivel** (900 de test).
- **Mapeo simbólico:** a ProbLog, que resuelve la inferencia.

**Goossens, Vandevelde, Vanthienen y Vennekens (2023). GPT-3 for Decision Logic Modeling** (citado por [2]).
- **Dataset:** 6 descripciones de decisiones de 88 a 225 palabras:
  - IMC,
  - mascota,
  - licencia de conducir,
  - vacaciones,
  - beca,
  - medio de transporte.
- **Origen de las descripciones:** 2 salen de fuentes existentes (vacaciones sale de un desafío de la Decision Management Community) y **4 son sintéticas "realistas, en la misma línea"**.
- **Protocolo:** 9 preguntas, con tests escritos a mano. Temperaturas 0, 0,3, 0,7 y 1, con 3 repeticiones de cada una: 72 experimentos.
- **Resultados:**
  - GPT-3 armó una tabla correcta solo en 3 de 72;
  - las tablas eran completas en un 42 %;
  - **el cálculo del IMC fue incorrecto en todos los casos**.

**[7] Liu et al. (2025). Safe / FormalStep.** 30.809 enunciados Lean autoformalizados a partir de 500 problemas de MATH. Evalúan en MATH-500, GSM8K y CollegeMath. Es matemática: no sirve como ítem del corpus.

**[1] Abdel-Rahman et al. (2025). Revisión sistemática de LLMs en programación matemática.**
- **Datasets más usados:**
  - **NL4Opt**, el más usado: 6 dominios (ventas, publicidad, inversión, producción, transporte, ciencias), unas 2 restricciones y 2 variables por problema;
  - ComplexOR, el segundo.
- **Críticas a la literatura:**
  - datasets demasiado simples;
  - predominio de modelos cerrados;
  - falta de una evaluación unificada;
  - "compilar no garantiza corrección".
- **Experimento propio:**
  - 10 problemas de redes, descritos en su apéndice;
  - 3 prompts (experto, *chain-of-thought*, *self-consistency*), con 0, 1 y 2 ejemplos;
  - métricas: *optimality gap*, F1 por *token* y tasa de compilación.

## Contexto (sin datos para el corpus)

**[5] Huang et al. (2025).** Taxonomía de alucinaciones:
- **factualidad:** contradicción y fabricación;
- **fidelidad:** inconsistencia con la instrucción, con el contexto y lógica.

La rama de fidelidad es la que aplica a traducir reglas: usar una variable fuera de Γ es inconsistencia con el contexto, y una regla invertida es inconsistencia lógica. HaluEval y FELM miden factualidad en preguntas y respuestas; no aplican al corpus.

Según el resumen del proyecto (sección 7), no releído en detalle:
- **[6] Karne et al.:** exceso de confianza en afirmaciones falsas.
- **[19] Zhu et al.:** colapso del modelo por datos sintéticos.
- **[17] Yang:** fundamentos estadísticos.
- **[12] Patil y Jadon, [9] Lu y Li:** RAG más intérprete de código, +10 a 15 puntos en educación. Lu y Li evalúan en 5 datasets públicos (AI2_ARC, OpenBookQA, E-EVAL, Textbook QA, ScienceQA) con 4 configuraciones.
- **[13] Pramanik et al.:** NSF-CoT, fidelidad de la cadena de razonamiento con Z3.
- **[14] Shao et al.:** RNSP, 86 % en Game of 24 (100 problemas).
- **[3] Chojecki, [8] Liu (tesis):** razonamiento matemático y lógico.

## Inventario de datasets

Verificado en la web el 2026-09-26. "Sin licencia" significa que el repositorio no declara ninguna: por defecto rigen todos los derechos reservados. Se puede estudiar el método, pero no redistribuir los datos.

| Dataset | Fuente | Dónde | Licencia | Uso para el corpus |
|---|---|---|---|---|
| λCodeGen, λRepair, λExplain | [18] | Zenodo [`10.5281/zenodo.18470483`](https://doi.org/10.5281/zenodo.18470483), zip de 76,7 MB | MIT | Errores reales por categoría (OCaml): modelo para diseñar las peticiones de cada categoría |
| Paquete de reproducción de type-constrained decoding | [10] | [github.com/eth-sri/type-constrained-code-generation](https://github.com/eth-sri/type-constrained-code-generation), Zenodo `10.5281/zenodo.15355889` | MIT / CC-BY-4.0 | Cómo se arman los tests para `pass@1` |
| GPT-DMN: 6 descripciones, 72 salidas y la planilla de evaluación | Goossens 2023 | [gitlab.com/EAVISE/sva/GPT-DMN](https://gitlab.com/EAVISE/sva/GPT-DMN) | Sin licencia | **Dominio y formato más cercanos:** reglas de decisión en lenguaje natural |
| Desafíos de la Decision Management Community (87, de 2014 a 2026; unos 24 son reglas de negocio: préstamos, tarjetas, impuestos, seguros, elegibilidad) | citado por Goossens | [dmcommunity.org/challenges](https://dmcommunity.org/challenges/) | Todos los derechos reservados; el reuso académico no está contemplado | Inspiración de dominio. **Escribir reglas propias**, no copiarlas |
| LTLBench | [15] | [github.com/RutaTang/LTLBench](https://github.com/RutaTang/LTLBench) | Sin licencia | Modelo de generador: fórmula → texto → verdad calculada |
| ToM-LM | [15] | [github.com/RutaTang/ToM-LM](https://github.com/RutaTang/ToM-LM) | Sin licencia | Poco relevante |
| BLInD | [11] | [github.com/HLR/BLInD](https://github.com/HLR/BLInD) | Sin licencia | Modelo de generador con niveles de complejidad |
| FormalStep | [7] | [github.com/liuchengwucn/Safe](https://github.com/liuchengwucn/Safe) | Sin licencia | No aplica (Lean, matemática) |
| NSF-CoT | [13] | [github.com/VishalPramanik/NSF-CoT](https://github.com/VishalPramanik/NSF-CoT) | MIT | No aplica |
| Escenarios fiscales (20) | [16] | "A pedido de los autores" (autora de contacto en el paper) | — | **Muy relevante:** umbrales y topes fiscales. Vale la pena pedirlos |
| Batería clínica | [4] | No publicada; solo el cuestionario, a pedido | — | Solo el método |
| VITA test: 130 preguntas y 260 variantes perturbadas | citado por [16] (Gogani-Khiabani et al. 2025, `10.1007/s10506-025-09465-7`) | Sin enlace público encontrado | — | Relevante: declaraciones de impuestos. Pedir a los autores |
| Examen de certificación VITA/TCE (Form 6744, año fiscal 2025), de donde sale el VITA test | IRS | [irs.gov/pub/irs-pdf/f6744.pdf](https://www.irs.gov/pub/irs-pdf/f6744.pdf) | Dominio público (17 U.S.C. § 105), salvo capturas de TaxSlayer | **Fuente principal de reglas reales:** 27 reglas inventariadas en [`corpus-fuentes.md`](corpus-fuentes.md) |
| MindGames | [15] | [huggingface.co/datasets/sileod/mindgames](https://huggingface.co/datasets/sileod/mindgames) | Apache-2.0 | No aplica (teoría de la mente); solo el criterio 50/50 |
| ToMBench | [15] | [github.com/zhchen18/ToMBench](https://github.com/zhchen18/ToMBench) | MIT | No aplica |
| HaluEval | [5] | [github.com/RUCAIBox/HaluEval](https://github.com/RUCAIBox/HaluEval) | MIT | No aplica (factualidad) |
| FELM | [5] | [github.com/hkust-nlp/felm](https://github.com/hkust-nlp/felm) | Sin licencia | No aplica |
| NL4Opt | [1] | [github.com/nl4opt/nl4opt-competition](https://github.com/nl4opt/nl4opt-competition) | MIT | Solo los dominios; los problemas son de optimización |
| ComplexOR (37 problemas; el repo aclara que por ahora hay una versión preliminar) | [1] | [github.com/xzymustbexzy/Chain-of-Experts](https://github.com/xzymustbexzy/Chain-of-Experts) | — | No aplica (optimización) |
| GSM8K | [1], [7], [11] | [github.com/openai/grade-school-math](https://github.com/openai/grade-school-math) | Sin licencia en la API | No aplica (aritmética escolar) |
| MATH-500 | [7] | [huggingface.co/datasets/HuggingFaceH4/MATH-500](https://huggingface.co/datasets/HuggingFaceH4/MATH-500) | No declarada | No aplica |
| CLadder | [11] | [github.com/causalNLP/cladder](https://github.com/causalNLP/cladder) | MIT | No aplica |

**Conclusión:** ningún dataset trae reglas de negocio listas para el DSL con sus escenarios. Hay que construir el corpus. De los antecedentes se toman:
- **qué tipo de reglas incluir:** Goossens, los desafíos de DM Community y Veeramani;
- **cómo repartir las categorías:** λRepair;
- **cómo generar escenarios con el resultado esperado calculado por máquina y balanceado:** Tang, BLInD y Cuconato.
