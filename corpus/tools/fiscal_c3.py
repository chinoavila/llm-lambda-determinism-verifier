"""Tanda 3: fiscal, categoría 3 (IRS-18, 19, 21, 23, 25, 27). Ver docs/corpus-fuentes.md.

La tentación es lógica y bien tipada: límites (`<` contra `<=`, "al menos",
"más de la mitad"), excepciones con negación, el menor de dos montos, y dos datos
parecidos en Γ de los que solo uno es el correcto.

    docker compose run --rm pipeline python /workspace/corpus/tools/fiscal_c3.py /workspace/corpus
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from dsl import F6744, adapted, all_, any_, dec, eq, in_, ite, lit, not_, op, var, write_rule  # noqa: E402

OUT = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(__file__).parents[1]


def rule(name, case_id, reference, description, gamma, expr, python, scenarios):
    write_rule(
        OUT, name, case_id=case_id, category=3, domain="fiscal", source=adapted(reference),
        description=description, gamma=gamma, expr=expr, python=python, scenarios=scenarios,
        generator="corpus/tools/fiscal_c3.py",
    )


# --- IRS-18: hijo que cuenta para el crédito por hijos ---------------------------------------

def hijo(edad, meses=12, se_mantiene=False, ssn=True):
    return {"edad_al_31_dic": edad, "meses_con_contribuyente": meses, "se_mantiene_solo": se_mantiene, "tiene_ssn": ssn}


rule(
    "fiscal-c3-hijo-credito", "FIS-C3-HIJO-CREDITO",
    f"{F6744}, Basic Scenarios 3 y 4 y Advanced Scenario 2; IRS Instructions for Schedule 8812 (2025), Qualifying child",
    "Determinar si un hijo le da al contribuyente el crédito por hijos de 2025. Se lo da si al 31 de diciembre tenía "
    "menos de 17 años, vivió con el contribuyente más de la mitad del año (se cuentan meses completos, de 0 a 12), "
    "tiene número de seguro social y no pagó más de la mitad de su propio sustento. Un hijo que cumplió 17 durante "
    "el año ya no da el crédito.",
    {"edad_al_31_dic": "Int", "meses_con_contribuyente": "Int", "se_mantiene_solo": "Bool", "tiene_ssn": "Bool"},
    all_(
        op("<", var("edad_al_31_dic"), lit(17)),
        op(">", var("meses_con_contribuyente"), lit(6)),
        var("tiene_ssn"),
        not_(var("se_mantiene_solo")),
    ),
    "def evaluate_rule(data):\n"
    "    return (\n"
    "        data['edad_al_31_dic'] < 17\n"
    "        and data['meses_con_contribuyente'] > 6\n"
    "        and data['tiene_ssn']\n"
    "        and not data['se_mantiene_solo']\n"
    "    )\n",
    [
        ("F6744-B3-ELENA", hijo(12)),
        ("F6744-B3-JORGE", hijo(16)),
        ("F6744-A2-JACK", hijo(17)),
        ("F6744-B4-BLAKE", hijo(11)),
        ("F6744-B4-KYLE", hijo(19)),
        ("V1-SEIS-MESES", hijo(10, meses=6)),
        ("V2-SIETE-MESES", hijo(10, meses=7)),
        ("V3-SE-MANTIENE", hijo(16, se_mantiene=True)),
        ("V4-SIN-SSN", hijo(5, ssn=False)),
        ("V5-RECIEN-NACIDO", hijo(0)),
        ("V6-CERO-MESES", hijo(3, meses=0)),
    ],
)

# --- IRS-19: obligación de presentar la declaración ------------------------------------------

def obl(estado, mayores, ingreso):
    return {"estado_civil": estado, "cantidad_65_o_mas": mayores, "ingreso_bruto": ingreso}


umbral = ite(
    eq("estado_civil", "casado_separado"),
    lit(5),
    op("+",
       ite(in_(var("estado_civil"), ["casado_conjunta", "viudo_calificado"]), lit(31500),
           ite(eq("estado_civil", "jefe_de_hogar"), lit(23625), lit(15750))),
       op("*", var("cantidad_65_o_mas"),
          ite(in_(var("estado_civil"), ["soltero", "jefe_de_hogar"]), lit(2000), lit(1600)))),
)
rule(
    "fiscal-c3-obligacion-de-presentar", "FIS-C3-OBLIGACION",
    f"{F6744}, Basic Scenario 5; IRS Pub. 501 (2025), Table 1",
    "Determinar si el contribuyente está obligado a presentar la declaración de 2025. Lo está si su ingreso bruto "
    "llega al menos al umbral de su estado civil (\"soltero\", \"jefe_de_hogar\", \"casado_conjunta\", "
    "\"casado_separado\" o \"viudo_calificado\"). El umbral es 15750 dólares para soltero, 23625 para "
    "jefe_de_hogar y 31500 para casado_conjunta y viudo_calificado, más un adicional por cada persona de 65 años o "
    "más (el contribuyente, y en la declaración conjunta también el cónyuge): 2000 dólares para soltero y "
    "jefe_de_hogar, 1600 para los demás. La excepción es casado_separado: tiene que presentar con 5 dólares de "
    "ingreso bruto, cualquiera sea su edad.",
    {"cantidad_65_o_mas": "Int", "estado_civil": "String", "ingreso_bruto": "Int"},
    op(">=", var("ingreso_bruto"), umbral),
    "def evaluate_rule(data):\n"
    "    estado = data['estado_civil']\n"
    "    if estado == 'casado_separado':\n"
    "        umbral = 5\n"
    "    else:\n"
    "        if estado in ('casado_conjunta', 'viudo_calificado'):\n"
    "            base = 31500\n"
    "        elif estado == 'jefe_de_hogar':\n"
    "            base = 23625\n"
    "        else:\n"
    "            base = 15750\n"
    "        adicional = 2000 if estado in ('soltero', 'jefe_de_hogar') else 1600\n"
    "        umbral = base + data['cantidad_65_o_mas'] * adicional\n"
    "    return data['ingreso_bruto'] >= umbral\n",
    [
        ("F6744-B5-NEIL", obl("soltero", 0, 9250)),
        ("V1-JUSTO-EN-EL-UMBRAL", obl("soltero", 0, 15750)),
        ("V2-UN-DOLAR-MENOS", obl("soltero", 0, 15749)),
        ("V3-MAYOR-DEBAJO", obl("soltero", 1, 17749)),
        ("V4-CONJUNTA-DOS-MAYORES", obl("casado_conjunta", 2, 34700)),
        ("V5-SEPARADO-CINCO", obl("casado_separado", 0, 5)),
        ("V6-SEPARADO-CUATRO", obl("casado_separado", 1, 4)),
        ("V7-JEFE-MAYOR", obl("jefe_de_hogar", 1, 25625)),
        ("V8-CONJUNTA-UN-MAYOR-DEBAJO", obl("casado_conjunta", 1, 33099)),
    ],
)

# --- IRS-21: pérdidas de juego deducibles ----------------------------------------------------

def juego(detalla, ganancias, perdidas):
    return {"detalla_deducciones": detalla, "ganancias_juego": ganancias, "perdidas_juego": perdidas}


rule(
    "fiscal-c3-perdidas-juego", "FIS-C3-PERDIDAS-JUEGO",
    f"{F6744}, Advanced Scenario 5; IRS Instructions for Schedule A (2025), line 16",
    "Calcular cuánto de sus pérdidas de juego puede deducir el contribuyente en 2025, en dólares. Solo se deducen si "
    "detalla sus deducciones en lugar de usar la deducción estándar, y nunca más que lo que ganó en el juego ese "
    "año: si perdió más de lo que ganó, deduce lo ganado. Si no detalla, deduce 0.",
    {"detalla_deducciones": "Bool", "ganancias_juego": "Int", "perdidas_juego": "Int"},
    ite(var("detalla_deducciones"),
        ite(op("<", var("perdidas_juego"), var("ganancias_juego")), var("perdidas_juego"), var("ganancias_juego")),
        lit(0)),
    "def evaluate_rule(data):\n"
    "    if not data['detalla_deducciones']:\n"
    "        return 0\n"
    "    return min(data['perdidas_juego'], data['ganancias_juego'])\n",
    [
        ("F6744-A5-JULIA", juego(True, 3000, 2000)),
        ("V1-NO-DETALLA", juego(False, 3000, 2000)),
        ("V2-PERDIO-MAS", juego(True, 3000, 5000)),
        ("V3-IGUALES", juego(True, 3000, 3000)),
        ("V4-SIN-GANANCIAS", juego(True, 0, 800)),
        ("V5-UN-DOLAR-MENOS", juego(True, 1200, 1199)),
    ],
)

# --- IRS-23: millas deducibles en una mudanza militar ----------------------------------------

def mudanza(recorridas, directa, peajes):
    return {"millas_recorridas": recorridas, "millas_ruta_directa": directa, "peajes_y_estacionamiento": peajes}


rule(
    "fiscal-c3-millas-mudanza", "FIS-C3-MILLAS-MUDANZA",
    f"{F6744}, Military Scenario 2; IRS Pub. 3 (2025), Moving Expenses (Travel)",
    "Calcular el gasto de auto deducible en la mudanza de un militar por cambio permanente de destino en 2025. Se "
    "deducen 0.21 dólares por milla más los peajes y el estacionamiento. Las desviaciones innecesarias no se deducen: "
    "si las millas recorridas superan las de la ruta más directa, se usan las de la ruta más directa; si no, las "
    "recorridas. Las comidas y el hotel no entran en este cálculo.",
    {"millas_recorridas": "Int", "millas_ruta_directa": "Int", "peajes_y_estacionamiento": "Int"},
    op("+",
       op("*", ite(op(">", var("millas_recorridas"), var("millas_ruta_directa")), var("millas_ruta_directa"), var("millas_recorridas")),
          dec("0.21")),
       var("peajes_y_estacionamiento")),
    "from decimal import Decimal\n\n"
    "def evaluate_rule(data):\n"
    "    millas = min(data['millas_recorridas'], data['millas_ruta_directa'])\n"
    "    return millas * Decimal('0.21') + data['peajes_y_estacionamiento']\n",
    [
        ("F6744-M2-RIVERS", mudanza(878, 618, 305)),
        ("V1-SIN-DESVIO", mudanza(618, 618, 305)),
        ("V2-MENOS-QUE-LA-DIRECTA", mudanza(600, 618, 0)),
        ("V3-SIN-PEAJES", mudanza(1500, 1200, 0)),
        ("V4-UNA-MILLA-DE-DESVIO", mudanza(1001, 1000, 40)),
        ("V5-DESVIO-LARGO", mudanza(3000, 900, 12)),
    ],
)

# --- IRS-25: cuidado de dependientes pagado a un familiar ------------------------------------

def cuidador(dependiente=False, hijo=False, edad=40, conyuge=False, padre=False, edad_nino=8):
    return {"cuidador_es_dependiente": dependiente, "cuidador_es_hijo": hijo, "edad_cuidador": edad,
            "cuidador_fue_conyuge": conyuge, "cuidador_es_padre_del_nino": padre, "edad_nino": edad_nino}


rule(
    "fiscal-c3-cuidado-familiar", "FIS-C3-CUIDADO-FAMILIAR",
    f"{F6744}, Advanced Scenario 2; IRS Pub. 503 (2025), Payments to Relatives or Dependents",
    "Determinar si lo que el contribuyente le pagó en 2025 a un familiar por cuidar a su hijo cuenta para el crédito "
    "por cuidado de dependientes. Los pagos a familiares cuentan, salvo en cuatro casos: si el cuidador es "
    "dependiente del contribuyente; si es hijo del contribuyente y tenía menos de 19 años al 31 de diciembre; si fue "
    "su cónyuge en algún momento del año; o si es el padre o la madre del niño cuidado y ese niño tiene menos de 13 "
    "años.",
    {"cuidador_es_dependiente": "Bool", "cuidador_es_hijo": "Bool", "cuidador_es_padre_del_nino": "Bool",
     "cuidador_fue_conyuge": "Bool", "edad_cuidador": "Int", "edad_nino": "Int"},
    not_(any_(
        var("cuidador_es_dependiente"),
        op("AND", var("cuidador_es_hijo"), op("<", var("edad_cuidador"), lit(19))),
        var("cuidador_fue_conyuge"),
        op("AND", var("cuidador_es_padre_del_nino"), op("<", var("edad_nino"), lit(13))),
    )),
    "def evaluate_rule(data):\n"
    "    excluido = (\n"
    "        data['cuidador_es_dependiente']\n"
    "        or (data['cuidador_es_hijo'] and data['edad_cuidador'] < 19)\n"
    "        or data['cuidador_fue_conyuge']\n"
    "        or (data['cuidador_es_padre_del_nino'] and data['edad_nino'] < 13)\n"
    "    )\n"
    "    return not excluido\n",
    [
        ("F6744-A2-SUMMER-JACK", cuidador(dependiente=True, hijo=True, edad=17)),
        ("V1-HIJO-19", cuidador(hijo=True, edad=19)),
        ("V2-HIJO-18", cuidador(hijo=True, edad=18)),
        ("V3-ABUELA", cuidador(edad=67)),
        ("V4-EX-CONYUGE", cuidador(conyuge=True)),
        ("V5-PADRE-NINO-12", cuidador(padre=True, edad_nino=12)),
        ("V6-PADRE-NINO-13", cuidador(padre=True, edad_nino=13)),
        ("V7-TIA-DEPENDIENTE", cuidador(dependiente=True, edad=70)),
        ("V8-HERMANA-16", cuidador(edad=16)),
        ("V9-TIO", cuidador(edad=45)),
    ],
)

# --- IRS-27: considerado no casado ----------------------------------------------------------

def no_casado(separado=True, paga=True, ultimo_mes=0, meses_hijo=12, declara=True):
    return {"presenta_por_separado": separado, "paga_mas_mitad_hogar": paga, "ultimo_mes_conyuge_en_casa": ultimo_mes,
            "meses_hijo_en_casa": meses_hijo, "puede_declarar_hijo": declara}


rule(
    "fiscal-c3-considerado-no-casado", "FIS-C3-NO-CASADO",
    f"{F6744}, Advanced Scenarios 1 y 4; IRS Pub. 501 (2025), Considered Unmarried",
    "Determinar si una persona casada puede considerarse no casada al 31 de diciembre de 2025 para presentar como "
    "jefe de hogar. Puede, si se cumplen todas estas condiciones: presenta una declaración separada de la de su "
    "cónyuge; pagó más de la mitad del costo de mantener su casa; su hijo vivió en esa casa más de la mitad del año "
    "(se cuentan meses completos) y lo puede declarar como dependiente; y el cónyuge no vivió en la casa durante los "
    "últimos 6 meses del año. Para esto último se informa el último mes de 2025 en que el cónyuge vivió en la casa "
    "(de 1 a 12), o 0 si no vivió allí en todo 2025.",
    {"meses_hijo_en_casa": "Int", "paga_mas_mitad_hogar": "Bool", "presenta_por_separado": "Bool",
     "puede_declarar_hijo": "Bool", "ultimo_mes_conyuge_en_casa": "Int"},
    all_(
        var("presenta_por_separado"),
        var("paga_mas_mitad_hogar"),
        op(">", var("meses_hijo_en_casa"), lit(6)),
        var("puede_declarar_hijo"),
        op("<=", var("ultimo_mes_conyuge_en_casa"), lit(6)),
    ),
    "def evaluate_rule(data):\n"
    "    return (\n"
    "        data['presenta_por_separado']\n"
    "        and data['paga_mas_mitad_hogar']\n"
    "        and data['meses_hijo_en_casa'] > 6\n"
    "        and data['puede_declarar_hijo']\n"
    "        and data['ultimo_mes_conyuge_en_casa'] <= 6\n"
    "    )\n",
    [
        ("F6744-A1-JOY", no_casado()),
        ("F6744-A4-AMY", no_casado(paga=False)),
        ("V1-SE-FUE-EN-JUNIO", no_casado(ultimo_mes=6)),
        ("V2-SE-FUE-EN-JULIO", no_casado(ultimo_mes=7)),
        ("V3-PRESENTAN-JUNTOS", no_casado(separado=False)),
        ("V4-HIJO-SEIS-MESES", no_casado(meses_hijo=6)),
        ("V5-HIJO-SIETE-MESES", no_casado(meses_hijo=7, ultimo_mes=3)),
        ("V6-NO-PUEDE-DECLARARLO", no_casado(declara=False)),
        ("V7-SE-FUE-EN-ENERO", no_casado(ultimo_mes=1)),
    ],
)
print("ok")
