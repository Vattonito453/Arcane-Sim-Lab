"""Export the six mana pips from the source artwork to 96px WebP.

Asset build tooling, NOT part of the engine. It needs Pillow + numpy, which is
why it lives here and not in `engine/` (which is stdlib-only by design).

    python3 -m venv .venv && .venv/bin/pip install pillow numpy
    .venv/bin/python "Design System/tools/export_pips.py" \
        --src <dir-of-source-pngs> --out web/public/art/pips

The source PNGs ("White Mana Pip.png" etc.) are the commissioned 1536x1024
originals and are not committed; point --src at wherever they live.

Pipeline, per pip:
  1. keep the source alpha (the art is ~70% transparent and carries junk RGB in
     those pixels; dropping it bakes in a grey plate, which was the original bug)
  2. crop square to the true content bounds, so the medallion's spikes and wing
     flourishes survive instead of being clipped by a circular mask
  3. optional per-colour grade (black needs its shadows lifted or the skull
     disappears below ~20px)
  4. premultiply -> Lanczos -> un-premultiply, so no colour bleeds out of
     fully transparent pixels during downscale
"""
import argparse
import os

import numpy as np
from PIL import Image

import white_sun

SIZE = 96

# gamma <1 lifts buried shadow detail, gain re-expands contrast around mid,
# lift keeps the deepest blacks from turning muddy grey. "strong" for black.
GRADE = {
    "b": (0.50, 1.45, 0.020),
}

FILES = {
    "w": "White Mana Pip.png",
    "u": "Blue Mana Pip.png",
    "b": "Black Mana Pip.png",
    "r": "Red Mana Pip.png",
    "g": "Green Mana Pip.png",
    "c": "Colorless Mana Pip.png",
}


def square(im):
    a = np.array(im)[:, :, 3]
    ys, xs = np.where(a > 24)
    cx, cy = (xs.min() + xs.max()) / 2, (ys.min() + ys.max()) / 2
    half = max(xs.max() - xs.min(), ys.max() - ys.min()) / 2 + 6
    return im.crop((max(int(cx - half), 0), max(int(cy - half), 0),
                    min(int(cx + half), im.width), min(int(cy + half), im.height)))


def grade(rgb, gamma, gain, lift):
    x = np.clip(rgb, 0, 1) ** gamma
    return np.clip((x - 0.5) * gain + 0.5 + lift, 0, 1)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--src", required=True, help="directory holding the source PNGs")
    ap.add_argument("--out", required=True, help="output directory for the WebP set")
    args = ap.parse_args()

    src, out = args.src, args.out
    os.makedirs(out, exist_ok=True)
    white_sun.SRC = os.path.join(src, FILES["w"])
    for key, fname in FILES.items():
        if key == "w":
            # white's teardrop is swapped for a sun (12 fine rays)
            im = white_sun.build(sun_rays=12, ray_w=0.115, ray_len=0.80,
                                 core=0.30, field_depth=0.80)
        else:
            im = square(Image.open(os.path.join(src, fname)).convert("RGBA"))

        a = np.array(im).astype(np.float32) / 255.0
        if key in GRADE:
            a[:, :, :3] = grade(a[:, :, :3], *GRADE[key])

        al = a[:, :, 3:4]
        pre = np.concatenate([a[:, :, :3] * al, al], axis=2)
        p = Image.fromarray((pre * 255).round().astype(np.uint8), "RGBA") \
                 .resize((SIZE, SIZE), Image.LANCZOS)
        q = np.array(p).astype(np.float32) / 255.0
        qa = q[:, :, 3:4]
        rgb = np.where(qa > 1e-4, q[:, :, :3] / np.maximum(qa, 1e-4), 0.0)
        final = np.dstack([np.clip(rgb, 0, 1), qa])
        path = os.path.join(out, f"pip-{key}.webp")
        Image.fromarray((final * 255).round().astype(np.uint8), "RGBA") \
             .save(path, quality=95, method=6)
        print(f"{path}  {os.path.getsize(path)} bytes")


if __name__ == "__main__":
    main()
