"""Ruta fresca Madrid — sombra real por horas (edificios + árboles) y seguridad vial en las calles de Madrid.

Es el mismo cálculo que en València, adaptado a los datos abiertos de Madrid:
- Edificios del Catastro (INSPIRE, partes de edificio con número de plantas), ráster de alturas a 1 m.
- Árboles del inventario municipal (work/trees.pkl, de trees_madrid.py): copa estimada a partir del perímetro del tronco.
- Red peatonal de OpenStreetMap dentro del término municipal y de las zonas con edificios o arbolado.
- Seguridad: clase de vía y límite de velocidad (OSM), intensidad medida en los puntos de tráfico municipales
  (junio de 2026, días laborables de 8 a 20 h), cruces con semáforo (OSM) y atropellos de 2022 a 2025 (Policía Municipal).
- Las aceras dibujadas aparte en OSM heredan el nivel de tráfico de la calzada que tienen al lado.
Salidas (en RF_OUT, por defecto app/data/): index.json, t/<fila>_<columna>.json (red por cuadrículas), overview.json,
schools.json, calles.json y plant.json (simulador del plan de plantaciones 2025-2026).
Etapas con resultados intermedios en work/ (se recalculan si se borran o con RF_FORCE=1).
"""
import json, math, collections, base64, os, re, time, pickle, unicodedata, difflib
import numpy as np, pandas as pd, shapefile
from PIL import Image, ImageDraw
from pyproj import Transformer
from scipy.spatial import cKDTree
import shapely
from shapely.geometry import shape, Point, LineString
from shapely.ops import unary_union
from shapely import STRtree
import networkx as nx

t0 = time.time()
def log(*a): print(f'[{time.time() - t0:7.1f}s]', *a, flush=True)
W, RAW = 'work/', 'raw/'
OUT = os.environ.get('RF_OUT', 'app/data/')
FORCE = bool(os.environ.get('RF_FORCE'))
os.makedirs(OUT + 't', exist_ok=True)
to_utm = Transformer.from_crs(4326, 25830, always_xy=True)
to_wgs = Transformer.from_crs(25830, 4326, always_xy=True)
HOURS = [9, 11, 13, 15, 17, 19]
DAYS = [(2026, 6, 15), (2026, 9, 15)]
DAYNAMES = ['15 de junio', '15 de septiembre']
FLOOR_H = float(os.environ.get('RF_FLOOR_H', 3.0)); GROUND_X = float(os.environ.get('RF_GROUND_X', 1.0))
CROWN_K = float(os.environ.get('RF_CROWN_K', 1.0)); WALL_OFF = float(os.environ.get('RF_WALL_OFF', 1.5))
LAT0, LON0 = 40.4168, -3.7038
b64 = lambda a: base64.b64encode(np.asarray(a, np.uint8).tobytes()).decode()
HOT = [2, 3, 4]                                   # 13, 15 y 17 h del 15 de junio


def sun(hour_local, day):
    """Acimut (grados desde el norte, sentido horario) y elevación del sol en Madrid (Astronomical Almanac, baja precisión)."""
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

def norm(s):
    """Mayúsculas sin tildes ni signos, para comparar nombres de calles."""
    s = unicodedata.normalize('NFKD', str(s)).encode('ascii', 'ignore').decode().upper()
    return re.sub(r'[^A-Z0-9 ]+', ' ', s).split()

# ---------------- municipio, distritos y barrios (ETRS89 UTM 30N) ----------------
br = shapefile.Reader(RAW + 'barrios/BARRIOS', encoding='utf-8')
barrios = []
for shp_, rec in zip(br.shapes(), br.records()):
    d_ = rec.as_dict()
    barrios.append({'cod': int(d_['COD_BAR']), 'nombre': d_['NOMBRE'].strip(), 'dis': int(d_['CODDIS']), 'dnom': d_['NOMDIS'].strip(),
                    'g': shape(shp_.__geo_interface__).buffer(0)})
muni = unary_union([b['g'] for b in barrios]); shapely.prepare(muni)
DIS = {}
for b in barrios: DIS.setdefault(b['dis'], {'nombre': b['dnom'], 'gs': []})['gs'].append(b['g'])
for k, v in DIS.items(): v['g'] = unary_union(v['gs']); shapely.prepare(v['g'])
bar_tree = STRtree([b['g'] for b in barrios])
def barrio_of(x, y):
    for j in bar_tree.query(Point(x, y)):
        if barrios[j]['g'].contains(Point(x, y)): return barrios[j]
    return None
log('barrios', len(barrios), 'distritos', len(DIS))

# ---------------- árboles ----------------
TREES = pd.read_pickle(W + 'trees.pkl')
TX = TREES[['x', 'y']].to_numpy(); TR = TREES.r.to_numpy() * CROWN_K; TF = TREES.f.to_numpy(); THC = 0.65 * TREES.h.to_numpy()
RMAX = float(TR.max())
log('árboles con sombra', len(TREES), 'radio de copa máximo', RMAX)

# ---------------- etapa 1: red peatonal, ráster de edificios y muestras sobre las aceras ----------------
WALK = {'footway', 'residential', 'service', 'cycleway', 'pedestrian', 'tertiary', 'tertiary_link', 'primary', 'primary_link', 'secondary',
        'secondary_link', 'track', 'unclassified', 'steps', 'path', 'trunk', 'trunk_link', 'living_street'}
OFF = {'primary': 9, 'primary_link': 6, 'secondary': 8, 'secondary_link': 6, 'tertiary': 7, 'tertiary_link': 5, 'residential': 5,
       'unclassified': 5, 'service': 3, 'trunk': 10, 'trunk_link': 6, 'living_street': 3, 'pedestrian': 4}
OSMCLS = {'trunk': 3, 'trunk_link': 3, 'primary': 3, 'primary_link': 3, 'secondary': 2, 'secondary_link': 2, 'tertiary': 1, 'tertiary_link': 1}
NET = W + 'net.pkl'
if FORCE or not os.path.exists(NET):
    osm = json.load(open(W + 'osm.json'))['elements']
    nodes = {e['id']: (e['lon'], e['lat']) for e in osm if e['type'] == 'node'}
    ways = [e for e in osm if e['type'] == 'way']
    del osm
    nid = np.array(list(nodes.keys())); nll = np.array([nodes[i] for i in nid])
    ux, uy = to_utm.transform(nll[:, 0], nll[:, 1]); utm = {i: (x, y) for i, x, y in zip(nid.tolist(), ux, uy)}
    segs = []   # (nodo a, nodo b, desplazamiento por defecto de la acera, nombre, highway, id de la vía, acera dibujada aparte, velocidad, cubierto)
    for w in ways:
        tg = w.get('tags', {}); hw = tg.get('highway'); foot = tg.get('foot'); acc = tg.get('access')
        if hw not in WALK: continue
        if foot == 'no': continue
        if acc in ('private', 'no') and foot not in ('yes', 'designated', 'permissive'): continue
        if hw in ('trunk', 'trunk_link') and foot not in ('yes', 'designated'): continue
        if hw == 'service' and tg.get('service') in ('parking_aisle', 'drive-through'): continue
        if tg.get('indoor') == 'yes' or tg.get('level', '0').startswith('-'): continue
        ms = re.match(r'\d+', tg.get('maxspeed', '')); ms = int(ms.group()) if ms else 0
        cov = tg.get('tunnel') in ('yes', 'building_passage') or tg.get('covered') == 'yes'
        side = hw == 'footway' and tg.get('footway') == 'sidewalk'
        nds = [n for n in w['nodes'] if n in utm]
        for a, b in zip(nds[:-1], nds[1:]):
            if a != b: segs.append((a, b, OFF.get(hw, 0), tg.get('name', ''), hw, w['id'], side, ms, cov))
    A = np.array([utm[s[0]] for s in segs]); B = np.array([utm[s[1]] for s in segs]); M_ = (A + B) / 2
    keep = shapely.contains_xy(muni, M_[:, 0], M_[:, 1])
    log('segmentos OSM caminables', len(segs), 'dentro del término municipal', int(keep.sum()))
    # zonas con edificios o arbolado: a menos de 250 m de un edificio o a menos de 30 m de un árbol del inventario
    BZ = np.load(W + 'buildings.npz')
    xy = BZ['xy']; ro = BZ['ring_off']; rp = BZ['ring_part']; rh = BZ['ring_hole']
    ext = np.nonzero(~rh)[0]
    cx = np.add.reduceat(xy[:, 0], ro[:-1])[ext] / np.diff(ro)[ext]; cy = np.add.reduceat(xy[:, 1], ro[:-1])[ext] / np.diff(ro)[ext]
    bkd = cKDTree(np.c_[cx, cy]); tkd = cKDTree(TX)
    db, _ = bkd.query(M_, distance_upper_bound=250); dt, _ = tkd.query(M_, distance_upper_bound=30)
    built = np.isfinite(db) | np.isfinite(dt)
    keep &= built
    log('segmentos en zonas con edificios o arbolado', int(keep.sum()))
    segs = [s for s, k in zip(segs, keep) if k]
    used_nodes = {s[0] for s in segs} | {s[1] for s in segs}
    nodes = {n: nodes[n] for n in used_nodes}; utm = {n: utm[n] for n in used_nodes}
    pickle.dump({'segs': segs, 'nodes': nodes, 'utm': utm}, open(NET, 'wb'))
    del ways, BZ, xy
else:
    d_ = pickle.load(open(NET, 'rb')); segs, nodes, utm = d_['segs'], d_['nodes'], d_['utm']
NS = len(segs)
A = np.array([utm[s[0]] for s in segs]); B = np.array([utm[s[1]] for s in segs])
D = B - A; Ls = np.hypot(D[:, 0], D[:, 1]); Ls[Ls == 0] = 0.01
N = np.stack([-D[:, 1] / Ls, D[:, 0] / Ls], axis=1)
defoff = np.array([s[2] for s in segs], float)
footlike = defoff == 0
sidewalk = np.array([s[6] for s in segs]); covered = np.array([s[8] for s in segs])
log('segmentos', NS, 'km', round(float(Ls.sum()) / 1000), 'aceras dibujadas aparte', int(sidewalk.sum()), 'cubiertos', int(covered.sum()))

# ---------------- ráster de alturas a 1 m ----------------
RES = 1.0
allxy = np.vstack([A, B])
X0, X1 = allxy[:, 0].min() - 450, allxy[:, 0].max() + 450
Y0, Y1 = allxy[:, 1].min() - 450, allxy[:, 1].max() + 450
NC, NR = int(math.ceil((X1 - X0) / RES)), int(math.ceil((Y1 - Y0) / RES))
GFILE = W + f'raster_{int(FLOOR_H * 10)}_{int(GROUND_X * 10)}.npy'
if FORCE or not os.path.exists(GFILE):
    G = np.lib.format.open_memmap(GFILE + '.tmp', mode='w+', dtype=np.uint8, shape=(NR, NC))
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
    G.flush(); del G, BZ, XY
    os.replace(GFILE + '.tmp', GFILE)
G = np.load(GFILE, mmap_mode='r')
G = np.ascontiguousarray(G)
HMAX = int(G.max())
log('ráster de edificios', G.shape, 'altura máx', HMAX, 'm')

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
del Nn, dflt
urban_seg = np.bincount(seg_idx, weights=(wall[0] | wall[1]).astype(float), minlength=NS) / np.bincount(seg_idx, minlength=NS) >= 0.5
nb = len(base)
log('muestras', nb, 'tramos urbanos (con fachadas)', int(urban_seg.sum()))

# ---------------- etapa 2: sombra por hora ----------------
ALL = np.vstack([side_pts[0], side_pts[1]])
NA = len(ALL)
SFILE = W + f'shade_{int(FLOOR_H * 10)}_{int(GROUND_X * 10)}_{int(CROWN_K * 100)}_{int(WALL_OFF * 10)}.npz'
if FORCE or not os.path.exists(SFILE):
    pr, pc = pix(ALL)
    inside = G[pr, pc] > 0
    shade = np.zeros((NA, NSC), np.uint8)       # 0-100
    bld_only = np.zeros((NA, NSC), bool)
    for hi, (az, el) in enumerate(SUNS):
        tanE = math.tan(math.radians(el)); sx, sy = math.sin(math.radians(az)), -math.cos(math.radians(az))
        sh = inside.copy(); last = None
        todo = np.nonzero(~sh)[0]
        for tt in range(1, int(min(450, HMAX / tanE)) + 1):
            oc, orr = int(round(tt * sx / RES)), int(round(tt * sy / RES))
            if (orr, oc) == last: continue
            last = (orr, oc)
            if tt % 16 == 0: todo = todo[~sh[todo]]
            if len(todo) == 0: break
            rr = np.clip(pr[todo] + orr, 0, NR - 1); cc = np.clip(pc[todo] + oc, 0, NC - 1)
            sh[todo[G[rr, cc] > tt * tanE]] = True
        bld_only[:, hi] = sh
        dsh = np.array([-math.sin(math.radians(az)), -math.cos(math.radians(az))])
        kd = cKDTree(TX + dsh[None, :] * (THC / tanE)[:, None])
        tree = np.zeros(NA, np.float32)
        for c0 in range(0, NA, 500_000):
            d, idx = kd.query(ALL[c0:c0 + 500_000], k=8, distance_upper_bound=RMAX)
            valid = idx < len(TX); idx2 = np.where(valid, idx, 0)
            tree[c0:c0 + 500_000] = np.where(valid & (d <= TR[idx2]), TF[idx2], 0.0).max(axis=1)
        shade[:, hi] = np.round(100 * np.maximum(sh.astype(np.float32), tree)).astype(np.uint8)
        log(f'{DAYNAMES[hi // 6]} {HOURS[hi % 6]} h: sol a {el:.0f}°, sombra de edificios en {sh.mean() * 100:.0f} % de las muestras, de árboles {np.mean(tree > 0) * 100:.0f} %')
    np.savez(SFILE, shade=shade, bld=bld_only)
else:
    Z = np.load(SFILE); shade, bld_only = Z['shade'], Z['bld']
shade = shade.astype(np.float32) / 100
cov2 = np.concatenate([covered[seg_idx]] * 2)
shade[cov2] = 1.0; bld_only[cov2] = True                 # pasos cubiertos y túneles peatonales
del G

SL, SRt = shade[:nb], shade[nb:]
cnt = np.bincount(seg_idx, minlength=NS).astype(float)
seg_sh = np.zeros((NS, NSC), np.float32); seg_bld = np.zeros((NS, NSC), np.float32)
for hi in range(NSC):
    ml = np.bincount(seg_idx, weights=SL[:, hi], minlength=NS) / cnt
    mr = np.bincount(seg_idx, weights=SRt[:, hi], minlength=NS) / cnt
    seg_sh[:, hi] = np.maximum(ml, mr)
    bl = np.bincount(seg_idx, weights=bld_only[:nb, hi], minlength=NS) / cnt
    br_ = np.bincount(seg_idx, weights=bld_only[nb:, hi], minlength=NS) / cnt
    seg_bld[:, hi] = np.maximum(bl, br_)
LIGHT = bool(os.environ.get('RF_LIGHT'))

# ---------------- seguridad por segmento ----------------
HWS = [s[4] for s in segs]
osm_cls = np.array([0 if footlike[i] else OSMCLS.get(HWS[i], 0) for i in range(NS)])
vel_cls = np.array([2 if (not footlike[i] and segs[i][7] >= 40) else 0 for i in range(NS)])
mid = (A + B) / 2
road = ~footlike & np.isin(np.array(HWS), ['residential', 'tertiary', 'tertiary_link', 'secondary', 'secondary_link', 'primary', 'primary_link',
                                            'trunk', 'trunk_link', 'unclassified', 'living_street', 'service'])
road_i = np.nonzero(road)[0]
TP = [p for p in json.load(open(W + 'trafico_puntos.json')) if p['t'] == 'URB']
TPx = np.array([[p['x'], p['y']] for p in TP]); TPv = np.array([p['imh'] for p in TP])
p50, p75 = np.percentile(TPv, 50), np.percentile(TPv, 75)
rgeo = [LineString([A[i], B[i]]) for i in road_i]; rtree = STRtree(rgeo)
(ii, jj), dist = rtree.query_nearest([Point(*p) for p in TPx], max_distance=20, return_distance=True, all_matches=False)
way_lvl = collections.defaultdict(int)
for i, j in zip(ii, jj):
    lv = 3 if TPv[i] >= p75 else 2 if TPv[i] >= p50 else 1
    wid = segs[road_i[j]][5]; way_lvl[wid] = max(way_lvl[wid], lv)
imv_cls = np.array([way_lvl.get(s[5], 0) if road[k] else 0 for k, s in enumerate(segs)])
log('puntos de tráfico urbanos', len(TP), 'asignados a una calle', len(ii), 'vías con intensidad medida', len(way_lvl), 'p50/p75 veh/h', round(p50), round(p75))
Troad = np.maximum.reduce([osm_cls, vel_cls, imv_cls]); Troad[footlike] = 0
# aceras dibujadas aparte: el nivel de la calzada más cercana (a menos de 15 m)
Tseg = Troad.copy()
sw_i = np.nonzero(sidewalk)[0]
(ii, jj), dist = rtree.query_nearest([Point(*p) for p in mid[sw_i]], max_distance=15, return_distance=True, all_matches=False)
Tseg[sw_i[ii]] = Troad[road_i[jj]]
log('nivel de tráfico de los tramos (km por nivel):', {k: round(float(Ls[Tseg == k].sum()) / 1000) for k in range(4)},
    'aceras con el nivel de su calzada', int((Tseg[sw_i] > 0).sum()))

# descanso cerca: bancos, fuentes de beber y aseos públicos
def csv_pts(f, enc, xc, yc, filt=None):
    d_ = pd.read_csv(f, sep=';', encoding=enc, dtype=str)
    if filt is not None: d_ = d_[filt(d_)]
    x = pd.to_numeric(d_[xc].str.replace(',', '.'), errors='coerce'); y = pd.to_numeric(d_[yc].str.replace(',', '.'), errors='coerce')
    P_ = np.c_[x, y]; P_ = P_[np.isfinite(P_).all(1)]
    return P_[shapely.contains_xy(muni, P_[:, 0], P_[:, 1])]
rest = {'bancos': csv_pts(RAW + 'ayto2/bancos_2026.csv', 'utf-8-sig', 'COORD_GIS_X', 'COORD_GIS_Y', lambda d_: d_.ESTADO == 'OPERATIVO'),
        'fuentes': csv_pts(RAW + 'ayto2/fuentes_2026.csv', 'utf-8-sig', 'COORD_GIS_X', 'COORD_GIS_Y',
                           lambda d_: (d_.ESTADO == 'OPERATIVO') & d_.USO.fillna('PERSONAS').str.startswith('PERSONAS')),
        'aseos': csv_pts(RAW + 'ayto2/aseos.csv', 'utf-8-sig', 'COORD UTM ETRS89 X', 'COORD UTM ETRS89 Y')}
log('bancos', len(rest['bancos']), 'fuentes', len(rest['fuentes']), 'aseos', len(rest['aseos']))
rall = np.vstack(list(rest.values()))
near_rest = np.array([len(x) for x in cKDTree(rall).query_ball_point(mid, r=np.maximum(20, defoff + 12))])

# ---------------- grafo contraído ----------------
adj = collections.defaultdict(list)
for i, s in enumerate(segs): adj[s[0]].append(i); adj[s[1]].append(i)
junction = {n for n, l in adj.items() if len(l) != 2}
used = np.zeros(NS, bool); links = []
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
# cuadrículas de 0,02 grados de latitud por 0,025 de longitud (unos 2,2 x 2,1 km): cada enlace va a la de su punto medio
TLAT, TLON = 0.02, 0.025
LATMIN, LONMIN = 40.30, -3.90
def tile_of(lat, lon): return int((lat - LATMIN) // TLAT), int((lon - LONMIN) // TLON)
lk_tile = []
for p, m in links:
    q = p[len(p) // 2]; lk_tile.append(tile_of(nodes[q][1], nodes[q][0]))
order = sorted(range(len(links)), key=lambda k: lk_tile[k])
links = [links[k] for k in order]; lk_tile = [lk_tile[k] for k in order]
NL = len(links)
node_ids = sorted({p[0] for p, m in links} | {p[-1] for p, m in links}); nindex = {n: i for i, n in enumerate(node_ids)}
seg_link = np.full(NS, -1)
lk_len = np.zeros(NL); lk_sh = np.zeros((NL, NSC)); lk_bld = np.zeros((NL, NSC)); lk_T = np.zeros(NL, int); lk_Tr = np.zeros(NL, int)
lk_rest = np.zeros(NL, int); lk_name = []
for k, (p, m) in enumerate(links):
    m = np.array(m); seg_link[m] = k; L_ = Ls[m]
    lk_len[k] = L_.sum(); w_ = max(L_.sum(), 0.01)
    lk_sh[k] = (seg_sh[m] * L_[:, None]).sum(0) / w_; lk_bld[k] = (seg_bld[m] * L_[:, None]).sum(0) / w_
    lk_T[k] = Tseg[m].max(); lk_Tr[k] = Troad[m].max(); lk_rest[k] = near_rest[m].sum()
    nmc = collections.Counter()
    for i in m: nmc[segs[i][3]] += Ls[i]
    lk_name.append(nmc.most_common(1)[0][0])
log('enlaces', NL, 'nodos', len(node_ids), 'km en la red', round(lk_len.sum() / 1000))

# nodos: cruces de vías con tráfico (solo calzadas), semáforos
NUTM = np.array([utm[n] for n in node_ids])
deg = collections.Counter(); maxT_at = collections.defaultdict(int)
for k, (p, m) in enumerate(links):
    for n in (p[0], p[-1]): deg[nindex[n]] += 1; maxT_at[nindex[n]] = max(maxT_at[nindex[n]], int(lk_Tr[k]))
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

# ---------------- estadísticas de la ciudad y de cada distrito (tramos urbanos, ponderadas por longitud) ----------------
U = urban_seg
def shstats(sel, ssh=seg_sh, dec=0):
    r_ = (lambda v: round(v, 1)) if dec else (lambda v: int(round(v)))
    w_ = Ls[sel].sum()
    return {'sombra_hora': [[r_(100 * float((ssh[sel, d * 6 + h] * Ls[sel]).sum() / w_)) for h in range(6)] for d in range(len(DAYS))],
            'sin_sombra_hora': [[r_(100 * float(Ls[sel & (ssh[:, d * 6 + h] < 0.1)].sum() / w_)) for h in range(6)] for d in range(len(DAYS))]}
stats = {'arboles': int(len(TREES)), 'bancos': int(len(rest['bancos'])), 'fuentes': int(len(rest['fuentes'])), 'aseos': int(len(rest['aseos'])),
         'km_urbano': round(float(Ls[U].sum()) / 1000), **shstats(U),
         'sombra_edif_hora': [[int(round(100 * float((seg_bld[U, d * 6 + h] * Ls[U]).sum() / Ls[U].sum()))) for h in range(6)] for d in range(len(DAYS))],
         'atropellos': len(atr), 'atropellos_red': placed, 'cruces_trafico': int(node_major.sum()), 'cruces_sin_semaforo': int((node_major & ~sig_near).sum())}
seg_dis = np.zeros(NS, int)
for k, v in DIS.items(): seg_dis[shapely.contains_xy(v['g'], mid[:, 0], mid[:, 1])] = k
dstats = []
for k in sorted(DIS):
    sel = U & (seg_dis == k)
    if sel.sum() == 0: continue
    bx = DIS[k]['g'].bounds; lo0, la0 = to_wgs.transform(bx[0], bx[1]); lo1, la1 = to_wgs.transform(bx[2], bx[3])
    dstats.append({'cod': k, 'n': DIS[k]['nombre'], 'km': round(float(Ls[sel].sum()) / 1000), 'bb': [round(la0, 5), round(lo0, 5), round(la1, 5), round(lo1, 5)], **shstats(sel)})
log('stats', {k: v for k, v in stats.items() if not isinstance(v, list)}, 'sombra 13 h junio', stats['sombra_hora'][0][2], 'de edificios', stats['sombra_edif_hora'][0][2])

# ---------------- colegios ----------------
TIPOS = {'ColegiosPublicos': ('Colegio público', 'Público'), 'ColegiosPrivadosConcertados': ('Colegio concertado o privado', 'Concertado o privado'),
         'InstitutosEnseñanzaSecundaria': ('Instituto', 'Público'), 'EscuelasInfantilesPublicas': ('Escuela infantil pública', 'Público'),
         'EscuelasInfantilesPrivadasGuarderias': ('Escuela infantil privada', 'Privado'),
         'CentrosPublicosEducacionEspecial': ('Educación especial', 'Público'), 'CentrosPrivadosConcertadosEducacionEspecial': ('Educación especial', 'Concertado o privado')}
CE = pd.read_csv(RAW + 'ayto2/centros_educativos.csv', sep=';', encoding='cp1252', dtype=str)
CE['k'] = CE.TIPO.str.split('/').str[-1]
CE = CE[CE.k.isin(TIPOS)].copy()
CE['lat'] = pd.to_numeric(CE.LATITUD, errors='coerce'); CE['lon'] = pd.to_numeric(CE.LONGITUD, errors='coerce')
CE = CE.dropna(subset=['lat', 'lon']).drop_duplicates(subset=['NOMBRE', 'lat', 'lon'])
IG = pd.read_excel(RAW + 'ayto2/iguala_informe_globales.xlsx', sheet_name='Descriptivos barrios')
yI = int(IG['Fecha datos'].max()); IG = IG[IG['Fecha datos'] == yI]
renta = dict(zip(IG['Código barrio'].astype(int), IG['Renta neta media por hogar']))
renta_med = float(np.median(list(renta.values())))
IV = pd.read_excel(RAW + 'ayto2/iguala_informe_globales.xlsx', sheet_name='Vul. esferas distritos')
yV = int(IV['Fecha datos'].max()); IV = IV[IV['Fecha datos'] == yV]
ivta = dict(zip(IV['Codigo distrito'].astype(int), IV['Indice de Vulnerabilidad Territorial Agregado']))
ivta_med = float(IV['Indice de Vulnerabilidad Territorial Agregado - media ciudad'].iloc[0])
seg_kd = cKDTree(mid); atr_kd = cKDTree(AP)
schools, sch_ii = [], []
for r_ in CE.itertuples():
    x, y = to_utm.transform(r_.lon, r_.lat)
    if not muni.contains(Point(x, y)): continue
    ii = np.array(seg_kd.query_ball_point([x, y], r=250))
    if not len(ii): continue
    w_ = Ls[ii]; shs = (seg_sh[ii] * w_[:, None]).sum(0) / w_.sum()
    bq = barrio_of(x, y)
    rn = renta.get(bq['cod']) if bq else None
    nm = re.sub(r'\s+', ' ', str(r_.NOMBRE)).strip()
    schools.append({'n': nm, 't': TIPOS[r_.k][0], 'reg': TIPOS[r_.k][1], 'lat': round(r_.lat, 6), 'lon': round(r_.lon, 6),
                    'sh': [[int(round(100 * v)) for v in shs[d * 6:(d + 1) * 6]] for d in range(len(DAYS))], 'shh': int(round(100 * shs[HOT].mean())),
                    'atr': len(atr_kd.query_ball_point([x, y], r=250)), 'barrio': bq['nombre'] if bq else None, 'dis': bq['dnom'] if bq else None,
                    'renta': int(round(rn)) if rn else None, 'rbaja': bool(rn is not None and rn < renta_med),
                    'ivta': round(float(ivta[bq['dis']]), 2) if bq else None})
    sch_ii.append(ii)
q25 = float(np.percentile([s['shh'] for s in schools], 25))
for s in schools: s['prio'] = bool(s['shh'] <= q25 and s['rbaja'])
log('colegios', len(schools), 'sombra en horas de calor (media)', round(np.mean([s['shh'] for s in schools]), 1), 'p25', q25,
    'prioritarios', sum(s['prio'] for s in schools), f'(renta {yI}: mediana de los barrios {renta_med:.0f} €)')

# centros de mayores
CM = pd.read_csv(RAW + 'ayto2/centros_mayores.csv', sep=';', encoding='cp1252', dtype=str)
may = []
for r_ in CM.itertuples():
    la, lo = pd.to_numeric(r_.LATITUD, errors='coerce'), pd.to_numeric(r_.LONGITUD, errors='coerce')
    if not (np.isfinite(la) and np.isfinite(lo)): continue
    nm = re.sub(r'\s+', ' ', str(r_.NOMBRE)).strip()
    nm = re.sub(r'^Centro (Municipal )?de Mayores\s*', 'Centro de mayores ', nm)
    may.append({'n': nm, 'lat': round(float(la), 6), 'lon': round(float(lo), 6)})

# ---------------- simulador: plan de plantaciones 2025-2026 (arbolado viario) ----------------
# El plan da, para cada calle de cada distrito, la especie y el número de árboles, pero no el sitio exacto. Cada árbol se pone en el
# punto de su calle donde más acera sombrearía de 13 a 17 h en junio, a 8 m como mínimo de los otros árboles nuevos de la calle y en la
# línea de los alcorques (2 m más cerca de la calzada que la línea donde se mide la sombra), ya crecido: con la copa y la altura que
# tiene uno de cada cuatro árboles de calle de hoja ancha de Madrid (el percentil 75 del inventario), sea cual sea su especie, porque
# muchas especies del plan son nuevas en las calles y en el inventario solo hay ejemplares jóvenes. Escenario 2: el mismo número de
# árboles en las calles a menos de 250 m de los colegios prioritarios, repartidos a partes iguales entre ellos.
# Las zonas verdes del plan no se simulan (el plan no da su sitio).
PL = pd.read_csv(RAW + 'ayto2/plan_plantaciones_2025-2026.csv', sep=';', encoding='utf-8-sig', dtype=str)
PL.columns = ['dist', 'dnom', 'loc', 'tipo', 'esp', 'uds']
PL['uds'] = pd.to_numeric(PL.uds, errors='coerce').fillna(0).astype(int); PL['dist'] = pd.to_numeric(PL.dist, errors='coerce')
n_zv = int(PL[PL.tipo.str.strip() == 'ZV'].uds.sum())
PL = PL[PL.tipo.str.strip() == 'AV']
fix = lambda s: re.sub(r'(?<=[a-záéíóúñ])AV|AV(?=[a-záéíóúñ])', 'au', str(s).replace('\xa0', ' '))   # "AVstralis", "AVñón": una sustitución errónea en el fichero
PL['loc'] = PL['loc'].map(fix); PL['esp'] = PL['esp'].map(fix)
def sp_name(s):
    s = re.sub(r"^[A-Z]{2,4} [^()]*\(([^)]+)\)$", r'\1', s.strip())               # "MEA Melia (Melia azedarach)" -> "Melia azedarach"
    s = re.sub(r"'[^']*'", '', s).replace(' x ', ' X ')
    return ' '.join(s.upper().split()[:2]).replace('HYBRIDA', 'HISPANICA')
street_sz = TREES[TREES.NUM_PARQUE.isna()].copy(); street_sz['sp2'] = street_sz.ESPECIE.str.upper().str.split().str[:2].str.join(' ')
street_sz['gen'] = street_sz.ESPECIE.str.upper().str.split().str[0]
SPQ = street_sz.groupby('sp2')[['r', 'h']].median(); GNQ = street_sz.groupby('gen')[['r', 'h']].median(); ALLQ = street_sz[['r', 'h']].median()
SPN, GNN = street_sz.sp2.value_counts(), street_sz.gen.value_counts()
_sz = {}
def size_of(sp):
    if sp in _sz: return _sz[sp]
    s2 = sp_name(sp); g = s2.split()[0] if s2 else ''
    out = (float(ALLQ.r), float(ALLQ.h))
    for tab, cnt_, key in ((SPQ, SPN, s2), (GNQ, GNN, g)):
        if key in tab.index and cnt_.get(key, 0) >= 20:
            out = (float(tab.loc[key, 'r']), float(tab.loc[key, 'h'])); break
    _sz[sp] = out
    return out
TYPEW = {'CALLE', 'AVENIDA', 'PLAZA', 'PASEO', 'GLORIETA', 'CAMINO', 'CARRERA', 'CARRETERA', 'RONDA', 'TRAVESIA', 'COSTANILLA', 'CUESTA',
         'PASAJE', 'BULEVAR', 'PLAZUELA', 'VIA', 'SENDA', 'PARQUE', 'CALLEJON', 'AUTOVIA', 'PISTA', 'ACCESO', 'POLIGONO', 'COLONIA', 'JARDIN', 'VADO'}
PART = {'DE', 'DEL', 'LA', 'LAS', 'LOS', 'EL', 'Y', 'D'}
def core(words): return ' '.join(w for w in words if w not in TYPEW and w not in PART)
seg_core = collections.defaultdict(list)
for i, s in enumerate(segs):
    if s[3] and not footlike[i]: seg_core[(seg_dis[i], core(norm(s[3])))].append(i)
cores_by_dis = collections.defaultdict(list); dis_by_core = collections.defaultdict(set)
for (dk, c) in seg_core: cores_by_dis[dk].append(c); dis_by_core[c].add(dk)
def find_street(dk, name):
    c = core(norm(re.sub(r'\([^)]*\)', ' ', name)))
    for c2 in (c, c.replace('AV', 'AU')):
        if (dk, c2) in seg_core: return (dk, c2)
        if len(dis_by_core.get(c2, ())) == 1: return (next(iter(dis_by_core[c2])), c2)
    m_ = difflib.get_close_matches(c, cores_by_dis[dk], n=1, cutoff=0.85)
    return (dk, m_[0]) if m_ else None
pt_len = np.concatenate([(Ls / ns_)[seg_idx]] * 2)          # metros de acera que representa cada muestra
s_start = np.concatenate([[0], np.cumsum(ns_)[:-1]])
def samples_of(si):
    q = np.concatenate([np.arange(s_start[i], s_start[i] + ns_[i]) for i in si]) if len(si) else np.zeros(0, int)
    q = np.concatenate([q, q + nb]); return q[wall2[q]]
wall2 = np.concatenate([wall[0], wall[1]])
offv = np.vstack([side_pts[0] - base, side_pts[1] - base]); offl = np.hypot(offv[:, 0], offv[:, 1])
TRUNK = np.vstack([base, base]) + offv * np.where(offl > 1.0, np.maximum(1.0, offl - 2.0) / np.maximum(offl, 1e-6), 1.0)[:, None]
del offv
all_kd = cKDTree(ALL)
SUNH = [(math.tan(math.radians(e)), np.array([-math.sin(math.radians(a)), -math.cos(math.radians(a))])) for a, e in SUNS]
def gain_at(P, R, H):
    """Metros de acera que pasan a la sombra (media de las 13, 15 y 17 h de junio) con un árbol en cada punto de P, por separado."""
    g = np.zeros(len(P))
    if not len(P): return g
    for hi in HOT:
        tanE, dsh = SUNH[hi]
        for p, h_ in enumerate(all_kd.query_ball_point(P + dsh[None, :] * (0.65 * H / tanE)[:, None], r=R)):
            if h_: h_ = np.asarray(h_); g[p] += float(((1 - shade[h_, hi]) * pt_len[h_]).sum())
    return g / len(HOT)
def place(cands, n, R, H, taken, gap=8.0):
    """Los n puntos de cands con más ganancia, separados al menos gap m entre sí y de taken (rejilla de celdas de gap m)."""
    cands = cands[::2]
    if not len(cands) or n <= 0: return []
    g = gain_at(TRUNK[cands], np.full(len(cands), R), np.full(len(cands), H))
    out = []
    for q in cands[np.argsort(-g, kind='stable')]:
        P_ = TRUNK[q]; cx, cy = int(P_[0] // gap), int(P_[1] // gap)
        if any(np.hypot(*(P_ - T_)) < gap for a_ in (-1, 0, 1) for b_ in (-1, 0, 1) for T_ in taken.get((cx + a_, cy + b_), ())): continue
        taken.setdefault((cx, cy), []).append(P_); out.append(q)
        if len(out) >= n: break
    return out
FR = street_sz[street_sz.tipo == 'FRONDOSA']
R0, H0 = float(FR.r.quantile(0.75)) * CROWN_K, float(FR.h.quantile(0.75))
log('árbol simulado: radio de copa', round(R0, 2), 'm, altura', round(H0, 1), 'm')
plan_trees, unmatched = [], []
taken1 = collections.defaultdict(dict)
for r_ in PL.itertuples():
    key = find_street(int(r_.dist), r_.loc.split(',')[0])
    if key is None: unmatched.append((r_.dnom, r_.loc, r_.uds)); continue
    got = place(samples_of(seg_core[key]), r_.uds, R0, H0, taken1[key])
    if len(got) < r_.uds: unmatched.append((r_.dnom, r_.loc, r_.uds - len(got)))
    for q in got: plan_trees.append({'p': TRUNK[q], 'r': R0, 'h': H0, 'esp': r_.esp.strip(), 'calle': r_.loc.strip()})
n_plan = int(PL.uds.sum())
log('plan de plantaciones (árboles de calle):', n_plan, 'colocados', len(plan_trees), 'sin calle o sin sitio', sum(u[2] for u in unmatched),
    'filas', len(unmatched), '| zonas verdes', n_zv)
prio_i = [k for k, s_ in enumerate(schools) if s_['prio']]
sch_xy = np.array([to_utm.transform(s_['lon'], s_['lat']) for s_ in schools])
PXP = np.array([t_['p'] for t_ in plan_trees])
dprio, _ = cKDTree(sch_xy[prio_i]).query(PXP)
near_prio = int((dprio <= 250).sum())
log('árboles del plan a menos de 250 m de un colegio prioritario:', near_prio, f'({100 * near_prio / len(plan_trees):.1f} %)')
# escenario 2: el mismo número de árboles, repartido entre los colegios prioritarios
alt_trees = []; taken2 = {}
per = [len(plan_trees) // len(prio_i) + (1 if k < len(plan_trees) % len(prio_i) else 0) for k in range(len(prio_i))]
for k, si_ in enumerate(sorted(prio_i, key=lambda k_: schools[k_]['shh'])):
    for q in place(samples_of(sch_ii[si_]), per[k], R0, H0, taken2):
        alt_trees.append({'p': TRUNK[q], 'r': R0, 'h': H0})
log('escenario 2: árboles colocados junto a colegios prioritarios', len(alt_trees), 'de', len(plan_trees))
def plant(trees, label):
    PX = np.array([t_['p'] for t_ in trees]); R_ = np.array([t_['r'] for t_ in trees]); H_ = np.array([t_['h'] for t_ in trees])
    sp = shade.copy(); pg = np.zeros(len(PX))
    for hi in range(NSC):
        tanE, dsh = SUNH[hi]
        hits = [np.asarray(h_, dtype=np.int64) for h_ in all_kd.query_ball_point(PX + dsh[None, :] * (0.65 * H_ / tanE)[:, None], r=R_)]
        if hi in HOT:
            for p, h_ in enumerate(hits):
                if len(h_): pg[p] += float(((1 - shade[h_, hi]) * pt_len[h_]).sum())
        hits = [h_ for h_ in hits if len(h_)]
        if hits: sp[np.unique(np.concatenate(hits)), hi] = 1.0
    sl, sr = sp[:nb], sp[nb:]
    ssh = np.zeros((NS, NSC), np.float32)
    for hi in range(NSC):
        ssh[:, hi] = np.maximum(np.bincount(seg_idx, weights=sl[:, hi], minlength=NS) / cnt, np.bincount(seg_idx, weights=sr[:, hi], minlength=NS) / cnt)
    assert (ssh >= seg_sh - 1e-6).all()
    lsh = np.zeros((NL, NSC))
    for k, (p, m) in enumerate(links):
        m = np.array(m); L_ = Ls[m]; lsh[k] = (ssh[m] * L_[:, None]).sum(0) / max(L_.sum(), 0.01)
    e0 = np.round(lk_sh * 100).astype(np.uint8); e1 = np.round(lsh * 100).astype(np.uint8)
    chg = np.nonzero((e1 != e0).any(axis=1))[0].astype('<u4')
    s_sh, s_shh = [], []
    for k_, ii in enumerate(sch_ii):
        w_ = Ls[ii]; v0 = (seg_sh[ii] * w_[:, None]).sum(0) / w_.sum(); v1 = (ssh[ii] * w_[:, None]).sum(0) / w_.sum()
        assert int(round(100 * v0[HOT].mean())) == schools[k_]['shh']
        s_sh.append([int(round(100 * float(v))) for v in v1]); s_shh.append(int(round(100 * float(v1[HOT].mean()))))
    gain = np.array(s_shh) - np.array([s_['shh'] for s_ in schools]); pm = pg / len(HOT)
    ntr = [len(x) for x in cKDTree(PX).query_ball_point(sch_xy, r=250)]
    st1 = shstats(U, ssh, 1); st0 = shstats(U, ssh)
    pr_gain = gain[prio_i]
    log(f'{label}: árboles {len(PX)}, enlaces que cambian {len(chg)}; sombra 13 h junio {shstats(U, seg_sh, 1)["sombra_hora"][0][2]} -> {st1["sombra_hora"][0][2]}; '
        f'colegios prioritarios +{pr_gain.mean():.1f} de media (máx +{pr_gain.max()}); todos +{gain.mean():.2f}; '
        f'acera ganada (13-17 h): mediana {np.median(pm):.1f} m por árbol, total {pm.sum() / 1000:.1f} km')
    tw = [to_wgs.transform(*p) for p in PX]
    return {'trees': [[round(la, 6), round(lo, 6)] for lo, la in tw], 'idx': base64.b64encode(chg.tobytes()).decode(),
            'sh': [b64(e1[chg, hi]) for hi in range(NSC)], 'stats': st0, 'stats1': st1, 'sc_sh': s_sh, 'sc_shh': s_shh, 'ntr': ntr,
            'pit': b64(np.minimum(np.round(pm), 255)), 'acera_km': round(float(pm.sum()) / 1000, 1),
            'prio_gain': round(float(pr_gain.mean()), 1), 'r_med': round(float(np.median(R_)), 1), 'h_med': round(float(np.median(H_)), 1)}
if not LIGHT:
    json.dump({'n_plan': n_plan, 'n': len(plan_trees), 'n_fuera': int(sum(u[2] for u in unmatched)), 'n_zv': n_zv, 'near_prio': near_prio,
               'n_prio': len(prio_i), 'base1': shstats(U, seg_sh, 1),
               'esp': [t_['esp'] for t_ in plan_trees], 'calle': [t_['calle'] for t_ in plan_trees],
               'sc': [plant(plan_trees, 'plan 2025-2026'), plant(alt_trees, 'mismos árboles junto a colegios prioritarios')]},
              open(OUT + 'plant.json', 'w'), separators=(',', ':'), ensure_ascii=False)
    log('plant.json', os.path.getsize(OUT + 'plant.json') // 1024, 'KB')

if LIGHT:
    json.dump({'shh': {s_['n'] + '|' + str(s_['lat']): s_['shh'] for s_ in schools}, 'prio': [s_['n'] + '|' + str(s_['lat']) for s_ in schools if s_['prio']],
               'sombra_urb': stats['sombra_hora'], 'sin_sombra': stats['sin_sombra_hora'], 'lk_sh13': np.round(lk_sh[:, 2] * 100).astype(int).tolist()},
              open(OUT + 'sens.json', 'w'))
    raise SystemExit(0)

# ---------------- salida: red por cuadrículas ----------------
# traf = nivel de tráfico que se soporta al caminar por el enlace (0-3; en las aceras dibujadas aparte, el de su calzada)
#        + 4 x nivel de la propia calzada (0-3; 0 en aceras y caminos), que es el que cuenta para saber si se cruza una calle
E6 = lambda v: int(round(v * 1e6))
def to_ll(v):
    if not len(v): return np.zeros((0, 2))
    lo, la = to_wgs.transform(v[:, 0], v[:, 1]); return np.column_stack((la, lo))
rest_ll = {k: to_ll(v) for k, v in rest.items()}
alo, ala = to_wgs.transform(AP[:, 0], AP[:, 1])
def pts_in_tile(ll, key):
    if not len(ll): return []
    ti = ((ll[:, 0] - LATMIN) // TLAT).astype(int); tj = ((ll[:, 1] - LONMIN) // TLON).astype(int)
    sel = (ti == key[0]) & (tj == key[1])
    return [[E6(a), E6(b)] for a, b in ll[sel]]
atr_ll = np.c_[ala, alo]
tiles = []
k0 = 0
while k0 < NL:
    key = lk_tile[k0]; k1 = k0
    while k1 < NL and lk_tile[k1] == key: k1 += 1
    tn = sorted({links[k][0][0] for k in range(k0, k1)} | {links[k][0][-1] for k in range(k0, k1)}, key=lambda n: nindex[n])
    names = sorted({lk_name[k] for k in range(k0, k1) if lk_name[k]}); nmi = {n: i + 1 for i, n in enumerate(names)}
    glinks = []
    for k in range(k0, k1):
        p, m = links[k]; geom = []; plat, plon = E6(nodes[p[0]][1]), E6(nodes[p[0]][0])
        for n in p[1:-1]:
            la, lo = E6(nodes[n][1]), E6(nodes[n][0]); geom += [la - plat, lo - plon]; plat, plon = la, lo
        glinks.append([nindex[p[0]], nindex[p[-1]], round(float(lk_len[k]), 1), int(lk_rest[k]), nmi.get(lk_name[k], 0), geom])
    ni = np.array([nindex[n] for n in tn])
    tj_ = {'k0': k0, 'nodes': [[int(nindex[n]), E6(nodes[n][1]), E6(nodes[n][0])] for n in tn], 'links': glinks, 'names': [''] + names,
           'sh': [b64(np.round(lk_sh[k0:k1, h] * 100)) for h in range(NSC)], 'traf': b64(lk_T[k0:k1] + 4 * lk_Tr[k0:k1]), 'lacc': b64(np.minimum(lacc[k0:k1], 255)),
           'nflag': b64(node_major[ni].astype(int) + 2 * sig_near[ni].astype(int)), 'nacc': b64(np.minimum(nacc[ni], 255)),
           'bancos': pts_in_tile(rest_ll['bancos'], key)}
    fn = f'{key[0]}_{key[1]}.json'
    json.dump(tj_, open(OUT + 't/' + fn, 'w'), separators=(',', ':'), ensure_ascii=False)
    tiles.append([key[0], key[1], k0, k1 - k0, os.path.getsize(OUT + 't/' + fn) // 1024])
    k0 = k1
log('cuadrículas', len(tiles), 'tamaño total', sum(t_[4] for t_ in tiles) // 1024, 'MB; mayor', max(t_[4] for t_ in tiles), 'KB')

# vista general: celdas de unos 250 m con la sombra media (ponderada por longitud) de sus tramos urbanos
CLAT, CLON = 0.00225, 0.003
mlo, mla = to_wgs.transform(mid[:, 0], mid[:, 1])
ci = ((mla - LATMIN) // CLAT).astype(int); cj = ((mlo - LONMIN) // CLON).astype(int)
cells = collections.defaultdict(list)
for i in np.nonzero(U & (seg_link >= 0))[0]: cells[(ci[i], cj[i])].append(i)
ov = {'clat': CLAT, 'clon': CLON, 'lat0': LATMIN, 'lon0': LONMIN, 'cells': []}
for (a, b), ii in sorted(cells.items()):
    ii = np.array(ii); w_ = Ls[ii]
    if w_.sum() < 60: continue
    ov['cells'].append([int(a), int(b), *[int(round(100 * float((seg_sh[ii, h] * w_).sum() / w_.sum()))) for h in range(NSC)]])
json.dump(ov, open(OUT + 'overview.json', 'w'), separators=(',', ':'))
log('vista general', len(ov['cells']), 'celdas', os.path.getsize(OUT + 'overview.json') // 1024, 'KB')

json.dump({'atropellos': [[round(float(atr_ll[q, 0]), 6), round(float(atr_ll[q, 1]), 6), atr[q]['g'], atr[q]['m'], atr[q]['v']] for q in range(len(atr))],
           'fuentes': [[round(float(a), 6), round(float(b), 6)] for a, b in rest_ll['fuentes']], 'aseos': [[round(float(a), 6), round(float(b), 6)] for a, b in rest_ll['aseos']]},
          open(OUT + 'pois.json', 'w'), separators=(',', ':'))
json.dump({'tiles': tiles, 'tlat': TLAT, 'tlon': TLON, 'lat0': LATMIN, 'lon0': LONMIN, 'nn': len(node_ids), 'nl': NL,
           'hours': HOURS, 'dates': DAYNAMES, 'sun': [[round(a), round(e)] for a, e in SUNS]}, open(OUT + 'index.json', 'w'), separators=(',', ':'))
json.dump({'schools': schools, 'q25': q25, 'hours': HOURS, 'dates': DAYNAMES, 'stats': stats, 'dstats': dstats, 'mayores': may,
           'renta_med': round(renta_med), 'renta_year': yI, 'ivta_year': yV, 'ivta_med': round(ivta_med, 2),
           'plan': {'n_plan': n_plan, 'n': len(plan_trees), 'n_zv': n_zv, 'near_prio': near_prio, 'n_prio': len(prio_i)},
           **({'demo': json.load(open(W + 'demo.json'))} if os.path.exists(W + 'demo.json') else {}),
           'ivta': {DIS[k]['nombre']: round(float(v), 2) for k, v in ivta.items() if k in DIS}},
          open(OUT + 'schools.json', 'w'), separators=(',', ':'), ensure_ascii=False)
for f in ('index.json', 'schools.json', 'overview.json', 'pois.json'): log(f, os.path.getsize(OUT + f) // 1024, 'KB')

# ---------------- callejero municipal para buscar por calle y número ----------------
CA = pd.read_csv(RAW + 'ayto2/callejero_direcciones.csv', sep=';', encoding='cp1252', dtype=str)
CA = CA[CA.CLASE_APP.str.strip() == 'NUMERO'].copy()
CA['num'] = pd.to_numeric(CA.NUMERO, errors='coerce')
for c in ('UTMX_ETRS', 'UTMY_ETRS'): CA[c] = pd.to_numeric(CA[c].str.replace(',', '.'), errors='coerce')
CA = CA.dropna(subset=['num', 'UTMX_ETRS', 'UTMY_ETRS'])
lo_, la_ = to_wgs.transform(CA.UTMX_ETRS.to_numpy(), CA.UTMY_ETRS.to_numpy())
CA['la'] = np.round(la_ * 1e6).astype(int); CA['lo'] = np.round(lo_ * 1e6).astype(int)
LOWER = {'DE', 'DEL', 'LA', 'LAS', 'LOS', 'EL', 'Y', 'E', 'A', 'EN', 'AL', 'O', 'U', 'CON', 'SAN'}
def nice_words(t, first=True):
    out = []
    for k, w in enumerate(t.split()):
        if re.fullmatch(r'M{0,3}(CM|CD|D?C{0,3})(XC|XL|L?X{0,3})(IX|IV|V?I{0,3})', w) and w not in ('MI', 'DI', 'LI', 'CI', 'DIL', 'MIL', 'C', 'D', 'M', 'L'): out.append(w)
        elif w in LOWER and w != 'SAN' and (k > 0 or not first): out.append(w.lower())
        else: out.append(w[:1] + w[1:].lower())
    return ' '.join(out)
def full_name(r_):
    cl = str(r_.VIA_CLASE).strip().capitalize(); pa = str(r_.VIA_PAR).strip().lower() if isinstance(r_.VIA_PAR, str) else ''
    return ' '.join(x for x in (cl, pa, nice_words(str(r_.VIA_NOMBRE_ACENTOS).strip(), first=False)) if x and x != 'nan')
first_ = CA.drop_duplicates('COD_VIA').set_index('COD_VIA')
DNAME = {k: v['nombre'] for k, v in DIS.items()}
fname = {cod: full_name(r_) for cod, r_ in zip(first_.index, first_.itertuples())}
dup = collections.Counter(fname.values())
cnames, cstreets = [], []
for cod, g in CA.sort_values(['COD_VIA', 'num']).groupby('COD_VIA', sort=False):
    nm = fname[cod]
    if dup[nm] > 1:                                      # calles con el mismo nombre en distritos distintos
        dk = int(pd.to_numeric(g.DISTRITO, errors='coerce').mode().iloc[0]); nm = f'{nm} ({DNAME.get(dk, dk)})'
    g = g.drop_duplicates('num')
    nums = g.num.astype(int).tolist(); la, lo = g.la.to_numpy(), g.lo.to_numpy()
    flat = [int(la[0]), int(lo[0])] + np.c_[np.diff(la), np.diff(lo)].ravel().astype(int).tolist()
    cnames.append(nm); cstreets.append([np.diff([0] + nums).tolist(), flat])
json.dump({'names': cnames, 'streets': cstreets}, open(OUT + 'calles.json', 'w'), separators=(',', ':'), ensure_ascii=False)
log('callejero', len(cnames), 'calles', len(CA), 'portales', os.path.getsize(OUT + 'calles.json') // 1024, 'KB')
