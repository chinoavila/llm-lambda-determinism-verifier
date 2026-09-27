import { useMemo, useState, type ReactNode } from "react";
import { api, ApiError, errorText, type BaseType, type CheckReport, type ReviewStatus, type Rule } from "../api";
import { AstPreview, Badge, Button, Confirm, Drawer, Errors, Field, fmtDate, inputClass, Notice, Tab } from "../components/ui";
import { blankRule, defaultValue, parseCell, parseExpected, TYPES, validate, valueFits, type Errors as ErrorMap, type Tab as TabKey } from "../lib/rules";

export const DOMAINS = ["fiscal", "salud", "credito", "seguros", "laboral"];
export const REVIEW: Record<ReviewStatus, { label: string; tone: "neutral" | "ok" | "bad" }> = {
  pendiente: { label: "Pendiente", tone: "neutral" },
  aprobada: { label: "Aprobada", tone: "ok" },
  cambios: { label: "Requiere cambios", tone: "bad" },
};
const TABS: [TabKey, string][] = [
  ["general", "General"],
  ["escenarios", "Variables y escenarios"],
  ["ast", "AST"],
  ["python", "Python"],
  ["revision", "Revisión"],
];

const readReviewer = () => {
  try {
    return localStorage.getItem("reviewer") ?? "";
  } catch {
    return "";
  }
};

let nextKey = 0;
const newKey = () => ++nextKey;

export function RuleEditor({
  initial,
  existing,
  onClose,
  onSaved,
  onDeleted,
}: {
  initial: Rule | null;
  existing: ReadonlySet<string>;
  onClose: () => void;
  onSaved: (rule: Rule) => void;
  onDeleted: (id: string) => void;
}) {
  const [isNew, setIsNew] = useState(initial === null);
  const [draft, setDraft] = useState<Rule>(() => structuredClone(initial ?? blankRule()));
  const [rowKeys, setRowKeys] = useState<number[]>(() => draft.scenarios.map(newKey));
  const [tab, setTab] = useState<TabKey>("general");
  const [astText, setAstText] = useState(() => JSON.stringify(draft.canonical_ast, null, 2));
  const [astError, setAstError] = useState<string | null>(null);
  const [errors, setErrors] = useState<ErrorMap>({});
  const [message, setMessage] = useState<{ text: string; error: boolean } | null>(null);
  const [check, setCheck] = useState<CheckReport | null>(null);
  const [saving, setSaving] = useState(false);
  const [deleting, setDeleting] = useState<{ error: string | null } | null>(null);
  const [reviewer, setReviewer] = useState(readReviewer);
  const [comment, setComment] = useState("");

  const edit = (fn: (r: Rule) => void) =>
    setDraft((prev) => {
      const next = structuredClone(prev);
      fn(next);
      return next;
    });
  const vars = Object.keys(draft.gamma);
  const review = draft.review ?? { status: "pendiente" as const, comments: [] };

  async function save() {
    const errs = validate(draft, isNew, existing, astError);
    setErrors(errs);
    const bad = Object.keys(errs) as TabKey[];
    if (bad.length) {
      if (!errs[tab]) setTab(bad[0]!);
      setMessage({ text: "Hay datos por corregir en las pestañas marcadas.", error: true });
      return;
    }
    setSaving(true);
    setMessage({ text: "Guardando y verificando con check-case…", error: false });
    try {
      const saved = isNew ? await api.createRule(draft) : await api.updateRule(draft);
      setDraft(structuredClone(saved.rule));
      setRowKeys(saved.rule.scenarios.map(newKey));
      setAstText(JSON.stringify(saved.rule.canonical_ast, null, 2));
      setIsNew(false);
      setCheck(saved.check);
      setMessage({ text: saved.check.ok ? "Guardada y verificada." : "Guardada, pero check-case encontró errores.", error: !saved.check.ok });
      onSaved(saved.rule);
    } catch (e) {
      setMessage({ text: errorText(e), error: true });
    } finally {
      setSaving(false);
    }
  }

  async function remove() {
    try {
      await api.deleteRule(draft.case_id, draft._version ?? "");
      onDeleted(draft.case_id);
    } catch (e) {
      setDeleting({ error: e instanceof ApiError && e.status === 409 ? e.message : errorText(e) });
    }
  }

  const domains = useMemo(() => [...new Set([...DOMAINS, draft.domain].filter(Boolean))], [draft.domain]);

  const body = {
    general: (
      <>
        <Errors messages={errors.general} />
        {draft.generated_by && (
          <Notice>
            Esta regla la escribe <code className="font-mono">{draft.generated_by}</code>. Un cambio hecho acá se pierde si se vuelve a
            correr el script: llevalo también al script.
          </Notice>
        )}
        <div className="grid grid-cols-[repeat(auto-fit,minmax(180px,1fr))] gap-3.5">
          <Field label="Id" help={isNew ? "Por ejemplo FIS-C2-DEDUCCION. No se puede cambiar después." : undefined}>
            {(id) => (
              <input id={id} className={`${inputClass} font-mono`} value={draft.case_id} disabled={!isNew} onChange={(e) => edit((r) => void (r.case_id = e.target.value.trim()))} />
            )}
          </Field>
          <Field label="Categoría">
            {(id) => (
              <select id={id} className={inputClass} value={draft.category} onChange={(e) => edit((r) => void (r.category = Number(e.target.value)))}>
                <option value={1}>1 · estructura larga o anidada</option>
                <option value={2}>2 · tipos y alcance</option>
                <option value={3}>3 · inconsistencias lógicas</option>
              </select>
            )}
          </Field>
          <Field label="Dominio">
            {(id) => (
              <>
                <input id={id} list={`${id}-list`} className={inputClass} value={draft.domain} onChange={(e) => edit((r) => void (r.domain = e.target.value.trim()))} />
                <datalist id={`${id}-list`}>
                  {domains.map((d) => (
                    <option key={d} value={d} />
                  ))}
                </datalist>
              </>
            )}
          </Field>
        </div>
        <Field label="Enunciado" help="Es lo único que ve el LLM, junto con las variables. No nombres construcciones del DSL.">
          {(id) => <textarea id={id} rows={7} className={inputClass} value={draft.description} onChange={(e) => edit((r) => void (r.description = e.target.value))} />}
        </Field>
        <p className="mt-1.5 text-[13px] font-semibold">Fuente</p>
        <Field label="Origen">
          {(id) => (
            <select
              id={id}
              className={inputClass}
              value={draft.source.kind}
              onChange={(e) => edit((r) => void (r.source = e.target.value === "adapted" ? { ...r.source, kind: "adapted" } : { kind: "original" }))}
            >
              <option value="original">Propia (escrita para el corpus)</option>
              <option value="adapted">Adaptada de una fuente real</option>
            </select>
          )}
        </Field>
        {draft.source.kind === "adapted" && (
          <div className="grid grid-cols-[repeat(auto-fit,minmax(220px,1fr))] gap-3.5">
            <Field label="Referencia">
              {(id) => <input id={id} className={inputClass} value={draft.source.reference ?? ""} onChange={(e) => edit((r) => void (r.source.reference = e.target.value))} />}
            </Field>
            <Field label="Licencia">
              {(id) => <input id={id} className={inputClass} value={draft.source.license ?? ""} onChange={(e) => edit((r) => void (r.source.license = e.target.value))} />}
            </Field>
          </div>
        )}
      </>
    ),

    escenarios: (
      <>
        <Errors messages={errors.escenarios} />
        <p className="text-[13px] font-semibold">Variables (Γ)</p>
        <div className="overflow-x-auto">
          <table className="w-full border-collapse text-[13px]">
            <thead>
              <tr className="text-left text-xs text-muted">
                <th className="border-b border-line px-2 py-1.5 font-medium">Variable</th>
                <th className="border-b border-line px-2 py-1.5 font-medium">Tipo</th>
                <th className="w-px border-b border-line" />
              </tr>
            </thead>
            <tbody>
              {vars.map((name) => (
                <tr key={name}>
                  <td className="border-b border-line p-1">
                    <input
                      aria-label="Nombre de la variable"
                      defaultValue={name}
                      className={cellClass}
                      onBlur={(e) => {
                        const nn = e.target.value.trim();
                        if (!nn || nn === name || nn in draft.gamma) {
                          e.target.value = name;
                          return;
                        }
                        edit((r) => {
                          r.gamma = Object.fromEntries(Object.entries(r.gamma).map(([k, t]) => [k === name ? nn : k, t]));
                          for (const s of r.scenarios) {
                            s.env[nn] = s.env[name];
                            delete s.env[name];
                          }
                        });
                      }}
                    />
                  </td>
                  <td className="border-b border-line p-1">
                    <select aria-label={`Tipo de ${name}`} className={cellClass} value={draft.gamma[name]} onChange={(e) => edit((r) => void (r.gamma[name] = e.target.value as BaseType))}>
                      {TYPES.map((t) => (
                        <option key={t}>{t}</option>
                      ))}
                    </select>
                  </td>
                  <td className="border-b border-line p-1">
                    <Button variant="link-danger" onClick={() => edit((r) => {
                      delete r.gamma[name];
                      for (const s of r.scenarios) delete s.env[name];
                    })}>
                      Quitar
                    </Button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <div>
          <Button
            small
            onClick={() =>
              edit((r) => {
                let i = 1;
                while (`variable_${i}` in r.gamma) i++;
                r.gamma[`variable_${i}`] = "Int";
                for (const s of r.scenarios) s.env[`variable_${i}`] = 0;
              })
            }
          >
            + Agregar variable
          </Button>
        </div>

        <p className="mt-1.5 text-[13px] font-semibold">Escenarios ({draft.scenarios.length})</p>
        <p className="text-[12.5px] text-faint">
          Un valor justo en cada límite y uno a cada lado. El expected lo calcula el engine al guardar: si lo corregís a mano y no coincide
          con el AST, check-case lo marca, y esa diferencia es la que hay que discutir.
        </p>
        <div className="overflow-x-auto">
          <table className="w-full border-collapse text-[13px]">
            <thead>
              <tr className="text-left text-xs text-muted">
                <th className="border-b border-line px-2 py-1.5 font-medium">Escenario</th>
                {vars.map((v) => (
                  <th key={v} className="border-b border-line px-2 py-1.5 font-medium whitespace-nowrap">
                    {v}
                  </th>
                ))}
                <th className="border-b border-line px-2 py-1.5 font-medium">Expected</th>
                <th className="w-px border-b border-line" />
              </tr>
            </thead>
            <tbody>
              {draft.scenarios.map((s, idx) => {
                const key = rowKeys[idx] ?? idx;
                return (
                  <tr key={key}>
                    <td className="border-b border-line p-1">
                      <input aria-label="Id del escenario" defaultValue={s.scenario_id} className={cellClass} onChange={(e) => edit((r) => void (r.scenarios[idx]!.scenario_id = e.target.value.trim()))} />
                    </td>
                    {vars.map((v) => {
                      const type = draft.gamma[v]!;
                      if (type === "Bool")
                        return (
                          <td key={v} className="border-b border-line p-1">
                            <select aria-label={`${v} en ${s.scenario_id}`} className={cellClass} value={String(s.env[v] === true)} onChange={(e) => edit((r) => void (r.scenarios[idx]!.env[v] = e.target.value === "true"))}>
                              <option value="true">true</option>
                              <option value="false">false</option>
                            </select>
                          </td>
                        );
                      return (
                        <td key={`${v}-${type}`} className="border-b border-line p-1">
                          <input
                            aria-label={`${v} en ${s.scenario_id}`}
                            defaultValue={s.env[v] == null ? "" : String(s.env[v])}
                            className={`${cellClass} ${valueFits(type, s.env[v]) ? "" : "border-bad bg-bad-soft"}`}
                            onChange={(e) => edit((r) => void (r.scenarios[idx]!.env[v] = parseCell(type, e.target.value)))}
                          />
                        </td>
                      );
                    })}
                    <td className="border-b border-line p-1">
                      <input
                        aria-label={`Expected de ${s.scenario_id}`}
                        defaultValue={s.expected ? String(s.expected.value) : ""}
                        placeholder="lo calcula el engine"
                        title={s.expected ? s.expected.type : "Vacío: se calcula al guardar"}
                        className={cellClass}
                        onChange={(e) =>
                          edit((r) => {
                            const sc = r.scenarios[idx]!;
                            const parsed = parseExpected(e.target.value, sc.expected);
                            if (parsed) sc.expected = parsed;
                            else delete sc.expected;
                          })
                        }
                      />
                    </td>
                    <td className="border-b border-line p-1">
                      <Button
                        variant="link-danger"
                        onClick={() => {
                          edit((r) => void r.scenarios.splice(idx, 1));
                          setRowKeys((k) => k.filter((_, i) => i !== idx));
                        }}
                      >
                        Quitar
                      </Button>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
        <div>
          <Button
            small
            onClick={() => {
              edit((r) => void r.scenarios.push({ scenario_id: `V${r.scenarios.length + 1}`, env: Object.fromEntries(vars.map((v) => [v, defaultValue(r.gamma[v]!)])) }));
              setRowKeys((k) => [...k, newKey()]);
            }}
          >
            + Agregar escenario
          </Button>
        </div>
      </>
    ),

    ast: (
      <>
        <Errors messages={errors.ast} />
        <div className="grid gap-1.5">
          <span className="text-[12.5px] font-medium text-muted">Vista legible</span>
          {astError ? <p className="text-[12.5px] text-bad">{astError}</p> : <AstPreview expr={draft.canonical_ast.expr} />}
        </div>
        <Field label="AST canónico (JSON, contracts/ast-schema.json)" help="Es la interpretación correcta del enunciado. El engine lo ejecuta para calcular los expected.">
          {(id) => (
            <textarea
              id={id}
              rows={16}
              spellCheck={false}
              className={`${inputClass} bg-code font-mono text-[12.5px]`}
              value={astText}
              onChange={(e) => {
                setAstText(e.target.value);
                try {
                  const v: unknown = JSON.parse(e.target.value);
                  if (!v || typeof v !== "object" || !("expr" in v) || typeof v.expr !== "object") throw new Error('falta "expr"');
                  edit((r) => void (r.canonical_ast = v as Rule["canonical_ast"]));
                  setAstError(null);
                } catch (err) {
                  setAstError(`JSON inválido: ${errorText(err)}`);
                }
              }}
            />
          )}
        </Field>
      </>
    ),

    python: (
      <>
        <Errors messages={errors.python} />
        <Field label="Python canónico" help="La misma regla como evaluate_rule(data). Para los campos Decimal usá decimal.Decimal. check-case verifica en el sandbox que dé lo mismo que el AST.">
          {(id) => (
            <textarea id={id} rows={18} spellCheck={false} className={`${inputClass} bg-code font-mono text-[12.5px]`} value={draft.canonical_python} onChange={(e) => edit((r) => void (r.canonical_python = e.target.value))} />
          )}
        </Field>
      </>
    ),

    revision: (
      <>
        <Field label="Estado de revisión" help="Aprobada: el AST es la única lectura del enunciado, el Python coincide, los escenarios prueban los bordes y los parámetros coinciden con la fuente.">
          {(id) => (
            <select id={id} className={inputClass} value={review.status} onChange={(e) => edit((r) => void (r.review = { ...review, status: e.target.value as ReviewStatus }))}>
              {Object.entries(REVIEW).map(([k, v]) => (
                <option key={k} value={k}>
                  {v.label}
                </option>
              ))}
            </select>
          )}
        </Field>
        <p className="text-[13px] font-semibold">Comentarios ({review.comments.length})</p>
        {review.comments.length === 0 && <p className="text-faint">Sin comentarios todavía.</p>}
        <ul className="grid gap-3">
          {review.comments.map((c, i) => (
            <li key={i}>
              <div className="text-[12.5px] text-muted">
                <b className="font-medium text-ink">{c.author || "Revisor"}</b> · {fmtDate(c.at)}
              </div>
              <p className="mt-0.5 whitespace-pre-wrap">{c.text}</p>
            </li>
          ))}
        </ul>
        <div className="grid grid-cols-[minmax(0,200px)_1fr] gap-2.5 max-sm:grid-cols-1">
          <Field label="Tu nombre">
            {(id) => (
              <input
                id={id}
                className={inputClass}
                value={reviewer}
                onChange={(e) => {
                  setReviewer(e.target.value);
                  try {
                    localStorage.setItem("reviewer", e.target.value);
                  } catch {
                    /* sin almacenamiento: se pide de nuevo la próxima vez */
                  }
                }}
              />
            )}
          </Field>
          <Field label="Comentario">
            {(id) => <textarea id={id} rows={3} className={inputClass} placeholder="Qué revisaste o qué hay que cambiar" value={comment} onChange={(e) => setComment(e.target.value)} />}
          </Field>
        </div>
        <div className="flex flex-wrap items-center gap-2.5">
          <Button
            small
            disabled={!comment.trim() || !reviewer.trim()}
            onClick={() => {
              edit((r) => void (r.review = { ...review, comments: [...review.comments, { author: reviewer.trim(), text: comment.trim(), at: new Date().toISOString() }] }));
              setComment("");
            }}
          >
            Agregar comentario
          </Button>
          <span className="text-[12.5px] text-faint">Se guarda con la regla al tocar “Guardar”.</span>
        </div>
      </>
    ),
  } satisfies Record<TabKey, ReactNode>;

  return (
    <>
      <Drawer
        title={isNew ? "Nueva regla" : "Editar regla"}
        subtitle={isNew ? undefined : draft.case_id}
        onClose={onClose}
        tabs={TABS.map(([k, label]) => (
          <Tab key={k} selected={tab === k} flagged={!!errors[k]} onClick={() => setTab(k)}>
            {label}
          </Tab>
        ))}
        footer={
          <>
            <span className={`min-w-[200px] flex-1 text-[13px] ${message?.error ? "text-bad" : "text-muted"}`} role="status">
              {message?.text}
            </span>
            {!isNew && (
              <Button variant="danger" onClick={() => setDeleting({ error: null })}>
                Eliminar
              </Button>
            )}
            <Button onClick={onClose}>Cerrar</Button>
            <Button variant="primary" disabled={saving} onClick={save}>
              {isNew ? "Crear regla" : "Guardar"}
            </Button>
          </>
        }
      >
        {check && <CheckResult report={check} />}
        {body[tab]}
      </Drawer>
      {deleting && (
        <Confirm title={`¿Eliminar ${draft.case_id}?`} confirmLabel="Eliminar" danger error={deleting.error} onConfirm={remove} onCancel={() => setDeleting(null)}>
          Se borra el archivo {draft._file} de corpus/. Si la regla la escribe un script de corpus/tools/, volvería a aparecer al correrlo.
        </Confirm>
      )}
    </>
  );
}

const cellClass =
  "w-full min-w-[90px] rounded-md border border-transparent bg-transparent px-1.5 py-1 font-mono text-[12.5px] hover:border-line focus:border-accent focus:bg-surface focus:outline-none";

export function CheckResult({ report }: { report: CheckReport }) {
  const errors = report.issues.filter((i) => i.level === "error");
  const warnings = report.issues.filter((i) => i.level === "aviso");
  return (
    <div className={`grid gap-1.5 rounded-lg px-3.5 py-2.5 ${report.ok ? "bg-ok-soft" : "bg-bad-soft"}`}>
      <div className="flex flex-wrap items-center gap-2">
        <Badge tone={report.ok ? "ok" : "bad"}>check-case {report.ok ? "OK" : "con errores"}</Badge>
        {report.filled > 0 && <span className="text-[12.5px] text-muted">{report.filled} expected calculados por el engine</span>}
      </div>
      {[...errors, ...warnings].length > 0 && (
        <ul className="grid gap-0.5 text-[12.5px]">
          {[...errors, ...warnings].map((i, n) => (
            <li key={n} className={i.level === "error" ? "text-bad" : "text-warn"}>
              {i.level}: {i.message}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
