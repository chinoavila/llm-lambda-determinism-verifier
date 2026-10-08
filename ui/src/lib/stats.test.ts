/** Pruebas de las estadísticas de una corrida (specs/ui.md §Estadísticas). */
import { describe, expect, it } from "vitest";
import type { RecordRow, Rule } from "../api";
import { blankRule } from "./rules";
import {
  blockedStages,
  durationByGroup,
  errorsByGroup,
  fmtRate,
  generations,
  median,
  OUTSIDE_CORPUS,
  outcomesByGroup,
  passBy,
  passByGroup,
  rowMatches,
} from "./stats";

const row = (over: Partial<RecordRow>): RecordRow => ({
  run_id: "r",
  case_id: "c1",
  group: "treatment",
  repetition: 1,
  scenario_id: "S1",
  model: "m",
  timestamp: "2026-10-07T00:00:00Z",
  llm_raw: "{}",
  outcome: "executed",
  stage: "execution",
  result: { type: "Bool", value: true },
  error: null,
  duration_ms: 10,
  expected: { type: "Bool", value: true },
  ...over,
});
const blocked = (over: Partial<RecordRow>) =>
  row({ outcome: "blocked", stage: "typecheck", result: null, error: { code: "OPERAND_MISMATCH", message: "x" }, ...over });

describe("rowMatches", () => {
  it("exige mismo tipo y mismo valor", () => {
    expect(rowMatches(row({}))).toBe(true);
    expect(rowMatches(row({ result: { type: "Decimal", value: "1500.5" }, expected: { type: "Decimal", value: "1500.5" } }))).toBe(true);
    expect(rowMatches(row({ result: { type: "Int", value: 5 }, expected: { type: "Decimal", value: "5" } }))).toBe(false);
    expect(rowMatches(row({ result: { type: "Bool", value: false } }))).toBe(false);
  });

  it("no acierta si no ejecutó o falta expected", () => {
    expect(rowMatches(blocked({}))).toBe(false);
    expect(rowMatches(row({ expected: null }))).toBe(false);
  });
});

describe("generations y pass@1", () => {
  it("una generación pasa solo si aciertan todos sus escenarios", () => {
    const gens = generations([
      row({ scenario_id: "S1" }),
      row({ scenario_id: "S2" }),
      row({ repetition: 2, scenario_id: "S1" }),
      row({ repetition: 2, scenario_id: "S2", result: { type: "Bool", value: false } }),
    ]);
    expect(gens.map((g) => [g.repetition, g.rows.length, g.status])).toEqual([
      [1, 2, "pass"],
      [2, 2, "fail"],
    ]);
    expect(passByGroup(gens).treatment).toEqual({ pass: 1, fail: 1, noExpected: 0, rate: 0.5 });
  });

  it("deja las generaciones sin expected fuera del denominador", () => {
    const gens = generations([row({}), row({ case_id: "fx", expected: null }), blocked({ group: "baseline2" })]);
    const p = passByGroup(gens);
    expect(p.treatment).toEqual({ pass: 1, fail: 0, noExpected: 1, rate: 1 });
    expect(p.baseline2.rate).toBe(0);
    expect(p.baseline1.rate).toBeNull();
  });
});

describe("passBy", () => {
  const rules = new Map<string, Rule>([["c1", { ...blankRule(), case_id: "c1", category: 3, domain: "crédito" }]]);
  const gens = generations([row({}), row({ case_id: "fx", expected: null })]);

  it("desglosa por categoría y dominio, con lo que no está en el corpus al final", () => {
    expect(passBy(gens, "category", rules).map((r) => r.label)).toEqual(["Cat. 3 · lógica", OUTSIDE_CORPUS]);
    expect(passBy(gens, "domain", rules).map((r) => r.label)).toEqual(["crédito", OUTSIDE_CORPUS]);
    expect(passBy(gens, "rule", rules).map((r) => r.label)).toEqual(["c1", "fx"]);
  });
});

describe("conteos por renglón", () => {
  const rows = [
    blocked({ scenario_id: "S1" }),
    blocked({ scenario_id: "S2" }),
    row({ group: "baseline1", outcome: "runtime_error", stage: "execution", result: null, error: { code: "ZeroDivisionError", message: "x" } }),
  ];

  it("cuenta cada escenario de un bloqueo", () => {
    expect(outcomesByGroup(rows).treatment.blocked).toBe(2);
    expect(outcomesByGroup(rows).baseline1.runtime_error).toBe(1);
    expect(blockedStages(rows)).toEqual([{ key: "typecheck", byGroup: { treatment: 2, baseline1: 0, baseline2: 0 }, total: 2 }]);
  });

  it("ordena los códigos de error de mayor a menor", () => {
    expect(errorsByGroup(rows).map((e) => [e.key, e.total])).toEqual([
      ["OPERAND_MISMATCH", 2],
      ["ZeroDivisionError", 1],
    ]);
  });
});

describe("duración", () => {
  it("calcula media y mediana sin los nulos", () => {
    expect(median([4, 1, 3, 2])).toBe(2.5);
    expect(median([])).toBeNull();
    const d = durationByGroup([row({ duration_ms: 10 }), row({ duration_ms: 30 }), row({ duration_ms: null })]);
    expect(d.treatment).toEqual({ n: 2, mean: 20, median: 20 });
    expect(d.baseline1).toEqual({ n: 0, mean: null, median: null });
  });
});

describe("fmtRate", () => {
  it("escribe el porcentaje con coma decimal", () => {
    expect(fmtRate(0.5)).toBe("50,0 %");
    expect(fmtRate(null)).toBe("—");
  });
});
