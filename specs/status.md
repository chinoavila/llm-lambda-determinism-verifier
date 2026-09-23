# Estado del proyecto — guía de progreso

> Documento vivo. Se actualiza a medida que avanza [`roadmap.md`](./roadmap.md), no reemplaza a los specs normativos ([`mission.md`](./mission.md), [`tech-stack.md`](./tech-stack.md)).

**Última evaluación:** 2026-09-23, contra la guía de entrega **"Producto 2 — Desarrollo computacional"** de la cátedra.

## 1. Resumen

El repositorio está en **Día 0** del plan de [`roadmap.md`](./roadmap.md): documentación de diseño sólida, código 100% *placeholder*. Esto es consistente con el propio roadmap (que prohíbe avanzar lógica interna antes de cerrar los contratos del Día 0), pero **no cumple todavía** los requisitos de "Producto 2", que pide una primera versión funcional con algoritmos, tipos y ejemplos de ejecución reales.

## 2. Contra el contenido exigido por la guía

| Ítem exigido | Estado | Dónde vive / qué falta |
|---|---|---|
| Descripción del modelo | ✅ Cubierto | [`README.md`](../README.md), [`mission.md`](./mission.md) |
| Decisiones de diseño | ✅ Cubierto (como texto) | [`tech-stack.md`](./tech-stack.md) — ADT, `Either` para errores, evaluador *big-step*, tipado bidireccional. **No implementadas todavía.** |
| Representación de los elementos principales | ⚠️ Parcial | Gramática del DSL en prosa (`README.md`); falta como tipos Haskell reales |
| Funciones principales | ❌ Falta | `engine/src/Engine/Types.hs` no tiene funciones |
| Tipos utilizados | ❌ Falta | `Expr = Literal Int`, un solo constructor placeholder |
| Algoritmos | ❌ Falta | Typechecker y evaluador solo nombrados, no escritos |
| Código fuente | ⚠️ Existe, pero vacío | Compila pero no resuelve nada (ver `PLACEHOLDER` en cada archivo) |
| Ejemplos de ejecución | ❌ Falta | `Main.hs` solo imprime `Literal 0` |
| Resultados preliminares | ❌ Falta | No hay nada que producir todavía |

## 3. Contra la tabla de conceptos de programación funcional del curso

| Concepto | Estado | Dónde va a aparecer (según diseño ya acordado) |
|---|---|---|
| Tipos algebraicos | ⚠️ Trivial | ADT real con los 6 constructores del DSL (`Literal`, `Var`, `BinaryOp`, `IfThenElse`, `Lam`, `App`) |
| Funciones puras | ❌ | Typechecker y evaluador (`Expr -> Either TypeError Type`) |
| Recursión | ❌ | Typechecker/evaluador recorren el AST recursivamente |
| Funciones de orden superior | ❌ | `traverse`/`mapM` sobre argumentos de `App`, combinadores de parseo |
| Composición / composición funcional | ❌ | Pipeline `parse >=> typecheck >=> eval` |
| Inmutabilidad | ❌ | Entorno de tipos (Γ) y de evaluación, ambos inmutables |
| Polimorfismo | ❌ | Instancia `FromJSON`, o evaluador genérico en el tipo de resultado |
| Listas por comprensión / `map`, `filter`, `fold` | ❌ | Recorrido de entornos y validación de listas de argumentos |
| Evaluación perezosa | ❌ | Nativa de Haskell; señalar explícitamente en el evaluador |

**9 de 11 conceptos sin demostrar en código real.**

## 4. Por qué (y riesgo de calendario)

`roadmap.md` fija un "Día 0" de acuerdos entre los 3 desarrolladores (contratos JSON, gramática, CLI) antes de tocar lógica interna. El repo está fielmente ahí. El riesgo no es de diseño sino de **fecha de entrega**: si "Producto 2" vence antes de completar Día 0 + Día 1-2 del roadmap interno, hay un choque de calendario que el equipo debe resolver explícitamente (adelantar el Día 0, o acotar el subconjunto a entregar).

## 5. Subconjunto mínimo para cerrar la brecha

No hace falta el motor completo de la semana — alcanza con:

1. Cerrar [`contracts/ast-schema.json`](../contracts/ast-schema.json) con 2-3 constructores (`Literal`, `Var`, `BinaryOp` alcanza).
2. `Engine.Types`: ADT real con esos constructores + un tipo `Type` (`TInt | TBool`).
3. Typechecker recursivo (`Expr -> Either TypeError Type`) con un caso que acepta y uno que rechaza.
4. Evaluador *big-step* mínimo sobre el AST ya tipado.
5. `Main.hs` con 1-2 ejemplos de ejecución reales → resultados preliminares para la entrega.

Esto demuestra 6 de los 11 conceptos con código real, sin salirse del alcance del MVP ni tocar `pipeline/`.

## 6. Cómo mantener este documento

- Actualizar la tabla de la sección 2 y 3 cada vez que se cierre un ítem del roadmap.
- No convertir esto en un tracker de tareas: el detalle día a día vive en [`roadmap.md`](./roadmap.md); acá solo se registra el veredicto contra la guía de entrega.
- Si cambia la guía de la cátedra o el alcance de "Producto 2", reflejarlo primero acá antes de tocar `mission.md`.
