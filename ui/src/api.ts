// Cliente de la API de `python -m pipeline serve` (specs/ui.md).

export type BaseType = "Int" | "Decimal" | "Bool" | "String";
export type Result = { type: BaseType | "Other"; value: unknown };
export type Scenario = { scenario_id: string; env: Record<string, unknown>; expected?: Result };
export type Source = { kind: "original" | "adapted"; reference?: string; license?: string };
export type ReviewStatus = "pendiente" | "aprobada" | "cambios";
export type Comment = { author: string; text: string; at: string };
export type Review = { status: ReviewStatus; comments: Comment[] };
export type AstNode = { type: string; [key: string]: unknown };

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

export type Issue = { level: "error" | "aviso"; message: string };
export type CheckReport = { case_id: string; ok: boolean; issues: Issue[]; filled: number };
export type Saved = { rule: Rule; check: CheckReport };

export type Health = {
  engine: boolean;
  sandbox_queue: boolean;
  llm: { ready: boolean; models: string[]; error: string | null };
  corpus_rules: number;
  runs: number;
};

export type Selection = { source: "corpus" | "fixtures"; case_ids?: string[]; repetitions: number };
export type Estimate = { cases: number; repetitions: number; calls: number };
export type JobStatus = "running" | "finished" | "failed" | "cancelled";
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
export type RunInfo = { run_id: string; records: number; has_log: boolean; modified: string; job: Job | null };
export type Runs = { active: Job | null; runs: RunInfo[] };
export type LogChunk = { text: string; offset: number; status: JobStatus | null };

export type Group = "treatment" | "baseline1" | "baseline2";
export type Outcome = "executed" | "blocked" | "runtime_error" | "timeout" | "llm_error";
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
  constructor(
    readonly status: number,
    message: string,
  ) {
    super(message);
  }
}

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
  health: () => request<Health>("/api/health"),

  rules: () => request<Rule[]>("/api/rules"),
  rule: (id: string) => request<Rule>(`/api/rules/${enc(id)}`),
  createRule: (rule: Rule) => request<Saved>("/api/rules", { method: "POST", body: rule }),
  updateRule: (rule: Rule) => request<Saved>(`/api/rules/${enc(rule.case_id)}`, { method: "PUT", body: rule }),
  deleteRule: (id: string, version: string) =>
    request<{ deleted: string }>(`/api/rules/${enc(id)}?version=${enc(version)}`, { method: "DELETE" }),
  checkRule: (id: string) => request<CheckReport>(`/api/rules/${enc(id)}/check`, { method: "POST" }),
  checkAll: () => request<CheckReport[]>("/api/rules/check", { method: "POST" }),

  runs: () => request<Runs>("/api/runs"),
  estimate: (s: Selection) => request<Estimate>("/api/runs/estimate", { method: "POST", body: s }),
  startRun: (s: Selection, confirmCalls: number) =>
    request<Job>("/api/runs", { method: "POST", body: { ...s, confirm_calls: confirmCalls } }),
  cancelRun: (id: string) => request<Job>(`/api/runs/${enc(id)}/cancel`, { method: "POST" }),
  log: (id: string, offset: number) => request<LogChunk>(`/api/runs/${enc(id)}/log?offset=${offset}`),
  records: (id: string, filters: Record<string, string>) => {
    const q = new URLSearchParams(Object.entries(filters).filter(([, v]) => v !== "")).toString();
    return request<RecordRow[]>(`/api/runs/${enc(id)}/records${q ? `?${q}` : ""}`);
  },
};

export const errorText = (e: unknown) => (e instanceof Error ? e.message : String(e));
