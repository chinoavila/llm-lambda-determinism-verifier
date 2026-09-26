# Tech Stack — con qué construir

> Especificación normativa para agentes. Alcance definido en [`mission.md`](./mission.md).
>
> Solo se listan tecnologías necesarias para construir C-1, C-2 y C-3. Cualquier dependencia que no sirva a esos tres componentes queda fuera.

## 1. C-1 — Motor de validación STLC (Haskell)

| Aspecto | Decisión |
|---|---|
| Lenguaje | Haskell, GHC2021, GHC ≥ 9.4 |
| Build | Cabal, con versiones fijadas |
| Modelado del DSL | ADT (GADTs solo si son necesarios) |
| Deserialización | `aeson`: JSON → ADT. El parseo es la única frontera de entrada y rechaza lo malformado. |
| Verificación | Typechecker + scope checker propios, *bidirectional type checking* |
| Evaluación | Intérprete *big-step*, solo sobre AST ya verificado |
| Errores | `Either` / `Validation` — errores como valores, nunca excepciones |
| Tests | `hspec` + `QuickCheck` |
| Interfaz | CLI: JSON por `stdin` → veredicto JSON por `stdout`, códigos de salida estables |

**Gramática del DSL:** `Literal (Int | Bool | String)`, `Var`, `BinaryOp (> < >= <= == AND OR)`, `IfThenElse`, `Lam`, `App`. No agregar constructores que los tests no requieran.

## 2. C-2 — Orquestador del pipeline (Python)

| Aspecto | Decisión |
|---|---|
| Lenguaje | Python 3.12+ |
| Entorno | `pipeline/pyproject.toml` (deps + config de `mypy`/`pytest`), instalado dentro del contenedor Docker |
| Contrato con el LLM | JSON Schema del AST (`contracts/ast-schema.json`), para habilitar *structured output* |
| Cliente LLM | Agnóstico, OpenAI-compatible por `base_url`, con balanceo de modelos — ver [`llm-client.md`](./llm-client.md) |
| Integración con C-1 | Subproceso: escribir JSON a `stdin` del binario Haskell, leer el veredicto de `stdout` |
| Registro de salida | JSON Lines según `contracts/output-record-schema.json`: un renglón por caso, grupo, etapa alcanzada, desenlace, error si lo hubo |
| Tipado | *Type hints* obligatorios; `mypy --strict` limpio |
| Tests | `pytest` |

## 3. C-3 — Baselines (Python)

| Baseline | Qué hace | Validación previa |
|---|---|---|
| **Baseline 1** | Ejecuta el script Python del LLM tal cual | Ninguna |
| **Baseline 2** | Analiza con `ast` + `mypy` y solo ejecuta si pasa | Estática del ecosistema Python |

**Sandbox obligatorio para ambos:** subproceso aislado, sin red, sin acceso al filesystem del proyecto, con timeout.

## 4. Prohibiciones

- **Prohibido** `eval` o `exec` sobre salida de un LLM. La ejecución va siempre por el sandbox.
- **Prohibido** que C-1 dependa de la red durante la validación.
- **Prohibido** hardcodear claves de API: solo variables de entorno, `.env` fuera de Git.
- **Prohibido** reparar, reintentar o normalizar silenciosamente la salida del LLM antes de registrarla.
- **Prohibido** agregar código de agregación, cálculo de métricas, estadística o graficación — incluidas dependencias como `pandas` o `matplotlib`.
- **Prohibido** agregar dependencias que no sirvan directamente a C-1, C-2 o C-3.
- **Prohibido** que un agente de IA lea, busque, modifique o ejecute algo fuera de la raíz del repositorio (carpetas hermanas o superiores incluidas). Si falta contexto que no está en el repo, por ejemplo material de la cátedra, se le pide al desarrollador que lo pegue o lo agregue al repo; no se lo busca afuera. Única excepción: el directorio temporal propio de la sesión del agente.
- **Prohibido** hardcodear rutas absolutas de una máquina o usuario específico (por ejemplo `C:\Users\...` o `/home/...`) en código, configuración o Dockerfiles. Toda ruta debe ser relativa al repositorio o resolverse en tiempo de ejecución (variables de entorno, `argv`, working directory).

## 5. Entorno de laboratorio (Docker Compose)

Un solo `Dockerfile`, en la raíz, con una etapa por componente; cada servicio elige la suya con `target`.

| Servicio | Etapa (`target`) | Imagen base | Rol |
|---|---|---|---|
| `engine` | `engine-build` | `haskell:9.6-slim` | Corre build y tests C-1: `docker compose run --rm engine cabal test` |
| `pipeline` | `pipeline` | `python:3.12-slim` | Instala C-2/C-3 y corre gates: `docker compose run --rm pipeline sh -c "mypy . && pytest"` |

- La etapa `engine-build` compila y corre `cabal test`; solo si pasa, deja el binario en `/usr/local/bin/engine`.
- La etapa `pipeline` copia ese binario (`COPY --from=engine-build`) y el orquestador lo lanza como subproceso según el contrato CLI de `contracts/README.md` §2. En ejecución el pipeline no depende del contenedor `engine`: no se usa `depends_on`.
- `docker-compose.yml` monta `engine/`, `pipeline/` y `contracts/` como volúmenes, así que los cambios de código no requieren rebuild de imagen (solo si cambian dependencias). Excepción: el binario del engine dentro de `pipeline` es el de la última build; un cambio en `engine/` requiere `docker compose build pipeline` para llegar al orquestador.
- `docker compose up --build` corre ambos servicios y sus gates en un solo paso.
