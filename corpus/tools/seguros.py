"""Tandas del dominio seguros: 6 reglas por categoría, propias. Ver corpus/README.md.

Inspiradas en los desafíos de seguros de la Decision Management Community, sin
copiar su texto. Montos en pesos.

    docker compose run --rm pipeline python /workspace/corpus/tools/seguros.py /workspace/corpus
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from dsl import ORIGINAL, all_, any_, dec, eq, in_, ite, lit, not_, op, var, write_rule  # noqa: E402

OUT = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(__file__).parents[1]
S = lit


def rule(category, name, case_id, description, gamma, expr, python, scenarios):
    write_rule(
        OUT, f"seguros-c{category}-{name}", case_id=case_id, category=category, domain="seguros", source=ORIGINAL,
        description=description, gamma=gamma, expr=expr, python=python, scenarios=scenarios,
        generator="corpus/tools/seguros.py",
    )


def env(**kw):
    return kw


# ===================================== Categoría 1 =====================================

rule(
    1, "riesgo-conductor", "SEG-C1-RIESGO-AUTO",
    "Clasificar el riesgo de un conductor para cotizar un seguro de auto, revisando las condiciones en este orden y "
    "quedándose con la primera que se cumpla. El riesgo es \"Alto\" si el conductor tiene menos de 21 años, si tuvo "
    "3 o más siniestros en los últimos 3 años o si tiene licencia hace menos de 1 año. Si no, es \"Medio\" si tiene "
    "más de 75 años, si tuvo 1 o 2 siniestros o si el auto tiene más de 15 años de antigüedad. Si no, es \"Bajo\".",
    {"anios_licencia": "Int", "antiguedad_auto": "Int", "edad": "Int", "siniestros": "Int"},
    ite(any_(op("<", var("edad"), lit(21)), op(">=", var("siniestros"), lit(3)), op("<", var("anios_licencia"), lit(1))), S("Alto"),
        ite(any_(op(">", var("edad"), lit(75)), op(">=", var("siniestros"), lit(1)), op(">", var("antiguedad_auto"), lit(15))),
            S("Medio"), S("Bajo"))),
    "def evaluate_rule(data):\n"
    "    if data['edad'] < 21 or data['siniestros'] >= 3 or data['anios_licencia'] < 1:\n"
    "        return 'Alto'\n"
    "    if data['edad'] > 75 or data['siniestros'] >= 1 or data['antiguedad_auto'] > 15:\n"
    "        return 'Medio'\n"
    "    return 'Bajo'\n",
    [
        ("V1-JOVEN", env(edad=20, siniestros=0, anios_licencia=3, antiguedad_auto=2)),
        ("V2-TRES-SINIESTROS", env(edad=40, siniestros=3, anios_licencia=20, antiguedad_auto=2)),
        ("V3-LICENCIA-NUEVA", env(edad=35, siniestros=0, anios_licencia=0, antiguedad_auto=2)),
        ("V4-MAYOR-76", env(edad=76, siniestros=0, anios_licencia=50, antiguedad_auto=5)),
        ("V5-UN-SINIESTRO", env(edad=40, siniestros=1, anios_licencia=20, antiguedad_auto=5)),
        ("V6-AUTO-VIEJO", env(edad=40, siniestros=0, anios_licencia=20, antiguedad_auto=16)),
        ("V7-BAJO", env(edad=40, siniestros=0, anios_licencia=20, antiguedad_auto=15)),
        ("V8-LIMITES-BAJO", env(edad=21, siniestros=0, anios_licencia=1, antiguedad_auto=0)),
        ("V9-75-ANIOS", env(edad=75, siniestros=0, anios_licencia=55, antiguedad_auto=10)),
    ],
)

CUBIERTOS = ["incendio", "robo", "rayo", "explosion", "granizo", "danio_por_agua", "rotura_de_cristales"]
rule(
    1, "cobertura-hogar", "SEG-C1-HOGAR",
    "Determinar si un siniestro de hogar está cubierto. Lo está si se cumplen todas estas condiciones: el evento es "
    "uno de los cubiertos, informados con estos códigos: " + ", ".join(f'"{c}"' for c in CUBIERTOS[:-1])
    + f' o "{CUBIERTOS[-1]}"; la póliza estaba vigente el día del siniestro; la vivienda no estaba deshabitada '
    "hace más de 60 días seguidos; y, si el evento es \"robo\", la puerta tenía cerradura de seguridad. Cualquier "
    "otro evento, como \"inundacion\" o \"terremoto\", no está cubierto.",
    {"cerradura_seguridad": "Bool", "dias_deshabitada": "Int", "evento": "String", "poliza_vigente": "Bool"},
    all_(in_(var("evento"), CUBIERTOS), var("poliza_vigente"), op("<=", var("dias_deshabitada"), lit(60)),
         op("OR", op("!=", var("evento"), lit("robo")), var("cerradura_seguridad"))),
    f"CUBIERTOS = {tuple(CUBIERTOS)!r}\n\n"
    "def evaluate_rule(data):\n"
    "    return (\n"
    "        data['evento'] in CUBIERTOS\n"
    "        and data['poliza_vigente']\n"
    "        and data['dias_deshabitada'] <= 60\n"
    "        and (data['evento'] != 'robo' or data['cerradura_seguridad'])\n"
    "    )\n",
    [
        ("V1-INCENDIO", env(evento="incendio", poliza_vigente=True, dias_deshabitada=0, cerradura_seguridad=False)),
        ("V2-TERREMOTO", env(evento="terremoto", poliza_vigente=True, dias_deshabitada=0, cerradura_seguridad=True)),
        ("V3-POLIZA-VENCIDA", env(evento="granizo", poliza_vigente=False, dias_deshabitada=0, cerradura_seguridad=True)),
        ("V4-DESHABITADA-61", env(evento="danio_por_agua", poliza_vigente=True, dias_deshabitada=61, cerradura_seguridad=True)),
        ("V5-DESHABITADA-60", env(evento="danio_por_agua", poliza_vigente=True, dias_deshabitada=60, cerradura_seguridad=False)),
        ("V6-ROBO-SIN-CERRADURA", env(evento="robo", poliza_vigente=True, dias_deshabitada=0, cerradura_seguridad=False)),
        ("V7-ROBO-CON-CERRADURA", env(evento="robo", poliza_vigente=True, dias_deshabitada=10, cerradura_seguridad=True)),
        ("V8-CRISTALES", env(evento="rotura_de_cristales", poliza_vigente=True, dias_deshabitada=3, cerradura_seguridad=False)),
        ("V9-INUNDACION", env(evento="inundacion", poliza_vigente=True, dias_deshabitada=0, cerradura_seguridad=True)),
    ],
)

ENFERMEDADES = ["cancer", "cardiopatia", "insuficiencia_renal", "hepatitis_cronica", "vih", "diabetes_insulinodependiente"]
rule(
    1, "seguro-de-vida", "SEG-C1-VIDA",
    "Determinar si una persona puede contratar el seguro de vida sin examen médico. Puede, solo si se cumplen todas "
    "estas condiciones: tiene entre 18 y 65 años, ambos incluidos; su índice de masa corporal (con un decimal) está "
    "entre 18.5 y 32.0, ambos incluidos; no declara ninguna de estas enfermedades: "
    + ", ".join(f'"{e}"' for e in ENFERMEDADES[:-1]) + f' ni "{ENFERMEDADES[-1]}" (sin enfermedades se informa '
    "\"ninguna\"); y la suma asegurada no supera 50000000 pesos, salvo que no fume, en cuyo caso el tope es 80000000.",
    {"edad": "Int", "enfermedad": "String", "fuma": "Bool", "imc": "Decimal", "suma_asegurada": "Int"},
    all_(op(">=", var("edad"), lit(18)), op("<=", var("edad"), lit(65)),
         op(">=", var("imc"), dec("18.5")), op("<=", var("imc"), dec("32.0")),
         not_(in_(var("enfermedad"), ENFERMEDADES)),
         op("<=", var("suma_asegurada"), ite(var("fuma"), lit(50000000), lit(80000000)))),
    "from decimal import Decimal\n\n"
    f"ENFERMEDADES = {tuple(ENFERMEDADES)!r}\n\n"
    "def evaluate_rule(data):\n"
    "    tope = 50000000 if data['fuma'] else 80000000\n"
    "    return (\n"
    "        18 <= data['edad'] <= 65\n"
    "        and Decimal('18.5') <= data['imc'] <= Decimal('32.0')\n"
    "        and data['enfermedad'] not in ENFERMEDADES\n"
    "        and data['suma_asegurada'] <= tope\n"
    "    )\n",
    [
        ("V1-APTO", env(edad=40, imc=24.5, enfermedad="ninguna", fuma=False, suma_asegurada=60000000)),
        ("V2-MENOR", env(edad=17, imc=22.5, enfermedad="ninguna", fuma=False, suma_asegurada=1000000)),
        ("V3-66", env(edad=66, imc=22.5, enfermedad="ninguna", fuma=False, suma_asegurada=1000000)),
        ("V4-IMC-BAJO", env(edad=30, imc=18.4, enfermedad="ninguna", fuma=False, suma_asegurada=1000000)),
        ("V5-IMC-ALTO", env(edad=30, imc=32.1, enfermedad="ninguna", fuma=False, suma_asegurada=1000000)),
        ("V6-CARDIOPATIA", env(edad=50, imc=26.5, enfermedad="cardiopatia", fuma=False, suma_asegurada=1000000)),
        ("V7-FUMADOR-SUMA-ALTA", env(edad=35, imc=23.5, enfermedad="ninguna", fuma=True, suma_asegurada=60000000)),
        ("V8-FUMADOR-TOPE", env(edad=35, imc=23.5, enfermedad="ninguna", fuma=True, suma_asegurada=50000000)),
        ("V9-ASMA-NO-EXCLUYE", env(edad=28, imc=19.5, enfermedad="asma", fuma=False, suma_asegurada=20000000)),
        ("V10-LIMITES", env(edad=65, imc=31.9, enfermedad="ninguna", fuma=False, suma_asegurada=80000000)),
        ("V11-18-ANIOS", env(edad=18, imc=18.6, enfermedad="ninguna", fuma=True, suma_asegurada=5000000)),
        ("V12-SUMA-80-MILLONES-MAS-UNO", env(edad=45, imc=27.5, enfermedad="ninguna", fuma=False, suma_asegurada=80000001)),
        ("V13-ADULTO-SANO", env(edad=50, imc=29.5, enfermedad="ninguna", fuma=False, suma_asegurada=40000000)),
    ],
)

rule(
    1, "deducible", "SEG-C1-DEDUCIBLE",
    "Indicar el deducible, en pesos, de un siniestro según el tipo de póliza y la cantidad de siniestros previos del "
    "año. Para la póliza \"todo_riesgo\", el deducible es 150000 si es el primer siniestro del año (0 previos), 300000 "
    "si hubo 1 previo y 500000 si hubo 2 o más. Para \"terceros_completo\", es 80000 sin siniestros previos y 160000 "
    "con 1 o más. Para \"terceros\", siempre es 0. Si el conductor tenía menos de 25 años, al deducible que "
    "corresponda se le suman 50000.",
    {"edad_conductor": "Int", "poliza": "String", "siniestros_previos": "Int"},
    op("+",
       ite(eq("poliza", "todo_riesgo"),
           ite(op("==", var("siniestros_previos"), lit(0)), lit(150000),
               ite(op("==", var("siniestros_previos"), lit(1)), lit(300000), lit(500000))),
           ite(eq("poliza", "terceros_completo"),
               ite(op("==", var("siniestros_previos"), lit(0)), lit(80000), lit(160000)),
               lit(0))),
       ite(op("<", var("edad_conductor"), lit(25)), lit(50000), lit(0))),
    "def evaluate_rule(data):\n"
    "    previos, poliza = data['siniestros_previos'], data['poliza']\n"
    "    if poliza == 'todo_riesgo':\n"
    "        deducible = 150000 if previos == 0 else 300000 if previos == 1 else 500000\n"
    "    elif poliza == 'terceros_completo':\n"
    "        deducible = 80000 if previos == 0 else 160000\n"
    "    else:\n"
    "        deducible = 0\n"
    "    if data['edad_conductor'] < 25:\n"
    "        deducible += 50000\n"
    "    return deducible\n",
    [
        ("V1-TODO-RIESGO-PRIMERO", env(poliza="todo_riesgo", siniestros_previos=0, edad_conductor=40)),
        ("V2-TODO-RIESGO-SEGUNDO", env(poliza="todo_riesgo", siniestros_previos=1, edad_conductor=40)),
        ("V3-TODO-RIESGO-TERCERO", env(poliza="todo_riesgo", siniestros_previos=2, edad_conductor=40)),
        ("V4-COMPLETO", env(poliza="terceros_completo", siniestros_previos=0, edad_conductor=40)),
        ("V5-COMPLETO-CON-PREVIOS", env(poliza="terceros_completo", siniestros_previos=3, edad_conductor=40)),
        ("V6-TERCEROS", env(poliza="terceros", siniestros_previos=2, edad_conductor=40)),
        ("V7-JOVEN", env(poliza="todo_riesgo", siniestros_previos=0, edad_conductor=24)),
        ("V8-JOVEN-TERCEROS", env(poliza="terceros", siniestros_previos=0, edad_conductor=19)),
        ("V9-25-ANIOS", env(poliza="terceros_completo", siniestros_previos=1, edad_conductor=25)),
    ],
)

rule(
    1, "aprobacion-reclamo", "SEG-C1-RECLAMO",
    "Determinar si se aprueba el pago de un reclamo. Se aprueba solo si se cumplen todas estas condiciones: la "
    "denuncia se hizo dentro de las 72 horas del siniestro; la póliza tiene las cuotas al día; el monto reclamado no "
    "supera la suma asegurada; hay denuncia policial cuando el siniestro es \"robo\" o \"hurto\" (para los demás "
    "tipos no hace falta); y el asegurado no tiene otro reclamo abierto, salvo que la póliza sea \"premium\", que "
    "admite reclamos simultáneos. El tipo de póliza puede ser \"basica\", \"intermedia\" o \"premium\".",
    {"cuotas_al_dia": "Bool", "denuncia_policial": "Bool", "horas_hasta_denuncia": "Int", "monto_reclamado": "Int",
     "otro_reclamo_abierto": "Bool", "poliza": "String", "suma_asegurada": "Int", "tipo_siniestro": "String"},
    all_(op("<=", var("horas_hasta_denuncia"), lit(72)), var("cuotas_al_dia"),
         op("<=", var("monto_reclamado"), var("suma_asegurada")),
         op("OR", not_(in_(var("tipo_siniestro"), ["robo", "hurto"])), var("denuncia_policial")),
         op("OR", not_(var("otro_reclamo_abierto")), eq("poliza", "premium"))),
    "def evaluate_rule(data):\n"
    "    return (\n"
    "        data['horas_hasta_denuncia'] <= 72\n"
    "        and data['cuotas_al_dia']\n"
    "        and data['monto_reclamado'] <= data['suma_asegurada']\n"
    "        and (data['tipo_siniestro'] not in ('robo', 'hurto') or data['denuncia_policial'])\n"
    "        and (not data['otro_reclamo_abierto'] or data['poliza'] == 'premium')\n"
    "    )\n",
    [
        ("V1-APROBADO", env(horas_hasta_denuncia=72, cuotas_al_dia=True, monto_reclamado=500000, suma_asegurada=500000, tipo_siniestro="choque", denuncia_policial=False, otro_reclamo_abierto=False, poliza="basica")),
        ("V2-73-HORAS", env(horas_hasta_denuncia=73, cuotas_al_dia=True, monto_reclamado=100000, suma_asegurada=500000, tipo_siniestro="choque", denuncia_policial=False, otro_reclamo_abierto=False, poliza="basica")),
        ("V3-CUOTAS-ATRASADAS", env(horas_hasta_denuncia=10, cuotas_al_dia=False, monto_reclamado=100000, suma_asegurada=500000, tipo_siniestro="choque", denuncia_policial=False, otro_reclamo_abierto=False, poliza="basica")),
        ("V4-MONTO-EXCEDE", env(horas_hasta_denuncia=10, cuotas_al_dia=True, monto_reclamado=500001, suma_asegurada=500000, tipo_siniestro="choque", denuncia_policial=False, otro_reclamo_abierto=False, poliza="basica")),
        ("V5-HURTO-SIN-DENUNCIA", env(horas_hasta_denuncia=10, cuotas_al_dia=True, monto_reclamado=100000, suma_asegurada=500000, tipo_siniestro="hurto", denuncia_policial=False, otro_reclamo_abierto=False, poliza="basica")),
        ("V6-ROBO-CON-DENUNCIA", env(horas_hasta_denuncia=10, cuotas_al_dia=True, monto_reclamado=100000, suma_asegurada=500000, tipo_siniestro="robo", denuncia_policial=True, otro_reclamo_abierto=False, poliza="basica")),
        ("V7-OTRO-ABIERTO", env(horas_hasta_denuncia=10, cuotas_al_dia=True, monto_reclamado=100000, suma_asegurada=500000, tipo_siniestro="granizo", denuncia_policial=False, otro_reclamo_abierto=True, poliza="intermedia")),
        ("V8-OTRO-ABIERTO-PREMIUM", env(horas_hasta_denuncia=10, cuotas_al_dia=True, monto_reclamado=100000, suma_asegurada=500000, tipo_siniestro="granizo", denuncia_policial=False, otro_reclamo_abierto=True, poliza="premium")),
        ("V9-CHOQUE-RAPIDO", env(horas_hasta_denuncia=1, cuotas_al_dia=True, monto_reclamado=250000, suma_asegurada=900000, tipo_siniestro="choque", denuncia_policial=True, otro_reclamo_abierto=False, poliza="intermedia")),
        ("V10-GRANIZO-BASICA", env(horas_hasta_denuncia=48, cuotas_al_dia=True, monto_reclamado=80000, suma_asegurada=300000, tipo_siniestro="granizo", denuncia_policial=False, otro_reclamo_abierto=False, poliza="basica")),
    ],
)

EUROPA = ["España", "Italia", "Francia", "Alemania", "Portugal", "Reino Unido"]
LIMITROFES = ["Brasil", "Chile", "Uruguay", "Paraguay", "Bolivia"]
rule(
    1, "zona-asistencia-viaje", "SEG-C1-ZONA-VIAJE",
    "Asignar la zona de un seguro de asistencia al viajero según el país de destino. Los destinos \"Brasil\", "
    "\"Chile\", \"Uruguay\", \"Paraguay\" y \"Bolivia\" son zona \"Limítrofe\". \"Estados Unidos\" y \"Canadá\" son "
    "zona \"Norteamérica\". \"España\", \"Italia\", \"Francia\", \"Alemania\", \"Portugal\" y \"Reino Unido\" son zona "
    "\"Europa\". Cualquier otro país es zona \"Resto del mundo\". La excepción: si el viaje dura más de 90 días, la "
    "zona es \"Larga estadía\", sin importar el destino.",
    {"destino": "String", "dias_viaje": "Int"},
    ite(op(">", var("dias_viaje"), lit(90)), S("Larga estadía"),
        ite(in_(var("destino"), LIMITROFES), S("Limítrofe"),
            ite(in_(var("destino"), ["Estados Unidos", "Canadá"]), S("Norteamérica"),
                ite(in_(var("destino"), EUROPA), S("Europa"), S("Resto del mundo"))))),
    f"LIMITROFES = {tuple(LIMITROFES)!r}\nEUROPA = {tuple(EUROPA)!r}\n\n"
    "def evaluate_rule(data):\n"
    "    destino = data['destino']\n"
    "    if data['dias_viaje'] > 90:\n"
    "        return 'Larga estadía'\n"
    "    if destino in LIMITROFES:\n"
    "        return 'Limítrofe'\n"
    "    if destino in ('Estados Unidos', 'Canadá'):\n"
    "        return 'Norteamérica'\n"
    "    if destino in EUROPA:\n"
    "        return 'Europa'\n"
    "    return 'Resto del mundo'\n",
    [
        ("V1-URUGUAY", env(destino="Uruguay", dias_viaje=7)),
        ("V2-CANADA", env(destino="Canadá", dias_viaje=15)),
        ("V3-PORTUGAL", env(destino="Portugal", dias_viaje=20)),
        ("V4-JAPON", env(destino="Japón", dias_viaje=14)),
        ("V5-90-DIAS", env(destino="Italia", dias_viaje=90)),
        ("V6-91-DIAS", env(destino="Italia", dias_viaje=91)),
        ("V7-MEXICO", env(destino="México", dias_viaje=10)),
        ("V8-BOLIVIA-LARGO", env(destino="Bolivia", dias_viaje=120)),
    ],
)

# ===================================== Categoría 2 =====================================

neto = op("-", var("danio"), var("deducible"))
rule(
    2, "indemnizacion", "SEG-C2-INDEMNIZACION",
    "Calcular la indemnización de un siniestro, en pesos con centavos. Es el daño tasado (con centavos) menos el "
    "deducible de la póliza (en pesos enteros). Si el deducible es igual o mayor que el daño, la indemnización es "
    "0.0. El número de póliza y la fecha del siniestro no intervienen en la cuenta.",
    {"danio": "Decimal", "deducible": "Int"},
    ite(op(">", neto, lit(0)), neto, dec("0")),
    "from decimal import Decimal\n\n"
    "def evaluate_rule(data):\n"
    "    neto = data['danio'] - data['deducible']\n"
    "    return neto if neto > 0 else Decimal('0')\n",
    [
        ("V1-NORMAL", env(danio=450000.5, deducible=150000)),
        ("V2-DEDUCIBLE-MAYOR", env(danio=120000.5, deducible=150000)),
        ("V3-CASI-IGUAL", env(danio=150000.01, deducible=150000)),
        ("V4-SIN-DEDUCIBLE", env(danio=80000.75, deducible=0)),
        ("V5-GRANDE", env(danio=9500000.25, deducible=500000)),
        ("V6-MENOS-DE-UN-PESO", env(danio=149999.99, deducible=150000)),
    ],
)

tasa = ite(op("<", var("edad"), lit(40)), dec("0.0008"), ite(op("<", var("edad"), lit(60)), dec("0.0015"), dec("0.003")))
rule(
    2, "prima-vida", "SEG-C2-PRIMA-VIDA",
    "Calcular la prima mensual de un seguro de vida, en pesos con centavos. Es la suma asegurada (en pesos enteros) "
    "por una tasa según la edad: 0.0008 para menores de 40 años, 0.0015 desde 40 hasta 59 años y 0.003 desde 60 "
    "años. A eso se le suma un recargo fijo de 2500 pesos si la persona fuma. La profesión se evalúa en otra etapa y "
    "no cambia la prima.",
    {"edad": "Int", "fuma": "Bool", "suma_asegurada": "Int"},
    op("+", op("*", var("suma_asegurada"), tasa), ite(var("fuma"), lit(2500), lit(0))),
    "from decimal import Decimal\n\n"
    "def evaluate_rule(data):\n"
    "    edad = data['edad']\n"
    "    tasa = Decimal('0.0008') if edad < 40 else Decimal('0.0015') if edad < 60 else Decimal('0.003')\n"
    "    recargo = 2500 if data['fuma'] else 0\n"
    "    return data['suma_asegurada'] * tasa + recargo\n",
    [
        ("V1-JOVEN", env(edad=30, fuma=False, suma_asegurada=10000000)),
        ("V2-40-ANIOS", env(edad=40, fuma=False, suma_asegurada=10000000)),
        ("V3-59-FUMA", env(edad=59, fuma=True, suma_asegurada=10000000)),
        ("V4-60-ANIOS", env(edad=60, fuma=False, suma_asegurada=10000000)),
        ("V5-39-FUMA", env(edad=39, fuma=True, suma_asegurada=5000000)),
        ("V6-SUMA-IMPAR", env(edad=45, fuma=False, suma_asegurada=3333333)),
    ],
)

pct = ite(op(">", var("anios_sin_siniestros"), lit(6)), dec("0.30"), op("*", var("anios_sin_siniestros"), dec("0.05")))
rule(
    2, "bonificacion-sin-siniestros", "SEG-C2-BONUS",
    "Calcular la prima a pagar con la bonificación por años sin siniestros, en pesos con centavos. Cada año "
    "completo sin siniestros bonifica el 5 % de la prima base (con centavos), con un máximo de 30 % (6 años o más "
    "dan 30 %). La prima a pagar es la prima base menos la bonificación. Los años se informan como entero; la "
    "categoría del vehículo no cambia el porcentaje.",
    {"anios_sin_siniestros": "Int", "prima_base": "Decimal"},
    op("-", var("prima_base"), op("*", var("prima_base"), pct)),
    "from decimal import Decimal\n\n"
    "def evaluate_rule(data):\n"
    "    porcentaje = min(data['anios_sin_siniestros'], 6) * Decimal('0.05')\n"
    "    return data['prima_base'] - data['prima_base'] * porcentaje\n",
    [
        ("V1-SIN-BONUS", env(prima_base=45000.5, anios_sin_siniestros=0)),
        ("V2-UN-ANIO", env(prima_base=45000.5, anios_sin_siniestros=1)),
        ("V3-SEIS-ANIOS", env(prima_base=45000.5, anios_sin_siniestros=6)),
        ("V4-DIEZ-ANIOS", env(prima_base=45000.5, anios_sin_siniestros=10)),
        ("V5-TRES-ANIOS", env(prima_base=80000.25, anios_sin_siniestros=3)),
        ("V6-SIETE-ANIOS", env(prima_base=12000.75, anios_sin_siniestros=7)),
    ],
)

cubierto = op("*", var("gasto"), dec("0.8"))
rule(
    2, "reintegro-viaje", "SEG-C2-REINTEGRO-VIAJE",
    "Calcular el reintegro de gastos médicos de un seguro de viaje, en dólares con centavos. Se reintegra el 80 % "
    "del gasto médico (con centavos), sin superar el tope de la póliza (en dólares enteros). Si el 80 % supera el "
    "tope, se reintegra el tope, expresado con centavos (por ejemplo, 30000.00). La moneda del país visitado ya fue "
    "convertida a dólares.",
    {"gasto": "Decimal", "tope": "Int"},
    ite(op(">", cubierto, var("tope")), op("*", var("tope"), dec("1.00")), cubierto),
    "from decimal import Decimal\n\n"
    "def evaluate_rule(data):\n"
    "    return min(data['gasto'] * Decimal('0.8'), data['tope'] * Decimal('1.00'))\n",
    [
        ("V1-DEBAJO", env(gasto=1500.5, tope=30000)),
        ("V2-TOPE", env(gasto=40000.5, tope=30000)),
        ("V3-JUSTO-EN-EL-TOPE", env(gasto=37500.5, tope=30000)),
        ("V4-CHICO", env(gasto=99.99, tope=10000)),
        ("V5-TOPE-CHICO", env(gasto=15000.25, tope=10000)),
        ("V6-JUSTO-DEBAJO", env(gasto=12499.99, tope=10000)),
    ],
)

rule(
    2, "recargo-edad", "SEG-C2-RECARGO",
    "Calcular la prima mensual de un seguro de auto con el recargo por la franja de edad del conductor, en pesos "
    "con centavos. La franja viene como texto: \"joven\", \"adulto\" o \"mayor\". La prima base (con centavos) se "
    "multiplica por 1.35 para joven, por 1.00 para adulto y por 1.15 para mayor. El puntaje de manejo del conductor "
    "no se usa en este cálculo.",
    {"franja": "String", "prima_base": "Decimal"},
    op("*", var("prima_base"), ite(eq("franja", "joven"), dec("1.35"), ite(eq("franja", "mayor"), dec("1.15"), dec("1.00")))),
    "from decimal import Decimal\n\n"
    "FACTOR = {'joven': Decimal('1.35'), 'mayor': Decimal('1.15')}\n\n"
    "def evaluate_rule(data):\n"
    "    return data['prima_base'] * FACTOR.get(data['franja'], Decimal('1.00'))\n",
    [
        ("V1-JOVEN", env(franja="joven", prima_base=40000.5)),
        ("V2-ADULTO", env(franja="adulto", prima_base=40000.5)),
        ("V3-MAYOR", env(franja="mayor", prima_base=40000.5)),
        ("V4-JOVEN-CENTAVOS", env(franja="joven", prima_base=12345.67)),
        ("V5-MAYOR-CENTAVOS", env(franja="mayor", prima_base=99999.99)),
        ("V6-ADULTO-CHICA", env(franja="adulto", prima_base=0.5)),
    ],
)

rule(
    2, "prorrateo-cancelacion", "SEG-C2-PRORRATEO",
    "Calcular cuánto se le devuelve a un asegurado que cancela una póliza anual antes de tiempo, en pesos. Se "
    "devuelve la parte de la prima anual (con centavos) que corresponde a los días que faltaban: prima anual por "
    "días restantes / 365. El resultado es exacto, sin redondear. El motivo de la cancelación no cambia la cuenta.",
    {"dias_restantes": "Int", "prima_anual": "Decimal"},
    op("/", op("*", var("prima_anual"), var("dias_restantes")), lit(365)),
    "def evaluate_rule(data):\n"
    "    return data['prima_anual'] * data['dias_restantes'] / 365\n",
    [
        ("V1-MEDIO-ANIO", env(prima_anual=365000.5, dias_restantes=182)),
        ("V2-TODO-EL-ANIO", env(prima_anual=120000.5, dias_restantes=365)),
        ("V3-SIN-DIAS", env(prima_anual=120000.5, dias_restantes=0)),
        ("V4-UN-DIA", env(prima_anual=73000.5, dias_restantes=1)),
        ("V5-TREINTA", env(prima_anual=250000.75, dias_restantes=30)),
        ("V6-EXACTO", env(prima_anual=36500.5, dias_restantes=100)),
    ],
)

# ===================================== Categoría 3 =====================================

rule(
    3, "carencia", "SEG-C3-CARENCIA",
    "Determinar si una prestación médica está cubierta según el período de carencia. Está cubierta si pasaron al "
    "menos 30 días desde el alta en la póliza. Para las internaciones programadas, la carencia es de 180 días. Las "
    "urgencias están cubiertas desde el primer día, sin carencia. El tipo de prestación viene como \"consulta\", "
    "\"internacion_programada\" o \"urgencia\".",
    {"dias_desde_alta": "Int", "prestacion": "String"},
    op("OR", eq("prestacion", "urgencia"),
       op(">=", var("dias_desde_alta"), ite(eq("prestacion", "internacion_programada"), lit(180), lit(30)))),
    "def evaluate_rule(data):\n"
    "    if data['prestacion'] == 'urgencia':\n"
    "        return True\n"
    "    minimo = 180 if data['prestacion'] == 'internacion_programada' else 30\n"
    "    return data['dias_desde_alta'] >= minimo\n",
    [
        ("V1-CONSULTA-30", env(prestacion="consulta", dias_desde_alta=30)),
        ("V2-CONSULTA-29", env(prestacion="consulta", dias_desde_alta=29)),
        ("V3-URGENCIA-DIA-0", env(prestacion="urgencia", dias_desde_alta=0)),
        ("V4-INTERNACION-179", env(prestacion="internacion_programada", dias_desde_alta=179)),
        ("V5-INTERNACION-180", env(prestacion="internacion_programada", dias_desde_alta=180)),
        ("V6-INTERNACION-60", env(prestacion="internacion_programada", dias_desde_alta=60)),
        ("V7-CONSULTA-LARGA", env(prestacion="consulta", dias_desde_alta=400)),
        ("V8-CONSULTA-DIA-1", env(prestacion="consulta", dias_desde_alta=1)),
    ],
)

rule(
    3, "exclusion-conductor", "SEG-C3-EXCLUSION",
    "Determinar si un choque queda cubierto por la póliza. Queda cubierto, salvo que el conductor manejara con "
    "alcohol en sangre por encima de 0.5 g/L o sin licencia vigente. Con exactamente 0.5 g/L no se aplica la "
    "exclusión. El nivel de alcohol se informa con dos decimales.",
    {"alcohol": "Decimal", "licencia_vigente": "Bool"},
    not_(op("OR", op(">", var("alcohol"), dec("0.5")), not_(var("licencia_vigente")))),
    "from decimal import Decimal\n\n"
    "def evaluate_rule(data):\n"
    "    return not (data['alcohol'] > Decimal('0.5') or not data['licencia_vigente'])\n",
    [
        ("V1-SOBRIO", env(alcohol=0.01, licencia_vigente=True)),
        ("V2-EXACTO-0-5", env(alcohol=0.5, licencia_vigente=True)),
        ("V3-0-51", env(alcohol=0.51, licencia_vigente=True)),
        ("V4-SIN-LICENCIA", env(alcohol=0.01, licencia_vigente=False)),
        ("V5-TODO-MAL", env(alcohol=1.25, licencia_vigente=False)),
        ("V6-0-49", env(alcohol=0.49, licencia_vigente=True)),
    ],
)

rule(
    3, "denuncia-en-plazo", "SEG-C3-PLAZO",
    "Determinar si un siniestro se denunció en plazo. El plazo es de 72 horas desde el siniestro: una denuncia a "
    "las 72 horas todavía está en plazo. Si el asegurado estuvo internado por el mismo siniestro, el plazo se "
    "extiende a 240 horas.",
    {"horas": "Int", "internado": "Bool"},
    op("<=", var("horas"), ite(var("internado"), lit(240), lit(72))),
    "def evaluate_rule(data):\n"
    "    return data['horas'] <= (240 if data['internado'] else 72)\n",
    [
        ("V1-72", env(horas=72, internado=False)),
        ("V2-73", env(horas=73, internado=False)),
        ("V3-INTERNADO-240", env(horas=240, internado=True)),
        ("V4-INTERNADO-241", env(horas=241, internado=True)),
        ("V5-INTERNADO-100", env(horas=100, internado=True)),
        ("V6-500", env(horas=500, internado=False)),
    ],
)

rule(
    3, "renovacion-automatica", "SEG-C3-RENOVACION",
    "Determinar si una póliza se renueva automáticamente. Se renueva si en el año no hubo siniestros graves y, "
    "además, el asegurado pagó todas las cuotas a término o tiene el débito automático activo. Un siniestro grave "
    "impide la renovación automática aunque pague a término.",
    {"debito_automatico": "Bool", "pago_a_termino": "Bool", "siniestro_grave": "Bool"},
    op("AND", not_(var("siniestro_grave")), op("OR", var("pago_a_termino"), var("debito_automatico"))),
    "def evaluate_rule(data):\n"
    "    return not data['siniestro_grave'] and (data['pago_a_termino'] or data['debito_automatico'])\n",
    [
        ("V1-A-TERMINO", env(siniestro_grave=False, pago_a_termino=True, debito_automatico=False)),
        ("V2-DEBITO", env(siniestro_grave=False, pago_a_termino=False, debito_automatico=True)),
        ("V3-NINGUNO", env(siniestro_grave=False, pago_a_termino=False, debito_automatico=False)),
        ("V4-GRAVE", env(siniestro_grave=True, pago_a_termino=True, debito_automatico=True)),
        ("V5-GRAVE-CON-DEBITO", env(siniestro_grave=True, pago_a_termino=False, debito_automatico=True)),
        ("V6-AMBOS", env(siniestro_grave=False, pago_a_termino=True, debito_automatico=True)),
    ],
)

rule(
    3, "franquicia", "SEG-C3-FRANQUICIA",
    "Calcular cuánto paga la aseguradora por un daño con franquicia simple, en pesos enteros. Si el daño supera la "
    "franquicia, la aseguradora paga el daño completo; si el daño es igual o menor que la franquicia, no paga nada "
    "(0). A diferencia de un deducible, la franquicia no se descuenta del pago.",
    {"danio": "Int", "franquicia": "Int"},
    ite(op(">", var("danio"), var("franquicia")), var("danio"), lit(0)),
    "def evaluate_rule(data):\n"
    "    return data['danio'] if data['danio'] > data['franquicia'] else 0\n",
    [
        ("V1-SUPERA", env(danio=300000, franquicia=100000)),
        ("V2-IGUAL", env(danio=100000, franquicia=100000)),
        ("V3-UN-PESO-MAS", env(danio=100001, franquicia=100000)),
        ("V4-MENOR", env(danio=50000, franquicia=100000)),
        ("V5-SIN-FRANQUICIA", env(danio=7000, franquicia=0)),
        ("V6-GRANDE", env(danio=5000000, franquicia=250000)),
    ],
)

rule(
    3, "conductor-novel", "SEG-C3-NOVEL",
    "Determinar si un conductor está cubierto por la póliza familiar. Lo está si tiene 18 años o más y, además, "
    "tiene licencia hace más de 1 año o maneja acompañado por un titular de la póliza. Un conductor de 17 años no "
    "está cubierto, aunque maneje acompañado.",
    {"acompanado": "Bool", "anios_licencia": "Int", "edad": "Int"},
    op("AND", op(">=", var("edad"), lit(18)), op("OR", op(">", var("anios_licencia"), lit(1)), var("acompanado"))),
    "def evaluate_rule(data):\n"
    "    return data['edad'] >= 18 and (data['anios_licencia'] > 1 or data['acompanado'])\n",
    [
        ("V1-EXPERIMENTADO", env(edad=30, anios_licencia=10, acompanado=False)),
        ("V2-LICENCIA-1-SOLO", env(edad=19, anios_licencia=1, acompanado=False)),
        ("V3-LICENCIA-1-ACOMPANADO", env(edad=19, anios_licencia=1, acompanado=True)),
        ("V4-17-ACOMPANADO", env(edad=17, anios_licencia=0, acompanado=True)),
        ("V5-LICENCIA-2", env(edad=20, anios_licencia=2, acompanado=False)),
        ("V6-NUEVO-SOLO", env(edad=18, anios_licencia=0, acompanado=False)),
    ],
)
print("ok")
