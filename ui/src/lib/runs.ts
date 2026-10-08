// Selección del formulario de Corridas (specs/ui.md §API, corridas).
import type { Rule, Selection } from "../api";

/** Balanceo por prioridad de llm.toml: el modelo puede cambiar entre casos según la cuota. */
export const AUTO_MODEL = "auto";

export type RunForm = {
  source: Selection["source"];
  picked: string[];
  repetitions: number;
  model: string;
  temperature: number;
  resume: string | null;
};

/** Cuerpo de estimate/start: `case_ids` solo para el corpus elegido a mano y `resume` solo al reanudar. */
export const runSelection = (f: RunForm): Selection => ({
  source: f.source,
  repetitions: f.repetitions,
  model: f.model,
  temperature: f.temperature,
  ...(f.source === "corpus" && f.picked.length ? { case_ids: f.picked } : {}),
  ...(f.resume ? { resume: f.resume } : {}),
});

/** Reglas de la corrida cuyos expected todavía no aprobó una revisión manual. */
export function unreviewedRules(rules: Rule[], f: Pick<RunForm, "source" | "picked">): string[] {
  if (f.source !== "corpus") return [];
  const chosen = f.picked.length ? rules.filter((r) => f.picked.includes(r.case_id)) : rules;
  return chosen.filter((r) => r.review?.status !== "aprobada").map((r) => r.case_id);
}
