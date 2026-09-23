# AGENTS.md

Instrucciones mínimas para trabajar en este repo, sean humanos o agentes de IA (Copilot, Claude, etc.).

## Qué es esto

MVP de laboratorio: un pipeline que valida reglas de negocio generadas por un LLM usando un motor STLC en Haskell, contra dos baselines en Python. Ver [`README.md`](README.md) para el diseño y [`specs/`](specs/) para alcance, stack y plan de la semana. Ver [`specs/status.md`](specs/status.md) para el estado actual contra la guía de entrega de la cátedra.

## Cómo levantar el entorno

```powershell
docker compose up --build
```

Esto corre el build y los gates (`cabal test` para `engine/`, `mypy` + `pytest` para `pipeline/`). Ver [`README.md`](README.md) para más comandos.

## Reglas que importan

- **Alcance:** solo construir el pipeline (`engine/`, `pipeline/`, `contracts/`). No ejecutar el experimento, no calcular métricas, no analizar resultados — eso es posterior y de otra persona.
- **Sandbox obligatorio:** nunca `eval`/`exec` sobre salida de un LLM fuera de un proceso aislado sin red ni acceso al filesystem del repo.
- **Rutas siempre relativas.** Nunca hardcodear `C:\Users\...` ni `/home/...`.
- **Sin claves en el repo.** Credenciales del LLM van por variables de entorno (`.env`, fuera de Git).
- **Cambio mínimo.** No agregues dependencias, abstracciones o features que la tarea actual no pida.
- **Verificación SOLO por Docker.** Nunca instales ni invoques GHC, Cabal, Python, mypy o pytest en el entorno local del anfitrión, aunque estén disponibles. Toda build y todo test corren dentro de los contenedores:
  - `docker compose build engine` / `docker compose run --rm engine cabal build && cabal test` (o simplemente `docker compose up engine`)
  - `docker compose run --rm pipeline sh -c "mypy . && pytest"` (o `docker compose up pipeline`)
  - No crear `.venv`, `dist-newstyle/` ni ningún artefacto de build fuera de los contenedores. Si aparecen, es un error y hay que borrarlos.
- **Builds largas van en background.** La primera build de `engine` compila GHC + dependencias (aeson, hspec, QuickCheck) desde cero y puede tardar varios minutos. No la corras en modo síncrono bloqueante sin avisar; preferí modo asíncrono/background y reportá progreso, o preguntá antes de lanzarla si no es urgente.

## Contratos compartidos

El JSON Schema del AST y el formato del registro de salida viven en [`contracts/`](contracts/) y son de lectura obligatoria para `engine/` y `pipeline/` por igual. Si cambiás un contrato, avisá a los otros dos desarrolladores antes de tocar código que dependa de él.
