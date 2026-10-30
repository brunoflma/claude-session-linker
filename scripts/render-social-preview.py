"""Render the 1280x640 share image in the app's visual identity.

Uses the site's Manrope (docs/assets/fonts/manrope.woff2) unless --font is
given, and the app icon from .app/icon.png. Everything shown is fictional.
"""
import argparse
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[1]
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--font', type=Path, default=ROOT / 'docs/assets/fonts/manrope.woff2')
args = parser.parse_args()

PAPER, CARD, LINE, LINE2 = '#f5f2ec', '#ffffff', '#e4ddd1', '#d4cbbc'
INK, INK2, INK3 = '#1e1f22', '#57534c', '#8a8378'
ACCENT, ACCENT_SOFT = '#c15f3c', '#f8e9e2'
RAIL, RAIL2, RAIL3, RAIL_TXT, RAIL_TXT3, LIVE = '#16181c', '#1f2228', '#2a2e36', '#f3efe8', '#7f8790', '#5fbf7f'
INFO, INFO_BG, WARN, WARN_BG = '#2b5d84', '#e5eef6', '#8a5508', '#fcf1dc'

S = 2  # supersampling
image = Image.new('RGB', (1280 * S, 640 * S), PAPER)
draw = ImageDraw.Draw(image)


def box(bounds, fill, outline=None, radius=0):
    draw.rounded_rectangle(tuple(int(v * S) for v in bounds), radius=radius * S, fill=fill, outline=outline, width=S)


def text(x, y, value, size, color, weight=600):
    font = ImageFont.truetype(str(args.font), size * S)
    font.set_variation_by_axes([weight])
    draw.text((x * S, y * S), value, fill=color, font=font)


# Left: brand and message
icon = Image.open(ROOT / '.app/icon.png').convert('RGBA').resize((64 * S, 64 * S), Image.Resampling.LANCZOS)
image.paste(icon, (64 * S, 62 * S), icon)
text(142, 70, 'Claude Session Linker', 27, INK, 800)
text(143, 106, 'PARA CLAUDE DESKTOP', 12, INK3, 700)
text(64, 196, 'Sua conversa.', 66, INK, 800)
text(64, 276, 'Continua daqui.', 66, ACCENT, 800)
text(67, 384, 'Encontre, vincule e compare sessões', 24, INK2, 500)
text(67, 418, 'entre contas no mesmo computador.', 24, INK2, 500)
box((66, 486, 270, 524), ACCENT_SOFT, radius=9)
text(84, 494, 'CODE  ·  COWORK', 15, ACCENT, 800)
box((282, 486, 506, 524), CARD, LINE2, 9)
text(300, 494, 'WINDOWS  ·  macOS', 15, INK2, 800)
text(67, 566, 'Projeto independente · backups antes de alterar sessões', 14, INK3, 600)

# Right: replica of the app window (fictional data)
X, Y, W, H = 700, 72, 520, 496
box((X, Y + 10, X + W, Y + H + 10), '#e7e0d4', radius=18)  # soft shadow
box((X, Y, X + W, Y + H), CARD, LINE2, 16)
box((X + 1, Y + 1, X + W - 1, Y + 40), '#ebe5db', radius=15)
draw.rectangle(((X + 1) * S, (Y + 24) * S, (X + W - 1) * S, (Y + 40) * S), fill='#ebe5db')
for i, color in enumerate(('#e2735f', '#e4b54f', '#6cbd76')):
    cx = X + 22 + i * 18
    draw.ellipse(((cx - 6) * S, (Y + 14) * S, (cx + 6) * S, (Y + 26) * S), fill=color)
text(X + 196, Y + 11, 'Claude Session Linker', 13, INK3, 650)
# rail
rail = (X + 1, Y + 41, X + 170, Y + H - 1)
draw.rectangle(tuple(int(v * S) for v in rail), fill=RAIL)
small_icon = icon.resize((26 * S, 26 * S), Image.Resampling.LANCZOS)
image.paste(small_icon, ((X + 16) * S, (Y + 58) * S), small_icon)
text(X + 50, Y + 58, 'Session Linker', 13, RAIL_TXT, 800)
text(X + 50, Y + 75, 'Sessões entre contas', 9, RAIL_TXT3, 500)
box((X + 14, Y + 102, X + 156, Y + 130), RAIL2, radius=7)
box((X + 17, Y + 105, X + 85, Y + 127), ACCENT, radius=5)
text(X + 36, Y + 108, 'Code', 11, '#ffffff', 800)
text(X + 98, Y + 108, 'Cowork', 11, '#b4aea4', 700)
text(X + 18, Y + 148, 'CONTAS', 9, RAIL_TXT3, 800)
# Manrope (subset) has no ≡/●/→ glyphs, so those marks are drawn as shapes.
accounts = [('', RAIL2, 'Todas as contas', '5 sessões', RAIL_TXT3, True),
            ('TR', '#4e9a6b', 'Trabalho', 'ativa · 3 sessões', LIVE, False),
            ('PE', '#3e7cb1', 'Pessoal', '2 sessões', RAIL_TXT3, False)]
for i, (initials, color, name, meta, meta_color, selected) in enumerate(accounts):
    ay = Y + 168 + i * 50
    if selected:
        box((X + 10, ay - 4, X + 160, ay + 40), RAIL3, radius=8)
    box((X + 16, ay + 3, X + 44, ay + 31), color, radius=7)
    if initials:
        text(X + 21, ay + 8, initials, 11, '#ffffff', 800)
    else:
        for k in range(3):
            draw.rounded_rectangle(((X + 24) * S, (ay + 11 + k * 5) * S, (X + 36) * S, (ay + 13 + k * 5) * S), radius=S, fill=RAIL_TXT)
    text(X + 52, ay + 2, name, 12, RAIL_TXT, 750)
    meta_x = X + 52
    if meta_color == LIVE:
        draw.ellipse(((X + 52) * S, (ay + 24) * S, (X + 58) * S, (ay + 30) * S), fill=LIVE)
        meta_x += 10
    text(meta_x, ay + 20, meta, 9, meta_color, 600)
# workspace
MX = X + 186
draw.rectangle(((X + 170) * S, (Y + 41) * S, (X + W - 2) * S, (Y + H - 14) * S), fill=PAPER)
text(MX, Y + 58, 'Sessões do Code', 20, INK, 800)
text(MX, Y + 86, '5 sessões · 2 contas', 11, INK2, 500)
box((MX, Y + 110, X + W - 18, Y + 138), CARD, LINE2, 7)
text(MX + 12, Y + 116, 'Buscar por título, pasta, conta ou ID', 11, INK3, 500)
cards = [('Roteiro de pesquisa', 'Trabalho · pesquisa · há 2 h', ('Também em: Pessoal', INFO, INFO_BG)),
         ('Plano do site', 'Pessoal · site · ontem', ('Possível duplicata · comparar', WARN, WARN_BG)),
         ('Notas da reunião', 'Trabalho · notas · há 3 dias', None)]
cy = Y + 152
for title, meta, chip in cards:
    h = 92 if chip else 66
    box((MX, cy, X + W - 18, cy + h), CARD, LINE, 9)
    text(MX + 14, cy + 12, title, 13, INK, 800)
    text(MX + 14, cy + 34, meta, 10, INK2, 500)
    if chip:
        label, fg, bg = chip
        box((MX + 14, cy + 58, MX + 22 + len(label) * 6.4, cy + 78), bg, radius=5)
        text(MX + 20, cy + 61, label, 10, fg, 700)
    box((X + W - 92, cy + 12, X + W - 30, cy + 36), ACCENT, radius=6)
    text(X + W - 83, cy + 16, 'Vincular', 11, '#ffffff', 800)
    cy += h + 10
text(MX + 52, Y + H - 36, 'COMPOSIÇÃO ILUSTRATIVA · SEM DADOS REAIS', 9, INK3, 800)
# Re-draw the frame so the rail and workspace sit inside the rounded border.
box((X, Y, X + W, Y + H), None, LINE2, 16)

destination = ROOT / 'docs/assets/social-preview.png'
image.resize((1280, 640), Image.Resampling.LANCZOS).save(destination, optimize=True)
print('Rendered social preview: 1280 x 640.')
