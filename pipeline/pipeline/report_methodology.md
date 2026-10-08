# Bases metodológicas del reporte con IA

Resumen de "Mitigación de incertidumbre probabilística en LLM aplicados a procesos determinísticos mediante cálculo lambda", segunda entrega (DI_PF_TFI_ENTREGA2_v4, Avila, Samaniego y Smulever, UNNE). Es el contexto que `pipeline/report.py` le pasa al LLM para redactar el informe de una corrida. Si cambia el informe de la cátedra, actualizar este archivo.

## 1. Modelo computacional

- El LLM es un generador probabilístico: ante la misma regla de negocio puede producir programas distintos, y algunos serán estructuralmente inválidos, estarán mal tipados o harán referencia a datos que no existen. El modelo no intenta evitar esas salidas, sino detectarlas antes de ejecutarlas: restringe la salida a un DSL pequeño y cerrado (cálculo lambda simplemente tipado, STLC, serializado en JSON) y delega la verificación en un motor determinístico escrito en Haskell.
- Pipeline por regla:
  1. Generación: el LLM recibe la regla en lenguaje natural, las variables con sus tipos y el esquema JSON del DSL, y responde con un programa en JSON.
  2. Verificación, en orden: `parse` (JSON válido que respeta el esquema), `scope` (toda variable está declarada) y `typecheck` (el programa tipa y su resultado es un tipo base). La primera falla bloquea el programa.
  3. Ejecución: solo lo que pasó la verificación se evalúa con los datos del caso.
  4. Registro: cada desenlace (bloqueado y en qué etapa, error en ejecución o resultado) se escribe como una línea JSON. El registro no compara ni agrega.
- Grupos de comparación, con el mismo modelo de lenguaje para los tres dentro de una regla:
  - Tratamiento: el LLM emite un programa del DSL y el motor lo verifica y evalúa.
  - Baseline 1 (control libre): el LLM emite una función Python que se ejecuta sin validación previa.
  - Baseline 2 (control estructurado): el LLM emite una función Python con anotaciones de tipos, que pasa por `ast.parse` y `mypy --strict` antes de ejecutarse.
  - El código de los baselines corre en un contenedor aislado, sin red y sin credenciales.
- Limitación de diseño asumida: el motor intercepta fallas estructurales, de alcance y de tipos. No detecta una regla bien tipada con lógica equivocada (por ejemplo, `>` en lugar de `>=`); esas fallas solo se observan comparando el resultado con el esperado de cada escenario (pass@1, Mündler et al. 2025).

## 2. Decisiones de diseño que afectan la lectura de los datos

- Desenlaces del motor por etapa: `executed`; bloqueado en `parse` (MALFORMED_JSON, INVALID_AST, LITERAL_TYPE_MISMATCH); en `scope` (UNBOUND_VARIABLE); en `typecheck` (OPERAND_MISMATCH, BRANCH_MISMATCH, NOT_A_FUNCTION, entre otros); `runtime_error` (DIVISION_BY_ZERO, NUMERIC_OVERFLOW). Los errores internos del motor no son respuestas del LLM.
- El LLM responde en JSON en los tres grupos (Tratamiento `{"expr": ...}`, baselines `{"code": "..."}`). La respuesta se procesa tal cual, sin reparaciones: un JSON roto es un resultado, no un error del pipeline.
- Γ (tipos de las variables) se deduce de los datos del caso, no lo declara el LLM.
- `Decimal` exacto (racionales): `0.1 + 0.2 == 0.3`. Se evita el punto flotante porque rompe la igualdad exacta.
- Promoción numérica `Int` → `Decimal` solo dentro de operadores aritméticos y de comparación; en la aplicación de funciones el STLC sigue siendo estricto.
- Cortocircuito en `AND` y `OR`, igual que en Python, para no sesgar la comparación.
- Una generación, varios escenarios: siguiendo las pruebas de decisión DMN (Cherednichenko y Maliarenko 2025), cada regla trae varios escenarios con su resultado esperado; la misma respuesta del LLM se ejecuta contra todos y se escribe un registro por escenario. pass@1 se calcula por generación (regla × grupo × repetición): la generación acierta si acierta todos sus escenarios.
- Un escenario acierta si ejecutó y su resultado coincide en tipo y valor con el esperado (comparación estricta: un valor correcto con otro tipo es fallo).
- Baseline 2 recibe un `TypedDict` armado con el mismo Γ del Tratamiento, para que `mypy` pueda controlar algo.
- Cliente LLM intercambiable (API compatible con OpenAI). Una corrida puede fijar un solo modelo y una temperatura, que quedan registrados en cada renglón (`model`, `request_params`); sin modelo fijo, las reglas se reparten entre varios modelos según la cuota disponible. Las tres llamadas de una regla y repetición usan siempre el mismo modelo.
- Las corridas avanzan por rondas (la repetición 1 de todas las reglas, después la 2) y se pueden reanudar; las generaciones cortadas por cuota o red quedan pendientes y no cuentan en `pass@1` ni en `pass@k`.

## 3. Corpus

- Reglas de cinco dominios (fiscal, salud, crédito, seguros y laboral), repartidas en tres categorías de prueba adaptadas de λRepair (Zhang et al. 2026): 1 estructurales, 2 de tipos y alcance, 3 lógicas. La categoría es la falla que la petición está diseñada para tentar; lo observado se registra aparte y se cruza.
- Cada regla trae varios escenarios con su resultado esperado, al estilo DMN. Los esperados los calcula el motor a partir del AST canónico; su revisión humana está pendiente.

## 4. Observaciones metodológicas de la corrida preliminar

La corrida preliminar de la segunda entrega mostró estos puntos. El informe de una corrida nueva debe contrastarlos con su evidencia y decir, para cada uno, si se repite, si no se repite o si la evidencia no alcanza para decidirlo:

1. El proveedor intercepta parte de las fallas estructurales: en modo JSON rechaza la respuesta (`generation_failed`) cuando el modelo no produce JSON válido, y queda registrado como `llm_error`. Así el motor casi no recibe JSON malformado y esa clase de falla de la categoría 1 queda fuera de la medición del validador.
2. El formato de transporte perjudica a los baselines: el código va dentro de una cadena JSON y el modelo a veces escapa dos veces los saltos de línea, lo que termina en `SyntaxError`. Es un efecto del formato, no de la capacidad de generar código.
3. El preámbulo del Baseline 2 introduce fallas propias: el modelo redefine el tipo `Data`, usa `from __future__ import annotations` después del preámbulo o no respeta la firma exigida. Son fallas del arnés, no errores de tipos de la regla.
4. Los modelos no están balanceados entre categorías: el modelo de cada regla depende de la cuota disponible, y como el acierto varía mucho entre modelos, las diferencias entre categorías quedan confundidas con el modelo. Si `run.models` tiene un solo modelo, esta observación no se repite.
5. La categoría 2 casi no provoca errores de tipos en el Tratamiento; en cambio, el Baseline 1 falla ahí sobre todo por la representación del resultado (`float` o cadena donde se esperaba `Decimal`). Hay que revisar si los enunciados provocan la falla que buscan y si un valor correcto con otro tipo debe contar como acierto.
6. Los bloqueos del motor son mayormente de estructura (`parse`, INVALID_AST): el esquema no se impone al generar porque el modo JSON del proveedor no lo aplica.
7. Una repetición no alcanza para medir variabilidad: el experimento necesita varias repeticiones por regla (Zhang et al. usan 5) y una temperatura fija y registrada. Con varias repeticiones, contrastarla con `pass_at_k` y `consistency` (reglas inestables entre repeticiones); la temperatura está en `run.temperature` ("no registrada" o "del proveedor" significa que no quedó fijada).
8. Consistencia de los esperados: si en ningún escenario los tres grupos coinciden entre sí y contradicen el esperado, es un indicio de que los esperados son coherentes, pero no reemplaza la revisión humana.

## 5. Cautela al interpretar

- Con una sola repetición, sin temperatura fija, con más de un modelo o con los problemas anteriores sin resolver, las cifras no permiten comparar los grupos ni confirmar hipótesis: se presentan para revisar el diseño del experimento.
- El motor verifica estructura, alcance y tipos, no la lógica de la regla: los errores lógicos (categoría 3) solo los detectan los escenarios con su esperado. No atribuir al motor un acierto o un fallo lógico; describirlo como resultado de los escenarios (`failure_layers_by_category`: `blocked` frente a `wrong`).
- Las cifras citadas deben salir de la evidencia de la corrida. No se infieren tendencias que la evidencia no muestra ni se generalizan los resultados fuera del corpus.

## 6. Referencias

1. Cherednichenko, O., Maliarenko, V.: The dispatcher: bridging the probabilistic gap in automated decision modeling (2025). https://pm.khpi.edu.ua/article/view/350034
2. Mündler, N., He, J., Wang, H., Sen, K., Song, D., Vechev, M.: Type-Constrained Code Generation with Language Models (2025). https://dl.acm.org/doi/10.1145/3729274
3. Zhang, Y., Pientka, B., Si, X.: Evaluating LLMs in the context of a functional programming course: a comprehensive study (2026). https://programming-journal.org/2026/11/5
