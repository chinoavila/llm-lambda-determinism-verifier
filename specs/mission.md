# Misión — qué construir

> Especificación normativa para agentes. La descripción del proyecto para personas está en [`README.md`](../README.md).

## 1. Alcance (regla dirimente)

Este repositorio existe para **construir el pipeline**. Su alcance se agota en tres componentes, más la UI que se agregó después del MVP:

| # | Componente | Lenguaje | Carpeta |
|---|---|---|---|
| **C-1** | Motor de validación STLC (parser JSON→ADT, typechecker, scope checker, evaluador) | Haskell | [`engine/`](../engine/) |
| **C-2** | Orquestador del pipeline (invocación al LLM, ruteo por grupo, registro de resultados) | Python | [`pipeline/`](../pipeline/) |
| **C-3** | Baseline 1 (sin validación) y Baseline 2 (`ast` + mypy) | Python | [`pipeline/pipeline/baselines/`](../pipeline/pipeline/baselines/) |
| **C-4** | UI: ejecutar desde el navegador las acciones del pipeline (corpus, corridas, registros) | TypeScript (React) + Python (API) | [`ui/`](../ui/), [`pipeline/pipeline/server.py`](../pipeline/pipeline/server.py) |

**Nada más.** Si una tarea no produce código, esquema o test de C-1, C-2, C-3 o C-4, no pertenece a este repositorio.

C-4 es una extensión posterior al MVP, decidida por el equipo el 2026-09-26: la UI ejecuta las acciones que ya existen en la CLI, sin agregar lógica de dominio. Reglas en [`ui.md`](./ui.md).

## 2. Fuera de alcance

Rechazar toda tarea que implique:

- Ejecutar corridas experimentales o producir datos por iniciativa propia. La UI (C-4) permite que el desarrollador lance una corrida; un agente no la lanza sin que se lo pidan.
- Recolectar, agregar, analizar o graficar resultados, o calcular métricas, en el pipeline (C-1, C-2, C-3), la CLI o los contratos. Excepción decidida por el desarrollador (2026-10-07): la UI (C-4) muestra estadísticas de una corrida (desenlaces, `pass@1` por grupo y su desglose, duración y errores), calculadas en la SPA a partir de sus registros. Reglas en [`ui.md`](./ui.md) §Estadísticas.
- Construir o poblar un corpus de datos por iniciativa propia. Excepción acordada con el equipo (2026-09-26): las reglas del experimento se versionan en [`corpus/`](../corpus/) y un agente puede escribirlas **solo cuando el desarrollador lo pide**, siguiendo [`docs/corpus.md`](../docs/corpus.md) y verificándolas con `check-case`. El corpus no es un componente: no cambia C-1, C-2 ni C-3.
- Redactar documentación académica o discutir hallazgos.
- Extender el DSL, el orquestador o los baselines más allá de lo necesario para que los componentes funcionen.

## 3. Qué debe hacer el pipeline construido

1. El LLM recibe una regla en lenguaje natural y emite una representación estructurada.
2. Según el grupo, esa salida se rutea a C-1 (AST JSON) o a los baselines (código Python).
3. C-1 deserializa, comprueba tipos y alcance, y **bloquea** lo inválido antes de evaluar.
4. Lo que pasa la verificación se evalúa determinísticamente.
5. C-2 registra el desenlace de cada caso: si fue bloqueado, en qué etapa, o si ejecutó y con qué resultado.

El paso 5 es **registro**, no medición: se escribe un renglón por caso, sin agregar ni interpretar.

## 4. Criterio de terminación

Un tercero clona el repositorio, configura credenciales de un LLM en `.env`, corre `docker compose up --build` y obtiene el pipeline corriendo sobre los tres grupos — **sin escribir código adicional**. MVP de laboratorio: no se busca mantenimiento a largo plazo.

## 5. Limitaciones aceptadas

El motor **no intenta** detectar lógica de negocio incorrecta que sea bien tipada. Solo intercepta fallos estructurales, de tipos y de alcance. Esta limitación es de diseño y se documenta, no se compensa con código adicional.

## 6. Documentos relacionados

- Tecnologías y restricciones → [`tech-stack.md`](./tech-stack.md)
- Fases de construcción y criterios de aceptación → [`roadmap.md`](./roadmap.md)
- UI (C-4) → [`ui.md`](./ui.md)
