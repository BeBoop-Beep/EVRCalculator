#!/usr/bin/env python3
"""Batch-remove backgrounds from pack artwork with validation and reporting."""

from __future__ import annotations

import argparse
import json
import math
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from PIL import Image, ImageDraw, ImageFont

SUPPORTED_EXTENSIONS = {".webp", ".png", ".jpg", ".jpeg"}
MIN_FOREGROUND_RATIO = 0.01
MIN_BOUNDING_BOX_RATIO = 0.01


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True, type=Path, help="Directory to scan recursively")
    parser.add_argument("--output", required=True, type=Path, help="Staging/output directory")
    parser.add_argument("--force", action="store_true", help="Overwrite existing outputs")
    parser.add_argument("--dry-run", action="store_true", help="Audit without loading rembg or writing images")
    parser.add_argument("--report", type=Path, help="JSON report path (default: <output>/pack-background-removal-report.json)")
    parser.add_argument("--preview", type=Path, help="Optional dark/light QA contact-sheet path")
    parser.add_argument("--model", default="u2net", help="rembg model name (default: u2net)")
    parser.add_argument(
        "--extensions",
        nargs="+",
        choices=sorted(SUPPORTED_EXTENSIONS),
        default=sorted(SUPPORTED_EXTENSIONS),
        help="Source extensions to include (default: all supported extensions)",
    )
    return parser.parse_args()


def destination_for(source: Path, input_root: Path, output_root: Path) -> Path:
    relative = source.relative_to(input_root)
    # WebP and PNG can carry alpha. JPEG inputs become transparent PNGs.
    return output_root / (relative if source.suffix.lower() in {".webp", ".png"} else relative.with_suffix(".png"))


def validate_output(source: Path, output: Path) -> dict[str, Any]:
    with Image.open(source) as source_image:
        source_size = source_image.size
    with Image.open(output) as image:
        image.load()  # Decode fully so truncated/corrupt outputs fail here.
        rgba = image.convert("RGBA")
        alpha = rgba.getchannel("A")
        width, height = rgba.size
        extrema = alpha.getextrema()
        bbox = alpha.getbbox()
        histogram = alpha.histogram()

    pixels = width * height
    transparent_pixels = sum(histogram[:-1])
    foreground_pixels = pixels - histogram[0]
    bbox_area = 0 if bbox is None else (bbox[2] - bbox[0]) * (bbox[3] - bbox[1])
    problems: list[str] = []
    if (width, height) != source_size:
        problems.append(f"dimensions changed from {source_size} to {(width, height)}")
    if extrema[0] == 255:
        problems.append("output contains no transparent pixels")
    if extrema[1] == 0 or bbox is None:
        problems.append("output is entirely transparent")
    if foreground_pixels / pixels < MIN_FOREGROUND_RATIO:
        problems.append("foreground contains less than 1% of the canvas")
    if bbox_area / pixels < MIN_BOUNDING_BOX_RATIO:
        problems.append("foreground bounding box contains less than 1% of the canvas")

    return {
        "dimensions": [width, height],
        "source_bytes": source.stat().st_size,
        "output_bytes": output.stat().st_size,
        "transparent_pixel_percentage": round(transparent_pixels * 100 / pixels, 4),
        "foreground_pixel_percentage": round(foreground_pixels * 100 / pixels, 4),
        "foreground_bounding_box": list(bbox) if bbox else None,
        "alpha_extrema": list(extrema),
        "validation_errors": problems,
    }


def save_removed_image(image: Image.Image, output: Path) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.with_name(f".{output.stem}.processing{output.suffix}")
    rgba = image.convert("RGBA")
    try:
        if output.suffix.lower() == ".webp":
            rgba.save(temporary, "WEBP", lossless=True, method=6, exact=True)
        else:
            rgba.save(temporary, "PNG", optimize=True)
        temporary.replace(output)
    finally:
        temporary.unlink(missing_ok=True)


def make_contact_sheet(successes: list[dict[str, Any]], preview_path: Path) -> None:
    if not successes:
        return
    tile_w, tile_h, label_h = 260, 210, 28
    columns = min(4, len(successes))
    rows = math.ceil(len(successes) / columns)
    sheet = Image.new("RGB", (columns * tile_w * 2, rows * (tile_h + label_h)), "#111827")
    draw = ImageDraw.Draw(sheet)
    font = ImageFont.load_default()
    for index, item in enumerate(successes):
        row, column = divmod(index, columns)
        with Image.open(item["output_path"]) as source:
            pack = source.convert("RGBA")
            pack.thumbnail((tile_w - 24, tile_h - 20), Image.Resampling.LANCZOS)
        for variant in range(2):
            left = (column * 2 + variant) * tile_w
            top = row * (tile_h + label_h)
            if variant == 0:
                background = Image.new("RGBA", (tile_w, tile_h), "#111827")
            else:
                background = Image.new("RGBA", (tile_w, tile_h), "white")
                checker = ImageDraw.Draw(background)
                for y in range(0, tile_h, 16):
                    for x in range(0, tile_w, 16):
                        if (x // 16 + y // 16) % 2:
                            checker.rectangle((x, y, x + 15, y + 15), fill="#d1d5db")
            x = (tile_w - pack.width) // 2
            y = (tile_h - pack.height) // 2
            background.alpha_composite(pack, (x, y))
            sheet.paste(background.convert("RGB"), (left, top))
        draw.text((column * tile_w * 2 + 6, row * (tile_h + label_h) + tile_h + 7), Path(item["source_path"]).name, fill="white", font=font)
    preview_path.parent.mkdir(parents=True, exist_ok=True)
    sheet.save(preview_path, "PNG", optimize=True)


def main() -> int:
    args = parse_args()
    input_root = args.input.resolve()
    output_root = args.output.resolve()
    report_path = (args.report or output_root / "pack-background-removal-report.json").resolve()
    if not input_root.is_dir():
        print(f"ERROR: input directory does not exist: {input_root}", file=sys.stderr)
        return 2
    if input_root == output_root or input_root in output_root.parents:
        print("ERROR: output must not be the input directory or nested inside it", file=sys.stderr)
        return 2

    selected_extensions = set(args.extensions)
    sources = sorted(path for path in input_root.rglob("*") if path.is_file() and path.suffix.lower() in selected_extensions)
    print(f"Total files found: {len(sources)}")
    print("Extension breakdown: " + ", ".join(f"{ext}: {count}" for ext, count in sorted(Counter(p.suffix.lower() for p in sources).items())))
    records: list[dict[str, Any]] = []
    session = None
    remove = None
    if not args.dry_run and sources:
        from rembg import new_session, remove as rembg_remove

        session = new_session(args.model)
        remove = rembg_remove

    for source in sources:
        output = destination_for(source, input_root, output_root)
        record: dict[str, Any] = {"source_path": str(source), "output_path": str(output)}
        try:
            if output.exists() and not args.force:
                record.update(status="SKIPPED", reason="output already exists")
            elif args.dry_run:
                record.update(status="DRY_RUN")
            else:
                with Image.open(source) as opened:
                    source_image = opened.convert("RGBA")
                    # Camera EXIF can claim a rotation that is already baked into
                    # the pixels. rembg honors that tag, which would swap the
                    # canonical canvas dimensions, so inference receives pixels
                    # without inherited metadata.
                    source_image.info.pop("exif", None)
                result = remove(source_image, session=session, post_process_mask=True)
                save_removed_image(result, output)
                record.update(validate_output(source, output))
                if record["validation_errors"]:
                    output.unlink(missing_ok=True)
                    record.update(status="FAILED_REVIEW", reason="; ".join(record["validation_errors"]))
                else:
                    record.update(status="PROCESSED")
        except Exception as exc:  # Continue the batch while retaining an actionable error.
            output.unlink(missing_ok=True)
            record.update(status="FAILED", reason=f"{type(exc).__name__}: {exc}")
        records.append(record)
        print(f"[{record['status']}] {source.relative_to(input_root)}")

    counts = Counter(record["status"] for record in records)
    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "input_root": str(input_root),
        "output_root": str(output_root),
        "model": args.model,
        "dry_run": args.dry_run,
        "total_files_found": len(sources),
        "files_processed": counts["PROCESSED"],
        "files_skipped": counts["SKIPPED"],
        "files_failed": counts["FAILED"] + counts["FAILED_REVIEW"],
        "results": records,
    }
    if not args.dry_run:
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
        if args.preview:
            make_contact_sheet([record for record in records if record["status"] == "PROCESSED"], args.preview.resolve())
    print(f"Files processed: {report['files_processed']}")
    print(f"Files skipped: {report['files_skipped']}")
    print(f"Files failed: {report['files_failed']}")
    if not args.dry_run:
        print(f"Report: {report_path}")
    return 1 if report["files_failed"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
