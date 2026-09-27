# UI del pipeline (C-4)

> Especificación normativa para agentes. Explicación para personas: [`docs/ui.md`](../docs/ui.md). Alcance: [`mission.md`](./mission.md) §1.

## Qué es

- Una SPA (React + Vite + TypeScript + Tailwind) en `ui/` y una API HTTP en `pipeline/pipeline/server.py`, servidas juntas por `python -m pipeline serve`.
- Ejecuta las acciones del pipeline que hoy existen en la CLI: gestionar el corpus (`check-case`), correr el pipeline (`run`) y explorar los registros. No agrega lógica de dominio propia: la API llama a las mismas funciones que la CLI.
- No calcula métricas ni agrega resultados (`mission.md` §2). Mostrar un registro, filtrarlo o ponerlo junto a su `expected` está permitido; contar, promediar o graficar `pass@1` no.

## API

- Implementada con `http.server` de la stdlib (`ThreadingHTTPServer`). No agregar frameworks web ni dependencias al `pyproject.toml` para la API.
- Todas las rutas bajo `/api/` responden JSON (`application/json; charset=utf-8`, `Cache-Control: no-store`). Errores: `{"error": "<mensaje en español>"}` con 404 (no existe), 405 (método no admitido) o el código que corresponda.
- Cualquier otra ruta `GET` sirve la SPA desde `ui/dist` (`resolve_static`): un archivo existente se sirve tal cual; una ruta sin extensión devuelve `index.html`; un archivo con extensión que no existe o una ruta que sale de `ui/dist` da 404.
- `GET /api/health`: `engine` (binario en el PATH), `sandbox_queue` (hay `SANDBOX_IO`), `llm` (`ready`, `models`, `error`), `corpus_rules` (cantidad de `corpus/*.json`), `runs` (cantidad de `out/*.jsonl`).
- **Nunca** devolver una clave de API, ni parte de ella, ni el contenido de `.env`. De la configuración del LLM solo se expone si está lista, los nombres de modelo y el mensaje de `ConfigError` (que nombra la variable, no su valor). Lo verifica `test_health_never_returns_the_api_key`.

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
2. Corpus: CRUD de `corpus/*.json` desde la UI, con `check-case` al guardar.
3. Corridas y registros: lanzar `run` con confirmación de cuota, log en vivo, cancelación y exploración de `out/<run_id>.jsonl`.
