# AGENTS.md

Instrucciones mínimas para trabajar en este repo, sean humanos o agentes de IA (Copilot, Claude, etc.).

`specs/` es normativo y para agentes (texto plano, sin diagramas ni tablas complejas). Las decisiones de arquitectura para humanos van en [`docs/`](docs/), un `.md` corto por asunto. En `docs/`, cuando ayude, incluir diagramas Mermaid (flujos, arquitectura, secuencias) y verificar su sintaxis después de escribirlos:

```powershell
docker run --rm -v "${PWD}:/data" minlag/mermaid-cli -i docs/<archivo>.md -o /tmp/out.md
```

Si el comando falla, el diagrama está roto y hay que corregirlo.

## Qué es esto

MVP de laboratorio: un pipeline que valida reglas de negocio generadas por un LLM usando un motor STLC en Haskell, contra dos baselines en Python. Ver [`README.md`](README.md) para el diseño y [`specs/`](specs/) para alcance, stack, plan de la semana y reglas de cada componente (`llm-client.md`, `orquestador.md`, `sandbox.md`). Ver [`specs/status.md`](specs/status.md) para el estado actual contra la guía de entrega de la cátedra. Después del MVP se agregó una UI (C-4) para ejecutar las acciones del pipeline desde el navegador: [`specs/ui.md`](specs/ui.md).

## Cómo levantar el entorno

```powershell
docker compose up --build
```

Esto corre el build, los gates (`cabal test` para `engine/`, `mypy` + `pytest` para `pipeline/`) y el servicio `run`, que corre el pipeline de punta a punta sobre las fixtures **con el LLM real** si `.env` tiene credenciales. Un agente no debe correr `docker compose up` ni el servicio `run` sin que el desarrollador lo pida: consume cuota del proveedor. Para verificar, usar los servicios por separado (`engine`, `pipeline`) o `docker compose run --rm -e GROQ_API_KEY= run`, que omite la corrida. Ver [`README.md`](README.md) para más comandos.

## Reglas que importan

- **Alcance:** solo construir el pipeline (`engine/`, `pipeline/`, `contracts/`) y su UI (`ui/`, `pipeline/pipeline/server.py`). No ejecutar el experimento, no calcular métricas, no analizar resultados — eso es posterior y de otra persona. Única excepción: la pantalla de Estadísticas de la UI, que resume una corrida dentro de la SPA ([`specs/ui.md`](specs/ui.md) §Estadísticas). La UI puede lanzar corridas, pero un agente no lo hace sin que el desarrollador lo pida: consume cuota igual que `run`.
- **Sandbox obligatorio:** nunca `eval`/`exec` sobre salida de un LLM fuera del contenedor `sandbox` (sin red, sin `.env`, sin filesystem del repo). No relajar su configuración; ver [`specs/sandbox.md`](specs/sandbox.md).
- **Rutas siempre relativas.** Nunca hardcodear `C:\Users\...` ni `/home/...`.
- **Sin claves en el repo.** Credenciales del LLM van por variables de entorno (`.env`, fuera de Git).
- **Cambio mínimo.** No agregues dependencias, abstracciones o features que la tarea actual no pida.
- **Verificación SOLO por Docker.** Nunca instales ni invoques GHC, Cabal, Python, mypy, pytest, Node o npm en el entorno local del anfitrión, aunque estén disponibles. Toda build y todo test corren dentro de los contenedores:
  - `docker compose build engine` / `docker compose run --rm engine cabal build && cabal test` (o simplemente `docker compose up engine`)
  - `docker compose run --rm pipeline sh -c "mypy . && pytest"` (o `docker compose up pipeline`). Levanta también `sandbox` (por `depends_on`); cortarlo con `docker compose down`. Si cambia `sandbox_worker.py`: `docker compose build sandbox`.
  - `docker compose build ui`: compila la SPA y corre `tsc` y `vitest` (etapa `ui-build`). Para probarla, `docker compose up -d ui` y abrir `http://localhost:8000`; cortarla con `docker compose down`. Dependencias nuevas de `ui/`: ver [`specs/ui.md`](specs/ui.md) (npm solo en un contenedor, sobre una copia).
  - No crear `.venv`, `dist-newstyle/`, `ui/node_modules/`, `ui/dist/` ni ningún artefacto de build fuera de los contenedores. Si aparecen, es un error y hay que borrarlos.
- **Builds largas van en background.** La primera build de `engine` compila GHC + dependencias (aeson, hspec, QuickCheck) desde cero y puede tardar varios minutos. No la corras en modo síncrono bloqueante sin avisar; preferí modo asíncrono/background y reportá progreso, o preguntá antes de lanzarla si no es urgente.

## Contratos compartidos

El JSON Schema del AST y el formato del registro de salida viven en [`contracts/`](contracts/) y son de lectura obligatoria para `engine/` y `pipeline/` por igual. Si cambiás un contrato, avisá a los otros dos desarrolladores antes de tocar código que dependa de él.
