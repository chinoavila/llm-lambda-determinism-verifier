# Misión — qué construir

> Especificación normativa para agentes. La descripción del proyecto para personas está en [`README.md`](../README.md).

## 1. Alcance (regla dirimente)

Este repositorio existe para **construir el pipeline**. Su alcance se agota en tres componentes:

| # | Componente | Lenguaje | Carpeta |
|---|---|---|---|
| **C-1** | Motor de validación STLC (parser JSON→ADT, typechecker, scope checker, evaluador) | Haskell | [`engine/`](../engine/) |
| **C-2** | Orquestador del pipeline (invocación al LLM, ruteo por grupo, registro de resultados) | Python | [`pipeline/`](../pipeline/) |
| **C-3** | Baseline 1 (sin validación) y Baseline 2 (`ast` + mypy) | Python | [`pipeline/pipeline/baselines/`](../pipeline/pipeline/baselines/) |

**Nada más.** Si una tarea no produce código, esquema o test de C-1, C-2 o C-3, no pertenece a este repositorio.

## 2. Fuera de alcance

Rechazar toda tarea que implique:

- Ejecutar corridas experimentales o producir datos.
- Recolectar, agregar, analizar o graficar resultados.
- Calcular métricas de cualquier tipo.
- Construir o poblar un corpus de datos por iniciativa propia. Excepción acordada con el equipo (2026-09-26): las reglas del experimento se versionan en [`corpus/`](../corpus/) y un agente puede escribirlas **solo cuando el desarrollador lo pide**, siguiendo [`docs/corpus.md`](../docs/corpus.md) y verificándolas con `check-case`. El corpus no es un componente: no cambia C-1, C-2 ni C-3.
- Redactar documentación académica o discutir hallazgos.
- Extender el DSL, el orquestador o los baselines más allá de lo necesario para que los tres componentes funcionen.

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
