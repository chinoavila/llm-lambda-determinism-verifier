# Corpus del experimento

Una regla por archivo JSON. Cómo escribirlas, verificarlas y correrlas: [`docs/corpus.md`](../docs/corpus.md). Reglas adaptadas de fuentes reales: [`docs/corpus-fuentes.md`](../docs/corpus-fuentes.md).

```powershell
docker compose run --rm pipeline python -m pipeline check-case /workspace/corpus --write
```

## Avance

Este archivo es el registro del avance: se actualiza en el mismo commit que agrega o cambia reglas. Objetivo: 6 reglas por celda, 90 en total ([`docs/corpus.md`](../docs/corpus.md), "Estratificación y tamaño").

| Dominio | Cat. 1 · estructura | Cat. 2 · tipos | Cat. 3 · lógica | Fuente |
|---|---|---|---|---|
| `fiscal` | **6/6** | 0/6 | 0/6 | adaptadas del IRS |
| `salud` | 0/6 | 0/6 | 0/6 | propias + IMC de Goossens |
| `credito` | 0/6 | 0/6 | 0/6 | propias |
| `seguros` | 0/6 | 0/6 | 0/6 | propias |
| `laboral` | 0/6 | 0/6 | 0/6 | propias |
| **Total** | **6/30** | **0/30** | **0/30** | **6/90** |

### Tandas

| # | Tanda | Reglas | Estado |
|---|---|---|---|
| 1 | `fiscal` · cat. 1 | IRS-01, 02, 03, 04, 05, 07 | escritas, `check-case` 6/6; falta la revisión humana |
| 2 | `fiscal` · cat. 2 | IRS-09, 10, 11, 13, 15, 16 | siguiente |
| 3 | `fiscal` · cat. 3 | IRS-18, 19, 21, 23, 25, 27 | pendiente |
| 4-7 | `salud`, `credito`, `seguros`, `laboral` · cat. 1 a 3 | 18 por dominio, propias (salvo IMC) | pendiente |

La correspondencia entre cada id `IRS-xx`, sus escenarios del examen y su publicación está en [`docs/corpus-fuentes.md`](../docs/corpus-fuentes.md). Reserva del IRS por si alguna regla no pasa la revisión: IRS-06, 08, 12, 14, 17, 20, 22, 24, 26.

### Revisión humana (paso 7 de la guía)

| Regla | Revisada por | Resultado |
|---|---|---|
| FIS-C1-EITC | — | pendiente |
| FIS-C1-ESTADO-CIVIL | — | pendiente |
| FIS-C1-RESIDENCIA | — | pendiente |
| FIS-C1-EDUCACION | — | pendiente |
| FIS-C1-GASTO-HSA | — | pendiente |
| FIS-C1-OTROS-DEP | — | pendiente |

Supuestos de las reglas escritas que conviene confirmar en la revisión: [`docs/corpus-fuentes.md`](../docs/corpus-fuentes.md), "Reglas escritas".

La copia de estas reglas en la página publicada "Mesa de revisión del corpus" es un prototipo: la fuente de verdad es esta carpeta.
