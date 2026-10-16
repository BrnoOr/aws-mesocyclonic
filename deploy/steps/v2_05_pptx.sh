#!/usr/bin/env bash
set -eo pipefail
export HOME=/root
export PATH="$HOME/.local/bin:$PATH"
cd /opt/mesocyclonic-viewer

uv run python - <<'PY'
import zipfile, re, glob
f = "docs/presentacion_producto_final.pptx"
z = zipfile.ZipFile(f)
slides = sorted([n for n in z.namelist() if re.match(r"ppt/slides/slide\d+\.xml$", n)],
                key=lambda x: int(re.search(r"(\d+)", x).group(1)))
print(f"diapositivas: {len(slides)}\n")
for s in slides:
    xml = z.read(s).decode("utf-8", "ignore")
    # Extrae el texto de los <a:t>...</a:t>
    textos = re.findall(r"<a:t>(.*?)</a:t>", xml, re.S)
    n = re.search(r"(\d+)", s).group(1)
    print(f"===== Diapositiva {n} =====")
    for t in textos:
        t = re.sub(r"&amp;", "&", t).strip()
        if t:
            print("  ", t)
    print()
PY
echo "PPTX_DONE"
