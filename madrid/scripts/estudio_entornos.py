"""Estudio de los entornos escolares de Madrid: sombra, renta, seguridad vial y plan de plantaciones 2025-2026.

Lee la web ya calculada (app/data: colegios, cuadrículas de la red y simulación del plan), los barrios municipales y el plan de
plantaciones, y escribe work/estudio.json con todas las cifras y tablas del estudio, y work/estudio_mapa.png.
Entorno escolar = los tramos de acera a menos de 250 m del centro (en línea recta). Horas de calor = 13, 15 y 17 h del 15 de junio.
Uso, desde la carpeta de Madrid:  python3 -I scripts/estudio_entornos.py
"""
import base64, collections, glob, json, os, re, sys
import numpy as np, pandas as pd, shapefile
from pyproj import Transformer
from scipy.spatial import cKDTree
from scipy.stats import spearmanr
from shapely.geometry import shape as shp_shape, Point
from shapely.ops import unary_union
import shapely

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
D = f'{ROOT}/app/data/'; RAW = f'{ROOT}/raw/'; W = f'{ROOT}/work/'
to_utm = Transformer.from_crs('EPSG:4326', 'EPSG:25830', always_xy=True)
S = json.load(open(D + 'schools.json'))
SC = S['schools']; q25 = S['q25']
P = json.load(open(D + 'plant.json'))
dec = lambda s: np.frombuffer(base64.b64decode(s), dtype=np.uint8)

xy = np.array([to_utm.transform(s['lon'], s['lat']) for s in SC])
shh = np.array([s['shh'] for s in SC], float)
atr = np.array([s['atr'] for s in SC], float)
ren = np.array([s['renta'] if s['renta'] else np.nan for s in SC], float)
prio = np.array([s['prio'] for s in SC]); rbaja = np.array([s['rbaja'] for s in SC])
R = {}

def pct(a, q): return float(np.percentile(a, q))
def med(a): return float(np.median(a)) if len(a) else None

# ---------- 1. sombra en los entornos escolares ----------
R['n'] = len(SC); R['q25'] = q25
R['shh'] = {'media': round(float(shh.mean()), 1), 'mediana': med(shh), 'p10': pct(shh, 10), 'p25': pct(shh, 25), 'p75': pct(shh, 75),
            'p90': pct(shh, 90), 'min': float(shh.min()), 'max': float(shh.max()),
            'n_menos_20': int((shh < 20).sum()), 'n_menos_25': int((shh < 25).sum()), 'n_mas_60': int((shh >= 60).sum())}
# a qué hora: sombra media de los entornos a cada hora, junio y septiembre
R['por_hora'] = [[round(float(np.mean([s['sh'][d][h] for s in SC])), 1) for h in range(6)] for d in range(2)]
by = lambda key: collections.defaultdict(list)
tipos = collections.defaultdict(list)
for s in SC: tipos[s['t']].append(s['shh'])
R['tipos'] = sorted([{'t': k, 'n': len(v), 'mediana': med(v), 'p25': pct(v, 25), 'p75': pct(v, 75)} for k, v in tipos.items()], key=lambda r: -r['n'])
regs = collections.defaultdict(list)
for s in SC: regs[s['reg']].append(s['shh'])
R['regimen'] = [{'reg': k, 'n': len(v), 'mediana': med(v)} for k, v in regs.items()]
dis = collections.defaultdict(list)
for k, s in enumerate(SC): dis[s['dis']].append(k)
IV = S['ivta']
drows = []
for d, ks in dis.items():
    v = shh[ks]
    drows.append({'dis': d, 'n': len(ks), 'mediana': med(v), 'p25': pct(v, 25), 'p75': pct(v, 75), 'prio': int(prio[ks].sum()),
                  'bajo_q25': int((v <= q25).sum()), 'atr_med': med(atr[ks]), 'ivta': IV.get(d)})
drows.sort(key=lambda r: -r['mediana'])
R['distritos'] = drows

# ---------- 2. sombra y renta ----------
ok = ~np.isnan(ren)
rho, pv = spearmanr(shh[ok], ren[ok]); R['rho_sombra_renta'] = {'rho': round(float(rho), 3), 'p': float(pv), 'n': int(ok.sum())}
qs = np.percentile(ren[ok], [20, 40, 60, 80])
quint = np.full(len(SC), -1); quint[ok] = np.searchsorted(qs, ren[ok], side='right')
qrows = []
for q in range(5):
    m = quint == q; v = shh[m]
    lo_ = float(ren[m].min()); hi_ = float(ren[m].max())
    qrows.append({'q': q + 1, 'n': int(m.sum()), 'renta_min': round(lo_), 'renta_max': round(hi_), 'mediana': med(v),
                  'bajo_q25': int((v <= q25).sum()), 'pct_bajo_q25': round(100 * float((v <= q25).mean()), 1)})
R['quintiles_renta'] = qrows
R['bajo_q25_rbaja'] = {'n_rbaja': int(rbaja.sum()), 'bajo_q25_rbaja': int((rbaja & (shh <= q25)).sum()),
                       'n_ralta': int((~rbaja & ok).sum()), 'bajo_q25_ralta': int((~rbaja & ok & (shh <= q25)).sum())}
dd = [r for r in drows if r['ivta'] is not None]
rd, pd_ = spearmanr([r['mediana'] for r in dd], [r['ivta'] for r in dd])
R['rho_distrito_ivta'] = {'rho': round(float(rd), 3), 'p': float(pd_), 'n': len(dd)}

# ---------- 3. seguridad vial ----------
nodes, flags = [], []
for f in sorted(glob.glob(D + 't/*.json')):
    J = json.load(open(f)); nf = dec(J['nflag'])
    for q, (g, la, lo) in enumerate(J['nodes']): nodes.append((g, la / 1e6, lo / 1e6)); flags.append(int(nf[q]))
nodes = {g: (la, lo, fl) for (g, la, lo), fl in zip(nodes, flags)}
NX = np.array([to_utm.transform(lo, la) for la, lo, fl in nodes.values()]); NF = np.array([fl for la, lo, fl in nodes.values()])
major = (NF & 1) > 0; sig = (NF & 2) > 0
kd_ns = cKDTree(NX[major & ~sig]); kd_s = cKDTree(NX[major & sig])
cr_ns = np.array([len(x) for x in kd_ns.query_ball_point(xy, r=250)], float)
cr_s = np.array([len(x) for x in kd_s.query_ball_point(xy, r=250)], float)
R['cruces_red'] = {'major': int(major.sum()), 'sin_semaforo': int((major & ~sig).sum())}
R['atr'] = {'total_en_entornos': None, 'media': round(float(atr.mean()), 1), 'mediana': med(atr), 'p75': pct(atr, 75), 'p90': pct(atr, 90), 'max': float(atr.max()),
            'n_cero': int((atr == 0).sum()), 'n_10_o_mas': int((atr >= 10).sum())}
A = json.load(open(W + 'atropellos.json')); AP = np.array([[a['x'], a['y']] for a in A])
inside = np.zeros(len(AP), bool)
for x in cKDTree(xy).query_ball_point(AP, r=250): pass
dmin, _ = cKDTree(xy).query(AP); inside = dmin <= 250
R['atr']['total_en_entornos'] = int(inside.sum()); R['atr']['total'] = len(AP); R['atr']['pct_en_entornos'] = round(100 * float(inside.mean()), 1)
R['cruces'] = {'media_sin_sem': round(float(cr_ns.mean()), 1), 'mediana_sin_sem': med(cr_ns), 'p75_sin_sem': pct(cr_ns, 75),
               'n_cero_sin_sem': int((cr_ns == 0).sum()), 'media_con_sem': round(float(cr_s.mean()), 1)}
rs, ps = spearmanr(shh, atr); R['rho_sombra_atr'] = {'rho': round(float(rs), 3), 'p': float(ps)}
atr75 = pct(atr, 75)
doble = (shh <= q25) & (atr >= atr75)
R['doble'] = {'atr_p75': atr75, 'n': int(doble.sum()), 'n_y_rbaja': int((doble & rbaja).sum()),
              'por_distrito': collections.Counter(SC[k]['dis'] for k in np.nonzero(doble & rbaja)[0]).most_common()}

# ---------- 4. plan de plantaciones ----------
PL = pd.read_csv(RAW + 'ayto2/plan_plantaciones_2025-2026.csv', sep=';', encoding='utf-8-sig', dtype=str)
PL.columns = ['dist', 'dnom', 'loc', 'tipo', 'esp', 'uds']
PL['uds'] = pd.to_numeric(PL.uds, errors='coerce').fillna(0).astype(int); PL['tipo'] = PL.tipo.str.strip(); PL['dnom'] = PL.dnom.str.strip()
r_ = shapefile.Reader(RAW + 'barrios/BARRIOS')
dpoly = collections.defaultdict(list); dname = {}
for sr, rec in zip(r_.shapes(), r_.records()):
    dpoly[int(rec[0])].append(shp_shape(sr.__geo_interface__)); dname[int(rec[0])] = rec[1]
DG = {k: unary_union(v) for k, v in dpoly.items()}
def district_of(pts):
    out = np.zeros(len(pts), int)
    for k, g in DG.items(): out[shapely.contains_xy(g, pts[:, 0], pts[:, 1])] = k
    return out
TR = [np.array([to_utm.transform(lo, la) for la, lo in sc['trees']]) for sc in P['sc']]
tdis = [district_of(t) for t in TR]
sdis_code = {dname[k]: k for k in dname}
prio_xy = xy[prio]
near = [cKDTree(prio_xy).query(t)[0] <= 250 for t in TR]
gain = [np.array(sc['sc_shh'], float) - shh for sc in P['sc']]
R['plan'] = {'n_av': int(PL[PL.tipo == 'AV'].uds.sum()), 'n_zv': int(PL[PL.tipo == 'ZV'].uds.sum()), 'n_colocados': len(TR[0]), 'n_alt': len(TR[1]),
             'calles_av': int(PL[PL.tipo == 'AV'].shape[0]), 'near_prio': int(near[0].sum()), 'near_prio_pct': round(100 * float(near[0].mean()), 1),
             'acera_km': [P['sc'][0]['acera_km'], P['sc'][1]['acera_km']],
             'gain_prio_media': [round(float(g[prio].mean()), 1) for g in gain], 'gain_prio_max': [float(g[prio].max()) for g in gain],
             'gain_todos_media': [round(float(g.mean()), 2) for g in gain],
             'prio_gain_ge5': [int((g[prio] >= 5).sum()) for g in gain], 'prio_gain_ge1': [int((g[prio] >= 1).sum()) for g in gain],
             'prio_salen_q25': [int(((shh[prio] + g[prio]) > q25).sum()) for g in gain],
             'sombra13_ciudad': [P['base1']['sombra_hora'][0][2], P['sc'][0]['stats1']['sombra_hora'][0][2], P['sc'][1]['stats1']['sombra_hora'][0][2]]}
# por distrito: árboles del plan (viario), colocados, colegios prioritarios, árboles cerca de ellos
import unicodedata
nrm = lambda t: re.sub(r'\s*-\s*', '-', unicodedata.normalize('NFKD', t).encode('ascii', 'ignore').decode().lower().strip())
av = PL[PL.tipo == 'AV'].groupby('dnom').uds.sum().to_dict(); zv = PL[PL.tipo == 'ZV'].groupby('dnom').uds.sum().to_dict()
av = {nrm(k): v for k, v in av.items()}; zv = {nrm(k): v for k, v in zv.items()}
pdrows = []
n_prio_tot = int(prio.sum()); n_tr = len(TR[0])
for k in sorted(DG):
    nm = dname[k]
    sk = [i for i, s in enumerate(SC) if s['dis'] == nm]
    np_ = int(prio[sk].sum()) if sk else 0
    placed = int((tdis[0] == k).sum())
    pdrows.append({'dis': nm, 'av_plan': int(av.get(nrm(nm), 0)), 'zv_plan': int(zv.get(nrm(nm), 0)),
                   'colocados': placed, 'pct_arboles': round(100 * placed / n_tr, 1), 'prio': np_, 'pct_prio': round(100 * np_ / n_prio_tot, 1),
                   'near_prio': int(((tdis[0] == k) & near[0]).sum()), 'colegios': len(sk),
                   'gain_prio_plan': round(float(gain[0][sk][prio[sk]].mean()), 1) if np_ else None})
R['plan_distritos'] = pdrows
assert sum(r['av_plan'] for r in pdrows) == R['plan']['n_av'], 'nombres de distrito del plan sin casar'
sin_prio = [r for r in pdrows if r['prio'] == 0]
R['plan_sin_prio'] = {'distritos': [r['dis'] for r in sin_prio], 'colocados': sum(r['colocados'] for r in sin_prio),
                      'pct': round(100 * sum(r['colocados'] for r in sin_prio) / n_tr, 1)}
# barrios con más entornos escolares en el cuarto con menos sombra
bq = collections.defaultdict(list)
for k, s in enumerate(SC): bq[(s['dis'], s['barrio'])].append(k)
R['barrios_poca_sombra'] = sorted([{'dis': d, 'barrio': b, 'n': len(ks), 'bajo_q25': int((shh[ks] <= q25).sum()), 'mediana': med(shh[ks]),
                                    'renta': SC[ks[0]]['renta']} for (d, b), ks in bq.items()], key=lambda r: -r['bajo_q25'])[:12]
# colegios con poca sombra y muchos atropellos a la vez
R['doble_lista'] = sorted([{'n': SC[k]['n'], 'dis': SC[k]['dis'], 'barrio': SC[k]['barrio'], 'shh': int(shh[k]), 'atr': int(atr[k]), 'cruces_ss': int(cr_ns[k]),
                            'rbaja': bool(rbaja[k])} for k in np.nonzero(doble)[0]], key=lambda r: -r['atr'])
R['prio_vs_resto'] = {'atr_med_prio': med(atr[prio]), 'atr_med_resto': med(atr[~prio]), 'cr_med_prio': med(cr_ns[prio]), 'cr_med_resto': med(cr_ns[~prio])}
# nombres de distrito del plan que no casan con los del mapa
R['plan_nombres'] = sorted(set(av) | set(zv))
# ---------- 5. prioridades: colegios prioritarios donde un árbol daría más sombra ----------
ntr2 = np.array(P['sc'][1]['ntr'])
top = sorted(np.nonzero(prio)[0], key=lambda k: -gain[1][k])
R['top'] = [{'n': SC[k]['n'], 't': SC[k]['t'], 'dis': SC[k]['dis'], 'barrio': SC[k]['barrio'], 'shh': int(shh[k]), 'despues': int(shh[k] + gain[1][k]),
             'gain': int(gain[1][k]), 'gain_plan': int(gain[0][k]), 'atr': int(atr[k]), 'cruces_ss': int(cr_ns[k]), 'renta': SC[k]['renta'], 'ntr': int(ntr2[k])}
            for k in top[:20]]
R['prio_gain2_dist'] = {'media': round(float(gain[1][prio].mean()), 1), 'mediana': med(gain[1][prio]), 'p25': pct(gain[1][prio], 25), 'p75': pct(gain[1][prio], 75)}
R['prio_lista'] = [{'n': SC[k]['n'], 'dis': SC[k]['dis'], 'barrio': SC[k]['barrio'], 'shh': int(shh[k]), 'atr': int(atr[k]), 'cruces_ss': int(cr_ns[k]),
                    'g_plan': int(gain[0][k]), 'g_alt': int(gain[1][k])} for k in np.nonzero(prio)[0]]
json.dump(R, open(W + 'estudio.json', 'w'), ensure_ascii=False, indent=1)

# ---------- mapa: árboles de calle del plan y colegios prioritarios ----------
import matplotlib; matplotlib.use('Agg'); import matplotlib.pyplot as plt; import matplotlib.patheffects as pe
fig, ax = plt.subplots(figsize=(9, 9), dpi=180)
for k, g in DG.items():
    for poly in getattr(g, 'geoms', [g]):
        x_, y_ = poly.exterior.xy; ax.fill(x_, y_, facecolor='#f4f4f2', edgecolor='#9a9a96', linewidth=0.5, zorder=1)
ax.scatter(TR[0][:, 0], TR[0][:, 1], s=1.2, c='#6b6b68', linewidths=0, zorder=2, label=f'Árboles de calle del plan 2025-2026 ({len(TR[0]):,})'.replace(',', '.'))
for x_, y_ in prio_xy: ax.add_patch(plt.Circle((x_, y_), 250, facecolor='#1f5fbf', alpha=0.18, edgecolor='none', zorder=3))
ax.scatter(prio_xy[:, 0], prio_xy[:, 1], s=9, c='#1f5fbf', linewidths=0, zorder=4, label=f'Centros prioritarios ({n_prio_tot}) y 250 m alrededor')
ax.set_aspect('equal'); ax.axis('off')
allp = np.vstack([TR[0], xy]); minx, miny = allp.min(0); maxx, maxy = allp.max(0)
ax.set_xlim(minx - 800, maxx + 800); ax.set_ylim(miny - 800, maxy + 800)
for k, g in DG.items():                                    # nombre de cada distrito, en gris, en un punto interior
    c = g.representative_point()
    if minx < c.x < maxx and miny < c.y < maxy:
        ax.text(c.x, c.y, dname[k].replace(' - ', '-\n'), fontsize=6.5, color='#3f3f3b', ha='center', va='center', zorder=5, path_effects=[pe.withStroke(linewidth=2.6, foreground='white')])
ax.legend(loc='upper center', bbox_to_anchor=(0.5, 0.0), ncol=2, frameon=False, fontsize=9, markerscale=4)
fig.savefig(W + 'estudio_mapa.png', bbox_inches='tight', facecolor='white'); plt.close(fig)
print(json.dumps({k: R[k] for k in ('shh', 'rho_sombra_renta', 'quintiles_renta', 'bajo_q25_rbaja', 'rho_distrito_ivta', 'atr', 'cruces', 'rho_sombra_atr', 'doble', 'plan')}, ensure_ascii=False, indent=1))
