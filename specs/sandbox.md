# Sandbox de los baselines — especificación para agentes

Código: `pipeline/pipeline/baselines/sandbox.py` (cliente, corre en `pipeline`) y `pipeline/pipeline/baselines/sandbox_worker.py` (worker, corre en `sandbox`). Explicación para humanos: `docs/sandbox.md`.

## Decisión

- El código Python del LLM se ejecuta solo en el contenedor `sandbox`, nunca en `pipeline`.
- `sandbox` tiene `network_mode: none`. Es la opción B del análisis en `docs/sandbox.md`: se eligió sobre una red interna (C) y sobre un contenedor por ejecución (A) porque es la menos vulnerable.
- La única comunicación entre `pipeline` y `sandbox` es la cola de archivos del volumen `sandbox-io`, montado en `/io` en ambos. No agregar red, puertos, sockets ni el socket de Docker.
- Solo la ejecución va al sandbox. El análisis estático de Baseline 2 (`ast.parse`, `mypy`) no ejecuta código y corre en `pipeline`.

## Por qué sin red

- El código del LLM no es confiable: con red podría descargar y ejecutar otra cosa o sacar datos.
- `pipeline` carga `.env`: el código ejecutado ahí podría filtrar `GROQ_API_KEY`.
- El experimento mide determinismo: un resultado que depende de la red no es reproducible.
- El engine corre sin red por contrato: los baselines no pueden tener más capacidades que el Tratamiento.

## Configuración que no se debe relajar

- Contenedor: `network_mode: none`, `init: true`, `read_only: true`, sin `env_file`, sin volúmenes del repo (solo `sandbox-io`), `cap_drop: ALL` con `cap_add` solo de `SETUID`, `SETGID` y `KILL`, `no-new-privileges:true`, `mem_limit: 512m`, `cpus: 1`, `pids_limit: 64`.
- `init: true` es obligatorio: el worker no recoge procesos huérfanos, y sin un init como PID 1 quedan zombies del usuario `sandbox`.
- Proceso hijo: usuario `sandbox` (uid 10001), `env={}`, `python -I -S`, `cwd="/"`, sesión propia, sin directorios escribibles. Límites: `RLIMIT_AS` 256 MB, `RLIMIT_NPROC` 16, `RLIMIT_NOFILE` 64, `RLIMIT_FSIZE` 1 MB y `RLIMIT_CPU` igual al timeout + 1 s.
- `/io` es `0700` de root: el hijo no puede leer ni escribir la cola.
- Un proceso nuevo por job. Al terminar cada job, matar todos los procesos del usuario `sandbox` (`kill(-1)` desde un auxiliar con ese uid).
- Lo que imprime el código va a `/dev/null`. El resultado sale por una copia privada de stdout, como la última línea JSON.
- `sandbox_worker.py` usa solo stdlib: la imagen `sandbox` copia ese archivo y nada más del repo.

## Protocolo

- Job: `jobs/<id>.json` con `code`, `env`, `function` y `timeout`. Se escribe en `.<id>.tmp` y se renombra con `os.replace`, para que el worker nunca lea un job a medio escribir.
- Resultado: `results/<id>.json`, escrito de forma atómica por el worker. El cliente lo lee y lo borra.
- `status` del resultado:
  - `ok`, con `type` y `value`;
  - `exception`, con `name` y `message`;
  - `timeout`;
  - `crash`, si el hijo terminó sin resultado.
- `type`: `Bool` si es `bool` (se chequea antes que `int`), `Int`, `String`, o `Other` con `value = repr(x)`.
- Si falta la función pedida, el resultado es `exception` con `name: "NameError"`. `SystemExit` y `KeyboardInterrupt` también se reportan como `exception`.
- Si no llega resultado en `timeout` + 30 s, el cliente borra el job y lanza `SandboxError`. Es una falla del sistema: abortar la corrida, no registrar.
- El cliente devuelve el resultado crudo. El mapeo a `outcome`, `stage` y `error` del registro lo hace cada baseline.

## Operación

- `docker compose run pipeline` levanta `sandbox` por `depends_on`.
- El worker no termina solo: después de `docker compose up`, cortar con `docker compose down`.
- Un cambio en `sandbox_worker.py` requiere `docker compose build sandbox`.
- `tests/test_sandbox.py` usa el sandbox real y se saltea si no existe `SANDBOX_IO`. Si se cambia una capa de aislamiento, agregar o ajustar el test que la prueba.

## Baselines sobre el sandbox (decidido)

- Cada baseline es un runner `(llm_raw, env, gamma) -> Verdict` y extrae `code` él mismo (`extract_code` en `baseline1.py`). `llm_raw` debe ser un objeto JSON con `code` de tipo string. Se toleran claves extra; no se repara nada.
- Baseline 1 llega siempre a `execution`. Una respuesta ilegible o sin `code` se registra como `outcome: "runtime_error"`, `stage: "execution"`, `error.code: "InvalidResponse"`, y no llega al sandbox.
- Timeout de ejecución: 5 s (`DEFAULT_TIMEOUT_SECONDS` en `sandbox.py`).
- `to_verdict` en `sandbox.py` mapea el resultado a la etapa `execution`, y lo usan ambos baselines:
  - `ok` → `executed`, con `result` igual a `type` y `value`;
  - `exception` → `runtime_error`, con `error.code` igual al nombre de la excepción (`SyntaxError`, `KeyError`, `NameError`...);
  - `timeout` → `timeout`, con `error.code: "TIMEOUT"` (el mismo código que usa el engine);
  - `crash` → `runtime_error`, con `error.code: "SANDBOX_CRASH"`.

## Baseline 2 (decidido)

Código: `pipeline/pipeline/baselines/baseline2.py`. Runner: `run_baseline_2(llm_raw, env, gamma)`.

- `data` se tipa con un `TypedDict` llamado `Data`, armado desde Γ (el del engine, nunca deducido en Python). Tipos: `Int` → `int`, `Bool` → `bool`, `String` → `str`.
- `data_preamble(gamma)` genera `from typing import TypedDict` y `Data = TypedDict("Data", {...})`, en sintaxis funcional porque una clave de Γ puede ser palabra reservada de Python. Claves en orden alfabético.
- El prompt de `baseline2` muestra ese preámbulo, pide `evaluate_rule(data: Data)` con anotaciones completas que pasen `mypy --strict`, y avisa que `Data` ya está definido.
- El preámbulo se antepone al código del LLM, tanto para mypy como para ejecutar. El código del LLM no se modifica. Los números de línea de los mensajes de mypy incluyen las 2 líneas del preámbulo.
- Etapas, en orden. La primera que falla bloquea y se registra con `outcome: "blocked"`:
  - parse: la respuesta no es un objeto JSON con `code` string → `InvalidResponse`.
  - parse: `ast.parse` falla → nombre de la excepción (`SyntaxError`, `ValueError`, `RecursionError`, `MemoryError`).
  - typecheck: no hay un `def evaluate_rule(data: Data)` a nivel de módulo con un único parámetro anotado exactamente `Data` → `SignatureMismatch`. Sin esta regla, el LLM podría anotar `dict[str, Any]` y mypy no controlaría nada. Si hay varias definiciones, se mira la última.
  - typecheck: `mypy --strict` con exit 1 (o exit 2 que menciona `rule.py:`) → `error.code: "mypy"`, `error.message` con la salida de mypy.
  - typecheck: mypy supera `MYPY_TIMEOUT_SECONDS` (60 s) → `outcome: "timeout"`, `stage: "typecheck"`, `error.code: "TIMEOUT"`.
  - execution: el programa completo va al sandbox; `to_verdict` como en Baseline 1.
- Aislamiento de mypy (`run_mypy`): subproceso `python -I -m mypy`, directorio temporal con `rule.py` y un `mypy.ini` vacío (no se lee la config del repo), `--cache-dir /dev/null`, `env={}`, cwd en el temporal para que los mensajes digan `rule.py` y no una ruta aleatoria.
- mypy ausente, o exit distinto de 0/1 sin mención a `rule.py`: `StaticCheckError`. Es falla del sistema: abortar la corrida.
- `mypy` es dependencia de ejecución en `pipeline/pyproject.toml` (ya no solo de desarrollo).
- `duration_ms` de Baseline 2 incluye el análisis estático y la ejecución, igual que el del engine incluye su typecheck.
- Resultado con versiones tipadas de las fixtures (ver `tests/test_baseline2.py`):
  - 001 y 006 ejecutan con `True`;
  - 002 y 007 se bloquean en parse (`SyntaxError`);
  - 003 y 004 se bloquean en typecheck (`mypy`);
  - 005, declarado `-> int | str`, pasa mypy y ejecuta `"Rejected"`, mientras que el engine lo bloquea.
