// Estadísticas de una corrida, calculadas en la SPA a partir de sus registros
// (specs/ui.md §Estadísticas). La API no agrega: devuelve renglones.
import type { Group, Outcome, RecordRow, Rule } from "../api";

export const GROUPS: Group[] = ["treatment", "baseline1", "baseline2"];
export const OUTCOMES: Outcome[] = ["executed", "blocked", "runtime_error", "timeout", "llm_error"];
export const OUTSIDE_CORPUS = "fuera del corpus";
export const CATEGORY_LABEL: Record<number, string> = { 1: "Cat. 1 · estructura", 2: "Cat. 2 · tipos", 3: "Cat. 3 · lógica" };

type PerGroup<T> = Record<Group, T>;
const perGroup = <T>(make: () => T): PerGroup<T> => ({ treatment: make(), baseline1: make(), baseline2: make() });

/** Ejecutó y su resultado coincide con el expected en tipo y valor (comparación estricta). */
export function rowMatches(r: RecordRow): boolean {
  return (
    r.outcome === "executed" &&
    r.result !== null &&
    r.expected !== null &&
    r.result.type === r.expected.type &&
    JSON.stringify(r.result.value) === JSON.stringify(r.expected.value)
  );
}

export type GenerationStatus = "pass" | "fail" | "no_expected" | "pending";
export type Generation = { case_id: string; group: Group; repetition: number; rows: RecordRow[]; status: GenerationStatus };

/** Fallas de infraestructura (cuota, red), no del modelo: la llamada queda pendiente y `--resume` la reintenta. */
export const PENDING_CODES = ["quota_exhausted", "transport_error"];
export const isPending = (r: RecordRow) => r.outcome === "llm_error" && PENDING_CODES.includes(r.error?.code ?? "");

/** Agrupa los renglones por generación `(case_id, group, repetition)`, en orden de aparición. */
export function generations(rows: RecordRow[]): Generation[] {
  const byKey = new Map<string, Generation>();
  for (const r of rows) {
    const key = JSON.stringify([r.case_id, r.group, r.repetition]);
    let g = byKey.get(key);
    if (!g) byKey.set(key, (g = { case_id: r.case_id, group: r.group, repetition: r.repetition, rows: [], status: "pass" }));
    g.rows.push(r);
  }
  for (const g of byKey.values())
    g.status = g.rows.some(isPending)
      ? "pending"
      : g.rows.some((r) => r.expected === null)
        ? "no_expected"
        : g.rows.every(rowMatches)
          ? "pass"
          : "fail";
  return [...byKey.values()];
}

/** `rate` es pass / (pass + fail); null si no hay generaciones con expected. Las pendientes no cuentan. */
export type PassCount = { pass: number; fail: number; noExpected: number; pending: number; rate: number | null };

function passCount(gens: Generation[]): PassCount {
  const c = { pass: 0, fail: 0, noExpected: 0, pending: 0 };
  for (const g of gens) c[g.status === "no_expected" ? "noExpected" : g.status]++;
  const judged = c.pass + c.fail;
  return { ...c, rate: judged ? c.pass / judged : null };
}

/** pass@1 de cada grupo. */
export const passByGroup = (gens: Generation[]): PerGroup<PassCount> => ({
  treatment: passCount(gens.filter((g) => g.group === "treatment")),
  baseline1: passCount(gens.filter((g) => g.group === "baseline1")),
  baseline2: passCount(gens.filter((g) => g.group === "baseline2")),
});

export type BreakdownKey = "rule" | "category" | "domain";
export type BreakdownRow = { label: string; byGroup: PerGroup<PassCount> };

/** pass@1 por grupo para cada regla, categoría o dominio. Lo que no está en `rules` va a "fuera del corpus". */
export function passBy(gens: Generation[], key: BreakdownKey, rules: ReadonlyMap<string, Rule>): BreakdownRow[] {
  const labelOf = (caseId: string) => {
    if (key === "rule") return caseId;
    const rule = rules.get(caseId);
    if (!rule) return OUTSIDE_CORPUS;
    return key === "category" ? (CATEGORY_LABEL[rule.category] ?? `Cat. ${rule.category}`) : rule.domain;
  };
  const buckets = new Map<string, Generation[]>();
  for (const g of gens) {
    const label = labelOf(g.case_id);
    buckets.set(label, [...(buckets.get(label) ?? []), g]);
  }
  return [...buckets]
    .map(([label, gs]) => ({ label, byGroup: passByGroup(gs) }))
    .sort((a, b) => Number(a.label === OUTSIDE_CORPUS) - Number(b.label === OUTSIDE_CORPUS) || a.label.localeCompare(b.label));
}

/** Renglones por desenlace y grupo. */
export function outcomesByGroup(rows: RecordRow[]): PerGroup<Record<Outcome, number>> {
  const out = perGroup(() => Object.fromEntries(OUTCOMES.map((o) => [o, 0])) as Record<Outcome, number>);
  for (const r of rows) if (out[r.group]) out[r.group][r.outcome]++;
  return out;
}

export type CountRow = { key: string; byGroup: PerGroup<number>; total: number };

function countBy(rows: RecordRow[], keyOf: (r: RecordRow) => string | null): CountRow[] {
  const map = new Map<string, CountRow>();
  for (const r of rows) {
    const key = keyOf(r);
    if (key === null || !GROUPS.includes(r.group)) continue;
    let c = map.get(key);
    if (!c) map.set(key, (c = { key, byGroup: perGroup(() => 0), total: 0 }));
    c.byGroup[r.group]++;
    c.total++;
  }
  return [...map.values()].sort((a, b) => b.total - a.total || a.key.localeCompare(b.key));
}

/** Renglones bloqueados por etapa y grupo, de mayor a menor. */
export const blockedStages = (rows: RecordRow[]) => countBy(rows, (r) => (r.outcome === "blocked" ? r.stage : null));

/** Renglones por código de error y grupo, de mayor a menor. */
export const errorsByGroup = (rows: RecordRow[]) => countBy(rows, (r) => r.error?.code ?? null);

export type Duration = { n: number; mean: number | null; median: number | null };

export function median(values: number[]): number | null {
  if (!values.length) return null;
  const s = [...values].sort((a, b) => a - b);
  const mid = Math.floor(s.length / 2);
  return s.length % 2 ? s[mid]! : (s[mid - 1]! + s[mid]!) / 2;
}

/** n, media y mediana de `duration_ms` (se ignoran los nulos). */
export function durationByGroup(rows: RecordRow[]): PerGroup<Duration> {
  const out = perGroup<Duration>(() => ({ n: 0, mean: null, median: null }));
  for (const group of GROUPS) {
    const ms = rows.filter((r) => r.group === group && r.duration_ms !== null).map((r) => r.duration_ms!);
    out[group] = { n: ms.length, mean: ms.length ? ms.reduce((a, b) => a + b, 0) / ms.length : null, median: median(ms) };
  }
  return out;
}

/** Porcentaje con un decimal en formato es-AR, o raya si no hay tasa. */
export const fmtRate = (rate: number | null) =>
  rate === null ? "—" : `${(rate * 100).toLocaleString("es-AR", { minimumFractionDigits: 1, maximumFractionDigits: 1 })} %`;

export type RunConditions = {
  models: string[];
  /** Una etiqueta por valor distinto: el número, "del proveedor" (no se envió) o "no registrada" (registro 2.0). */
  temperatures: string[];
  repetitions: number;
  generations: number;
  /** Generaciones cuyo registro trae `usage.total_tokens` (registro 2.1 con respuesta del proveedor). */
  withUsage: number;
  totalTokens: number;
  tokensPerCall: number | null;
};

const temperatureLabel = (r: RecordRow) => {
  if (r.request_params === undefined) return "no registrada";
  const t = r.request_params.temperature;
  return typeof t === "number" ? String(t) : "del proveedor";
};

const totalTokens = (r: RecordRow) => {
  const t = r.usage?.total_tokens;
  return typeof t === "number" ? t : null;
};

/** Modelo, temperatura y tokens de la corrida, leídos de `request_params` y `usage` (una vez por generación). */
export function runConditions(gens: Generation[]): RunConditions {
  const firsts = gens.map((g) => g.rows[0]!).filter(Boolean);
  const tokens = firsts.map(totalTokens).filter((t): t is number => t !== null);
  const sum = tokens.reduce((a, b) => a + b, 0);
  return {
    models: [...new Set(firsts.map((r) => r.model))].sort(),
    temperatures: [...new Set(firsts.map(temperatureLabel))].sort(),
    repetitions: new Set(gens.map((g) => g.repetition)).size,
    generations: gens.length,
    withUsage: tokens.length,
    totalTokens: sum,
    tokensPerCall: tokens.length ? sum / tokens.length : null,
  };
}

/** Generaciones juzgadas (pass o fail) de cada regla de un grupo: n repeticiones, c aciertos. */
function perCase(gens: Generation[], group: Group): Map<string, { n: number; c: number }> {
  const byCase = new Map<string, { n: number; c: number }>();
  for (const g of gens) {
    if (g.group !== group || (g.status !== "pass" && g.status !== "fail")) continue;
    const e = byCase.get(g.case_id) ?? { n: 0, c: 0 };
    e.n++;
    if (g.status === "pass") e.c++;
    byCase.set(g.case_id, e);
  }
  return byCase;
}

/** Estimador insesgado de pass@k para una regla (Chen et al. 2021): 1 - C(n-c, k) / C(n, k). */
export function passAtKOne(n: number, c: number, k: number): number {
  if (n - c < k) return 1;
  let miss = 1;
  for (let i = n - c + 1; i <= n; i++) miss *= 1 - k / i;
  return 1 - miss;
}

export type PassAtK = { k: number; byGroup: PerGroup<{ rate: number | null; cases: number }> };

/** pass@k por grupo: promedio entre las reglas con al menos k generaciones juzgadas. */
export function passAtK(gens: Generation[], ks: number[]): PassAtK[] {
  const byGroup = perGroup(() => [] as { n: number; c: number }[]);
  for (const group of GROUPS) byGroup[group] = [...perCase(gens, group).values()];
  return ks.map((k) => {
    const at = (group: Group) => {
      const cases = byGroup[group].filter((e) => e.n >= k);
      return { rate: cases.length ? cases.reduce((s, e) => s + passAtKOne(e.n, e.c, k), 0) / cases.length : null, cases: cases.length };
    };
    return { k, byGroup: { treatment: at("treatment"), baseline1: at("baseline1"), baseline2: at("baseline2") } };
  });
}

/** Valores de k que tiene sentido mostrar para una corrida de `repetitions` repeticiones. */
export const kValues = (repetitions: number) => [1, 2, 3, 5, 10, 20].filter((k) => k <= repetitions);

export type Consistency = { cases: number; stable: number; unstable: string[] };

/** Reglas con 2+ generaciones juzgadas: estables si pasan todas o fallan todas; inestables si se mezclan. */
export function consistency(gens: Generation[]): PerGroup<Consistency> {
  const out = perGroup<Consistency>(() => ({ cases: 0, stable: 0, unstable: [] }));
  for (const group of GROUPS)
    for (const [caseId, { n, c }] of [...perCase(gens, group)].sort(([a], [b]) => a.localeCompare(b))) {
      if (n < 2) continue;
      out[group].cases++;
      if (c === 0 || c === n) out[group].stable++;
      else out[group].unstable.push(caseId);
    }
  return out;
}

/** Dónde quedó cada generación juzgada: sin respuesta del LLM, bloqueada antes de ejecutar
 * (en el Tratamiento, por el motor), con error de ejecución, ejecutada con un resultado
 * incorrecto (solo lo detectan los escenarios) o acertada. */
export type Layer = "llm" | "blocked" | "runtime" | "wrong" | "pass";
export const LAYERS: Layer[] = ["llm", "blocked", "runtime", "wrong", "pass"];

export function layerOf(g: Generation): Layer {
  if (g.rows.some((r) => r.outcome === "llm_error")) return "llm";
  if (g.rows.some((r) => r.outcome === "blocked")) return "blocked";
  if (g.rows.some((r) => r.outcome === "runtime_error" || r.outcome === "timeout")) return "runtime";
  return g.status === "pass" ? "pass" : "wrong";
}

export type LayerRow = { label: string; group: Group; counts: Record<Layer, number>; total: number };

/** Generaciones juzgadas (con expected, no pendientes) por categoría, grupo y capa. */
export function layersByCategory(gens: Generation[], rules: ReadonlyMap<string, Rule>): LayerRow[] {
  const rows = new Map<string, LayerRow>();
  for (const g of gens) {
    if (g.status !== "pass" && g.status !== "fail") continue;
    const rule = rules.get(g.case_id);
    const label = rule ? (CATEGORY_LABEL[rule.category] ?? `Cat. ${rule.category}`) : OUTSIDE_CORPUS;
    const key = `${label}\u0000${g.group}`;
    let row = rows.get(key);
    if (!row) rows.set(key, (row = { label, group: g.group, counts: { llm: 0, blocked: 0, runtime: 0, wrong: 0, pass: 0 }, total: 0 }));
    row.counts[layerOf(g)]++;
    row.total++;
  }
  return [...rows.values()].sort(
    (a, b) =>
      Number(a.label === OUTSIDE_CORPUS) - Number(b.label === OUTSIDE_CORPUS) ||
      a.label.localeCompare(b.label) ||
      GROUPS.indexOf(a.group) - GROUPS.indexOf(b.group),
  );
}
