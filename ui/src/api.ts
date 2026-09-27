// Cliente de la API de `python -m pipeline serve` (specs/ui.md).

export type Health = {
  engine: boolean;
  sandbox_queue: boolean;
  llm: { ready: boolean; models: string[]; error: string | null };
  corpus_rules: number;
  runs: number;
};

export class ApiError extends Error {
  constructor(
    readonly status: number,
    message: string,
  ) {
    super(message);
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const resp = await fetch(path, { headers: { Accept: "application/json" }, ...init });
  const body: unknown = await resp.json().catch(() => null);
  if (!resp.ok) {
    const message =
      body && typeof body === "object" && "error" in body ? String(body.error) : `HTTP ${resp.status}`;
    throw new ApiError(resp.status, message);
  }
  return body as T;
}

export const getHealth = () => request<Health>("/api/health");
