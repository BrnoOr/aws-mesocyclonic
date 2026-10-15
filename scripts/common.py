"""Utilidades compartidas por los scripts de descarga, procesamiento y visualización.

Define las regiones de análisis, las rutas de salida (en ``data/crops/`` o en un bucket de S3), el
acceso anónimo a S3 y la geometría de la grilla fija del ABI de GOES. Los scripts lo importan como
módulo hermano (``import common``), porque ``scripts/`` no es un paquete instalable.

Las rutas de datos (``DATA`` y ``CROPS``) son objetos ``store.Store``, no ``pathlib.Path``: así el
mismo código escribe en disco local o directo en un bucket del equipo según ``--data-root`` o la
variable de entorno ``MESO_DATA_ROOT`` (ver ``scripts/store.py``).
"""

import argparse
import datetime as dt
import multiprocessing as mp
import time
from collections.abc import Callable
from concurrent.futures import ProcessPoolExecutor
from dataclasses import dataclass
from pathlib import Path

import h5py
import numpy as np
import s3fs
import xarray as xr
from botocore.exceptions import BotoCoreError

import store
from store import COMPRESSION as COMPRESSION  # reexportado: scripts y figuras usan common.COMPRESSION
from store import Store

ROOT = Path(__file__).resolve().parents[1]

# Raíz de datos: ``data/`` local por defecto, o lo que fijen --data-root / MESO_DATA_ROOT.
# ``set_data_root`` la reemplaza al interpretar los argumentos de un script.
DATA = Store.at(store.default_root(None, ROOT / "data"))
CROPS = DATA.child("crops")

G = 9.80665  # m/s², gravedad estándar (geopotencial → altura)


@dataclass(frozen=True)
class Region:
    """Rectángulo lat/lon en grados; latitudes negativas al sur y longitudes negativas al oeste."""

    name: str
    north: float
    south: float
    west: float
    east: float
    label: str = ""  # nombre para la interfaz; vacío usa ``name``

    def contains(self, lat: np.ndarray, lon: np.ndarray) -> np.ndarray:
        """Máscara booleana de los puntos (``lat``, ``lon``) que caen dentro de la región."""
        return (lat <= self.north) & (lat >= self.south) & (lon >= self.west) & (lon <= self.east)


REGIONS = {
    r.name: r
    for r in (
        Region("full", -15, -60, -95, -55),
        Region("south-central", -30, -45, -76, -70, "Centro-sur de Chile"),
        Region("south-central-austral", -30, -56, -76, -66, "Centro-sur y zona austral"),
    )
}


def region_of(a: argparse.Namespace) -> Region:
    """Devuelve la región pedida en los argumentos ``a`` (predefinida o a medida con ``--bbox``)."""
    if a.bbox:
        n, s, o, e = a.bbox
        assert n > s and e > o, (
            "--bbox espera NORTH SOUTH WEST EAST con NORTH > SOUTH y EAST > WEST"
        )
        return Region(a.region, n, s, o, e)
    if a.region not in REGIONS:
        raise SystemExit(f"región desconocida {a.region!r}; usa una de {list(REGIONS)} o --bbox")
    return REGIONS[a.region]


def parser(doc: str | None, unit: str) -> argparse.ArgumentParser:
    """Parser de un script de datos con las opciones comunes.

    Trae ``--start`` y ``--end`` (fechas UTC, inclusive), ``--region`` y ``--bbox`` (región de
    trabajo) y ``--force``, que rehace lo que ya existe (``unit``: ``"los días"`` o ``"las horas"``).
    """
    p = argparse.ArgumentParser(
        description=doc, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    p.add_argument(
        "--start", type=dt.date.fromisoformat, required=True, help="primer día, AAAA-MM-DD"
    )
    p.add_argument(
        "--end", type=dt.date.fromisoformat, help="último día (inclusive); por defecto --start"
    )
    p.add_argument(
        "--region",
        default="south-central-austral",
        help=f"región predefinida: {', '.join(REGIONS)} (por defecto south-central-austral)",
    )
    p.add_argument(
        "--bbox",
        nargs=4,
        type=float,
        metavar=("NORTH", "SOUTH", "WEST", "EAST"),
        help="región a medida en grados (p. ej. -30 -45 -76 -70); se guarda con el nombre de --region",
    )
    p.add_argument("--force", action="store_true", help=f"rehace {unit} que ya existen")
    p.add_argument(
        "--data-root",
        default=None,
        metavar="RUTA",
        help=(
            "raíz de los datos: una carpeta local o un prefijo s3://bucket/prefijo "
            f"(por defecto data/ del repositorio o la variable de entorno {store.ENV_VAR})"
        ),
    )
    return p


def set_data_root(a: argparse.Namespace) -> None:
    """Fija ``DATA`` y ``CROPS`` según ``--data-root`` (o la env var ``MESO_DATA_ROOT``).

    Hay que llamarlo justo después de ``parse_args`` y antes de usar ``CROPS``/``folder``, para que la
    salida de los scripts caiga en la raíz pedida (local o S3). Si no se pasa ``--data-root`` ni la
    variable de entorno, mantiene ``data/`` dentro del repositorio.
    """
    global DATA, CROPS
    DATA = Store.at(store.default_root(a.data_root, ROOT / "data"))
    CROPS = DATA.child("crops")


def days(a: argparse.Namespace) -> list[dt.date]:
    """Lista de días entre ``a.start`` y ``a.end`` (inclusive)."""
    end = a.end or a.start
    assert end >= a.start, "--end debe ser igual o posterior a --start"
    return [a.start + dt.timedelta(days=i) for i in range((end - a.start).days + 1)]


def folder(region: str, source: str) -> Store:
    """Carpeta de salida ``<raíz>/crops/<region>/<source>/``, creada si es local y no existe."""
    d = CROPS.child(region, source)
    d.mkdir()
    return d


def write(ds: xr.Dataset, out_file: Store, encoding: dict | None = None) -> None:
    """Escribe ``ds`` en ``out_file`` (local o S3) de forma atómica.

    Sin ``encoding``, cada variable se comprime con ``COMPRESSION``. Delega en ``Store.write``: en
    local pasa por un ``.tmp`` y renombra; en S3 arma el NetCDF en un temporal y lo sube como objeto.
    """
    out_file.write(ds, encoding)


def now() -> str:
    """Marca de tiempo UTC para el atributo ``created`` de un NetCDF."""
    return dt.datetime.now(dt.UTC).isoformat(timespec="seconds")


def stamp(reg: Region) -> dict[str, str]:
    """Atributos ``region`` y ``created`` de un NetCDF de ``reg``."""
    return {
        "region": f"{reg.name}: {reg.north}..{reg.south} lat, {reg.west}..{reg.east} lon",
        "created": now(),
    }


def pool(processes: int) -> ProcessPoolExecutor:
    """Pool de procesos con contexto ``spawn`` (s3fs no tolera fork: cada proceso abre su conexión)."""
    return ProcessPoolExecutor(processes, mp_context=mp.get_context("spawn"))


def s3() -> s3fs.S3FileSystem:
    """Sistema de archivos S3 anónimo (los buckets de Open Data no requieren credenciales)."""
    return s3fs.S3FileSystem(anon=True)


def retry[T](fn: Callable[..., T], *args: object, attempts: int = 5) -> T:
    """Llama ``fn(*args)`` y reintenta ante errores de red, esperando 2, 4, 8… segundos entre intentos."""
    for k in range(attempts):
        try:
            return fn(*args)
        except (
            OSError,
            RuntimeError,
            ValueError,
            BotoCoreError,
        ) as e:  # s3fs/botocore envuelven los cortes de red (EndpointConnectionError no es OSError)
            if k == attempts - 1:
                raise
            print(
                f"  reintento {k + 1}/{attempts - 1} de {getattr(fn, '__name__', fn)}: {e!s:.120}",
                flush=True,
            )
            time.sleep(2 ** (k + 1))
    raise AssertionError("inalcanzable")


def dataset(h: h5py.File | h5py.Group, name: str) -> h5py.Dataset:
    """Devuelve el dataset ``name`` de ``h``, fallando si es un grupo u otro tipo de objeto."""
    obj = h[name]
    assert isinstance(obj, h5py.Dataset), f"{name} no es un dataset"
    return obj


def text(v: object) -> str:
    """Convierte un atributo HDF5 (``bytes``, ``str`` o arreglo) a ``str``."""
    if isinstance(v, bytes):
        return v.decode()
    if isinstance(v, np.ndarray):
        return text(v.item()) if v.size == 1 else str(v.tolist())
    return str(v)


def num(obj: h5py.Dataset, name: str) -> float:
    """Atributo numérico ``name`` de ``obj`` como ``float`` (HDF5 los guarda como arreglos de 1)."""
    return float(np.asarray(obj.attrs[name]).ravel()[0])


def axis(h: h5py.File, name: str) -> np.ndarray:
    """Eje ``name`` (``x`` o ``y``) del ABI en radianes, aplicando su escala y desplazamiento."""
    d = dataset(h, name)
    return d[:] * num(d, "scale_factor") + num(d, "add_offset")


def latlon(x: np.ndarray, y: np.ndarray, pr: h5py.Dataset) -> tuple[np.ndarray, np.ndarray]:
    """Latitud y longitud geodésicas (grados, 2D, NaN fuera del disco) de la grilla ``x`` × ``y``.

    ``x`` e ``y`` son ángulos de barrido del ABI en radianes y ``pr`` es ``goes_imager_projection``.
    Implementa la proyección geoestacionaria del GOES-R PUG (vol. 4, sección 4.2.8).
    """
    req, rpol = num(pr, "semi_major_axis"), num(pr, "semi_minor_axis")
    H = num(pr, "perspective_point_height") + req
    l0 = np.deg2rad(num(pr, "longitude_of_projection_origin"))
    X, Y = np.meshgrid(x, y)
    a = np.sin(X) ** 2 + np.cos(X) ** 2 * (np.cos(Y) ** 2 + req**2 / rpol**2 * np.sin(Y) ** 2)
    b = -2 * H * np.cos(X) * np.cos(Y)
    c = H**2 - req**2
    with np.errstate(invalid="ignore"):
        rs = (-b - np.sqrt(b**2 - 4 * a * c)) / (2 * a)
        sx, sy, sz = rs * np.cos(X) * np.cos(Y), -rs * np.sin(X), rs * np.cos(X) * np.sin(Y)
        lat = np.rad2deg(np.arctan(req**2 / rpol**2 * sz / np.sqrt((H - sx) ** 2 + sy**2)))
        lon = np.rad2deg(l0 - np.arctan(sy / (H - sx)))
    return lat, lon


def latlon_abi(h: h5py.File) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """Coordenadas de la grilla fija del ABI de un archivo GOES abierto ``h``.

    Devuelve ``(x, y, lat, lon)``: los ángulos de barrido en radianes (1D) y la latitud y longitud
    geodésicas en grados (2D, ``float32``, NaN fuera del disco), calculadas con ``latlon``.
    """
    x, y = axis(h, "x"), axis(h, "y")
    lat, lon = latlon(x, y, dataset(h, "goes_imager_projection"))
    return x, y, lat.astype("f4"), lon.astype("f4")
