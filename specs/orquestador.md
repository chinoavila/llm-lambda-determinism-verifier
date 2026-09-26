# Orquestador — especificación para agentes

Código: `pipeline/pipeline/orchestrator.py`. Explicación para humanos: `docs/orquestador.md`. Contratos: `contracts/README.md`.

## Triple llamada, repeticiones y escenarios

- "Triple llamada por grupo" significa una llamada al LLM por grupo del caso: `treatment`, `baseline1` y `baseline2`, en ese orden. No son repeticiones dentro de un grupo.
- Las tres llamadas usan el mismo `ModelAssignment` (un modelo por caso, ver `specs/llm-client.md`). Nunca pedir otro modelo dentro de un caso.
- Cada grupo recibe su propio prompt (`build_messages`). Los tres piden JSON.
- `run_case(case, assignment, runners, gamma, run_id=, repetitions=1)` hace `repetitions` rondas de triple llamada, todas con el mismo `ModelAssignment`. Cada llamada es una **generación**, identificada por `(run_id, case_id, group, repetition)`; `repetition` empieza en 1.
- La salida de una generación se ejecuta contra el `env` de **cada escenario** del caso, en orden, y produce un registro por escenario con su `scenario_id`. Nunca llamar al LLM por escenario.
- `run_case` devuelve los registros; no los escribe. Obtener el modelo (`balancer.acquire()`) y Γ (`case_gamma`) es responsabilidad de quien llama.

## Casos de entrada

- `load_case(data)` construye `Case(case_id, description, scenarios)` desde un objeto conforme a `contracts/case-schema.json`. Ignora los campos del corpus. Lanza `CaseError` si faltan campos, si `scenarios` está vacía o si hay `scenario_id` repetidos.
- `case_gamma(case, engine_cmd)` llama a `print_gamma` por escenario y exige que todos los Γ sean iguales; si no, `CaseError`. Ese Γ común va en el prompt y en los runners.
- `read_case(path)` lee un caso del corpus con `parse_float=Decimal` y llama a `load_case`. En `load_case`, cada `Decimal` de `env` pasa a `float` solo si `Decimal(repr(float(d))) == d` (el texto sobrevive al viaje por JSON hasta el engine y el sandbox); si no, `CaseError`. No escribir otro serializador de JSON.
- `CaseError` es error del corpus: abortar la corrida, no registrar.

## Ruteo a partir del outcome de LLMCall

- `outcome != "ok"`: registrar, en **cada escenario**, `outcome: "llm_error"`, `stage: "llm"`, `llm_raw: null`, `duration_ms: null`, `error.code` igual al `outcome` de `LLMCall` (`generation_failed`, `quota_exhausted`, `transport_error`, `request_error`). No ejecutar nada.
- `outcome == "ok"` con `content == null`: igual que el caso anterior, con `error.code: "missing_content"`.
- `outcome == "ok"` con `content`: `llm_raw` es `content` sin transformar y se pasa tal cual al runner del grupo.
- `error.message` de un `llm_error` es texto libre (status y error del último intento). No parsearlo.
- `model` del registro sale de `LLMCall.model`.

## Runners

- Un `Runner` es `(llm_raw, envs, gamma) -> list[Timed]`: recibe la misma salida del LLM y los `env` de todos los escenarios, y devuelve, en el mismo orden, un `(Verdict, duration_ms)` por escenario. `Verdict` son los campos `outcome`, `stage`, `result` y `error`. Si devuelve otra cantidad, `route_call` lanza `RuntimeError`.
- Un `ScenarioRunner` es `(llm_raw, env, gamma) -> Verdict` para un solo escenario. `per_scenario(runner)` lo convierte en `Runner` y cronometra cada escenario.
- `duration_ms` lo mide cada `Runner` por escenario (contracts/README.md §3).
- Runner de `treatment`: `per_scenario(run_treatment)`. `run_treatment` ignora `gamma` y llama a `run_engine`, que escribe `llm_raw` en el stdin del engine con el `env` del escenario y copia el veredicto sin transformarlo.
- Runner de `baseline1`: `per_scenario(run_baseline_1)`. Extrae `code` de `llm_raw`; ignora `gamma`.
- Runner de `baseline2`: `run_baseline_2_scenarios`. Hace `check_static` (parse y typecheck) **una vez por generación**; si bloquea, repite ese veredicto en todos los escenarios; si pasa, ejecuta cada escenario en el sandbox. `duration_ms` = análisis estático + ejecución del escenario. `run_baseline_2` es la versión de un escenario (tests). Ver `specs/sandbox.md`.

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
- Los prompts de `build_messages` son provisorios: el equipo debe revisarlos antes de correr el experimento. Invariante que no se debe romper: los tres grupos reciben la misma información de tipos (`TYPES_NOTE`); el Tratamiento suma la semántica del DSL (`DSL_SEMANTICS`) y los baselines, el mapeo a tipos de Python (`PYTHON_TYPES_NOTE`).
- El comando que carga los casos y corre todo de punta a punta (roadmap, Día 5) no existe todavía.
