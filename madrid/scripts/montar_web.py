"""Monta la web de Madrid: app/index.html (CSS de Leaflet incrustado y SRI de leaflet.js), manifiesto, service worker con una
versión que cambia con el contenido, y una copia de prueba en test/ que usa leaflet.js local (para probar sin conexión).
Uso: python3 scripts/montar_web.py  (desde la carpeta de Madrid; Leaflet 1.9.4 en vendor/package, de npm pack leaflet@1.9.4)"""
import base64, hashlib, os, shutil
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
src = open(f'{ROOT}/src/index.html', encoding='utf-8').read()
css = open(f'{ROOT}/vendor/package/dist/leaflet.css', encoding='utf-8').read()
js = open(f'{ROOT}/vendor/package/dist/leaflet.js', 'rb').read()
sri = 'sha256-' + base64.b64encode(hashlib.sha256(js).digest()).decode()
assert sri == 'sha256-20nQCchB9co0qIjJZRGuk2/Z9VM+kNiyxNV1lvTlZBo=', 'leaflet.js no es el oficial de Leaflet 1.9.4'
out = src.replace('/*LEAFLET_CSS*/', css).replace('__LEAFLET_SRI__', sri)
open(f'{ROOT}/app/index.html', 'w', encoding='utf-8').write(out)
man = open(f'{ROOT}/src/manifest.webmanifest', encoding='utf-8').read()
h = hashlib.sha256(out.encode()); h.update(man.encode())
files = []
for d, _, fs in os.walk(f'{ROOT}/app/data'):
    files += [os.path.join(d, f) for f in fs]
files = sorted(files) + ([f'{ROOT}/app/metodo.html'] if os.path.exists(f'{ROOT}/app/metodo.html') else []) + sorted(f'{ROOT}/app/icons/' + i for i in os.listdir(f'{ROOT}/app/icons'))
for f in files: h.update(open(f, 'rb').read())
sw = open(f'{ROOT}/src/sw.js', encoding='utf-8').read().replace('__VERSION__', h.hexdigest()[:12])
open(f'{ROOT}/app/manifest.webmanifest', 'w', encoding='utf-8').write(man)
open(f'{ROOT}/app/sw.js', 'w', encoding='utf-8').write(sw)
T = f'{ROOT}/test'; os.makedirs(T, exist_ok=True)
tag = f'<script src="https://cdn.jsdelivr.net/npm/leaflet@1.9.4/dist/leaflet.js" integrity="{sri}" crossorigin="anonymous"></script>'
assert tag in out
open(f'{T}/index.html', 'w', encoding='utf-8').write(out.replace(tag, '<script src="leaflet.js"></script>'))
shutil.copy(f'{ROOT}/vendor/package/dist/leaflet.js', f'{T}/leaflet.js')
for f in ('manifest.webmanifest', 'sw.js'): shutil.copy(f'{ROOT}/app/{f}', f'{T}/{f}')
if os.path.exists(f'{ROOT}/app/metodo.html'): shutil.copy(f'{ROOT}/app/metodo.html', f'{T}/metodo.html')
for d in ('data', 'icons'):
    if not os.path.exists(f'{T}/{d}'): os.symlink(f'{ROOT}/app/{d}', f'{T}/{d}')
print('index.html', len(out.encode()) // 1024, 'KB · sw.js', sw.split('"')[1])
