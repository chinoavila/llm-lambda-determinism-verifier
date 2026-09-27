"""Tandas 4 a 6 del dominio salud: 6 reglas por categoría. Ver corpus/README.md.

Reglas propias, salvo SAL-C1-IMC, adaptada de Goossens et al. (2023), CC BY 4.0.
Los umbrales clínicos son plausibles pero no son indicaciones médicas: lo que
importa es que cada regla tenga una sola lectura correcta.

    docker compose run --rm pipeline python /workspace/corpus/tools/salud.py /workspace/corpus
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from dsl import ORIGINAL, adapted, all_, any_, dec, eq, in_, ite, lit, not_, op, var, write_rule  # noqa: E402

OUT = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(__file__).parents[1]
S = lit


def rule(category, name, case_id, description, gamma, expr, python, scenarios, source=ORIGINAL):
    write_rule(
        OUT, f"salud-c{category}-{name}", case_id=case_id, category=category, domain="salud", source=source,
        description=description, gamma=gamma, expr=expr, python=python, scenarios=scenarios,
        generator="corpus/tools/salud.py",
    )


def env(**kw):
    return kw


# ===================================== Categoría 1 =====================================

imc = op("/", var("peso_kg"), op("*", var("altura_m"), var("altura_m")))
masc = eq("sexo", "masculino")
rule(
    1, "imc", "SAL-C1-IMC",
    "Clasificar el nivel de índice de masa corporal (IMC) de una persona. El IMC se calcula con el peso en "
    "kilogramos y la altura en metros, con la fórmula peso / (altura * altura). Si el IMC es 30 o más, el nivel es "
    "\"Obesidad\". Si el IMC es menor que 18.5, el nivel es \"Bajo peso severo\" para el sexo \"masculino\" y \"Bajo "
    "peso\" para el sexo \"femenino\". Si está entre 18.5 y 25 (sin incluir 25), el nivel es \"Bajo peso\" para "
    "masculino y \"Normal\" para femenino. Por último, si está entre 25 y 30 (sin incluir 30), el nivel es \"Normal\" "
    "para masculino y \"Sobrepeso\" para femenino.",
    {"altura_m": "Decimal", "peso_kg": "Decimal", "sexo": "String"},
    ite(op(">=", imc, lit(30)), S("Obesidad"),
        ite(op("<", imc, dec("18.5")), ite(masc, S("Bajo peso severo"), S("Bajo peso")),
            ite(op("<", imc, lit(25)), ite(masc, S("Bajo peso"), S("Normal")),
                ite(masc, S("Normal"), S("Sobrepeso"))))),
    "from decimal import Decimal\n\n"
    "def evaluate_rule(data):\n"
    "    imc = data['peso_kg'] / (data['altura_m'] * data['altura_m'])\n"
    "    masculino = data['sexo'] == 'masculino'\n"
    "    if imc >= 30:\n"
    "        return 'Obesidad'\n"
    "    if imc < Decimal('18.5'):\n"
    "        return 'Bajo peso severo' if masculino else 'Bajo peso'\n"
    "    if imc < 25:\n"
    "        return 'Bajo peso' if masculino else 'Normal'\n"
    "    return 'Normal' if masculino else 'Sobrepeso'\n",
    [
        ("V1-ENTRE-18-5-Y-25-F", env(peso_kg=70.5, altura_m=1.75, sexo="femenino")),
        ("V2-ENTRE-18-5-Y-25-M", env(peso_kg=70.5, altura_m=1.75, sexo="masculino")),
        ("V3-BAJO-MASCULINO", env(peso_kg=55.5, altura_m=1.8, sexo="masculino")),
        ("V4-BAJO-FEMENINO", env(peso_kg=55.5, altura_m=1.8, sexo="femenino")),
        ("V5-ENTRE-25-Y-30-F", env(peso_kg=80.5, altura_m=1.75, sexo="femenino")),
        ("V6-ENTRE-25-Y-30-M", env(peso_kg=80.5, altura_m=1.75, sexo="masculino")),
        ("V7-EXACTO-30", env(peso_kg=67.5, altura_m=1.5, sexo="femenino")),
        ("V8-EXACTO-25-F", env(peso_kg=62.41, altura_m=1.58, sexo="femenino")),
        ("V9-EXACTO-18-5-M", env(peso_kg=47.36, altura_m=1.6, sexo="masculino")),
    ],
    source=adapted(
        "Goossens, Vandevelde, Vanthienen y Vennekens (2023), GPT-3 for Decision Logic Modeling, CEUR-WS Vol-3485, "
        "descripción BMI (tomada a su vez del desafío DMN Community de enero de 2016)",
        "CC BY 4.0",
    ),
)

rule(
    1, "triaje", "SAL-C1-TRIAJE",
    "Asignar el color de triaje a un paciente que llega a la guardia, revisando los criterios en este orden y "
    "quedándose con el primero que se cumpla. Es \"Rojo\" si el paciente no está consciente o si su saturación de "
    "oxígeno es menor que 90 %. Si no, es \"Naranja\" si la saturación es menor que 94 %, si la frecuencia cardíaca "
    "supera 120 latidos por minuto o si el dolor, en una escala de 0 a 10, es 8 o más. Si tampoco, es \"Amarillo\" "
    "si la temperatura llega a 38.5 grados o si el dolor es 5 o más. En cualquier otro caso es \"Verde\". La "
    "temperatura se informa con un decimal; la saturación, la frecuencia y el dolor, como enteros.",
    {"consciente": "Bool", "dolor": "Int", "frecuencia_cardiaca": "Int", "saturacion": "Int", "temperatura": "Decimal"},
    ite(op("OR", not_(var("consciente")), op("<", var("saturacion"), lit(90))), S("Rojo"),
        ite(any_(op("<", var("saturacion"), lit(94)), op(">", var("frecuencia_cardiaca"), lit(120)), op(">=", var("dolor"), lit(8))),
            S("Naranja"),
            ite(op("OR", op(">=", var("temperatura"), dec("38.5")), op(">=", var("dolor"), lit(5))), S("Amarillo"), S("Verde")))),
    "from decimal import Decimal\n\n"
    "def evaluate_rule(data):\n"
    "    if not data['consciente'] or data['saturacion'] < 90:\n"
    "        return 'Rojo'\n"
    "    if data['saturacion'] < 94 or data['frecuencia_cardiaca'] > 120 or data['dolor'] >= 8:\n"
    "        return 'Naranja'\n"
    "    if data['temperatura'] >= Decimal('38.5') or data['dolor'] >= 5:\n"
    "        return 'Amarillo'\n"
    "    return 'Verde'\n",
    [
        ("V1-INCONSCIENTE", env(consciente=False, saturacion=98, frecuencia_cardiaca=80, temperatura=36.5, dolor=0)),
        ("V2-SATURACION-89", env(consciente=True, saturacion=89, frecuencia_cardiaca=80, temperatura=36.5, dolor=0)),
        ("V3-SATURACION-90", env(consciente=True, saturacion=90, frecuencia_cardiaca=80, temperatura=36.5, dolor=0)),
        ("V4-TAQUICARDIA", env(consciente=True, saturacion=97, frecuencia_cardiaca=121, temperatura=36.8, dolor=2)),
        ("V5-FRECUENCIA-120", env(consciente=True, saturacion=97, frecuencia_cardiaca=120, temperatura=36.8, dolor=2)),
        ("V6-FIEBRE-38-5", env(consciente=True, saturacion=97, frecuencia_cardiaca=90, temperatura=38.5, dolor=1)),
        ("V7-DOLOR-8", env(consciente=True, saturacion=96, frecuencia_cardiaca=90, temperatura=37.2, dolor=8)),
        ("V8-DOLOR-5", env(consciente=True, saturacion=96, frecuencia_cardiaca=90, temperatura=37.2, dolor=5)),
        ("V9-ESTABLE", env(consciente=True, saturacion=98, frecuencia_cardiaca=72, temperatura=38.4, dolor=4)),
    ],
)

CONDICIONES = ["diabetes", "asma", "epoc", "cardiopatia", "insuficiencia_renal", "inmunodepresion",
               "obesidad_morbida", "cancer_en_tratamiento", "trasplante"]
rule(
    1, "vacuna-antigripal", "SAL-C1-VACUNA-GRIPE",
    "Determinar si una persona recibe gratis la vacuna antigripal. La recibe si cumple al menos uno de estos "
    "criterios: tiene 65 años o más; tiene menos de 2 años; está embarazada; trabaja en salud; o tiene una de estas "
    "condiciones, informadas con estos códigos exactos: " + ", ".join(f'"{c}"' for c in CONDICIONES[:-1])
    + f' o "{CONDICIONES[-1]}". Si no tiene ninguna condición, el código es "ninguna"; cualquier otro código '
    "(por ejemplo \"hipertension\" o \"alergia\") no da derecho a la vacuna gratuita.",
    {"condicion": "String", "edad": "Int", "embarazada": "Bool", "personal_salud": "Bool"},
    any_(op(">=", var("edad"), lit(65)), op("<", var("edad"), lit(2)), var("embarazada"), var("personal_salud"),
         in_(var("condicion"), CONDICIONES)),
    f"CONDICIONES = {tuple(CONDICIONES)!r}\n\n"
    "def evaluate_rule(data):\n"
    "    return (\n"
    "        data['edad'] >= 65\n"
    "        or data['edad'] < 2\n"
    "        or data['embarazada']\n"
    "        or data['personal_salud']\n"
    "        or data['condicion'] in CONDICIONES\n"
    "    )\n",
    [
        ("V1-MAYOR-65", env(edad=65, embarazada=False, personal_salud=False, condicion="ninguna")),
        ("V2-64-SANO", env(edad=64, embarazada=False, personal_salud=False, condicion="ninguna")),
        ("V3-BEBE-1", env(edad=1, embarazada=False, personal_salud=False, condicion="ninguna")),
        ("V4-NINO-2", env(edad=2, embarazada=False, personal_salud=False, condicion="ninguna")),
        ("V5-EMBARAZADA", env(edad=30, embarazada=True, personal_salud=False, condicion="ninguna")),
        ("V6-ENFERMERO", env(edad=40, embarazada=False, personal_salud=True, condicion="ninguna")),
        ("V7-TRASPLANTE", env(edad=50, embarazada=False, personal_salud=False, condicion="trasplante")),
        ("V8-HIPERTENSION", env(edad=50, embarazada=False, personal_salud=False, condicion="hipertension")),
        ("V9-ALERGIA", env(edad=33, embarazada=False, personal_salud=False, condicion="alergia")),
        ("V10-ASMA", env(edad=12, embarazada=False, personal_salud=False, condicion="asma")),
        ("V11-ADULTO-SANO", env(edad=25, embarazada=False, personal_salud=False, condicion="ninguna")),
    ],
)

rule(
    1, "cirugia-programada", "SAL-C1-CIRUGIA",
    "Determinar si un paciente está en condiciones de entrar a una cirugía programada. Lo está solo si se cumplen "
    "todas estas condiciones: firmó el consentimiento informado; lleva al menos 8 horas de ayuno; su hemoglobina es "
    "de 10.0 g/dL o más (se informa con un decimal); no está tomando anticoagulantes; su riesgo anestésico ASA es 1, "
    "2 o 3; y, si tiene 70 años o más, ya pasó por la evaluación cardiológica. Un paciente menor de 70 no necesita la "
    "evaluación cardiológica.",
    {"anticoagulado": "Bool", "consentimiento": "Bool", "edad": "Int", "evaluacion_cardiologica": "Bool",
     "hemoglobina": "Decimal", "horas_ayuno": "Int", "riesgo_asa": "Int"},
    all_(var("consentimiento"), op(">=", var("horas_ayuno"), lit(8)), op(">=", var("hemoglobina"), dec("10.0")),
         not_(var("anticoagulado")), in_(var("riesgo_asa"), [1, 2, 3]),
         op("OR", op("<", var("edad"), lit(70)), var("evaluacion_cardiologica"))),
    "from decimal import Decimal\n\n"
    "def evaluate_rule(data):\n"
    "    return (\n"
    "        data['consentimiento']\n"
    "        and data['horas_ayuno'] >= 8\n"
    "        and data['hemoglobina'] >= Decimal('10.0')\n"
    "        and not data['anticoagulado']\n"
    "        and data['riesgo_asa'] in (1, 2, 3)\n"
    "        and (data['edad'] < 70 or data['evaluacion_cardiologica'])\n"
    "    )\n",
    [
        ("V1-APTO", env(consentimiento=True, horas_ayuno=8, hemoglobina=12.5, anticoagulado=False, riesgo_asa=2, edad=45, evaluacion_cardiologica=False)),
        ("V2-SIN-CONSENTIMIENTO", env(consentimiento=False, horas_ayuno=10, hemoglobina=12.5, anticoagulado=False, riesgo_asa=1, edad=45, evaluacion_cardiologica=False)),
        ("V3-AYUNO-7", env(consentimiento=True, horas_ayuno=7, hemoglobina=12.5, anticoagulado=False, riesgo_asa=1, edad=45, evaluacion_cardiologica=False)),
        ("V4-HEMOGLOBINA-9-9", env(consentimiento=True, horas_ayuno=9, hemoglobina=9.9, anticoagulado=False, riesgo_asa=1, edad=45, evaluacion_cardiologica=False)),
        ("V5-HEMOGLOBINA-10-5", env(consentimiento=True, horas_ayuno=9, hemoglobina=10.5, anticoagulado=False, riesgo_asa=3, edad=69, evaluacion_cardiologica=False)),
        ("V6-ANTICOAGULADO", env(consentimiento=True, horas_ayuno=9, hemoglobina=13.5, anticoagulado=True, riesgo_asa=2, edad=50, evaluacion_cardiologica=False)),
        ("V7-ASA-4", env(consentimiento=True, horas_ayuno=9, hemoglobina=13.5, anticoagulado=False, riesgo_asa=4, edad=50, evaluacion_cardiologica=False)),
        ("V8-70-SIN-EVALUACION", env(consentimiento=True, horas_ayuno=9, hemoglobina=13.5, anticoagulado=False, riesgo_asa=2, edad=70, evaluacion_cardiologica=False)),
        ("V9-70-CON-EVALUACION", env(consentimiento=True, horas_ayuno=9, hemoglobina=13.5, anticoagulado=False, riesgo_asa=2, edad=70, evaluacion_cardiologica=True)),
        ("V10-ASA-1-JOVEN", env(consentimiento=True, horas_ayuno=12, hemoglobina=11.2, anticoagulado=False, riesgo_asa=1, edad=30, evaluacion_cardiologica=False)),
        ("V11-MAYOR-EVALUADO", env(consentimiento=True, horas_ayuno=10, hemoglobina=12.1, anticoagulado=False, riesgo_asa=3, edad=82, evaluacion_cardiologica=True)),
    ],
)

CARDIO = ["dolor_toracico", "palpitaciones", "hipertension"]
NEURO = ["cefalea", "convulsiones", "mareos", "perdida_de_memoria"]
NEUMO = ["tos_cronica", "disnea", "asma"]
DERMA = ["erupcion", "picazon", "lunar_cambiante", "acne"]
rule(
    1, "derivacion", "SAL-C1-DERIVACION",
    "Indicar a qué especialidad se deriva a un paciente según su motivo de consulta. Los menores de 15 años van "
    "siempre a \"Pediatría\", sin importar el motivo. Para los demás: los motivos \"dolor_toracico\", "
    "\"palpitaciones\" e \"hipertension\" van a \"Cardiología\"; \"cefalea\", \"convulsiones\", \"mareos\" y "
    "\"perdida_de_memoria\", a \"Neurología\"; \"tos_cronica\", \"disnea\" y \"asma\", a \"Neumonología\"; "
    "\"erupcion\", \"picazon\", \"lunar_cambiante\" y \"acne\", a \"Dermatología\". Cualquier otro motivo va a "
    "\"Clínica médica\".",
    {"edad": "Int", "motivo": "String"},
    ite(op("<", var("edad"), lit(15)), S("Pediatría"),
        ite(in_(var("motivo"), CARDIO), S("Cardiología"),
            ite(in_(var("motivo"), NEURO), S("Neurología"),
                ite(in_(var("motivo"), NEUMO), S("Neumonología"),
                    ite(in_(var("motivo"), DERMA), S("Dermatología"), S("Clínica médica")))))),
    f"CARDIO = {tuple(CARDIO)!r}\nNEURO = {tuple(NEURO)!r}\nNEUMO = {tuple(NEUMO)!r}\nDERMA = {tuple(DERMA)!r}\n\n"
    "def evaluate_rule(data):\n"
    "    if data['edad'] < 15:\n"
    "        return 'Pediatría'\n"
    "    motivo = data['motivo']\n"
    "    if motivo in CARDIO:\n"
    "        return 'Cardiología'\n"
    "    if motivo in NEURO:\n"
    "        return 'Neurología'\n"
    "    if motivo in NEUMO:\n"
    "        return 'Neumonología'\n"
    "    if motivo in DERMA:\n"
    "        return 'Dermatología'\n"
    "    return 'Clínica médica'\n",
    [
        ("V1-NINO-CON-ASMA", env(edad=14, motivo="asma")),
        ("V2-15-ASMA", env(edad=15, motivo="asma")),
        ("V3-PALPITACIONES", env(edad=50, motivo="palpitaciones")),
        ("V4-MEMORIA", env(edad=78, motivo="perdida_de_memoria")),
        ("V5-ACNE", env(edad=19, motivo="acne")),
        ("V6-DOLOR-DE-RODILLA", env(edad=40, motivo="dolor_de_rodilla")),
        ("V7-HIPERTENSION", env(edad=60, motivo="hipertension")),
        ("V8-MAREOS", env(edad=35, motivo="mareos")),
    ],
)

rule(
    1, "alta-hospitalaria", "SAL-C1-ALTA",
    "Determinar si un paciente internado puede recibir el alta. Puede, solo si se cumplen todas estas condiciones: "
    "lleva al menos 24 horas sin fiebre; su saturación de oxígeno es 94 % o más; tolera la alimentación por boca; "
    "su dolor, en una escala de 0 a 10, es 3 o menos; no tiene drenajes colocados; y, si vive solo, cuenta con un "
    "acompañante para los primeros días. Si no vive solo, no hace falta el acompañante.",
    {"dolor": "Int", "horas_sin_fiebre": "Int", "saturacion": "Int", "tiene_acompanante": "Bool",
     "tiene_drenajes": "Bool", "tolera_via_oral": "Bool", "vive_solo": "Bool"},
    all_(op(">=", var("horas_sin_fiebre"), lit(24)), op(">=", var("saturacion"), lit(94)), var("tolera_via_oral"),
         op("<=", var("dolor"), lit(3)), not_(var("tiene_drenajes")),
         op("OR", not_(var("vive_solo")), var("tiene_acompanante"))),
    "def evaluate_rule(data):\n"
    "    return (\n"
    "        data['horas_sin_fiebre'] >= 24\n"
    "        and data['saturacion'] >= 94\n"
    "        and data['tolera_via_oral']\n"
    "        and data['dolor'] <= 3\n"
    "        and not data['tiene_drenajes']\n"
    "        and (not data['vive_solo'] or data['tiene_acompanante'])\n"
    "    )\n",
    [
        ("V1-ALTA", env(horas_sin_fiebre=24, saturacion=94, tolera_via_oral=True, dolor=3, tiene_drenajes=False, vive_solo=False, tiene_acompanante=False)),
        ("V2-23-HORAS", env(horas_sin_fiebre=23, saturacion=97, tolera_via_oral=True, dolor=1, tiene_drenajes=False, vive_solo=False, tiene_acompanante=False)),
        ("V3-SATURACION-93", env(horas_sin_fiebre=48, saturacion=93, tolera_via_oral=True, dolor=1, tiene_drenajes=False, vive_solo=False, tiene_acompanante=False)),
        ("V4-NO-TOLERA", env(horas_sin_fiebre=48, saturacion=97, tolera_via_oral=False, dolor=1, tiene_drenajes=False, vive_solo=False, tiene_acompanante=False)),
        ("V5-DOLOR-4", env(horas_sin_fiebre=48, saturacion=97, tolera_via_oral=True, dolor=4, tiene_drenajes=False, vive_solo=False, tiene_acompanante=False)),
        ("V6-DRENAJE", env(horas_sin_fiebre=48, saturacion=97, tolera_via_oral=True, dolor=0, tiene_drenajes=True, vive_solo=False, tiene_acompanante=False)),
        ("V7-SOLO-SIN-ACOMPANANTE", env(horas_sin_fiebre=48, saturacion=97, tolera_via_oral=True, dolor=0, tiene_drenajes=False, vive_solo=True, tiene_acompanante=False)),
        ("V8-SOLO-CON-ACOMPANANTE", env(horas_sin_fiebre=48, saturacion=97, tolera_via_oral=True, dolor=0, tiene_drenajes=False, vive_solo=True, tiene_acompanante=True)),
        ("V9-ACOMPANADO-SIN-NECESIDAD", env(horas_sin_fiebre=72, saturacion=99, tolera_via_oral=True, dolor=2, tiene_drenajes=False, vive_solo=False, tiene_acompanante=True)),
        ("V10-SOLO-ACOMPANADO-LIMITES", env(horas_sin_fiebre=24, saturacion=94, tolera_via_oral=True, dolor=3, tiene_drenajes=False, vive_solo=True, tiene_acompanante=True)),
        ("V11-SIN-DOLOR", env(horas_sin_fiebre=30, saturacion=96, tolera_via_oral=True, dolor=0, tiene_drenajes=False, vive_solo=False, tiene_acompanante=False)),
    ],
)

# ===================================== Categoría 2 =====================================

dosis = op("*", var("peso_kg"), lit(15))
rule(
    2, "dosis-paracetamol", "SAL-C2-DOSIS",
    "Calcular la dosis de paracetamol por toma, en miligramos, para un paciente según su peso en kilogramos (con "
    "decimales). La dosis es de 15 mg por kilo, con un máximo de 1000.0 mg por toma. Si el paciente pesa menos de "
    "5.0 kg, no se calcula dosis y el resultado es 0.0. La edad del paciente y la presentación del medicamento "
    "(jarabe o comprimidos) no cambian el cálculo.",
    {"peso_kg": "Decimal"},
    ite(op("<", var("peso_kg"), dec("5.0")), dec("0"),
        ite(op(">", dosis, lit(1000)), dec("1000.0"), dosis)),
    "from decimal import Decimal\n\n"
    "def evaluate_rule(data):\n"
    "    peso = data['peso_kg']\n"
    "    if peso < Decimal('5.0'):\n"
    "        return Decimal('0')\n"
    "    return min(peso * 15, Decimal('1000.0'))\n",
    [
        ("V1-MENOS-DE-5", env(peso_kg=4.5)),
        ("V2-5-Y-MEDIO", env(peso_kg=5.5)),
        ("V3-NINO", env(peso_kg=20.5)),
        ("V4-JUSTO-DEBAJO-DEL-TOPE", env(peso_kg=66.6)),
        ("V5-JUSTO-ARRIBA-DEL-TOPE", env(peso_kg=66.7)),
        ("V6-ADULTO", env(peso_kg=80.5)),
    ],
)

rule(
    2, "goteo", "SAL-C2-GOTEO",
    "Calcular a cuántas gotas por minuto hay que regular un suero. Se reciben el volumen a pasar, en mililitros "
    "enteros, y las horas en que debe pasar, también enteras. Con un equipo de 20 gotas por mililitro, el goteo es "
    "volumen * 20 / (horas * 60). El resultado se informa exacto, con decimales, sin redondear. El tipo de suero "
    "(fisiológico, dextrosa) no cambia la cuenta.",
    {"horas": "Int", "volumen_ml": "Int"},
    op("/", op("*", var("volumen_ml"), lit(20)), op("*", var("horas"), lit(60))),
    "from decimal import Decimal\n\n"
    "def evaluate_rule(data):\n"
    "    return Decimal(data['volumen_ml'] * 20) / Decimal(data['horas'] * 60)\n",
    [
        ("V1-1000-EN-8", env(volumen_ml=1000, horas=8)),
        ("V2-500-EN-4", env(volumen_ml=500, horas=4)),
        ("V3-1500-EN-24", env(volumen_ml=1500, horas=24)),
        ("V4-250-EN-1", env(volumen_ml=250, horas=1)),
        ("V5-EXACTO", env(volumen_ml=60, horas=1)),
        ("V6-100-EN-2", env(volumen_ml=100, horas=2)),
    ],
)

rule(
    2, "riesgo-cardiovascular", "SAL-C2-RIESGO-CV",
    "Calcular el puntaje de riesgo cardiovascular de un paciente, como número entero. Se suman puntos así: 3 si "
    "fuma; 2 si tiene diabetes; 2 si tiene 55 años o más; 2 si su colesterol total supera 240 mg/dL; y 1 si su "
    "presión sistólica es 140 o más. Cada condición que no se cumple suma 0. Los antecedentes familiares se "
    "registran en la historia clínica, pero no suman en este puntaje.",
    {"colesterol": "Int", "diabetes": "Bool", "edad": "Int", "fuma": "Bool", "sistolica": "Int"},
    op("+", op("+", op("+", op("+",
        ite(var("fuma"), lit(3), lit(0)),
        ite(var("diabetes"), lit(2), lit(0))),
        ite(op(">=", var("edad"), lit(55)), lit(2), lit(0))),
        ite(op(">", var("colesterol"), lit(240)), lit(2), lit(0))),
        ite(op(">=", var("sistolica"), lit(140)), lit(1), lit(0))),
    "def evaluate_rule(data):\n"
    "    puntos = 0\n"
    "    if data['fuma']:\n"
    "        puntos += 3\n"
    "    if data['diabetes']:\n"
    "        puntos += 2\n"
    "    if data['edad'] >= 55:\n"
    "        puntos += 2\n"
    "    if data['colesterol'] > 240:\n"
    "        puntos += 2\n"
    "    if data['sistolica'] >= 140:\n"
    "        puntos += 1\n"
    "    return puntos\n",
    [
        ("V1-SIN-RIESGO", env(fuma=False, diabetes=False, edad=40, colesterol=180, sistolica=120)),
        ("V2-TODO", env(fuma=True, diabetes=True, edad=60, colesterol=260, sistolica=150)),
        ("V3-LIMITES-QUE-SUMAN", env(fuma=False, diabetes=False, edad=55, colesterol=241, sistolica=140)),
        ("V4-LIMITES-QUE-NO-SUMAN", env(fuma=False, diabetes=False, edad=54, colesterol=240, sistolica=139)),
        ("V5-FUMADOR-JOVEN", env(fuma=True, diabetes=False, edad=30, colesterol=200, sistolica=118)),
        ("V6-DIABETICO", env(fuma=False, diabetes=True, edad=58, colesterol=210, sistolica=135)),
    ],
)

ESTUDIOS = ["laboratorio", "radiografia", "ecografia", "resonancia", "tomografia"]
pct = ite(eq("plan", "premium"), dec("0.9"), ite(eq("plan", "intermedio"), dec("0.7"), dec("0.5")))
rule(
    2, "reintegro-estudio", "SAL-C2-REINTEGRO",
    "Calcular el reintegro, en pesos con centavos, que la prepaga devuelve por un estudio pagado por el afiliado. "
    "Solo se reintegran estos estudios: " + ", ".join(f'"{e}"' for e in ESTUDIOS[:-1]) + f' y "{ESTUDIOS[-1]}"; '
    "para cualquier otro el reintegro es 0.0. El porcentaje depende del plan: 90 % para \"premium\", 70 % para "
    "\"intermedio\" y 50 % para \"basico\". El reintegro es el costo del estudio por ese porcentaje. La antigüedad "
    "del afiliado no cambia el porcentaje.",
    {"costo": "Decimal", "estudio": "String", "plan": "String"},
    ite(in_(var("estudio"), ESTUDIOS), op("*", var("costo"), pct), dec("0")),
    "from decimal import Decimal\n\n"
    f"ESTUDIOS = {tuple(ESTUDIOS)!r}\n"
    "PORCENTAJE = {'premium': Decimal('0.9'), 'intermedio': Decimal('0.7')}\n\n"
    "def evaluate_rule(data):\n"
    "    if data['estudio'] not in ESTUDIOS:\n"
    "        return Decimal('0')\n"
    "    return data['costo'] * PORCENTAJE.get(data['plan'], Decimal('0.5'))\n",
    [
        ("V1-PREMIUM", env(estudio="resonancia", plan="premium", costo=85000.5)),
        ("V2-INTERMEDIO", env(estudio="ecografia", plan="intermedio", costo=32000.25)),
        ("V3-BASICO", env(estudio="laboratorio", plan="basico", costo=12500.75)),
        ("V4-NO-CUBIERTO", env(estudio="acupuntura", plan="premium", costo=15000.5)),
        ("V5-TOMOGRAFIA-BASICO", env(estudio="tomografia", plan="basico", costo=64000.5)),
        ("V6-CENTAVOS", env(estudio="radiografia", plan="premium", costo=9999.99)),
    ],
)

semanas = op("/", var("dias_gestacion"), lit(7))
rule(
    2, "edad-gestacional", "SAL-C2-GESTACION",
    "Clasificar un parto según la edad gestacional. Se recibe la cantidad de días de gestación (entero) y se "
    "calculan las semanas como días / 7, con decimales. Si las semanas son menos de 37, el parto es \"Pretérmino\"; "
    "si son 37 o más pero menos de 42, es \"A término\"; con 42 semanas o más, es \"Postérmino\". La fecha de la "
    "última menstruación ya está reflejada en los días de gestación.",
    {"dias_gestacion": "Int"},
    ite(op("<", semanas, lit(37)), S("Pretérmino"), ite(op("<", semanas, lit(42)), S("A término"), S("Postérmino"))),
    "from decimal import Decimal\n\n"
    "def evaluate_rule(data):\n"
    "    semanas = Decimal(data['dias_gestacion']) / 7\n"
    "    if semanas < 37:\n"
    "        return 'Pretérmino'\n"
    "    if semanas < 42:\n"
    "        return 'A término'\n"
    "    return 'Postérmino'\n",
    [
        ("V1-258-DIAS", env(dias_gestacion=258)),
        ("V2-259-DIAS", env(dias_gestacion=259)),
        ("V3-280-DIAS", env(dias_gestacion=280)),
        ("V4-293-DIAS", env(dias_gestacion=293)),
        ("V5-294-DIAS", env(dias_gestacion=294)),
        ("V6-200-DIAS", env(dias_gestacion=200)),
    ],
)

tarifa = ite(eq("sala", "terapia_intensiva"), dec("4800.75"), ite(eq("sala", "intermedia"), dec("2500.5"), dec("1200.25")))
rule(
    2, "costo-internacion", "SAL-C2-INTERNACION",
    "Calcular el costo de una internación en pesos con centavos. Es la cantidad de días internado (entero) por la "
    "tarifa diaria de la sala, más el costo de los insumos. La tarifa diaria es 4800.75 para \"terapia_intensiva\", "
    "2500.50 para \"intermedia\" y 1200.25 para \"comun\". Los honorarios médicos se facturan aparte y no entran en "
    "este costo.",
    {"dias": "Int", "insumos": "Decimal", "sala": "String"},
    op("+", op("*", var("dias"), tarifa), var("insumos")),
    "from decimal import Decimal\n\n"
    "TARIFAS = {'terapia_intensiva': Decimal('4800.75'), 'intermedia': Decimal('2500.50')}\n\n"
    "def evaluate_rule(data):\n"
    "    tarifa = TARIFAS.get(data['sala'], Decimal('1200.25'))\n"
    "    return data['dias'] * tarifa + data['insumos']\n",
    [
        ("V1-COMUN", env(sala="comun", dias=3, insumos=1500.5)),
        ("V2-INTERMEDIA", env(sala="intermedia", dias=2, insumos=800.25)),
        ("V3-TERAPIA", env(sala="terapia_intensiva", dias=5, insumos=12000.75)),
        ("V4-UN-DIA", env(sala="comun", dias=1, insumos=0.5)),
        ("V5-SIN-DIAS", env(sala="terapia_intensiva", dias=0, insumos=350.25)),
        ("V6-LARGA", env(sala="intermedia", dias=30, insumos=45000.5)),
    ],
)

# ===================================== Categoría 3 =====================================

rule(
    3, "fiebre", "SAL-C3-FIEBRE",
    "Determinar si un paciente tiene fiebre según su temperatura axilar, informada con un decimal. Tiene fiebre a "
    "partir de 38.0 grados. La excepción son los bebés de menos de 3 meses: para ellos, la fiebre empieza en 37.5 "
    "grados. La edad se informa en meses cumplidos.",
    {"edad_meses": "Int", "temperatura": "Decimal"},
    op(">=", var("temperatura"), ite(op("<", var("edad_meses"), lit(3)), dec("37.5"), dec("38.0"))),
    "from decimal import Decimal\n\n"
    "def evaluate_rule(data):\n"
    "    umbral = Decimal('37.5') if data['edad_meses'] < 3 else Decimal('38.0')\n"
    "    return data['temperatura'] >= umbral\n",
    [
        ("V1-ADULTO-38-5", env(edad_meses=480, temperatura=38.5)),
        ("V2-ADULTO-37-9", env(edad_meses=480, temperatura=37.9)),
        ("V3-BEBE-37-5", env(edad_meses=2, temperatura=37.5)),
        ("V4-BEBE-37-4", env(edad_meses=2, temperatura=37.4)),
        ("V5-TRES-MESES-37-5", env(edad_meses=3, temperatura=37.5)),
        ("V6-ADULTO-39", env(edad_meses=300, temperatura=39.2)),
        ("V7-NINO-38-1", env(edad_meses=30, temperatura=38.1)),
        ("V8-NINO-36-8", env(edad_meses=30, temperatura=36.8)),
    ],
)

rule(
    3, "intervalo-dosis", "SAL-C3-INTERVALO",
    "Determinar si se puede aplicar la siguiente dosis de una vacuna de tres dosis. Se puede si la persona recibió "
    "menos de 3 dosis y pasaron al menos 28 días desde la última. La excepción es el esquema acelerado: con ese "
    "esquema alcanzan 21 días desde la última dosis, pero sigue habiendo un máximo de 3 dosis.",
    {"dias_desde_ultima": "Int", "dosis_aplicadas": "Int", "esquema_acelerado": "Bool"},
    op("AND", op("<", var("dosis_aplicadas"), lit(3)),
       op(">=", var("dias_desde_ultima"), ite(var("esquema_acelerado"), lit(21), lit(28)))),
    "def evaluate_rule(data):\n"
    "    minimo = 21 if data['esquema_acelerado'] else 28\n"
    "    return data['dosis_aplicadas'] < 3 and data['dias_desde_ultima'] >= minimo\n",
    [
        ("V1-28-DIAS", env(dosis_aplicadas=1, dias_desde_ultima=28, esquema_acelerado=False)),
        ("V2-27-DIAS", env(dosis_aplicadas=1, dias_desde_ultima=27, esquema_acelerado=False)),
        ("V3-ACELERADO-21", env(dosis_aplicadas=2, dias_desde_ultima=21, esquema_acelerado=True)),
        ("V4-ACELERADO-20", env(dosis_aplicadas=2, dias_desde_ultima=20, esquema_acelerado=True)),
        ("V5-YA-TIENE-3", env(dosis_aplicadas=3, dias_desde_ultima=90, esquema_acelerado=False)),
        ("V6-ACELERADO-CON-3", env(dosis_aplicadas=3, dias_desde_ultima=30, esquema_acelerado=True)),
        ("V7-SEGUNDA-TARDE", env(dosis_aplicadas=1, dias_desde_ultima=120, esquema_acelerado=False)),
        ("V8-ACELERADO-25", env(dosis_aplicadas=1, dias_desde_ultima=25, esquema_acelerado=True)),
    ],
)

rule(
    3, "ayuno", "SAL-C3-AYUNO",
    "Determinar si un paciente cumple el ayuno para ser anestesiado. Lo cumple si lleva al menos 8 horas sin comer "
    "sólidos y al menos 2 horas sin tomar líquidos claros. Si la cirugía es de urgencia, se anestesia igual, "
    "aunque no cumpla ninguna de las dos condiciones.",
    {"horas_sin_liquidos": "Int", "horas_sin_solidos": "Int", "urgencia": "Bool"},
    op("OR", var("urgencia"),
       op("AND", op(">=", var("horas_sin_solidos"), lit(8)), op(">=", var("horas_sin_liquidos"), lit(2)))),
    "def evaluate_rule(data):\n"
    "    return data['urgencia'] or (data['horas_sin_solidos'] >= 8 and data['horas_sin_liquidos'] >= 2)\n",
    [
        ("V1-CUMPLE", env(horas_sin_solidos=8, horas_sin_liquidos=2, urgencia=False)),
        ("V2-SOLIDOS-7", env(horas_sin_solidos=7, horas_sin_liquidos=5, urgencia=False)),
        ("V3-LIQUIDOS-1", env(horas_sin_solidos=10, horas_sin_liquidos=1, urgencia=False)),
        ("V4-URGENCIA", env(horas_sin_solidos=1, horas_sin_liquidos=0, urgencia=True)),
        ("V5-NADA", env(horas_sin_solidos=3, horas_sin_liquidos=1, urgencia=False)),
        ("V6-URGENCIA-CON-AYUNO", env(horas_sin_solidos=12, horas_sin_liquidos=6, urgencia=True)),
        ("V7-SOLO-SOLIDOS", env(horas_sin_solidos=12, horas_sin_liquidos=0, urgencia=False)),
        ("V8-LARGO", env(horas_sin_solidos=14, horas_sin_liquidos=3, urgencia=False)),
    ],
)

rule(
    3, "renovacion-receta", "SAL-C3-RECETA",
    "Determinar si la farmacia puede renovar una receta sin pedir una nueva al médico. Puede, si a la receta le "
    "quedan renovaciones disponibles y fue emitida hace 30 días o menos. Nunca se renueva un medicamento "
    "controlado, aunque le queden renovaciones y esté dentro del plazo.",
    {"dias_desde_emision": "Int", "es_controlado": "Bool", "renovaciones_restantes": "Int"},
    all_(not_(var("es_controlado")), op(">", var("renovaciones_restantes"), lit(0)),
         op("<=", var("dias_desde_emision"), lit(30))),
    "def evaluate_rule(data):\n"
    "    return (\n"
    "        not data['es_controlado']\n"
    "        and data['renovaciones_restantes'] > 0\n"
    "        and data['dias_desde_emision'] <= 30\n"
    "    )\n",
    [
        ("V1-DIA-30", env(es_controlado=False, renovaciones_restantes=1, dias_desde_emision=30)),
        ("V2-DIA-31", env(es_controlado=False, renovaciones_restantes=1, dias_desde_emision=31)),
        ("V3-SIN-RENOVACIONES", env(es_controlado=False, renovaciones_restantes=0, dias_desde_emision=5)),
        ("V4-CONTROLADO", env(es_controlado=True, renovaciones_restantes=2, dias_desde_emision=5)),
        ("V5-RECIENTE", env(es_controlado=False, renovaciones_restantes=3, dias_desde_emision=0)),
        ("V6-CONTROLADO-VENCIDO", env(es_controlado=True, renovaciones_restantes=0, dias_desde_emision=40)),
        ("V7-DOS-RENOVACIONES", env(es_controlado=False, renovaciones_restantes=2, dias_desde_emision=12)),
    ],
)

rule(
    3, "hipertension", "SAL-C3-HIPERTENSION",
    "Determinar si una toma de presión arterial es compatible con hipertensión. Lo es si la presión sistólica es "
    "140 o más, o si la diastólica es 90 o más: alcanza con que una de las dos esté alta. Con una sistólica de 139 "
    "y una diastólica de 89, la toma no es compatible con hipertensión.",
    {"diastolica": "Int", "sistolica": "Int"},
    op("OR", op(">=", var("sistolica"), lit(140)), op(">=", var("diastolica"), lit(90))),
    "def evaluate_rule(data):\n"
    "    return data['sistolica'] >= 140 or data['diastolica'] >= 90\n",
    [
        ("V1-NORMAL", env(sistolica=120, diastolica=80)),
        ("V2-SISTOLICA-140", env(sistolica=140, diastolica=80)),
        ("V3-DIASTOLICA-90", env(sistolica=125, diastolica=90)),
        ("V4-LIMITE-BAJO", env(sistolica=139, diastolica=89)),
        ("V5-AMBAS-ALTAS", env(sistolica=165, diastolica=100)),
        ("V6-BAJA", env(sistolica=95, diastolica=60)),
    ],
)

rule(
    3, "dosis-diaria", "SAL-C3-DOSIS-DIARIA",
    "Determinar si una indicación supera la dosis máxima diaria de un medicamento. La dosis diaria es la dosis por "
    "toma, en miligramos, por la cantidad de tomas por día. La indicación supera el máximo solo si la dosis diaria es "
    "mayor que el máximo diario; si es igual, no lo supera.",
    {"dosis_mg": "Int", "maximo_diario_mg": "Int", "tomas_por_dia": "Int"},
    op(">", op("*", var("dosis_mg"), var("tomas_por_dia")), var("maximo_diario_mg")),
    "def evaluate_rule(data):\n"
    "    return data['dosis_mg'] * data['tomas_por_dia'] > data['maximo_diario_mg']\n",
    [
        ("V1-IGUAL-AL-MAXIMO", env(dosis_mg=1000, tomas_por_dia=4, maximo_diario_mg=4000)),
        ("V2-SUPERA", env(dosis_mg=1000, tomas_por_dia=5, maximo_diario_mg=4000)),
        ("V3-DEBAJO", env(dosis_mg=500, tomas_por_dia=3, maximo_diario_mg=4000)),
        ("V4-UN-MG-DE-MAS", env(dosis_mg=401, tomas_por_dia=3, maximo_diario_mg=1202)),
        ("V5-UNA-TOMA", env(dosis_mg=200, tomas_por_dia=1, maximo_diario_mg=1200)),
        ("V6-MUCHAS-TOMAS", env(dosis_mg=250, tomas_por_dia=6, maximo_diario_mg=1200)),
    ],
)
print("ok")
