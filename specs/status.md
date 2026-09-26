# Estado del proyecto — guía de progreso

> Documento vivo. Se actualiza a medida que avanza [`roadmap.md`](./roadmap.md), no reemplaza a los specs normativos ([`mission.md`](./mission.md), [`tech-stack.md`](./tech-stack.md)).

**Última evaluación:** 2026-09-26, contra la guía de entrega **"Producto 2 — Desarrollo computacional"** de la cátedra.

## 1. Resumen

Los tres componentes están implementados y verificados en Docker.

- **Motor STLC (C-1):**
  - ADT del DSL extendido (aritmética, `Decimal` exacto, `NOT`, `!=`, `IN`);
  - parser que rechaza lo malformado;
  - chequeo de alcance y de tipos con errores como valores;
  - evaluador *big-step*;
  - CLI según el contrato.
- **Orquestador (C-2):**
  - cliente LLM con balanceo;
  - triple llamada por grupo y repeticiones;
  - ruteo según el desenlace de la llamada;
  - ejecución de cada generación contra todos los escenarios de su regla;
  - registro JSON Lines.
- **Baselines (C-3):**
  - sandbox sin red;
  - Baseline 1;
  - Baseline 2 con `ast` y `mypy --strict`.

**Falta el comando que corre todo de punta a punta con un LLM real** (roadmap, Día 5), y con él el primer caso ejecutado con un modelo.

## 2. Contra el contenido exigido por la guía

| Ítem exigido | Estado | Dónde vive |
|---|---|---|
| Descripción del modelo | ✅ | [`README.md`](../README.md), [`mission.md`](./mission.md) |
| Decisiones de diseño | ✅ Implementadas | `docs/` (una por asunto: [DSL](../docs/dsl-extension.md), [sandbox](../docs/sandbox.md), [orquestador](../docs/orquestador.md), [Docker](../docs/docker.md), [cliente LLM](../docs/llm-client.md)) |
| Representación de los elementos principales | ✅ | `engine/src/Engine/Types.hs`: `Type`, `LiteralValue`, `UnOp`, `BinOp`, `Expr`, `Program` |
| Funciones principales | ✅ | `parseProgram` (`Json.hs`), `scopeCheck` / `typeOf` / `checkProgram` (`TypeCheck.hs`), `eval` / `evalProgram` (`Eval.hs`), `run` (`Cli.hs`) |
| Tipos utilizados | ✅ | STLC con `Int`, `Decimal`, `Bool`, `String` y `τ → τ`; errores tipados (`ParseError`, `CheckError`, `EvalError`) |
| Algoritmos | ✅ | Chequeo de tipos por síntesis (los `Lam` vienen anotados), promoción numérica solo en operadores, evaluación *big-step* con llamada por valor y cortocircuito, aritmética racional exacta con límites |
| Código fuente | ✅ | `engine/` (Haskell), `pipeline/` (Python) |
| Ejemplos de ejecución | ✅ | 15 fixtures en [`contracts/fixtures/`](../contracts/fixtures/), ejecutadas por la CLI real en los tests del engine y del pipeline |
| Resultados preliminares | ⚠️ Solo sobre fixtures | La comparación de los tres grupos sobre las fixtures está en los tests (ver §4). No hay corridas con un LLM real: eso requiere el comando de punta a punta, y el experimento en sí queda fuera del alcance de este repo |

## 3. Contra la tabla de conceptos de programación funcional del curso

Los 27 conceptos de [`docs/guia-conceptos-fp.md`](../docs/guia-conceptos-fp.md) aparecen en el código del engine, marcados con etiquetas `FP[...]`. Para encontrar dónde se usa uno: `git grep -nF "FP[<concepto>]"`. Los de la tabla original:

| Concepto | Estado | Ejemplo en el código |
|---|---|---|
| Tipos algebraicos | ✅ | `Expr`, `Type`, `CheckError`, `EvalError` |
| Funciones puras | ✅ | `typeOf`, `eval`, `renderDecimal`: `Either` en vez de excepciones |
| Recursión | ✅ | `typeOf`, `eval`, `freeVars` recorren el AST |
| Funciones de orden superior | ✅ | `traverse` en `envFromJSON`, `mapM_` en `In`; `twice` dentro del propio DSL |
| Composición | ✅ | `parse → scope → typecheck → execution` en `validate` |
| Inmutabilidad | ✅ | Γ y el entorno de evaluación: `extend` devuelve un entorno nuevo |
| Polimorfismo | ✅ | `Env a` sirve para tipos y para valores |
| Listas por comprensión / `map`, `filter`, `fold` | ✅ | `freeVars`, `scopeCheck`, `encodeGamma` |
| Evaluación perezosa | ✅ | `scopeCheck` (primera variable libre), `--print-gamma` no lee stdin, cortocircuito de `AND`/`OR` |
| Currificación | ✅ | Constructores aplicativos en el parser; aplicación parcial en el DSL |
| Funciones lambda | ✅ | `Lam`/`App` del DSL con clausuras y alcance léxico |

## 4. Resultados preliminares sobre las fixtures

Sale de los tests, no de un experimento. El engine bloquea antes de ejecutar lo que los baselines descubren recién al ejecutar, o nunca:

| Fixture | Engine | Baseline 1 | Baseline 2 (con firma tipada) |
|---|---|---|---|
| 002, 007 (sintaxis) | bloquea en `parse` | `SyntaxError` al ejecutar | bloquea en `parse` |
| 003 (`Int > String`) | bloquea en `typecheck` | `TypeError` al ejecutar | bloquea en `typecheck` (mypy) |
| 004 (variable inexistente) | bloquea en `scope` | `KeyError` al ejecutar | bloquea en `typecheck` (mypy) |
| 005 (ramas `Int` / `String`) | bloquea (`BRANCH_MISMATCH`) | ejecuta | ejecuta si se declara `int \| str` |
| 013 (`%` sobre `Decimal`) | bloquea (`OPERAND_MISMATCH`) | ejecuta | ejecuta |
| 014 (`monto / 12`) | `Decimal` exacto | `float` (no exacto) | `Decimal` exacto |
| 011 (división por cero) | `runtime_error` controlado | `ZeroDivisionError` | — |

## 5. Pendiente para cerrar el MVP

1. El comando de punta a punta. Tiene que:
   - leer los casos (`read_case`);
   - pedir el modelo al balanceador;
   - calcular Γ (`case_gamma`) y ejecutar `run_case` con los tres runners y las repeticiones;
   - escribir el JSONL.
2. Que `docker compose up --build` corra ese comando sobre las fixtures, que es el criterio de cierre del roadmap.
3. Revisar los prompts de `build_messages` en equipo: son provisorios.
4. Confirmar con el equipo los contratos del Día 0, que ya están implementados en `develop`.
5. Opcional: la propiedad QuickCheck de *type soundness* del Día 4 del carril A.

## 6. Cómo mantener este documento

- Actualizar las tablas de las secciones 2 a 4 cada vez que se cierre un ítem del roadmap.
- No convertir esto en un tracker de tareas: el detalle día a día vive en [`roadmap.md`](./roadmap.md); acá solo se registra el veredicto contra la guía de entrega.
- Si cambia la guía de la cátedra o el alcance de "Producto 2", reflejarlo primero acá antes de tocar `mission.md`.
