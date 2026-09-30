// Piezas de interfaz compartidas, con el estilo del prototipo aprobado.
import { useEffect, useId, useRef, type ComponentProps, type ReactNode } from "react";
import type { Token } from "../lib/ast";
import { lines } from "../lib/ast";

type Variant = "default" | "primary" | "danger" | "danger-solid" | "link" | "link-danger";

const VARIANTS: Record<Variant, string> = {
  default: "border border-line bg-surface hover:bg-hover",
  primary: "border border-accent bg-accent text-accent-ink hover:brightness-110",
  danger: "border border-line bg-surface text-bad hover:bg-hover",
  "danger-solid": "border border-bad bg-bad text-white hover:brightness-110",
  link: "text-accent hover:bg-hover",
  "link-danger": "text-bad hover:bg-hover",
};

/** Botón semántico con variantes visuales y props nativas de HTMLButtonElement. */
export function Button({
  variant = "default",
  small = false,
  className = "",
  ...props
}: ComponentProps<"button"> & { variant?: Variant; small?: boolean }) {
  const size = variant.startsWith("link") ? "px-1.5 py-1 rounded" : small ? "px-2.5 py-1 text-[13px] rounded-md" : "px-3.5 py-[7px] rounded-lg";
  return (
    <button
      type="button"
      className={`inline-flex items-center gap-1.5 font-medium whitespace-nowrap disabled:cursor-not-allowed disabled:opacity-50 ${size} ${VARIANTS[variant]} ${className}`}
      {...props}
    />
  );
}

export type Tone = "neutral" | "ok" | "bad" | "warn" | "accent";
const TONES: Record<Tone, string> = {
  neutral: "bg-hover text-muted",
  ok: "bg-ok-soft text-ok",
  bad: "bg-bad-soft text-bad",
  warn: "bg-warn-soft text-warn",
  accent: "bg-accent-soft text-accent",
};

/** Etiqueta compacta para estados con tono accesible y texto proporcionado por el caller. */
export function Badge({ tone = "neutral", children }: { tone?: Tone; children: ReactNode }) {
  return (
    <span className={`inline-flex items-center gap-1.5 whitespace-nowrap rounded-full px-2.5 py-0.5 text-xs font-medium ${TONES[tone]}`}>
      <span className="size-1.5 rounded-full bg-current" aria-hidden />
      {children}
    </span>
  );
}

/** Mensaje destacado que comparte la paleta de estados de Badge. */
export function Notice({ tone = "warn", children }: { tone?: Tone; children: ReactNode }) {
  return <div className={`rounded-lg px-3.5 py-2.5 ${TONES[tone]} text-ink`}>{children}</div>;
}

export const inputClass =
  "w-full rounded-lg border border-line bg-surface px-2.5 py-2 disabled:opacity-60 focus:border-accent focus:outline-none";

/** Asocia una etiqueta accesible y ayuda con el control creado por children(id). */
export function Field({ label, help, children }: { label: string; help?: ReactNode; children: (id: string) => ReactNode }) {
  const id = useId();
  return (
    <div className="grid gap-1.5">
      <label htmlFor={id} className="text-[12.5px] font-medium text-muted">
        {label}
      </label>
      {children(id)}
      {help && <p className="text-[12.5px] text-faint">{help}</p>}
    </div>
  );
}

/** Renderiza mensajes de validación; no crea markup cuando la lista está vacía. */
export function Errors({ messages }: { messages?: string[] }) {
  if (!messages?.length) return null;
  return (
    <ul className="grid gap-1 text-[12.5px] text-bad">
      {messages.map((m) => (
        <li key={m}>{m}</li>
      ))}
    </ul>
  );
}

/** Panel lateral modal; Escape y click en el fondo llaman onClose. */
export function Drawer({
  title,
  subtitle,
  onClose,
  tabs,
  footer,
  children,
}: {
  title: string;
  subtitle?: string;
  onClose: () => void;
  tabs?: ReactNode;
  footer?: ReactNode;
  children: ReactNode;
}) {
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape" && !document.querySelector("[data-dialog]")) onClose();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);
  return (
    <>
      <div className="fixed inset-0 z-10 bg-black/35" onClick={onClose} aria-hidden />
      <aside
        role="dialog"
        aria-label={title}
        className="fixed inset-y-0 right-0 z-20 flex w-[min(820px,100%)] flex-col bg-surface shadow-2xl motion-safe:animate-[slide_.18s_ease-out]"
      >
        <header className="flex items-center gap-3 border-b border-line px-5 py-4">
          <h2 className="min-w-0 flex-1 truncate text-base font-semibold">
            {title}
            {subtitle && <small className="ml-1.5 font-mono text-[13px] font-medium text-muted">{subtitle}</small>}
          </h2>
          <Button small onClick={onClose}>
            Cerrar
          </Button>
        </header>
        {tabs && <div className="flex shrink-0 gap-0.5 overflow-x-auto border-b border-line px-4">{tabs}</div>}
        <div className="grid min-h-0 flex-1 content-start gap-4.5 overflow-y-auto p-5">{children}</div>
        {footer && <footer className="flex flex-wrap items-center gap-2.5 border-t border-line px-5 py-3.5">{footer}</footer>}
      </aside>
    </>
  );
}

/** Pestaña accesible con estado seleccionado e indicador opcional de errores. */
export function Tab({ selected, flagged, onClick, children }: { selected: boolean; flagged?: boolean; onClick: () => void; children: ReactNode }) {
  return (
    <button
      type="button"
      role="tab"
      aria-selected={selected}
      onClick={onClick}
      className={`border-b-2 px-3 py-2.5 font-medium whitespace-nowrap ${selected ? "border-accent text-accent" : "border-transparent text-muted hover:text-ink"}`}
    >
      {children}
      {flagged && <span className="ml-1.5 inline-block size-[7px] rounded-full bg-bad align-middle" aria-label="con errores" />}
    </button>
  );
}

/** Diálogo de confirmación; enfoca Cancelar al abrir y bloquea Confirmar si busy. */
export function Confirm({
  title,
  children,
  confirmLabel,
  danger = false,
  busy = false,
  error,
  onConfirm,
  onCancel,
}: {
  title: string;
  children: ReactNode;
  confirmLabel: string;
  danger?: boolean;
  busy?: boolean;
  error?: string | null;
  onConfirm: () => void;
  onCancel: () => void;
}) {
  const cancel = useRef<HTMLButtonElement>(null);
  useEffect(() => cancel.current?.focus(), []);
  return (
    <div data-dialog className="fixed inset-0 z-30 grid place-items-center bg-black/40 px-4" role="alertdialog" aria-label={title}>
      <div className="grid w-[min(460px,100%)] gap-3 rounded-xl bg-surface p-5 shadow-2xl">
        <h3 className="text-base font-semibold">{title}</h3>
        <div className="text-muted">{children}</div>
        {error && <p className="text-bad">{error}</p>}
        <div className="flex justify-end gap-2">
          <Button ref={cancel} onClick={onCancel}>
            Cancelar
          </Button>
          <Button variant={danger ? "danger-solid" : "primary"} disabled={busy} onClick={onConfirm}>
            {confirmLabel}
          </Button>
        </div>
      </div>
    </div>
  );
}

const TOKEN_CLASS: Record<Token["kind"], string> = { kw: "font-medium text-accent", str: "text-ok", num: "text-warn", "": "" };

/** Muestra el AST en su representación legible y con tokens coloreados. */
export function AstPreview({ expr }: { expr: unknown }) {
  return (
    <pre className="overflow-x-auto rounded-lg border border-line bg-code p-3 font-mono text-[12.5px] leading-relaxed">
      {lines(expr).map((l, i) => (
        <span key={i}>
          {i > 0 && "\n"}
          {"  ".repeat(l.indent)}
          {l.tokens.map((t, j) => (t.kind ? <span key={j} className={TOKEN_CLASS[t.kind]}>{t.text}</span> : t.text))}
        </span>
      ))}
    </pre>
  );
}

/** Contenedor visual simple para agrupar contenido relacionado. */
export function Card({ children, className = "" }: { children: ReactNode; className?: string }) {
  return <div className={`rounded-xl border border-line bg-surface ${className}`}>{children}</div>;
}

/** Formatea ISO en horario/localización es-AR; devuelve raya si falta o es inválido. */
export const fmtDate = (iso?: string | null) => {
  if (!iso) return "—";
  const d = new Date(iso);
  return Number.isNaN(d.getTime())
    ? "—"
    : `${d.toLocaleDateString("es-AR", { day: "numeric", month: "short" })} ${d.toLocaleTimeString("es-AR", { hour: "2-digit", minute: "2-digit" })}`;
};
