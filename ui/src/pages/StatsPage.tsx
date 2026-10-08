// Estadísticas de una corrida, calculadas en el navegador con lib/stats.ts
// a partir de sus registros (specs/ui.md §Estadísticas).
import { useEffect, useMemo, useState, type ReactNode } from "react";
import { api, errorText, type RecordRow, type Rule, type RunInfo } from "../api";
import { Button, Card, Notice, Tab, type Tone } from "../components/ui";
import {
  blockedStages,
  durationByGroup,
  errorsByGroup,
  fmtRate,
  generations,
  GROUPS,
  OUTCOMES,
  outcomesByGroup,
  passBy,
  passByGroup,
  type BreakdownKey,
  type CountRow,
  type PassCount,
} from "../lib/stats";
import { navigate } from "../router";
import { GROUP, OUTCOME } from "./RecordsPage";

const BAR: Record<Tone, string> = { accent: "bg-accent", ok: "bg-ok", warn: "bg-warn", bad: "bg-bad", neutral: "bg-faint" };
const BREAKDOWN: [BreakdownKey, string][] = [
  ["rule", "Regla"],
  ["category", "Categoría"],
  ["domain", "Dominio"],
];
const ms = (v: number | null) => (v === null ? "—" : `${Math.round(v).toLocaleString("es-AR")} ms`);
const th = "border-b border-line px-4 py-2.5 font-medium whitespace-nowrap";
const td = "px-4 py-2.5";

/** Barra fina proporcional; el número va siempre al lado, así no depende del color. */
function Meter({ share, tone = "accent" }: { share: number; tone?: Tone }) {
  return (
    <span className="block h-1.5 w-full min-w-12 overflow-hidden rounded-full bg-hover" aria-hidden>
      <span className={`block h-full rounded-full ${BAR[tone]}`} style={{ width: `${Math.round(share * 100)}%` }} />
    </span>
  );
}

function Table({ head, children }: { head: ReactNode[]; children: ReactNode }) {
  return (
    <div className="overflow-x-auto">
      <table className="w-full border-collapse text-[13px]">
        <thead>
          <tr className="text-left text-xs text-muted">
            {head.map((h, i) => (
              <th key={i} className={`${th} ${i ? "text-right" : ""}`}>
                {h}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>{children}</tbody>
      </table>
    </div>
  );
}

function Section({ title, help, children }: { title: string; help?: string; children: ReactNode }) {
  return (
    <Card className="overflow-hidden">
      <div className="border-b border-line px-4 py-3.5">
        <h3 className="text-base font-semibold">{title}</h3>
        {help && <p className="mt-0.5 max-w-[80ch] text-[12.5px] text-muted">{help}</p>}
      </div>
      {children}
    </Card>
  );
}

const passText = (p: PassCount) => (p.pass + p.fail ? `${p.pass}/${p.pass + p.fail}` : "");

function CountTable({ first, rows }: { first: string; rows: CountRow[] }) {
  return (
    <Table head={[first, ...GROUPS.map((g) => GROUP[g]), "Total"]}>
      {rows.map((r) => (
        <tr key={r.key} className="border-b border-line last:border-b-0">
          <td className={`${td} font-mono text-[12px]`}>{r.key}</td>
          {GROUPS.map((g) => (
            <td key={g} className={`${td} text-right tabular-nums ${r.byGroup[g] ? "" : "text-faint"}`}>
              {r.byGroup[g]}
            </td>
          ))}
          <td className={`${td} text-right font-medium tabular-nums`}>{r.total}</td>
        </tr>
      ))}
    </Table>
  );
}

export function StatsPage({ runId }: { runId: string | null }) {
  const [runs, setRuns] = useState<RunInfo[] | null>(null);
  const [rows, setRows] = useState<RecordRow[] | null>(null);
  const [rules, setRules] = useState<ReadonlyMap<string, Rule>>(new Map());
  const [error, setError] = useState<string | null>(null);
  const [breakdown, setBreakdown] = useState<BreakdownKey>("rule");

  useEffect(() => {
    api
      .runs()
      .then((r) => setRuns(r.runs.filter((x) => x.records > 0)))
      .catch((e: unknown) => setError(errorText(e)));
    api
      .rules()
      .then((rs) => setRules(new Map(rs.map((r) => [r.case_id, r]))))
      .catch(() => setRules(new Map()));
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

  const stats = useMemo(() => {
    if (!rows) return null;
    const gens = generations(rows);
    return {
      gens,
      pass: passByGroup(gens),
      outcomes: outcomesByGroup(rows),
      stages: blockedStages(rows),
      errors: errorsByGroup(rows),
      duration: durationByGroup(rows),
    };
  }, [rows]);
  const breakdownRows = useMemo(() => (stats ? passBy(stats.gens, breakdown, rules) : []), [stats, breakdown, rules]);

  return (
    <div className="grid gap-4">
      {error && <Notice tone="bad">{error}</Notice>}

      <Card className="flex flex-wrap items-center gap-2.5 px-4 py-3.5">
        <select
          aria-label="Corrida"
          value={runId ?? ""}
          onChange={(e) => navigate(e.target.value ? `/estadisticas/${e.target.value}` : "/estadisticas")}
          className="rounded-lg border border-line bg-surface px-2.5 py-[7px] font-mono text-[12.5px]"
        >
          <option value="">Elegí una corrida</option>
          {runs?.map((r) => (
            <option key={r.run_id} value={r.run_id}>
              {r.run_id}
            </option>
          ))}
        </select>
        {stats && (
          <span className="text-[13px] text-muted">
            {rows?.length} renglones · {stats.gens.length} generaciones
          </span>
        )}
        {runId && (
          <Button variant="link" className="ml-auto" onClick={() => navigate(`/registros/${runId}`)}>
            Ver registros
          </Button>
        )}
      </Card>

      {!runId && <p className="px-4 py-10 text-center text-muted">Elegí una corrida para ver sus estadísticas.</p>}
      {runId && !stats && !error && <p className="px-4 py-10 text-center text-muted">Cargando registros…</p>}

      {stats && (
        <>
          <Section
            title="pass@1 por grupo"
            help="Generaciones (regla × grupo × repetición) que aciertan el expected en todos sus escenarios, sobre las que tienen expected."
          >
            <ul className="grid gap-px bg-line sm:grid-cols-3">
              {GROUPS.map((g) => {
                const p = stats.pass[g];
                return (
                  <li key={g} className="grid content-start gap-2 bg-surface px-4 py-4">
                    <span className="text-[12.5px] font-medium text-muted">{GROUP[g]}</span>
                    <span className="text-[28px] leading-none font-semibold tabular-nums">{fmtRate(p.rate)}</span>
                    <Meter share={p.rate ?? 0} />
                    <span className="text-[12.5px] text-muted">
                      {p.pass + p.fail ? `${p.pass} de ${p.pass + p.fail} generaciones` : "Sin generaciones con expected"}
                      {p.noExpected > 0 && ` · ${p.noExpected} sin expected`}
                    </span>
                  </li>
                );
              })}
            </ul>
          </Section>

          <Section title="Desenlaces por grupo" help="Renglones por desenlace: uno por escenario, así un bloqueo cuenta una vez por cada escenario de la regla.">
            <Table head={["Grupo", ...OUTCOMES.map((o) => OUTCOME[o].label), "Total"]}>
              {GROUPS.map((g) => {
                const counts = stats.outcomes[g];
                const total = OUTCOMES.reduce((s, o) => s + counts[o], 0);
                return (
                  <tr key={g} className="border-b border-line last:border-b-0">
                    <td className={`${td} whitespace-nowrap`}>{GROUP[g]}</td>
                    {OUTCOMES.map((o) => (
                      <td key={o} className={td} title={`${GROUP[g]} · ${OUTCOME[o].label}: ${counts[o]} de ${total}`}>
                        <span className={`block text-right tabular-nums ${counts[o] ? "" : "text-faint"}`}>{counts[o]}</span>
                        <Meter share={total ? counts[o] / total : 0} tone={OUTCOME[o].tone} />
                      </td>
                    ))}
                    <td className={`${td} text-right font-medium tabular-nums`}>{total}</td>
                  </tr>
                );
              })}
            </Table>
            {stats.stages.length > 0 && (
              <div className="border-t border-line">
                <p className="px-4 pt-3 text-[12.5px] font-medium text-muted">Bloqueos por etapa</p>
                <CountTable first="Etapa" rows={stats.stages} />
              </div>
            )}
          </Section>

          <Section title="Desglose de pass@1">
            <div role="tablist" className="flex gap-0.5 border-b border-line px-3">
              {BREAKDOWN.map(([key, label]) => (
                <Tab key={key} selected={breakdown === key} onClick={() => setBreakdown(key)}>
                  {label}
                </Tab>
              ))}
            </div>
            <Table head={[BREAKDOWN.find(([k]) => k === breakdown)![1], ...GROUPS.map((g) => GROUP[g])]}>
              {breakdownRows.map((r) => (
                <tr key={r.label} className="border-b border-line last:border-b-0">
                  <td className={`${td} ${breakdown === "rule" ? "font-mono text-[12px]" : ""}`}>{r.label}</td>
                  {GROUPS.map((g) => {
                    const p = r.byGroup[g];
                    return (
                      <td key={g} className={`${td} text-right whitespace-nowrap tabular-nums`} title={p.noExpected ? `${p.noExpected} sin expected` : undefined}>
                        <span className={p.rate === null ? "text-faint" : ""}>{fmtRate(p.rate)}</span>
                        <span className="ml-2 text-[12px] text-muted">{passText(p)}</span>
                      </td>
                    );
                  })}
                </tr>
              ))}
            </Table>
          </Section>

          <div className="grid gap-4 lg:grid-cols-2">
            <Section title="Duración" help="duration_ms de cada renglón que lo tiene.">
              <Table head={["Grupo", "n", "Media", "Mediana"]}>
                {GROUPS.map((g) => {
                  const d = stats.duration[g];
                  return (
                    <tr key={g} className="border-b border-line last:border-b-0">
                      <td className={td}>{GROUP[g]}</td>
                      <td className={`${td} text-right tabular-nums`}>{d.n}</td>
                      <td className={`${td} text-right tabular-nums`}>{ms(d.mean)}</td>
                      <td className={`${td} text-right tabular-nums`}>{ms(d.median)}</td>
                    </tr>
                  );
                })}
              </Table>
            </Section>
            <Section title="Códigos de error" help="Renglones por error.code, de mayor a menor.">
              {stats.errors.length ? <CountTable first="Código" rows={stats.errors} /> : <p className="px-4 py-6 text-center text-muted">Ningún renglón tiene error.</p>}
            </Section>
          </div>
        </>
      )}
    </div>
  );
}
