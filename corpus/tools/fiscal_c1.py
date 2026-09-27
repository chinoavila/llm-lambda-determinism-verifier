"""Tanda 1: fiscal, categoría 1 (IRS-01, 02, 03, 04, 05, 07). Ver docs/corpus-fuentes.md.

    docker compose run --rm pipeline python /workspace/corpus/tools/fiscal_c1.py /workspace/corpus
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from dsl import F6744, adapted, all_, any_, eq, in_, ite, lit, not_, op, var, write_rule  # noqa: E402

OUT = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(__file__).parents[1]


def rule(name, case_id, reference, description, gamma, expr, python, scenarios):
    write_rule(
        OUT, name, case_id=case_id, category=1, domain="fiscal", source=adapted(reference),
        description=description, gamma=gamma, expr=expr, python=python, scenarios=scenarios,
        generator="corpus/tools/fiscal_c1.py",
    )


# --- IRS-01: EITC sin hijo calificable ------------------------------------------------

def eitc(conj, edad, edad_c, ganado, agi, inv, ssn=True, dep=False, dias=365):
    return {
        "declaracion_conjunta": conj, "edad": edad, "edad_conyuge": edad_c,
        "ingreso_ganado": ganado, "agi": agi, "ingreso_inversion": inv,
        "tiene_ssn_valido": ssn, "puede_ser_dependiente": dep, "dias_en_eeuu": dias,
    }


def edad_ok(v):
    return op("AND", op(">=", var(v), lit(25)), op("<", var(v), lit(65)))


tope = ite(var("declaracion_conjunta"), lit(26214), lit(19104))
rule(
    "fiscal-c1-eitc-sin-hijos", "FIS-C1-EITC",
    f"{F6744}, Basic Scenarios 2, 5 y 6 y Advanced Scenario 6; IRS Pub. 596 (2025), Rules 1-15",
    "Determinar si el contribuyente puede pedir en su declaración de 2025 el crédito por ingreso del trabajo "
    "sin hijo calificable. Lo puede pedir solo si se cumplen todas estas condiciones: tiene un número de seguro "
    "social válido; nadie más puede declararlo como dependiente; vivió en los Estados Unidos al menos 183 días "
    "del año; su ingreso de inversión no supera los 11950 dólares; tuvo algún ingreso del trabajo (mayor que "
    "cero); y tanto su ingreso del trabajo como su ingreso bruto ajustado (AGI) son menores que 19104 dólares, "
    "o menores que 26214 dólares si presenta la declaración en forma conjunta con su cónyuge. Además, tiene que "
    "tener al menos 25 años y menos de 65; si presenta en forma conjunta, alcanza con que cumpla esa edad "
    "cualquiera de los dos cónyuges. La edad del cónyuge vale 0 cuando no presenta en forma conjunta.",
    {"agi": "Int", "declaracion_conjunta": "Bool", "dias_en_eeuu": "Int", "edad": "Int",
     "edad_conyuge": "Int", "ingreso_ganado": "Int", "ingreso_inversion": "Int",
     "puede_ser_dependiente": "Bool", "tiene_ssn_valido": "Bool"},
    all_(
        var("tiene_ssn_valido"),
        not_(var("puede_ser_dependiente")),
        op(">=", var("dias_en_eeuu"), lit(183)),
        op("<=", var("ingreso_inversion"), lit(11950)),
        op(">", var("ingreso_ganado"), lit(0)),
        op("<", var("ingreso_ganado"), tope),
        op("<", var("agi"), tope),
        op("OR", edad_ok("edad"), op("AND", var("declaracion_conjunta"), edad_ok("edad_conyuge"))),
    ),
    "def evaluate_rule(data):\n"
    "    tope = 26214 if data['declaracion_conjunta'] else 19104\n"
    "    def edad_ok(e):\n"
    "        return 25 <= e < 65\n"
    "    return (\n"
    "        data['tiene_ssn_valido']\n"
    "        and not data['puede_ser_dependiente']\n"
    "        and data['dias_en_eeuu'] >= 183\n"
    "        and data['ingreso_inversion'] <= 11950\n"
    "        and 0 < data['ingreso_ganado'] < tope\n"
    "        and data['agi'] < tope\n"
    "        and (edad_ok(data['edad']) or (data['declaracion_conjunta'] and edad_ok(data['edad_conyuge'])))\n"
    "    )\n",
    [
        ("F6744-B2-WALSH", eitc(True, 31, 30, 16000, 16300, 300)),
        ("F6744-B5-NEIL", eitc(False, 63, 0, 9250, 9250, 0)),
        ("F6744-B6-SCOTT", eitc(False, 24, 0, 27500, 35500, 0)),
        ("F6744-A6-CARLOS", eitc(False, 28, 0, 18500, 21250, 0)),
        ("V1-EDAD-25", eitc(False, 25, 0, 19103, 19103, 11950)),
        ("V2-EDAD-65", eitc(False, 65, 0, 12000, 12000, 0)),
        ("V3-CONYUGE-RESCATA", eitc(True, 24, 64, 26213, 26213, 0)),
        ("V4-INVERSION", eitc(False, 40, 0, 12000, 12000, 11951)),
        ("V5-DEPENDIENTE", eitc(False, 30, 0, 12000, 12000, 0, dep=True)),
        ("V6-DIAS-183", eitc(False, 30, 0, 12000, 12000, 0, dias=183)),
    ],
)

# --- IRS-02: estado civil más conveniente -----------------------------------------------

def fs(estado, juntos=False, conyuge_6m=False, paga=True, hijo=False, anio=0, persona=False):
    return {
        "estado_civil": estado, "presentan_juntos": juntos, "conyuge_vivio_ultimos_6_meses": conyuge_6m,
        "paga_mas_mitad_hogar": paga, "tiene_hijo_dependiente": hijo, "anio_muerte_conyuge": anio,
        "tiene_persona_calificante": persona or hijo,
    }



S = lambda s: lit(s)  # noqa: E731
rule(
    "fiscal-c1-estado-civil", "FIS-C1-ESTADO-CIVIL",
    f"{F6744}, Basic Scenarios 1, 2 y 5 y Advanced Scenario 1; IRS Pub. 501 (2025), Filing Status",
    "Determinar el estado civil más conveniente que puede usar el contribuyente en su declaración de 2025. "
    "Responder con uno de estos textos exactos: \"Casado conjunta\", \"Casado separado\", \"Viudo calificado\", "
    "\"Jefe de hogar\" o \"Soltero\". El estado civil al 31 de diciembre viene como \"soltero\", \"casado\", "
    "\"divorciado\" o \"viudo\". Si está casado y los dos cónyuges aceptan presentar juntos, corresponde Casado "
    "conjunta. Si está casado pero no presentan juntos, corresponde Jefe de hogar solo cuando el cónyuge no vivió "
    "en la casa durante los últimos 6 meses del año, el contribuyente pagó más de la mitad del costo de mantener "
    "el hogar y tiene un hijo o hijastro dependiente que vivió con él; si no, Casado separado. Si es viudo y el "
    "cónyuge murió en 2025, corresponde Casado conjunta. Si es viudo, el cónyuge murió en 2023 o en 2024, tiene un "
    "hijo o hijastro dependiente y pagó más de la mitad del costo del hogar, corresponde Viudo calificado. En "
    "cualquier otro caso, corresponde Jefe de hogar si pagó más de la mitad del costo del hogar y una persona "
    "calificante vivió con él más de la mitad del año, y Soltero si no. El año de muerte del cónyuge vale 0 "
    "cuando no es viudo.",
    {"anio_muerte_conyuge": "Int", "conyuge_vivio_ultimos_6_meses": "Bool", "estado_civil": "String",
     "paga_mas_mitad_hogar": "Bool", "presentan_juntos": "Bool", "tiene_hijo_dependiente": "Bool",
     "tiene_persona_calificante": "Bool"},
    ite(
        eq("estado_civil", "casado"),
        ite(
            var("presentan_juntos"), S("Casado conjunta"),
            ite(
                all_(not_(var("conyuge_vivio_ultimos_6_meses")), var("paga_mas_mitad_hogar"),
                     var("tiene_hijo_dependiente")),
                S("Jefe de hogar"), S("Casado separado"),
            ),
        ),
        ite(
            op("AND", eq("estado_civil", "viudo"), eq("anio_muerte_conyuge", 2025)),
            S("Casado conjunta"),
            ite(
                all_(eq("estado_civil", "viudo"), in_(var("anio_muerte_conyuge"), [2023, 2024]),
                     var("tiene_hijo_dependiente"), var("paga_mas_mitad_hogar")),
                S("Viudo calificado"),
                ite(op("AND", var("paga_mas_mitad_hogar"), var("tiene_persona_calificante")),
                    S("Jefe de hogar"), S("Soltero")),
            ),
        ),
    ),
    "def evaluate_rule(data):\n"
    "    estado = data['estado_civil']\n"
    "    paga = data['paga_mas_mitad_hogar']\n"
    "    hijo = data['tiene_hijo_dependiente']\n"
    "    if estado == 'casado':\n"
    "        if data['presentan_juntos']:\n"
    "            return 'Casado conjunta'\n"
    "        if not data['conyuge_vivio_ultimos_6_meses'] and paga and hijo:\n"
    "            return 'Jefe de hogar'\n"
    "        return 'Casado separado'\n"
    "    if estado == 'viudo' and data['anio_muerte_conyuge'] == 2025:\n"
    "        return 'Casado conjunta'\n"
    "    if estado == 'viudo' and data['anio_muerte_conyuge'] in (2023, 2024) and hijo and paga:\n"
    "        return 'Viudo calificado'\n"
    "    if paga and data['tiene_persona_calificante']:\n"
    "        return 'Jefe de hogar'\n"
    "    return 'Soltero'\n",
    [
        ("F6744-B1-FRED", fs("soltero", persona=True)),
        ("F6744-B2-WALSH", fs("casado", juntos=True, conyuge_6m=True)),
        ("F6744-A1-JOY", fs("casado", hijo=True)),
        ("F6744-B5-NEIL", fs("soltero")),
        ("V1-CONYUGE-EN-CASA", fs("casado", conyuge_6m=True, hijo=True)),
        ("V2-VIUDO-2024", fs("viudo", hijo=True, anio=2024)),
        ("V3-VIUDO-2022", fs("viudo", hijo=True, anio=2022)),
        ("V4-VIUDO-2025", fs("viudo", anio=2025)),
        ("V5-DIVORCIADO-NO-PAGA", fs("divorciado", paga=False, persona=True)),
        ("V6-VIUDO-2023-SIN-HIJO", fs("viudo", anio=2023)),
    ],
)

# --- IRS-03: residencia fiscal de extranjeros con visa F o J -----------------------------

def res(est, doc, a_est, a_6, d25, d24=0, d23=0):
    return {
        "es_estudiante": est, "es_docente_o_aprendiz": doc, "anios_exento_estudiante": a_est,
        "anios_exento_ultimos_6": a_6, "dias_2025": d25, "dias_2024": d24, "dias_2023": d23,
    }


presencia = op(
    "+", op("+", var("dias_2025"), op("/", var("dias_2024"), lit(3))), op("/", var("dias_2023"), lit(6))
)
rule(
    "fiscal-c1-residencia-fiscal", "FIS-C1-RESIDENCIA",
    f"{F6744}, Foreign Student Test, Residency Status preguntas 1-5; IRS Pub. 519 (2025), chapter 1",
    "Determinar la residencia fiscal en 2025 de un extranjero que está en los Estados Unidos: responder "
    "\"Residente\" o \"No residente\". Primero, la persona está exenta en 2025, y entonces es No residente, si es "
    "estudiante con visa F, J, M o Q y estuvo exenta como estudiante en menos de 5 años calendario anteriores, o "
    "si es docente o aprendiz con visa J o Q y estuvo exenta (como docente, aprendiz o estudiante) en menos de 2 "
    "de los 6 años calendario anteriores. Si no está exenta, es Residente cuando pasa la prueba de presencia "
    "sustancial: estuvo al menos 31 días en el país en 2025 y, además, los días de 2025, más un tercio de los días "
    "de 2024, más un sexto de los días de 2023, suman 183 o más. Los días de cada año ya vienen descontados de los "
    "días en que la persona estaba exenta. Si no pasa la prueba, es No residente.",
    {"anios_exento_estudiante": "Int", "anios_exento_ultimos_6": "Int", "dias_2023": "Int", "dias_2024": "Int",
     "dias_2025": "Int", "es_docente_o_aprendiz": "Bool", "es_estudiante": "Bool"},
    ite(
        any_(
            op("AND", var("es_estudiante"), op("<", var("anios_exento_estudiante"), lit(5))),
            op("AND", var("es_docente_o_aprendiz"), op("<", var("anios_exento_ultimos_6"), lit(2))),
        ),
        S("No residente"),
        ite(
            op("AND", op(">=", var("dias_2025"), lit(31)), op(">=", presencia, lit(183))),
            S("Residente"), S("No residente"),
        ),
    ),
    "from decimal import Decimal\n\n"
    "def evaluate_rule(data):\n"
    "    exento = (data['es_estudiante'] and data['anios_exento_estudiante'] < 5) or (\n"
    "        data['es_docente_o_aprendiz'] and data['anios_exento_ultimos_6'] < 2\n"
    "    )\n"
    "    if exento:\n"
    "        return 'No residente'\n"
    "    dias = Decimal(data['dias_2025']) + Decimal(data['dias_2024']) / 3 + Decimal(data['dias_2023']) / 6\n"
    "    if data['dias_2025'] >= 31 and dias >= 183:\n"
    "        return 'Residente'\n"
    "    return 'No residente'\n",
    [
        ("F6744-E1-MAYLOR", res(True, False, 3, 3, 365)),
        ("F6744-E2-AMELIA", res(False, True, 3, 3, 365, 12)),
        ("F6744-E3-LUCAS", res(False, False, 4, 4, 153)),
        ("F6744-E4-ANTONIO", res(True, False, 4, 4, 365)),
        ("F6744-E5-YVONNE", res(False, True, 0, 2, 212)),
        ("V1-ESTUDIANTE-6TO-ANIO", res(True, False, 5, 5, 365)),
        ("V2-MENOS-DE-31-DIAS", res(True, False, 5, 5, 30)),
        ("V3-PRESENCIA-183", res(False, False, 0, 0, 150, 90, 18)),
        ("V4-PRESENCIA-182", res(False, False, 0, 0, 150, 89, 18)),
        ("V5-DOCENTE-EXENTO", res(False, True, 0, 1, 365, 200)),
    ],
)

# --- IRS-04: crédito educativo aplicable -------------------------------------------------

def edu(tipo, magi, comp4=False, anios=0, titulo=True, medio=True, condena=False):
    return {
        "tipo_declaracion": tipo, "magi": magi, "completo_4_anios": comp4, "anios_aotc_pedidos": anios,
        "programa_con_titulo": titulo, "al_menos_medio_tiempo": medio, "condena_drogas": condena,
    }


rule(
    "fiscal-c1-credito-educativo", "FIS-C1-EDUCACION",
    f"{F6744}, Basic Scenarios 6 y 7 y Advanced Scenario 6; IRS Pub. 970 (2025), Tables 2-1 y 3-1",
    "Determinar qué crédito educativo puede pedir el contribuyente en 2025 por los gastos de un estudiante: "
    "\"AOTC\" (crédito de oportunidad estadounidense), \"LLC\" (crédito vitalicio por aprendizaje) o \"Ninguno\". "
    "El tipo de declaración viene como \"individual\", \"conjunta\" o \"separada\". Corresponde Ninguno si el "
    "tipo de declaración es separada, o si el ingreso bruto ajustado modificado (MAGI) llega a 90000 dólares, o a "
    "180000 dólares cuando el tipo de declaración es conjunta. Si no, corresponde AOTC cuando se cumplen todas "
    "estas condiciones: el estudiante no completó los primeros 4 años de estudios superiores antes de 2025, el "
    "AOTC se pidió para él en menos de 4 años anteriores, cursa un programa que otorga un título, estuvo inscripto "
    "al menos a medio tiempo y no tiene condenas por delitos graves de drogas. Si alguna de esas condiciones no se "
    "cumple, corresponde LLC.",
    {"al_menos_medio_tiempo": "Bool", "anios_aotc_pedidos": "Int", "completo_4_anios": "Bool",
     "condena_drogas": "Bool", "magi": "Int", "programa_con_titulo": "Bool", "tipo_declaracion": "String"},
    ite(
        op("OR", eq("tipo_declaracion", "separada"),
           op(">=", var("magi"), ite(eq("tipo_declaracion", "conjunta"), lit(180000), lit(90000)))),
        S("Ninguno"),
        ite(
            all_(not_(var("completo_4_anios")), op("<", var("anios_aotc_pedidos"), lit(4)),
                 var("programa_con_titulo"), var("al_menos_medio_tiempo"), not_(var("condena_drogas"))),
            S("AOTC"), S("LLC"),
        ),
    ),
    "def evaluate_rule(data):\n"
    "    tipo = data['tipo_declaracion']\n"
    "    tope = 180000 if tipo == 'conjunta' else 90000\n"
    "    if tipo == 'separada' or data['magi'] >= tope:\n"
    "        return 'Ninguno'\n"
    "    if (\n"
    "        not data['completo_4_anios']\n"
    "        and data['anios_aotc_pedidos'] < 4\n"
    "        and data['programa_con_titulo']\n"
    "        and data['al_menos_medio_tiempo']\n"
    "        and not data['condena_drogas']\n"
    "    ):\n"
    "        return 'AOTC'\n"
    "    return 'LLC'\n",
    [
        ("F6744-B6-SCOTT", edu("individual", 34600, comp4=True, anios=4, titulo=False, medio=False)),
        ("F6744-A6-CARLOS", edu("individual", 21250, titulo=False, medio=False)),
        ("F6744-B7-KNOX", edu("conjunta", 60000, anios=3)),
        ("V1-SEPARADA", edu("separada", 30000)),
        ("V2-MAGI-90000", edu("individual", 90000)),
        ("V3-MAGI-89999", edu("individual", 89999)),
        ("V4-CUATRO-ANIOS-PEDIDOS", edu("conjunta", 179999, anios=4)),
        ("V5-MAGI-180000", edu("conjunta", 180000)),
        ("V6-CONDENA", edu("individual", 40000, condena=True)),
    ],
)

# --- IRS-05: gasto médico calificado para la HSA -----------------------------------------

CALIFICAN = [
    "consulta_medica", "medicamento_recetado", "medicamento_venta_libre", "producto_menstrual", "fisioterapia",
    "tratamiento_dental", "limpieza_dental", "corona_dental", "anteojos", "lentes_de_contacto", "audifonos",
    "ambulancia", "analisis_laboratorio", "psiquiatria", "internacion",
]


def hsa(tipo, reemb=False, post=True):
    return {"tipo_gasto": tipo, "reembolsado": reemb, "posterior_a_apertura": post}


rule(
    "fiscal-c1-gasto-hsa", "FIS-C1-GASTO-HSA",
    f"{F6744}, Advanced Scenario 3; IRS Pub. 969 (2025) y Pub. 502 (2025)",
    "Determinar si un gasto se puede pagar con la cuenta de ahorro para la salud (HSA) como gasto médico "
    "calificado. El gasto califica solo si no fue reembolsado por un seguro, se hizo después de abrir la cuenta y "
    "su tipo es uno de estos: "
    + ", ".join(f"\"{c}\"" for c in CALIFICAN[:-1]) + f" o \"{CALIFICAN[-1]}\". "
    "Los demás tipos, como \"gimnasio\", \"blanqueamiento_dental\", \"cirugia_estetica\", "
    "\"suplemento_nutricional\" o \"gastos_funerarios\", no califican.",
    {"posterior_a_apertura": "Bool", "reembolsado": "Bool", "tipo_gasto": "String"},
    all_(not_(var("reembolsado")), var("posterior_a_apertura"), in_(var("tipo_gasto"), CALIFICAN)),
    "CALIFICAN = {\n"
    + "".join(f"    '{c}',\n" for c in CALIFICAN)
    + "}\n\n"
    "def evaluate_rule(data):\n"
    "    return not data['reembolsado'] and data['posterior_a_apertura'] and data['tipo_gasto'] in CALIFICAN\n",
    [
        ("F6744-A3-FISIOTERAPIA", hsa("fisioterapia")),
        ("F6744-A3-MEDICO", hsa("consulta_medica")),
        ("F6744-A3-RECETA", hsa("medicamento_recetado")),
        ("F6744-A3-CORONA", hsa("corona_dental")),
        ("F6744-A3-VENTA-LIBRE", hsa("medicamento_venta_libre")),
        ("F6744-A3-GIMNASIO", hsa("gimnasio")),
        ("V1-BLANQUEAMIENTO", hsa("blanqueamiento_dental")),
        ("V2-CIRUGIA-ESTETICA", hsa("cirugia_estetica")),
        ("V3-REEMBOLSADO", hsa("consulta_medica", reemb=True)),
        ("V4-ANTES-DE-ABRIR", hsa("fisioterapia", post=False)),
    ],
)

# --- IRS-07: crédito por otros dependientes ----------------------------------------------

def odc(dep, sit, ident, hijo, edad):
    return {"es_dependiente": dep, "situacion": sit, "identificacion": ident, "es_hijo_calificable": hijo,
            "edad": edad}


rule(
    "fiscal-c1-otros-dependientes", "FIS-C1-OTROS-DEP",
    f"{F6744}, Basic Scenario 4 e International Scenario 2; IRS Instructions for Schedule 8812 (2025)",
    "Determinar si una persona le da al contribuyente derecho al crédito por otros dependientes en 2025. Da "
    "derecho solo si se cumplen todas estas condiciones: el contribuyente la declara como dependiente; su "
    "situación en los Estados Unidos es \"ciudadano\", \"nacional\" o \"residente\" (la otra situación posible es "
    "\"no_residente\"); tiene un número de identificación de tipo \"SSN\", \"SSN_sin_permiso_laboral\", \"ITIN\" o "
    "\"ATIN\" (el otro valor posible es \"ninguna\"); y no le da derecho al crédito por hijos. Una persona le da "
    "derecho al crédito por hijos, y entonces no al de otros dependientes, cuando es hijo calificable, tiene menos "
    "de 17 años y su identificación es \"SSN\".",
    {"edad": "Int", "es_dependiente": "Bool", "es_hijo_calificable": "Bool", "identificacion": "String",
     "situacion": "String"},
    all_(
        var("es_dependiente"),
        in_(var("situacion"), ["ciudadano", "nacional", "residente"]),
        in_(var("identificacion"), ["SSN", "SSN_sin_permiso_laboral", "ITIN", "ATIN"]),
        not_(all_(var("es_hijo_calificable"), op("<", var("edad"), lit(17)), eq("identificacion", "SSN"))),
    ),
    "def evaluate_rule(data):\n"
    "    credito_por_hijos = data['es_hijo_calificable'] and data['edad'] < 17 and data['identificacion'] == 'SSN'\n"
    "    return (\n"
    "        data['es_dependiente']\n"
    "        and data['situacion'] in ('ciudadano', 'nacional', 'residente')\n"
    "        and data['identificacion'] in ('SSN', 'SSN_sin_permiso_laboral', 'ITIN', 'ATIN')\n"
    "        and not credito_por_hijos\n"
    "    )\n",
    [
        ("F6744-B4-KYLE", odc(True, "ciudadano", "SSN", False, 19)),
        ("F6744-B4-BLAKE", odc(True, "ciudadano", "SSN", True, 11)),
        ("F6744-I2-BINDI", odc(False, "no_residente", "ninguna", False, 30)),
        ("F6744-I2-JACKSON", odc(True, "ciudadano", "SSN", True, 3)),
        ("V1-HIJO-CON-ITIN", odc(True, "residente", "ITIN", True, 16)),
        ("V2-HIJO-17", odc(True, "ciudadano", "SSN", True, 17)),
        ("V3-HIJO-16", odc(True, "ciudadano", "SSN", True, 16)),
        ("V4-SOBRINO-EN-MEXICO", odc(True, "no_residente", "ITIN", False, 10)),
        ("V5-MADRE", odc(True, "ciudadano", "SSN", False, 70)),
        ("V6-SSN-SIN-PERMISO", odc(True, "residente", "SSN_sin_permiso_laboral", True, 12)),
    ],
)
print("ok")
