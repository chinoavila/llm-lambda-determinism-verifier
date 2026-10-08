import { describe, expect, it } from "vitest";
import type { Rule } from "../api";
import { blindCompare, blindSummary, canonicalDecimal, parseAnswer } from "./review";
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
