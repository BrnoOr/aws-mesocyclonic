---
inclusion: always
---

# Contexto del proyecto — hackatón CR2, detección y anticipación de tornados en Chile

## Qué hacemos
Entregamos al CR2 una lista ordenada de candidatos a tornado en Chile para 2026. Cada candidato es una
**celda de 1° × día UTC** y lleva un puntaje y los índices físicos que lo explican. Además medimos cuánta
anticipación conserva el modelo (objetivo O7) usando cortes temporales sobre ERA5.

## Datos
- ERA5 horario (NSF NCAR, `s3://nsf-ncar-era5/`, us-west-2) procesado por `scripts/model/run_days.sh`.
  Solo se bajan `u v t z` en niveles de presión y seis variables de superficie. **No hay humedad en
  niveles de presión**: no inventar índices que la necesiten; usar las variables de superficie disponibles.
- Catálogo de tornados y trombas: `data/tornados_chile.xlsx`. Un positivo es un evento del catálogo en esa
  celda y día UTC.
- Días de control: 200 días al azar de abril a septiembre, 2018–2025, a más de un día de cualquier evento.
  Son **sin etiqueta**, no negativos confirmados.
- GOES: GOES-16 hasta el 6 de abril de 2025 y GOES-19 desde el 7 de abril de 2025. Cualquier variable GOES
  debe considerar ese cambio. GLM (rayos) viene en los mismos buckets.

## Convenciones obligatorias
1. **Hemisferio sur.** La helicidad (SRH) y el STP de tornados chilenos son **negativos**. Las variables del
   modelo usan `neg_stp = -STP` y `neg_srh01 = -SRH01`, de modo que "más alto = más favorable". Nunca usar
   valor absoluto sin dejarlo documentado.
2. **Sin fugas temporales.** Una variable calculada para un corte τ solo puede usar horas ≤ τ.
3. **Sin fugas entre celdas del mismo día.** Toda validación separa por año completo (o, como mínimo, por día
   completo con todas sus celdas). Nunca separar celdas sueltas al azar.
4. **Interpretabilidad.** Todo puntaje entregado debe poder descomponerse en contribuciones por variable.
5. **Pocos positivos (~40).** Preferir modelos simples y regularizados; no agregar redes neuronales.
6. Reportar siempre conteos (ej. "29 de 40") junto a los porcentajes, y la tasa base.

## Metas (lámina 6 de la presentación)
POD ≥ 70 %, FAR ≤ 50 %, ≤ 2 días de alerta por tornado detectado. La vara física de comparación es la
regla de Marín et al. (2024): alerta si STP ≤ −0,3 o SHERBE ≥ 1.

## Estilo de código
- Python con `uv` (`uv run python ...`). No agregar dependencias si scikit-learn, pandas, numpy, xarray o
  pyarrow bastan.
- Rutas relativas a la raíz del repo; datos en `data/` (enlace a `/srv/tornados/data`), salidas en
  `data/outputs/`.
- Semillas fijas y parámetros en `scripts/model/config/model_selection.yaml`.
- Mantener compatibles los comandos que ya usa el equipo (`train.py --until`, `score.py --start --end
  --evaluate`); las opciones nuevas se agregan, no reemplazan.
- Comentarios y mensajes en español.
