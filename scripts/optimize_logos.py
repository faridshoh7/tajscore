"""Ужимает эмблемы клубов и логотипы сайта до разумного размера.

На сайте эмблема занимает 20–64 пикселя, а исходники из интернета весят по
полмегабайта. Мобильный интернет в Таджикистане медленный и платный — каждую
новую эмблему перед загрузкой на сервер прогоняйте через этот скрипт:

    ./venv/bin/python scripts/optimize_logos.py

Файл перезаписывается на месте (имя то же), поэтому ничего в коде менять не надо.
Уже маленькие файлы не трогаются.
"""
import io
import pathlib
import sys

from PIL import Image

ROOT = pathlib.Path(__file__).resolve().parents[1]
TARGETS = {
    ROOT / "static" / "logosligaioli": 128,
}
SINGLE = {
    ROOT / "static" / "img" / "logo-round.png": 192,
    ROOT / "static" / "img" / "logo.png": 256,
    ROOT / "static" / "img" / "ligai-oli.png": 128,
}
SKIP_BELOW = 40_000   # байт: такие уже достаточно лёгкие


def shrink(path: pathlib.Path, size: int) -> None:
    before = path.stat().st_size
    if before < SKIP_BELOW:
        return
    im = Image.open(path)
    im = im.convert("RGBA")
    im.thumbnail((size, size), Image.LANCZOS)
    buf = io.BytesIO()
    im.save(buf, "PNG", optimize=True)
    data = buf.getvalue()
    if len(data) < before:
        path.write_bytes(data)
        print(f"{path.relative_to(ROOT)}: {before // 1024} КБ -> {len(data) // 1024} КБ")


def main() -> None:
    for folder, size in TARGETS.items():
        for p in sorted(folder.glob("*.png")):
            shrink(p, size)
    for p, size in SINGLE.items():
        if p.exists():
            shrink(p, size)


if __name__ == "__main__":
    sys.exit(main())
