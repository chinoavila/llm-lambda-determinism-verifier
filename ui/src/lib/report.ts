// Evidencia del reporte con IA de una corrida (specs/ui.md §Reporte con IA). Reutiliza las
// estadísticas de lib/stats.ts y suma los indicadores de las observaciones metodológicas
// (pipeline/pipeline/report_methodology.md §4). Lo que va al LLM está acotado en tamaño.
import type { Group, RecordRow, Result, Rule, RunInfo } from "../api";
import {
  blockedStages,
  CATEGORY_LABEL,
  durationByGroup,
  errorsByGroup,
  generations,
  GROUPS,
  outcomesByGroup,
  OUTSIDE_CORPUS,
  passBy,
  passByGroup,
  rowMatches,
  type BreakdownRow,
  type CountRow,
  type Generation,
  type PassCount,
} from "./stats";

type PerGroup<T> = Record<Group, T>;
const perGroup = <T>(make: (g: Group) => T): PerGroup<T> => ({ treatment: make("treatment"), baseline1: make("baseline1"), baseline2: make("baseline2") });

export type Contradiction = { case_id: string; repetition: number; scenario_id: string; result: Result; expected: Result };

export type FailureSample = {
  case_id: string;
  category: string;
  group: Group;
  model: string;
  outcome: string;
  stage: string;
  error_code: string | null;
  error_message: string | null;
  result: Result | null;
  expected: Result | null;
  llm_raw: string | null;
};

export type Evidence = {
  run: {
    run_id: string;
    modified: string;
    records: number;
    generations: number;
    cases: number;
    scenarios: number;
    repetitions: number;
    models: string[];
    cases_by_category: Record<string, number>;
    cases_by_domain: Record<string, number>;
    temperature: string;
  };
  definitions: Record<string, string>;
  pass_by_group: PerGroup<PassCount>;
  pass_by_category: BreakdownRow[];
  pass_by_domain: BreakdownRow[];
  pass_by_model: BreakdownRow[];
  generations_by_model_and_category: Record<string, Record<string, number>>;
  outcomes_by_group: ReturnType<typeof outcomesByGroup>;
  blocked_stages: CountRow[];
  errors: CountRow[];
  duration: ReturnType<typeof durationByGroup>;
  observations: {
    llm_error_generations: PerGroup<number>;
    double_escaped_syntax_errors: { baseline1: number; baseline2: number };
    baseline2_harness_failures: { redefined_or_future_import: number; signature_mismatch: number };
    category_imbalance: string;
    category2: { treatment_scope_or_type_blocks: number; treatment_generations: number; result_type_mismatch_rows: PerGroup<number> };
    treatment_blocks_by_code: Record<string, number>;
    expected_contradictions: { scenarios: number; examples: Contradiction[] };
  };
  failure_sample: FailureSample[];
};

/** Lo que el PDF muestra además de la evidencia del prompt: el desglose por regla es largo. */
export type ReportData = { evidence: Evidence; passByRule: BreakdownRow[] };

const categoryOf = (rules: ReadonlyMap<string, Rule>, caseId: string) => {
  const rule = rules.get(caseId);
  return rule ? (CATEGORY_LABEL[rule.category] ?? `Cat. ${rule.category}`) : OUTSIDE_CORPUS;
};

const tally = (keys: string[]) => {
  const out: Record<string, number> = {};
  for (const k of keys) out[k] = (out[k] ?? 0) + 1;
  return out;
};

/** El modelo de una generación (las tres llamadas de una regla usan el mismo). */
const modelOf = (g: Generation) => g.rows[0]?.model ?? "?";

/** pass@1 por modelo, con las mismas reglas que passBy. */
export function passByModel(gens: Generation[]): BreakdownRow[] {
  const models = [...new Set(gens.map(modelOf))].sort();
  return models.map((label) => ({ label, byGroup: passByGroup(gens.filter((g) => modelOf(g) === label)) }));
}

/** Generaciones del Tratamiento por modelo y categoría: una por regla y repetición (obs. 4). */
export function modelByCategory(gens: Generation[], rules: ReadonlyMap<string, Rule>): Record<string, Record<string, number>> {
  const out: Record<string, Record<string, number>> = {};
  for (const g of gens.filter((x) => x.group === "treatment")) {
    const m = (out[modelOf(g)] ??= {});
    const c = categoryOf(rules, g.case_id);
    m[c] = (m[c] ?? 0) + 1;
  }
  return out;
}

/** La respuesta cruda trae `\\n` literal: el modelo escapó dos veces los saltos de línea (obs. 2). */
export const doubleEscaped = (raw: string | null) => raw !== null && raw.includes("\\\\n");

const firstError = (g: Generation) => g.rows.find((r) => r.error)?.error ?? null;

/** Mismo valor con otro tipo, por ejemplo `float` o cadena donde se esperaba `Decimal` (obs. 5). */
export function sameValueOtherType(r: RecordRow): boolean {
  if (r.outcome !== "executed" || !r.result || !r.expected || r.result.type === r.expected.type) return false;
  const a = Number(r.result.value);
  const b = Number(r.expected.value);
  return typeof r.result.value !== "boolean" && Number.isFinite(a) && Number.isFinite(b) && Math.abs(a - b) < 1e-9 * Math.max(1, Math.abs(b));
}

const same = (a: Result, b: Result) => a.type === b.type && JSON.stringify(a.value) === JSON.stringify(b.value);

/** Escenarios en que los tres grupos ejecutaron, coinciden entre sí y contradicen el expected (obs. 8). */
export function expectedContradictions(rows: RecordRow[]): Contradiction[] {
  const byScenario = new Map<string, Partial<Record<Group, RecordRow>>>();
  for (const r of rows) {
    const key = JSON.stringify([r.case_id, r.repetition, r.scenario_id]);
    const entry = byScenario.get(key) ?? {};
    entry[r.group] = r;
    byScenario.set(key, entry);
  }
  const out: Contradiction[] = [];
  for (const entry of byScenario.values()) {
    const rs = GROUPS.map((g) => entry[g]);
    const [first] = rs;
    if (!first?.result || !first.expected) continue;
    const result = first.result;
    if (rs.every((r) => r?.outcome === "executed" && r.result && same(r.result, result)) && !rowMatches(first))
      out.push({ case_id: first.case_id, repetition: first.repetition, scenario_id: first.scenario_id, result, expected: first.expected });
  }
  return out;
}

const truncate = (s: string | null, max: number) => (s === null || s.length <= max ? s : `${s.slice(0, max)}… [${s.length - max} caracteres más]`);

/** Hasta `perGroup` generaciones que fallan por grupo, alternando categorías, con el primer renglón fallido. */
export function sampleFailures(gens: Generation[], rules: ReadonlyMap<string, Rule>, perGroup = 3, maxChars = 400): FailureSample[] {
  const out: FailureSample[] = [];
  for (const group of GROUPS) {
    const failed = gens.filter((g) => g.group === group && g.status === "fail");
    const byCategory = new Map<string, Generation[]>();
    for (const g of failed) {
      const c = categoryOf(rules, g.case_id);
      byCategory.set(c, [...(byCategory.get(c) ?? []), g]);
    }
    const queues = [...byCategory.entries()].sort(([a], [b]) => a.localeCompare(b)).map(([, gs]) => gs);
    const picked: Generation[] = [];
    for (let i = 0; picked.length < perGroup && queues.some((q) => i < q.length); i++)
      for (const q of queues) if (i < q.length && picked.length < perGroup) picked.push(q[i]!);
    for (const g of picked) {
      const r = g.rows.find((x) => !rowMatches(x)) ?? g.rows[0]!;
      out.push({
        case_id: g.case_id,
        category: categoryOf(rules, g.case_id),
        group,
        model: r.model,
        outcome: r.outcome,
        stage: r.stage,
        error_code: r.error?.code ?? null,
        error_message: truncate(r.error?.message ?? null, 200),
        result: r.result,
        expected: r.expected,
        llm_raw: truncate(r.llm_raw, maxChars),
      });
    }
  }
  return out;
}

export function buildReportData(run: RunInfo, rows: RecordRow[], rules: ReadonlyMap<string, Rule>): ReportData {
  const gens = generations(rows);
  const caseIds = [...new Set(rows.map((r) => r.case_id))];
  const of = (group: Group) => gens.filter((g) => g.group === group);
  const errorIs = (g: Generation, test: (code: string, message: string) => boolean) => {
    const e = firstError(g);
    return !!e && test(e.code, e.message);
  };
  const cat2 = of("treatment").filter((g) => rules.get(g.case_id)?.category === 2);
  const contradictions = expectedContradictions(rows);

  const evidence: Evidence = {
    run: {
      run_id: run.run_id,
      modified: run.modified,
      records: rows.length,
      generations: gens.length,
      cases: caseIds.length,
      scenarios: new Set(rows.map((r) => `${r.case_id}\u0000${r.scenario_id}`)).size,
      repetitions: new Set(rows.map((r) => r.repetition)).size,
      models: [...new Set(rows.map((r) => r.model))].sort(),
      cases_by_category: tally(caseIds.map((id) => categoryOf(rules, id))),
      cases_by_domain: tally(caseIds.map((id) => rules.get(id)?.domain ?? OUTSIDE_CORPUS)),
      temperature: "no figura en los registros (se usa la del proveedor salvo que llm.toml la fije)",
    },
    definitions: {
      generacion: "una respuesta del LLM: regla × grupo × repetición, con un renglón por escenario",
      pass_at_1: "generaciones que aciertan todos sus escenarios / generaciones con expected",
      renglones: "los conteos de desenlaces, etapas, errores y duración son por renglón (escenario)",
    },
    pass_by_group: passByGroup(gens),
    pass_by_category: passBy(gens, "category", rules),
    pass_by_domain: passBy(gens, "domain", rules),
    pass_by_model: passByModel(gens),
    generations_by_model_and_category: modelByCategory(gens, rules),
    outcomes_by_group: outcomesByGroup(rows),
    blocked_stages: blockedStages(rows),
    errors: errorsByGroup(rows),
    duration: durationByGroup(rows),
    observations: {
      llm_error_generations: perGroup((g) => of(g).filter((x) => x.rows.some((r) => r.outcome === "llm_error")).length),
      double_escaped_syntax_errors: {
        baseline1: of("baseline1").filter((g) => errorIs(g, (c) => c === "SyntaxError") && doubleEscaped(g.rows[0]?.llm_raw ?? null)).length,
        baseline2: of("baseline2").filter((g) => errorIs(g, (c) => c === "SyntaxError") && doubleEscaped(g.rows[0]?.llm_raw ?? null)).length,
      },
      baseline2_harness_failures: {
        redefined_or_future_import: of("baseline2").filter((g) => errorIs(g, (c, m) => c === "mypy" && /already defined|__future__/.test(m))).length,
        signature_mismatch: of("baseline2").filter((g) => errorIs(g, (c) => c === "SignatureMismatch")).length,
      },
      category_imbalance: "ver generations_by_model_and_category y pass_by_model",
      category2: {
        treatment_scope_or_type_blocks: cat2.filter((g) => g.rows.some((r) => r.outcome === "blocked" && (r.stage === "scope" || r.stage === "typecheck"))).length,
        treatment_generations: cat2.length,
        result_type_mismatch_rows: perGroup((g) => rows.filter((r) => r.group === g && sameValueOtherType(r)).length),
      },
      treatment_blocks_by_code: tally(of("treatment").filter((g) => g.rows.some((r) => r.outcome === "blocked")).map((g) => firstError(g)?.code ?? "?")),
      expected_contradictions: { scenarios: contradictions.length, examples: contradictions.slice(0, 5) },
    },
    failure_sample: sampleFailures(gens, rules),
  };
  return { evidence, passByRule: passBy(gens, "rule", rules) };
}
