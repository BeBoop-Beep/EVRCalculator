import assert from "node:assert/strict";
import { execFileSync } from "node:child_process";
import { readdirSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import test from "node:test";

const root = join(dirname(fileURLToPath(import.meta.url)), "../../public/images/pokemon/booster-packs");

test("every booster JPEG has a valid EXIF-normalized upright portrait WebP output", () => {
  const script = String.raw`
from pathlib import Path
from PIL import Image, ImageOps
root=Path(r"${root}")
for src in root.iterdir():
    if src.suffix.lower() not in ('.jpg','.jpeg'): continue
    out=src.with_suffix('.webp')
    assert out.exists(), out
    with Image.open(src) as a, Image.open(out) as b:
        b.load()
        assert b.format == 'WEBP', out
        expected = ImageOps.exif_transpose(a).size
        assert b.size == expected, (src, a.size, b.size, expected)
        assert b.height > b.width, (out, b.size)
        assert 'A' in b.mode, (out, b.mode)
        alpha = b.getchannel('A')
        assert alpha.getextrema()[0] < 255, (out, alpha.getextrema())
        bbox = alpha.getbbox()
        assert bbox and (bbox[3] - bbox[1]) > (bbox[2] - bbox[0]), (out, bbox)
`;
  execFileSync("python", ["-c", script]);
  assert.equal(readdirSync(root).filter((name) => /\.webp$/i.test(name)).length, 19);
});
