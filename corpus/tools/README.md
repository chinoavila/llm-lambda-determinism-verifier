# Generadores del corpus

Scripts que escriben las reglas de `corpus/` a partir de su AST canónico, armado con las funciones de [`dsl.py`](dsl.py) en lugar de a mano. Un script por tanda (ver la tabla de tandas en [`../README.md`](../README.md)).

```powershell
# Escribir (o reescribir) las reglas de una tanda y calcular sus expected con el engine
docker compose run --rm pipeline python /workspace/corpus/tools/fiscal_c1.py /workspace/corpus
docker compose run --rm pipeline python -m pipeline check-case /workspace/corpus --write
```

- Corren en el contenedor `pipeline`, como todo lo demás: no usar el Python del host.
- Reescribir una tanda conserva los `expected` de los escenarios que no cambiaron, siempre que el AST sea el mismo. Si el AST cambió, se borran todos y `check-case --write` los vuelve a calcular.
- Un cambio hecho a mano en un JSON de `corpus/` se pierde si después se corre su script: corregir el script, no el JSON.
- `dsl.py` solo arma estructuras; lo que valida la regla es `check-case`.
