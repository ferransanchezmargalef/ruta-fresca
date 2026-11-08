"""Prueba la web de Madrid en Chromium: ejemplos al abrir, paso lento, Ayuntamiento con los dos escenarios del plan, búsqueda por
calle y número, móvil, modo oscuro y uso sin conexión de lo ya cargado. Capturas en shots/."""
import os, subprocess, sys, time, json
from playwright.sync_api import sync_playwright
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..')); SH = f'{ROOT}/shots/'; os.makedirs(SH, exist_ok=True)
srv = subprocess.Popen([sys.executable, '-m', 'http.server', '8773', '-d', f'{ROOT}/test'], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
time.sleep(1)
logs = []
def hook(pg, name):
    pg.on('console', lambda m: logs.append(f'[{name}] {m.type}: {m.text}') if m.type in ('error', 'warning') and 'Failed to load resource' not in m.text else None)
    pg.on('pageerror', lambda e: logs.append(f'[{name}] pageerror: {e}'))
    pg.route('**/fonts.g*/**', lambda r: r.abort())
txt = lambda pg, sel, n=500: pg.inner_text(sel)[:n].replace('\n', ' | ')
try:
    with sync_playwright() as p:
        b = p.chromium.launch()
        ctx = b.new_context(viewport={'width': 1400, 'height': 900}); pg = ctx.new_page(); hook(pg, 'escritorio')
        t0 = time.time(); pg.goto('http://localhost:8773/index.html?debug=1')
        pg.wait_for_selector('#cole-result .compare', timeout=60000); pg.wait_for_timeout(1200)
        print('al cole (ejemplo) en', round(time.time() - t0, 1), 's:', txt(pg, '#cole-result', 300)); pg.screenshot(path=SH + 'm1_cole.png')
        pg.click('#tab-lento'); pg.wait_for_selector('#lento-result .compare', timeout=60000); pg.wait_for_timeout(1000)
        print('paso lento:', txt(pg, '#lento-result', 300)); pg.screenshot(path=SH + 'm2_lento.png')
        pg.click('#tab-ayto'); pg.wait_for_timeout(1000); pg.screenshot(path=SH + 'm3_ayto.png')
        print('ayto:', txt(pg, '#mode-ayto', 700))
        pg.click('#plant-seg [data-pl="1"]'); pg.wait_for_selector('#plant-gain:not(.hidden)', timeout=30000); pg.wait_for_timeout(800)
        print('plan:', txt(pg, '#plant-help', 600)); pg.screenshot(path=SH + 'm4_plan.png')
        pg.click('#plant-seg [data-pl="2"]'); pg.wait_for_timeout(800)
        print('junto a colegios:', txt(pg, '#plant-help', 600)); print('ganan:', txt(pg, '#gain-list', 400))
        pg.evaluate('() => document.querySelector("#gain-list .row").click()'); pg.wait_for_timeout(2500); pg.screenshot(path=SH + 'm5_plan_zoom.png')
        pg.click('#plant-seg [data-pl="0"]'); pg.wait_for_timeout(300)
        pg.evaluate('() => document.querySelector("#dis-list .row").click()'); pg.wait_for_timeout(1500); pg.screenshot(path=SH + 'm6_distrito.png')
        # búsqueda por calle y número
        pg.click('#tab-cole'); pg.wait_for_timeout(500)
        pg.focus('#street-cole'); pg.wait_for_function('document.querySelectorAll("#street-list option").length > 1000', timeout=30000)
        pg.fill('#num-cole', '20'); pg.fill('#street-cole', 'Calle de Santa Engracia'); pg.dispatch_event('#street-cole', 'input')
        pg.wait_for_timeout(2500); print('calle y número:', txt(pg, '#cole-result', 200))
        print('cuadrículas cargadas:', pg.evaluate('window.__rf.TILES.filter(t => t.ok).length'))
        # oscuro
        pg.evaluate('document.documentElement.dataset.theme = "dark"'); pg.wait_for_timeout(800); pg.screenshot(path=SH + 'm7_oscuro.png')
        ctx.close()
        # móvil
        mb = b.new_context(viewport={'width': 390, 'height': 844}, device_scale_factor=2, is_mobile=True, has_touch=True); pm = mb.new_page(); hook(pm, 'móvil')
        pm.goto('http://localhost:8773/index.html'); pm.wait_for_selector('#cole-result .compare', timeout=60000); pm.wait_for_timeout(1000)
        pm.screenshot(path=SH + 'm8_movil.png'); pm.screenshot(path=SH + 'm9_movil_panel.png', full_page=True); mb.close()
        # sin conexión (service worker en localhost): primera visita con conexión y luego sin ella
        oc = b.new_context(viewport={'width': 1200, 'height': 800}); po = oc.new_page(); hook(po, 'sin conexión')
        po.goto('http://localhost:8773/index.html'); po.wait_for_selector('#cole-result .compare', timeout=60000)
        po.wait_for_function('navigator.serviceWorker && navigator.serviceWorker.controller', timeout=20000) if po.evaluate('!!navigator.serviceWorker.controller') is False else None
        po.reload(); po.wait_for_selector('#cole-result .compare', timeout=60000); po.wait_for_timeout(1500)
        oc.set_offline(True); po.reload(); po.wait_for_selector('#cole-result .compare', timeout=60000)
        print('sin conexión:', txt(po, '#cole-result', 120)); oc.close()
        b.close()
finally:
    srv.terminate()
print('\n'.join(logs[:30]) or 'Consola: sin errores')
