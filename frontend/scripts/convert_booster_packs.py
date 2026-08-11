"""One-time, idempotent JPEG -> WebP conversion for local booster-pack assets."""

from pathlib import Path

from PIL import Image


ASSET_DIR = Path(__file__).resolve().parents[1] / "public" / "images" / "pokemon" / "booster-packs"


def convert(source: Path) -> Path:
    destination = source.with_suffix(".webp")
    with Image.open(source) as image:
        image.load()
        size = image.size
        image.save(destination, "WEBP", quality=92, method=6, exif=image.getexif().tobytes())
    with Image.open(destination) as verified:
        verified.load()
        if verified.format != "WEBP" or verified.size != size:
            destination.unlink(missing_ok=True)
            raise RuntimeError(f"verification failed: {source.name}")
    return destination


if __name__ == "__main__":
    sources = sorted(
        path for path in ASSET_DIR.iterdir()
        if path.is_file() and path.suffix.lower() in {".jpg", ".jpeg"}
    )
    for source in sources:
        output = convert(source)
        print(f"{source.name} -> {output.name}")
