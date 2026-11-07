"""Comprueba la web de este repositorio antes de publicarla.

Pone al día la versión de sw.js (cambia con el contenido, para que los móviles descarguen la web nueva)
y prueba la web en Chromium: Al cole, Paso lento, Ayuntamiento con el simulador de plantación, valenciano,
móvil y uso sin conexión. Al final dice si la consola ha dado errores.

Uso, desde la raíz del repositorio:  python3 scripts/comprobar_web.py
Necesita Python con playwright (y Chromium: python3 -m playwright install chromium) y Pillow, y npm para
bajar Leaflet 1.9.4, que la web carga del CDN y aquí se sirve en local para probarla sin conexión.
Las capturas se guardan en la carpeta que indique RF_SHOTS o, si no, en una carpeta temporal.
"""
import base64, hashlib, os, re, shutil, subprocess, sys, tarfile, tempfile, time
from playwright.sync_api import sync_playwright
from PIL import Image

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.environ.get('RF_SHOTS') or tempfile.mkdtemp(prefix='ruta-fresca-capturas-')
os.makedirs(OUT, exist_ok=True)
TEST = tempfile.mkdtemp(prefix='ruta-fresca-prueba-')
PKG = tempfile.mkdtemp(prefix='leaflet-')

out = open(f'{ROOT}/index.html', encoding='utf-8').read()
tag = re.search(r'<script src="https://cdn\.jsdelivr\.net/npm/leaflet@1\.9\.4/dist/leaflet\.js" '
                r'integrity="([^"]+)" crossorigin="anonymous"></script>', out)
assert tag, 'No encuentro la etiqueta de Leaflet 1.9.4 en index.html'
subprocess.run(['npm', 'pack', 'leaflet@1.9.4', '--silent'], cwd=PKG, check=True, stdout=subprocess.DEVNULL)
with tarfile.open(os.path.join(PKG, 'leaflet-1.9.4.tgz')) as tf:
    try:
        tf.extractall(PKG, filter='data')
    except TypeError:
        tf.extractall(PKG)
leaflet = os.path.join(PKG, 'package', 'dist', 'leaflet.js')
sri = 'sha256-' + base64.b64encode(hashlib.sha256(open(leaflet, 'rb').read()).digest()).decode()
print('SRI de Leaflet igual al de index.html:', sri == tag.group(1))

# versión del service worker: huella de la web, el manifiesto, los datos, el método y los iconos
man = open(f'{ROOT}/manifest.webmanifest', encoding='utf-8').read()
h = hashlib.sha256(out.encode())
h.update(man.encode())
for f in sorted(os.listdir(f'{ROOT}/data')) + ['../metodo.html'] + ['../icons/' + i for i in sorted(os.listdir(f'{ROOT}/icons'))]:
    h.update(open(f'{ROOT}/data/{f}', 'rb').read())
ver = 'rf-' + h.hexdigest()[:12]
sw_old = open(f'{ROOT}/sw.js', encoding='utf-8').read()
sw = re.sub(r'rf-[0-9a-f]{12}', ver, sw_old)
if sw != sw_old:
    open(f'{ROOT}/sw.js', 'w', encoding='utf-8').write(sw)
    print('sw.js: versión nueva', ver, '(hay que publicarla)')
else:
    print('sw.js: versión', ver, '(sin cambios)')

open(f'{TEST}/index.html', 'w', encoding='utf-8').write(out.replace(tag.group(0), '<script src="leaflet.js"></script>'))
shutil.copy(leaflet, f'{TEST}/leaflet.js')
for f in ('manifest.webmanifest', 'sw.js', 'metodo.html'):
    shutil.copy(f'{ROOT}/{f}', f'{TEST}/{f}')
for d in ('data', 'icons'):
    os.symlink(f'{ROOT}/{d}', f'{TEST}/{d}')

srv = subprocess.Popen([sys.executable, '-m', 'http.server', '8765', '-d', TEST],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
time.sleep(1)
logs = []


def hook(pg, name):
    pg.on('console', lambda m: logs.append(f'[{name}] {m.type}: {m.text}')
          if m.type in ('error', 'warning') and 'Failed to load resource' not in m.text else None)
    pg.on('pageerror', lambda e: logs.append(f'[{name}] pageerror: {e}'))
    pg.route('**/fonts.googleapis.com/**', lambda r: r.abort())
    pg.route('**/fonts.gstatic.com/**', lambda r: r.abort())


def txt(pg, sel, n=400):
    return pg.inner_text(sel).replace('\n', ' | ')[:n]


try:
    with sync_playwright() as p:
        b = p.chromium.launch()
        pg = b.new_page(viewport={'width': 1440, 'height': 900})
        hook(pg, 'escritorio')
        t = time.time()
        pg.goto('http://localhost:8765/index.html')
        pg.wait_for_selector('#cole-result .compare', timeout=40000)
        print('carga + ruta inicial:', round(time.time() - t, 2), 's')
        pg.wait_for_timeout(700)
        print('COLE:', txt(pg, '#cole-result'))
        pg.screenshot(path=f'{OUT}/shot_cole.png')
        for hb in ('0', '4', '5'):
            pg.click(f'#hours button[data-h="{hb}"]'); pg.wait_for_timeout(500)
            print(f'COLE hora {hb}:', txt(pg, '#cole-result', 330))
        pg.click('#hours button[data-h="2"]'); pg.wait_for_timeout(500)
        pg.click('#tab-lento'); pg.wait_for_selector('#lento-result .compare', timeout=10000); pg.wait_for_timeout(500)
        print('LENTO:', txt(pg, '#lento-result'))
        pg.screenshot(path=f'{OUT}/shot_lento.png')
        pg.click('#tab-ayto'); pg.wait_for_timeout(900)
        print('KPIS:', txt(pg, '#kpis'))
        print('LEAD:', txt(pg, '#ayto-lead'))
        print('PRIO:', txt(pg, '#prio-list', 700))
        print('CAMINOS:', txt(pg, '#camins-list', 300))
        pg.screenshot(path=f'{OUT}/shot_ayto.png')
        pg.click('#prio-list .row'); pg.wait_for_timeout(700)
        print('POPUP:', txt(pg, '.leaflet-popup-content', 250))
        pg.click('#camins-list .row'); pg.wait_for_timeout(700)
        print('PLANTAR (antes):', txt(pg, '#plant-help', 300))
        pg.click('#plant-seg button[data-pl="1"]'); pg.wait_for_selector('#plant-gain:not(.hidden)', timeout=20000); pg.wait_for_timeout(800)
        print('PLANTAR habitual:', txt(pg, '#kpis', 420), '|', txt(pg, '#plant-help', 520))
        print('GANAN MÁS:', txt(pg, '#gain-list', 520))
        pg.screenshot(path=f'{OUT}/shot_plant.png')
        pg.click('#gain-list .row'); pg.wait_for_timeout(800)
        print('POPUP plantación:', txt(pg, '.leaflet-popup-content', 320))
        pg.click('#plant-seg button[data-pl="2"]'); pg.wait_for_timeout(800)
        print('PLANTAR grande:', txt(pg, '#kpis', 300), '|', txt(pg, '#plant-help', 420))
        pg.click('#plant-seg button[data-pl="0"]'); pg.wait_for_timeout(600)
        print('SIN PLANTAR:', txt(pg, '#kpis', 200), '|', txt(pg, '#plant-help', 160))
        pg.click('#tab-cole'); pg.wait_for_timeout(700)
        pg.mouse.click(1100, 300); pg.wait_for_timeout(700)
        print('COLE tras tocar el mapa:', txt(pg, '#cole-result', 200))
        pg.focus('#street-cole'); pg.wait_for_timeout(1500)
        print('calles en el buscador:', pg.eval_on_selector_all('#street-list option', 'o => o.length'))
        pg.fill('#street-cole', 'Avinguda Blasco Ibáñez'); pg.wait_for_timeout(800)
        pg.fill('#num-cole', '21'); pg.press('#num-cole', 'Enter'); pg.wait_for_timeout(800)
        print('COLE calle y número:', txt(pg, '#cole-result', 200))
        pg.click('details.steps summary'); pg.wait_for_timeout(300)
        print('INDICACIONES:', txt(pg, 'details.steps', 300))
        pg.click('#prio button[data-p="2"]'); pg.wait_for_timeout(700)
        print('COLE prioridad seguridad:', txt(pg, '#cole-result', 200))
        pg.click('#prio button[data-p="1"]'); pg.click('#dates button[data-d="1"]'); pg.wait_for_timeout(700)
        print('COLE septiembre:', txt(pg, '#cole-result', 200))
        pg.click('#dates button[data-d="0"]'); pg.wait_for_timeout(400)
        pg.click('#lang-btn'); pg.wait_for_timeout(700)
        print('VALENCIANO:', txt(pg, '#cole-result', 300), '| pestañas:', txt(pg, '.tabs', 80))
        pg.screenshot(path=f'{OUT}/shot_va.png')
        pg.click('#tab-lento'); pg.wait_for_timeout(700); print('VA LENTO:', txt(pg, '#lento-result', 300))
        pg.click('#tab-ayto'); pg.wait_for_timeout(700); print('VA AYTO:', txt(pg, '#kpis', 300))
        pg.click('#lang-btn'); pg.wait_for_timeout(500); pg.click('#tab-cole'); pg.wait_for_timeout(500)
        pg.emulate_media(color_scheme='dark'); pg.wait_for_timeout(700)
        pg.click('#tab-ayto'); pg.wait_for_timeout(900)
        pg.screenshot(path=f'{OUT}/shot_dark.png')
        mb = b.new_page(viewport={'width': 390, 'height': 844}, is_mobile=True, has_touch=True)
        hook(mb, 'movil')
        mb.goto('http://localhost:8765/index.html'); mb.wait_for_selector('#cole-result .compare', timeout=40000); mb.wait_for_timeout(700)
        mb.screenshot(path=f'{OUT}/shot_mobile.png', full_page=True)
        # sin conexión: tras abrirla una vez, la web y sus datos deben cargar desde la copia guardada
        ctx = b.new_context(viewport={'width': 1200, 'height': 800}); off = ctx.new_page(); hook(off, 'sin-conexion')
        off.goto('http://localhost:8765/index.html'); off.wait_for_selector('#cole-result .compare', timeout=40000)
        print('service worker activo:', off.evaluate('navigator.serviceWorker.ready.then(r => !!r.active)'))
        off.reload(); off.wait_for_selector('#cole-result .compare', timeout=40000)
        print('manifiesto:', off.evaluate('fetch("manifest.webmanifest").then(r => r.json()).then(j => j.name + " · " + j.icons.length + " iconos")'))
        ctx.set_offline(True); off.reload(); off.wait_for_selector('#cole-result .compare', timeout=40000)
        print('SIN CONEXIÓN:', txt(off, '#cole-result', 120))
        ctx.close()
        b.close()
finally:
    srv.terminate()
    shutil.rmtree(TEST, ignore_errors=True)
    shutil.rmtree(PKG, ignore_errors=True)

W, H = 1440, 900
grid = Image.new('RGB', (W, H), 'white')
for k, name in enumerate(['shot_cole.png', 'shot_lento.png', 'shot_ayto.png', 'shot_plant.png']):
    grid.paste(Image.open(f'{OUT}/{name}').resize((W // 2, H // 2)), ((k % 2) * W // 2, (k // 2) * H // 2))
grid.save(f'{OUT}/shot_grid.png')
print('Capturas en', OUT)
print('\n'.join(logs) if logs else 'Consola: sin errores')
