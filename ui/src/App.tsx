/** Aplicación raíz: navegación entre vistas, estado de salud y selección de página. */
import { useCallback, useEffect, useState } from "react";
import { api, errorText, type Health } from "./api";
import { healthChecks } from "./health";
import { CorpusPage } from "./pages/CorpusPage";
import { RecordsPage } from "./pages/RecordsPage";
import { RunsPage } from "./pages/RunsPage";
import { navigate, usePath } from "./router";

const SECTIONS = [
  { path: "/corpus", label: "Corpus", intro: "Las reglas del experimento: enunciado, variables, AST y Python canónicos, escenarios y revisión." },
  { path: "/corridas", label: "Corridas", intro: "Correr el pipeline con los tres grupos sobre el corpus o las fixtures." },
  { path: "/registros", label: "Registros", intro: "Los renglones de cada corrida, con la respuesta cruda del LLM y el expected de su escenario." },
] as const;

/** Presenta estado/carga/error de los servicios y permite reintentar la consulta. */
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
          <span className={`mt-1.5 size-2 shrink-0 rounded-full ${c.ok ? "bg-ok" : "bg-bad"}`} aria-label={c.ok ? "listo" : "falta"} />
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

/** Resuelve la ruta actual y coordina las vistas Corpus, Corridas y Registros. */
export default function App() {
  const path = usePath();
  useEffect(() => {
    if (path === "/") navigate("/corpus");
  }, [path]);
  const current = SECTIONS.find((s) => path.startsWith(s.path)) ?? SECTIONS[0];
  const runId = path.startsWith("/registros/") ? decodeURIComponent(path.slice("/registros/".length)) || null : null;

  const [health, setHealth] = useState<Health | null>(null);
  const [error, setError] = useState<string | null>(null);
  const loadHealth = useCallback(() => {
    setError(null);
    api
      .health()
      .then(setHealth)
      .catch((e: unknown) => setError(errorText(e)));
  }, []);
  useEffect(loadHealth, [loadHealth]);

  return (
    <div className="mx-auto grid max-w-[1240px] gap-5 px-4 pt-7 pb-12">
      <header className="flex flex-wrap items-end justify-between gap-x-6 gap-y-3">
        <div>
          <h1 className="text-[22px] font-semibold tracking-tight text-balance">Mesa del pipeline</h1>
          <p className="mt-1 max-w-[62ch] text-muted">{current.intro}</p>
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
              className={`rounded-md px-3.5 py-1.5 font-medium ${s === current ? "bg-accent-soft text-accent" : "text-muted hover:bg-hover"}`}
            >
              {s.label}
            </a>
          ))}
        </nav>
      </header>

      <HealthBar health={health} error={error} onRetry={loadHealth} />

      {current.path === "/corpus" && <CorpusPage onChanged={loadHealth} />}
      {current.path === "/corridas" && <RunsPage health={health} onChanged={loadHealth} />}
      {current.path === "/registros" && <RecordsPage runId={runId} />}
    </div>
  );
}
