# UI del pipeline (C-4)

> Especificación normativa para agentes. Explicación para personas: [`docs/ui.md`](../docs/ui.md). Alcance: [`mission.md`](./mission.md) §1.

## Qué es

- Una SPA (React + Vite + TypeScript + Tailwind) en `ui/` y una API HTTP en `pipeline/pipeline/server.py`, servidas juntas por `python -m pipeline serve`.
- Ejecuta las acciones del pipeline que hoy existen en la CLI: gestionar el corpus (`check-case`), correr el pipeline (`run`) y explorar los registros. No agrega lógica de dominio propia: la API llama a las mismas funciones que la CLI.
- Las estadísticas de una corrida se calculan solo en la SPA, a partir de sus registros (§Estadísticas). La API no agrega ni resume: devuelve renglones (`mission.md` §2). El reporte con IA (§Reporte con IA) recibe esas estadísticas ya calculadas.

## API

- Implementada con `http.server` de la stdlib (`ThreadingHTTPServer`). No agregar frameworks web ni dependencias al `pyproject.toml` para la API.
- Todas las rutas bajo `/api/` responden JSON (`application/json; charset=utf-8`, `Cache-Control: no-store`). Errores: `{"error": "<mensaje en español>"}` con 404 (no existe), 405 (método no admitido) o el código que corresponda.
- Cualquier otra ruta `GET` sirve la SPA desde `ui/dist` (`resolve_static`): un archivo existente se sirve tal cual; una ruta sin extensión devuelve `index.html`; un archivo con extensión que no existe o una ruta que sale de `ui/dist` da 404.
- `GET /api/health`: `engine` (binario en el PATH), `sandbox_queue` (hay `SANDBOX_IO`), `llm` (`ready`, `models`, `error`), `corpus_rules` (cantidad de `corpus/*.json`), `runs` (cantidad de `out/*.jsonl`).
- Corpus (`pipeline/pipeline/store.py`, clase `RuleStore`):
  - `GET /api/rules` y `GET /api/rules/{id}`: reglas de `corpus/*.json`, cada una con `_version` (hash del archivo) y `_file`. Los JSON ilegibles o sin `case_id` no se listan.
  - `POST /api/rules` crea `corpus/<slug del id>.json` (409 si el id o el archivo existen). `PUT /api/rules/{id}` reemplaza la regla; exige la `_version` leída (409 si el archivo cambió) y no permite cambiar el id. Ambas corren `check_case` + `write_expected` y responden `{"rule", "check"}`: la regla queda guardada aunque `check` tenga errores, para no perder el trabajo.
  - `reconcile_expected` al guardar: si cambió el AST se quitan todos los `expected`; si cambió el `env` de un escenario, el suyo. Un `expected` editado a mano con el mismo AST y `env` se conserva, y `check-case` lo marca si difiere del engine.
  - `DELETE /api/rules/{id}?version=...` (409 si la versión no coincide). `POST /api/rules/{id}/check` verifica y completa `expected`; `POST /api/rules/check` verifica todas sin escribir.
  - `_version` y `_file` nunca se escriben en el archivo. `review` (`status`: `pendiente` | `aprobada` | `cambios`, `comments`: `[{author, text, at}]`) es un campo del corpus que la UI edita; `check-case` y el orquestador lo ignoran.
- Corridas (`pipeline/pipeline/jobs.py`, clase `RunManager`):
  - `POST /api/runs/estimate` con `{"source": "corpus" | "fixtures", "case_ids"?: [...], "repetitions": 1-20, "model"?: id | "auto", "temperature"?: 0-2, "resume"?: run_id}` devuelve `{cases, repetitions, calls}`, con `calls = casos × 3 × repeticiones`. Con `resume`, `calls` cuenta solo las llamadas pendientes de esa corrida (`specs/orquestador.md`: no resueltas o cortadas por cuota o red), y la corrida se lanza con `--resume` sobre el mismo `run_id`, agregando al log. `model` y `temperature` pasan como `--model` y `--temperature`; el modelo se valida contra `llm.toml` en la CLI.
  - `POST /api/runs` con la misma selección más `confirm_calls`: lanza `python -m pipeline run` como subproceso (`pipeline_command`), con `--run-id` y la salida en `out/<run_id>.log`. 409 si `confirm_calls` no es exactamente `calls`, si ya hay una corrida en curso o si faltan credenciales del LLM. A lo sumo una corrida a la vez.
  - `GET /api/runs`: `{active, runs}`, con las corridas de `out/` (registros, log, última escritura y, si se lanzó desde este servidor, su estado). `POST /api/runs/{id}/cancel` termina el subproceso (los casos ya escritos quedan). `GET /api/runs/{id}/log?offset=n` devuelve el log desde `n` para leerlo de a partes.
  - `GET /api/runs/{id}/records`: los renglones del JSONL, filtrables por igualdad en `case_id`, `scenario_id`, `group`, `repetition`, `outcome`, `stage` y `model`, cada uno con el `expected` de su escenario si la regla está en `corpus/`. Nunca conteos, tasas ni resúmenes: eso lo calcula la SPA.
  - `run_id` solo admite letras, dígitos, `-` y `_`: no puede salir de `out/`.
  - Exportar: cada fila de Corridas con registros ofrece JSONL, TXT, MD, CSV, Excel (.xlsx) y PDF. Se arma en el navegador (`ui/src/lib/export.ts`) a partir de `GET /api/runs/{id}/records` sin filtros; la API no cambia. El JSONL son los registros como en `out/` (sin `expected`); los demás formatos agregan el `expected` de cada escenario. XLSX (ZIP sin comprimir) y PDF (Courier, WinAnsi) se generan sin dependencias. Solo renglones: sin conteos, tasas ni resúmenes.
- Errores de la verificación o de la corrida por el engine o el sandbox caídos: 503.
- **Nunca** devolver una clave de API, ni parte de ella, ni el contenido de `.env`. De la configuración del LLM solo se expone si está lista, los nombres de modelo y el mensaje de `ConfigError` (que nombra la variable, no su valor). Lo verifica `test_health_never_returns_the_api_key`.

## Estadísticas

- Ruta `/estadisticas/<run_id>` (sección de la navegación, con selector de corrida como Registros). Cada fila del listado de Corridas con registros tiene "Ver estadísticas".
- Se calculan en `ui/src/lib/stats.ts` (funciones puras con tests de vitest) sobre `GET /api/runs/{id}/records` y `GET /api/rules`. No hay endpoint de estadísticas ni dependencias de gráficos: tablas y barras con Tailwind y los tokens de color.
- Generación: `(case_id, group, repetition)`, con un renglón por escenario (`docs/orquestador.md`).
- Un renglón acierta si `outcome` es `executed`, tiene `result` y `expected`, y los dos coinciden en `type` y `value` (comparación estricta: `Int 5` contra `Decimal "5"` es fallo; los `Decimal` llegan en texto canónico, `contracts/README.md` §3).
- Una generación pasa si aciertan todos sus renglones. Si a algún renglón le falta `expected` (fixtures, regla fuera del corpus), queda "sin expected" y fuera del denominador.
- Una generación cortada por cuota o red (`llm_error` con `quota_exhausted` o `transport_error`) queda "pendiente": fuera del denominador, porque no es una falla del modelo. Se reintenta con "Reanudar" en Corridas.
- `pass@1` de un grupo: generaciones que pasan / generaciones con `expected`.
- Contenido: `pass@1` por grupo; desenlaces por grupo (renglones por `outcome`, y por `stage` en los bloqueos); desglose de `pass@1` por regla, categoría y dominio (las dos últimas salen de `corpus/`; un caso que no está ahí va a "fuera del corpus"); duración (n, media y mediana de `duration_ms`) y códigos de error por grupo.

## Reporte con IA

- Cada fila de Corridas con registros tiene "Generar reporte con IA". Pide confirmación dentro de la página (una llamada al LLM, consume cuota) y está deshabilitado si el LLM no está listo o si ya hay un reporte en curso. Un agente no lo usa sin pedido del desarrollador.
- La SPA arma la evidencia en `ui/src/lib/report.ts` (funciones puras con tests) reutilizando `stats.ts`: metadata de la corrida, `pass@1` por grupo y su desglose por regla, categoría, dominio y modelo, la matriz modelo × categoría, desenlaces, bloqueos por etapa, errores y duración, los indicadores de las observaciones metodológicas (`report_methodology.md` §4) y una muestra acotada de fallos (`llm_raw` truncado), para no superar el límite de tokens del proveedor.
- `POST /api/runs/{id}/report` con `{"evidence": {...}}` (`pipeline/pipeline/report.py`, clase `Reporter`). El servidor no calcula nada: arma el prompt con `report_methodology.md` y la evidencia, hace una sola llamada con el balanceador y valida la forma de la respuesta sin repararla. Responde `{report, model, usage, saved}`, con `report` = `{title, abstract, sections: [{heading, paragraphs}], observations: [{number 1-8, status: se_repite | no_se_repite | no_concluyente, text}], limitations, conclusions}`.
- Errores: 400 si `evidence` no es un objeto; 404 si la corrida no tiene registros; 409 sin credenciales o sin metodología; 429 si se agotó la cuota; 502 si el LLM falla o el informe no tiene la forma pedida; 503 si no hay modelos disponibles.
- Cada llamada guarda `out/<run_id>.report-<timestamp>.json` (evidencia, modelo, `request_params`, `usage`, respuesta cruda), también cuando el informe es inválido. No son corridas: `GET /api/runs` solo lista `*.jsonl` y `*.log`.
- El PDF lo arma la SPA con `pdfmake` (`ui/src/lib/reportPdf.ts`, importado de forma dinámica, con las fuentes embebidas): portada, resumen, secciones, contraste con las observaciones, limitaciones, conclusiones, referencias fijas de la metodología, Anexo A con las tablas de la evidencia y Anexo B con la muestra de fallos. Las cifras de las tablas salen de la evidencia, nunca del texto del LLM, y el PDF dice qué modelo redactó el texto.

## Seguridad

- `serve` escucha por defecto en `127.0.0.1`. En Docker escucha en `0.0.0.0` dentro del contenedor y compose publica el puerto solo en `127.0.0.1:8000`. No publicar en otra interfaz: el contenedor tiene las credenciales del LLM.
- La API no ejecuta código del LLM: eso sigue yendo por el sandbox, igual que en la CLI (`specs/sandbox.md`).
- Sin autenticación: la UI es de uso local, de una persona por máquina.

## Build y verificación

- Node, npm y `node_modules` existen solo dentro de Docker. Nunca correr `npm` en el host. Para agregar o actualizar dependencias, correr `npm install` en un contenedor `node:22-alpine` sobre una copia de `ui/` y traer de vuelta solo `package.json` y `package-lock.json`.
- La etapa `ui-build` del `Dockerfile` corre `npm ci`, `npm run check` (`tsc -p .` + `vitest run`) y `npm run build`. Si algo falla, la imagen `ui` no se construye.
- Gates: `docker compose build ui` (SPA) y `docker compose run --rm pipeline sh -c "mypy . && pytest"` (API, en `tests/test_server.py`).
- TypeScript en modo estricto (`strict`, `noUncheckedIndexedAccess`). La lógica que no es de presentación (formatos, validaciones, transformaciones) va en módulos `.ts` con tests de vitest.

## Diseño

- Sigue el prototipo aprobado ("Mesa de revisión del corpus"): tabla con búsqueda y filtros, panel lateral con pestañas para crear y editar, confirmación dentro de la página para eliminar.
- Colores como tokens semánticos en `ui/src/index.css` (`bg-surface`, `text-muted`, `border-line`, `bg-accent`, `text-bad`...), con tema claro y oscuro según el sistema. No usar colores literales en los componentes.
- Tipografías empaquetadas con `@fontsource` (la UI funciona sin internet): Instrument Sans y JetBrains Mono.
- Textos de la interfaz en español rioplatense, como el resto del repo.

## Etapas

1. Base: servidor, `GET /api/health`, SPA con navegación (Corpus, Corridas, Registros) y barra de estado. Hecha.
2. Corpus: CRUD de `corpus/*.json` desde la UI, con `check-case` al guardar. Hecha.
3. Corridas y registros: lanzar `run` con confirmación de cuota, log en vivo, cancelación y exploración de `out/<run_id>.jsonl`. Hecha.
4. Estadísticas: pantalla por corrida calculada en la SPA (§Estadísticas). Hecha.
5. Reporte con IA: informe en PDF de una corrida redactado por el LLM (§Reporte con IA). Hecha.
6. Condiciones de corrida: modelo fijo (por defecto el primero de `llm.toml`; "Automático" avisa que mezcla modelos), temperatura (por defecto 0) y 5 repeticiones por defecto; "Reanudar" en cada corrida con registros; aviso de reglas sin review aprobada (`ui/src/lib/runs.ts`). Pendiente: guardar `request_params` en el registro (cambio de contrato).

## Relación con los generadores del corpus

- Las reglas que escribe un script de `corpus/tools/` llevan `generated_by`. La UI avisa que un cambio hecho ahí se pierde si se vuelve a correr el script; el cambio tiene que llevarse también al script.
- Los scripts conservan `review` y los `expected` que siguen valiendo (`corpus/tools/dsl.py`, `write_rule`).
