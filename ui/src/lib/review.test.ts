import { describe, expect, it } from "vitest";
import type { Rule } from "../api";
import { blindCompare, blindSummary, canonicalDecimal, parseAnswer, scenarioCoverage, thresholds } from "./review";
import { blankRule } from "./rules";

const rule: Rule = {
  ...blankRule(),
  scenarios: [
    { scenario_id: "S1", env: {}, expected: { type: "Decimal", value: "1500.5" } },
    { scenario_id: "S2", env: {}, expected: { type: "Bool", value: true } },
    { scenario_id: "S3", env: {}, expected: { type: "Int", value: 3 } },
    { scenario_id: "S4", env: {} },
  ],
};

describe("revisión a ciegas", () => {
  it("normaliza decimales como el contrato", () => {
    expect(canonicalDecimal("1500.50")).toBe("1500.5");
    expect(canonicalDecimal("+007.0")).toBe("7");
    expect(canonicalDecimal("-0.00")).toBe("0");
    expect(parseAnswer("2.10", "Decimal")).toEqual({ type: "Decimal", value: "2.1" });
    expect(parseAnswer("true", "Bool")).toEqual({ type: "Bool", value: true });
    expect(parseAnswer("", "Int")).toBeUndefined();
  });

  it("compara con el tipo del expected y resume las diferencias", () => {
    const rows = blindCompare(rule, { S1: "1500.50", S2: "false", S3: "3", S4: "1" });
    expect(rows.map((r) => r.match)).toEqual([true, false, true, null]);
    expect(blindSummary(rows)).toBe(
      ["Revisión a ciegas: 2 de 4 escenarios coinciden con el expected.", "- S2: expected Bool true, revisor Bool false", "1 sin respuesta o sin expected."].join("\n"),
    );
  });
});

describe("scenarioCoverage", () => {
  const lit = (value: unknown, value_type = "Int") => ({ type: "Literal", value, value_type });
  const v = (name: string) => ({ type: "Var", name });
  const expr = {
    type: "BinaryOp",
    op: "AND",
    left: { type: "BinaryOp", op: ">=", left: v("score"), right: lit(700) },
    right: { type: "BinaryOp", op: "<", left: lit("0.4", "Decimal"), right: v("ratio") },
  };
  const base: Rule = { ...blankRule(), canonical_ast: { expr } };

  it("encuentra los umbrales Var op Literal", () => {
    expect(thresholds(expr)).toEqual([
      { name: "score", op: ">=", value: 700 },
      { name: "ratio", op: "<", value: 0.4 },
    ]);
  });

  it("marca umbrales sin escenario en el borde y esperados todos iguales", () => {
    const same = { type: "Bool" as const, value: true };
    const rule: Rule = {
      ...base,
      scenarios: [
        { scenario_id: "A", env: { score: 700, ratio: "0.5" }, expected: same },
        { scenario_id: "B", env: { score: 800, ratio: "0.9" }, expected: same },
      ],
    };
    expect(scenarioCoverage(rule)).toEqual({ sameExpected: true, missingBorders: ["ratio < 0.4"] });
    const varied: Rule = {
      ...rule,
      scenarios: [...rule.scenarios, { scenario_id: "C", env: { score: 1, ratio: "0.40" }, expected: { type: "Bool", value: false } }],
    };
    expect(scenarioCoverage(varied)).toEqual({ sameExpected: false, missingBorders: [] });
  });
});
