/** Pruebas de normalización del estado de corpus, engine, sandbox, LLM y corridas. */
import { describe, expect, it } from "vitest";
import type { Health } from "./api";
import { healthChecks } from "./health";

const ready: Health = {
  engine: true,
  sandbox_queue: true,
  llm: { ready: true, models: ["openai/gpt-oss-120b", "qwen/qwen3-32b"], error: null },
  corpus_rules: 6,
  runs: 1,
};

describe("healthChecks", () => {
  it("resume cada parte del pipeline", () => {
    expect(healthChecks(ready).map((c) => [c.key, c.ok, c.detail])).toEqual([
      ["corpus", true, "6 reglas"],
      ["engine", true, "binario disponible"],
      ["sandbox", true, "cola configurada"],
      ["llm", true, "openai/gpt-oss-120b, qwen/qwen3-32b"],
      ["runs", true, "1 corrida"],
    ]);
  });

  it("explica lo que falta", () => {
    const checks = healthChecks({
      ...ready,
      engine: false,
      corpus_rules: 0,
      llm: { ready: false, models: [], error: "la variable de entorno GROQ_API_KEY no está definida" },
    });
    const byKey = Object.fromEntries(checks.map((c) => [c.key, c]));
    expect(byKey.corpus).toMatchObject({ ok: false, detail: "sin reglas en corpus/" });
    expect(byKey.engine?.ok).toBe(false);
    expect(byKey.llm?.detail).toContain("GROQ_API_KEY");
  });
});
