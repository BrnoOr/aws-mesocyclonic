#!/usr/bin/env python3
"""Genera las listas de días a descargar/procesar con ERA5 (docs/claude).

Produce archivos de texto con fechas (una por línea) en ``data/tables/dias_<grupo>.txt``:

- ``eventos``: días con al menos un evento del catálogo en temporada 2018–2025.
- ``control``: muestra aleatoria de días de temporada 2018–2025 a más de 1 día de cualquier evento
  (sin etiqueta; 200 por defecto).
- ``ciego2025``: días de temporada de 2025 (prueba ciega).
- ``puntaje2026``: días de temporada de 2026 (puntaje).

Uso::
    uv run python scripts/model/plan_days.py --n-control 200 --seed 20260115
"""

import argparse
import datetime as dt
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import common  # noqa: E402

import features as features_mod  # noqa: E402
import labels as labels_mod  # noqa: E402


def season_days(year: int, meses: tuple[int, int]) -> list[dt.date]:
    """Todos los días del rango de meses (inclusive) de un año."""
    m0, m1 = meses
    start = dt.date(year, m0, 1)
    end = dt.date(year, m1, 1)
    # último día del mes m1
    end = (dt.date(year + (m1 == 12), (m1 % 12) + 1, 1) - dt.timedelta(days=1))
    return [start + dt.timedelta(days=i) for i in range((end - start).days + 1)]


def main() -> None:
    """Punto de entrada: escribe los archivos de días por grupo."""
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--n-control", type=int, default=200)
    p.add_argument("--seed", type=int, default=20260115)
    p.add_argument("--data-root", default=None)
    a = p.parse_args()

    import store

    cfg = features_mod.load_config()
    data_store = store.Store.at(store.default_root(a.data_root, common.ROOT / "data"))
    meses = tuple(cfg["dominio"]["temporada"])
    anios = cfg["dominio"]["anios_entrenamiento"]

    events = labels_mod.load_events(data_store.child("tornados_chile.xlsx"), cfg["dominio"]["resolucion_grados"])
    ev_season = labels_mod.events_in_range(events, [*anios, 2025], meses)
    event_days = sorted({pd.Timestamp(f).date() for f in ev_season["fecha"]})

    # Controles: días de temporada 2018-2024 a más de 1 día de cualquier evento.
    rng = np.random.default_rng(a.seed)
    pool = []
    ev_set = set(event_days)
    for y in anios:
        for d in season_days(y, meses):
            if all(abs((d - e).days) > 1 for e in ev_set):
                pool.append(d)
    rng.shuffle(pool)
    control_days = sorted(pool[: a.n_control])

    ciego_eventos = [d for d in event_days if d.year == 2025]
    ciego_muestra = list(season_days(2025, meses)[::7])  # 1 de cada 7 días para cobertura
    ciego = sorted(set(ciego_eventos + ciego_muestra))

    out_dir = data_store.child("tables")
    out_dir.mkdir()
    groups = {
        "eventos": [d for d in event_days if d.year in anios],
        "control": control_days,
        "ciego2025": ciego,
    }
    for name, days in groups.items():
        f = out_dir.child(f"dias_{name}.txt")
        text = "\n".join(d.isoformat() for d in days) + "\n"
        if f.is_s3:
            with f.fs.open(f.root, "w") as fh:
                fh.write(text)
        else:
            Path(f.root).parent.mkdir(parents=True, exist_ok=True)
            Path(f.root).write_text(text, encoding="utf-8")
        print(f"dias_{name}: {len(days)} días -> {f.root}", flush=True)


if __name__ == "__main__":
    main()
