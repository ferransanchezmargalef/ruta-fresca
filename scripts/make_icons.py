"""Dibuja los iconos de Ruta fresca (círculo de sol y sombra con una ruta) en app/icons/."""
import os
from PIL import Image, ImageDraw

OUT = os.environ.get('RF_WEB', 'app/') + 'icons/'
os.makedirs(OUT, exist_ok=True)
S = 2048                                    # se dibuja a 4x y se reduce, para bordes suaves
INK, SUN, SHADE, WHITE = '#13302a', '#cf5a26', '#235f98', '#f4f7f5'

img = Image.new('RGB', (S, S), INK)
d = ImageDraw.Draw(img)
c, R = S // 2, 640                          # radio 0,31 del lado: cabe en la zona segura de los iconos adaptables
box = (c - R, c - R, c + R, c + R)
d.pieslice(box, 135, 315, fill=SUN)         # mitad al sol (arriba a la izquierda)
d.pieslice(box, -45, 135, fill=SHADE)       # mitad a la sombra (abajo a la derecha)
# ruta: curva suave por la mitad a la sombra, de la salida (punto) a la llegada (diana)
P0, P1, P2, P3 = (760, 1500), (1240, 1700), (980, 1080), (1540, 960)
route = [tuple(round((1 - t) ** 3 * a + 3 * (1 - t) ** 2 * t * b + 3 * (1 - t) * t ** 2 * c_ + t ** 3 * e) for a, b, c_, e in zip(P0, P1, P2, P3))
         for t in [i / 60 for i in range(61)]]
w = 112
d.line(route, fill=WHITE, width=w, joint='curve')
for x, y in route:
    d.ellipse((x - w // 2, y - w // 2, x + w // 2, y + w // 2), fill=WHITE)
x, y = route[0]; d.ellipse((x - 92, y - 92, x + 92, y + 92), fill=WHITE)
x, y = route[-1]; d.ellipse((x - 120, y - 120, x + 120, y + 120), fill=WHITE); d.ellipse((x - 52, y - 52, x + 52, y + 52), fill=INK)

for size, name in [(512, 'icon-512.png'), (192, 'icon-192.png'), (180, 'apple-touch-icon.png'), (32, 'favicon-32.png')]:
    img.resize((size, size), Image.LANCZOS).save(OUT + name, optimize=True)
print('iconos en', OUT, sorted(os.listdir(OUT)))
