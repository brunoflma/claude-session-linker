"""Generate Claude Session Linker icon assets: terracotta tile + two linked
conversation bubbles (one per account).

Each .ico frame is rendered separately with supersampling and LANCZOS, so the
16-32 px taskbar frames stay sharp; those small frames drop the inner link
glyph and thicken the shapes. The tile color matches the app's ACCENT.

Run from the repository root:  python .app/_gen_icon.py
"""
import os
from PIL import Image, ImageDraw

HERE = os.path.dirname(os.path.abspath(__file__))
PNG = os.path.join(HERE, "icon.png")
ICO = os.path.join(HERE, "icon.ico")
ICO_SIZES = (16, 20, 24, 32, 40, 48, 64, 128, 256)

TOP = (221, 124, 84)      # #DD7C54
BOT = (166, 72, 41)       # #A64829 (≈ app ACCENT_H)
ACCENT = (193, 95, 60)    # #C15F3C, link glyph on the front bubble
WHITE = (255, 255, 255, 255)
GHOST = (255, 255, 255, 120)
SS = 4  # supersampling factor


def _gradient(size):
    # Diagonal gradient (top-left light -> bottom-right dark).
    img = Image.new("RGB", (size, size))
    px = img.load()
    span = max(1, 2 * (size - 1))
    for y in range(size):
        for x in range(size):
            t = (x + y) / span
            px[x, y] = tuple(round(TOP[i] + (BOT[i] - TOP[i]) * t) for i in range(3))
    return img


def _bubble(draw, box, radius, tail, fill):
    x1, y1, x2, y2 = box
    draw.rounded_rectangle(box, radius=radius, fill=fill)
    h = (y2 - y1) * 0.30
    if tail == "left":
        draw.polygon([(x1 + radius * 0.6, y2 - 2), (x1 + radius * 0.6 + h, y2 - 2), (x1 + radius * 0.35, y2 + h * 0.75)], fill=fill)
    else:
        draw.polygon([(x2 - radius * 0.6, y2 - 2), (x2 - radius * 0.6 - h, y2 - 2), (x2 - radius * 0.35, y2 + h * 0.75)], fill=fill)


def _ring(draw, cx, cy, r_out, width, fill):
    draw.ellipse((cx - r_out, cy - r_out, cx + r_out, cy + r_out), outline=fill, width=max(1, round(width)))


def render(size):
    small = size <= 32
    ss = size * SS
    k = ss / 256

    canvas = Image.new("RGBA", (ss, ss), (0, 0, 0, 0))
    margin = (10 if small else 12) * k
    mask = Image.new("L", (ss, ss), 0)
    ImageDraw.Draw(mask).rounded_rectangle(
        (margin, margin, ss - margin, ss - margin), radius=(52 if small else 56) * k, fill=255,
    )
    canvas.paste(_gradient(ss), (0, 0), mask)

    back = Image.new("RGBA", (ss, ss), (0, 0, 0, 0))
    front = Image.new("RGBA", (ss, ss), (0, 0, 0, 0))
    if small:
        _bubble(ImageDraw.Draw(back), (40 * k, 50 * k, 150 * k, 140 * k), 26 * k, "left", GHOST)
        _bubble(ImageDraw.Draw(front), (100 * k, 104 * k, 216 * k, 196 * k), 28 * k, "right", WHITE)
    else:
        _bubble(ImageDraw.Draw(back), (48 * k, 56 * k, 152 * k, 140 * k), 24 * k, "left", GHOST)
        d = ImageDraw.Draw(front)
        _bubble(d, (100 * k, 108 * k, 208 * k, 192 * k), 26 * k, "right", WHITE)
        # Two interlocked rings on the front bubble: "these are linked".
        cy = 150 * k
        _ring(d, 138 * k, cy, 17 * k, 7 * k, ACCENT + (255,))
        _ring(d, 170 * k, cy, 17 * k, 7 * k, ACCENT + (255,))
    canvas = Image.alpha_composite(canvas, back)
    canvas = Image.alpha_composite(canvas, front)
    return canvas.resize((size, size), Image.LANCZOS)


def main():
    render(512).save(PNG)
    frames = [render(sz) for sz in ICO_SIZES]
    # Pillow writes every size listed in `sizes`, taking each frame from
    # append_images; the base image must be the largest, otherwise larger
    # sizes are silently dropped (the old generator shipped only 16x16).
    frames[-1].save(
        ICO, format="ICO", sizes=[(f.width, f.height) for f in frames],
        append_images=frames[:-1],
    )
    print(f"Wrote {PNG} and {ICO} ({', '.join(str(s) for s in ICO_SIZES)} px)")


if __name__ == "__main__":
    main()
