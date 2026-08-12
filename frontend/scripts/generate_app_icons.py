"""Idempotent favicon / app-icon generation from the inDex master artwork.

The site used to point every icon slot (`rel="icon"`, `rel="shortcut icon"`,
`rel="apple-touch-icon"` and the manifest) at `public/inDex.png` — a 2000x2000
RGBA PNG weighing 1.74 MB. Browsers fetch `rel="icon"` eagerly, so every route
on the site paid 1.74 MB for a 16-32 px glyph.

This script derives correctly sized icons from that same master so the artwork,
crop, proportions and transparency are byte-for-byte the same design, only
resampled. It deliberately does NOT re-crop: the master's transparent padding is
part of how the mark sits inside a rounded app-icon tile.

Run from `frontend/`:

    python scripts/generate_app_icons.py

It is a build-time asset tool, not a runtime dependency — Pillow is not, and
must not become, a package.json dependency.
"""

from pathlib import Path

from PIL import Image


PUBLIC_DIR = Path(__file__).resolve().parents[1] / "public"
MASTER = PUBLIC_DIR / "inDex.png"

# Only the sizes something actually references. Every extra file here is another
# asset a browser might speculatively fetch for no benefit.
PNG_TARGETS = {
    "favicon-16x16.png": 16,
    "favicon-32x32.png": 32,
    "apple-touch-icon.png": 180,
    "icon-192.png": 192,
    "icon-512.png": 512,
}

# Multi-resolution .ico so legacy browsers and the Windows taskbar each pick
# their own size out of one small file.
ICO_SIZES = [(16, 16), (32, 32), (48, 48)]


def load_master() -> Image.Image:
    with Image.open(MASTER) as image:
        image.load()
        return image.convert("RGBA")


def resize(master: Image.Image, size: int) -> Image.Image:
    # LANCZOS on the straight RGBA master. The mark is drawn on full
    # transparency with no matte, so there is no dark-fringe risk that would
    # require premultiplying first.
    return master.resize((size, size), Image.LANCZOS)


def main() -> None:
    master = load_master()
    if master.size[0] != master.size[1]:
        raise SystemExit(f"expected a square master, got {master.size}")

    for name, size in PNG_TARGETS.items():
        destination = PUBLIC_DIR / name
        resize(master, size).save(destination, "PNG", optimize=True)
        print(f"{name}: {size}x{size}, {destination.stat().st_size} bytes")

    ico = PUBLIC_DIR / "favicon.ico"
    resize(master, ICO_SIZES[-1][0]).save(ico, "ICO", sizes=ICO_SIZES)
    print(f"favicon.ico: {ICO_SIZES}, {ico.stat().st_size} bytes")


if __name__ == "__main__":
    main()
