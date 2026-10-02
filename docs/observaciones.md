
# Observaciones sobre documentación existente

Este archivo cumple la regla del encargo: **no modificar** archivos que ya tenían documentación relevante, y registrar aquí qué se podría mejorar para mayor claridad pedagógica.

Convención: **Ubicación** → **Estado actual** → **Mejora sugerida**.

---

## Motor Haskell (`engine/`)

### `engine/src/Engine/Types.hs`

- **Estado:** Haddock de módulo con gramática; comentarios `FP[...]` en tipos y funciones.
- **Mejora:** Añadir un párrafo explícito “Entradas: JSON deserializado / Salidas: valores `Type`, `Expr`” en el bloque de módulo; tabla breve constructor JSON ↔ constructor Haskell para auditores no familiarizados con ADTs.

### `engine/src/Engine/Json.hs`

- **Estado:** Documenta frontera `ast-schema.json` y separación ADT/JSON.
- **Mejora:** Enlazar cada constructor `ParseError` con el exit code y `outcome` del veredicto (hoy está repartido entre `contracts/README.md` y `Engine.Cli`).

### `engine/src/Engine/TypeCheck.hs`

- **Estado:** Describe orden scope → typecheck y ausencia de excepciones.
- **Mejora:** Docstring por constructor `CheckError` con ejemplo JSON mínimo que lo dispara (útil para evaluadores).

### `engine/src/Engine/Eval.hs`

- **Estado:** Distingue `Runtime` vs estados `Stuck*` (bug del motor).
- **Mejora:** Diagrama ASCII de reglas de evaluación para `AND`/`OR`/`IfThenElse`/`In` (cortocircuito) en comentario de módulo — hoy está solo en contratos.

### `engine/src/Engine/Env.hs`

- **Estado:** Claro y breve.
- **Mejora:** Mencionar explícitamente el polimorfismo `Env Type` vs `Env Value` en el export list del comentario de módulo.

### `engine/src/Engine/Number.hs`

- **Estado:** Límites y exactitud documentados.
- **Mejora:** Un ejemplo numérico de `scientificDecimal` vs rechazo (`INVALID_AST`) en comentario.

### `engine/src/Engine/Cli.hs`

- **Estado:** Contrato CLI muy completo; función `run` bien explicada.
- **Mejora:** Tabla “exit code → stage → outcome” duplicada desde contratos en un solo bloque `-- |` para lectura offline del fuente.

### `engine/app/Main.hs`

- **Estado:** Comentario sobre exit 70 y UTF-8.
- **Mejora:** Bloque `-- |` de módulo `Main` con “Entradas: argv, stdin / Salidas: stdout línea única, stderr diagnóstico”.

### `engine/test/Spec.hs`

- **Estado:** Secciones `-- *` por área (JSON, typecheck, eval, CLI, fixtures); tags FP.
- **Mejora:** Haddock inicial del módulo de test explicando que `fixturesSpec` replica el contrato CLI exacto del orquestador; referencia a `contracts/fixtures/`.

---

## Pipeline Python (`pipeline/pipeline/`)

### `orchestrator.py`

- **Estado:** Docstring de módulo sólido; tipos y constantes autoexplicativos.
- **Mejora:** Docstrings en `run_case`, `run_treatment`, `read_case` con pre/postcondiciones (Γ común, timeout engine, abort on 64/70).

### `cli.py`

- **Estado:** Enumera comandos y flujo de `run`.
- **Mejora:** Tabla en docstring: subcomando → función → side effects (JSONL, LLM).

### `corpus.py`

- **Estado:** Referencia a `docs/corpus.md`.
- **Mejora:** Documentar formato de salida de `check-case` (texto vs JSON) para integradores.

### `store.py`, `jobs.py`, `server.py`

- **Estado:** Alineados con `specs/ui.md`.
- **Mejora:** En `server.py`, listar rutas `/api/*` en el docstring de módulo (hoy hay que leer el handler).

### `baselines/baseline1.py`, `baseline2.py`, `sandbox.py`, `sandbox_worker.py`

- **Estado:** Etapas y sandbox bien descritos.
- **Mejora:** En baseline2, ejemplo mínimo de `Data` generado desde Γ en comentario de `data_preamble`.

### `llm/config.py`, `balancer.py`, `client.py`, `transport.py`, `ratelimit.py`

- **Estado:** Referencias a `specs/llm-client.md`.
- **Mejora:** En `client.py`, documentar cada valor de `Outcome` con cuándo el orquestador registra `llm_error` vs reintento.

### `__init__.py`, `__main__.py`, `baselines/__init__.py`, `llm/__init__.py`

- **Estado:** Una línea; suficiente para paquetes.
- **Mejora:** Opcional: export `__all__` documentado en `pipeline/__init__.py`.

---

## Tests Python (`pipeline/tests/`)

### `test_sandbox.py`

- **Estado:** Docstring sobre dependencia del servicio sandbox.
- **Mejora:** Indicar variable de entorno mínima para skip en CI sin sandbox.

### Resto (`test_cli`, `test_orchestrator`, …)

- **Estado:** Sin docstring de módulo (se añadió encabezado mínimo en esta entrega donde faltaba).
- **Mejora:** Mantener encabezado con “qué componente verifica” y fixtures usadas.

---

## UI TypeScript (`ui/src/`)

### `api.ts`

- **Estado:** Comentario de una línea + tipos exportados.
- **Mejora:** (Aplicado encabezado ampliado en archivos sin bloque estándar.) Documentar códigos HTTP de error (`409` versión, etc.) junto a `ApiError`.

### `lib/ast.ts`, `lib/rules.ts`

- **Estado:** Comentario inicial breve.
- **Mejora:** Diferenciar explícitamente “vista legible” vs “validación de forma” vs verificación engine en servidor.

### `router.ts`, `components/ui.tsx`, `pages/RecordsPage.tsx`

- **Estado:** Comentarios parciales al inicio.
- **Mejora:** Unificar formato de encabezado (propósito / entradas / API) como en `README_v2.md` §9.

### `App.tsx`, `main.tsx`, `CorpusPage.tsx`, `RunsPage.tsx`, `RuleEditor.tsx`, `health.ts`

- **Estado:** Sin encabezado de módulo antes de esta entrega.
- **Mejora:** Encabezados añadidos; ampliar con diagrama de navegación `SECTIONS` ↔ rutas.

---

## Corpus (`corpus/tools/`)

### `dsl.py`

- **Estado:** Docstring con flujo `--write`.
- **Mejora:** Ejemplo mínimo `write_rule(...)` en docstring de módulo.

### Scripts por dominio (`fiscal_*.py`, `laboral.py`, …)

- **Estado:** Docstring con dominio y comando docker.
- **Mejora:** En cada script, párrafo “Categoría N = taxonomía de errores λRepair” alineado con experimento (referencia bibliográfica en README).

---

## Prototipo (`prototype/`)

### `gemini_mockup_pipeline.py`

- **Estado:** Aviso NO NORMATIVO muy claro + docstring histórico en inglés.
- **Mejora:** Traducir sección técnica al español y añadir tabla “mockup vs repo actual” (duplicado pedagógico de `ARCHITECTURE_v2.md` §7).

### `validaciones/haskell_validator/Types.hs`, `Typecheck.hs`, `Main.hs`

- **Estado:** Comentarios de sección en inglés; esquema JSON distinto.
- **Mejora:** Banner inicial en español: “Esquema legacy; no usar para integración”; mapeo `Double` → `Decimal` del contrato actual.

### Notebooks Colab

- **Estado:** No son código versionado ejecutable en Docker.
- **Mejora:** Índice en `prototype/README_v2_snippet.md` (opcional) con orden de lectura 1→7; no modificar notebooks in situ.

### `guia_construccion_corpus.md`, `guia_fixtures_pruebas.md`

- **Estado:** Guías en español del prototipo.
- **Mejora:** Enlazar explícitamente a `docs/corpus.md` y señalar diferencias de formato de caso vs `case-schema.json` actual.

---

## Contratos (`contracts/`)

### `README.md`, `*.json`

- **Estado:** Normativo y detallado; `$comment` en schemas.
- **Mejora:** Para auditores JSON-only, generar en docs un ejemplo completo “caso + AST + veredicto + registro JSONL” en un solo bloque (sin duplicar reglas de tipado).

---

## Documentación humana existente (`docs/`)

| Archivo | Mejora sugerida |
|---------|-----------------|
| `orquestador.md` | Sincronizar pendientes (§ Pendiente) con `contracts/README.md` cuando se cierren códigos `missing_content` / `TIMEOUT`. |
| `docker.md` | Enlace prominente a `ARCHITECTURE_v2.md` ADR-003. |
| `guia-conceptos-fp.md` | Añadir enlace a `README_v2.md` §8. |

---

## Resumen

La base de documentación **in-code del motor Haskell y del pipeline principal ya era de alta calidad** (Haddock, docstrings, tags FP). El entregable v2 **consolida** narrativa en `README_v2.md` y `ARCHITECTURE_v2.md`, **añade encabezados** donde faltaban (UI y tests), y deja aquí las **mejoras incrementales** sin sobrescribir el trabajo previo del equipo.
