// Vista legible del AST canónico: IF / THEN / ELSE en columna, cadenas largas de
// AND u OR con un operando por línea. Misma lectura que el prototipo aprobado.
import type { AstNode } from "../api";

export type TokenKind = "kw" | "str" | "num" | "";
/** Fragmento visual clasificado para coloreado del AST legible. */
export type Token = { kind: TokenKind; text: string };
/** Línea renderizada con nivel de indentación y tokens preservados. */
export type Line = { indent: number; tokens: Token[] };

const WIDTH = 72;
const PREC: Record<string, number> = {
  OR: 1, AND: 2, "==": 3, "!=": 3, "<": 3, "<=": 3, ">": 3, ">=": 3, "+": 4, "-": 4, "*": 5, "/": 5, "%": 5,
};

const t = (kind: TokenKind, text: string): Token => ({ kind, text });
const node = (x: unknown): AstNode | null => (x && typeof x === "object" && "type" in x ? (x as AstNode) : null);
const width = (ts: Token[]) => ts.reduce((n, x) => n + x.text.length, 0);

/** Convierte una expresión en tokens de una línea, respetando precedencia. */
export function inline(e: unknown, parent = 0): Token[] {
  const n = node(e);
  if (!n) return [t("", "?")];
  switch (n.type) {
    case "Literal": {
      const vt = n.value_type;
      if (vt === "String") return [t("str", `"${String(n.value)}"`)];
      return [t(vt === "Bool" ? "kw" : "num", String(n.value))];
    }
    case "Var":
      return [t("", String(n.name))];
    case "UnaryOp":
      return [t("kw", "NOT "), ...inline(n.operand, 6)];
    case "In": {
      const opts = Array.isArray(n.options) ? n.options : [];
      return [
        ...inline(n.value, 3), t("kw", " IN "), t("", "["),
        ...opts.flatMap((o, i) => (i ? [t("", ", "), ...inline(o)] : inline(o))), t("", "]"),
      ];
    }
    case "BinaryOp": {
      const op = String(n.op);
      const p = PREC[op] ?? 3;
      const body = [...inline(n.left, p), t(p <= 2 ? "kw" : "", ` ${op} `), ...inline(n.right, p + 1)];
      return p < parent ? [t("", "("), ...body, t("", ")")] : body;
    }
    case "IfThenElse":
      return [
        t("kw", "IF "), ...inline(n.condition), t("kw", " THEN "), ...inline(n.then), t("kw", " ELSE "), ...inline(n.else),
      ];
    case "Lam":
      return [t("kw", "λ"), t("", `${String(n.param)}. `), ...inline(n.body)];
    case "App":
      return [t("", "("), ...inline(n.fn), t("", " "), ...inline(n.arg), t("", ")")];
    default:
      return [t("", "?")];
  }
}

function flatten(e: unknown, op: string): unknown[] {
  const n = node(e);
  return n && n.type === "BinaryOp" && n.op === op ? [...flatten(n.left, op), ...flatten(n.right, op)] : [e];
}

/** Parte condicionales y expresiones largas en líneas legibles e indentadas. */
export function lines(e: unknown, indent = 0): Line[] {
  const n = node(e);
  const one = inline(e);
  if (n?.type === "IfThenElse") {
    const out: Line[] = [{ indent, tokens: [t("kw", "IF "), ...inline(n.condition)] }];
    if (width(out[0]!.tokens) + indent * 2 > WIDTH) {
      out[0] = { indent, tokens: [t("kw", "IF")] };
      out.push(...lines(n.condition, indent + 1));
    }
    out.push({ indent, tokens: [t("kw", "THEN")] }, ...lines(n.then, indent + 1));
    if (node(n.else)?.type === "IfThenElse") {
      const rest = lines(n.else, indent);
      rest[0] = { indent, tokens: [t("kw", "ELSE "), ...rest[0]!.tokens] };
      out.push(...rest);
    } else {
      out.push({ indent, tokens: [t("kw", "ELSE")] }, ...lines(n.else, indent + 1));
    }
    return out;
  }
  if (width(one) + indent * 2 <= WIDTH || !n) return [{ indent, tokens: one }];
  if (n.type === "BinaryOp" && (n.op === "AND" || n.op === "OR")) {
    const op = String(n.op);
    return flatten(n, op).flatMap((part, i) => {
      const sub = lines(part, indent + 1);
      sub[0] = { indent, tokens: [t("kw", i ? `${op.padEnd(3)} ` : "    "), ...sub[0]!.tokens] };
      return sub.map((l, j) => (j === 0 ? l : { indent: l.indent + 2, tokens: l.tokens }));
    });
  }
  if (n.type === "UnaryOp") {
    return [{ indent, tokens: [t("kw", "NOT (")] }, ...lines(n.operand, indent + 1), { indent, tokens: [t("", ")")] }];
  }
  if (n.type === "In") {
    const opts = Array.isArray(n.options) ? n.options : [];
    return [
      { indent, tokens: [...inline(n.value), t("kw", " IN "), t("", "[")] },
      ...opts.map((o, i) => ({ indent: indent + 1, tokens: [...inline(o), t("", i < opts.length - 1 ? "," : "")] })),
      { indent, tokens: [t("", "]")] },
    ];
  }
  return [{ indent, tokens: one }];
}

/** Produce texto multilínea para previsualizar el AST sin evaluarlo. */
export const render = (e: unknown) =>
  lines(e)
    .map((l) => "  ".repeat(l.indent) + l.tokens.map((x) => x.text).join(""))
    .join("\n");
