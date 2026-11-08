"""Elige los ejemplos que se ven al abrir la web (15 de junio, 13 h): un colegio público con una salida a 500-900 m donde la ruta
fresca gana mucha sombra o seguridad sin alargar mucho el camino, y un centro de mayores para el paso lento. Los candidatos salen
de un Dijkstra en Python; la elección final usa el cálculo de rutas de la propia web (Chromium) y se guarda en schools.json."""
import json, base64, subprocess, sys, time, os
import numpy as np
from scipy.sparse import csr_matrix
from scipy.sparse.csgraph import dijkstra
from playwright.sync_api import sync_playwright
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..')); D = f'{ROOT}/app/data/'
IX = json.load(open(D + 'index.json')); S = json.load(open(D + 'schools.json'))
NN, NL = IX['nn'], IX['nl']
lat = np.zeros(NN); lon = np.zeros(NN); A = np.zeros(NL, int); B = np.zeros(NL, int); Ln = np.zeros(NL); sh = np.zeros(NL); tr = np.zeros(NL); la_ = np.zeros(NL)
for i, j, k0, n, kb in IX['tiles']:
    t = json.load(open(D + f't/{i}_{j}.json'))
    for g, a, b in t['nodes']: lat[g] = a / 1e6; lon[g] = b / 1e6
    s13 = np.frombuffer(base64.b64decode(t['sh'][2]), np.uint8) / 100
    trr = np.frombuffer(base64.b64decode(t['traf']), np.uint8) & 3; acc = np.frombuffer(base64.b64decode(t['lacc']), np.uint8)
    for q, L in enumerate(t['links']):
        A[k0 + q], B[k0 + q], Ln[k0 + q] = L[0], L[1], L[2]
    sh[k0:k0 + n] = s13; tr[k0:k0 + n] = trr; la_[k0:k0 + n] = acc
KX = 111320 * np.cos(np.radians(40.42)); KY = 110540
def build(cost):
    ok = A != B; c = np.maximum(cost[ok], 0.01)
    return csr_matrix((np.concatenate([c, c]), (np.concatenate([A[ok], B[ok]]), np.concatenate([B[ok], A[ok]]))), shape=(NN, NN))
Mc = build(Ln); Mf = build(Ln * (1 + 1.5 * (1 - sh)) * (1 + 0.1 * tr) + 30 * np.minimum(la_, 3))
def near(la, lo):
    d = np.hypot((lon - lo) * KX, (lat - la) * KY); c = int(d.argmin()); return c, d[c]
cands = []
pub = [s for s in S['schools'] if s['t'] == 'Colegio público' and s['dis'] in ('Centro', 'Arganzuela', 'Chamberí', 'Tetuán', 'Salamanca', 'Retiro', 'Usera', 'Carabanchel', 'Latina', 'Puente de Vallecas')]
print('colegios públicos candidatos', len(pub))
for s in pub:
    c, dc_ = near(s['lat'], s['lon'])
    if dc_ > 120: continue
    dc = dijkstra(Mc, indices=c, limit=1000); df = dijkstra(Mf, indices=c, limit=3000)
    cand = np.where((dc >= 500) & (dc <= 900))[0]
    for o in cand[::max(1, len(cand) // 60)]:
        if not np.isfinite(df[o]): continue
        cands.append((s, o))
print('pares', len(cands))
# evaluación rápida con la web: todos los pares (agrupados), con el cálculo real
srv = subprocess.Popen([sys.executable, '-m', 'http.server', '8772', '-d', f'{ROOT}/test'], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL); time.sleep(1)
try:
    with sync_playwright() as p:
        b = p.chromium.launch(); pg = b.new_page()
        pg.route('**/fonts.g*/**', lambda r: r.abort())
        pg.goto('http://localhost:8772/index.html?debug=1'); pg.wait_for_function('window.__rf', timeout=60000)
        pairs = [{'n': s['n'], 'lat': s['lat'], 'lon': s['lon'], 'o': [float(lat[o]), float(lon[o])]} for s, o in cands]
        res = []
        for k in range(0, len(pairs), 150):
            res += pg.evaluate('''async (P) => {
                const R = window.__rf; R.state.di = 0; R.state.hi = 2; R.state.prio = 1; const out = [];
                for(const c of P){
                    const rr = await R.pair(c.o, [c.lat, c.lon], "fresca"); if(!rr) continue; const [f, k] = rr;
                    out.push({n: c.n, lat: c.lat, o: c.o, extra: Math.round(f.len - k.len), lf: Math.round(f.len), lc: Math.round(k.len), pf: f.pct, pc: k.pct, xf: f.crossNo, xc: k.crossNo, af: f.atr, ac: k.atr});
                }
                return out;
            }''', pairs[k:k + 150])
        # paso lento: centros de mayores con salidas a 600-900 m
        M = S['mayores']; lp = []
        for m in M:
            c, d0 = near(m['lat'], m['lon'])
            if d0 > 120: continue
            dc = dijkstra(Mc, indices=c, limit=1000)
            cand = np.where((dc >= 600) & (dc <= 900))[0]
            for o in cand[::max(1, len(cand) // 25)]: lp.append({'n': m['n'], 'lat': m['lat'], 'lon': m['lon'], 'o': [float(lat[o]), float(lon[o])]})
        resl = []
        for k in range(0, len(lp), 150):
            resl += pg.evaluate('''async (P) => {
                const R = window.__rf; R.state.di = 0; R.state.hi = 2; R.state.prio = 1; const out = [];
                for(const c of P){
                    const rr = await R.pair(c.o, [c.lat, c.lon], "lenta"); if(!rr) continue; const [f, k] = rr;
                    const ra = R.restAlong(f.pts), rb = R.restAlong(k.pts);
                    out.push({n: c.n, o: c.o, lf: Math.round(f.len), lc: Math.round(k.len), pf: f.pct, pc: k.pct, xf: f.crossNo, xc: k.crossNo, af: f.atr, ac: k.atr, ga: ra.maxGap, gb: rb.maxGap, nb: ra.count.banco, nf: ra.count.fuente});
                }
                return out;
            }''', lp[k:k + 150])
        b.close()
finally:
    srv.terminate()
def score(r): return (r['pf'] - r['pc']) + 4 * (r['ac'] - r['af']) + 6 * (r['xc'] - r['xf'])
ok = [r for r in res if r['lf'] <= 1.12 * r['lc'] and r['af'] <= r['ac'] and r['xf'] <= r['xc'] and r['pf'] >= 55]
ok.sort(key=lambda r: -score(r))
for r in ok[:8]: print(score(r), r)
okl = [r for r in resl if r['lf'] <= 1.15 * r['lc'] and r['af'] <= r['ac'] and r['xf'] <= r['xc'] and r['ga'] <= 150 and r['pf'] >= 55]
okl.sort(key=lambda r: -((r['pf'] - r['pc']) + (r['gb'] - r['ga']) / 20 + 4 * (r['ac'] - r['af'])))
for r in okl[:6]: print(r)
best, bl = ok[0], okl[0]
S['demo'] = {'cole': {'n': best['n'], 'lat': best['lat'], 'o': [round(v, 6) for v in best['o']]}, 'lento': {'n': bl['n'], 'o': [round(v, 6) for v in bl['o']]}}
json.dump(S, open(D + 'schools.json', 'w'), separators=(',', ':'), ensure_ascii=False)
json.dump(S['demo'], open(f'{ROOT}/work/demo.json', 'w'), ensure_ascii=False)   # para que build_madrid.py lo conserve
print('ejemplos guardados:', S['demo'])
