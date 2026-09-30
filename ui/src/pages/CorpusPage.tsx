/** Vista de corpus: busca, filtra, valida, crea, edita y elimina reglas. */
import { useCallback, useEffect, useMemo, useState } from "react";
import { api, errorText, type CheckReport, type Rule } from "../api";
import { Badge, Button, Card, Confirm, Notice } from "../components/ui";
import { CheckResult, REVIEW, RuleEditor } from "./RuleEditor";

const statusOf = (r: Rule) => r.review?.status ?? "pendiente";

/** Carga las reglas desde la API y notifica cambios que afectan al estado global. */
export function CorpusPage({ onChanged }: { onChanged: () => void }) {
  const [rules, setRules] = useState<Rule[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [query, setQuery] = useState("");
  const [cat, setCat] = useState("");
  const [status, setStatus] = useState("");
  const [open, setOpen] = useState<{ rule: Rule | null } | null>(null);
  const [toDelete, setToDelete] = useState<{ rule: Rule; error: string | null } | null>(null);
  const [checking, setChecking] = useState(false);
  const [checks, setChecks] = useState<CheckReport[] | null>(null);

  const load = useCallback(() => {
    setError(null);
    api
      .rules()
      .then(setRules)
      .catch((e: unknown) => setError(errorText(e)));
  }, []);
  useEffect(load, [load]);

  const sorted = useMemo(
    () =>
      [...(rules ?? [])].sort(
        (a, b) => a.category - b.category || a.domain.localeCompare(b.domain) || a.case_id.localeCompare(b.case_id),
      ),
    [rules],
  );
  const visible = sorted.filter(
    (r) =>
      (!cat || String(r.category) === cat) &&
      (!status || statusOf(r) === status) &&
      (!query || `${r.case_id} ${r.domain} ${r.description}`.toLowerCase().includes(query.toLowerCase())),
  );
  const ids = useMemo(() => new Set((rules ?? []).map((r) => r.case_id)), [rules]);

  function saved(rule: Rule) {
    setRules((prev) => [...(prev ?? []).filter((r) => r.case_id !== rule.case_id), rule]);
    onChanged();
  }
  function deleted(id: string) {
    setRules((prev) => (prev ?? []).filter((r) => r.case_id !== id));
    setOpen(null);
    setToDelete(null);
    onChanged();
  }
  async function checkAll() {
    setChecking(true);
    setChecks(null);
    try {
      setChecks(await api.checkAll());
    } catch (e) {
      setError(errorText(e));
    } finally {
      setChecking(false);
    }
  }

  const failed = checks?.filter((c) => !c.ok) ?? [];

  return (
    <div className="grid gap-4">
      {error && (
        <Notice tone="bad">
          {error}{" "}
          <button type="button" className="font-medium text-accent hover:underline" onClick={load}>
            Reintentar
          </button>
        </Notice>
      )}
      {checks && (
        <Card className="grid gap-3 p-4">
          <div className="flex flex-wrap items-center gap-3">
            <Badge tone={failed.length ? "bad" : "ok"}>
              {checks.length - failed.length}/{checks.length} reglas sin errores
            </Badge>
            <Button variant="link" onClick={() => setChecks(null)}>
              Ocultar
            </Button>
          </div>
          {failed.map((c) => (
            <div key={c.case_id} className="grid gap-1.5">
              <span className="font-mono text-[12.5px] font-medium">{c.case_id}</span>
              <CheckResult report={c} />
            </div>
          ))}
        </Card>
      )}

      <Card className="overflow-hidden">
        <div className="flex flex-wrap items-center gap-2.5 border-b border-line px-4 py-3.5">
          <input
            type="search"
            aria-label="Buscar reglas"
            placeholder="Buscar por id, dominio o enunciado"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            className="min-w-0 flex-[1_1_220px] rounded-lg border border-line bg-bg px-3 py-[7px] focus:border-accent focus:outline-none"
          />
          <select aria-label="Categoría" value={cat} onChange={(e) => setCat(e.target.value)} className="rounded-lg border border-line bg-surface px-2.5 py-[7px]">
            <option value="">Todas las categorías</option>
            <option value="1">Cat. 1 · estructura</option>
            <option value="2">Cat. 2 · tipos</option>
            <option value="3">Cat. 3 · lógica</option>
          </select>
          <select aria-label="Estado de revisión" value={status} onChange={(e) => setStatus(e.target.value)} className="rounded-lg border border-line bg-surface px-2.5 py-[7px]">
            <option value="">Todos los estados</option>
            {Object.entries(REVIEW).map(([k, v]) => (
              <option key={k} value={k}>
                {v.label}
              </option>
            ))}
          </select>
          <span className="ml-auto text-[13px] text-muted tabular-nums">
            {visible.length} de {sorted.length} reglas
          </span>
          <Button disabled={checking || !sorted.length} onClick={checkAll}>
            {checking ? "Verificando…" : "Verificar todas"}
          </Button>
          <Button variant="primary" onClick={() => setOpen({ rule: null })}>
            + Nueva regla
          </Button>
        </div>
        <div className="overflow-x-auto">
          <table className="w-full border-collapse">
            <thead>
              <tr className="text-left text-xs text-muted">
                {["Id", "Cat.", "Dominio", "Enunciado", "Escenarios", "Origen", "Revisión", ""].map((h, i) => (
                  <th key={i} className={`border-b border-line px-4 py-2.5 font-medium whitespace-nowrap ${h === "Escenarios" ? "text-right" : ""}`}>
                    {h}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {rules === null && !error && (
                <tr>
                  <td colSpan={8} className="px-4 py-10 text-center text-muted">
                    Cargando reglas…
                  </td>
                </tr>
              )}
              {rules !== null && visible.length === 0 && (
                <tr>
                  <td colSpan={8} className="px-4 py-10 text-center text-muted">
                    {sorted.length ? "Ninguna regla coincide con la búsqueda." : "Todavía no hay reglas en corpus/. Creá la primera con “Nueva regla”."}
                  </td>
                </tr>
              )}
              {visible.map((r) => {
                const review = REVIEW[statusOf(r)];
                return (
                  <tr
                    key={r.case_id}
                    tabIndex={0}
                    onClick={() => setOpen({ rule: r })}
                    onKeyDown={(e) => e.key === "Enter" && setOpen({ rule: r })}
                    className="cursor-pointer border-b border-line align-top last:border-b-0 hover:bg-hover"
                  >
                    <td className="px-4 py-3 font-mono text-[12.5px] font-medium whitespace-nowrap">{r.case_id}</td>
                    <td className="px-4 py-3">
                      <span className="rounded-md bg-accent-soft px-2 py-px font-mono text-xs text-accent">{r.category}</span>
                    </td>
                    <td className="px-4 py-3">{r.domain}</td>
                    <td className="max-w-[440px] min-w-[240px] px-4 py-3 text-muted">
                      <span className="line-clamp-2">{r.description}</span>
                    </td>
                    <td className="px-4 py-3 text-right tabular-nums">{r.scenarios.length}</td>
                    <td className="px-4 py-3 text-[12.5px] whitespace-nowrap text-muted">{r.source.kind === "adapted" ? "adaptada" : "propia"}</td>
                    <td className="px-4 py-3">
                      <Badge tone={review.tone}>{review.label}</Badge>
                    </td>
                    <td className="px-4 py-3 text-right whitespace-nowrap">
                      <Button variant="link" onClick={(e) => (e.stopPropagation(), setOpen({ rule: r }))}>
                        Editar
                      </Button>
                      <Button variant="link-danger" onClick={(e) => (e.stopPropagation(), setToDelete({ rule: r, error: null }))}>
                        Eliminar
                      </Button>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </Card>

      {open && (
        <RuleEditor
          key={open.rule?.case_id ?? "nueva"}
          initial={open.rule}
          existing={ids}
          onClose={() => setOpen(null)}
          onSaved={saved}
          onDeleted={deleted}
        />
      )}
      {toDelete && (
        <Confirm
          title={`¿Eliminar ${toDelete.rule.case_id}?`}
          confirmLabel="Eliminar"
          danger
          error={toDelete.error}
          onCancel={() => setToDelete(null)}
          onConfirm={() =>
            api
              .deleteRule(toDelete.rule.case_id, toDelete.rule._version ?? "")
              .then(() => deleted(toDelete.rule.case_id))
              .catch((e: unknown) => setToDelete({ ...toDelete, error: errorText(e) }))
          }
        >
          Se borra el archivo {toDelete.rule._file} de corpus/. Si la regla la escribe un script de corpus/tools/, volvería a aparecer al
          correrlo.
        </Confirm>
      )}
    </div>
  );
}
