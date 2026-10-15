"""Comprueba la lógica del dataset (etiquetas, anticipación y particiones) sin datos descargados."""

import datetime as dt
import sys
import unittest
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts" / "dataset"))

import build_dataset as bd  # noqa: E402
import features as ft  # noqa: E402


class PartitionTest(unittest.TestCase):
    """``partition_of`` reparte por año con el brote de desarrollo (2019) aparte."""

    def test_years(self) -> None:
        """train 2018–2023 · val 2024 · test 2025 · inference 2026."""
        self.assertEqual(ft.partition_of(dt.date(2018, 3, 22)), "train")
        self.assertEqual(ft.partition_of(dt.date(2023, 6, 2)), "train")
        self.assertEqual(ft.partition_of(dt.date(2024, 6, 18)), "val")
        self.assertEqual(ft.partition_of(dt.date(2025, 5, 17)), "test")
        self.assertEqual(ft.partition_of(dt.date(2026, 1, 1)), "inference")

    def test_dev_takes_priority(self) -> None:
        """El 30 y 31 de mayo de 2019 son desarrollo, no entrenamiento."""
        self.assertEqual(ft.partition_of(dt.date(2019, 5, 30)), "dev")
        self.assertEqual(ft.partition_of(dt.date(2019, 5, 31)), "dev")

    def test_other_2019_is_train(self) -> None:
        """Otro día de 2019 cae en entrenamiento, no en desarrollo."""
        self.assertEqual(ft.partition_of(dt.date(2019, 6, 13)), "train")


class RoundHourTest(unittest.TestCase):
    """``round_hour`` lleva un ``HH:MM`` a la hora ERA5 más cercana."""

    def test_rounds_to_nearest(self) -> None:
        """21:57 → 22; 20:06 → 20; 22:42 → 23."""
        self.assertEqual(ft.round_hour("21:57"), 22)
        self.assertEqual(ft.round_hour("20:06"), 20)
        self.assertEqual(ft.round_hour("22:42"), 23)

    def test_does_not_cross_midnight(self) -> None:
        """Un redondeo que llegaría a 24 se queda en 23 para no cambiar de día."""
        self.assertEqual(ft.round_hour("23:40"), 23)

    def test_missing_is_none(self) -> None:
        """Un vacío o ilegible da ``None``."""
        self.assertIsNone(ft.round_hour(None))
        self.assertIsNone(ft.round_hour(np.nan))
        self.assertIsNone(ft.round_hour("sin hora"))


class EventsFromCatalogTest(unittest.TestCase):
    """``events_from_catalog`` toma solo positivos con hora y coordenada."""

    def _catalog(self) -> pd.DataFrame:
        """Catálogo mínimo: un positivo completo, uno sin hora y uno sin marca de evento."""
        return pd.DataFrame(
            {
                "uid": ["CL0057", "CL9998", "CL9999"],
                "date": ["2019-05-30", "2019-05-30", "2019-05-30"],
                "hour_utc": ["21:57", None, "18:00"],
                "lat": [-37.463, -37.0, -37.0],
                "lon": [-72.330, -72.0, -72.0],
                "tornado": [1, 1, 0],
                "waterspout": [0, 0, 0],
                "register": [1.0, 0.0, 0.0],
                "hour_is_range": [False, False, False],
            }
        )

    def test_keeps_only_usable_positives(self) -> None:
        """Solo el positivo con hora y coordenada se conserva, con la hora redondeada."""
        events = ft.events_from_catalog(self._catalog(), dt.date(2019, 5, 30))
        self.assertEqual(len(events), 1)
        e = events[0]
        self.assertEqual(e.uid, "CL0057")
        self.assertEqual(e.hour_utc, 22)
        self.assertEqual(e.register, 1.0)

    def test_other_day_is_empty(self) -> None:
        """Un día sin eventos devuelve una lista vacía."""
        self.assertEqual(ft.events_from_catalog(self._catalog(), dt.date(2019, 5, 31)), [])


class LabelGridTest(unittest.TestCase):
    """``label_grid`` marca las celdas cercanas al evento solo en su hora."""

    def _grid(self) -> tuple[np.ndarray, np.ndarray]:
        """Grilla pequeña de 0,25° alrededor de Los Ángeles."""
        lat = np.array([-37.25, -37.5, -37.75])
        lon = np.array([-72.5, -72.25, -72.0])
        return lat, lon

    def _event(self, hour: int, register: float = 1.0) -> ft.Event:
        """Un evento en el centro de la grilla a la hora ``hour``."""
        return ft.Event("CL0057", dt.date(2019, 5, 30), hour, -37.5, -72.25, register, False)

    def test_labels_cells_within_radius(self) -> None:
        """La celda del evento y sus vecinas dentro del radio quedan en 1."""
        lat, lon = self._grid()
        label, uid, conf = ft.label_grid(lat, lon, [self._event(22)], 22, 0.2)
        self.assertEqual(label[1, 1], 1)  # celda central
        self.assertEqual(uid[1, 1], "CL0057")
        self.assertEqual(conf[1, 1], 1)
        self.assertEqual(label[0, 0], 0)  # esquina, fuera del radio

    def test_other_hour_has_no_label(self) -> None:
        """En otra hora el evento no etiqueta ninguna celda."""
        lat, lon = self._grid()
        label, _, _ = ft.label_grid(lat, lon, [self._event(22)], 21, 0.2)
        self.assertEqual(label.sum(), 0)

    def test_weak_register_is_not_confirmed(self) -> None:
        """Un registro débil (register 0) etiqueta pero no cuenta como confirmado."""
        lat, lon = self._grid()
        label, _, conf = ft.label_grid(lat, lon, [self._event(22, register=0.0)], 22, 0.2)
        self.assertEqual(label[1, 1], 1)
        self.assertEqual(conf[1, 1], 0)


class NoLeakageTest(unittest.TestCase):
    """``check_no_leakage`` detecta un grupo (día) repartido en dos particiones."""

    def test_clean_split_passes(self) -> None:
        """Un reparto donde cada día está en una sola partición no falla."""
        df = pd.DataFrame(
            {
                "group": ["2019-05-30", "2019-05-30", "2024-06-18"],
                "partition": ["dev", "dev", "val"],
                "label": [1, 0, 0],
            }
        )
        bd.check_no_leakage({0: df})  # no lanza

    def test_leaking_group_raises(self) -> None:
        """Un día en dos particiones a la vez dispara el aserto."""
        df = pd.DataFrame(
            {
                "group": ["2019-05-30", "2019-05-30"],
                "partition": ["dev", "train"],
                "label": [1, 0],
            }
        )
        with self.assertRaises(AssertionError):
            bd.check_no_leakage({0: df})


class SummarizeGoesTest(unittest.TestCase):
    """``summarize_goes`` resume la banda térmica sobre cada celda ERA5."""

    def _dataset(self) -> object:
        """GOES sintético: 2 pasos de 10 min en una grilla fina, con un tope frío que se enfría."""
        import xarray as xr

        glat = np.array([-37.0, -37.1, -37.2])
        glon = np.array([-72.0, -72.1])
        prev = np.full((3, 2), 260.0)
        last = prev.copy()
        last[0, 0] = 220.0  # un tope que se enfría respecto del paso anterior
        bt = np.stack([prev, last])  # (time, lat, lon)
        return xr.Dataset(
            {bd.GOES_BAND: (("time", "latitude", "longitude"), bt)},
            coords={
                "time": pd.to_datetime(["2019-05-30T21:40", "2019-05-30T21:50"]),
                "latitude": glat,
                "longitude": glon,
            },
        )

    def test_min_mean_trend(self) -> None:
        """El mínimo capta el tope frío, la media promedia y la tendencia da el enfriamiento."""
        ds = self._dataset()
        lat = np.array([-37.1])
        lon = np.array([-72.05])
        out = bd.summarize_goes(ds, lat, lon, 0.15)
        self.assertAlmostEqual(float(out["goes_bt_min"][0, 0]), 220.0, places=3)
        self.assertLess(float(out["goes_bt_mean"][0, 0]), 260.0)
        self.assertLess(float(out["goes_bt_trend"][0, 0]), 0.0)  # se enfrió

    def test_empty_cell_is_nan(self) -> None:
        """Una celda sin píxeles GOES queda en ``NaN``."""
        ds = self._dataset()
        lat = np.array([-30.0])  # lejos de la grilla GOES sintética
        lon = np.array([-72.05])
        out = bd.summarize_goes(ds, lat, lon, 0.05)
        self.assertTrue(np.isnan(out["goes_bt_min"][0, 0]))


if __name__ == "__main__":
    unittest.main()
