---
inclusion: always
---

# Producto: Vórtice

Vórtice es la **demo** del proyecto de mesociclones de Chile (hackathon Breaking Barriers). Es una
sala de situación web que muestra, sobre el centro-sur de Chile, **qué celdas y horas tienen un
entorno atmosférico parecido al de los tornados y trombas documentados**, y deja comparar modelos
distintos bajo **un mismo objetivo fijo**.

## Lo que Vórtice es

- Un **banco de modelos intercambiables**: cualquier modelo que cumpla el contrato de
  `scripts/vortice/core/contract.py` se registra, se evalúa con el mismo protocolo y aparece en la
  arena. Cambiar de modelo no exige tocar la app.
- Un **objetivo congelado** en `scripts/vortice/objective.yaml`: qué se predice, con qué datos, cómo
  se parte, cómo se mide y qué regla elige al campeón. Ese archivo manda sobre cualquier modelo.
- Una **app de solo lectura** para el público: lee resultados ya calculados, no entrena ni descarga.

## Lo que Vórtice no es

- No es un pronóstico operativo: ERA5 es un reanálisis histórico, no llega a tiempo real.
- No confirma tornados: una celda con puntaje alto y sin reporte es un **candidato a revisión**.
- No entrena modelos. Entrenar es trabajo de `scripts/model/`; Vórtice consume artefactos.

## Público y tono

Jurado de la hackathon, meteorólogos y equipos que quieran sumar su modelo. Textos en español,
claros, sin exagerar cifras. Toda métrica se muestra con su conteo (`n` eventos, `n` días) y, cuando
aplique, con su intervalo bootstrap por día.

## Reglas de honestidad (no negociables)

1. `label = 0` significa **sin etiqueta**, no negativo confirmado (aprendizaje PU).
2. El brote del 30–31 de mayo de 2019 es **caso de desarrollo**: se muestra como repetición, nunca
   como prueba ciega.
3. El umbral de alerta se elige en validación (2024) y se aplica **una sola vez** a prueba (2025).
4. Se muestra siempre la línea base (climatología y reglas físicas) junto a cada modelo.
5. Las celdas sobre la cordillera (`sfc_height > 1500 m`) llevan aviso: ahí los índices de capas
   bajas de ERA5 son poco fiables.
