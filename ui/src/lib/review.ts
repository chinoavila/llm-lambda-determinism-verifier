// Revisión a ciegas de los expected (corpus/README.md, revisión humana): el revisor lee
// solo el enunciado y el env de cada escenario, anota el resultado que espera y recién
// después lo compara con el expected que calculó el engine.
import type { BaseType, Result, Rule } from "../api";
import { parseExpected, showValue } from "./rules";

export type BlindRow = {
  scenario_id: string;
  expected: Result | undefined;
  answer: Result | undefined;
  /** null si falta el expected o la respuesta. */
  match: boolean | null;
};

/** Texto decimal canónico (contracts/README.md §3): sin ceros finales ni punto final, sin "-0". */
export function canonicalDecimal(text: string): string {
  let t = text.trim().replace(/^\+/, "");
  if (t.includes(".")) t = t.replace(/0+$/, "").replace(/\.$/, "");
  t = t.replace(/^(-?)0+(?=\d)/, "$1");
  return /^-?0$/.test(t) ? "0" : t;
}

/** La respuesta del revisor, leída con el tipo del expected (Int, Decimal, Bool o String). */
export function parseAnswer(raw: string, type: BaseType | "Other" | undefined): Result | undefined {
  const parsed = parseExpected(raw, type && type !== "Other" ? { type, value: null } : undefined);
  if (parsed?.type === "Decimal") return { type: "Decimal", value: canonicalDecimal(String(parsed.value)) };
  return parsed;
}

const sameResult = (a: Result, b: Result) =>
  a.type === b.type &&
  (a.type === "Decimal" ? canonicalDecimal(String(a.value)) === canonicalDecimal(String(b.value)) : JSON.stringify(a.value) === JSON.stringify(b.value));

/** Compara las respuestas del revisor (texto por scenario_id) con los expected de la regla. */
export function blindCompare(rule: Rule, answers: Readonly<Record<string, string>>): BlindRow[] {
  return rule.scenarios.map((s) => {
    const answer = parseAnswer(answers[s.scenario_id] ?? "", s.expected?.type);
    return {
      scenario_id: s.scenario_id,
      expected: s.expected,
      answer,
      match: s.expected && answer ? sameResult(s.expected, answer) : null,
    };
  });
}

const show = (r: Result | undefined) => (r ? `${r.type} ${showValue(r.value)}` : "—");

/** Comentario que deja la revisión a ciegas en `review.comments`. */
export function blindSummary(rows: BlindRow[]): string {
  const judged = rows.filter((r) => r.match !== null);
  const diff = judged.filter((r) => !r.match);
  const head = `Revisión a ciegas: ${judged.length - diff.length} de ${rows.length} escenarios coinciden con el expected.`;
  const lines = diff.map((r) => `- ${r.scenario_id}: expected ${show(r.expected)}, revisor ${show(r.answer)}`);
  const missing = rows.length - judged.length;
  return [head, ...lines, ...(missing ? [`${missing} sin respuesta o sin expected.`] : [])].join("\n");
}

const ORDER_OPS = new Set(["<", "<=", ">", ">="]);
type Node = { type?: unknown; [key: string]: unknown };
const isNode = (x: unknown): x is Node => typeof x === "object" && x !== null && !Array.isArray(x);

/** Comparaciones `Var op Literal` (o al revés) con literal numérico: los umbrales de la regla. */
export function thresholds(expr: unknown): { name: string; op: string; value: number }[] {
  const out: { name: string; op: string; value: number }[] = [];
  const walk = (x: unknown): void => {
    if (Array.isArray(x)) return x.forEach(walk);
    if (!isNode(x)) return;
    if (x.type === "BinaryOp" && typeof x.op === "string" && ORDER_OPS.has(x.op)) {
      const [v, l] = isNode(x.left) && x.left.type === "Var" ? [x.left, x.right] : [x.right, x.left];
      if (isNode(v) && v.type === "Var" && isNode(l) && l.type === "Literal" && (l.value_type === "Int" || l.value_type === "Decimal"))
        out.push({ name: String(v.name), op: x.op, value: Number(l.value) });
    }
    Object.values(x).forEach(walk);
  };
  walk(expr);
  return out;
}

export type Coverage = { sameExpected: boolean; missingBorders: string[] };

/** Indicios de escenarios flojos: todos esperan lo mismo (una regla constante acertaría) o
 * hay umbrales del AST canónico sin un escenario justo en el borde. */
export function scenarioCoverage(rule: Rule): Coverage {
  const expected = rule.scenarios.filter((s) => s.expected).map((s) => JSON.stringify(s.expected));
  const missing = thresholds(rule.canonical_ast.expr).filter(
    (t) => !rule.scenarios.some((s) => s.env[t.name] !== undefined && s.env[t.name] !== null && Number(s.env[t.name]) === t.value),
  );
  return {
    sameExpected: expected.length > 1 && new Set(expected).size === 1,
    missingBorders: [...new Set(missing.map((t) => `${t.name} ${t.op} ${t.value}`))],
  };
}
