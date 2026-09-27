# Orquestador — especificación para agentes

Código: `pipeline/pipeline/orchestrator.py`. Explicación para humanos: `docs/orquestador.md`. Contratos: `contracts/README.md`.

## Triple llamada, repeticiones y escenarios

- "Triple llamada por grupo" significa una llamada al LLM por grupo del caso: `treatment`, `baseline1` y `baseline2`, en ese orden. No son repeticiones dentro de un grupo.
- Las tres llamadas usan el mismo `ModelAssignment` (un modelo por caso, ver `specs/llm-client.md`). Nunca pedir otro modelo dentro de un caso.
- Cada grupo recibe su propio prompt (`build_messages`). Los tres piden JSON.
- El LLM solo ve `description` y Γ (más las instrucciones de su grupo). `canonical_ast`, `canonical_python`, `expected`, `source` y el resto de los campos del corpus son la clave de respuestas y nunca van al prompt. Lo verifican `test_corpus_answer_key_never_reaches_the_llm` (marcas en cada campo) y `test_corpus_descriptions_do_not_embed_the_answer_key` (cada regla de `corpus/`) en `pipeline/tests/test_orchestrator.py`.
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

## Comando de punta a punta (`python -m pipeline run`)

- Código: `pipeline/pipeline/cli.py`; entrada `pipeline/pipeline/__main__.py`.
- `python -m pipeline run [casos...] [--repetitions N] [--out-dir DIR] [--run-id ID]`. Sin casos, usa `contracts/fixtures/`. Un directorio aporta sus `*.json` en orden alfabético.
- Acepta casos en formato `contracts/case-schema.json` y también fixtures (§4): `read_case` lee una fixture como caso de un único escenario `S1` (`FIXTURE_SCENARIO_ID`).
- Antes de la primera llamada al LLM, `prepare` lee y valida **todos** los casos (formato, `case_id` sin repetir, Γ común con `case_gamma`). Un error ahí sale con código 1 sin llamar al LLM.
- Sin la clave del LLM en el entorno (`MissingCredentials`, subclase de `ConfigError`), avisa por stderr y sale con 0: así `docker compose up` sigue sirviendo para correr los gates. Cualquier otro `ConfigError` sale con 1.
- Por caso: `balancer.acquire()` (un modelo por caso), `run_case` con `RUNNERS` (`per_scenario(run_treatment)`, `per_scenario(run_baseline_1)`, `run_baseline_2_scenarios`) y `append_jsonl` apenas termina el caso.
- Salida: `<out-dir>/<run_id>.jsonl`, por defecto `out/` en la raíz del repo (montado en el contenedor, fuera de Git). `run_id` = fecha y hora UTC + 6 hex (`new_run_id`).
- `EngineError`, `SandboxError`, `StaticCheckError` y `NoModelAvailable` cortan la corrida con código 1; lo ya escrito queda. Son fallas del sistema, no desenlaces del modelo.
- Los casos corren en secuencia. No agregar concurrencia sin revisar las cuotas del pool (`specs/llm-client.md`).
- Test de punta a punta sin red: `tests/test_cli.py` responde con el `llm_raw` y el `python_code` de cada fixture y usa engine, sandbox y mypy reales.

## Verificación del corpus (`python -m pipeline check-case`)

- Código: `pipeline/pipeline/corpus.py`. Guía para humanos: `docs/corpus.md`. Las reglas del experimento se versionan en `corpus/` (ver `specs/mission.md` §2); los ejemplos válidos viven en `pipeline/tests/data/corpus/` y los tests los verifican.
- `check-case <archivos|directorios> [--write]`. Por regla: campos del corpus (`category` 1-3, `domain`, `source` con `kind` `original` o `adapted`, y en `adapted` también `reference` y `license` no vacíos, `gamma`, `canonical_ast`, `canonical_python`), `load_case`, `gamma` igual al de `case_gamma`, el engine **ejecuta** `canonical_ast` en cada escenario (si bloquea o falla, error), el Python canónico da el mismo `Result` en el sandbox, `expected` declarado igual al calculado, y balance (booleanas: ambos valores y diferencia <= 1, si no aviso; otras: al menos dos resultados distintos).
- `expected` lo calcula siempre el engine. `--write` solo completa los que faltan y solo si la regla no tiene errores; nunca pisa uno existente. Sale con 1 si alguna regla tiene errores.
- No usar `check-case` para calcular métricas ni comparar grupos: verifica el corpus, no resultados del experimento.

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
