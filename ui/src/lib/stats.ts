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

export type GenerationStatus = "pass" | "fail" | "no_expected";
export type Generation = { case_id: string; group: Group; repetition: number; rows: RecordRow[]; status: GenerationStatus };

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
    g.status = g.rows.some((r) => r.expected === null) ? "no_expected" : g.rows.every(rowMatches) ? "pass" : "fail";
  return [...byKey.values()];
}

/** `rate` es pass / (pass + fail); null si no hay generaciones con expected. */
export type PassCount = { pass: number; fail: number; noExpected: number; rate: number | null };

function passCount(gens: Generation[]): PassCount {
  const c = { pass: 0, fail: 0, noExpected: 0 };
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
