# Pack background-removal utility

This local utility recursively removes backgrounds from booster-pack artwork with
`rembg`, preserves source-relative folders, and validates every generated file.
WebP inputs remain lossless transparent WebP files with the same name and canvas
dimensions. PNG inputs remain PNG; JPEG inputs become PNG because JPEG cannot
store transparency. The pipeline applies EXIF normalization before segmentation,
then enforces a portrait canvas and portrait alpha-foreground bounding box.

## Install

From the repository root, install the isolated utility requirements into the
existing environment:

```powershell
.\.venv\Scripts\python.exe -m pip install -r backend\scripts\assets\requirements.txt
```

The first real run downloads the selected `rembg` model to the user's local
model cache.

## Usage

Audit what would be processed without loading the model or writing files:

```powershell
.\.venv\Scripts\python.exe backend\scripts\assets\remove_pack_backgrounds.py `
  --input frontend\public\images\pokemon\booster-packs `
  --output tmp\pack-background-removal `
  --dry-run
```

Run the batch and create an optional QA contact sheet:

```powershell
.\.venv\Scripts\python.exe backend\scripts\assets\remove_pack_backgrounds.py `
  --input frontend\public\images\pokemon\booster-packs `
  --output tmp\pack-background-removal `
  --extensions .jpg `
  --output-format webp `
  --preview tmp\pack-background-removal-preview.png
```

Existing outputs are skipped. Add `--force` to regenerate them. A JSON report is
written to the output directory by default; use `--report PATH` to place it
elsewhere. Processing errors and validation failures are recorded while the
remaining files continue. Use `--extensions .webp` when a directory also holds
archival JPEG sources that are not part of the frontend asset contract.
Use `--output-format webp` to regenerate canonical transparent WebPs directly
from pristine JPEG sources. If a landscape image remains after EXIF
normalization, the whole canvas is rotated clockwise by default; use
`--landscape-rotation counterclockwise` only after verifying the source family.

Automatic semantic segmentation can still produce halos or remove dark,
reflective, transparent, or crimped packaging details. Review the contact sheet
before replacing production assets; failed validation outputs are deleted and
never overwrite their source files.
