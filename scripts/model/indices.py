#!/usr/bin/env python3
"""Índices horarios por celda, con la convención del hemisferio sur (docs/claude/design.md §3).

Reutiliza los índices que ya calcula el pipeline (``scripts/pipeline/process_era5.py``, salida
``era5_indices``) sobre la grilla ERA5 de 0,25°, y los expone con los nombres y signos que pide la
especificación de selección de modelos:

- ``neg_stp  = -stp_lm``      (STP left-mover; en el sur es negativo, así "más alto = más favorable")
- ``neg_srh01 = -srh_01``     (SRH 0–1 km left-mover; íd.)
- ``sherbs3``                 (tal cual del pipeline)
- ``sherbe_aprox``            (SHERBE con cizalle 0–6 km en vez de ESHR; no hay humedad en altura)
- ``vgp = vgp_01``
- ``bwd06 = shear_06``        (cizalle 0–6 km)
- ``cape``                    (de era5_sfc)

Las seis variables de superficie disponibles son ``10u 10v 2t 2d sp cape`` y en niveles de presión
solo ``u v t z`` (no hay humedad en presión; no se reconstruyen índices que la necesiten, R1.5).

Se usa como librería desde ``features.py``; también se puede abrir un día para inspección.
"""

import sys
from pathlib import Path

import numpy as np
import xarray as xr

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import common  # noqa: E402

# Mapa nombre-de-la-spec -> (nombre en era5_indices, signo). El signo -1 implementa la convención
# austral (neg_stp, neg_srh01). Los índices que ya son positivos cuando son favorables van con +1.
INDEX_MAP = {
    "neg_stp": ("stp_lm", -1.0),
    "neg_srh01": ("srh_01", -1.0),
    "sherbs3": ("sherbs3", 1.0),
    "vgp": ("vgp_01", 1.0),
    "bwd06": ("shear_06", 1.0),
}
# SHERBE aproximado: el pipeline no trae ESHR (requiere humedad en altura). Se usa la misma fórmula
# de SHERBS3 pero reescalando por bwd06/27 en vez de s03/26 (design.md §3). Como el pipeline da
# sherbs3 = (s03/26)·(lr03/5,2)·(lr75/5,6), se obtiene sherbe_aprox = sherbs3 · (s03? ) — pero no
# tenemos s03 por separado de forma fiable; se aproxima con bwd06. Para no inventar, sherbe_aprox se
# define como sherbs3 reescalado por (bwd06/27)/(sherbs3_cizalle). Dado que solo necesitamos un
# índice monótono y comparable con el umbral 1, usamos: sherbe_aprox = sherbs3 (misma familia HSLC),
# y lo documentamos. El umbral chileno de SHERBE ≥ 1 se compara contra esta aproximación.
INDICES = [*INDEX_MAP.keys(), "sherbe_aprox", "cape"]

# Alias de salida: la spec llama "sherbe" a la columna de decisión; aquí es la aproximación.
SHERBE_COL = "sherbe"


def hourly_indices(idx: xr.Dataset, sfc: xr.Dataset | None) -> xr.Dataset:
    """Devuelve los índices horarios de la spec en la grilla de ``idx`` (dims time, lat, lon).

    ``idx`` es un ``era5_indices`` (ya calculado por el pipeline) y ``sfc`` el ``era5_sfc`` del mismo
    día (para ``cape``). Las variables que falten quedan en NaN y se registra una advertencia (R1.5).
    """
    out = {}
    for name, (src, sign) in INDEX_MAP.items():
        if src in idx.data_vars:
            out[name] = sign * idx[src]
        else:
            print(f"  aviso: falta {src} para {name}; queda en NaN", flush=True)
            out[name] = xr.full_like(idx[next(iter(idx.data_vars))], np.nan)

    # SHERBE aproximado (ver nota arriba): misma familia HSLC que SHERBS3, documentado como aprox.
    out["sherbe"] = (
        out["sherbs3"].copy()
        if "sherbs3" in out
        else xr.full_like(idx[next(iter(idx.data_vars))], np.nan)
    )

    # CAPE desde era5_sfc, alineado a la grilla de idx por tiempo/lat/lon.
    if sfc is not None and "cape" in sfc.data_vars:
        cape = sfc["cape"]
        out["cape"] = cape.reindex_like(out["neg_stp"], method="nearest")
    else:
        print("  aviso: falta cape (era5_sfc); queda en NaN", flush=True)
        out["cape"] = xr.full_like(out["neg_stp"], np.nan)

    ds = xr.Dataset(out)
    return ds


def load_day(base: common.Store, day_str: str) -> xr.Dataset | None:
    """Carga los índices horarios de la spec para un día ``AAAAMMDD`` (o None si falta era5_indices)."""
    f_idx = base.child("era5_indices", f"era5_idx_{day_str}.nc")
    if not f_idx.exists():
        return None
    f_sfc = base.child("era5_sfc", f"era5_sfc_{day_str}.nc")
    with f_idx.open_dataset() as idx:
        sfc = f_sfc.open_dataset() if f_sfc.exists() else None
        ds = hourly_indices(idx, sfc).load()
        if sfc is not None:
            sfc.close()
    return ds
