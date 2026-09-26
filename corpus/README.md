# Corpus del experimento

Una regla por archivo JSON. Cómo escribirlas, verificarlas y correrlas: [`docs/corpus.md`](../docs/corpus.md). Reglas adaptadas de fuentes reales: [`docs/corpus-fuentes.md`](../docs/corpus-fuentes.md).

```powershell
docker compose run --rm pipeline python -m pipeline check-case /workspace/corpus --write
```
