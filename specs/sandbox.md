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

## Pendiente de decisión (etapa 2 en adelante, no implementar sin acuerdo)

- Quién extrae `code` del JSON `{"code": ...}` y en qué etapa se registra una respuesta ilegible o sin `code`. Propuesta: el runner del baseline, con `stage: "execution"` y `error.code: "InvalidResponse"` en Baseline 1.
- Timeout de ejecución de los baselines. Propuesta: 5 s (`DEFAULT_TIMEOUT_SECONDS`).
- Mapeo de `status` al registro. Propuesta:
  - `exception` → `runtime_error`, con el nombre de la excepción como `error.code`;
  - `timeout` → `timeout`;
  - `crash` → `runtime_error` con `SANDBOX_CRASH`.
- Tipo de `data` en la firma que exige Baseline 2: `dict[str, Any]`, un `TypedDict` construido desde Γ, o un parámetro por variable. Con `dict[str, object]`, `mypy --strict` rechaza casi toda regla por la firma y no por el modelo.
- `mypy` pasa de dependencia de desarrollo a dependencia real en `pyproject.toml` cuando se implemente Baseline 2.
