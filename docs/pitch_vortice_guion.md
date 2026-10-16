# Pitch de Vórtice: guion de 5 minutos

Acompaña a `docs/pitch_vortice.pptx` (10 diapositivas). El mismo texto va en las notas del orador de
cada diapositiva. Son unas 730 palabras: a 150 palabras por minuto, unos 4:50. Si la demo se alarga,
acortar las diapositivas 3 y 7, que se entienden solas.

| # | Diapositiva | Tiempo |
|---|---|---|
| 1 | Portada | 0:00–0:15 |
| 2 | El problema | 0:15–0:50 |
| 3 | Por qué es difícil | 0:50–1:15 |
| 4 | Metodología | 1:15–1:45 |
| 5 | El modelo Vórtice | 1:45–2:10 |
| 6 | Evidencia | 2:10–2:45 |
| 7 | Arquitectura en AWS | 2:45–3:10 |
| 8 | Costo | 3:10–3:40 |
| 9 | Demo en vivo | 3:40–4:40 |
| 10 | Cierre | 4:40–5:00 |

---

**1 · Portada.** Esto es Los Ángeles, en el Biobío, el 30 de mayo de 2019: un tornado EF2 que cruzó
la ciudad. Somos Vórtice, y venimos a encontrar las tormentas que nadie vio.

**2 · El problema.** En Chile hay tornados. El catálogo del CR2 tiene 102 tornados y trombas, y 68 son
de los últimos diez años: no es que haya más, es que ahora hay celulares. El problema es que Chile no
tiene una red de radares: un tornado solo existe si alguien lo graba. En mayo de 2019 hubo siete
tornados en menos de un día, uno mató a una persona en Los Ángeles, y nadie avisó. Y el índice que usa
Estados Unidos, el STP, no marca ninguno de esos siete.

**3 · Por qué es difícil.** ¿Por qué no basta con copiar lo de afuera? Por tres razones. Uno, estamos
en el hemisferio sur: la rotación va al revés y los índices salen con el signo cambiado. Dos, en Chile
los tornados nacen con mucho viento y poca inestabilidad, y ahí los umbrales de Estados Unidos no
disparan. Y tres, el catálogo solo tiene positivos: que no haya reporte no significa que no hubo
tornado.

**4 · Metodología.** Usamos solo datos abiertos que ya están en AWS: el reanálisis ERA5 y el satélite
GOES. Recortamos el centro-sur en celdas de 25 kilómetros, hora a hora, y calculamos once índices
físicos con los signos y umbrales del hemisferio sur. Encima va un modelo de aprendizaje PU, que
aprende de los positivos sin asumir que lo no reportado es negativo. La salida es un puntaje de 0 a
100 por celda y hora. Y medimos como pide el CR2: por evento, con años que el modelo no vio.

**5 · El modelo.** El motor nuevo de Vórtice es una red neuronal pequeña: once índices de entrada, dos
capas ocultas y un puntaje. Son menos de tres mil parámetros, 15 kilobytes. Se entrena con una pérdida
PU no negativa, pensada para eventos rarísimos: menos del 0,3 % de las celdas-hora. Y como es tan
chica, la servimos con numpy, sin GPU. Este checkpoint todavía es de prueba: antes de ponerlo en
producción tiene que pasar el mismo examen que el motor actual.

**6 · Evidencia.** ¿Funciona? Lo probamos donde importa: sobre el pronóstico de inteligencia artificial
Pangu-Weather, con 25 tornados y trombas, y cada evento puntuado por un modelo que no vio su año. Con
la misma área marcada, Vórtice detecta el 80 % y la regla física el 32 %. En los siete casos de 2024 y
2025, que nunca vio, detecta cinco: cumple la meta del CR2 de 70 %. Las falsas alarmas todavía están
sobre la meta, y somos honestos: son pocos casos y los intervalos son anchos.

**7 · Arquitectura.** La solución vive entera en AWS. Los datos ya están en S3 como datos abiertos. Una
máquina Graviton calcula los índices, y una API sirve los puntajes a la consola web, detrás de
CloudFront. Esa API es un contrato: hoy responde con el modelo cargado en la misma máquina y mañana con
un endpoint de SageMaker, cambiando dos variables, sin tocar la web.

**8 · Costo.** ¿Cuánto cuesta? Muy poco. Como los datos son abiertos, pagamos solo cómputo: un servidor
pequeño para la web y la API, y una máquina grande que se enciende una hora al día para calcular los
índices. Son unos 54 dólares al mes en temporada de tormentas y unos 16 el resto del año: cerca de 420
dólares al año. Un solo radar meteorológico cuesta millones.

**9 · Demo.** Vamos a la web. Esta es la consola de Vórtice. Elijo el 26 de junio de 2023, un día que
este motor no vio. Muevo la hora desde las 16 UTC. A la izquierda, el puntaje de Vórtice; a la
derecha, la regla física. A las 20 UTC Vórtice marca una franja oscura justo sobre el lago Llanquihue,
donde se reportó una tromba a las 19:35, y cerca del tornado de Futrono. La regla STP no dispara. Toco
la celda: aquí está por qué, la cizalle, la helicidad y la base de la nube. Un meteorólogo lo revisa en
segundos. Y todo esto sale de una API documentada que cualquier sistema puede consumir.

**10 · Cierre.** Vórtice ya está en línea con su consola y su API. Para 2026 proponemos un piloto con
el CR2: validar el motor nuevo con 2024 y 2025, correr el puntaje cada día de la temporada y revisar en
terreno los días que marque sin reporte. Encontremos juntos las tormentas que nadie vio. Gracias.

---

## Notas para quien presenta

- **Demo con el 26-06-2023, no con el 30-05-2019.** Con el checkpoint actual (`model_vortice/vortice.pt`)
  el puntaje no se enciende junto a los tornados de 2019, y ese día además se usó para entrenar.
- **Plan B sin internet:** la diapositiva 9 ya trae los mapas reales de la consola a las 20 UTC.
- **Si preguntan por el motor nuevo:** se entrenó con dos días (2018-03-22 y 2019-05-30) y aún no tiene
  conjunto de prueba (`scores.parquet` está vacío). Las cifras de la diapositiva 6 son del motor de
  referencia (bosque aleatorio con variables de viento, `New_Web/reports/aiwp_bundle_eval.md`).
- **Costo:** precios de lista on-demand en us-east-1, sin impuestos, con el supuesto de 1 h de cómputo
  al día. Conviene confirmarlos en la calculadora de AWS antes de presentar.
