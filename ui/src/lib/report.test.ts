/** Pruebas de la evidencia y del PDF del reporte con IA (specs/ui.md §Reporte con IA). */
import { describe, expect, it } from "vitest";
import type { AiReport, RecordRow, Rule, RunInfo } from "../api";
import { buildReportData, doubleEscaped, expectedContradictions, modelByCategory, passByModel, sameValueOtherType, sampleFailures } from "./report";
import { OBSERVATION_TITLES, REFERENCES, reportDocDefinition } from "./reportPdf";
import { blankRule } from "./rules";
import { generations } from "./stats";

const row = (over: Partial<RecordRow>): RecordRow => ({
  run_id: "r",
  case_id: "c1",
  group: "treatment",
  repetition: 1,
  scenario_id: "S1",
  model: "m1",
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
const fail = (over: Partial<RecordRow>) => row({ outcome: "runtime_error", result: null, error: { code: "SyntaxError", message: "x" }, ...over });

const rule = (case_id: string, category: number, domain = "credito"): Rule => ({ ...blankRule(), case_id, category, domain });
const RULES = new Map([rule("c1", 1), rule("c2", 2, "salud")].map((r) => [r.case_id, r]));
const RUN: RunInfo = { run_id: "r", records: 0, has_log: false, modified: "2026-10-07T00:00:00+00:00", job: null };

describe("indicadores de las observaciones", () => {
  it("detecta saltos de línea escapados dos veces en la respuesta cruda", () => {
    expect(doubleEscaped(String.raw`{"code": "def f():\\n    return 1"}`)).toBe(true);
    expect(doubleEscaped(String.raw`{"code": "def f():\n    return 1"}`)).toBe(false);
    expect(doubleEscaped(null)).toBe(false);
  });

  it("reconoce el valor correcto con otro tipo", () => {
    expect(sameValueOtherType(row({ result: { type: "Other", value: 0.3 }, expected: { type: "Decimal", value: "0.30" } }))).toBe(true);
    expect(sameValueOtherType(row({ result: { type: "Decimal", value: "0.3" }, expected: { type: "Decimal", value: "0.3" } }))).toBe(false);
    expect(sameValueOtherType(row({ result: { type: "Int", value: 4 }, expected: { type: "Decimal", value: "5" } }))).toBe(false);
  });

  it("encuentra escenarios en que los tres grupos coinciden y contradicen el expected", () => {
    const wrong = { result: { type: "Bool" as const, value: false } };
    const rows = [
      row({ ...wrong }),
      row({ ...wrong, group: "baseline1" }),
      row({ ...wrong, group: "baseline2" }),
      row({ scenario_id: "S2", ...wrong }),
      row({ scenario_id: "S2", group: "baseline1" }),
      row({ scenario_id: "S2", group: "baseline2", ...wrong }),
    ];
    expect(expectedContradictions(rows)).toEqual([
      { case_id: "c1", repetition: 1, scenario_id: "S1", result: { type: "Bool", value: false }, expected: { type: "Bool", value: true } },
    ]);
  });

  it("cuenta generaciones por modelo y categoría, y pass@1 por modelo", () => {
    const gens = generations([row({}), row({ case_id: "c2", model: "m2" }), fail({ case_id: "c2", model: "m2", group: "baseline1" })]);
    expect(modelByCategory(gens, RULES)).toEqual({ m1: { "Cat. 1 · estructura": 1 }, m2: { "Cat. 2 · tipos": 1 } });
    const m2 = passByModel(gens).find((r) => r.label === "m2")!;
    expect(m2.byGroup.treatment.pass).toBe(1);
    expect(m2.byGroup.baseline1.fail).toBe(1);
  });

  it("acota la muestra de fallos por grupo y trunca llm_raw", () => {
    const rows = Array.from({ length: 6 }, (_, i) => fail({ case_id: i % 2 ? "c1" : "c2", repetition: i, group: "baseline1", llm_raw: "x".repeat(50) }));
    const sample = sampleFailures(generations(rows), RULES, 3, 10);
    expect(sample).toHaveLength(3);
    expect(new Set(sample.map((s) => s.category)).size).toBe(2);
    expect(sample[0]!.llm_raw).toBe(`${"x".repeat(10)}… [40 caracteres más]`);
  });
});

describe("buildReportData", () => {
  it("reúne la metadata, las estadísticas y los indicadores", () => {
    const rows = [
      row({}),
      row({ scenario_id: "S2" }),
      fail({ group: "baseline1", llm_raw: String.raw`{"code": "a\\nb"}` }),
      row({ group: "baseline2", outcome: "llm_error", stage: "llm", result: null, error: { code: "generation_failed", message: "" } }),
      row({ case_id: "c2", group: "treatment", outcome: "blocked", stage: "typecheck", result: null, error: { code: "OPERAND_MISMATCH", message: "" } }),
    ];
    const { evidence: e, passByRule } = buildReportData(RUN, rows, RULES);
    expect(e.run).toMatchObject({ run_id: "r", records: 5, generations: 4, cases: 2, scenarios: 3, repetitions: 1, models: ["m1"] });
    expect(e.run.cases_by_category).toEqual({ "Cat. 1 · estructura": 1, "Cat. 2 · tipos": 1 });
    expect(e.run).toMatchObject({ temperature: "no registrada", tokens: { total: 0, per_call: null, generations_with_usage: 0 } }); // registros 2.0
    expect(e.pass_at_k.map((r) => r.k)).toEqual([1]);
    expect(e.pass_by_group.treatment).toMatchObject({ pass: 1, fail: 1 });
    expect(e.observations.llm_error_generations).toEqual({ treatment: 0, baseline1: 0, baseline2: 1 });
    expect(e.observations.double_escaped_syntax_errors).toEqual({ baseline1: 1, baseline2: 0 });
    expect(e.observations.category2).toMatchObject({ treatment_scope_or_type_blocks: 1, treatment_generations: 1 });
    expect(e.observations.treatment_blocks_by_code).toEqual({ OPERAND_MISMATCH: 1 });
    expect(passByRule.map((r) => r.label)).toEqual(["c1", "c2"]);
    expect(e).not.toHaveProperty("pass_by_rule"); // el desglose por regla no va al prompt
  });
});

describe("reportDocDefinition", () => {
  const report: AiReport = {
    title: "Informe",
    abstract: "Resumen.",
    sections: [{ heading: "Resultados", paragraphs: ["Párrafo."] }],
    observations: [
      { number: 2, status: "se_repite", text: "B." },
      { number: 1, status: "no_concluyente", text: "A." },
    ],
    limitations: ["Una repetición."],
    conclusions: ["Revisar."],
  };

  it("pone el texto del LLM, las referencias fijas y los anexos con la evidencia", () => {
    const data = buildReportData(RUN, [row({}), fail({ group: "baseline1" })], RULES);
    const doc = reportDocDefinition(report, data, { model: "gpt-x", createdAt: "hoy" });
    const text = JSON.stringify(doc.content);
    for (const s of ["Informe", "Resumen.", "Resultados", "Párrafo.", "Contraste con las observaciones metodológicas", "Anexo A", "Anexo B", "gpt-x"])
      expect(text).toContain(s);
    expect(text).toContain(JSON.stringify(REFERENCES[1]));
    expect(text.indexOf(OBSERVATION_TITLES[0]!)).toBeLessThan(text.indexOf(OBSERVATION_TITLES[1]!));
    expect(text).toContain("100,0 %"); // pass@1 del Tratamiento, calculado por la SPA
    expect(doc.info?.title).toBe("Informe");
  });
});
