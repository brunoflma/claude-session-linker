"""Generate Claude Session Linker icon assets -- rounded tile + chain-link glyph.

Same technique as Claude Profiles' _gen_icon.py: each .ico frame is rendered
separately at high supersampling then downsampled with LANCZOS, so small
taskbar frames stay sharp. Single dominant glyph (two interlocked rings)
survives 16-32px downscaling far better than fine detail would.

Geometry mirrors the Claude-coral gradient tile used across the sibling
tools (Claude Profiles, Cowork VM Manager) for a consistent icon family.
"""
import os
from PIL import Image, ImageDraw

HERE = os.path.dirname(os.path.abspath(__file__))
PNG = os.path.join(HERE, "icon.png")
ICO = os.path.join(HERE, "icon.ico")

TILE_X, TILE_Y, TILE_W, TILE_H, TILE_R = 8, 8, 240, 240, 54
TOP = (245, 118, 62)     # #F5763E
BOT = (196, 58, 26)      # #C43A1A
WHITE = (255, 255, 255, 255)
GHOST = (255, 255, 255, 110)

SS = 4  # supersampling factor


def _gradient(size):
    img = Image.new("RGB", (size, size))
    px = img.load()
    for y in range(size):
        t = y / max(1, size - 1)
        row = (
            round(TOP[0] + (BOT[0] - TOP[0]) * t),
            round(TOP[1] + (BOT[1] - TOP[1]) * t),
            round(TOP[2] + (BOT[2] - TOP[2]) * t),
        )
        for x in range(size):
            px[x, y] = row
    return img


def _rounded_mask(size, box, radius):
    mask = Image.new("L", (size, size), 0)
    d = ImageDraw.Draw(mask)
    d.rounded_rectangle(box, radius=radius, fill=255)
    return mask


def _ring_mask(size, cx, cy, r_outer, r_inner):
    mask = Image.new("L", (size, size), 0)
    d = ImageDraw.Draw(mask)
    d.ellipse((cx - r_outer, cy - r_outer, cx + r_outer, cy + r_outer), fill=255)
    d.ellipse((cx - r_inner, cy - r_inner, cx + r_inner, cy + r_inner), fill=0)
    return mask


def render(size, small=False):
    ss = size * SS
    scale = ss / 256

    tile = _gradient(ss)
    tile_mask = _rounded_mask(
        ss,
        (TILE_X * scale, TILE_Y * scale, (TILE_X + TILE_W) * scale, (TILE_Y + TILE_H) * scale),
        TILE_R * scale,
    )
    canvas = Image.new("RGBA", (ss, ss), (0, 0, 0, 0))
    canvas.paste(tile, (0, 0), tile_mask)

    glyph = Image.new("RGBA", (ss, ss), (0, 0, 0, 0))

    if small:
        # <=32px: a single bold ring pair, thick strokes, high contrast.
        r_out, r_in = 58 * scale, 30 * scale
        cx1, cy1 = 100 * scale, 128 * scale
        cx2, cy2 = 156 * scale, 128 * scale
        ring1 = _ring_mask(ss, cx1, cy1, r_out, r_in)
        ring2 = _ring_mask(ss, cx2, cy2, r_out, r_in)
        white = Image.new("RGBA", (ss, ss), WHITE)
        glyph.paste(white, (0, 0), ring1)
        glyph.paste(white, (0, 0), ring2)
    else:
        # Larger sizes: two interlocked chain links (front link solid white,
        # back link translucent) -- reads clearly as "linking two things".
        r_out, r_in = 46 * scale, 26 * scale
        cx1, cy1 = 96 * scale, 116 * scale
        cx2, cy2 = 152 * scale, 148 * scale

        ghost = Image.new("RGBA", (ss, ss), GHOST)
        ring_back = _ring_mask(ss, cx1, cy1, r_out, r_in)
        glyph.paste(ghost, (0, 0), ring_back)

        white = Image.new("RGBA", (ss, ss), WHITE)
        ring_front = _ring_mask(ss, cx2, cy2, r_out, r_in)
        glyph.paste(white, (0, 0), ring_front)

    canvas = Image.alpha_composite(canvas, glyph)
    return canvas.resize((size, size), Image.LANCZOS)


def main():
    master = render(512, small=False)
    master.save(PNG)

    ico_sizes = [16, 24, 32, 48, 64, 128, 256]
    frames = []
    for sz in ico_sizes:
        frames.append(render(sz, small=(sz <= 32)))
    frames[0].save(ICO, format="ICO", sizes=[(f.width, f.height) for f in frames], append_images=frames[1:])
    print(f"Wrote {PNG} and {ICO}")


if __name__ == "__main__":
    main()
