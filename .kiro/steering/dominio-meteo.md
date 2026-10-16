---
inclusion: fileMatch
fileMatchPattern: ["scripts/vortice/**", "scripts/model/**", "scripts/dataset/**", "tests/test_vortice_*.py"]
---

# Trampas del dominio

Fuente de verdad: `docs/mesociclones_chile.md` (secciones 3, 5 y 6). Resumen operativo:

- **Hemisferio sur.** La SRH tornádica es **negativa** y la supercelda favorecida es la
  *left-mover*. En el dataset, `srh_01`, `srh_03` y `stp_lm` son negativos en los positivos.
  No invertir signos en silencio; si una regla usa `-stp_lm`, el nombre lo dice (`neg_stp`).
- **Régimen HSLC** (mucha cizalladura, poco CAPE). Los umbrales norteamericanos no sirven. Reglas
  físicas de línea base calibradas para Chile: `stp_lm ≤ −0,3`, `vgp_01 > 0,1`, `sherbs3 ≥ 1`.
- **Cordillera.** Sobre los Andes los niveles bajos están bajo tierra: avisar en celdas con
  `sfc_height > 1500 m`.
- **GOES** sin corrección de paralaje (~21 km a 53°S). `goes_*` puede ser `NaN` si falta la imagen:
  cada adaptador declara en su ficha cómo lo trata.
- **Catálogo.** Solo positivos. Que un día no tenga registro no prueba que no hubo tornado.
- **Fuga.** Agrupar siempre por `group` (día). Nunca usar como variable: `event_uid`, `confirmed`,
  `hour_is_range`, `partition`, `group`, `date`, `region`, `label`.
- **Métricas.** POD por evento con acierto tolerante, FAR por día de alerta, AUC-PR, Brier. Nunca
  *accuracy*.
