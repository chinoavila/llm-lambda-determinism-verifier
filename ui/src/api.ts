// Cliente tipado de la API de `python -m pipeline serve` (specs/ui.md).
// Los tipos reflejan sus DTO; las respuestas HTTP no reemplazan la validación del servidor.

/** Tipos base admitidos por el DSL y el contrato del corpus. */
export type BaseType = "Int" | "Decimal" | "Bool" | "String";
/** Resultado de regla persistido en expected o en un registro de corrida. */
export type Result = { type: BaseType | "Other"; value: unknown };
/** Entorno y resultado esperado de un escenario del caso. */
export type Scenario = { scenario_id: string; env: Record<string, unknown>; expected?: Result };
/** Procedencia de una regla y referencia/licencia cuando deriva de otra fuente. */
export type Source = { kind: "original" | "adapted"; reference?: string; license?: string };
/** Estado editorial asignado durante la revisión del corpus. */
export type ReviewStatus = "pendiente" | "aprobada" | "cambios";
/** Comentario de revisión con autor y timestamp. */
export type Comment = { author: string; text: string; at: string };
/** Estado de revisión e historial de comentarios de una regla. */
export type Review = { status: ReviewStatus; comments: Comment[] };
/** Nodo abierto del AST JSON; sus campos concretos dependen de `type`. */
export type AstNode = { type: string; [key: string]: unknown };

/** Regla editable del corpus, incluyendo metadatos internos de versión/archivo. */
export type Rule = {
  case_id: string;
  category: number;
  domain: string;
  source: Source;
  generated_by?: string;
  description: string;
  gamma: Record<string, BaseType>;
  canonical_ast: { expr: AstNode };
  canonical_python: string;
  scenarios: Scenario[];
  review?: Review;
  _version?: string;
  _file?: string;
};

/** Hallazgo de validación del corpus con severidad y texto legible. */
export type Issue = { level: "error" | "aviso"; message: string };
/** Resumen del endpoint check-case y cantidad de expected completados. */
export type CheckReport = { case_id: string; ok: boolean; issues: Issue[]; filled: number };
/** Respuesta de create/update: regla persistida y resultado de verificación. */
export type Saved = { rule: Rule; check: CheckReport };

/** Estado agregado que la API informa para los subsistemas del pipeline. */
export type Health = {
  engine: boolean;
  sandbox_queue: boolean;
  llm: { ready: boolean; models: string[]; error: string | null };
  corpus_rules: number;
  runs: number;
};

/** Selección para estimar o iniciar una corrida; case_ids restringe el corpus. */
export type Selection = { source: "corpus" | "fixtures"; case_ids?: string[]; repetitions: number };
/** Estimación de volumen; `calls` es casos × grupos × repeticiones. */
export type Estimate = { cases: number; repetitions: number; calls: number };
/** Estados terminales y activo del proceso de corrida. */
export type JobStatus = "running" | "finished" | "failed" | "cancelled";
/** Estado público del proceso de corrida administrado por la API. */
export type Job = {
  run_id: string;
  source: string;
  cases: string[];
  repetitions: number;
  calls: number;
  started_at: string;
  status: JobStatus;
  returncode: number | null;
};
/** Corrida encontrada en disco junto a sus conteos y job en memoria opcional. */
export type RunInfo = { run_id: string; records: number; has_log: boolean; modified: string; job: Job | null };
/** Lista de corridas y referencia a la corrida activa, si existe. */
export type Runs = { active: Job | null; runs: RunInfo[] };
/** Fragmento de log para polling incremental por offset. */
export type LogChunk = { text: string; offset: number; status: JobStatus | null };

/** Identificadores estables de los tres carriles experimentales. */
export type Group = "treatment" | "baseline1" | "baseline2";
/** Desenlaces admitidos por el registro de salida v2.0. */
export type Outcome = "executed" | "blocked" | "runtime_error" | "timeout" | "llm_error";
/** Registro JSONL, enriquecido por el servidor con expected del corpus si existe. */
export type RecordRow = {
  run_id: string;
  case_id: string;
  group: Group;
  repetition: number;
  scenario_id: string;
  model: string;
  timestamp: string;
  llm_raw: string | null;
  outcome: Outcome;
  stage: string;
  result: Result | null;
  error: { code: string; message: string } | null;
  duration_ms: number | null;
  expected: Result | null;
};

export class ApiError extends Error {
  /** Error HTTP con status para que la UI distinga conflictos y fallos de servicio. */
  constructor(
    readonly status: number,
    message: string,
  ) {
    super(message);
  }
}

// Centraliza JSON, cabeceras y traducción de respuestas no-2xx a ApiError.
async function request<T>(path: string, init?: { method?: string; body?: unknown }): Promise<T> {
  const resp = await fetch(path, {
    method: init?.method ?? "GET",
    headers: { Accept: "application/json", ...(init?.body !== undefined ? { "Content-Type": "application/json" } : {}) },
    body: init?.body !== undefined ? JSON.stringify(init.body) : undefined,
  });
  const body: unknown = await resp.json().catch(() => null);
  if (!resp.ok) {
    const message =
      body && typeof body === "object" && "error" in body ? String(body.error) : `HTTP ${resp.status}`;
    throw new ApiError(resp.status, message);
  }
  return body as T;
}

const enc = encodeURIComponent;

export const api = {
  /** Consulta salud, corpus y servicios sin exponer credenciales. */
  health: () => request<Health>("/api/health"),

  /** Operaciones CRUD de reglas; writes devuelven regla y reporte de verificación. */
  rules: () => request<Rule[]>("/api/rules"),
  /** Lee una regla; `id` se codifica como segmento de ruta. */
  rule: (id: string) => request<Rule>(`/api/rules/${enc(id)}`),
  /** Crea una regla; el servidor valida y completa expected calculables. */
  createRule: (rule: Rule) => request<Saved>("/api/rules", { method: "POST", body: rule }),
  /** Actualiza una regla usando `_version` para detectar conflictos de edición. */
  updateRule: (rule: Rule) => request<Saved>(`/api/rules/${enc(rule.case_id)}`, { method: "PUT", body: rule }),
  /** Borra solo la versión consultada; un conflicto se reporta como ApiError 409. */
  deleteRule: (id: string, version: string) =>
    request<{ deleted: string }>(`/api/rules/${enc(id)}?version=${enc(version)}`, { method: "DELETE" }),
  checkRule: (id: string) => request<CheckReport>(`/api/rules/${enc(id)}/check`, { method: "POST" }),
  /** Verifica todas las reglas sin modificar expected. */
  checkAll: () => request<CheckReport[]>("/api/rules/check", { method: "POST" }),

  /** Lista corridas, incluyendo la activa y los JSONL históricos. */
  runs: () => request<Runs>("/api/runs"),
  /** Estima volumen/costo potencial sin iniciar una corrida. */
  estimate: (s: Selection) => request<Estimate>("/api/runs/estimate", { method: "POST", body: s }),
  /** Inicia la corrida solo si confirmCalls coincide con la estimación vigente. */
  startRun: (s: Selection, confirmCalls: number) =>
    request<Job>("/api/runs", { method: "POST", body: { ...s, confirm_calls: confirmCalls } }),
  /** Solicita cancelación del job; error HTTP si no está activo. */
  cancelRun: (id: string) => request<Job>(`/api/runs/${enc(id)}/cancel`, { method: "POST" }),
  /** Obtiene bytes de log a partir del offset para polling incremental. */
  log: (id: string, offset: number) => request<LogChunk>(`/api/runs/${enc(id)}/log?offset=${offset}`),
  /** Lee registros JSONL y filtra por igualdad de campos admitidos por la API. */
  records: (id: string, filters: Record<string, string>) => {
    const q = new URLSearchParams(Object.entries(filters).filter(([, v]) => v !== "")).toString();
    return request<RecordRow[]>(`/api/runs/${enc(id)}/records${q ? `?${q}` : ""}`);
  },
};

export const errorText = (e: unknown) => (e instanceof Error ? e.message : String(e));
