#!/usr/bin/env python3
"""Convierte el checkpoint PyTorch ``vortice.pt`` en un paquete numpy portable (``vortice_model.npz``).

El modelo Vórtice es un MLP diminuto (11 → 64 → 32 → 1, 2 881 parámetros) entrenado con
*PU learning* (Kiryo et al. 2017). Para servirlo en la API no hace falta PyTorch: basta reproducir
el paso hacia adelante con numpy. Este script extrae los pesos, la normalización y los metadatos del
checkpoint y los guarda en ``New_Web/vortice_model.npz`` (lo que carga ``VortexMLPPredictor``).

Requiere PyTorch solo aquí (una vez), no en el contenedor de la API. Uso::

    uv run --with torch python scripts/api/convert_vortice.py /ruta/a/vortice.pt
"""

import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_SRC = ROOT.parent / "model_vortice" / "vortice.pt"
DEFAULT_OUT = ROOT / "vortice_model.npz"


def convert(src: Path, out: Path) -> None:
    """Lee ``vortice.pt`` con PyTorch y escribe el paquete numpy equivalente en ``out``."""
    import torch  # type: ignore[import-not-found]  # solo para convertir, no se instala en el contenedor

    ckpt = torch.load(src, map_location="cpu", weights_only=False)
    sd = ckpt["state_dict"]

    def arr(name: str) -> np.ndarray:
        """Tensor del ``state_dict`` como ``float64`` de numpy."""
        return sd[name].detach().cpu().numpy().astype(np.float64)

    np.savez(
        out,
        w0=arr("net.0.weight"),
        b0=arr("net.0.bias"),
        w3=arr("net.3.weight"),
        b3=arr("net.3.bias"),
        w6=arr("net.6.weight"),
        b6=arr("net.6.bias"),
        mean=np.asarray(ckpt["mean"], dtype=np.float64),
        std=np.asarray(ckpt["std"], dtype=np.float64),
        features=np.asarray(list(ckpt["features"])),
        threshold=np.float64(ckpt["threshold"]),
        pi=np.float64(ckpt["pi"]),
        use_goes=np.bool_(ckpt["use_goes"]),
    )
    print(f"{src.name} -> {out} ({out.stat().st_size} bytes, {len(ckpt['features'])} features)")


def main() -> None:
    """Convierte el checkpoint indicado (o el de ``model_vortice/`` por omisión)."""
    src = Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_SRC
    out = Path(sys.argv[2]) if len(sys.argv) > 2 else DEFAULT_OUT
    if not src.exists():
        raise SystemExit(f"no existe el checkpoint: {src}")
    convert(src, out)


if __name__ == "__main__":
    main()
