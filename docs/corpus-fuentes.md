# Fuentes reales para el corpus: inventario del examen VITA del IRS

Etapa 1 de la construcción del corpus: qué reglas de una fuente real y de reuso libre se pueden llevar al corpus, y a qué categoría de la sección 8 conviene asignar cada una. El método general está en [`corpus.md`](corpus.md); los antecedentes, en [`antecedentes.md`](antecedentes.md).

## La fuente

- **Documento:** IRS Form 6744, *VITA/TCE Volunteer Assistor's Test/Retest* (Rev. 10-2025, año fiscal 2025, 209 páginas): [irs.gov/pub/irs-pdf/f6744.pdf](https://www.irs.gov/pub/irs-pdf/f6744.pdf). Es el examen de certificación de los voluntarios que preparan declaraciones gratuitas. Gogani-Khiabani et al. (2025) armaron su *VITA test* (130 preguntas y 260 variantes) a partir de estos exámenes.
- **Licencia:** obra del gobierno federal de EE.UU., sin derechos de autor (17 U.S.C. § 105). La excepción son las capturas de pantalla de TaxSlayer, que no usamos.
- **Qué trae:** escenarios con los datos de un contribuyente ficticio ("Fred tiene 39 años, nunca se casó, su hermano de 14 vive con él…") y preguntas de verdadero o falso y de opción múltiple sobre elegibilidad, estado civil y montos.
- **Qué no trae:**
  - **las respuestas:** se corrigen en línea (Link & Learn Taxes), no están en el PDF;
  - **las reglas:** el examen supone que el voluntario las conoce. Los montos que aparecen en las preguntas pueden ser distractores de una pregunta falsa, así que no sirven como fuente.
- **El *retest* repite los mismos datos** con otras preguntas. No aporta escenarios nuevos.

## Cómo se usa

| Parte de la regla | De dónde sale |
|---|---|
| Lógica (`canonical_ast`) y parámetros (topes, edades, tasas) | La publicación del IRS que define la regla (columna "Pub."), también de dominio público. Se verifica para 2025 al escribir la regla |
| Escenarios | Los del examen como punto de partida (columna "Escenarios"). Se completan hasta 6–10 variando un dato por vez alrededor de cada límite, con 50/50 de `true` y `false` |
| `expected` | El engine, con `check-case --write` |
| Enunciado | Redacción propia con la técnica de la categoría: la provocación no viene de la fuente |
| Γ | Propio. El DSL no tiene fechas: los datos de fecha se pasan ya calculados (años, meses, días) |

Cada regla fuente se usa **en una sola categoría**, para que las celdas sean independientes. Las preguntas que dependen de un formulario (qué línea completar, en qué formulario se informa) no son reglas y quedan afuera.

## Inventario

Solo los mini-escenarios: los que no piden preparar una declaración completa. B = Basic, A = Advanced, M = Military, I = International, E = estudiantes extranjeros (sección de residencia).

### Categoría 1: estructura larga o anidada

| Id | Regla | Resultado | Escenarios | Pub. |
|---|---|---|---|---|
| IRS-01 | EITC sin hijo calificable: edad, ingreso ganado, ingreso de inversión, SSN, residencia, no ser dependiente | Bool | B2 Walsh, B5 Neil, B6 Scott, A6 Carlos | 596 |
| IRS-02 | Estado civil más favorable (casado conjunto, jefe de hogar, viudo calificado, soltero) | String | B1 Fred, A1 Joy, A4 Alexa, B5 Neil | 501 |
| IRS-03 | Residencia fiscal de un extranjero con visa F o J: años exentos como estudiante o como docente, y días de presencia | String | E1 Maylor, E2 Amelia, E3 Lucas, E4 Antonio, E5 Yvonne, E9 Ayesha, E10 Klaus | 519 |
| IRS-04 | Crédito educativo aplicable (AOTC, LLC o ninguno): carga horaria, año de estudio, título, MAGI | String | B6 Scott, A6 Carlos | 970 |
| IRS-05 | ¿Es gasto médico calificado para la HSA? Lista larga de tipos de gasto | Bool | A3 Nancy (7 gastos, uno por escenario) | 969 |
| IRS-06 | De quién es hijo calificable un menor que vive con padre y abuela (reglas de desempate) | String | A4 Lillian | 501 |
| IRS-07 | Dependiente que da derecho al crédito por otros dependientes | Bool | B4 Kyle, I2 Bindi | Instr. Schedule 8812 |
| IRS-08 | Quién debe presentar el Form 8843 | Bool | E6 Janice y Rick, E7 Steven, E8 Arya, Jocelyn y Connor, E11 Gustavo | Instr. Form 8843 |

### Categoría 2: tipos y alcance

| Id | Regla | Resultado | Escenarios | Tentación de tipos |
|---|---|---|---|---|
| IRS-09 | Deducción estándar: monto base por estado civil más adicionales por edad y ceguera | Decimal | B1 Fred, B5 Neil, B7 Knox, A5 Julia | estado civil como texto (`IN`); monto contra cantidad de adicionales (Pub. 501) |
| IRS-10 | Ingreso ganado para el EITC: salarios sí, intereses no | Decimal | B2 Walsh, A1 Joy | el enunciado menciona los intereses, que no están en Γ (Pub. 596) |
| IRS-11 | Deducción de viaje de un reservista: millas × tarifa, solo si la base está a más de 100 millas | Decimal | M1 Malik | millas (`Int`) por tarifa (`Decimal`); una rama devuelve 0 (Pub. 3) |
| IRS-12 | Retención sobre dividendos de un no residente: 30 % salvo tasa de tratado | Decimal | E19 Lacey | país como texto; tasa porcentual (Pub. 519) |
| IRS-13 | Prueba de ciudadanía del dependiente: ciudadano o residente de EE.UU., Canadá o México | Bool | I2 Bindi, I2 Jackson, B4 Kyle | país (`String`) con `IN` contra un número (Pub. 501) |
| IRS-14 | EITC cuando un cónyuge tiene ITIN | Bool | B4 Dowd, I2 Outbacker | tipo de identificación como texto (Pub. 596) |
| IRS-15 | Monto del crédito por hijos: hijos calificables por monto por hijo | Decimal | B3 Ramirez, A2 Summer | cantidad (`Int`) por monto (`Decimal`) (Instr. Schedule 8812) |
| IRS-16 | Impuesto adicional del 10 % por retiro anticipado de una IRA, salvo gastos de educación | Decimal | A6 Carlos | edad límite 59½ como `Decimal` contra edad `Int` (Pub. 590-B) |
| IRS-17 | Tope de aportes a la HSA: límite individual más adicional por edad; los aportes de terceros cuentan | Decimal | A3 Nancy | suma de aportes `Decimal` contra el tope (Pub. 969) |

### Categoría 3: inconsistencias lógicas

| Id | Regla | Resultado | Escenarios | Tentación lógica |
|---|---|---|---|---|
| IRS-18 | Edad del hijo para el crédito por hijos | Bool | B3 Elena y Jorge, A2 Janice y Jack, B4 Blake | "menor de 17" contra "17 o menos" (Instr. Schedule 8812) |
| IRS-19 | Obligación de presentar la declaración | Bool | B5 Neil | umbral de ingreso bruto: `>=` contra `>` (Pub. 501) |
| IRS-20 | Deducción por intereses de préstamo estudiantil | Decimal | B6 Scott | el menor entre lo pagado y el tope (Pub. 970) |
| IRS-21 | Pérdidas de juego deducibles | Decimal | A5 Julia | hasta el monto de las ganancias, y solo si detalla deducciones (Pub. 529) |
| IRS-22 | Prueba de presencia física para excluir ingresos del exterior | Bool | I1 Kamo y Grim | al menos 330 días completos (Pub. 54) |
| IRS-23 | Millas deducibles en una mudanza militar | Decimal | M2 Rivers | la ruta más directa, no las millas recorridas (Pub. 3) |
| IRS-24 | Alojamiento deducible en una mudanza militar | Decimal | M2 Rivers | noches autorizadas, no noches pasadas (Pub. 3) |
| IRS-25 | Crédito por cuidado de dependientes pagado a un familiar | Bool | A2 Summer | excepción: no vale si el cuidador es hijo propio menor de 19 (Pub. 503) |
| IRS-26 | Aporte adicional a la HSA por edad | Decimal | A3 Nancy | desde los 55: `>=` contra `>` (Pub. 969) |
| IRS-27 | Considerado no casado (cónyuge fuera de casa los últimos 6 meses) | Bool | A1 Joy, A4 Amy | negación y excepción: "salvo que haya vivido con el cónyuge…" (Pub. 501) |

**Total: 27 reglas** (8 + 9 + 10) con escenarios reales. Quedaron afuera las preguntas sin regla (qué formulario, qué línea, trámites), las que dependen de años anteriores a 2025 (primas de seguro hipotecario) y las de monto trivial (el seguro de desempleo es imponible, los premios de lotería también).

**Sin inventariar:** los escenarios que piden preparar una declaración completa (B7–B9, A7–A9, M5, I3, E-Kim Lee y siguientes). Tienen más reglas, pero mezcladas con la carga de formularios. Se revisan solo si hacen falta más reglas.

## Selección para el corpus

Las 27 son del mismo dominio. La matriz de [`corpus.md`](corpus.md) tiene 5 dominios con 6 reglas por celda, así que entran **6 por categoría (18)** en el dominio `fiscal`, y las otras 9 quedan de reserva.

| Categoría | Entran | Reserva | Por qué quedan en reserva |
|---|---|---|---|
| 1 | IRS-01, 02, 03, 05, 07, 08 | IRS-04, 06 | El crédito educativo depende de una reducción gradual por MAGI; el desempate entre padre y abuela tiene un solo escenario real |
| 2 | IRS-09, 10, 11, 13, 15, 16 | IRS-12, 14, 17 | Las tasas de tratado varían por país; ITIN tiene poca lógica; el tope de la HSA repite los datos de Nancy de IRS-05 |
| 3 | IRS-18, 19, 21, 23, 25, 27 | IRS-20, 22, 24, 26 | IRS-24 e IRS-26 repiten los datos de IRS-23 e IRS-05; IRS-20 e IRS-22 son un solo umbral y se parecen a IRS-19 |

En cada regla adaptada, `source` queda así:

```json
"source": {
  "kind": "adapted",
  "reference": "IRS Form 6744 (Rev. 10-2025), Basic Scenario 3; Instrucciones del Schedule 8812 (2025)",
  "license": "Dominio público (17 U.S.C. § 105)"
}
```

## Qué más hace falta

- **Otras fuentes de reuso libre:** la descripción de IMC de Goossens et al. (2023, CC BY 4.0) aporta una regla del dominio salud. Los demás dominios (`credito`, `seguros`, `laboral`) no tienen una fuente de reuso libre encontrada: se escriben reglas propias, inspiradas en los desafíos de la Decision Management Community sin copiarlos.
- **Contaminación:** los exámenes VITA son públicos y probablemente estuvieron en el entrenamiento de los modelos. Como el enunciado lo redactamos nosotros y el examen no trae las reglas, el riesgo queda acotado a que el modelo conozca la ley fiscal, que es lo esperable de cualquier regla real. El campo `source` de cada regla permite separar el análisis.
