# Contratos compartidos

Estos dos esquemas son el punto de acuerdo obligatorio entre `engine/` (Haskell) y `pipeline/` (Python). **Se definen el Día 0**, entre los 3 desarrolladores, antes de escribir lógica real — ver [`specs/roadmap.md`](../specs/roadmap.md).

- [`ast-schema.json`](./ast-schema.json) — el AST STLC serializado en JSON que el LLM emite y que `engine/` deserializa (grupo Tratamiento).
- [`output-record-schema.json`](./output-record-schema.json) — el registro JSON Lines que `pipeline/` escribe por cada caso, en los tres grupos.

Ninguno de los tres componentes avanza en su lógica interna hasta que ambos esquemas dejan de ser placeholders.
