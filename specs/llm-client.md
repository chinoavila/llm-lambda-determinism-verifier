# Cliente LLM — especificación para agentes

Código: `pipeline/pipeline/llm/`. Config: `pipeline/llm.toml`. Explicación para humanos: `docs/llm-client.md`.

## Reglas

- Un único protocolo: OpenAI Chat Completions, `POST {base_url}/chat/completions`. No agregar adaptadores por proveedor ni SDKs.
- HTTP solo con `urllib` de la stdlib. No seguir redirects.
- El proveedor se define solo por config: `base_url`, `model`, `api_key_env`, `priority`, `params`. Ruta del TOML en `LLM_CONFIG` (default `llm.toml`, relativo a `pipeline/`).
- Claves solo en variables de entorno. Nunca en el TOML, en logs ni en `repr`.
- Todas las llamadas usan `response_format = {"type": "json_object"}`, en los tres grupos. Tratamiento pide el AST; los baselines, `{"code": "..."}`. El prompt debe mencionar JSON.
- `params` se envía tal cual. `model`, `messages`, `response_format` y `stream` los fija el cliente; la config no puede definirlos.
- Todos los campos de `[balancer]` son obligatorios; no inventar defaults en código.

## Balanceo

- Modelo fijo por caso: un `ModelAssignment` por caso (`balancer.acquire()`); los tres grupos del caso llaman `assignment.complete(messages)` sobre el mismo modelo. Nunca cambiar de modelo dentro de un caso.
- Health check al construir (`build_balancer`): `GET {base_url}/models`. Se excluyen los modelos no listados y los endpoints con status distinto de 200 o que no responden.
- Un modelo es elegible si: está disponible, no está en cooldown, `remaining_requests >= min_remaining_requests` y `remaining_tokens - reserve_tokens * asignaciones_activas >= reserve_tokens`. Los datos de cuota (headers `x-ratelimit-*`) vencen en su `reset`. Sin headers, el balanceo es solo reactivo.
- Orden de elección: `priority`, después asignaciones activas, después nombre.
- Si no hay ningún modelo elegible, `acquire` espera; si la espera supera `max_wait_seconds`, lanza `NoModelAvailable`.
- Es thread-safe; la cantidad de workers la decide el orquestador.

## Errores (outcome de `LLMCall`)

- 2xx: `ok`.
- 429: cooldown del modelo; esperar `retry-after` y reintentar el mismo modelo. Si la espera supera `max_wait_seconds`: `quota_exhausted`.
- Red, timeout o 5xx: backoff exponencial, hasta `max_transport_retries` reintentos; después, `transport_error`.
- 400 con `error.code == json_validate_failed`: `generation_failed`, sin reintento.
- Otros 4xx: `request_error`, sin reintento.
- Nunca reparar ni normalizar la salida. `raw_response` es el cuerpo HTTP tal cual y cada intento queda en `attempts`.

## Contrato de registro

- `contracts/output-record-schema.json` no se toca sin avisar a los 3 devs.
- Desde la versión 2.1, cada registro lleva `request_params` y `usage` de su `LLMCall` (el resto del bloque `llm` propuesto —`endpoint`, `base_url`, `content`, `finish_reason`, `raw_response`, `attempts`, `duration_seconds`— sigue sin registrarse).

## Pool del experimento

- Groq, plan Free, relevado el 2026-09-25: `openai/gpt-oss-120b` (priority 1), `openai/gpt-oss-20b` (2), `qwen/qwen3.8-27b` (3, preview). Cada uno: 30 RPM, 1K RPD, 8K TPM, 200K TPD.
- Revalidar contra la documentación de Groq antes de cambiar el pool; no asumir modelos de memoria.
