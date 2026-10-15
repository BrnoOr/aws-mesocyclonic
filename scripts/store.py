"""Capa de almacenamiento que trata disco local y Amazon S3 con la misma interfaz.

Los scripts de ``scripts/pipeline/`` y el visor leen y escriben recortes NetCDF siempre a través de un
``Store``, que apunta a una raíz local (``data/crops``) o a un prefijo de S3 (``s3://bucket/crops``).
Así el mismo código escribe en disco cuando se prueba un día en el computador y directo en el bucket
del equipo cuando se corre en una máquina EC2 de ``us-west-2``, sin pasos intermedios de copia.

La raíz se elige, en orden, con el argumento ``--data-root`` de la línea de comandos, con la variable
de entorno ``MESO_DATA_ROOT`` o, si no hay ninguna, con ``data/`` dentro del repositorio. Las lecturas
de los buckets públicos de ERA5 y GOES siguen siendo anónimas (``common.s3()``); el ``Store`` de S3
usa las credenciales del entorno (el rol IAM de la máquina EC2) para escribir el bucket del equipo.

NetCDF necesita un archivo con posicionamiento (``seek``), así que no se escribe en streaming a S3:
``Store.write`` arma el NetCDF en un temporal local y luego lo sube como un solo objeto (una subida que
S3 completa de forma atómica).
"""

import os
import tempfile
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

import fsspec
import s3fs
import xarray as xr

ENV_VAR = "MESO_DATA_ROOT"
S3_SCHEME = "s3://"

# Compresión sin pérdida para todo lo que se escribe en NetCDF (gzip + shuffle).
COMPRESSION = {"zlib": True, "complevel": 4, "shuffle": True}


def _is_s3(root: str) -> bool:
    """Si ``root`` apunta a S3 (``s3://...``) en vez de a una ruta local."""
    return root.startswith(S3_SCHEME)


@dataclass(frozen=True)
class Store:
    """Raíz de datos (local o S3) con las operaciones de archivo que usan los scripts y el visor.

    ``root`` es la ruta base: un directorio local o un prefijo ``s3://bucket/prefijo``. ``fs`` es el
    sistema de archivos ``fsspec`` correspondiente, compartido por las rutas hijas que crea ``child``.
    """

    root: str
    fs: fsspec.AbstractFileSystem
    is_s3: bool

    @staticmethod
    def at(root: str | os.PathLike[str]) -> "Store":
        """Crea un ``Store`` en ``root``, local o ``s3://...`` (con las credenciales del entorno)."""
        text = os.fspath(root)
        if _is_s3(text):
            return Store(text.rstrip("/"), s3fs.S3FileSystem(), is_s3=True)
        return Store(str(Path(text)), fsspec.filesystem("file"), is_s3=False)

    def child(self, *parts: str) -> "Store":
        """Un ``Store`` en un subcamino de este, uniendo ``parts`` con ``/`` (local o S3)."""
        joined = "/".join(p.strip("/") for p in parts if p)
        if self.is_s3:
            base = self.root if not joined else f"{self.root}/{joined}"
            return Store(base, self.fs, is_s3=True)
        return Store(str(Path(self.root, *parts)), self.fs, is_s3=False)

    @property
    def name(self) -> str:
        """Último componente del camino (nombre del archivo o de la carpeta)."""
        return PurePosixPath(self.root).name if self.is_s3 else Path(self.root).name

    @property
    def stem(self) -> str:
        """Nombre sin la última extensión (como ``Path.stem``)."""
        return PurePosixPath(self.root).stem if self.is_s3 else Path(self.root).stem

    def _fspath(self) -> str:
        """Ruta que entiende ``fsspec``: sin esquema en local, con ``s3://`` en S3."""
        return self.root

    def exists(self) -> bool:
        """Si el archivo o prefijo existe."""
        return bool(self.fs.exists(self._fspath()))

    def mtime(self) -> float:
        """Fecha de modificación en segundos (0 si no existe), para la clave de caché del visor."""
        if not self.exists():
            return 0.0
        info = self.fs.info(self._fspath())
        stamp = info.get("LastModified") or info.get("mtime")
        if stamp is None:
            return 0.0
        return stamp.timestamp() if hasattr(stamp, "timestamp") else float(stamp)

    def mkdir(self) -> None:
        """Crea la carpeta en local (con sus padres); en S3 no hace nada (no hay carpetas)."""
        if not self.is_s3:
            Path(self.root).mkdir(parents=True, exist_ok=True)

    def unlink(self) -> None:
        """Borra el archivo si existe."""
        if self.exists():
            self.fs.rm_file(self._fspath())

    def glob(self, pattern: str) -> list["Store"]:
        """Rutas hijas que calzan con ``pattern`` (glob relativo), ordenadas por nombre."""
        sep = "/" if self.is_s3 else os.sep
        hits = self.fs.glob(f"{self._fspath()}{sep}{pattern}")
        if self.is_s3:
            return [Store(f"{S3_SCHEME}{h.lstrip('/')}", self.fs, is_s3=True) for h in sorted(hits)]
        return [Store(str(Path(h)), self.fs, is_s3=False) for h in sorted(hits)]

    def is_dir(self) -> bool:
        """Si el camino es una carpeta (en S3, un prefijo con objetos debajo)."""
        return bool(self.fs.isdir(self._fspath()))

    @contextmanager
    def local_copy(self) -> Iterator[Path]:
        """Da una ruta local al archivo: la propia en local; en S3, un temporal que se borra al salir.

        Para librerías que necesitan un archivo en disco (``geopandas`` leyendo un zip de shapefiles).
        """
        if not self.is_s3:
            yield Path(self.root)
            return
        suffix = PurePosixPath(self.root).suffix
        with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
            tmp_path = Path(tmp.name)
        try:
            self.fs.get_file(self._fspath(), str(tmp_path))
            yield tmp_path
        finally:
            tmp_path.unlink(missing_ok=True)

    def open_dataset(self) -> xr.Dataset:
        """Abre el NetCDF sin cargarlo a memoria (lectura perezosa, también desde S3)."""
        return xr.open_dataset(self.fs.open(self._fspath(), "rb"), engine="h5netcdf")

    def load_dataset(self) -> xr.Dataset:
        """Lee el NetCDF completo a memoria (para unirlo con otros, como en ``merge_parts``)."""
        with self.fs.open(self._fspath(), "rb") as f:
            return xr.load_dataset(f, engine="h5netcdf")

    def write(self, ds: xr.Dataset, encoding: dict | None = None) -> None:
        """Escribe ``ds`` como NetCDF comprimido.

        En local pasa por un ``.tmp`` y renombra, para no dejar un archivo a medias. En S3 arma el
        NetCDF en un temporal local y lo sube como un solo objeto.
        """
        enc = {v: COMPRESSION for v in ds.data_vars} if encoding is None else encoding
        if self.is_s3:
            with tempfile.NamedTemporaryFile(suffix=".nc", delete=False) as tmp:
                tmp_path = Path(tmp.name)
            try:
                ds.to_netcdf(tmp_path, engine="h5netcdf", encoding=enc)
                self.fs.put_file(str(tmp_path), self._fspath())
            finally:
                tmp_path.unlink(missing_ok=True)
        else:
            out = Path(self.root)
            out.parent.mkdir(parents=True, exist_ok=True)
            tmp_path = out.with_suffix(".tmp")
            ds.to_netcdf(tmp_path, engine="h5netcdf", encoding=enc)
            tmp_path.rename(out)


def default_root(root_arg: str | None, fallback: str | os.PathLike[str]) -> str:
    """Raíz de datos elegida: ``--data-root``, si no la env var, si no ``fallback`` (``data/`` local)."""
    if root_arg:
        return root_arg
    env = os.environ.get(ENV_VAR)
    if env:
        return env
    return os.fspath(fallback)
