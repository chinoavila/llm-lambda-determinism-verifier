/** Vista para estimar, iniciar, consultar y cancelar corridas del pipeline. */
import { useCallback, useEffect, useRef, useState } from "react";
import { api, errorText, type Estimate, type Health, type Job, type JobStatus, type Rule, type RunInfo, type Runs, type Selection } from "../api";
import { Badge, Button, Card, Confirm, fmtDate, inputClass, Notice, type Tone } from "../components/ui";
import { EXPORT_FORMATS, exportRecords, type ExportFormat } from "../lib/export";
import { buildReportData } from "../lib/report";
import { downloadReportPdf, reportDocDefinition } from "../lib/reportPdf";
import { navigate } from "../router";

/** Presentación de estados de job compartida por la vista de corridas. */
export const JOB_STATUS: Record<JobStatus, { label: string; tone: Tone }> = {
  running: { label: "En curso", tone: "accent" },
  finished: { label: "Terminada", tone: "ok" },
  failed: { label: "Falló", tone: "bad" },
  cancelled: { label: "Cancelada", tone: "warn" },
};

/** Coordina el formulario de selección, el seguimiento del job y el log en vivo. */
export function RunsPage({ health, onChanged }: { health: Health | null; onChanged: () => void }) {
  const [runs, setRuns] = useState<Runs | null>(null);
  const [rules, setRules] = useState<Rule[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [source, setSource] = useState<Selection["source"]>("corpus");
  const [picked, setPicked] = useState<string[]>([]);
  const [repetitions, setRepetitions] = useState(1);
  const [resume, setResume] = useState<string | null>(null);
  const [estimate, setEstimate] = useState<Estimate | null>(null);
  const [estimateError, setEstimateError] = useState<string | null>(null);
  const [confirming, setConfirming] = useState<{ error: string | null; busy: boolean } | null>(null);
  const [cancelling, setCancelling] = useState(false);
  const [logFor, setLogFor] = useState<string | null>(null);
  const [reporting, setReporting] = useState<{ run: RunInfo; busy: boolean; error: string | null } | null>(null);

  const selection: Selection = {
    source,
    repetitions,
    ...(source === "corpus" && picked.length ? { case_ids: picked } : {}),
    ...(resume ? { resume } : {}),
  };
  const selectionKey = JSON.stringify(selection);

  const loadRuns = useCallback(() => {
    api
      .runs()
      .then((r) => {
        setRuns(r);
        if (r.active) setLogFor(r.active.run_id);
      })
      .catch((e: unknown) => setError(errorText(e)));
  }, []);
  useEffect(() => {
    loadRuns();
    api.rules().then(setRules).catch(() => setRules([]));
  }, [loadRuns]);

  useEffect(() => {
    let alive = true;
    setEstimateError(null);
    const s: Selection = JSON.parse(selectionKey);
    const t = setTimeout(() => {
      api
        .estimate(s)
        .then((e) => alive && setEstimate(e))
        .catch((e: unknown) => {
          if (!alive) return;
          setEstimate(null);
          setEstimateError(errorText(e));
        });
    }, 200);
    return () => {
      alive = false;
      clearTimeout(t);
    };
  }, [selectionKey]);

  const active = runs?.active ?? null;
  useEffect(() => {
    if (!active) return;
    const t = setInterval(loadRuns, 2000);
    return () => clearInterval(t);
  }, [active, loadRuns]);
  const wasActive = useRef(false);
  useEffect(() => {
    if (wasActive.current && !active) onChanged();
    wasActive.current = !!active;
  }, [active, onChanged]);

  async function launch() {
    if (!estimate) return;
    setConfirming({ error: null, busy: true });
    try {
      const job = await api.startRun(selection, estimate.calls);
      setConfirming(null);
      setResume(null);
      setLogFor(job.run_id);
      loadRuns();
    } catch (e) {
      setConfirming({ error: errorText(e), busy: false });
    }
  }

  async function cancel(runId: string) {
    setCancelling(true);
    try {
      await api.cancelRun(runId);
      loadRuns();
    } catch (e) {
      setError(errorText(e));
    } finally {
      setCancelling(false);
    }
  }

  // Una llamada al LLM: la evidencia la arma la SPA y el PDF también (specs/ui.md §Reporte con IA).
  async function generateReport(run: RunInfo) {
    setReporting({ run, busy: true, error: null });
    try {
      const rows = await api.records(run.run_id, {});
      const data = buildReportData(run, rows, new Map(rules.map((r) => [r.case_id, r])));
      const res = await api.report(run.run_id, data.evidence);
      const doc = reportDocDefinition(res.report, data, { model: res.model, createdAt: new Date().toLocaleString("es-AR") });
      await downloadReportPdf(doc, `${run.run_id}-reporte.pdf`);
      setReporting(null);
    } catch (e) {
      setReporting({ run, busy: false, error: errorText(e) });
    }
  }

  const llmReady = health?.llm.ready ?? false;

  return (
    <div className="grid gap-4">
      {error && <Notice tone="bad">{error}</Notice>}

      <Card className="grid gap-4 p-5">
        <div>
          <h3 className="text-base font-semibold">Nueva corrida</h3>
          <p className="mt-0.5 max-w-[70ch] text-muted">
            Es la misma corrida que <code className="font-mono text-[12.5px]">python -m pipeline run</code>: una llamada al LLM por grupo y
            repetición, ejecutada contra todos los escenarios de cada regla. Consume cuota del proveedor.
          </p>
        </div>
        {!llmReady && health && <Notice>Faltan las credenciales del LLM: {health.llm.error}. Completá .env y reiniciá el servicio ui.</Notice>}
        {resume && (
          <Notice>
            Reanudando <code className="font-mono">{resume}</code>: se saltean las llamadas ya resueltas y se reintentan las cortadas por cuota o
            red. Elegí los mismos casos y repeticiones que la corrida original.{" "}
            <Button variant="link" onClick={() => setResume(null)}>
              Volver a una corrida nueva
            </Button>
          </Notice>
        )}
        <div className="flex flex-wrap gap-6">
          <fieldset className="grid gap-1.5">
            <legend className="mb-1.5 text-[12.5px] font-medium text-muted">Casos</legend>
            {(
              [
                ["corpus", "Corpus (corpus/)"],
                ["fixtures", "Fixtures (contracts/fixtures/)"],
              ] as const
            ).map(([value, label]) => (
              <label key={value} className="flex items-center gap-2">
                <input type="radio" name="source" value={value} checked={source === value} onChange={() => setSource(value)} className="accent-accent" />
                {label}
              </label>
            ))}
          </fieldset>
          <label className="grid content-start gap-1.5">
            <span className="text-[12.5px] font-medium text-muted">Repeticiones</span>
            <input
              type="number"
              min={1}
              max={20}
              value={repetitions}
              onChange={(e) => setRepetitions(Math.max(1, Math.min(20, Number(e.target.value) || 1)))}
              className={`${inputClass} w-28 tabular-nums`}
            />
          </label>
        </div>
        {source === "corpus" && rules.length > 0 && (
          <details className="rounded-lg border border-line px-3.5 py-2.5">
            <summary className="cursor-pointer text-muted">
              {picked.length ? `${picked.length} reglas elegidas` : "Todas las reglas del corpus"} · elegir reglas
            </summary>
            <div className="mt-3 grid grid-cols-[repeat(auto-fill,minmax(220px,1fr))] gap-1.5">
              {rules
                .map((r) => r.case_id)
                .sort()
                .map((id) => (
                  <label key={id} className="flex items-center gap-2 font-mono text-[12.5px]">
                    <input
                      type="checkbox"
                      className="accent-accent"
                      checked={picked.includes(id)}
                      onChange={(e) => setPicked((p) => (e.target.checked ? [...p, id] : p.filter((x) => x !== id)))}
                    />
                    {id}
                  </label>
                ))}
            </div>
            {picked.length > 0 && (
              <Button variant="link" className="mt-2" onClick={() => setPicked([])}>
                Volver a todas
              </Button>
            )}
          </details>
        )}
        <div className="flex flex-wrap items-center gap-3">
          <Button variant="primary" disabled={!estimate || !llmReady || !!active} onClick={() => setConfirming({ error: null, busy: false })}>
            {resume ? "Reanudar corrida…" : "Lanzar corrida…"}
          </Button>
          <span className={`text-[13px] ${estimateError ? "text-bad" : "text-muted"}`}>
            {estimateError ??
              (estimate &&
                (resume
                  ? `${estimate.calls} llamadas al LLM pendientes de ${estimate.cases * 3 * estimate.repetitions}`
                  : `${estimate.cases} casos × 3 grupos × ${estimate.repetitions} ${estimate.repetitions === 1 ? "repetición" : "repeticiones"} = ${estimate.calls} llamadas al LLM`))}
            {active && " · ya hay una corrida en curso"}
          </span>
        </div>
      </Card>

      {logFor && <LogPanel runId={logFor} job={runs?.runs.find((r) => r.run_id === logFor)?.job ?? null} cancelling={cancelling} onCancel={cancel} onClose={() => setLogFor(null)} />}

      <Card className="overflow-hidden">
        <div className="border-b border-line px-4 py-3.5">
          <h3 className="text-base font-semibold">Corridas en out/</h3>
        </div>
        <div className="overflow-x-auto">
          <table className="w-full border-collapse">
            <thead>
              <tr className="text-left text-xs text-muted">
                {["Run id", "Última escritura", "Registros", "Estado", ""].map((h, i) => (
                  <th key={i} className="border-b border-line px-4 py-2.5 font-medium whitespace-nowrap">
                    {h}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {runs?.runs.length === 0 && (
                <tr>
                  <td colSpan={5} className="px-4 py-10 text-center text-muted">
                    Todavía no hay corridas.
                  </td>
                </tr>
              )}
              {runs?.runs.map((r) => (
                <tr key={r.run_id} className="border-b border-line last:border-b-0">
                  <td className="px-4 py-3 font-mono text-[12.5px] font-medium whitespace-nowrap">{r.run_id}</td>
                  <td className="px-4 py-3 whitespace-nowrap text-muted">{fmtDate(r.modified)}</td>
                  <td className="px-4 py-3 tabular-nums">{r.records}</td>
                  <td className="px-4 py-3">{r.job ? <Badge tone={JOB_STATUS[r.job.status].tone}>{JOB_STATUS[r.job.status].label}</Badge> : <span className="text-faint">—</span>}</td>
                  <td className="px-4 py-3 text-right whitespace-nowrap">
                    {r.has_log && (
                      <Button variant="link" onClick={() => setLogFor(r.run_id)}>
                        Ver log
                      </Button>
                    )}
                    {r.records > 0 && (
                      <Button variant="link" onClick={() => navigate(`/registros/${r.run_id}`)}>
                        Ver registros
                      </Button>
                    )}
                    {r.records > 0 && (
                      <Button variant="link" onClick={() => navigate(`/estadisticas/${r.run_id}`)}>
                        Ver estadísticas
                      </Button>
                    )}
                    {r.records > 0 && !active && (
                      <Button
                        variant="link"
                        onClick={() => {
                          setResume(r.run_id);
                          if (r.job) {
                            setSource(r.job.source === "fixtures" ? "fixtures" : "corpus");
                            setRepetitions(r.job.repetitions);
                          }
                          window.scrollTo({ top: 0, behavior: "smooth" });
                        }}
                      >
                        Reanudar
                      </Button>
                    )}
                    {r.records > 0 && <ExportMenu runId={r.run_id} onError={setError} />}
                    {r.records > 0 && (
                      <Button
                        variant="link"
                        disabled={!llmReady || !!reporting?.busy}
                        title={llmReady ? undefined : "Faltan las credenciales del LLM"}
                        onClick={() => setReporting({ run: r, busy: false, error: null })}
                      >
                        {reporting?.busy && reporting.run.run_id === r.run_id ? "Generando…" : "Generar reporte con IA"}
                      </Button>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Card>

      {confirming && estimate && (
        <Confirm
          title={resume ? `¿Reanudar ${resume}?` : "¿Lanzar la corrida?"}
          confirmLabel={`${resume ? "Reanudar" : "Lanzar"} ${estimate.calls} llamadas`}
          busy={confirming.busy}
          error={confirming.error}
          onConfirm={launch}
          onCancel={() => setConfirming(null)}
        >
          Hace <b className="text-ink">{estimate.calls} llamadas</b> al LLM ({health?.llm.models.join(", ")}) y consume cuota del proveedor.
          Los registros se agregan a <code className="font-mono">out/</code> a medida que termina cada caso.
        </Confirm>
      )}

      {reporting && (
        <Confirm
          title="¿Generar el reporte con IA?"
          confirmLabel="Generar reporte (1 llamada)"
          busy={reporting.busy}
          error={reporting.error}
          onConfirm={() => void generateReport(reporting.run)}
          onCancel={() => !reporting.busy && setReporting(null)}
        >
          Hace <b className="text-ink">1 llamada</b> al LLM ({health?.llm.models.join(", ")}) con las estadísticas de{" "}
          <code className="font-mono">{reporting.run.run_id}</code> y las bases metodológicas del proyecto, y consume cuota del proveedor. El
          texto lo redacta el modelo; las tablas del PDF salen de los registros. La respuesta queda guardada en{" "}
          <code className="font-mono">out/</code>.
        </Confirm>
      )}
    </div>
  );
}

/** Menú por fila que descarga los registros de la corrida en el formato elegido. */
function ExportMenu({ runId, onError }: { runId: string; onError: (message: string) => void }) {
  const [at, setAt] = useState<{ top: number; right: number } | null>(null);
  const [busy, setBusy] = useState(false);
  const root = useRef<HTMLSpanElement>(null);

  // El menú es `fixed` para que no lo recorte el `overflow` de la tabla.
  useEffect(() => {
    if (!at) return;
    const close = (e: Event) => {
      if (e instanceof KeyboardEvent ? e.key === "Escape" : !root.current?.contains(e.target as Node)) setAt(null);
    };
    const reset = () => setAt(null);
    document.addEventListener("mousedown", close);
    document.addEventListener("keydown", close);
    window.addEventListener("scroll", reset, true);
    window.addEventListener("resize", reset);
    return () => {
      document.removeEventListener("mousedown", close);
      document.removeEventListener("keydown", close);
      window.removeEventListener("scroll", reset, true);
      window.removeEventListener("resize", reset);
    };
  }, [at]);

  async function download(format: ExportFormat, mime: string) {
    setAt(null);
    setBusy(true);
    try {
      const rows = await api.records(runId, {});
      const url = URL.createObjectURL(new Blob([exportRecords(runId, rows, format)], { type: mime }));
      const a = document.createElement("a");
      a.href = url;
      a.download = `${runId}.${format}`;
      a.click();
      setTimeout(() => URL.revokeObjectURL(url), 0);
    } catch (e) {
      onError(errorText(e));
    } finally {
      setBusy(false);
    }
  }

  return (
    <span ref={root}>
      <Button
        variant="link"
        disabled={busy}
        aria-haspopup="menu"
        aria-expanded={!!at}
        onClick={(e) => {
          const r = e.currentTarget.getBoundingClientRect();
          setAt(at ? null : { top: r.bottom + 4, right: window.innerWidth - r.right });
        }}
      >
        {busy ? "Exportando…" : "Exportar ▾"}
      </Button>
      {at && (
        <span role="menu" style={at} className="fixed z-10 grid min-w-40 rounded-lg border border-line bg-surface py-1 text-left shadow-lg">
          {EXPORT_FORMATS.map(({ format, label, mime }) => (
            <button key={format} type="button" role="menuitem" onClick={() => void download(format, mime)} className="px-3 py-1.5 text-left hover:bg-hover">
              Exportar {label}
            </button>
          ))}
        </span>
      )}
    </span>
  );
}

function LogPanel({
  runId,
  job,
  cancelling,
  onCancel,
  onClose,
}: {
  runId: string;
  job: Job | null;
  cancelling: boolean;
  onCancel: (id: string) => void;
  onClose: () => void;
}) {
  const [text, setText] = useState("");
  const [status, setStatus] = useState<JobStatus | null>(job?.status ?? null);
  const [error, setError] = useState<string | null>(null);
  const [confirmCancel, setConfirmCancel] = useState(false);
  const pre = useRef<HTMLPreElement>(null);

  useEffect(() => {
    let offset = 0;
    let alive = true;
    let timer: ReturnType<typeof setTimeout> | undefined;
    setText("");
    const tick = () =>
      api
        .log(runId, offset)
        .then((chunk) => {
          if (!alive) return;
          offset = chunk.offset;
          if (chunk.text) setText((t) => t + chunk.text);
          setStatus(chunk.status);
          if (chunk.status === "running") timer = setTimeout(tick, 1000);
        })
        .catch((e: unknown) => alive && setError(errorText(e)));
    void tick();
    return () => {
      alive = false;
      clearTimeout(timer);
    };
  }, [runId]);

  useEffect(() => {
    const el = pre.current;
    if (el) el.scrollTop = el.scrollHeight;
  }, [text]);

  return (
    <Card className="grid gap-3 p-4">
      <div className="flex flex-wrap items-center gap-3">
        <h3 className="font-mono text-[13px] font-medium">{runId}</h3>
        {status && <Badge tone={JOB_STATUS[status].tone}>{JOB_STATUS[status].label}</Badge>}
        {job && <span className="text-[12.5px] text-muted">{job.calls} llamadas · {job.cases.length} casos · iniciada {fmtDate(job.started_at)}</span>}
        <span className="ml-auto flex gap-2">
          {status === "running" && (
            <Button variant="danger" small disabled={cancelling} onClick={() => setConfirmCancel(true)}>
              Cancelar corrida
            </Button>
          )}
          {status !== "running" && (
            <Button small onClick={() => navigate(`/registros/${runId}`)}>
              Ver registros
            </Button>
          )}
          <Button small onClick={onClose}>
            Cerrar log
          </Button>
        </span>
      </div>
      {error && <p className="text-bad">{error}</p>}
      <pre ref={pre} className="max-h-[360px] min-h-[120px] overflow-auto rounded-lg border border-line bg-code p-3 font-mono text-[12.5px] leading-relaxed whitespace-pre-wrap">
        {text || "Esperando salida…"}
      </pre>
      {confirmCancel && (
        <Confirm
          title="¿Cancelar la corrida?"
          confirmLabel="Cancelar corrida"
          danger
          onCancel={() => setConfirmCancel(false)}
          onConfirm={() => {
            setConfirmCancel(false);
            onCancel(runId);
          }}
        >
          Los registros de los casos ya terminados quedan en out/{runId}.jsonl; el caso en curso se pierde.
        </Confirm>
      )}
    </Card>
  );
}
