"""Tandas del dominio laboral: 6 reglas por categoría, propias. Ver corpus/README.md.

Inspiradas en reglas habituales de recursos humanos (vacaciones, horas extra,
aguinaldo, preaviso), con parámetros simplificados: no son asesoramiento legal.
Montos en pesos.

    docker compose run --rm pipeline python /workspace/corpus/tools/laboral.py /workspace/corpus
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from dsl import ORIGINAL, all_, any_, dec, eq, in_, ite, lit, not_, op, var, write_rule  # noqa: E402

OUT = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(__file__).parents[1]
S = lit


def rule(category, name, case_id, description, gamma, expr, python, scenarios):
    write_rule(
        OUT, f"laboral-c{category}-{name}", case_id=case_id, category=category, domain="laboral", source=ORIGINAL,
        description=description, gamma=gamma, expr=expr, python=python, scenarios=scenarios,
        generator="corpus/tools/laboral.py",
    )


def env(**kw):
    return kw


# ===================================== Categoría 1 =====================================

rule(
    1, "dias-vacaciones", "LAB-C1-VACACIONES",
    "Calcular los días de vacaciones anuales de un empleado. Si en el año trabajó menos de 6 meses, le corresponde "
    "1 día por cada mes trabajado. Si trabajó 6 meses o más, depende de su antigüedad en años completos: con menos "
    "de 5 años le corresponden 14 días; desde 5 y hasta menos de 10 años, 21 días; desde 10 y hasta menos de 20 "
    "años, 28 días; y con 20 años o más, 35 días. Los meses trabajados en el año y la antigüedad se informan como "
    "enteros; el puesto del empleado no cambia la cantidad de días.",
    {"antiguedad_anios": "Int", "meses_trabajados": "Int"},
    ite(op("<", var("meses_trabajados"), lit(6)), var("meses_trabajados"),
        ite(op("<", var("antiguedad_anios"), lit(5)), lit(14),
            ite(op("<", var("antiguedad_anios"), lit(10)), lit(21),
                ite(op("<", var("antiguedad_anios"), lit(20)), lit(28), lit(35))))),
    "def evaluate_rule(data):\n"
    "    if data['meses_trabajados'] < 6:\n"
    "        return data['meses_trabajados']\n"
    "    anios = data['antiguedad_anios']\n"
    "    if anios < 5:\n"
    "        return 14\n"
    "    if anios < 10:\n"
    "        return 21\n"
    "    if anios < 20:\n"
    "        return 28\n"
    "    return 35\n",
    [
        ("V1-NUEVO-COMPLETO", env(antiguedad_anios=0, meses_trabajados=12)),
        ("V2-CINCO-ANIOS", env(antiguedad_anios=5, meses_trabajados=12)),
        ("V3-NUEVE-ANIOS", env(antiguedad_anios=9, meses_trabajados=12)),
        ("V4-DIEZ-ANIOS", env(antiguedad_anios=10, meses_trabajados=12)),
        ("V5-VEINTE-ANIOS", env(antiguedad_anios=20, meses_trabajados=12)),
        ("V6-CINCO-MESES", env(antiguedad_anios=0, meses_trabajados=5)),
        ("V7-DOS-MESES-ANTIGUO", env(antiguedad_anios=12, meses_trabajados=2)),
        ("V8-SEIS-MESES", env(antiguedad_anios=0, meses_trabajados=6)),
        ("V9-DIECINUEVE-ANIOS", env(antiguedad_anios=19, meses_trabajados=11)),
    ],
)

rule(
    1, "bono-anual", "LAB-C1-BONO",
    "Determinar si un empleado cobra el bono anual. Lo cobra solo si se cumplen todas estas condiciones: trabajó al "
    "menos 9 meses del año; su evaluación de desempeño fue \"supera\" o \"cumple\" (las otras posibles son "
    "\"parcial\" y \"no_cumple\"); tuvo 5 ausencias injustificadas o menos; no tiene sanciones disciplinarias en el "
    "año; su área cumplió al menos el 80 % del objetivo (se informa como entero de 0 a 150); y sigue en la empresa al "
    "momento del pago, salvo que se haya jubilado durante el año, en cuyo caso lo cobra igual.",
    {"ausencias_injustificadas": "Int", "cumplimiento_area": "Int", "evaluacion": "String", "jubilado_en_el_anio": "Bool",
     "meses_trabajados": "Int", "sanciones": "Bool", "sigue_en_la_empresa": "Bool"},
    all_(op(">=", var("meses_trabajados"), lit(9)), in_(var("evaluacion"), ["supera", "cumple"]),
         op("<=", var("ausencias_injustificadas"), lit(5)), not_(var("sanciones")),
         op(">=", var("cumplimiento_area"), lit(80)),
         op("OR", var("sigue_en_la_empresa"), var("jubilado_en_el_anio"))),
    "def evaluate_rule(data):\n"
    "    return (\n"
    "        data['meses_trabajados'] >= 9\n"
    "        and data['evaluacion'] in ('supera', 'cumple')\n"
    "        and data['ausencias_injustificadas'] <= 5\n"
    "        and not data['sanciones']\n"
    "        and data['cumplimiento_area'] >= 80\n"
    "        and (data['sigue_en_la_empresa'] or data['jubilado_en_el_anio'])\n"
    "    )\n",
    [
        ("V1-COBRA", env(meses_trabajados=12, evaluacion="cumple", ausencias_injustificadas=0, sanciones=False, cumplimiento_area=100, sigue_en_la_empresa=True, jubilado_en_el_anio=False)),
        ("V2-OCHO-MESES", env(meses_trabajados=8, evaluacion="supera", ausencias_injustificadas=0, sanciones=False, cumplimiento_area=100, sigue_en_la_empresa=True, jubilado_en_el_anio=False)),
        ("V3-PARCIAL", env(meses_trabajados=12, evaluacion="parcial", ausencias_injustificadas=0, sanciones=False, cumplimiento_area=100, sigue_en_la_empresa=True, jubilado_en_el_anio=False)),
        ("V4-SEIS-AUSENCIAS", env(meses_trabajados=12, evaluacion="cumple", ausencias_injustificadas=6, sanciones=False, cumplimiento_area=100, sigue_en_la_empresa=True, jubilado_en_el_anio=False)),
        ("V5-SANCION", env(meses_trabajados=12, evaluacion="cumple", ausencias_injustificadas=0, sanciones=True, cumplimiento_area=100, sigue_en_la_empresa=True, jubilado_en_el_anio=False)),
        ("V6-AREA-79", env(meses_trabajados=12, evaluacion="cumple", ausencias_injustificadas=0, sanciones=False, cumplimiento_area=79, sigue_en_la_empresa=True, jubilado_en_el_anio=False)),
        ("V7-RENUNCIO", env(meses_trabajados=12, evaluacion="cumple", ausencias_injustificadas=0, sanciones=False, cumplimiento_area=100, sigue_en_la_empresa=False, jubilado_en_el_anio=False)),
        ("V8-JUBILADO", env(meses_trabajados=10, evaluacion="supera", ausencias_injustificadas=1, sanciones=False, cumplimiento_area=90, sigue_en_la_empresa=False, jubilado_en_el_anio=True)),
        ("V9-LIMITES", env(meses_trabajados=9, evaluacion="supera", ausencias_injustificadas=5, sanciones=False, cumplimiento_area=80, sigue_en_la_empresa=True, jubilado_en_el_anio=False)),
        ("V10-ESTRELLA", env(meses_trabajados=12, evaluacion="supera", ausencias_injustificadas=0, sanciones=False, cumplimiento_area=135, sigue_en_la_empresa=True, jubilado_en_el_anio=False)),
        ("V11-BUENO", env(meses_trabajados=11, evaluacion="cumple", ausencias_injustificadas=2, sanciones=False, cumplimiento_area=95, sigue_en_la_empresa=True, jubilado_en_el_anio=False)),
        ("V12-NO-CUMPLE", env(meses_trabajados=12, evaluacion="no_cumple", ausencias_injustificadas=0, sanciones=False, cumplimiento_area=120, sigue_en_la_empresa=True, jubilado_en_el_anio=False)),
        ("V13-TRES-AUSENCIAS", env(meses_trabajados=12, evaluacion="supera", ausencias_injustificadas=3, sanciones=False, cumplimiento_area=81, sigue_en_la_empresa=True, jubilado_en_el_anio=False)),
    ],
)

TECNICOS = ["desarrollador", "analista", "tester", "administrador_sistemas"]
GESTION = ["lider_tecnico", "gerente", "jefe_de_area"]
rule(
    1, "categoria-salarial", "LAB-C1-CATEGORIA",
    "Asignar la categoría salarial de un empleado según su puesto y sus años de experiencia. Los puestos "
    "\"lider_tecnico\", \"gerente\" y \"jefe_de_area\" son de gestión: con 8 años de experiencia o más la categoría "
    "es \"G2\", y con menos, \"G1\". Los puestos \"desarrollador\", \"analista\", \"tester\" y "
    "\"administrador_sistemas\" son técnicos: con menos de 2 años la categoría es \"T1\"; desde 2 y hasta menos de 5, "
    "\"T2\"; y con 5 o más, \"T3\". Cualquier otro puesto, como \"recepcionista\" o \"cadete\", es categoría \"A1\", "
    "sin importar la experiencia.",
    {"experiencia_anios": "Int", "puesto": "String"},
    ite(in_(var("puesto"), GESTION), ite(op(">=", var("experiencia_anios"), lit(8)), S("G2"), S("G1")),
        ite(in_(var("puesto"), TECNICOS),
            ite(op("<", var("experiencia_anios"), lit(2)), S("T1"), ite(op("<", var("experiencia_anios"), lit(5)), S("T2"), S("T3"))),
            S("A1"))),
    f"GESTION = {tuple(GESTION)!r}\nTECNICOS = {tuple(TECNICOS)!r}\n\n"
    "def evaluate_rule(data):\n"
    "    puesto, anios = data['puesto'], data['experiencia_anios']\n"
    "    if puesto in GESTION:\n"
    "        return 'G2' if anios >= 8 else 'G1'\n"
    "    if puesto in TECNICOS:\n"
    "        if anios < 2:\n"
    "            return 'T1'\n"
    "        return 'T2' if anios < 5 else 'T3'\n"
    "    return 'A1'\n",
    [
        ("V1-GERENTE-8", env(puesto="gerente", experiencia_anios=8)),
        ("V2-LIDER-7", env(puesto="lider_tecnico", experiencia_anios=7)),
        ("V3-DEV-1", env(puesto="desarrollador", experiencia_anios=1)),
        ("V4-TESTER-2", env(puesto="tester", experiencia_anios=2)),
        ("V5-ANALISTA-5", env(puesto="analista", experiencia_anios=5)),
        ("V6-CADETE-20", env(puesto="cadete", experiencia_anios=20)),
        ("V7-SYSADMIN-4", env(puesto="administrador_sistemas", experiencia_anios=4)),
        ("V8-JEFE-15", env(puesto="jefe_de_area", experiencia_anios=15)),
    ],
)

LICENCIAS = {"matrimonio": 10, "nacimiento": 15, "fallecimiento_familiar": 3, "mudanza": 1, "examen": 2}
rule(
    1, "licencia-especial", "LAB-C1-LICENCIA",
    "Determinar si se aprueba una licencia especial pedida por un empleado. El tipo de licencia viene con uno de "
    "estos códigos, cada uno con su máximo de días: \"matrimonio\" 10, \"nacimiento\" 15, "
    "\"fallecimiento_familiar\" 3, \"mudanza\" 1 y \"examen\" 2. Cualquier otro tipo, como \"viaje\", no se aprueba. "
    "Se aprueba si el tipo es uno de esos, los días pedidos no superan su máximo y el empleado presentó la "
    "documentación. La licencia por \"examen\" solo se aprueba, además, si el empleado está inscripto en una carrera.",
    {"dias_pedidos": "Int", "documentacion": "Bool", "inscripto_en_carrera": "Bool", "tipo": "String"},
    all_(in_(var("tipo"), list(LICENCIAS)), var("documentacion"),
         op("<=", var("dias_pedidos"),
            ite(eq("tipo", "matrimonio"), lit(10),
                ite(eq("tipo", "nacimiento"), lit(15),
                    ite(eq("tipo", "fallecimiento_familiar"), lit(3),
                        ite(eq("tipo", "mudanza"), lit(1), lit(2)))))),
         op("OR", op("!=", var("tipo"), lit("examen")), var("inscripto_en_carrera"))),
    f"MAXIMOS = {LICENCIAS!r}\n\n"
    "def evaluate_rule(data):\n"
    "    maximo = MAXIMOS.get(data['tipo'])\n"
    "    if maximo is None or not data['documentacion'] or data['dias_pedidos'] > maximo:\n"
    "        return False\n"
    "    return data['tipo'] != 'examen' or data['inscripto_en_carrera']\n",
    [
        ("V1-MATRIMONIO-10", env(tipo="matrimonio", dias_pedidos=10, documentacion=True, inscripto_en_carrera=False)),
        ("V2-MATRIMONIO-11", env(tipo="matrimonio", dias_pedidos=11, documentacion=True, inscripto_en_carrera=False)),
        ("V3-SIN-DOCUMENTACION", env(tipo="nacimiento", dias_pedidos=5, documentacion=False, inscripto_en_carrera=False)),
        ("V4-VIAJE", env(tipo="viaje", dias_pedidos=1, documentacion=True, inscripto_en_carrera=False)),
        ("V5-EXAMEN-INSCRIPTO", env(tipo="examen", dias_pedidos=2, documentacion=True, inscripto_en_carrera=True)),
        ("V6-EXAMEN-NO-INSCRIPTO", env(tipo="examen", dias_pedidos=1, documentacion=True, inscripto_en_carrera=False)),
        ("V7-MUDANZA-2", env(tipo="mudanza", dias_pedidos=2, documentacion=True, inscripto_en_carrera=False)),
        ("V8-FALLECIMIENTO", env(tipo="fallecimiento_familiar", dias_pedidos=3, documentacion=True, inscripto_en_carrera=False)),
        ("V9-NACIMIENTO-15", env(tipo="nacimiento", dias_pedidos=15, documentacion=True, inscripto_en_carrera=True)),
    ],
)

rule(
    1, "trabajo-remoto", "LAB-C1-REMOTO",
    "Determinar si un empleado puede trabajar de forma remota. Puede, solo si se cumplen todas estas condiciones: "
    "su puesto no es presencial; superó el período de prueba de 3 meses (lleva 3 meses o más en la empresa); tiene "
    "conexión a internet de al menos 50 Mbps; su última evaluación no fue \"no_cumple\"; y pide como máximo 3 días "
    "remotos por semana, salvo que tenga un certificado médico que lo justifique, en cuyo caso puede pedir hasta 5.",
    {"certificado_medico": "Bool", "dias_remotos": "Int", "evaluacion": "String", "meses_en_empresa": "Int",
     "puesto_presencial": "Bool", "velocidad_mbps": "Int"},
    all_(not_(var("puesto_presencial")), op(">=", var("meses_en_empresa"), lit(3)),
         op(">=", var("velocidad_mbps"), lit(50)), op("!=", var("evaluacion"), lit("no_cumple")),
         op("<=", var("dias_remotos"), ite(var("certificado_medico"), lit(5), lit(3)))),
    "def evaluate_rule(data):\n"
    "    maximo = 5 if data['certificado_medico'] else 3\n"
    "    return (\n"
    "        not data['puesto_presencial']\n"
    "        and data['meses_en_empresa'] >= 3\n"
    "        and data['velocidad_mbps'] >= 50\n"
    "        and data['evaluacion'] != 'no_cumple'\n"
    "        and data['dias_remotos'] <= maximo\n"
    "    )\n",
    [
        ("V1-PUEDE", env(puesto_presencial=False, meses_en_empresa=12, velocidad_mbps=100, evaluacion="cumple", dias_remotos=3, certificado_medico=False)),
        ("V2-PRESENCIAL", env(puesto_presencial=True, meses_en_empresa=12, velocidad_mbps=100, evaluacion="cumple", dias_remotos=1, certificado_medico=False)),
        ("V3-DOS-MESES", env(puesto_presencial=False, meses_en_empresa=2, velocidad_mbps=100, evaluacion="cumple", dias_remotos=1, certificado_medico=False)),
        ("V4-49-MBPS", env(puesto_presencial=False, meses_en_empresa=12, velocidad_mbps=49, evaluacion="cumple", dias_remotos=1, certificado_medico=False)),
        ("V5-NO-CUMPLE", env(puesto_presencial=False, meses_en_empresa=12, velocidad_mbps=100, evaluacion="no_cumple", dias_remotos=1, certificado_medico=False)),
        ("V6-CUATRO-DIAS", env(puesto_presencial=False, meses_en_empresa=12, velocidad_mbps=100, evaluacion="supera", dias_remotos=4, certificado_medico=False)),
        ("V7-CUATRO-CON-CERTIFICADO", env(puesto_presencial=False, meses_en_empresa=12, velocidad_mbps=100, evaluacion="parcial", dias_remotos=4, certificado_medico=True)),
        ("V8-LIMITES", env(puesto_presencial=False, meses_en_empresa=3, velocidad_mbps=50, evaluacion="parcial", dias_remotos=2, certificado_medico=False)),
        ("V9-CINCO-CON-CERTIFICADO", env(puesto_presencial=False, meses_en_empresa=30, velocidad_mbps=300, evaluacion="supera", dias_remotos=5, certificado_medico=True)),
        ("V10-UN-DIA", env(puesto_presencial=False, meses_en_empresa=6, velocidad_mbps=75, evaluacion="cumple", dias_remotos=1, certificado_medico=False)),
    ],
)

rule(
    1, "periodo-de-prueba", "LAB-C1-PRUEBA",
    "Determinar el resultado del período de prueba de un empleado nuevo. Si todavía no pasaron 90 días desde el "
    "ingreso, el resultado es \"En curso\". Si ya pasaron, es \"Efectivo\" cuando la evaluación del jefe es 6 o más "
    "(en una escala de 1 a 10) y el empleado tuvo 2 ausencias injustificadas o menos. Si no cumple eso, el resultado "
    "es \"Extender\" cuando la evaluación es 4 o 5 y no hubo ausencias injustificadas, y \"No continúa\" en cualquier "
    "otro caso.",
    {"ausencias_injustificadas": "Int", "dias_desde_ingreso": "Int", "evaluacion": "Int"},
    ite(op("<", var("dias_desde_ingreso"), lit(90)), S("En curso"),
        ite(op("AND", op(">=", var("evaluacion"), lit(6)), op("<=", var("ausencias_injustificadas"), lit(2))), S("Efectivo"),
            ite(op("AND", in_(var("evaluacion"), [4, 5]), op("==", var("ausencias_injustificadas"), lit(0))), S("Extender"),
                S("No continúa")))),
    "def evaluate_rule(data):\n"
    "    evaluacion, ausencias = data['evaluacion'], data['ausencias_injustificadas']\n"
    "    if data['dias_desde_ingreso'] < 90:\n"
    "        return 'En curso'\n"
    "    if evaluacion >= 6 and ausencias <= 2:\n"
    "        return 'Efectivo'\n"
    "    if evaluacion in (4, 5) and ausencias == 0:\n"
    "        return 'Extender'\n"
    "    return 'No continúa'\n",
    [
        ("V1-EN-CURSO", env(dias_desde_ingreso=89, evaluacion=9, ausencias_injustificadas=0)),
        ("V2-EFECTIVO", env(dias_desde_ingreso=90, evaluacion=6, ausencias_injustificadas=2)),
        ("V3-MUCHAS-AUSENCIAS", env(dias_desde_ingreso=120, evaluacion=8, ausencias_injustificadas=3)),
        ("V4-EXTENDER", env(dias_desde_ingreso=95, evaluacion=5, ausencias_injustificadas=0)),
        ("V5-CUATRO-CON-AUSENCIA", env(dias_desde_ingreso=95, evaluacion=4, ausencias_injustificadas=1)),
        ("V6-TRES", env(dias_desde_ingreso=95, evaluacion=3, ausencias_injustificadas=0)),
        ("V7-DIEZ", env(dias_desde_ingreso=200, evaluacion=10, ausencias_injustificadas=0)),
        ("V8-CUATRO", env(dias_desde_ingreso=91, evaluacion=4, ausencias_injustificadas=0)),
    ],
)

# ===================================== Categoría 2 =====================================

recargo = ite(eq("tipo_dia", "habil"), dec("1.5"), dec("2.0"))
rule(
    2, "horas-extra", "LAB-C2-HORAS-EXTRA",
    "Calcular el pago de horas extra, en pesos con centavos. Es la cantidad de horas extra (entero) por el valor "
    "de la hora normal (con centavos) por un recargo: 1.5 si las horas se hicieron en un día \"habil\" y 2.0 si fue "
    "\"sabado_tarde\", \"domingo\" o \"feriado\". El sueldo básico del convenio ya está reflejado en el valor de la "
    "hora.",
    {"horas": "Int", "tipo_dia": "String", "valor_hora": "Decimal"},
    op("*", op("*", var("horas"), var("valor_hora")), recargo),
    "from decimal import Decimal\n\n"
    "def evaluate_rule(data):\n"
    "    recargo = Decimal('1.5') if data['tipo_dia'] == 'habil' else Decimal('2.0')\n"
    "    return data['horas'] * data['valor_hora'] * recargo\n",
    [
        ("V1-HABIL", env(horas=4, valor_hora=3500.5, tipo_dia="habil")),
        ("V2-FERIADO", env(horas=4, valor_hora=3500.5, tipo_dia="feriado")),
        ("V3-DOMINGO", env(horas=8, valor_hora=2800.75, tipo_dia="domingo")),
        ("V4-SABADO", env(horas=3, valor_hora=4100.25, tipo_dia="sabado_tarde")),
        ("V5-SIN-HORAS", env(horas=0, valor_hora=3500.5, tipo_dia="habil")),
        ("V6-UNA-HORA", env(horas=1, valor_hora=999.99, tipo_dia="habil")),
    ],
)

rule(
    2, "aguinaldo-proporcional", "LAB-C2-AGUINALDO",
    "Calcular el aguinaldo proporcional de un semestre, en pesos. Es la mitad de la mejor remuneración mensual del "
    "semestre (con centavos) multiplicada por los días trabajados en el semestre (entero) y dividida por 180. Si "
    "trabajó los 180 días, cobra la mitad completa. El resultado es exacto, sin redondear. La fecha de ingreso ya "
    "está reflejada en los días trabajados.",
    {"dias_trabajados": "Int", "mejor_remuneracion": "Decimal"},
    op("/", op("*", op("/", var("mejor_remuneracion"), lit(2)), var("dias_trabajados")), lit(180)),
    "def evaluate_rule(data):\n"
    "    return data['mejor_remuneracion'] / 2 * data['dias_trabajados'] / 180\n",
    [
        ("V1-SEMESTRE-COMPLETO", env(mejor_remuneracion=900000.5, dias_trabajados=180)),
        ("V2-MEDIO-SEMESTRE", env(mejor_remuneracion=900000.5, dias_trabajados=90)),
        ("V3-UN-DIA", env(mejor_remuneracion=720000.5, dias_trabajados=1)),
        ("V4-SIN-DIAS", env(mejor_remuneracion=720000.5, dias_trabajados=0)),
        ("V5-45-DIAS", env(mejor_remuneracion=1250000.75, dias_trabajados=45)),
        ("V6-100-DIAS", env(mejor_remuneracion=654321.99, dias_trabajados=100)),
    ],
)

rule(
    2, "presentismo", "LAB-C2-PRESENTISMO",
    "Calcular el adicional por presentismo del mes, en pesos con centavos. Si el empleado no tuvo faltas en el mes, "
    "cobra el 10 % de su sueldo básico (con centavos); con 1 falta justificada, cobra el 5 %; en cualquier otro caso "
    "(una falta injustificada o más de una falta), el adicional es 0.0. Las faltas se informan por separado: "
    "justificadas e injustificadas, como enteros.",
    {"faltas_injustificadas": "Int", "faltas_justificadas": "Int", "sueldo_basico": "Decimal"},
    ite(op("AND", op("==", var("faltas_justificadas"), lit(0)), op("==", var("faltas_injustificadas"), lit(0))),
        op("*", var("sueldo_basico"), dec("0.10")),
        ite(op("AND", op("==", var("faltas_justificadas"), lit(1)), op("==", var("faltas_injustificadas"), lit(0))),
            op("*", var("sueldo_basico"), dec("0.05")),
            dec("0"))),
    "from decimal import Decimal\n\n"
    "def evaluate_rule(data):\n"
    "    justificadas, injustificadas = data['faltas_justificadas'], data['faltas_injustificadas']\n"
    "    if injustificadas == 0 and justificadas == 0:\n"
    "        return data['sueldo_basico'] * Decimal('0.10')\n"
    "    if injustificadas == 0 and justificadas == 1:\n"
    "        return data['sueldo_basico'] * Decimal('0.05')\n"
    "    return Decimal('0')\n",
    [
        ("V1-SIN-FALTAS", env(sueldo_basico=850000.5, faltas_justificadas=0, faltas_injustificadas=0)),
        ("V2-UNA-JUSTIFICADA", env(sueldo_basico=850000.5, faltas_justificadas=1, faltas_injustificadas=0)),
        ("V3-UNA-INJUSTIFICADA", env(sueldo_basico=850000.5, faltas_justificadas=0, faltas_injustificadas=1)),
        ("V4-DOS-JUSTIFICADAS", env(sueldo_basico=850000.5, faltas_justificadas=2, faltas_injustificadas=0)),
        ("V5-AMBAS", env(sueldo_basico=640000.25, faltas_justificadas=1, faltas_injustificadas=1)),
        ("V6-CENTAVOS", env(sueldo_basico=999999.99, faltas_justificadas=0, faltas_injustificadas=0)),
    ],
)

anios = op("+", op("/", op("-", var("meses_trabajados"), op("%", var("meses_trabajados"), lit(12))), lit(12)),
           ite(op(">", op("%", var("meses_trabajados"), lit(12)), lit(3)), lit(1), lit(0)))
rule(
    2, "indemnizacion-antiguedad", "LAB-C2-INDEMNIZACION",
    "Calcular la indemnización por antigüedad, en pesos. Es la mejor remuneración mensual (con centavos) por la "
    "cantidad de años de servicio. Los años de servicio salen de los meses trabajados (entero): cada 12 meses es un "
    "año, y si sobran más de 3 meses, se cuenta un año más (con 15 meses son 1 año, con 16 son 2). Si trabajó menos "
    "de 3 meses, la indemnización es 0.0. El motivo del despido no cambia la cuenta.",
    {"meses_trabajados": "Int", "mejor_remuneracion": "Decimal"},
    ite(op("<", var("meses_trabajados"), lit(3)), dec("0"), op("*", var("mejor_remuneracion"), anios)),
    "from decimal import Decimal\n\n"
    "def evaluate_rule(data):\n"
    "    meses = data['meses_trabajados']\n"
    "    if meses < 3:\n"
    "        return Decimal('0')\n"
    "    anios = meses // 12 + (1 if meses % 12 > 3 else 0)\n"
    "    return data['mejor_remuneracion'] * anios\n",
    [
        ("V1-DOS-MESES", env(meses_trabajados=2, mejor_remuneracion=800000.5)),
        ("V2-TRES-MESES", env(meses_trabajados=3, mejor_remuneracion=800000.5)),
        ("V3-CUATRO-MESES", env(meses_trabajados=4, mejor_remuneracion=800000.5)),
        ("V4-15-MESES", env(meses_trabajados=15, mejor_remuneracion=800000.5)),
        ("V5-16-MESES", env(meses_trabajados=16, mejor_remuneracion=800000.5)),
        ("V6-DIEZ-ANIOS", env(meses_trabajados=120, mejor_remuneracion=1500000.25)),
        ("V7-24-MESES", env(meses_trabajados=24, mejor_remuneracion=950000.75)),
    ],
)

rule(
    2, "aportes", "LAB-C2-APORTES",
    "Calcular el sueldo neto de un empleado, en pesos con centavos. Al sueldo bruto (con centavos) se le descuenta "
    "el 11 % de jubilación, el 3 % de obra social y el 3 % de PAMI, es decir, el 17 % en total. Además, si el "
    "empleado está afiliado al sindicato, se le descuenta un 2 % más del bruto. La obra social elegida por el "
    "empleado no cambia los porcentajes.",
    {"afiliado_sindicato": "Bool", "sueldo_bruto": "Decimal"},
    op("-", var("sueldo_bruto"),
       op("*", var("sueldo_bruto"), ite(var("afiliado_sindicato"), dec("0.19"), dec("0.17")))),
    "from decimal import Decimal\n\n"
    "def evaluate_rule(data):\n"
    "    descuento = Decimal('0.19') if data['afiliado_sindicato'] else Decimal('0.17')\n"
    "    return data['sueldo_bruto'] - data['sueldo_bruto'] * descuento\n",
    [
        ("V1-NO-AFILIADO", env(sueldo_bruto=1000000.5, afiliado_sindicato=False)),
        ("V2-AFILIADO", env(sueldo_bruto=1000000.5, afiliado_sindicato=True)),
        ("V3-CENTAVOS", env(sueldo_bruto=123456.78, afiliado_sindicato=False)),
        ("V4-AFILIADO-CENTAVOS", env(sueldo_bruto=987654.32, afiliado_sindicato=True)),
        ("V5-BAJO", env(sueldo_bruto=300000.25, afiliado_sindicato=False)),
        ("V6-ALTO-AFILIADO", env(sueldo_bruto=4500000.75, afiliado_sindicato=True)),
    ],
)

rule(
    2, "viaticos", "LAB-C2-VIATICOS",
    "Calcular los viáticos de un viaje de trabajo, en pesos con centavos. Se pagan 350.50 pesos por kilómetro "
    "recorrido (entero) más 25000 pesos por cada comida hecha fuera de la ciudad (entero). Si el viaje fue de menos "
    "de 50 kilómetros, no se pagan viáticos y el resultado es 0.0, aunque haya comidas. El vehículo usado no cambia "
    "la tarifa.",
    {"comidas": "Int", "kilometros": "Int"},
    ite(op("<", var("kilometros"), lit(50)), dec("0"),
        op("+", op("*", var("kilometros"), dec("350.50")), op("*", var("comidas"), lit(25000)))),
    "from decimal import Decimal\n\n"
    "def evaluate_rule(data):\n"
    "    if data['kilometros'] < 50:\n"
    "        return Decimal('0')\n"
    "    return data['kilometros'] * Decimal('350.50') + data['comidas'] * 25000\n",
    [
        ("V1-49-KM", env(kilometros=49, comidas=1)),
        ("V2-50-KM", env(kilometros=50, comidas=0)),
        ("V3-CON-COMIDAS", env(kilometros=300, comidas=2)),
        ("V4-LARGO", env(kilometros=1200, comidas=5)),
        ("V5-CORTO-SIN-COMIDAS", env(kilometros=10, comidas=0)),
        ("V6-51-KM", env(kilometros=51, comidas=1)),
    ],
)

# ===================================== Categoría 3 =====================================

rule(
    3, "preaviso", "LAB-C3-PREAVISO",
    "Calcular los días de preaviso que el empleador debe dar al despedir a un empleado. Si el empleado todavía está "
    "en el período de prueba (menos de 3 meses de antigüedad), son 15 días. Si tiene 3 meses o más pero menos de 5 "
    "años, son 30 días. Con 5 años o más, son 60 días. La antigüedad se informa en meses completos.",
    {"antiguedad_meses": "Int"},
    ite(op("<", var("antiguedad_meses"), lit(3)), lit(15), ite(op("<", var("antiguedad_meses"), lit(60)), lit(30), lit(60))),
    "def evaluate_rule(data):\n"
    "    meses = data['antiguedad_meses']\n"
    "    if meses < 3:\n"
    "        return 15\n"
    "    return 30 if meses < 60 else 60\n",
    [
        ("V1-DOS-MESES", env(antiguedad_meses=2)),
        ("V2-TRES-MESES", env(antiguedad_meses=3)),
        ("V3-59-MESES", env(antiguedad_meses=59)),
        ("V4-60-MESES", env(antiguedad_meses=60)),
        ("V5-RECIEN-INGRESADO", env(antiguedad_meses=0)),
        ("V6-VEINTE-ANIOS", env(antiguedad_meses=240)),
    ],
)

rule(
    3, "licencia-matrimonio", "LAB-C3-MATRIMONIO",
    "Determinar si un empleado tiene derecho a la licencia paga por matrimonio. Tiene derecho si lleva al menos 6 "
    "meses en la empresa, salvo que ya haya usado esta licencia en la misma empresa en los últimos 5 años. Un "
    "empleado que nunca la usó se informa con 99 años desde el último uso.",
    {"anios_desde_ultimo_uso": "Int", "meses_en_empresa": "Int"},
    op("AND", op(">=", var("meses_en_empresa"), lit(6)), not_(op("<", var("anios_desde_ultimo_uso"), lit(5)))),
    "def evaluate_rule(data):\n"
    "    return data['meses_en_empresa'] >= 6 and not data['anios_desde_ultimo_uso'] < 5\n",
    [
        ("V1-SEIS-MESES", env(meses_en_empresa=6, anios_desde_ultimo_uso=99)),
        ("V2-CINCO-MESES", env(meses_en_empresa=5, anios_desde_ultimo_uso=99)),
        ("V3-USO-HACE-4", env(meses_en_empresa=100, anios_desde_ultimo_uso=4)),
        ("V4-USO-HACE-5", env(meses_en_empresa=100, anios_desde_ultimo_uso=5)),
        ("V5-ANTIGUO-NUNCA", env(meses_en_empresa=48, anios_desde_ultimo_uso=99)),
        ("V6-NUEVO-Y-RECIENTE", env(meses_en_empresa=2, anios_desde_ultimo_uso=1)),
    ],
)

rule(
    3, "jornada-nocturna", "LAB-C3-NOCTURNA",
    "Determinar si una hora de trabajo es nocturna. La hora se informa como la hora de inicio, de 0 a 23: la hora "
    "que empieza a las 21 es nocturna, y la que empieza a las 6 ya no. Es nocturna toda hora que empiece desde las "
    "21 inclusive hasta las 23, o desde las 0 hasta antes de las 6.",
    {"hora_inicio": "Int"},
    op("OR", op(">=", var("hora_inicio"), lit(21)), op("<", var("hora_inicio"), lit(6))),
    "def evaluate_rule(data):\n"
    "    return data['hora_inicio'] >= 21 or data['hora_inicio'] < 6\n",
    [
        ("V1-21", env(hora_inicio=21)),
        ("V2-20", env(hora_inicio=20)),
        ("V3-5", env(hora_inicio=5)),
        ("V4-6", env(hora_inicio=6)),
        ("V5-MEDIANOCHE", env(hora_inicio=0)),
        ("V6-MEDIODIA", env(hora_inicio=12)),
        ("V7-23", env(hora_inicio=23)),
        ("V8-7", env(hora_inicio=7)),
    ],
)

rule(
    3, "tardanza", "LAB-C3-TARDANZA",
    "Determinar si un fichaje de entrada cuenta como tardanza. Cuenta como tardanza si el empleado ingresó más de 10 "
    "minutos después de su horario: con 10 minutos de demora todavía no es tardanza. La excepción: si tiene un "
    "permiso de ingreso tardío aprobado para ese día, nunca es tardanza. La demora se informa en minutos (negativa "
    "si llegó antes).",
    {"minutos_demora": "Int", "permiso_aprobado": "Bool"},
    op("AND", op(">", var("minutos_demora"), lit(10)), not_(var("permiso_aprobado"))),
    "def evaluate_rule(data):\n"
    "    return data['minutos_demora'] > 10 and not data['permiso_aprobado']\n",
    [
        ("V1-10-MINUTOS", env(minutos_demora=10, permiso_aprobado=False)),
        ("V2-11-MINUTOS", env(minutos_demora=11, permiso_aprobado=False)),
        ("V3-CON-PERMISO", env(minutos_demora=60, permiso_aprobado=True)),
        ("V4-TEMPRANO", env(minutos_demora=-5, permiso_aprobado=False)),
        ("V5-UNA-HORA", env(minutos_demora=60, permiso_aprobado=False)),
        ("V6-VEINTE", env(minutos_demora=20, permiso_aprobado=False)),
    ],
)

rule(
    3, "elegible-teletrabajo", "LAB-C3-TELETRABAJO",
    "Determinar si un área puede pasar a teletrabajo total. Puede si al menos el 70 % de sus puestos pueden hacerse "
    "de forma remota (se informa como entero de 0 a 100), salvo que el área atienda público o maneje documentación "
    "en papel: en esos casos no puede, aunque supere ese porcentaje.",
    {"atiende_publico": "Bool", "documentacion_papel": "Bool", "porcentaje_remoto": "Int"},
    op("AND", op(">=", var("porcentaje_remoto"), lit(70)),
       not_(op("OR", var("atiende_publico"), var("documentacion_papel")))),
    "def evaluate_rule(data):\n"
    "    return data['porcentaje_remoto'] >= 70 and not (data['atiende_publico'] or data['documentacion_papel'])\n",
    [
        ("V1-70", env(porcentaje_remoto=70, atiende_publico=False, documentacion_papel=False)),
        ("V2-69", env(porcentaje_remoto=69, atiende_publico=False, documentacion_papel=False)),
        ("V3-PUBLICO", env(porcentaje_remoto=100, atiende_publico=True, documentacion_papel=False)),
        ("V4-PAPEL", env(porcentaje_remoto=90, atiende_publico=False, documentacion_papel=True)),
        ("V5-100", env(porcentaje_remoto=100, atiende_publico=False, documentacion_papel=False)),
        ("V6-BAJO-Y-PUBLICO", env(porcentaje_remoto=20, atiende_publico=True, documentacion_papel=True)),
        ("V7-85", env(porcentaje_remoto=85, atiende_publico=False, documentacion_papel=False)),
    ],
)

rule(
    3, "descanso-entre-jornadas", "LAB-C3-DESCANSO",
    "Determinar si se respetó el descanso mínimo entre dos jornadas de trabajo. Se respetó si entre el fin de una "
    "jornada y el inicio de la siguiente pasaron al menos 12 horas. Las horas se informan como enteros: el fin de la "
    "jornada anterior (de 0 a 23) y el inicio de la siguiente (de 0 a 23), que siempre es al día siguiente, así que "
    "el descanso es 24 - fin + inicio.",
    {"fin_jornada": "Int", "inicio_siguiente": "Int"},
    op(">=", op("+", op("-", lit(24), var("fin_jornada")), var("inicio_siguiente")), lit(12)),
    "def evaluate_rule(data):\n"
    "    return 24 - data['fin_jornada'] + data['inicio_siguiente'] >= 12\n",
    [
        ("V1-DOCE-HORAS", env(fin_jornada=20, inicio_siguiente=8)),
        ("V2-ONCE-HORAS", env(fin_jornada=21, inicio_siguiente=8)),
        ("V3-LARGO", env(fin_jornada=17, inicio_siguiente=9)),
        ("V4-CORTO", env(fin_jornada=23, inicio_siguiente=6)),
        ("V5-MADRUGADA", env(fin_jornada=2, inicio_siguiente=0)),
        ("V6-ONCE-EXACTAS", env(fin_jornada=19, inicio_siguiente=6)),
    ],
)
print("ok")
