// Registros de una corrida, renglón por renglón. Sin conteos ni resúmenes: eso es
// análisis y queda fuera del repo (specs/mission.md §2, specs/ui.md).
import { useEffect, useMemo, useState } from "react";
import { api, errorText, type Outcome, type RecordRow, type Result, type RunInfo } from "../api";
import { Badge, Card, Drawer, fmtDate, Notice, type Tone } from "../components/ui";
import { showValue } from "../lib/rules";
import { navigate } from "../router";

const OUTCOME: Record<Outcome, { label: string; tone: Tone }> = {
  executed: { label: "ejecutó", tone: "accent" },
  blocked: { label: "bloqueado", tone: "warn" },
  runtime_error: { label: "error en ejecución", tone: "bad" },
  timeout: { label: "timeout", tone: "bad" },
  llm_error: { label: "error del LLM", tone: "neutral" },
};
const GROUP: Record<string, string> = { treatment: "Tratamiento", baseline1: "Baseline 1", baseline2: "Baseline 2" };
const FILTERS = [
  ["case_id", "Regla"],
  ["group", "Grupo"],
  ["outcome", "Desenlace"],
  ["model", "Modelo"],
] as const;
type FilterKey = (typeof FILTERS)[number][0];

const result = (r: Result | null | undefined) => (r ? showValue(r.value) : "—");

/** Consulta y filtra los registros de una corrida, mostrando el expected asociado. */
export function RecordsPage({ runId }: { runId: string | null }) {
  const [runs, setRuns] = useState<RunInfo[] | null>(null);
  const [rows, setRows] = useState<RecordRow[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [filters, setFilters] = useState<Record<FilterKey, string>>({ case_id: "", group: "", outcome: "", model: "" });
  const [detail, setDetail] = useState<RecordRow | null>(null);

  useEffect(() => {
    api
      .runs()
      .then((r) => setRuns(r.runs.filter((x) => x.records > 0)))
      .catch((e: unknown) => setError(errorText(e)));
  }, []);

  useEffect(() => {
    if (!runId) return;
    setRows(null);
    setError(null);
    api
      .records(runId, {})
      .then(setRows)
      .catch((e: unknown) => setError(errorText(e)));
  }, [runId]);

  const options = useMemo(() => {
    const out = {} as Record<FilterKey, string[]>;
    for (const [key] of FILTERS) out[key] = [...new Set((rows ?? []).map((r) => String(r[key])))].sort();
    return out;
  }, [rows]);
  const visible = (rows ?? []).filter((r) => FILTERS.every(([k]) => !filters[k] || String(r[k]) === filters[k]));

  return (
    <div className="grid gap-4">
      {error && <Notice tone="bad">{error}</Notice>}
      <Card className="overflow-hidden">
        <div className="flex flex-wrap items-center gap-2.5 border-b border-line px-4 py-3.5">
          <select
            aria-label="Corrida"
            value={runId ?? ""}
            onChange={(e) => navigate(e.target.value ? `/registros/${e.target.value}` : "/registros")}
            className="rounded-lg border border-line bg-surface px-2.5 py-[7px] font-mono text-[12.5px]"
          >
            <option value="">Elegí una corrida</option>
            {runs?.map((r) => (
              <option key={r.run_id} value={r.run_id}>
                {r.run_id}
              </option>
            ))}
          </select>
          {rows &&
            FILTERS.map(([key, label]) => (
              <select
                key={key}
                aria-label={label}
                value={filters[key]}
                onChange={(e) => setFilters((f) => ({ ...f, [key]: e.target.value }))}
                className="rounded-lg border border-line bg-surface px-2.5 py-[7px]"
              >
                <option value="">{label}: todos</option>
                {options[key].map((v) => (
                  <option key={v} value={v}>
                    {key === "group" ? (GROUP[v] ?? v) : key === "outcome" ? (OUTCOME[v as Outcome]?.label ?? v) : v}
                  </option>
                ))}
              </select>
            ))}
        </div>
        {!runId && <p className="px-4 py-10 text-center text-muted">Elegí una corrida para ver sus registros.</p>}
        {runId && rows === null && !error && <p className="px-4 py-10 text-center text-muted">Cargando registros…</p>}
        {rows && (
          <div className="overflow-x-auto">
            <table className="w-full border-collapse text-[13px]">
              <thead>
                <tr className="text-left text-xs text-muted">
                  {["Regla", "Escenario", "Grupo", "Rep.", "Modelo", "Desenlace", "Etapa", "Resultado", "Expected", "Error"].map((h) => (
                    <th key={h} className="border-b border-line px-3 py-2.5 font-medium whitespace-nowrap">
                      {h}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {visible.map((r, i) => (
                  <tr
                    key={i}
                    tabIndex={0}
                    onClick={() => setDetail(r)}
                    onKeyDown={(e) => e.key === "Enter" && setDetail(r)}
                    className="cursor-pointer border-b border-line last:border-b-0 hover:bg-hover"
                  >
                    <td className="px-3 py-2.5 font-mono text-[12px] whitespace-nowrap">{r.case_id}</td>
                    <td className="px-3 py-2.5 font-mono text-[12px] whitespace-nowrap text-muted">{r.scenario_id}</td>
                    <td className="px-3 py-2.5 whitespace-nowrap">{GROUP[r.group] ?? r.group}</td>
                    <td className="px-3 py-2.5 tabular-nums">{r.repetition}</td>
                    <td className="px-3 py-2.5 font-mono text-[12px] whitespace-nowrap text-muted">{r.model}</td>
                    <td className="px-3 py-2.5">
                      <Badge tone={OUTCOME[r.outcome].tone}>{OUTCOME[r.outcome].label}</Badge>
                    </td>
                    <td className="px-3 py-2.5 text-muted">{r.stage}</td>
                    <td className="px-3 py-2.5 font-mono text-[12px] whitespace-nowrap">{result(r.result)}</td>
                    <td className="px-3 py-2.5 font-mono text-[12px] whitespace-nowrap text-muted">{result(r.expected)}</td>
                    <td className="max-w-[260px] truncate px-3 py-2.5 font-mono text-[12px] text-bad" title={r.error?.message}>
                      {r.error?.code ?? ""}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Card>

      {detail && (
        <Drawer title={`${detail.case_id} · ${detail.scenario_id}`} subtitle={`${GROUP[detail.group]} · rep. ${detail.repetition}`} onClose={() => setDetail(null)}>
          <dl className="grid grid-cols-[max-content_1fr] gap-x-6 gap-y-2">
            {(
              [
                ["Modelo", detail.model],
                ["Momento", fmtDate(detail.timestamp)],
                ["Desenlace", OUTCOME[detail.outcome].label],
                ["Etapa", detail.stage],
                ["Resultado", detail.result ? `${result(detail.result)} (${detail.result.type})` : "—"],
                ["Expected", detail.expected ? `${result(detail.expected)} (${detail.expected.type})` : "— (la regla no está en corpus/)"],
                ["Duración", detail.duration_ms == null ? "—" : `${detail.duration_ms} ms`],
              ] as const
            ).map(([k, v]) => (
              <div key={k} className="contents">
                <dt className="text-muted">{k}</dt>
                <dd className="font-mono text-[12.5px]">{v}</dd>
              </div>
            ))}
          </dl>
          {detail.error && (
            <div className="grid gap-1.5">
              <span className="text-[12.5px] font-medium text-muted">Error</span>
              <pre className="overflow-x-auto rounded-lg border border-line bg-bad-soft p-3 font-mono text-[12.5px] whitespace-pre-wrap">
                {detail.error.code}: {detail.error.message}
              </pre>
            </div>
          )}
          <div className="grid gap-1.5">
            <span className="text-[12.5px] font-medium text-muted">Respuesta cruda del LLM (llm_raw)</span>
            <pre className="max-h-[420px] overflow-auto rounded-lg border border-line bg-code p-3 font-mono text-[12.5px] whitespace-pre-wrap">
              {detail.llm_raw ?? "— (la llamada al LLM falló)"}
            </pre>
          </div>
        </Drawer>
      )}
    </div>
  );
}
