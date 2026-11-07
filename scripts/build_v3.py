"""Ruta fresca v2 — sombra real por horas (edificios + árboles) y seguridad vial.

Entradas: work/ (OSM, capas municipales, árboles, edificios del Catastro, atropellos ubicados) y raw/ (velocidades, tráfico, cruces)
Salidas:  app/data/graph.json, schools.json, pois.json

Sombra (15 de junio, el día con el sol más alto del curso escolar; horas oficiales de verano):
- Edificios: altura = plantas sobre rasante x 3 m + 1 m (planta baja), rasterizada a 1 m. Un punto está a la sombra
  si, mirando hacia el sol, algún edificio supera la línea del sol.
- Árboles: copa circular (radio por clase de copa) desplazada en la dirección de la sombra según la altura del árbol;
  la sombra útil depende del tipo (palmera 0,35, conífera 0,8, arbusto 0,5...) y del estado.
- Aceras: a 1,5 m de la fachada más cercana (si hay edificios a menos de 25 m); si no, a una distancia según el tipo de vía.
- Cada tramo toma la acera más sombreada (se puede cambiar de acera).
Seguridad:
- Nivel de tráfico del tramo (0-3): clase de vía (OSM), límite de velocidad municipal y tramos con aforo municipal.
- Cruces de vías con tráfico (con o sin semáforo, OSM) y atropellos 2022-2025 ubicados por dirección.
"""
import json, math, collections, base64, os, re, time
import numpy as np, pandas as pd, shapefile
from PIL import Image, ImageDraw
from pyproj import Transformer
from scipy.spatial import cKDTree
from shapely.geometry import shape, Point, LineString
from shapely.ops import unary_union
from shapely.prepared import prep
from shapely import STRtree
import networkx as nx

t0 = time.time()
def log(*a): print(f'[{time.time() - t0:6.1f}s]', *a, flush=True)
W, RAW, OUT = 'work/', 'raw/', 'app/data/'
os.makedirs(OUT, exist_ok=True)
to_utm = Transformer.from_crs(4326, 25830, always_xy=True)
to_wgs = Transformer.from_crs(25830, 4326, always_xy=True)
HOURS = [9, 11, 13, 15, 17, 19]
DAYS = [(2026, 6, 15), (2026, 9, 15)]
DAYNAMES = ['15 de junio', '15 de septiembre']
FLOOR_H = float(os.environ.get('RF_FLOOR_H', 3.0)); GROUND_X = float(os.environ.get('RF_GROUND_X', 1.0))
CROWN_K = float(os.environ.get('RF_CROWN_K', 1.0)); WALL_OFF = float(os.environ.get('RF_WALL_OFF', 1.5))
OUT = os.environ.get('RF_OUT', OUT); LIGHT = bool(os.environ.get('RF_LIGHT'))
LAT0, LON0 = 39.4699, -0.3763
b64 = lambda a: base64.b64encode(np.asarray(a, np.uint8).tobytes()).decode()


def sun(hour_local, day):
    """Acimut (grados desde el norte, sentido horario) y elevación del sol en València (Astronomical Almanac, baja precisión)."""
    y, m, d = day; ut = hour_local - 2
    a = (14 - m) // 12; yy = y + 4800 - a; mm = m + 12 * a - 3
    jd = d + (153 * mm + 2) // 5 + 365 * yy + yy // 4 - yy // 100 + yy // 400 - 32045 - 0.5 + ut / 24
    n = jd - 2451545.0
    L = (280.460 + 0.9856474 * n) % 360
    g = math.radians((357.528 + 0.9856003 * n) % 360)
    lam = math.radians(L + 1.915 * math.sin(g) + 0.020 * math.sin(2 * g))
    eps = math.radians(23.439 - 0.0000004 * n)
    ra = math.atan2(math.cos(eps) * math.sin(lam), math.cos(lam))
    dec = math.asin(math.sin(eps) * math.sin(lam))
    gmst = (18.697374558 + 24.06570982441908 * n) % 24
    H = math.radians(((gmst + LON0 / 15) % 24) * 15) - ra
    phi = math.radians(LAT0)
    el = math.asin(math.sin(phi) * math.sin(dec) + math.cos(phi) * math.cos(dec) * math.cos(H))
    az = math.atan2(-math.sin(H), math.tan(dec) * math.cos(phi) - math.sin(phi) * math.cos(H))
    return math.degrees(az) % 360, math.degrees(el)


SUNS = [sun(h, d) for d in DAYS for h in HOURS]   # escenario k = fecha * 6 + hora
NSC = len(SUNS)
log('sol (acimut, elevación):', [(DAYNAMES[k // 6], HOURS[k % 6], round(a), round(e, 1)) for k, (a, e) in enumerate(SUNS)])

# ---------------- municipio ----------------
LY = json.load(open(W + 'layers.json'))
barrios = [(f['properties']['nombre'], shape(f['geometry'])) for f in LY['barrios']['features']]
muni_p = prep(unary_union([g for _, g in barrios]).buffer(0.0003))

# ---------------- árboles ----------------
t = pd.read_pickle(W + 'trees.pkl')
def cls(s):
    if not isinstance(s, str): return None
    s = s.replace(' ', '').replace('m', '')
    return {'0/4': '0-4', '0-4': '0-4', '4/8': '4-8', '4-8': '4-8', '8/12': '8-12', '8-12': '8-12', '>12': '>12'}.get(s)
t['copa_c'] = t.copa.map(cls); t['alt_c'] = t.altura.map(cls)
t['r'] = t.copa_c.map({'0-4': 1.5, '4-8': 3.0, '8-12': 5.0, '>12': 6.5})
t.loc[t.r.isna(), 'r'] = t.loc[t.r.isna(), 'alt_c'].map({'0-4': 1.2, '4-8': 2.5, '8-12': 3.5, '>12': 4.5})
t['r'] = t.r.fillna(2.0)
t['h'] = t.alt_c.map({'0-4': 3.0, '4-8': 6.0, '8-12': 10.0, '>12': 14.0})
t['h'] = t.h.fillna(2.2 * t.r + 1)
def gfac(g):
    if not isinstance(g, str): return 0.8
    if g.startswith('Caduc') or g == 'Perenne': return 1.0
    if g == 'Conifera': return 0.8
    if g == 'Palmacea': return 0.35
    if g.startswith('Arbusto'): return 0.5
    return 0.8
t['f'] = t.grupo.map(gfac)
t.loc[t.estado == 'Malo', 'f'] *= 0.6
t.loc[t.estado == 'Regular', 'f'] *= 0.85
dead = t.estado.isin(['Falta', 'Tocón', 'Seco'])
pits = t[t.estado.isin(['Falta', 'Tocón']) & (t.tipo == 'Viario')].copy()
live = t[~dead].reset_index(drop=True)
TX = live[['x', 'y']].to_numpy(); TR = live.r.to_numpy() * CROWN_K; TF = live.f.to_numpy(); THC = 0.65 * live.h.to_numpy()
RMAX = 6.5 * CROWN_K
log('árboles vivos', len(live), 'alcorques de calle vacíos', len(pits))

# ---------------- red peatonal OSM ----------------
osm = json.load(open(W + 'osm.json'))['elements']
nodes = {e['id']: (e['lon'], e['lat']) for e in osm if e['type'] == 'node'}
ways = [e for e in osm if e['type'] == 'way']
OFF = {'primary': 9, 'primary_link': 6, 'secondary': 8, 'secondary_link': 6, 'tertiary': 7, 'tertiary_link': 5, 'residential': 5,
       'unclassified': 5, 'service': 3, 'trunk': 10, 'trunk_link': 6, 'living_street': 3, 'pedestrian': 4}
OSMCLS = {'trunk': 3, 'trunk_link': 3, 'primary': 3, 'primary_link': 3, 'secondary': 2, 'secondary_link': 2, 'tertiary': 1, 'tertiary_link': 1}
nid = list(nodes.keys()); nll = np.array([nodes[i] for i in nid])
ux, uy = to_utm.transform(nll[:, 0], nll[:, 1]); utm = {i: (x, y) for i, x, y in zip(nid, ux, uy)}
segs = []
for w in ways:
    tg = w.get('tags', {}); hw = tg.get('highway'); foot = tg.get('foot'); acc = tg.get('access')
    if foot == 'no': continue
    if acc in ('private', 'no') and foot not in ('yes', 'designated', 'permissive'): continue
    if hw in ('trunk', 'trunk_link') and foot not in ('yes', 'designated'): continue
    if hw == 'service' and tg.get('service') in ('parking_aisle', 'drive-through'): continue
    nds = [n for n in w['nodes'] if n in utm]
    for a, b in zip(nds[:-1], nds[1:]):
        if a != b: segs.append((a, b, OFF.get(hw, 0), tg.get('name', ''), hw))
segs = [s for s in segs if muni_p.contains(Point((nodes[s[0]][0] + nodes[s[1]][0]) / 2, (nodes[s[0]][1] + nodes[s[1]][1]) / 2))]
NS = len(segs)
A = np.array([utm[s[0]] for s in segs]); B = np.array([utm[s[1]] for s in segs])
D = B - A; Ls = np.hypot(D[:, 0], D[:, 1]); Ls[Ls == 0] = 0.01
N = np.stack([-D[:, 1] / Ls, D[:, 0] / Ls], axis=1)
defoff = np.array([s[2] for s in segs], float)
footlike = defoff == 0
log('segmentos en el municipio', NS)

# ---------------- edificios: ráster de alturas a 1 m ----------------
RES = 1.0
allxy = np.vstack([A, B])
X0, X1 = allxy[:, 0].min() - 450, allxy[:, 0].max() + 450
Y0, Y1 = allxy[:, 1].min() - 450, allxy[:, 1].max() + 450
NC, NR = int(math.ceil((X1 - X0) / RES)), int(math.ceil((Y1 - Y0) / RES))
G = np.zeros((NR, NC), np.uint8)
BZ = np.load(W + 'buildings.npz')
floors = BZ['floors'].astype(np.int32); ring_part = BZ['ring_part']; ring_hole = BZ['ring_hole']; ring_off = BZ['ring_off']; XY = BZ['xy']
hgt = np.where(floors > 0, np.minimum(np.round(floors * FLOOR_H + GROUND_X), 250), 0).astype(int)
first = np.searchsorted(ring_part, np.arange(len(floors) + 1))
for p in np.nonzero(hgt > 0)[0]:
    rings = [(XY[ring_off[r]:ring_off[r + 1]], ring_hole[r]) for r in range(first[p], first[p + 1])]
    ext = [v for v, h in rings if not h]
    if not ext: continue
    allv = np.vstack(ext); cols = (allv[:, 0] - X0) / RES; rows = (Y1 - allv[:, 1]) / RES
    c0, c1 = max(0, int(cols.min())), min(NC, int(math.ceil(cols.max())) + 1)
    q0, q1 = max(0, int(rows.min())), min(NR, int(math.ceil(rows.max())) + 1)
    if c1 - c0 < 1 or q1 - q0 < 1: continue
    img = Image.new('L', (c1 - c0, q1 - q0), 0); dr = ImageDraw.Draw(img)
    for v, h in rings:
        if len(v) >= 3: dr.polygon(list(zip((v[:, 0] - X0) / RES - c0, (Y1 - v[:, 1]) / RES - q0)), fill=0 if h else 1)
    m = np.asarray(img, dtype=bool)
    sub = G[q0:q1, c0:c1]; np.maximum(sub, m.astype(np.uint8) * np.uint8(hgt[p]), out=sub)
HMAX = int(G.max())
log('ráster de edificios', G.shape, 'altura máx', HMAX, 'm; celdas con edificio', round(float((G > 0).mean()) * 100, 1), '%')

def pix(P):
    c = ((P[:, 0] - X0) / RES).astype(np.int64); r = ((Y1 - P[:, 1]) / RES).astype(np.int64)
    return np.clip(r, 0, NR - 1), np.clip(c, 0, NC - 1)

# ---------------- muestras sobre las aceras ----------------
ns_ = np.maximum(1, np.ceil(Ls / 4).astype(int))
seg_idx = np.repeat(np.arange(NS), ns_)
frac = np.concatenate([(np.arange(n) + 0.5) / n for n in ns_])
base = A[seg_idx] + D[seg_idx] * frac[:, None]
Nn = N[seg_idx]; dflt = defoff[seg_idx]; flk = footlike[seg_idx]
side_pts, wall = [], []
for sgn in (1, -1):
    w = np.full(len(base), np.inf)
    for k in range(1, 26):
        r, c = pix(base + sgn * Nn * k)
        hit = (G[r, c] > 0) & np.isinf(w)
        w[hit] = k
    off = np.where(np.isfinite(w), np.maximum(0.5, w - WALL_OFF), dflt)
    off = np.where(flk, 0.0, off)
    side_pts.append(base + sgn * Nn * off[:, None]); wall.append(np.isfinite(w))
urban_seg = np.bincount(seg_idx, weights=(wall[0] | wall[1]).astype(float), minlength=NS) / np.bincount(seg_idx, minlength=NS) >= 0.5
log('muestras', len(base), 'tramos urbanos (con fachadas)', int(urban_seg.sum()))

# ---------------- caminos escolares (muestras propias) ----------------
cam_pts, cam_owner, cam_len, cam_lines = [], [], collections.defaultdict(float), collections.defaultdict(list)
cam_names = []
for f in LY['colecamins']['features']:
    gg = f['geometry']; nm = f['properties']['capa']
    if nm not in cam_names: cam_names.append(nm)
    ci = cam_names.index(nm)
    for line in ([gg['coordinates']] if gg['type'] == 'LineString' else gg['coordinates']):
        arr = np.array(line)[:, :2]; x, y = to_utm.transform(arr[:, 0], arr[:, 1]); P = np.c_[x, y]
        for p0, p1 in zip(P[:-1], P[1:]):
            dd = p1 - p0; L_ = float(np.hypot(*dd))
            if L_ < 0.01: continue
            n = max(1, int(math.ceil(L_ / 4))); fr = (np.arange(n) + 0.5) / n; nrm = np.array([-dd[1], dd[0]]) / L_
            pts_ = p0 + dd * fr[:, None]
            for o in (0, 3, -3): cam_pts.append(pts_ + o * nrm); cam_owner.append(np.full(n, ci))
            cam_len[ci] += L_
        cam_lines[ci].append([[round(b_, 6), round(a_, 6)] for a_, b_ in arr])
cam_pts = np.vstack(cam_pts); cam_owner = np.concatenate(cam_owner)

# ---------------- sombra por hora ----------------
ALL = np.vstack([side_pts[0], side_pts[1], cam_pts])
NA = len(ALL); nb = len(base)
pr, pc = pix(ALL)
inside = G[pr, pc] > 0
shade = np.zeros((NA, NSC), np.float32)
bld_only = np.zeros((NA, NSC), bool)
for hi, (az, el) in enumerate(SUNS):
    tanE = math.tan(math.radians(el)); sx, sy = math.sin(math.radians(az)), -math.cos(math.radians(az))
    sh = inside.copy(); last = None
    for tt in range(1, int(min(450, HMAX / tanE)) + 1):
        oc, orr = int(round(tt * sx / RES)), int(round(tt * sy / RES))
        if (orr, oc) == last: continue
        last = (orr, oc)
        todo = np.nonzero(~sh)[0]
        if len(todo) == 0: break
        rr = np.clip(pr[todo] + orr, 0, NR - 1); cc = np.clip(pc[todo] + oc, 0, NC - 1)
        sh[todo[G[rr, cc] > tt * tanE]] = True
    bld_only[:, hi] = sh
    # árboles: copa desplazada en la dirección de la sombra
    dsh = np.array([-math.sin(math.radians(az)), -math.cos(math.radians(az))])
    centers = TX + dsh[None, :] * (THC / tanE)[:, None]
    kd = cKDTree(centers)
    d, idx = kd.query(ALL, k=8, distance_upper_bound=RMAX)
    valid = idx < len(TX); idx2 = np.where(valid, idx, 0)
    tree = np.where(valid & (d <= TR[idx2]), TF[idx2], 0.0).max(axis=1)
    shade[:, hi] = np.maximum(sh.astype(np.float32), tree)
    log(f'{DAYNAMES[hi // 6]} {HOURS[hi % 6]} h: sol a {el:.0f}°, sombra de edificios en {sh[:2 * nb].mean() * 100:.0f} % de las muestras, de árboles {np.mean(tree[:2 * nb] > 0) * 100:.0f} %')

SL, SRt, SC_ = shade[:nb], shade[nb:2 * nb], shade[2 * nb:]
cnt = np.bincount(seg_idx, minlength=NS).astype(float)
seg_sh = np.zeros((NS, NSC), np.float32); seg_bld = np.zeros((NS, NSC), np.float32)
for hi in range(NSC):
    ml = np.bincount(seg_idx, weights=SL[:, hi], minlength=NS) / cnt
    mr = np.bincount(seg_idx, weights=SRt[:, hi], minlength=NS) / cnt
    seg_sh[:, hi] = np.maximum(ml, mr)
    bl = np.bincount(seg_idx, weights=bld_only[:nb, hi], minlength=NS) / cnt
    br = np.bincount(seg_idx, weights=bld_only[nb:2 * nb, hi], minlength=NS) / cnt
    seg_bld[:, hi] = np.maximum(bl, br)

# ---------------- seguridad por segmento ----------------
osm_cls = np.array([0 if footlike[i] else OSMCLS.get(segs[i][4], 0) for i in range(NS)])
mid = (A + B) / 2
mid_pts = [Point(*p) for p in mid]
vr = shapefile.Reader(RAW + 'vel/Trafico__223', encoding='utf-8')
vgeo, vval = [], []
for shp_, rec in zip(vr.shapes(), vr.records()):
    if len(shp_.points) >= 2:
        vgeo.append(LineString(shp_.points)); vval.append(str(rec.as_dict().get('velocidad') or ''))
vtree = STRtree(vgeo)
(ii, jj), dist = vtree.query_nearest(mid_pts, max_distance=12, return_distance=True, all_matches=False)
vel_cls = np.zeros(NS, int)
for i, j in zip(ii, jj):
    if not footlike[i] and vval[j] in ('50', '40'): vel_cls[i] = 2
tram = json.load(open(RAW + 'tramos.geojson'))['features']
tgeo, timv = [], []
for f in tram:
    g = f.get('geometry')
    if not g or not g.get('coordinates'): continue
    co = np.array(g['coordinates'] if g['type'] == 'LineString' else [p for part in g['coordinates'] for p in part])
    x, y = to_utm.transform(co[:, 0], co[:, 1])
    try: v = float(f['properties'].get('imv') or 0)
    except ValueError: v = 0
    if len(x) >= 2: tgeo.append(LineString(np.c_[x, y])); timv.append(v)
timv = np.array(timv); pos = timv[timv > 0]; p50, p75 = np.percentile(pos, 50), np.percentile(pos, 75)
ttree = STRtree(tgeo)
(ii, jj), dist = ttree.query_nearest(mid_pts, max_distance=15, return_distance=True, all_matches=False)
imv_cls = np.zeros(NS, int)
for i, j in zip(ii, jj):
    if not footlike[i] and timv[j] > 0: imv_cls[i] = 3 if timv[j] >= p75 else 2 if timv[j] >= p50 else 1
Tseg = np.maximum.reduce([osm_cls, vel_cls, imv_cls])
log('nivel de tráfico de los tramos (longitud km por nivel):', {k: round(float(Ls[Tseg == k].sum()) / 1000) for k in range(4)})

# descanso cerca
def pts_(layer):
    out = [f['geometry']['coordinates'][:2] for f in LY[layer]['features'] if f.get('geometry') and f['geometry'].get('coordinates')]
    return np.array(out)
rest = {k: pts_(k) for k in ('bancos', 'fuentes', 'urinarios')}
rall = np.vstack(list(rest.values())); rx, ry = to_utm.transform(rall[:, 0], rall[:, 1])
near_rest = np.array([len(x) for x in cKDTree(np.c_[rx, ry]).query_ball_point(mid, r=np.maximum(20, defoff + 12))])

# ---------------- grafo contraído ----------------
adj = collections.defaultdict(list)
for i, s in enumerate(segs): adj[s[0]].append(i); adj[s[1]].append(i)
junction = {n for n, l in adj.items() if len(l) != 2}
used = np.zeros(NS, bool); links = []; seg_link = np.full(NS, -1)
def walk(start, si):
    path = [start]; cur = start; members = []
    while True:
        used[si] = True; members.append(si)
        u, v = segs[si][0], segs[si][1]; nxt = v if u == cur else u
        path.append(nxt); cur = nxt
        if cur in junction or cur == start: break
        cand = [j for j in adj[cur] if not used[j]]
        if not cand: break
        si = cand[0]
    return path, members
for j in junction:
    for si in adj[j]:
        if not used[si]: links.append(walk(j, si))
for si in range(NS):
    if not used[si]: links.append(walk(segs[si][0], si))
Gx = nx.Graph()
for p, m in links: Gx.add_edge(p[0], p[-1])
comp = max(nx.connected_components(Gx), key=len)
links = [(p, m) for p, m in links if p[0] in comp]
node_ids = sorted({p[0] for p, m in links} | {p[-1] for p, m in links}); nindex = {n: i for i, n in enumerate(node_ids)}
NL = len(links)
lk_len = np.zeros(NL); lk_sh = np.zeros((NL, NSC)); lk_T = np.zeros(NL, int); lk_rest = np.zeros(NL, int); lk_name = []
for k, (p, m) in enumerate(links):
    m = np.array(m); seg_link[m] = k; L_ = Ls[m]
    lk_len[k] = L_.sum(); lk_sh[k] = (seg_sh[m] * L_[:, None]).sum(0) / max(L_.sum(), 0.01)
    lk_T[k] = Tseg[m].max(); lk_rest[k] = near_rest[m].sum()
    nmc = collections.Counter(); [nmc.__setitem__(segs[i][3], nmc[segs[i][3]] + Ls[i]) for i in m]; lk_name.append(nmc.most_common(1)[0][0])
log('enlaces', NL, 'nodos', len(node_ids))

# nodos: cruces de vías con tráfico, semáforos
NUTM = np.array([utm[n] for n in node_ids])
deg = collections.Counter(); maxT_at = collections.defaultdict(int)
for k, (p, m) in enumerate(links):
    for n in (p[0], p[-1]): deg[nindex[n]] += 1; maxT_at[nindex[n]] = max(maxT_at[nindex[n]], int(lk_T[k]))
cross = json.load(open(RAW + 'osm_cross.json'))['elements']
sig_ll = np.array([[e['lon'], e['lat']] for e in cross if 'traffic_signals' in (e.get('tags', {}).get('highway', '') + e.get('tags', {}).get('crossing', ''))])
sx_, sy_ = to_utm.transform(sig_ll[:, 0], sig_ll[:, 1]); sig_kd = cKDTree(np.c_[sx_, sy_])
sig_near = np.array([len(x) > 0 for x in sig_kd.query_ball_point(NUTM, r=25)])
node_major = np.array([deg[i] >= 3 and maxT_at[i] >= 2 for i in range(len(node_ids))])
log('cruces con vías de tráfico', int(node_major.sum()), 'con semáforo', int((node_major & sig_near).sum()))

# atropellos: al nodo si está a <15 m de un cruce; si no, al tramo más cercano (<15 m)
atr = json.load(open(W + 'atropellos.json'))
AP = np.array([[a['x'], a['y']] for a in atr])
nkd = cKDTree(NUTM); dn, inn = nkd.query(AP)
bkd = cKDTree(base); db, ib = bkd.query(AP)
nacc = np.zeros(len(node_ids), int); lacc = np.zeros(NL, int); placed = 0
for q in range(len(AP)):
    if dn[q] <= 15: nacc[inn[q]] += 1; placed += 1
    elif db[q] <= 15 and seg_link[seg_idx[ib[q]]] >= 0: lacc[seg_link[seg_idx[ib[q]]]] += 1; placed += 1
log('atropellos asignados a la red', placed, 'de', len(AP))

# ---------------- salida: grafo ----------------
E6 = lambda v: int(round(v * 1e6))
gnodes = [[E6(nodes[n][1]), E6(nodes[n][0])] for n in node_ids]
names = sorted({n for n in lk_name if n}); nmi = {n: i + 1 for i, n in enumerate(names)}
glinks = []
for k, (p, m) in enumerate(links):
    geom = []; plat, plon = E6(nodes[p[0]][1]), E6(nodes[p[0]][0])
    for n in p[1:-1]:
        la, lo = E6(nodes[n][1]), E6(nodes[n][0]); geom += [la - plat, lo - plon]; plat, plon = la, lo
    glinks.append([nindex[p[0]], nindex[p[-1]], round(float(lk_len[k]), 1), int(lk_rest[k]), nmi.get(lk_name[k], 0), geom])
if not LIGHT: json.dump({'nodes': gnodes, 'links': glinks, 'names': [''] + names, 'hours': HOURS, 'dates': DAYNAMES,
           'sun': [[round(a), round(e)] for a, e in SUNS],
           'sh': [b64(np.round(lk_sh[:, h] * 100)) for h in range(NSC)],
           'traf': b64(lk_T), 'lacc': b64(np.minimum(lacc, 255)),
           'nflag': b64(node_major.astype(int) + 2 * sig_near.astype(int)), 'nacc': b64(np.minimum(nacc, 255))},
          open(OUT + 'graph.json', 'w'), separators=(',', ':'))

# ---------------- colegios ----------------
S_ = json.load(open(W + 'schools.geojson'))['features']
keep_re = re.compile(r"INFANTIL|PRIMÀRIA|SECUNDÀRIA|INSTITUT|EDUCACIÓ ESPECIAL|ESTRANGER")
V = json.load(open(W + 'vuln.geojson'))['features']
vpolys = [(f['properties']['nombre'], f['properties']['vul_global'], f['properties']['ind_global'], shape(f['geometry'])) for f in V if f.get('geometry')]
seg_kd = cKDTree(mid); pit_kd = cKDTree(pits[['x', 'y']].to_numpy()); atr_kd = cKDTree(AP)
HOT = [HOURS.index(h) for h in (13, 15, 17)]   # junio
schools = []
for f in S_:
    pr_ = f['properties']
    if pr_.get('municipio') != 'València' or not keep_re.search(pr_.get('dgenerica', '')): continue
    lon, lat = f['geometry']['coordinates'][:2]; x, y = to_utm.transform(lon, lat)
    ii = seg_kd.query_ball_point([x, y], r=250)
    if not ii: continue
    ii = np.array(ii); w_ = Ls[ii]
    shs = (seg_sh[ii] * w_[:, None]).sum(0) / w_.sum()
    pt = Point(lon, lat); vb = next(((n, v, iv) for n, v, iv, g in vpolys if g.contains(pt)), (None, None, None))
    bar = next((n for n, g in barrios if g.contains(pt)), None)
    schools.append({'n': pr_.get('dlibre'), 't': pr_.get('dgenerica'), 'reg': pr_.get('regimen'), 'lat': round(lat, 6), 'lon': round(lon, 6),
                    'sh': [[int(round(100 * v)) for v in shs[d * 6:(d + 1) * 6]] for d in range(len(DAYS))], 'shh': int(round(100 * shs[HOT].mean())),
                    'pits': len(pit_kd.query_ball_point([x, y], r=250)), 'atr': len(atr_kd.query_ball_point([x, y], r=250)),
                    'barrio': bar, 'vul': vb[1]})
q25 = float(np.percentile([s['shh'] for s in schools], 25))
for s in schools: s['prio'] = bool(s['shh'] <= q25 and s['vul'] in ('Vulnerabilidad Media', 'Vulnerabilidad Alta'))
log('colegios', len(schools), 'sombra en horas de calor (media)', round(np.mean([s['shh'] for s in schools]), 1), 'p25', q25, 'prioritarios', sum(s['prio'] for s in schools))

# caminos escolares
camins = []
for ci, nm in enumerate(cam_names):
    sel = cam_owner == ci
    v3 = SC_[sel].reshape(-1, 3, len(HOURS)) if False else None
    camins.append({'n': nm, 'len': round(cam_len[ci]), 'lines': cam_lines[ci],
                   'sh': [[int(round(100 * float(SC_[sel, d * 6 + h].mean()))) for h in range(6)] for d in range(len(DAYS))]})
# (las tres desviaciones 0/±3 m se promedian; el trazado escolar va por la acera)

# ---------------- estadísticas ----------------
U = urban_seg
stats = {'arboles': int(len(t)), 'arboles_sombra': int(len(live)), 'alcorques': int(len(pits)),
         'bancos': int(len(rest['bancos'])), 'fuentes': int(len(rest['fuentes'])), 'urinarios': int(len(rest['urinarios'])),
         'km_urbano': round(float(Ls[U].sum()) / 1000),
         'sombra_hora': [[int(round(100 * float((seg_sh[U, d * 6 + h] * Ls[U]).sum() / Ls[U].sum()))) for h in range(6)] for d in range(len(DAYS))],
         'sombra_edif_hora': [[int(round(100 * float((seg_bld[U, d * 6 + h] * Ls[U]).sum() / Ls[U].sum()))) for h in range(6)] for d in range(len(DAYS))],
         'sin_sombra_hora': [[int(round(100 * float(Ls[U & (seg_sh[:, d * 6 + h] < 0.1)].sum() / Ls[U].sum()))) for h in range(6)] for d in range(len(DAYS))],
         'atropellos': len(atr), 'atropellos_total': 1632, 'cruces_trafico': int(node_major.sum()), 'cruces_sin_semaforo': int((node_major & ~sig_near).sum())}
log('stats', stats)

if LIGHT:
    pass
px, py = pits.x.to_numpy(), pits.y.to_numpy(); plo, pla = to_wgs.transform(px, py)
alo, ala = to_wgs.transform(AP[:, 0], AP[:, 1])
may = []
for f in LY['mayores']['features']:
    p_ = f['properties']
    if p_.get('x') and p_.get('y') and re.search(r'MAYORES|MAJORS|CENTRO DE DÍA|RESIDENCIA|JUBILAD', p_.get('equipamien', ''), re.I):
        lo, la = to_wgs.transform(p_['x'], p_['y']); may.append({'n': p_.get('equipamien', '').title(), 'lat': round(la, 6), 'lon': round(lo, 6)})
ll = lambda a: [[round(p[1], 6), round(p[0], 6)] for p in a]
json.dump({'bancos': ll(rest['bancos']), 'fuentes': ll(rest['fuentes']), 'urinarios': ll(rest['urinarios']), 'mayores': may,
           'alcorques': [[round(a, 6), round(b, 6)] for a, b in zip(pla, plo)],
           'atropellos': [[round(a, 6), round(b, 6), atr[i]['g']] for i, (a, b) in enumerate(zip(ala, alo))],
           'pusdar': [[round(f['geometry']['coordinates'][1], 6), round(f['geometry']['coordinates'][0], 6), f['properties'].get('pusdar') or ''] for f in json.load(open(RAW + 'pusdar.geojson'))['features']]},
          open(OUT + 'pois.json', 'w'), separators=(',', ':'))
json.dump({'schools': [{k: v for k, v in s_.items()} for s_ in schools], 'school_ids': [s_['n'] for s_ in schools], 'prio_ids': [s_['n'] for s_ in schools if s_['prio']],
           'sombra_urb': stats['sombra_hora'], 'enlaces_sh': None} if False else {}, open('/dev/null', 'w'))
if LIGHT:
    json.dump({'shh': {s_['n'] + '|' + str(s_['lat']): s_['shh'] for s_ in schools}, 'prio': [s_['n'] + '|' + str(s_['lat']) for s_ in schools if s_['prio']],
               'sombra_urb': stats['sombra_hora'], 'sin_sombra': stats['sin_sombra_hora'], 'lk_sh13': np.round(lk_sh[:, 2] * 100).astype(int).tolist()},
              open(OUT + 'sens.json', 'w'))
    raise SystemExit(0)
json.dump({'schools': schools, 'camins': camins, 'q25': q25, 'hours': HOURS, 'dates': DAYNAMES, 'stats': stats}, open(OUT + 'schools.json', 'w'), separators=(',', ':'))
for f in sorted(os.listdir(OUT)): log(f, os.path.getsize(OUT + f) // 1024, 'KB')

# ---------------- callejero municipal para buscar por calle y número ----------------
er = shapefile.Reader(RAW + 'eixos/UrbanismoEInfraestructuras__223', encoding='utf-8')
cnames, cidx, csegs = [], {}, []
for shp_, rec in zip(er.shapes(), er.records()):
    d_ = rec.as_dict()
    if not shp_.points or not d_.get('nomcalle'): continue
    nm = ((d_.get('tipcalle') or '') + ' ' + d_['nomcalle']).strip()
    if nm not in cidx: cidx[nm] = len(cnames); cnames.append(nm)
    pts = np.array(shp_.points)[:shp_.parts[1] if len(shp_.parts) > 1 else None]
    lo_, la_ = to_wgs.transform(pts[:, 0], pts[:, 1])
    flat = []; pla_, plo_ = 0, 0
    for a_, b_ in zip(la_, lo_):
        A6, B6 = int(round(a_ * 1e6)), int(round(b_ * 1e6)); flat += [A6 - pla_, B6 - plo_]; pla_, plo_ = A6, B6
    rng = [int(v) if v else 0 for v in (d_['lf_add'], d_['lt_add'], d_['rf_add'], d_['rt_add'])]
    csegs.append([cidx[nm]] + rng + [flat])
json.dump({'names': cnames, 'segs': csegs}, open(OUT + 'calles.json', 'w'), separators=(',', ':'))
log('callejero', len(cnames), 'calles', len(csegs), 'tramos', os.path.getsize(OUT + 'calles.json') // 1024, 'KB')

# ---------------- simulador de plantación ----------------
# Un árbol en cada alcorque de calle vacío, ya crecido y en buen estado (factor 1), con el mismo modelo que el resto de
# árboles: copa circular desplazada en la dirección de la sombra según su altura. Dos escenarios: el árbol de calle más
# frecuente en el inventario (clases de copa y de altura más comunes) y un árbol de copa grande (copa y altura de 8 a 12 m).
CLS_R = {'0-4': 1.5, '4-8': 3.0, '8-12': 5.0, '>12': 6.5}; CLS_H = {'0-4': 3.0, '4-8': 6.0, '8-12': 10.0, '>12': 14.0}
sv = live[live.tipo == 'Viario']
c_mode, a_mode = sv.copa_c.mode()[0], sv.alt_c.mode()[0]
PX = pits[['x', 'y']].to_numpy()
all_kd = cKDTree(ALL)
pt_len2 = np.concatenate([(Ls / ns_)[seg_idx]] * 2)      # metros de acera que representa cada muestra
sch_ii = []                                              # tramos a menos de 250 m de cada colegio, en el mismo orden
for f in S_:
    pr_ = f['properties']
    if pr_.get('municipio') != 'València' or not keep_re.search(pr_.get('dgenerica', '')): continue
    lon, lat = f['geometry']['coordinates'][:2]; x, y = to_utm.transform(lon, lat)
    ii = seg_kd.query_ball_point([x, y], r=250)
    if ii: sch_ii.append(np.array(ii))
assert len(sch_ii) == len(schools)
def st_dec(ssh):   # sombra media y calles casi sin sombra, con un decimal (para comparar escenarios)
    return {'sombra_hora': [[round(100 * float((ssh[U, d * 6 + h] * Ls[U]).sum() / Ls[U].sum()), 1) for h in range(6)] for d in range(len(DAYS))],
            'sin_sombra_hora': [[round(100 * float(Ls[U & (ssh[:, d * 6 + h] < 0.1)].sum() / Ls[U].sum()), 1) for h in range(6)] for d in range(len(DAYS))]}
def plant(copa, alt):
    R_, H_ = CLS_R[copa] * CROWN_K, CLS_H[alt]
    sp = shade.copy(); pg = np.zeros(len(PX))
    for hi, (az, el) in enumerate(SUNS):
        tanE = math.tan(math.radians(el)); dsh = np.array([-math.sin(math.radians(az)), -math.cos(math.radians(az))])
        hits = [np.asarray(h_, dtype=np.int64) for h_ in all_kd.query_ball_point(PX + dsh[None, :] * (0.65 * H_ / tanE), r=R_)]
        if hi in HOT:                                    # 13, 15 y 17 h de junio: metros de acera que gana cada árbol
            for p, h_ in enumerate(hits):
                h_ = h_[h_ < 2 * nb]
                if len(h_): pg[p] += float(((1 - shade[h_, hi]) * pt_len2[h_]).sum())
        hits = [h_ for h_ in hits if len(h_)]
        if hits: sp[np.unique(np.concatenate(hits)), hi] = 1.0
    sl, sr, sc = sp[:nb], sp[nb:2 * nb], sp[2 * nb:]
    ssh = np.zeros((NS, NSC), np.float32)
    for hi in range(NSC):
        ssh[:, hi] = np.maximum(np.bincount(seg_idx, weights=sl[:, hi], minlength=NS) / cnt, np.bincount(seg_idx, weights=sr[:, hi], minlength=NS) / cnt)
    assert (ssh >= seg_sh - 1e-6).all()
    lsh = np.zeros((NL, NSC))
    for k, (p, m) in enumerate(links):
        m = np.array(m); L_ = Ls[m]; lsh[k] = (ssh[m] * L_[:, None]).sum(0) / max(L_.sum(), 0.01)
    e0 = np.round(lk_sh * 100).astype(np.uint8); e1 = np.round(lsh * 100).astype(np.uint8)
    chg = np.nonzero((e1 != e0).any(axis=1))[0].astype('<u4')
    stp = {'sombra_hora': [[int(round(100 * float((ssh[U, d * 6 + h] * Ls[U]).sum() / Ls[U].sum()))) for h in range(6)] for d in range(len(DAYS))],
           'sin_sombra_hora': [[int(round(100 * float(Ls[U & (ssh[:, d * 6 + h] < 0.1)].sum() / Ls[U].sum()))) for h in range(6)] for d in range(len(DAYS))]}
    s_sh, s_shh = [], []
    for k_, ii in enumerate(sch_ii):
        w_ = Ls[ii]; v0 = (seg_sh[ii] * w_[:, None]).sum(0) / w_.sum(); v1 = (ssh[ii] * w_[:, None]).sum(0) / w_.sum()
        assert int(round(100 * v0[HOT].mean())) == schools[k_]['shh']
        s_sh.append([int(round(100 * float(q))) for q in v1]); s_shh.append(int(round(100 * float(v1[HOT].mean()))))
    cam = [[int(round(100 * float(sc[cam_owner == ci, h].mean()))) for h in range(NSC)] for ci in range(len(cam_names))]
    gain = np.array(s_shh) - np.array([s_['shh'] for s_ in schools]); pm = pg / len(HOT)
    log(f'plantación copa {copa} altura {alt}: enlaces que cambian {len(chg)}; sombra 13 h junio {stats["sombra_hora"][0][2]} -> {stp["sombra_hora"][0][2]}; '
        f'sin sombra {stats["sin_sombra_hora"][0][2]} -> {stp["sin_sombra_hora"][0][2]}; colegios +{gain.mean():.2f} de media, máx +{gain.max()}; '
        f'acera ganada por árbol (13-17 h): mediana {np.median(pm):.1f} m, p75 {np.percentile(pm, 75):.1f} m, total {pm.sum() / 1000:.1f} km')
    return {'copa': copa, 'altura': alt, 'r': R_, 'h': H_, 'idx': base64.b64encode(chg.tobytes()).decode(), 'sh': [b64(e1[chg, hi]) for hi in range(NSC)],
            'stats': stp, 'stats1': st_dec(ssh), 'sc_sh': s_sh, 'sc_shh': s_shh, 'cam_sh': cam, 'pit': b64(np.minimum(np.round(pm), 255)), 'acera_km': round(float(pm.sum()) / 1000, 1)}
json.dump({'n': int(len(PX)), 'base1': st_dec(seg_sh), 'sc': [plant(c_mode, a_mode), plant('8-12', '8-12')]}, open(OUT + 'plant.json', 'w'), separators=(',', ':'))
log('plant.json', os.path.getsize(OUT + 'plant.json') // 1024, 'KB')
