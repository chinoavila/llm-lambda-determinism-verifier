/** Revisión a ciegas de los expected de una regla (lib/review.ts). */
import { useState } from "react";
import type { Rule } from "../api";
import { Badge, Button, inputClass } from "../components/ui";
import { TablePagination, usePagination } from "../components/pagination";
import { blindCompare, blindSummary } from "../lib/review";
import { showValue } from "../lib/rules";

const showEnv = (env: Record<string, unknown>) =>
  Object.entries(env)
    .map(([k, v]) => `${k} = ${showValue(v)}`)
    .join(", ");

/** Muestra solo el enunciado y los env; el expected aparece recién al comparar. */
export function BlindReview({ rule, reviewer, onComment }: { rule: Rule; reviewer: string; onComment: (text: string) => void }) {
  const [answers, setAnswers] = useState<Record<string, string> | null>(null);
  const [compared, setCompared] = useState(false);
  const [saved, setSaved] = useState(false);

  if (!answers)
    return (
      <div className="grid gap-2 rounded-lg border border-line px-3.5 py-3">
        <p className="text-[13px] font-semibold">Revisión a ciegas de los expected</p>
        <p className="text-[12.5px] text-muted">
          Leés solo el enunciado y los datos de cada escenario, anotás el resultado que esperás y recién después se compara con el expected que
          calculó el engine. Para que valga, no mires antes la pestaña de escenarios.
        </p>
        <div>
          <Button small disabled={!rule.scenarios.length} onClick={() => setAnswers({})}>
            Empezar revisión a ciegas
          </Button>
        </div>
      </div>
    );

  const rows = blindCompare(rule, answers);
  const scenarios = usePagination(rule.scenarios.map((scenario, index) => ({ scenario, index })), rule.case_id);
  const matched = rows.filter((r) => r.match).length;
  return (
    <div className="grid gap-3 rounded-lg border border-line px-3.5 py-3">
      <p className="text-[13px] font-semibold">Revisión a ciegas de los expected</p>
      <p className="whitespace-pre-wrap">{rule.description}</p>
      <div className="overflow-x-auto">
        <table className="w-full border-collapse text-[13px]">
          <thead>
            <tr className="text-left text-xs text-muted">
              {["Escenario", "Datos", "Tu resultado", ...(compared ? ["Expected", ""] : [])].map((h) => (
                <th key={h} className="border-b border-line px-2 py-2 font-medium whitespace-nowrap">
                  {h}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {scenarios.items.map(({ scenario: s, index: i }) => {
              const row = rows[i]!;
              return (
                <tr key={s.scenario_id} className="border-b border-line align-top last:border-b-0">
                  <td className="px-2 py-2 font-mono text-[12px] whitespace-nowrap">{s.scenario_id}</td>
                  <td className="px-2 py-2 font-mono text-[12px]">{showEnv(s.env)}</td>
                  <td className="px-2 py-2">
                    <input
                      aria-label={`Resultado de ${s.scenario_id}`}
                      className={`${inputClass} w-36 font-mono text-[12px]`}
                      placeholder={s.expected?.type ?? ""}
                      disabled={compared}
                      value={answers[s.scenario_id] ?? ""}
                      onChange={(e) => setAnswers({ ...answers, [s.scenario_id]: e.target.value })}
                    />
                  </td>
                  {compared && (
                    <>
                      <td className="px-2 py-2 font-mono text-[12px]">{s.expected ? showValue(s.expected.value) : "—"}</td>
                      <td className="px-2 py-2">
                        {row.match === null ? <Badge>sin comparar</Badge> : row.match ? <Badge tone="ok">coincide</Badge> : <Badge tone="bad">difiere</Badge>}
                      </td>
                    </>
                  )}
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
      <TablePagination pagination={scenarios} label="escenarios de revisión" />
      <div className="flex flex-wrap items-center gap-2.5">
        {!compared ? (
          <Button small variant="primary" onClick={() => setCompared(true)}>
            Comparar con los expected
          </Button>
        ) : (
          <>
            <span className="text-[13px] tabular-nums">
              {matched} de {rows.length} coinciden
            </span>
            <Button
              small
              disabled={saved || !reviewer.trim()}
              title={reviewer.trim() ? undefined : "Completá tu nombre abajo"}
              onClick={() => {
                onComment(blindSummary(rows));
                setSaved(true);
              }}
            >
              {saved ? "Agregado a los comentarios" : "Agregar el resultado como comentario"}
            </Button>
          </>
        )}
        <Button
          small
          variant="link"
          onClick={() => {
            setAnswers(null);
            setCompared(false);
            setSaved(false);
          }}
        >
          Cerrar
        </Button>
      </div>
    </div>
  );
}
