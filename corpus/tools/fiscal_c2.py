"""Tanda 2: fiscal, categoría 2 (IRS-09, 10, 11, 13, 15, 16). Ver docs/corpus-fuentes.md.

La tentación de tipos sale de la regla misma: montos `Decimal` contra cantidades
`Int`, ramas que valen `0.0` (no `0`), datos que el enunciado nombra pero no están
en Γ, y `%` que solo vale sobre enteros.

    docker compose run --rm pipeline python /workspace/corpus/tools/fiscal_c2.py /workspace/corpus
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from dsl import F6744, adapted, all_, any_, dec, eq, in_, ite, lit, not_, op, var, write_rule  # noqa: E402

OUT = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(__file__).parents[1]


def rule(name, case_id, reference, description, gamma, expr, python, scenarios):
    write_rule(
        OUT, name, case_id=case_id, category=2, domain="fiscal", source=adapted(reference),
        description=description, gamma=gamma, expr=expr, python=python, scenarios=scenarios,
        generator="corpus/tools/fiscal_c2.py",
    )


# --- IRS-09: deducción estándar ------------------------------------------------------------

def std(estado, casillas):
    return {"estado_civil": estado, "casillas": casillas}


conjunta_o_viudo = in_(var("estado_civil"), ["casado_conjunta", "viudo_calificado"])
rule(
    "fiscal-c2-deduccion-estandar", "FIS-C2-DEDUCCION-STD",
    f"{F6744}, Basic Scenarios 1, 5 y 7 y Advanced Scenario 5; IRS Pub. 501 (2025), Tables 6 y 7",
    "Calcular la deducción estándar de 2025 en dólares. El estado civil viene como \"soltero\", "
    "\"jefe_de_hogar\", \"casado_conjunta\", \"casado_separado\" o \"viudo_calificado\". El monto base es 31500 "
    "para casado_conjunta y viudo_calificado, 23625 para jefe_de_hogar y 15750 para soltero y casado_separado. "
    "A ese monto se le suma un adicional por cada casilla marcada: se marca una casilla por tener 65 años o más y "
    "otra por ser ciego, para el contribuyente y también para su cónyuge si presentan juntos, así que puede haber "
    "de 0 a 4 casillas. El adicional por casilla es de 2000 dólares para soltero y jefe_de_hogar, y de 1600 para "
    "los demás. La edad y la ceguera ya vienen contadas en la cantidad de casillas.",
    {"casillas": "Int", "estado_civil": "String"},
    op(
        "+",
        ite(conjunta_o_viudo, lit(31500), ite(eq("estado_civil", "jefe_de_hogar"), lit(23625), lit(15750))),
        op("*", var("casillas"),
           ite(in_(var("estado_civil"), ["soltero", "jefe_de_hogar"]), lit(2000), lit(1600))),
    ),
    "def evaluate_rule(data):\n"
    "    estado = data['estado_civil']\n"
    "    if estado in ('casado_conjunta', 'viudo_calificado'):\n"
    "        base = 31500\n"
    "    elif estado == 'jefe_de_hogar':\n"
    "        base = 23625\n"
    "    else:\n"
    "        base = 15750\n"
    "    adicional = 2000 if estado in ('soltero', 'jefe_de_hogar') else 1600\n"
    "    return base + data['casillas'] * adicional\n",
    [
        ("F6744-B1-FRED", std("jefe_de_hogar", 1)),
        ("F6744-B5-NEIL", std("soltero", 0)),
        ("F6744-B7-KNOX", std("casado_conjunta", 0)),
        ("V1-SOLTERO-DOS-CASILLAS", std("soltero", 2)),
        ("V2-CONJUNTA-CUATRO", std("casado_conjunta", 4)),
        ("V3-SEPARADO-DOS", std("casado_separado", 2)),
        ("V4-VIUDO-UNA", std("viudo_calificado", 1)),
        ("V5-JEFE-SIN-CASILLAS", std("jefe_de_hogar", 0)),
    ],
)

# --- IRS-10: ingreso ganado con paga de combate ---------------------------------------------

def ganado(salarios, combate, elige, independiente):
    return {"salarios": salarios, "paga_combate": combate, "incluye_combate": elige, "trabajo_independiente": independiente}


rule(
    "fiscal-c2-ingreso-ganado", "FIS-C2-INGRESO-GANADO",
    f"{F6744}, Military Scenario 4 y Basic Scenario 2; IRS Pub. 596 (2025) e IRS Pub. 3 (2025), Nontaxable combat pay election",
    "Calcular el ingreso del trabajo de un hogar militar para el crédito por ingreso del trabajo de 2025. Es la "
    "suma de los salarios imponibles (con centavos), la ganancia neta del trabajo independiente (en dólares "
    "enteros, puede ser negativa si hubo pérdida) y la paga de combate no imponible, que solo se suma si el "
    "contribuyente elige incluirla; si no la elige, esa parte vale cero. Los intereses, los dividendos, el seguro "
    "de desempleo y las jubilaciones no son ingreso del trabajo y no entran en el cálculo.",
    {"incluye_combate": "Bool", "paga_combate": "Decimal", "salarios": "Decimal", "trabajo_independiente": "Int"},
    op("+", op("+", var("salarios"), var("trabajo_independiente")),
       ite(var("incluye_combate"), var("paga_combate"), dec("0"))),
    "from decimal import Decimal\n\n"
    "def evaluate_rule(data):\n"
    "    combate = data['paga_combate'] if data['incluye_combate'] else Decimal('0')\n"
    "    return data['salarios'] + data['trabajo_independiente'] + combate\n",
    [
        ("F6744-M4-WATERS-SIN-ELEGIR", ganado(53500.25, 6000.5, False, 0)),
        ("F6744-M4-WATERS-ELIGE", ganado(53500.25, 6000.5, True, 0)),
        ("V1-INDEPENDIENTE-ELIGE", ganado(18000.5, 2400.25, True, 1200)),
        ("V2-PERDIDA-INDEPENDIENTE", ganado(30000.5, 1000.5, False, -800)),
        ("V3-COMBATE-IGUAL-A-SALARIO", ganado(12000.75, 12000.25, True, 0)),
        ("V4-CENTAVOS", ganado(9999.99, 5000.01, False, 500)),
    ],
)

# --- IRS-11: viaje de un reservista ---------------------------------------------------------

def viaje(distancia, millas, peajes):
    return {"distancia_millas": distancia, "millas_recorridas": millas, "peajes_y_estacionamiento": peajes}


rule(
    "fiscal-c2-viaje-reservista", "FIS-C2-VIAJE-RESERVISTA",
    f"{F6744}, Military Scenario 1; IRS Pub. 3 (2025), Armed Forces Reservists y standard mileage rate",
    "Calcular cuánto puede deducir en 2025 un miembro de la reserva por viajar en su auto a las prácticas. Solo "
    "hay deducción si la base está a más de 100 millas de su casa; en ese caso deduce las millas recorridas a 0.70 "
    "dólares por milla, más lo que pagó de peajes y estacionamiento. Si la base está a 100 millas o menos, la "
    "deducción es 0.0. Las comidas y los uniformes no se deducen por esta vía.",
    {"distancia_millas": "Int", "millas_recorridas": "Int", "peajes_y_estacionamiento": "Int"},
    ite(op(">", var("distancia_millas"), lit(100)),
        op("+", op("*", var("millas_recorridas"), dec("0.70")), var("peajes_y_estacionamiento")),
        dec("0")),
    "from decimal import Decimal\n\n"
    "def evaluate_rule(data):\n"
    "    if data['distancia_millas'] > 100:\n"
    "        return data['millas_recorridas'] * Decimal('0.70') + data['peajes_y_estacionamiento']\n"
    "    return Decimal('0')\n",
    [
        ("F6744-M1-MALIK", viaje(150, 3600, 92)),
        ("V1-DISTANCIA-100", viaje(100, 2400, 50)),
        ("V2-DISTANCIA-101", viaje(101, 2424, 0)),
        ("V3-DISTANCIA-99", viaje(99, 2376, 30)),
        ("V4-SIN-PEAJES", viaje(250, 1000, 0)),
        ("V5-UNA-MILLA", viaje(500, 1, 3)),
    ],
)

# --- IRS-13: prueba de ciudadanía del dependiente -------------------------------------------

def ciud(situacion, pais, adoptado=False, meses=0, contribuyente_ciudadano=True):
    return {"situacion": situacion, "pais_residencia": pais, "es_adoptado": adoptado,
            "meses_con_contribuyente": meses, "contribuyente_es_ciudadano": contribuyente_ciudadano}


rule(
    "fiscal-c2-ciudadania-dependiente", "FIS-C2-CIUDADANIA",
    f"{F6744}, International Scenario 2 y Basic Scenario 4; IRS Pub. 501 (2025), Citizen or Resident Test",
    "Determinar si una persona pasa la prueba de ciudadanía para poder ser declarada como dependiente en 2025. "
    "La pasa si su situación es \"ciudadano\", \"nacional\" o \"residente\" de los Estados Unidos (la otra "
    "situación posible es \"extranjero\"), o si vive en \"Canadá\" o en \"México\". También la pasa un hijo "
    "adoptado que vivió con el contribuyente los 12 meses del año, siempre que el contribuyente sea ciudadano o "
    "nacional de los Estados Unidos. La edad y los ingresos de la persona no importan para esta prueba.",
    {"contribuyente_es_ciudadano": "Bool", "es_adoptado": "Bool", "meses_con_contribuyente": "Int",
     "pais_residencia": "String", "situacion": "String"},
    any_(
        in_(var("situacion"), ["ciudadano", "nacional", "residente"]),
        in_(var("pais_residencia"), ["Canadá", "México"]),
        all_(var("es_adoptado"), op("==", var("meses_con_contribuyente"), lit(12)), var("contribuyente_es_ciudadano")),
    ),
    "def evaluate_rule(data):\n"
    "    return (\n"
    "        data['situacion'] in ('ciudadano', 'nacional', 'residente')\n"
    "        or data['pais_residencia'] in ('Canadá', 'México')\n"
    "        or (data['es_adoptado'] and data['meses_con_contribuyente'] == 12 and data['contribuyente_es_ciudadano'])\n"
    "    )\n",
    [
        ("F6744-I2-BINDI", ciud("extranjero", "Australia", meses=12)),
        ("F6744-I2-JACKSON", ciud("ciudadano", "Australia", meses=12)),
        ("F6744-B4-KYLE", ciud("ciudadano", "Estados Unidos", meses=12)),
        ("V1-VIVE-EN-MEXICO", ciud("extranjero", "México")),
        ("V2-VIVE-EN-CANADA", ciud("extranjero", "Canadá")),
        ("V3-ADOPTADO-12-MESES", ciud("extranjero", "Francia", adoptado=True, meses=12)),
        ("V4-ADOPTADO-11-MESES", ciud("extranjero", "Francia", adoptado=True, meses=11)),
        ("V5-ADOPTANTE-NO-CIUDADANO", ciud("extranjero", "Francia", adoptado=True, meses=12, contribuyente_ciudadano=False)),
        ("V6-EXTRANJERO-EN-FRANCIA", ciud("extranjero", "Francia", meses=12)),
    ],
)

# --- IRS-15: crédito por hijos con reducción por ingreso -------------------------------------

def ctc(hijos, otros, conjunta, magi):
    return {"hijos_menores_17": hijos, "otros_dependientes": otros, "declaracion_conjunta": conjunta, "magi": magi}


umbral = ite(var("declaracion_conjunta"), lit(400000), lit(200000))
exceso = op("-", var("magi"), umbral)
redondeado = op("+", exceso, lit(999))
reduccion = ite(
    op(">", var("magi"), umbral),
    op("*", op("/", op("-", redondeado, op("%", redondeado, lit(1000))), lit(1000)), lit(50)),
    dec("0"),
)
total = op("-", op("+", op("*", var("hijos_menores_17"), lit(2200)), op("*", var("otros_dependientes"), lit(500))), reduccion)
rule(
    "fiscal-c2-credito-por-hijos", "FIS-C2-CREDITO-HIJOS",
    f"{F6744}, Basic Scenario 3 y Advanced Scenario 2; IRS Instructions for Schedule 8812 (2025), Credit Limit Worksheet A",
    "Calcular el crédito por hijos y por otros dependientes de 2025, en dólares, antes del límite por impuesto. "
    "Son 2200 dólares por cada hijo calificable menor de 17 años más 500 por cada otro dependiente. Si el ingreso "
    "bruto ajustado modificado (MAGI) supera 400000 dólares en una declaración conjunta, o 200000 en cualquier otra, "
    "el crédito se reduce 50 dólares por cada 1000 dólares o fracción de exceso: 1 dólar de exceso ya reduce 50, "
    "1000 de exceso reducen 50 y 1001 reducen 100. El crédito nunca es negativo: si la reducción lo supera, vale 0.0.",
    {"declaracion_conjunta": "Bool", "hijos_menores_17": "Int", "magi": "Int", "otros_dependientes": "Int"},
    ite(op(">", total, lit(0)), total, dec("0")),
    "from decimal import Decimal\n\n"
    "def evaluate_rule(data):\n"
    "    umbral = 400000 if data['declaracion_conjunta'] else 200000\n"
    "    base = data['hijos_menores_17'] * 2200 + data['otros_dependientes'] * 500\n"
    "    reduccion = Decimal('0')\n"
    "    if data['magi'] > umbral:\n"
    "        miles = (data['magi'] - umbral + 999) // 1000\n"
    "        reduccion = Decimal(miles * 50)\n"
    "    total = base - reduccion\n"
    "    return total if total > 0 else Decimal('0')\n",
    [
        ("F6744-B3-RAMIREZ", ctc(2, 0, True, 34500)),
        ("F6744-A2-SUMMER", ctc(1, 1, True, 54000)),
        ("V1-EN-EL-UMBRAL", ctc(1, 0, False, 200000)),
        ("V2-UN-DOLAR-DE-EXCESO", ctc(1, 0, False, 200001)),
        ("V3-MIL-DE-EXCESO", ctc(1, 0, False, 201000)),
        ("V4-MIL-UNO-DE-EXCESO", ctc(1, 0, False, 201001)),
        ("V5-CONJUNTA-ALTA", ctc(3, 0, True, 450000)),
        ("V6-REDUCCION-TOTAL", ctc(1, 0, False, 300000)),
        ("V7-SOLO-OTROS", ctc(0, 2, False, 80000)),
    ],
)

# --- IRS-16: impuesto adicional por retiro anticipado de una IRA -------------------------------

EXCEPCIONES = ["educacion_superior", "discapacidad_total", "fallecimiento_del_titular", "seguro_medico_desempleado"]


def ira(edad, motivo, monto):
    return {"edad": edad, "motivo": motivo, "monto": monto}


rule(
    "fiscal-c2-ira-anticipado", "FIS-C2-IRA-ANTICIPADO",
    f"{F6744}, Advanced Scenario 6; IRS Pub. 590-B (2025), Age 59 1/2 Rule y Exceptions",
    "Calcular el impuesto adicional de 2025 por un retiro anticipado de una cuenta IRA tradicional. La edad viene "
    "en años con decimales (por ejemplo, 28.5) y el monto con centavos. Si la persona tenía menos de 59 años y medio "
    "al retirar, paga un 10 % del monto retirado, salvo que el motivo del retiro sea uno de estos: "
    "\"educacion_superior\", \"discapacidad_total\", \"fallecimiento_del_titular\" o \"seguro_medico_desempleado\". "
    "Con 59 años y medio o más, o con uno de esos motivos, el impuesto adicional es 0.0. El saldo de la cuenta no "
    "cambia el resultado.",
    {"edad": "Decimal", "monto": "Decimal", "motivo": "String"},
    ite(op("AND", op("<", var("edad"), dec("59.5")), not_(in_(var("motivo"), EXCEPCIONES))),
        op("*", var("monto"), dec("0.10")),
        dec("0")),
    "from decimal import Decimal\n\n"
    f"EXCEPCIONES = {tuple(EXCEPCIONES)!r}\n\n"
    "def evaluate_rule(data):\n"
    "    if data['edad'] < Decimal('59.5') and data['motivo'] not in EXCEPCIONES:\n"
    "        return data['monto'] * Decimal('0.10')\n"
    "    return Decimal('0')\n",
    [
        ("F6744-A6-CARLOS-MATRICULA", ira(28.5, "educacion_superior", 2000.5)),
        ("F6744-A6-CARLOS-AUTO", ira(28.5, "reparacion_auto", 750.5)),
        ("V1-JUSTO-ANTES", ira(59.4, "vacaciones", 1000.5)),
        ("V2-EN-EL-LIMITE", ira(59.5, "vacaciones", 1000.5)),
        ("V3-MAYOR", ira(61.25, "vacaciones", 5000.75)),
        ("V4-DISCAPACIDAD", ira(45.5, "discapacidad_total", 5000.75)),
        ("V5-DESEMPLEADO", ira(38.75, "seguro_medico_desempleado", 1200.25)),
    ],
)
print("ok")
