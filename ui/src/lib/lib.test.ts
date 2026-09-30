/** Pruebas de renderizado del AST y validación/conversión de campos de reglas. */
import { describe, expect, it } from "vitest";
import type { AstNode, Rule } from "../api";
import { render } from "./ast";
import { blankRule, parseCell, parseExpected, validate, valueFits } from "./rules";

const v = (name: string): AstNode => ({ type: "Var", name });
const lit = (value: unknown, value_type: string): AstNode => ({ type: "Literal", value, value_type });
const bin = (op: string, left: AstNode, right: AstNode): AstNode => ({ type: "BinaryOp", op, left, right });

describe("render", () => {
  it("escribe expresiones cortas en una línea, con paréntesis solo donde hacen falta", () => {
    expect(render(bin("AND", bin(">=", v("edad"), lit(25, "Int")), bin("OR", v("a"), v("b"))))).toBe(
      "edad >= 25 AND (a OR b)",
    );
  });

  it("encadena IF / ELSE IF en columna", () => {
    const expr: AstNode = {
      type: "IfThenElse",
      condition: bin("<", v("s"), lit(600, "Int")),
      then: lit("Alto", "String"),
      else: { type: "IfThenElse", condition: bin("<", v("s"), lit(700, "Int")), then: lit("Medio", "String"), else: lit("Bajo", "String") },
    };
    expect(render(expr)).toBe(
      ["IF s < 600", "THEN", '  "Alto"', "ELSE IF s < 700", "THEN", '  "Medio"', "ELSE", '  "Bajo"'].join("\n"),
    );
  });

  it("parte cadenas largas de AND con un operando por línea", () => {
    const long = ["tiene_ssn_valido", "no_es_dependiente_de_otro", "vivio_en_eeuu_mas_de_medio_anio"].map(v);
    const expr = bin("AND", bin("AND", long[0]!, long[1]!), long[2]!);
    expect(render(expr).split("\n")).toEqual([
      "    tiene_ssn_valido",
      "AND no_es_dependiente_de_otro",
      "AND vivio_en_eeuu_mas_de_medio_anio",
    ]);
  });

  it("marca con ? lo que no es un nodo", () => {
    expect(render(null)).toBe("?");
  });
});

describe("valores del formulario", () => {
  it("valueFits distingue Int de Decimal como el engine", () => {
    expect(valueFits("Int", 1500)).toBe(true);
    expect(valueFits("Decimal", 1500)).toBe(false);
    expect(valueFits("Decimal", 1500.5)).toBe(true);
    expect(valueFits("Bool", "true")).toBe(false);
  });

  it("parseCell acepta coma decimal y deja el texto si no es número", () => {
    expect(parseCell("Decimal", "1500,5")).toBe(1500.5);
    expect(parseCell("Int", "abc")).toBe("abc");
    expect(parseCell("Bool", "true")).toBe(true);
  });

  it("parseExpected deduce el tipo o respeta el anterior", () => {
    expect(parseExpected("")).toBeUndefined();
    expect(parseExpected("false")).toEqual({ type: "Bool", value: false });
    expect(parseExpected("12")).toEqual({ type: "Int", value: 12 });
    expect(parseExpected("0.30")).toEqual({ type: "Decimal", value: "0.30" });
    expect(parseExpected("12", { type: "String", value: "x" })).toEqual({ type: "String", value: "12" });
  });
});

describe("validate", () => {
  const valid = (): Rule => ({ ...blankRule(), case_id: "FIS-C2-X", domain: "fiscal", description: "Una regla." });

  it("acepta una regla completa", () => {
    expect(validate(valid(), true, new Set(), null)).toEqual({});
  });

  it("agrupa los errores por pestaña", () => {
    const r = valid();
    r.case_id = "con espacios";
    r.source = { kind: "adapted" };
    r.gamma = { monto: "Decimal" };
    r.scenarios = [{ scenario_id: "S1", env: { monto: 1500 } }];
    r.canonical_python = "return 1";
    const errs = validate(r, true, new Set(), "JSON inválido");
    expect(Object.keys(errs).sort()).toEqual(["ast", "escenarios", "general", "python"]);
    expect(errs.escenarios).toContain("S1: monto debe ser Decimal con parte decimal (1500.5, no 1500).");
  });

  it("rechaza un id repetido solo al crear", () => {
    expect(validate(valid(), true, new Set(["FIS-C2-X"]), null).general).toEqual(["Ya existe una regla con ese id."]);
    expect(validate(valid(), false, new Set(["FIS-C2-X"]), null)).toEqual({});
  });
});
