# Corpus del experimento

Una regla por archivo JSON. Cómo escribirlas, verificarlas y correrlas: [`docs/corpus.md`](../docs/corpus.md). Reglas adaptadas de fuentes reales: [`docs/corpus-fuentes.md`](../docs/corpus-fuentes.md). Los JSON los escriben los scripts de [`tools/`](tools/), uno por tanda o por dominio.

```powershell
docker compose run --rm pipeline python -m pipeline check-case /workspace/corpus --write
```

## Avance

Este archivo es el registro del avance: se actualiza en el mismo commit que agrega o cambia reglas. Objetivo: 6 reglas por celda, 90 en total ([`docs/corpus.md`](../docs/corpus.md), "Estratificación y tamaño").

| Dominio | Cat. 1 · estructura | Cat. 2 · tipos | Cat. 3 · lógica | Fuente | Script |
|---|---|---|---|---|---|
| `fiscal` | **6/6** | **6/6** | **6/6** | adaptadas del IRS | `fiscal_c1.py`, `fiscal_c2.py`, `fiscal_c3.py` |
| `salud` | **6/6** | **6/6** | **6/6** | propias + IMC de Goossens (CC BY 4.0) | `salud.py` |
| `credito` | **6/6** | **6/6** | **6/6** | propias | `credito.py` |
| `seguros` | **6/6** | **6/6** | **6/6** | propias | `seguros.py` |
| `laboral` | **6/6** | **6/6** | **6/6** | propias | `laboral.py` |
| **Total** | **30/30** | **30/30** | **30/30** | **90/90** (19 adaptadas, 71 propias) | |

`check-case` sobre todo el corpus: 90/90 reglas sin errores ni avisos (2026-09-27).

### Tandas

| # | Tanda | Reglas | Estado |
|---|---|---|---|
| 1 | `fiscal` · cat. 1 | IRS-01, 02, 03, 04, 05, 07 | escritas y verificadas |
| 2 | `fiscal` · cat. 2 | IRS-09, 10, 11, 13, 15, 16 | escritas y verificadas |
| 3 | `fiscal` · cat. 3 | IRS-18, 19, 21, 23, 25, 27 | escritas y verificadas |
| 4 | `salud` · cat. 1 a 3 | `SAL-*` | escritas y verificadas |
| 5 | `credito` · cat. 1 a 3 | `CRE-*` | escritas y verificadas |
| 6 | `seguros` · cat. 1 a 3 | `SEG-*` | escritas y verificadas |
| 7 | `laboral` · cat. 1 a 3 | `LAB-*` | escritas y verificadas |

La correspondencia entre cada id `IRS-xx`, sus escenarios del examen y su publicación está en [`docs/corpus-fuentes.md`](../docs/corpus-fuentes.md). Reserva del IRS por si alguna regla no pasa la revisión: IRS-06, 08, 12, 14, 17, 20, 22, 24, 26.

### Revisión humana (paso 7 de la guía)

**Pendiente para las 90 reglas.** Es lo único que falta para cerrar el corpus: otra persona lee solo el enunciado, decide el resultado de cada escenario y lo compara con el `expected`. El estado y los comentarios de cada regla se cargan desde la UI (sección Corpus, pestaña Revisión) y quedan en el campo `review` del JSON; los scripts de `tools/` lo conservan al regenerar.

Qué conviene mirar primero:
- los supuestos y simplificaciones de las reglas fiscales ([`docs/corpus-fuentes.md`](../docs/corpus-fuentes.md), "Reglas escritas");
- que cada enunciado de categoría 2 provoque la falla de tipos sin volverse ambiguo, y que el de categoría 3 tenga una sola lectura.

La página publicada "Mesa de revisión del corpus" fue el prototipo de la UI; la fuente de verdad es esta carpeta.
