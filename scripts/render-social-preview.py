"""Render the share image. Supply a Manrope TTF through --font."""
import argparse
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--font', type=Path, required=True)
args = parser.parse_args()
scale = 2
image = Image.new('RGB', (1280 * scale, 640 * scale), '#0b1118')
draw = ImageDraw.Draw(image)


def box(bounds, fill, outline=None, radius=0):
    coords = tuple(int(v * scale) for v in bounds)
    draw.rounded_rectangle(coords, radius=radius * scale, fill=fill, outline=outline, width=scale)


def text(x, y, value, size, color, weight=500):
    font = ImageFont.truetype(str(args.font), size * scale)
    font.set_variation_by_axes([weight])
    draw.text((x * scale, y * scale), value, fill=color, font=font)


box((23, 23, 1257, 617), None, '#2c4c59', 20)
box((66, 65, 112, 111), '#45dfff', radius=10)
text(74, 61, '↔', 34, '#0b1118', 650)
text(130, 69, 'Claude Session Linker', 30, '#eef3f5', 800)
text(67, 194, 'Sua conversa.', 68, '#eef3f5', 800)
text(67, 281, 'Continua daqui.', 68, '#c6ff5e', 800)
text(71, 397, 'Vincule e compare sessões', 25, '#a1b2bf')
text(71, 438, 'entre contas no mesmo computador.', 23, '#a1b2bf')
box((69, 500, 333, 544), '#172b31', '#335562', 8)
text(89, 511, 'CODE  /  COWORK', 17, '#45dfff', 700)
text(72, 572, 'WINDOWS + macOS · CONHEÇA NO GITHUB', 13, '#819aa9', 600)
box((797, 139, 1193, 303), '#111b25', '#335361', 13)
text(823, 164, 'CONTA DE ORIGEM', 13, '#45dfff', 700)
text(823, 204, 'Roteiro de pesquisa', 26, '#eef3f5', 750)
text(823, 253, 'Uma sessão para continuar.', 17, '#a1b2bf')
text(981, 313, '↓', 33, '#c6ff5e', 700)
box((797, 368, 1193, 533), '#16271f', '#5a713e', 13)
text(823, 392, 'CONTA DE DESTINO', 13, '#c6ff5e', 700)
text(823, 434, 'Um novo ponto de partida.', 22, '#eef3f5', 750)
text(823, 480, 'Cópia local · Exemplo ilustrativo', 15, '#a1b2bf')
destination = Path(__file__).resolve().parents[1] / 'docs/assets/social-preview.png'
image.resize((1280, 640), Image.Resampling.LANCZOS).save(destination, optimize=True)
print('Rendered social preview: 1280 x 640.')
