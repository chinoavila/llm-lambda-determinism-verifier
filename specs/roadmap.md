# Roadmap — plan de 1 semana, 3 desarrolladores

> Alcance en [`mission.md`](./mission.md), tecnologías en [`tech-stack.md`](./tech-stack.md). MVP de laboratorio: no se planifica más allá de tener el pipeline corriendo de punta a punta.

Tres carriles en paralelo, uno por persona, sincronizados por los contratos de [`contracts/`](../contracts/). Cada carril corre sus propios gates en Docker:

```powershell
docker compose run --rm engine cabal test      # carril Engine
docker compose run --rm pipeline sh -c "mypy . && pytest"   # carriles Orquestador / Baselines
```

## Día 0 (medio día, los 3 juntos)

- [ ] Elegir proveedor de LLM, SDK y variables de entorno para credenciales (`.env`, nunca en el repo).
- [ ] Acordar y completar [`contracts/ast-schema.json`](../contracts/ast-schema.json): gramática STLC serializada (`Literal`, `Var`, `BinaryOp`, `IfThenElse`, `Lam`, `App`). — *propuesta en la rama `definicion-dsl`, pendiente de acuerdo.*
- [ ] Acordar y completar [`contracts/output-record-schema.json`](../contracts/output-record-schema.json): un objeto por caso, JSON Lines. — *propuesta en la rama `definicion-dsl`, pendiente de acuerdo.*
- [ ] Acordar el contrato de CLI de `engine/`: qué recibe por `stdin`, qué devuelve por `stdout`, códigos de salida. — *propuesta en [`contracts/README.md`](../contracts/README.md) §2, pendiente de acuerdo.*
- [ ] Definir 3-5 casos de prueba de punta a punta (uno por categoría de error: sintáctico, de tipos, lógico) que los tres carriles van a usar como fixtures compartidas. — *propuesta: 7 casos en [`contracts/fixtures/`](../contracts/fixtures/), pendiente de acuerdo.*

**Sin este día, los otros tres arrancan a ciegas.** No avanzar en lógica interna de ningún componente hasta que los dos JSON Schema dejen de ser placeholders.

## Carril A — `engine/` (C-1, Haskell)

- [ ] Día 1-2: ADT del DSL según el contrato; instancia `FromJSON` que rechaza estructura malformada; typechecker con errores tipados (`Either`, nunca excepciones).
- [x] Día 3: evaluador *big-step* sobre AST ya verificado; CLI según el contrato acordado el Día 0.
- [ ] Día 4: suite `hspec`/`QuickCheck` sobre las fixtures compartidas del Día 0, incluida una propiedad de *type soundness*.
- [ ] Día 5: integración con el carril B (probar el binario real desde `pipeline/`, no un mock).

**Listo cuando:** `docker compose run --rm engine cabal test` da verde y las fixtures negativas del Día 0 son interceptadas.

## Carril B — `pipeline/` orquestador (C-2, Python)

- [x] Día 1-2: cliente de LLM con salida estructurada (no partir de `prototype/gemini_mockup_pipeline.py`, no es normativo); ruteo por grupo.
- [ ] Día 3: integración por subproceso con el binario de `engine/` (contrato de CLI del Día 0); primer caso de punta a punta. — *integración por subproceso hecha (`run_engine`); falta el primer caso de punta a punta con el LLM real.*
- [x] Día 4: registro JSON Lines según el contrato; persistencia de la respuesta cruda del LLM sin transformar. — *ver [`specs/orquestador.md`](./orquestador.md).*
- [ ] Día 5: correr los tres grupos sobre las fixtures del Día 0 con un solo comando.

**Listo cuando:** un comando corre el grupo Tratamiento de punta a punta y escribe el archivo de registros.

## Carril C — `pipeline/` baselines (C-3, Python)

- [x] Día 1-2: sandbox de ejecución aislado (sin red, sin acceso al filesystem del repo, con timeout) — lo van a compartir Baseline 1 y 2. — *contenedor `sandbox`, ver [`specs/sandbox.md`](./sandbox.md).*
- [ ] Día 3: Baseline 1 (ejecución directa dentro del sandbox).
- [ ] Día 4: Baseline 2 (`ast` + `mypy --strict` antes de ejecutar; firma tipada obligatoria en el código generado, si no el control no sirve).
- [ ] Día 5: mismo formato de registro que el carril B; integración con el runner común.

**Listo cuando:** ambos baselines corren sobre las fixtures del Día 0 y emiten el mismo formato de registro que C-2.

## Día 5 (tarde, los 3 juntos)

- [ ] `docker compose up --build` corre los tres grupos de punta a punta sobre las fixtures compartidas y produce el archivo de registros.
- [ ] Actualizar el `README.md` con cualquier paso real que haya cambiado desde el Día 0.

**Criterio de cierre del MVP:** alguien clona el repo, corre `docker compose up --build`, y sin escribir código adicional obtiene el pipeline corriendo sobre los tres grupos.

---

## Fuera de este roadmap

No planificar ni implementar acá: corridas experimentales a escala, recolección o agregación de resultados, cálculo de métricas, estadística, gráficos, documentación académica. Eso es del experimento posterior, no de esta semana.
