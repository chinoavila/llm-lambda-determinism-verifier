// Validación del formulario de reglas: lo que check-case exige de forma, sin el
// engine. La verificación completa la hace el servidor al guardar.
import type { BaseType, Result, Rule } from "../api";

export const TYPES: BaseType[] = ["Int", "Decimal", "Bool", "String"];
export type Tab = "general" | "escenarios" | "ast" | "python" | "revision";
export type Errors = Partial<Record<Tab, string[]>>;

/** Comprueba compatibilidad básica de un valor JS con el tipo declarado. */
export function valueFits(type: BaseType, v: unknown): boolean {
  switch (type) {
    case "Bool":
      return typeof v === "boolean";
    case "String":
      return typeof v === "string";
    case "Int":
      return typeof v === "number" && Number.isInteger(v);
    case "Decimal":
      return typeof v === "number" && !Number.isInteger(v);
  }
}

/** Texto de una celda del formulario al valor del `env`. */
export function parseCell(type: BaseType, raw: string): unknown {
  if (type === "Bool") return raw === "true";
  if (type === "String") return raw;
  const n = Number(raw.replace(",", "."));
  return raw.trim() === "" || Number.isNaN(n) ? raw : n;
}

/** Texto de un expected escrito a mano. Vacío: lo calcula el engine. */
export function parseExpected(raw: string, previous?: Result): Result | undefined {
  const text = raw.trim();
  if (!text) return undefined;
  const type =
    previous?.type ??
    (text === "true" || text === "false" ? "Bool" : /^-?\d+$/.test(text) ? "Int" : /^-?\d+\.\d+$/.test(text) ? "Decimal" : "String");
  if (type === "Bool") return { type, value: text === "true" };
  if (type === "Int") return { type, value: Number(text) };
  return { type, value: text };
}

export const showValue = (v: unknown) => (typeof v === "string" ? `"${v}"` : String(v));

/** Valida formato del formulario; la verificación semántica completa corre en el servidor/engine. */
export function validate(r: Rule, isNew: boolean, existing: ReadonlySet<string>, astError: string | null): Errors {
  const errs: Errors = {};
  const add = (tab: Tab, msg: string) => (errs[tab] ??= []).push(msg);
  if (!/^[A-Za-z0-9_-]{1,120}$/.test(r.case_id)) add("general", "El id solo admite letras, dígitos, - y _.");
  else if (isNew && existing.has(r.case_id)) add("general", "Ya existe una regla con ese id.");
  if (![1, 2, 3].includes(r.category)) add("general", "Elegí una categoría.");
  if (!r.domain.trim()) add("general", "Falta el dominio.");
  if (!r.description.trim()) add("general", "Falta el enunciado.");
  if (r.source.kind === "adapted" && (!r.source.reference?.trim() || !r.source.license?.trim()))
    add("general", "Una regla adaptada necesita referencia y licencia.");

  const vars = Object.keys(r.gamma);
  if (!vars.length) add("escenarios", "Agregá al menos una variable.");
  if (vars.some((v) => !/^[A-Za-z_][A-Za-z0-9_]*$/.test(v)))
    add("escenarios", "Los nombres de variable son identificadores (letras, dígitos y _).");
  if (r.scenarios.length < 2) add("escenarios", "Hacen falta al menos 2 escenarios (la guía pide de 6 a 10).");
  const ids = r.scenarios.map((s) => s.scenario_id);
  if (ids.some((i) => !i) || new Set(ids).size !== ids.length) add("escenarios", "Cada escenario necesita un id único.");
  for (const s of r.scenarios)
    for (const v of vars) {
      const type = r.gamma[v]!;
      if (!valueFits(type, s.env[v]))
        add("escenarios", `${s.scenario_id || "?"}: ${v} debe ser ${type}${type === "Decimal" ? " con parte decimal (1500.5, no 1500)" : ""}.`);
    }

  if (astError) add("ast", astError);
  else if (!r.canonical_ast?.expr || typeof r.canonical_ast.expr !== "object") add("ast", 'El AST debe ser {"expr": …}.');
  if (!/def\s+evaluate_rule\s*\(/.test(r.canonical_python)) add("python", "Falta def evaluate_rule(data).");
  return errs;
}

/** Devuelve una regla mínima editable con dos escenarios de ejemplo. */
export function blankRule(): Rule {
  return {
    case_id: "",
    category: 1,
    domain: "",
    source: { kind: "original" },
    description: "",
    gamma: { variable: "Int" },
    canonical_ast: { expr: { type: "Var", name: "variable" } },
    canonical_python: "def evaluate_rule(data):\n    return data['variable']\n",
    scenarios: [
      { scenario_id: "S1", env: { variable: 0 } },
      { scenario_id: "S2", env: { variable: 1 } },
    ],
    review: { status: "pendiente", comments: [] },
  };
}

/** Valor inicial de formulario compatible con el tipo base seleccionado. */
export function defaultValue(type: BaseType): unknown {
  return type === "Bool" ? false : type === "String" ? "" : type === "Decimal" ? 0.5 : 0;
}
