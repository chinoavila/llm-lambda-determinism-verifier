# Orquestador — especificación para agentes

Código: `pipeline/pipeline/orchestrator.py`. Explicación para humanos: `docs/orquestador.md`. Contratos: `contracts/README.md`.

## Triple llamada por caso

- "Triple llamada por grupo" significa una llamada al LLM por grupo del caso: `treatment`, `baseline1` y `baseline2`, en ese orden. No son repeticiones dentro de un grupo.
- Las tres llamadas usan el mismo `ModelAssignment` (un modelo por caso, ver `specs/llm-client.md`). Nunca pedir otro modelo dentro de un caso.
- Cada grupo recibe su propio prompt (`build_messages`). Los tres piden JSON.
- `run_case` devuelve los tres registros; no los escribe. Obtener el modelo (`balancer.acquire()`) y Γ (`print_gamma`) es responsabilidad de quien llama.

## Ruteo a partir del outcome de LLMCall

- `outcome != "ok"`: registrar `outcome: "llm_error"`, `stage: "llm"`, `llm_raw: null`, `duration_ms: null`, `error.code` igual al `outcome` de `LLMCall` (`generation_failed`, `quota_exhausted`, `transport_error`, `request_error`). No ejecutar nada.
- `outcome == "ok"` con `content == null`: igual que el caso anterior, con `error.code: "missing_content"`.
- `outcome == "ok"` con `content`: `llm_raw` es `content` sin transformar y se pasa tal cual al runner del grupo.
- `error.message` de un `llm_error` es texto libre (status y error del último intento). No parsearlo.
- `model` del registro sale de `LLMCall.model`.

## Runners

- Un runner es `(llm_raw, env, gamma) -> Verdict`, donde `Verdict` son los campos `outcome`, `stage`, `result` y `error` del registro y `gamma` es Γ del caso (de `print_gamma`). El resto del registro lo pone el orquestador. `route_call` recibe `gamma` como argumento de palabra clave.
- `duration_ms` lo mide el orquestador alrededor de la llamada al runner.
- Runner de `treatment`: `run_treatment`, que ignora `gamma` y llama a `run_engine`. Escribe `llm_raw` en el stdin del engine y copia el veredicto sin transformarlo.
- Runners de `baseline1` y `baseline2`: `run_baseline_1` y `run_baseline_2`, en `pipeline/pipeline/baselines/`. Reciben `llm_raw` completo y extraen `code` ellos mismos. Baseline 1 ignora `gamma`; Baseline 2 lo usa para armar `Data` (ver `specs/sandbox.md`).

## Errores del engine en validación

- Exit 0 a 3: el veredicto debe tener exactamente las claves `outcome`, `stage`, `result` y `error`, y `stage` debe coincidir con el código de salida (0 execution, 1 parse, 2 scope, 3 typecheck). Si no, `EngineError`.
- Exit 70: `outcome: "runtime_error"`, `stage: "execution"`, `error.code: "ENGINE_INTERNAL"`, `error.message` con el stderr.
- Timeout (`ENGINE_TIMEOUT_SECONDS`, 10 s): `outcome: "timeout"`, `stage: "execution"`, `error.code: "TIMEOUT"`.
- Exit 64, cualquier otro código, o un binario que no se puede ejecutar: `EngineError`. Son bugs del sistema; la corrida se aborta, no se registra.

## Registro JSON Lines

- `append_jsonl(path, records)`: un objeto por línea, UTF-8 sin escapar (`ensure_ascii=False`), separadores compactos, saltos de línea `\n`.
- Solo agrega: nunca reescribir ni truncar el archivo. Crea el directorio si falta.
- `timestamp` es UTC en ISO 8601, tomado al armar el registro.
- No agregar campos al registro: `output-record-schema.json` tiene `additionalProperties: false`. El bloque `llm` propuesto en `specs/llm-client.md` sigue pendiente de acuerdo.

## Pendiente de acuerdo del equipo

- Los códigos `missing_content` y `TIMEOUT`, y el uso del `outcome` de `LLMCall` como `error.code`, son convenciones del orquestador. Todavía no figuran en `contracts/README.md` §3; moverlos ahí requiere avisar a los otros dos desarrolladores.
- Los prompts de `build_messages` son provisorios: el equipo debe revisarlos antes de correr el experimento.
- El comando que carga los casos y corre todo de punta a punta (roadmap, Día 5) no existe todavía.
