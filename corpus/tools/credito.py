"""Tandas del dominio credito: 6 reglas por categoría, propias. Ver corpus/README.md.

Inspiradas en los desafíos de préstamos y tarjetas de la Decision Management
Community, sin copiar su texto. Los montos son pesos; las tasas, decimales.

    docker compose run --rm pipeline python /workspace/corpus/tools/credito.py /workspace/corpus
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from dsl import ORIGINAL, all_, any_, dec, eq, in_, ite, lit, not_, op, var, write_rule  # noqa: E402

OUT = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(__file__).parents[1]
S = lit


def rule(category, name, case_id, description, gamma, expr, python, scenarios):
    write_rule(
        OUT, f"credito-c{category}-{name}", case_id=case_id, category=category, domain="credito", source=ORIGINAL,
        description=description, gamma=gamma, expr=expr, python=python, scenarios=scenarios,
        generator="corpus/tools/credito.py",
    )


def env(**kw):
    return kw


# ===================================== Categoría 1 =====================================

rule(
    1, "prestamo-personal", "CRE-C1-PRESTAMO",
    "Aprobar o rechazar una solicitud de préstamo personal. Se aprueba solo si se cumplen todas estas condiciones: "
    "el solicitante tiene entre 18 y 75 años, ambos incluidos; su ingreso mensual es de al menos 350000 pesos; "
    "trabaja en su empleo actual hace 12 meses o más; su puntaje crediticio es de 650 o más; no tiene deudas en "
    "mora; y la cuota mensual del préstamo no supera el 35 % de su ingreso mensual. Si el solicitante es cliente "
    "del banco con sueldo acreditado, alcanzan 6 meses de antigüedad laboral en lugar de 12; las demás condiciones "
    "no cambian.",
    {"antiguedad_meses": "Int", "cuota": "Int", "edad": "Int", "en_mora": "Bool", "ingreso": "Int",
     "puntaje": "Int", "sueldo_acreditado": "Bool"},
    all_(
        op(">=", var("edad"), lit(18)), op("<=", var("edad"), lit(75)),
        op(">=", var("ingreso"), lit(350000)),
        op(">=", var("antiguedad_meses"), ite(var("sueldo_acreditado"), lit(6), lit(12))),
        op(">=", var("puntaje"), lit(650)),
        not_(var("en_mora")),
        op("<=", var("cuota"), op("*", var("ingreso"), dec("0.35"))),
    ),
    "from decimal import Decimal\n\n"
    "def evaluate_rule(data):\n"
    "    minimo = 6 if data['sueldo_acreditado'] else 12\n"
    "    return (\n"
    "        18 <= data['edad'] <= 75\n"
    "        and data['ingreso'] >= 350000\n"
    "        and data['antiguedad_meses'] >= minimo\n"
    "        and data['puntaje'] >= 650\n"
    "        and not data['en_mora']\n"
    "        and data['cuota'] <= data['ingreso'] * Decimal('0.35')\n"
    "    )\n",
    [
        ("V1-APROBADO", env(edad=35, ingreso=500000, antiguedad_meses=24, sueldo_acreditado=False, puntaje=700, en_mora=False, cuota=175000)),
        ("V2-EDAD-17", env(edad=17, ingreso=500000, antiguedad_meses=24, sueldo_acreditado=False, puntaje=700, en_mora=False, cuota=100000)),
        ("V3-EDAD-76", env(edad=76, ingreso=500000, antiguedad_meses=24, sueldo_acreditado=False, puntaje=700, en_mora=False, cuota=100000)),
        ("V4-INGRESO-BAJO", env(edad=35, ingreso=349999, antiguedad_meses=24, sueldo_acreditado=False, puntaje=700, en_mora=False, cuota=100000)),
        ("V5-ANTIGUEDAD-11", env(edad=35, ingreso=500000, antiguedad_meses=11, sueldo_acreditado=False, puntaje=700, en_mora=False, cuota=100000)),
        ("V6-ACREDITADO-6-MESES", env(edad=35, ingreso=500000, antiguedad_meses=6, sueldo_acreditado=True, puntaje=700, en_mora=False, cuota=100000)),
        ("V7-PUNTAJE-649", env(edad=35, ingreso=500000, antiguedad_meses=24, sueldo_acreditado=False, puntaje=649, en_mora=False, cuota=100000)),
        ("V8-EN-MORA", env(edad=35, ingreso=500000, antiguedad_meses=24, sueldo_acreditado=False, puntaje=700, en_mora=True, cuota=100000)),
        ("V9-CUOTA-ALTA", env(edad=35, ingreso=500000, antiguedad_meses=24, sueldo_acreditado=False, puntaje=700, en_mora=False, cuota=175001)),
        ("V10-LIMITES", env(edad=75, ingreso=350000, antiguedad_meses=12, sueldo_acreditado=False, puntaje=650, en_mora=False, cuota=122500)),
        ("V11-JOVEN-ACREDITADO", env(edad=18, ingreso=420000, antiguedad_meses=8, sueldo_acreditado=True, puntaje=690, en_mora=False, cuota=90000)),
        ("V12-VETERANO", env(edad=58, ingreso=900000, antiguedad_meses=120, sueldo_acreditado=True, puntaje=810, en_mora=False, cuota=200000)),
        ("V13-INGRESO-ALTO", env(edad=45, ingreso=1200000, antiguedad_meses=36, sueldo_acreditado=False, puntaje=760, en_mora=False, cuota=300000)),
    ],
)

rule(
    1, "riesgo-crediticio", "CRE-C1-RIESGO",
    "Clasificar el riesgo crediticio de un cliente con una letra, revisando las condiciones en este orden y "
    "quedándose con la primera que se cumpla. Es \"E\" si tiene más de 2 deudas en mora. Si no, es \"D\" si su "
    "puntaje es menor que 500 o si tiene 2 deudas en mora. Si no, es \"C\" si su puntaje es menor que 650. Si no, es "
    "\"B\" si su puntaje es menor que 750 o si tiene 1 deuda en mora. En cualquier otro caso es \"A\".",
    {"deudas_en_mora": "Int", "puntaje": "Int"},
    ite(op(">", var("deudas_en_mora"), lit(2)), S("E"),
        ite(op("OR", op("<", var("puntaje"), lit(500)), op("==", var("deudas_en_mora"), lit(2))), S("D"),
            ite(op("<", var("puntaje"), lit(650)), S("C"),
                ite(op("OR", op("<", var("puntaje"), lit(750)), op("==", var("deudas_en_mora"), lit(1))), S("B"), S("A"))))),
    "def evaluate_rule(data):\n"
    "    puntaje, mora = data['puntaje'], data['deudas_en_mora']\n"
    "    if mora > 2:\n"
    "        return 'E'\n"
    "    if puntaje < 500 or mora == 2:\n"
    "        return 'D'\n"
    "    if puntaje < 650:\n"
    "        return 'C'\n"
    "    if puntaje < 750 or mora == 1:\n"
    "        return 'B'\n"
    "    return 'A'\n",
    [
        ("V1-TRES-MORAS", env(puntaje=800, deudas_en_mora=3)),
        ("V2-DOS-MORAS", env(puntaje=800, deudas_en_mora=2)),
        ("V3-PUNTAJE-499", env(puntaje=499, deudas_en_mora=0)),
        ("V4-PUNTAJE-500", env(puntaje=500, deudas_en_mora=0)),
        ("V5-PUNTAJE-650", env(puntaje=650, deudas_en_mora=0)),
        ("V6-UNA-MORA-ALTO", env(puntaje=780, deudas_en_mora=1)),
        ("V7-PUNTAJE-750", env(puntaje=750, deudas_en_mora=0)),
        ("V8-PUNTAJE-749", env(puntaje=749, deudas_en_mora=0)),
    ],
)

rule(
    1, "tarjeta-ofrecida", "CRE-C1-TARJETA",
    "Decidir qué tarjeta de crédito ofrecerle a un cliente. Si su puntaje es menor que 600, no se le ofrece ninguna "
    "y la respuesta es \"Ninguna\". Si no: con un ingreso mensual de 2000000 pesos o más y al menos 5 años como "
    "cliente, se ofrece \"Black\"; si no, con un ingreso de 1000000 o más y al menos 2 años como cliente, "
    "\"Platinum\"; si no, con un ingreso de 500000 o más, \"Gold\"; y en cualquier otro caso, \"Clásica\". Un cliente "
    "con ingreso alto pero poca antigüedad baja al nivel que sí cumple.",
    {"anios_cliente": "Int", "ingreso": "Int", "puntaje": "Int"},
    ite(op("<", var("puntaje"), lit(600)), S("Ninguna"),
        ite(op("AND", op(">=", var("ingreso"), lit(2000000)), op(">=", var("anios_cliente"), lit(5))), S("Black"),
            ite(op("AND", op(">=", var("ingreso"), lit(1000000)), op(">=", var("anios_cliente"), lit(2))), S("Platinum"),
                ite(op(">=", var("ingreso"), lit(500000)), S("Gold"), S("Clásica"))))),
    "def evaluate_rule(data):\n"
    "    ingreso, anios = data['ingreso'], data['anios_cliente']\n"
    "    if data['puntaje'] < 600:\n"
    "        return 'Ninguna'\n"
    "    if ingreso >= 2000000 and anios >= 5:\n"
    "        return 'Black'\n"
    "    if ingreso >= 1000000 and anios >= 2:\n"
    "        return 'Platinum'\n"
    "    if ingreso >= 500000:\n"
    "        return 'Gold'\n"
    "    return 'Clásica'\n",
    [
        ("V1-PUNTAJE-BAJO", env(puntaje=599, ingreso=3000000, anios_cliente=10)),
        ("V2-BLACK", env(puntaje=720, ingreso=2000000, anios_cliente=5)),
        ("V3-ALTO-NUEVO", env(puntaje=720, ingreso=2500000, anios_cliente=1)),
        ("V4-PLATINUM", env(puntaje=720, ingreso=1000000, anios_cliente=2)),
        ("V5-ALTO-CUATRO-ANIOS", env(puntaje=700, ingreso=2100000, anios_cliente=4)),
        ("V6-GOLD", env(puntaje=650, ingreso=500000, anios_cliente=0)),
        ("V7-CLASICA", env(puntaje=650, ingreso=499999, anios_cliente=8)),
        ("V8-PUNTAJE-600", env(puntaje=600, ingreso=300000, anios_cliente=1)),
    ],
)

rule(
    1, "hipoteca", "CRE-C1-HIPOTECA",
    "Aprobar o rechazar un crédito hipotecario. Se aprueba solo si se cumplen todas estas condiciones: el monto "
    "pedido no supera el 80 % del valor de la vivienda; la suma de la cuota nueva y las cuotas de otras deudas no "
    "supera el 40 % del ingreso mensual del hogar; el solicitante tiene empleo en relación de dependencia o es "
    "\"monotributista\" o \"autonomo\" con al menos 24 meses de actividad; y la vivienda es la primera vivienda del "
    "solicitante o el plazo es de 20 años o menos. El tipo de empleo viene como \"dependencia\", \"monotributista\", "
    "\"autonomo\" o \"informal\".",
    {"cuota_nueva": "Int", "cuotas_otras": "Int", "empleo": "String", "ingreso_hogar": "Int", "meses_actividad": "Int",
     "monto": "Int", "plazo_anios": "Int", "primera_vivienda": "Bool", "valor_vivienda": "Int"},
    all_(
        op("<=", var("monto"), op("*", var("valor_vivienda"), dec("0.8"))),
        op("<=", op("+", var("cuota_nueva"), var("cuotas_otras")), op("*", var("ingreso_hogar"), dec("0.4"))),
        op("OR", eq("empleo", "dependencia"),
           op("AND", in_(var("empleo"), ["monotributista", "autonomo"]), op(">=", var("meses_actividad"), lit(24)))),
        op("OR", var("primera_vivienda"), op("<=", var("plazo_anios"), lit(20))),
    ),
    "from decimal import Decimal\n\n"
    "def evaluate_rule(data):\n"
    "    empleo_ok = data['empleo'] == 'dependencia' or (\n"
    "        data['empleo'] in ('monotributista', 'autonomo') and data['meses_actividad'] >= 24\n"
    "    )\n"
    "    return (\n"
    "        data['monto'] <= data['valor_vivienda'] * Decimal('0.8')\n"
    "        and data['cuota_nueva'] + data['cuotas_otras'] <= data['ingreso_hogar'] * Decimal('0.4')\n"
    "        and empleo_ok\n"
    "        and (data['primera_vivienda'] or data['plazo_anios'] <= 20)\n"
    "    )\n",
    [
        ("V1-APROBADA", env(monto=80000000, valor_vivienda=100000000, cuota_nueva=600000, cuotas_otras=200000, ingreso_hogar=2000000, empleo="dependencia", meses_actividad=0, primera_vivienda=True, plazo_anios=30)),
        ("V2-LTV-ALTO", env(monto=80000001, valor_vivienda=100000000, cuota_nueva=600000, cuotas_otras=0, ingreso_hogar=2000000, empleo="dependencia", meses_actividad=0, primera_vivienda=True, plazo_anios=20)),
        ("V3-DEUDA-ALTA", env(monto=50000000, valor_vivienda=100000000, cuota_nueva=600000, cuotas_otras=200001, ingreso_hogar=2000000, empleo="dependencia", meses_actividad=0, primera_vivienda=True, plazo_anios=20)),
        ("V4-AUTONOMO-24", env(monto=50000000, valor_vivienda=100000000, cuota_nueva=500000, cuotas_otras=0, ingreso_hogar=2000000, empleo="autonomo", meses_actividad=24, primera_vivienda=False, plazo_anios=15)),
        ("V5-MONOTRIBUTO-23", env(monto=50000000, valor_vivienda=100000000, cuota_nueva=500000, cuotas_otras=0, ingreso_hogar=2000000, empleo="monotributista", meses_actividad=23, primera_vivienda=True, plazo_anios=15)),
        ("V6-INFORMAL", env(monto=50000000, valor_vivienda=100000000, cuota_nueva=500000, cuotas_otras=0, ingreso_hogar=2000000, empleo="informal", meses_actividad=60, primera_vivienda=True, plazo_anios=15)),
        ("V7-SEGUNDA-VIVIENDA-25-ANIOS", env(monto=50000000, valor_vivienda=100000000, cuota_nueva=500000, cuotas_otras=0, ingreso_hogar=2000000, empleo="dependencia", meses_actividad=0, primera_vivienda=False, plazo_anios=25)),
        ("V8-SEGUNDA-VIVIENDA-20-ANIOS", env(monto=50000000, valor_vivienda=100000000, cuota_nueva=500000, cuotas_otras=0, ingreso_hogar=2000000, empleo="dependencia", meses_actividad=0, primera_vivienda=False, plazo_anios=20)),
        ("V9-MONOTRIBUTO-36", env(monto=30000000, valor_vivienda=60000000, cuota_nueva=300000, cuotas_otras=100000, ingreso_hogar=1200000, empleo="monotributista", meses_actividad=36, primera_vivienda=True, plazo_anios=25)),
    ],
)

rule(
    1, "requiere-garante", "CRE-C1-GARANTE",
    "Determinar si un préstamo requiere garante. Lo requiere si se cumple al menos una de estas condiciones: el "
    "solicitante tiene menos de 25 años; su puntaje es menor que 680; el monto pedido supera 6 veces su ingreso "
    "mensual; trabaja como \"informal\" o \"temporario\" (el tipo de empleo también puede ser \"dependencia\", "
    "\"monotributista\" o \"autonomo\"); o tuvo algún rechazo de crédito en los últimos 12 meses. La excepción: "
    "quien ofrece una garantía prendaria (un auto a nombre del solicitante) nunca necesita garante.",
    {"edad": "Int", "empleo": "String", "garantia_prendaria": "Bool", "ingreso": "Int", "monto": "Int",
     "puntaje": "Int", "rechazos_12_meses": "Int"},
    op("AND", not_(var("garantia_prendaria")),
       any_(op("<", var("edad"), lit(25)), op("<", var("puntaje"), lit(680)),
            op(">", var("monto"), op("*", var("ingreso"), lit(6))),
            in_(var("empleo"), ["informal", "temporario"]), op(">", var("rechazos_12_meses"), lit(0)))),
    "def evaluate_rule(data):\n"
    "    if data['garantia_prendaria']:\n"
    "        return False\n"
    "    return (\n"
    "        data['edad'] < 25\n"
    "        or data['puntaje'] < 680\n"
    "        or data['monto'] > data['ingreso'] * 6\n"
    "        or data['empleo'] in ('informal', 'temporario')\n"
    "        or data['rechazos_12_meses'] > 0\n"
    "    )\n",
    [
        ("V1-SIN-RIESGO", env(edad=40, puntaje=720, monto=3000000, ingreso=600000, empleo="dependencia", rechazos_12_meses=0, garantia_prendaria=False)),
        ("V2-EDAD-24", env(edad=24, puntaje=720, monto=3000000, ingreso=600000, empleo="dependencia", rechazos_12_meses=0, garantia_prendaria=False)),
        ("V3-PUNTAJE-679", env(edad=40, puntaje=679, monto=3000000, ingreso=600000, empleo="dependencia", rechazos_12_meses=0, garantia_prendaria=False)),
        ("V4-MONTO-6-VECES", env(edad=40, puntaje=720, monto=3600000, ingreso=600000, empleo="autonomo", rechazos_12_meses=0, garantia_prendaria=False)),
        ("V5-MONTO-MAS-DE-6", env(edad=40, puntaje=720, monto=3600001, ingreso=600000, empleo="dependencia", rechazos_12_meses=0, garantia_prendaria=False)),
        ("V6-TEMPORARIO", env(edad=40, puntaje=720, monto=1000000, ingreso=600000, empleo="temporario", rechazos_12_meses=0, garantia_prendaria=False)),
        ("V7-RECHAZO", env(edad=40, puntaje=720, monto=1000000, ingreso=600000, empleo="dependencia", rechazos_12_meses=1, garantia_prendaria=False)),
        ("V8-PRENDARIA", env(edad=22, puntaje=600, monto=9000000, ingreso=600000, empleo="informal", rechazos_12_meses=2, garantia_prendaria=True)),
        ("V9-MONOTRIBUTO-OK", env(edad=25, puntaje=680, monto=2000000, ingreso=500000, empleo="monotributista", rechazos_12_meses=0, garantia_prendaria=False)),
    ],
)

DESTINOS_FIJOS = ["auto", "moto", "electrodomesticos", "refaccion", "estudios"]
rule(
    1, "destino-prestamo", "CRE-C1-DESTINO",
    "Determinar si el destino y el monto de un préstamo están permitidos. Los destinos admitidos son \"auto\", "
    "\"moto\", \"electrodomesticos\", \"refaccion\", \"estudios\" y \"libre\"; cualquier otro destino, como "
    "\"viaje\" o \"apuestas\", no se admite. Además, cada destino tiene un monto máximo: 30000000 pesos para auto; "
    "8000000 para moto y para refaccion; 3000000 para electrodomesticos y para estudios; y 2000000 para libre. El "
    "préstamo está permitido si el destino se admite y el monto no supera su máximo.",
    {"destino": "String", "monto": "Int"},
    op("AND", in_(var("destino"), DESTINOS_FIJOS + ["libre"]),
       op("<=", var("monto"),
          ite(eq("destino", "auto"), lit(30000000),
              ite(in_(var("destino"), ["moto", "refaccion"]), lit(8000000),
                  ite(in_(var("destino"), ["electrodomesticos", "estudios"]), lit(3000000), lit(2000000)))))),
    "MAXIMOS = {'auto': 30000000, 'moto': 8000000, 'refaccion': 8000000,\n"
    "           'electrodomesticos': 3000000, 'estudios': 3000000, 'libre': 2000000}\n\n"
    "def evaluate_rule(data):\n"
    "    maximo = MAXIMOS.get(data['destino'])\n"
    "    return maximo is not None and data['monto'] <= maximo\n",
    [
        ("V1-AUTO-TOPE", env(destino="auto", monto=30000000)),
        ("V2-AUTO-EXCEDE", env(destino="auto", monto=30000001)),
        ("V3-MOTO", env(destino="moto", monto=5000000)),
        ("V4-REFACCION-EXCEDE", env(destino="refaccion", monto=9000000)),
        ("V5-ESTUDIOS-TOPE", env(destino="estudios", monto=3000000)),
        ("V6-LIBRE-EXCEDE", env(destino="libre", monto=2500000)),
        ("V7-VIAJE", env(destino="viaje", monto=100000)),
        ("V8-ELECTRO", env(destino="electrodomesticos", monto=1500000)),
    ],
)

# ===================================== Categoría 2 =====================================

rule(
    2, "cuota-tasa-cero", "CRE-C2-CUOTA",
    "Calcular la cuota mensual de una compra en cuotas sin interés, en pesos con centavos. Se suma al monto de la "
    "compra (con centavos) una comisión fija de otorgamiento (en pesos enteros) y el total se divide por la "
    "cantidad de cuotas. El resultado es exacto, sin redondear. La tasa de interés es cero, así que no interviene "
    "en la cuenta.",
    {"comision": "Int", "cuotas": "Int", "monto": "Decimal"},
    op("/", op("+", var("monto"), var("comision")), var("cuotas")),
    "def evaluate_rule(data):\n"
    "    return (data['monto'] + data['comision']) / data['cuotas']\n",
    [
        ("V1-TRES-CUOTAS", env(monto=299999.5, comision=500, cuotas=3)),
        ("V2-DOCE-CUOTAS", env(monto=1200000.75, comision=0, cuotas=12)),
        ("V3-UNA-CUOTA", env(monto=15000.5, comision=250, cuotas=1)),
        ("V4-SEIS-CUOTAS", env(monto=60000.25, comision=1000, cuotas=6)),
        ("V5-DIVISION-EXACTA", env(monto=99999.5, comision=0, cuotas=2)),
        ("V6-DIECIOCHO", env(monto=500000.5, comision=1500, cuotas=18)),
    ],
)

rule(
    2, "interes-punitorio", "CRE-C2-PUNITORIO",
    "Calcular el interés punitorio de una cuota vencida, en pesos con centavos. Es el saldo impago (con centavos) "
    "por una tasa diaria de 0.0005 por la cantidad de días de atraso (entero). Si los días de atraso son 0 o menos, "
    "el punitorio es 0.0. La categoría de riesgo del cliente no modifica la tasa.",
    {"dias_atraso": "Int", "saldo": "Decimal"},
    ite(op(">", var("dias_atraso"), lit(0)), op("*", op("*", var("saldo"), dec("0.0005")), var("dias_atraso")), dec("0")),
    "from decimal import Decimal\n\n"
    "def evaluate_rule(data):\n"
    "    if data['dias_atraso'] <= 0:\n"
    "        return Decimal('0')\n"
    "    return data['saldo'] * Decimal('0.0005') * data['dias_atraso']\n",
    [
        ("V1-DIEZ-DIAS", env(saldo=100000.5, dias_atraso=10)),
        ("V2-SIN-ATRASO", env(saldo=100000.5, dias_atraso=0)),
        ("V3-ADELANTADO", env(saldo=50000.25, dias_atraso=-3)),
        ("V4-UN-DIA", env(saldo=20000.5, dias_atraso=1)),
        ("V5-TREINTA-DIAS", env(saldo=250000.75, dias_atraso=30)),
        ("V6-CENTAVOS", env(saldo=999.99, dias_atraso=7)),
    ],
)

multiplicador = ite(eq("categoria", "premium"), lit(4), ite(eq("categoria", "estandar"), lit(2), lit(1)))
limite = op("*", var("ingreso"), multiplicador)
rule(
    2, "limite-tarjeta", "CRE-C2-LIMITE",
    "Calcular el límite de compra de una tarjeta, en pesos con centavos. Es el ingreso mensual (con centavos) por un "
    "multiplicador según la categoría del cliente: 4 para \"premium\", 2 para \"estandar\" y 1 para \"inicial\". El "
    "límite nunca supera 5000000.00 pesos: si la cuenta da más, el límite es 5000000.00. El puntaje crediticio ya "
    "está reflejado en la categoría.",
    {"categoria": "String", "ingreso": "Decimal"},
    ite(op(">", limite, lit(5000000)), dec("5000000.00"), limite),
    "from decimal import Decimal\n\n"
    "MULTIPLICADOR = {'premium': 4, 'estandar': 2}\n\n"
    "def evaluate_rule(data):\n"
    "    limite = data['ingreso'] * MULTIPLICADOR.get(data['categoria'], 1)\n"
    "    return min(limite, Decimal('5000000.00'))\n",
    [
        ("V1-PREMIUM", env(categoria="premium", ingreso=800000.5)),
        ("V2-PREMIUM-TOPE", env(categoria="premium", ingreso=1250000.25)),
        ("V3-ESTANDAR", env(categoria="estandar", ingreso=650000.75)),
        ("V4-INICIAL", env(categoria="inicial", ingreso=400000.5)),
        ("V5-ESTANDAR-TOPE", env(categoria="estandar", ingreso=2600000.5)),
        ("V6-JUSTO-DEBAJO", env(categoria="premium", ingreso=1249999.75)),
    ],
)

rule(
    2, "puntaje-ajustado", "CRE-C2-PUNTAJE",
    "Calcular el puntaje crediticio ajustado de un cliente, como entero. Se parte del puntaje del buró, se suman 20 "
    "puntos si tiene una hipoteca al día, se suman 10 puntos por cada año como cliente del banco (hasta 5 años: más "
    "de 5 años suman lo mismo que 5) y se restan 50 puntos por cada deuda en mora. El nivel de riesgo del cliente se "
    "calcula después, a partir de este puntaje, y no interviene acá.",
    {"anios_cliente": "Int", "deudas_en_mora": "Int", "hipoteca_al_dia": "Bool", "puntaje_buro": "Int"},
    op("-",
       op("+", op("+", var("puntaje_buro"), ite(var("hipoteca_al_dia"), lit(20), lit(0))),
          op("*", ite(op(">", var("anios_cliente"), lit(5)), lit(5), var("anios_cliente")), lit(10))),
       op("*", var("deudas_en_mora"), lit(50))),
    "def evaluate_rule(data):\n"
    "    puntaje = data['puntaje_buro']\n"
    "    if data['hipoteca_al_dia']:\n"
    "        puntaje += 20\n"
    "    puntaje += min(data['anios_cliente'], 5) * 10\n"
    "    return puntaje - data['deudas_en_mora'] * 50\n",
    [
        ("V1-BASE", env(puntaje_buro=650, hipoteca_al_dia=False, anios_cliente=0, deudas_en_mora=0)),
        ("V2-HIPOTECA", env(puntaje_buro=650, hipoteca_al_dia=True, anios_cliente=0, deudas_en_mora=0)),
        ("V3-CINCO-ANIOS", env(puntaje_buro=650, hipoteca_al_dia=False, anios_cliente=5, deudas_en_mora=0)),
        ("V4-DIEZ-ANIOS", env(puntaje_buro=650, hipoteca_al_dia=False, anios_cliente=10, deudas_en_mora=0)),
        ("V5-MORAS", env(puntaje_buro=700, hipoteca_al_dia=True, anios_cliente=3, deudas_en_mora=2)),
        ("V6-TODO", env(puntaje_buro=580, hipoteca_al_dia=True, anios_cliente=7, deudas_en_mora=1)),
    ],
)

relacion = op("/", var("cuota"), var("ingreso"))
rule(
    2, "relacion-cuota-ingreso", "CRE-C2-RELACION",
    "Calificar la relación entre la cuota de un préstamo y el ingreso mensual del solicitante, ambos en pesos con "
    "centavos. La relación es cuota / ingreso. Si la relación es 0.30 o menos, la calificación es \"Holgada\"; si es "
    "mayor que 0.30 pero no supera 0.40, es \"Ajustada\"; si supera 0.40, es \"Excesiva\". La respuesta es solo la "
    "palabra de la calificación, no el número.",
    {"cuota": "Decimal", "ingreso": "Decimal"},
    ite(op("<=", relacion, dec("0.30")), S("Holgada"), ite(op("<=", relacion, dec("0.40")), S("Ajustada"), S("Excesiva"))),
    "from decimal import Decimal\n\n"
    "def evaluate_rule(data):\n"
    "    relacion = data['cuota'] / data['ingreso']\n"
    "    if relacion <= Decimal('0.30'):\n"
    "        return 'Holgada'\n"
    "    if relacion <= Decimal('0.40'):\n"
    "        return 'Ajustada'\n"
    "    return 'Excesiva'\n",
    [
        ("V1-HOLGADA", env(cuota=100000.5, ingreso=500000.5)),
        ("V2-EXACTO-030", env(cuota=150000.15, ingreso=500000.5)),
        ("V3-AJUSTADA", env(cuota=175000.5, ingreso=500000.5)),
        ("V4-EXACTO-040", env(cuota=200000.2, ingreso=500000.5)),
        ("V5-EXCESIVA", env(cuota=200000.25, ingreso=500000.5)),
        ("V6-MUY-ALTA", env(cuota=400000.5, ingreso=500000.5)),
    ],
)

cinco = op("*", var("saldo"), dec("0.05"))
rule(
    2, "pago-minimo", "CRE-C2-PAGO-MINIMO",
    "Calcular el pago mínimo del resumen de una tarjeta, en pesos con centavos. Es el 5 % del saldo, pero nunca "
    "menos de 500.00 pesos. La excepción: si el saldo total es menor que 500.00, el pago mínimo es el saldo completo. "
    "El resultado siempre tiene centavos; no se redondea.",
    {"saldo": "Decimal"},
    ite(op("<", var("saldo"), dec("500.00")), var("saldo"), ite(op(">", cinco, lit(500)), cinco, dec("500.00"))),
    "from decimal import Decimal\n\n"
    "def evaluate_rule(data):\n"
    "    saldo = data['saldo']\n"
    "    if saldo < Decimal('500.00'):\n"
    "        return saldo\n"
    "    return max(saldo * Decimal('0.05'), Decimal('500.00'))\n",
    [
        ("V1-SALDO-CHICO", env(saldo=320.5)),
        ("V2-MINIMO-FIJO", env(saldo=6000.5)),
        ("V3-CINCO-POR-CIENTO", env(saldo=25000.5)),
        ("V4-JUSTO-10000", env(saldo=10000.2)),
        ("V5-JUSTO-DEBAJO", env(saldo=9999.9)),
        ("V6-SALDO-500", env(saldo=500.5)),
    ],
)

# ===================================== Categoría 3 =====================================

rule(
    3, "cliente-en-mora", "CRE-C3-MORA",
    "Determinar si un cliente está en mora. Está en mora si tiene una cuota impaga con más de 30 días de atraso. "
    "Con exactamente 30 días todavía no está en mora. La excepción: si tiene un plan de pagos vigente, no está en "
    "mora aunque tenga más de 30 días de atraso.",
    {"dias_atraso": "Int", "plan_de_pagos": "Bool"},
    op("AND", op(">", var("dias_atraso"), lit(30)), not_(var("plan_de_pagos"))),
    "def evaluate_rule(data):\n"
    "    return data['dias_atraso'] > 30 and not data['plan_de_pagos']\n",
    [
        ("V1-30-DIAS", env(dias_atraso=30, plan_de_pagos=False)),
        ("V2-31-DIAS", env(dias_atraso=31, plan_de_pagos=False)),
        ("V3-PLAN-VIGENTE", env(dias_atraso=90, plan_de_pagos=True)),
        ("V4-AL-DIA", env(dias_atraso=0, plan_de_pagos=False)),
        ("V5-90-DIAS", env(dias_atraso=90, plan_de_pagos=False)),
        ("V6-PLAN-Y-AL-DIA", env(dias_atraso=5, plan_de_pagos=True)),
        ("V7-45-DIAS", env(dias_atraso=45, plan_de_pagos=False)),
        ("V8-120-DIAS", env(dias_atraso=120, plan_de_pagos=False)),
    ],
)

rule(
    3, "refinanciacion", "CRE-C3-REFINANCIACION",
    "Determinar si un cliente puede refinanciar su deuda. Puede, salvo en dos casos: si ya refinanció en los "
    "últimos 12 meses (es decir, si su última refinanciación fue hace menos de 12 meses), o si tiene una causa "
    "judicial abierta con el banco. Un cliente que nunca refinanció se informa con 999 meses desde la última "
    "refinanciación.",
    {"causa_judicial": "Bool", "meses_desde_refinanciacion": "Int"},
    not_(op("OR", op("<", var("meses_desde_refinanciacion"), lit(12)), var("causa_judicial"))),
    "def evaluate_rule(data):\n"
    "    return not (data['meses_desde_refinanciacion'] < 12 or data['causa_judicial'])\n",
    [
        ("V1-NUNCA", env(meses_desde_refinanciacion=999, causa_judicial=False)),
        ("V2-HACE-11", env(meses_desde_refinanciacion=11, causa_judicial=False)),
        ("V3-HACE-12", env(meses_desde_refinanciacion=12, causa_judicial=False)),
        ("V4-JUDICIAL", env(meses_desde_refinanciacion=999, causa_judicial=True)),
        ("V5-JUDICIAL-Y-RECIENTE", env(meses_desde_refinanciacion=3, causa_judicial=True)),
        ("V6-HACE-DOS-ANIOS", env(meses_desde_refinanciacion=24, causa_judicial=False)),
    ],
)

rule(
    3, "bonificacion-tasa", "CRE-C3-BONIFICACION",
    "Determinar si un préstamo recibe bonificación de tasa. La recibe el cliente que tiene el sueldo acreditado en "
    "el banco y, además, cumple al menos una de estas dos: contrató el seguro de vida del banco o adhirió el pago de "
    "las cuotas al débito automático. Sin sueldo acreditado no hay bonificación, aunque tenga el seguro y el débito.",
    {"debito_automatico": "Bool", "seguro_de_vida": "Bool", "sueldo_acreditado": "Bool"},
    op("AND", var("sueldo_acreditado"), op("OR", var("seguro_de_vida"), var("debito_automatico"))),
    "def evaluate_rule(data):\n"
    "    return data['sueldo_acreditado'] and (data['seguro_de_vida'] or data['debito_automatico'])\n",
    [
        ("V1-SUELDO-Y-SEGURO", env(sueldo_acreditado=True, seguro_de_vida=True, debito_automatico=False)),
        ("V2-SUELDO-Y-DEBITO", env(sueldo_acreditado=True, seguro_de_vida=False, debito_automatico=True)),
        ("V3-SOLO-SUELDO", env(sueldo_acreditado=True, seguro_de_vida=False, debito_automatico=False)),
        ("V4-SIN-SUELDO-CON-TODO", env(sueldo_acreditado=False, seguro_de_vida=True, debito_automatico=True)),
        ("V5-SIN-SUELDO-CON-DEBITO", env(sueldo_acreditado=False, seguro_de_vida=False, debito_automatico=True)),
        ("V6-TODO", env(sueldo_acreditado=True, seguro_de_vida=True, debito_automatico=True)),
    ],
)

rule(
    3, "condonacion-intereses", "CRE-C3-CONDONACION",
    "Determinar si se le condonan los intereses del mes a un cliente con tarjeta. Se le condonan si paga el total "
    "del resumen hasta el día 10 del mes, inclusive. Si paga el día 11 o después, o si paga menos que el total, no "
    "hay condonación. El día de pago va de 1 a 31.",
    {"dia_de_pago": "Int", "pago_total": "Bool"},
    op("AND", var("pago_total"), op("<=", var("dia_de_pago"), lit(10))),
    "def evaluate_rule(data):\n"
    "    return data['pago_total'] and data['dia_de_pago'] <= 10\n",
    [
        ("V1-DIA-10", env(dia_de_pago=10, pago_total=True)),
        ("V2-DIA-11", env(dia_de_pago=11, pago_total=True)),
        ("V3-PAGO-PARCIAL", env(dia_de_pago=5, pago_total=False)),
        ("V4-DIA-1", env(dia_de_pago=1, pago_total=True)),
        ("V5-TARDE-Y-PARCIAL", env(dia_de_pago=25, pago_total=False)),
        ("V6-DIA-9", env(dia_de_pago=9, pago_total=True)),
    ],
)

rule(
    3, "bloqueo-tarjeta", "CRE-C3-BLOQUEO",
    "Determinar si se bloquea una tarjeta por seguridad. Se bloquea si hubo 3 o más intentos fallidos de PIN en el "
    "día, o si se intenta una compra en un país distinto del habitual y el cliente no avisó que viajaba. Una compra "
    "en otro país con aviso de viaje no provoca bloqueo.",
    {"aviso_de_viaje": "Bool", "compra_en_otro_pais": "Bool", "intentos_fallidos": "Int"},
    op("OR", op(">=", var("intentos_fallidos"), lit(3)),
       op("AND", var("compra_en_otro_pais"), not_(var("aviso_de_viaje")))),
    "def evaluate_rule(data):\n"
    "    return data['intentos_fallidos'] >= 3 or (data['compra_en_otro_pais'] and not data['aviso_de_viaje'])\n",
    [
        ("V1-TRES-INTENTOS", env(intentos_fallidos=3, compra_en_otro_pais=False, aviso_de_viaje=False)),
        ("V2-DOS-INTENTOS", env(intentos_fallidos=2, compra_en_otro_pais=False, aviso_de_viaje=False)),
        ("V3-EXTERIOR-SIN-AVISO", env(intentos_fallidos=0, compra_en_otro_pais=True, aviso_de_viaje=False)),
        ("V4-EXTERIOR-CON-AVISO", env(intentos_fallidos=0, compra_en_otro_pais=True, aviso_de_viaje=True)),
        ("V5-AVISO-Y-INTENTOS", env(intentos_fallidos=4, compra_en_otro_pais=True, aviso_de_viaje=True)),
        ("V6-NORMAL", env(intentos_fallidos=1, compra_en_otro_pais=False, aviso_de_viaje=True)),
    ],
)

rule(
    3, "tope-por-ingresos", "CRE-C3-TOPE",
    "Determinar si el monto de un préstamo está dentro del tope. El monto no puede superar el 30 % de los ingresos "
    "anuales del solicitante (ingreso mensual por 12). La excepción: con garantía hipotecaria, el tope no se aplica "
    "y el monto siempre está dentro.",
    {"garantia_hipotecaria": "Bool", "ingreso_mensual": "Int", "monto": "Int"},
    op("OR", var("garantia_hipotecaria"),
       op("<=", var("monto"), op("*", op("*", var("ingreso_mensual"), lit(12)), dec("0.3")))),
    "from decimal import Decimal\n\n"
    "def evaluate_rule(data):\n"
    "    if data['garantia_hipotecaria']:\n"
    "        return True\n"
    "    return data['monto'] <= data['ingreso_mensual'] * 12 * Decimal('0.3')\n",
    [
        ("V1-EN-EL-TOPE", env(monto=1800000, ingreso_mensual=500000, garantia_hipotecaria=False)),
        ("V2-UN-PESO-DE-MAS", env(monto=1800001, ingreso_mensual=500000, garantia_hipotecaria=False)),
        ("V3-HIPOTECARIA", env(monto=50000000, ingreso_mensual=500000, garantia_hipotecaria=True)),
        ("V4-CHICO", env(monto=100000, ingreso_mensual=500000, garantia_hipotecaria=False)),
        ("V5-MENSUAL-POR-ERROR", env(monto=2000000, ingreso_mensual=500000, garantia_hipotecaria=False)),
        ("V6-HIPOTECARIA-CHICO", env(monto=10, ingreso_mensual=100, garantia_hipotecaria=True)),
        ("V7-SUPERA", env(monto=3000000, ingreso_mensual=800000, garantia_hipotecaria=False)),
        ("V8-SUPERA-CHICO", env(monto=1000, ingreso_mensual=200, garantia_hipotecaria=False)),
    ],
)
print("ok")
