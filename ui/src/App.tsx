import { useCallback, useEffect, useState } from "react";
import { getHealth, type Health } from "./api";
import { healthChecks } from "./health";
import { navigate, usePath } from "./router";

const SECTIONS = [
  {
    path: "/corpus",
    label: "Corpus",
    intro: "Las reglas del experimento: enunciado, variables, AST y Python canónicos, escenarios y estado de revisión.",
    next: "Etapa 2: crear, editar y eliminar reglas, con check-case al guardar.",
  },
  {
    path: "/corridas",
    label: "Corridas",
    intro: "Ejecutar el pipeline sobre el corpus o las fixtures con los tres grupos.",
    next: "Etapa 3: lanzar una corrida con confirmación de cuota, seguir el log y cancelarla.",
  },
  {
    path: "/registros",
    label: "Registros",
    intro: "Los renglones de cada corrida: grupo, escenario, etapa alcanzada, desenlace y la respuesta cruda del LLM.",
    next: "Etapa 3: explorar y filtrar los registros de un out/<run_id>.jsonl.",
  },
] as const;

function HealthBar({ health, error, onRetry }: { health: Health | null; error: string | null; onRetry: () => void }) {
  if (error) {
    return (
      <div className="flex flex-wrap items-center gap-3 rounded-lg bg-bad-soft px-4 py-2.5 text-ink">
        <span>No se pudo consultar el estado del pipeline: {error}</span>
        <button type="button" onClick={onRetry} className="font-medium text-accent hover:underline">
          Reintentar
        </button>
      </div>
    );
  }
  if (!health) return <div className="px-1 text-muted">Consultando el estado del pipeline…</div>;
  return (
    <ul className="grid grid-cols-[repeat(auto-fit,minmax(190px,1fr))] gap-2" aria-label="Estado del pipeline">
      {healthChecks(health).map((c) => (
        <li key={c.key} className="flex min-w-0 items-start gap-2.5 rounded-lg border border-line bg-surface px-3 py-2.5">
          <span
            className={`mt-1.5 size-2 shrink-0 rounded-full ${c.ok ? "bg-ok" : "bg-bad"}`}
            aria-label={c.ok ? "listo" : "falta"}
          />
          <span className="min-w-0">
            <span className="block font-medium">{c.label}</span>
            <span className="block truncate text-[12.5px] text-muted" title={c.detail}>
              {c.detail}
            </span>
          </span>
        </li>
      ))}
    </ul>
  );
}

export default function App() {
  const path = usePath();
  const current = SECTIONS.find((s) => path.startsWith(s.path)) ?? SECTIONS[0];
  const [health, setHealth] = useState<Health | null>(null);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(() => {
    setError(null);
    getHealth()
      .then(setHealth)
      .catch((e: unknown) => setError(e instanceof Error ? e.message : String(e)));
  }, []);
  useEffect(load, [load]);

  return (
    <div className="mx-auto grid max-w-[1200px] gap-5 px-4 pt-7 pb-12">
      <header className="flex flex-wrap items-end justify-between gap-x-6 gap-y-3">
        <div>
          <h1 className="text-[22px] font-semibold tracking-tight text-balance">Mesa del pipeline</h1>
          <p className="mt-1 max-w-[62ch] text-muted">
            Corpus, corridas y registros del validador STLC y sus dos baselines, desde un solo lugar.
          </p>
        </div>
        <nav className="flex gap-1 rounded-lg border border-line bg-surface p-1" aria-label="Secciones">
          {SECTIONS.map((s) => (
            <a
              key={s.path}
              href={s.path}
              aria-current={s === current ? "page" : undefined}
              onClick={(e) => {
                e.preventDefault();
                navigate(s.path);
              }}
              className={`rounded-md px-3.5 py-1.5 font-medium ${
                s === current ? "bg-accent-soft text-accent" : "text-muted hover:bg-hover"
              }`}
            >
              {s.label}
            </a>
          ))}
        </nav>
      </header>

      <HealthBar health={health} error={error} onRetry={load} />

      <main className="rounded-xl border border-line bg-surface">
        <div className="border-b border-line px-5 py-4">
          <h2 className="text-base font-semibold">{current.label}</h2>
          <p className="mt-0.5 text-muted">{current.intro}</p>
        </div>
        <div className="px-5 py-10 text-center text-muted">{current.next}</div>
      </main>
    </div>
  );
}
