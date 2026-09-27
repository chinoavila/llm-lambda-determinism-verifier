import type { Health } from "./api";

export type Check = { key: string; label: string; ok: boolean; detail: string };

/** Lo que muestra la barra de estado, en el orden en que se usa el pipeline. */
export function healthChecks(h: Health): Check[] {
  const rules = h.corpus_rules === 1 ? "1 regla" : `${h.corpus_rules} reglas`;
  const runs = h.runs === 1 ? "1 corrida" : `${h.runs} corridas`;
  return [
    { key: "corpus", label: "Corpus", ok: h.corpus_rules > 0, detail: h.corpus_rules > 0 ? rules : "sin reglas en corpus/" },
    { key: "engine", label: "Engine", ok: h.engine, detail: h.engine ? "binario disponible" : "no se encontró el binario" },
    { key: "sandbox", label: "Sandbox", ok: h.sandbox_queue, detail: h.sandbox_queue ? "cola configurada" : "falta SANDBOX_IO" },
    {
      key: "llm",
      label: "LLM",
      ok: h.llm.ready,
      detail: h.llm.ready ? h.llm.models.join(", ") : (h.llm.error ?? "sin configurar"),
    },
    { key: "runs", label: "Registros", ok: true, detail: runs },
  ];
}
