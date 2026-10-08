/** Pruebas de las estadísticas de una corrida (specs/ui.md §Estadísticas). */
import { describe, expect, it } from "vitest";
import type { RecordRow, Rule } from "../api";
import { blankRule } from "./rules";
import {
  blockedStages,
  consistency,
  kValues,
  layersByCategory,
  passAtK,
  passAtKOne,
  runConditions,
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
    expect(passByGroup(gens).treatment).toEqual({ pass: 1, fail: 1, noExpected: 0, pending: 0, rate: 0.5 });
  });

  it("deja las generaciones sin expected fuera del denominador", () => {
    const gens = generations([row({}), row({ case_id: "fx", expected: null }), blocked({ group: "baseline2" })]);
    const p = passByGroup(gens);
    expect(p.treatment).toEqual({ pass: 1, fail: 0, noExpected: 1, pending: 0, rate: 1 });
    expect(p.baseline2.rate).toBe(0);
    expect(p.baseline1.rate).toBeNull();
  });

  it("las llamadas cortadas por cuota o red quedan pendientes, no son fallas del modelo", () => {
    const llmError = (code: string, group: RecordRow["group"]) =>
      row({ group, outcome: "llm_error", stage: "llm", result: null, error: { code, message: "" } });
    const gens = generations([row({}), { ...llmError("quota_exhausted", "treatment"), repetition: 2 }]);
    expect(gens.map((g) => g.status)).toEqual(["pass", "pending"]);
    expect(passByGroup(gens).treatment).toEqual({ pass: 1, fail: 0, noExpected: 0, pending: 1, rate: 1 });
    const failed = generations([llmError("generation_failed", "baseline1"), llmError("transport_error", "baseline2")]);
    expect(failed.map((g) => g.status)).toEqual(["fail", "pending"]);
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

describe("repeticiones", () => {
  // c1: pasa 1 de 3; c2: pasa 3 de 3; c3: una sola repetición, que falla.
  const wrong = { result: { type: "Bool" as const, value: false } };
  const gens = generations([
    row({ repetition: 1 }),
    row({ repetition: 2, ...wrong }),
    row({ repetition: 3, ...wrong }),
    row({ case_id: "c2", repetition: 1 }),
    row({ case_id: "c2", repetition: 2 }),
    row({ case_id: "c2", repetition: 3 }),
    row({ case_id: "c3", ...wrong }),
  ]);

  it("pass@k con el estimador insesgado, solo sobre reglas con k generaciones", () => {
    expect(passAtKOne(3, 1, 1)).toBeCloseTo(1 / 3);
    expect(passAtKOne(3, 1, 2)).toBeCloseTo(2 / 3);
    expect(passAtKOne(5, 0, 3)).toBe(0);
    expect(passAtKOne(5, 3, 3)).toBe(1);
    const [k1, k3] = passAtK(gens, [1, 3]);
    expect(k1!.byGroup.treatment).toEqual({ rate: (1 / 3 + 1 + 0) / 3, cases: 3 });
    expect(k3!.byGroup.treatment).toEqual({ rate: 1, cases: 2 });
    expect(k1!.byGroup.baseline1).toEqual({ rate: null, cases: 0 });
    expect(kValues(5)).toEqual([1, 2, 3, 5]);
  });

  it("una regla es inestable si sus repeticiones pasan y fallan", () => {
    expect(consistency(gens).treatment).toEqual({ cases: 2, stable: 1, unstable: ["c1"] });
  });
});

describe("runConditions", () => {
  it("lee temperatura y tokens una vez por generación", () => {
    const params = { model: "m", temperature: 0 };
    const gens = generations([
      row({ request_params: params, usage: { total_tokens: 100 } }),
      row({ scenario_id: "S2", request_params: params, usage: { total_tokens: 100 } }),
      row({ group: "baseline1", request_params: params, usage: { total_tokens: 300 } }),
      row({ group: "baseline2", request_params: params, usage: null }),
    ]);
    expect(runConditions(gens)).toEqual({
      models: ["m"],
      temperatures: ["0"],
      repetitions: 1,
      generations: 3,
      withUsage: 2,
      totalTokens: 400,
      tokensPerCall: 200,
    });
  });

  it("distingue un registro 2.0 de una temperatura que no se envió", () => {
    const gens = generations([row({}), row({ case_id: "c2", request_params: { model: "m" }, usage: null })]);
    expect(runConditions(gens)).toMatchObject({ temperatures: ["del proveedor", "no registrada"], tokensPerCall: null });
  });
});

describe("layersByCategory", () => {
  it("separa lo que bloquea el motor de lo que solo detectan los escenarios", () => {
    const rules = new Map<string, Rule>([["c1", { ...blankRule(), case_id: "c1", category: 3 }]]);
    const gens = generations([
      row({ repetition: 1 }),
      row({ repetition: 2, result: { type: "Bool", value: false } }),
      blocked({ repetition: 3 }),
      row({ repetition: 4, outcome: "runtime_error", result: null, error: { code: "x", message: "" } }),
      row({ repetition: 5, outcome: "llm_error", stage: "llm", result: null, error: { code: "generation_failed", message: "" } }),
      row({ repetition: 6, outcome: "llm_error", stage: "llm", result: null, error: { code: "quota_exhausted", message: "" } }),
    ]);
    expect(layersByCategory(gens, rules)).toEqual([
      { label: "Cat. 3 · lógica", group: "treatment", counts: { llm: 1, blocked: 1, runtime: 1, wrong: 1, pass: 1 }, total: 5 },
    ]);
  });
});
