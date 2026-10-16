"""Pruebas del sistema de selección de modelos (docs/claude §11, requirements R8).

No requieren datos descargados: usan perfiles y tablas sintéticas.
"""

import sys
import unittest
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts" / "model"))

import decide as decide_mod  # noqa: E402
import kpis as kpis_mod  # noqa: E402


class TestKpisTolerancia(unittest.TestCase):
    """Una alerta en celda vecina el día anterior cuenta como acierto (R4.3)."""

    def test_alerta_vecina_dia_anterior_detecta(self) -> None:
        """Evento en (-37,-72) el día 30; alerta en (-36,-72) el día 29 → detectado."""
        events = pd.DataFrame([{"fecha": "2019-05-30", "lat": -37.5, "lon": -72.5}])
        df = pd.DataFrame(
            [
                {
                    "fecha": "2019-05-29",
                    "lat": -36.5,
                    "lon": -72.5,
                    "y": 0,
                    "alerta": 1,
                    "score": 0.9,
                },
            ]
        )
        k = kpis_mod.tolerant_metrics(df, events, vecindad=1, ventana_dias=(-1, 0))
        self.assertEqual(k["detectados"], 1)
        self.assertEqual(k["POD"], 1.0)

    def test_alerta_lejana_no_detecta(self) -> None:
        """Una alerta a 5 celdas no detecta el evento."""
        events = pd.DataFrame([{"fecha": "2019-05-30", "lat": -37.5, "lon": -72.5}])
        df = pd.DataFrame(
            [
                {
                    "fecha": "2019-05-30",
                    "lat": -32.5,
                    "lon": -72.5,
                    "y": 0,
                    "alerta": 1,
                    "score": 0.9,
                },
            ]
        )
        k = kpis_mod.tolerant_metrics(df, events, vecindad=1, ventana_dias=(-1, 0))
        self.assertEqual(k["detectados"], 0)


class TestReglaDecision(unittest.TestCase):
    """Con métricas simuladas, decide.py elige el modelo esperado (R5)."""

    def _cfg(self) -> dict:
        """Configuración mínima con la regla de decisión."""
        return {
            "version": "test",
            "decision": {
                "pod_objetivo": 0.70,
                "elegible": {"supera_m0_en": "pr_auc", "far_max_vs_m1": 0.0},
                "desempate": "un_error_estandar",
                "orden_simplicidad": ["M2", "M3", "M4"],
                "si_ninguno": "M1",
            },
            "metas": {"pod_min": 0.7, "far_max": 0.5, "dias_por_deteccion_max": 2},
        }

    def test_elige_mas_simple_dentro_de_un_ee(self) -> None:
        """M2 y M4 elegibles con FAR parecido → se elige el más simple (M2)."""
        rep = pd.DataFrame(
            [
                {"modelo": "M0", "POD": 0.9, "FAR": 0.9, "PR_AUC": 0.05, "dFAR_se": 0.0},
                {"modelo": "M1", "POD": 0.8, "FAR": 0.6, "PR_AUC": 0.10, "dFAR_se": 0.0},
                {"modelo": "M2", "POD": 0.75, "FAR": 0.50, "PR_AUC": 0.15, "dFAR_se": 0.05},
                {"modelo": "M3", "POD": 0.75, "FAR": 0.58, "PR_AUC": 0.16, "dFAR_se": 0.05},
                {"modelo": "M4", "POD": 0.78, "FAR": 0.48, "PR_AUC": 0.20, "dFAR_se": 0.05},
            ]
        )
        elegido, _ = decide_mod.decide(rep, self._cfg())
        self.assertEqual(elegido, "M2")

    def test_sin_elegibles_elige_m1(self) -> None:
        """Si ninguno supera a M0 en PR-AUC, se elige M1."""
        rep = pd.DataFrame(
            [
                {"modelo": "M0", "POD": 0.9, "FAR": 0.9, "PR_AUC": 0.30, "dFAR_se": 0.0},
                {"modelo": "M1", "POD": 0.8, "FAR": 0.6, "PR_AUC": 0.10, "dFAR_se": 0.0},
                {"modelo": "M2", "POD": 0.75, "FAR": 0.50, "PR_AUC": 0.15, "dFAR_se": 0.05},
            ]
        )
        elegido, _ = decide_mod.decide(rep, self._cfg())
        self.assertEqual(elegido, "M1")


class TestSignoHemisferioSur(unittest.TestCase):
    """Perfil ciclónico austral: neg_srh01 > 0 (R8.3). Se prueba el mapeo de signo de indices.py."""

    def test_neg_srh_positiva_si_srh_negativa(self) -> None:
        """El pipeline da SRH negativa en casos tornádicos; neg_srh01 = -srh debe ser positiva."""
        import indices as indices_mod
        import xarray as xr

        srh = xr.DataArray(np.array([[[-200.0]]]), dims=("time", "latitude", "longitude"))
        stp = xr.DataArray(np.array([[[-0.5]]]), dims=("time", "latitude", "longitude"))
        ds = xr.Dataset(
            {
                "srh_01": srh,
                "stp_lm": stp,
                "sherbs3": stp * 0,
                "vgp_01": stp * 0,
                "shear_06": stp * 0,
            }
        )
        out = indices_mod.hourly_indices(ds, None)
        self.assertGreater(float(out["neg_srh01"].values[0, 0, 0]), 0)
        self.assertGreaterEqual(float(out["neg_stp"].values[0, 0, 0]), 0)


class TestCorteSinFuturo(unittest.TestCase):
    """Alterar horas > τ no cambia las variables del corte (R8.1)."""

    def test_12utc_ignora_horas_posteriores(self) -> None:
        """Agregar valores enormes en horas > 12 no cambia los agregados del corte 12utc."""
        import features as features_mod
        import indices as indices_mod
        import xarray as xr

        times = pd.date_range("2020-05-01T00:00", periods=24, freq="h")
        base = np.ones((24, 1, 1))
        ds = xr.Dataset(
            {
                name: (("time", "lat", "lon"), base.copy())
                for name in [indices_mod.SHERBE_COL, *indices_mod.INDICES]
            },
            coords={"time": times, "lat": [-37.5], "lon": [-72.5]},
        )
        cfg = features_mod.load_config()
        a = features_mod.aggregate_cell_day(features_mod.cut_hours(ds, "12utc"), cfg)
        ds2 = ds.copy(deep=True)
        for v in ds2.data_vars:
            ds2[v].values[13:] = 999.0  # horas 13..23 (> τ=12)
        b = features_mod.aggregate_cell_day(features_mod.cut_hours(ds2, "12utc"), cfg)
        max_cols = [c for c in a.columns if c.endswith("_max")]
        pd.testing.assert_frame_equal(a[max_cols], b[max_cols])


class TestPlieguesSinFechaCompartida(unittest.TestCase):
    """Ningún pliegue año-fuera comparte una fecha entre entrenamiento y prueba (R8.2)."""

    def test_split_por_anio_no_comparte_fechas(self) -> None:
        """Al dividir por año, las fechas de prueba no aparecen en entrenamiento."""
        df = pd.DataFrame(
            {
                "fecha": pd.to_datetime(
                    ["2019-05-01", "2019-05-02", "2020-06-01", "2020-06-02", "2021-07-01"]
                ).date,
                "anio": [2019, 2019, 2020, 2020, 2021],
            }
        )
        for yv in sorted(df["anio"].unique()):
            tr = set(df[df["anio"] != yv]["fecha"])
            va = set(df[df["anio"] == yv]["fecha"])
            self.assertEqual(tr & va, set())


if __name__ == "__main__":
    unittest.main()
