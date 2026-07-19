"""Generate the Perimeter app icon (icon.icns + icon.png).

Design: dark zinc squircle, four white corner brackets marking the zone
perimeter, a green tap dot in the center with a soft ripple ring.

Run:  .venv/bin/python3 assets/make_icon.py
"""

import subprocess
import tempfile
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter

HERE = Path(__file__).resolve().parent
S = 1024  # master size

BG_TOP = (32, 32, 36)
BG_BOTTOM = (14, 14, 16)
WHITE = (250, 250, 250, 255)
GREEN = (74, 222, 128, 255)


def rounded_mask(size: int, radius: int) -> Image.Image:
    m = Image.new("L", (size, size), 0)
    d = ImageDraw.Draw(m)
    d.rounded_rectangle([0, 0, size - 1, size - 1], radius=radius, fill=255)
    return m


def build_master() -> Image.Image:
    img = Image.new("RGBA", (S, S), (0, 0, 0, 0))

    # macOS icon grid: content squircle inset ~10% on each side
    inset = int(S * 0.10)
    box = S - 2 * inset
    radius = int(box * 0.225)

    # vertical gradient background
    bg = Image.new("RGBA", (box, box))
    for yy in range(box):
        t = yy / box
        c = tuple(int(a + (b - a) * t) for a, b in zip(BG_TOP, BG_BOTTOM))
        ImageDraw.Draw(bg).line([(0, yy), (box, yy)], fill=c + (255,))
    bg.putalpha(rounded_mask(box, radius))
    img.paste(bg, (inset, inset), bg)

    d = ImageDraw.Draw(img)

    # four corner brackets (the "perimeter")
    b_inset = inset + int(box * 0.21)          # bracket square inset
    arm = int(box * 0.16)                      # bracket arm length
    w = int(box * 0.052)                       # stroke width
    r = w // 2
    x0, y0 = b_inset, b_inset
    x1, y1 = S - b_inset, S - b_inset

    def stroke(a, b):
        d.line([a, b], fill=WHITE, width=w)
        for p in (a, b):  # rounded caps
            d.ellipse([p[0] - r, p[1] - r, p[0] + r, p[1] + r], fill=WHITE)

    stroke((x0, y0), (x0 + arm, y0)); stroke((x0, y0), (x0, y0 + arm))
    stroke((x1, y0), (x1 - arm, y0)); stroke((x1, y0), (x1, y0 + arm))
    stroke((x0, y1), (x0 + arm, y1)); stroke((x0, y1), (x0, y1 - arm))
    stroke((x1, y1), (x1 - arm, y1)); stroke((x1, y1), (x1, y1 - arm))

    # ripple ring (soft) around the tap dot
    cx = cy = S // 2
    ring = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    rr = int(box * 0.155)
    ImageDraw.Draw(ring).ellipse(
        [cx - rr, cy - rr, cx + rr, cy + rr],
        outline=GREEN[:3] + (110,), width=int(box * 0.024))
    ring = ring.filter(ImageFilter.GaussianBlur(int(box * 0.012)))
    img.alpha_composite(ring)

    # tap dot
    dot = int(box * 0.085)
    d.ellipse([cx - dot, cy - dot, cx + dot, cy + dot], fill=GREEN)

    return img


def main():
    master = build_master()
    master.save(HERE / "icon.png")

    with tempfile.TemporaryDirectory() as td:
        iconset = Path(td) / "icon.iconset"
        iconset.mkdir()
        for pt in (16, 32, 128, 256, 512):
            for scale in (1, 2):
                px = pt * scale
                name = f"icon_{pt}x{pt}" + ("@2x" if scale == 2 else "") + ".png"
                master.resize((px, px), Image.LANCZOS).save(iconset / name)
        subprocess.run(
            ["iconutil", "-c", "icns", str(iconset), "-o", str(HERE / "icon.icns")],
            check=True)
    print("wrote", HERE / "icon.png", "and", HERE / "icon.icns")


if __name__ == "__main__":
    main()
