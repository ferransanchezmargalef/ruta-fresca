"""Validación de la sombra con la ortofoto municipal de 2018 (geoportal.valencia.es, FotoAerea_2018).

Para cada zona de 500 x 500 m:
1. Sombra observada: píxeles oscuros (umbral de Otsu) del suelo visible; se excluyen edificios (Catastro, +1 m) y la vegetación.
2. Sombra del modelo: la misma lógica que la app (edificios por plantas + copas de árbol desplazadas), con la posición del sol
   en el momento del vuelo. La hora del vuelo no se publica, así que la posición del sol (2 parámetros) se ajusta a la imagen.
3. Se compara píxel a píxel (1 m) y en los puntos de acera que usa la app.
Salida: work/validacion.json y work/validacion_*.png (comparación visual)."""
import json, math, base64
import numpy as np
from PIL import Image, ImageDraw
from pyproj import Transformer
from scipy.spatial import cKDTree
import pandas as pd

AREAS = {'carme': (725017, 4372792, 725517, 4373292), 'russafa': (725711, 4371146, 726211, 4371646),
         'algiros': (727163, 4373021, 727663, 4373521), 'campanar': (723709, 4373365, 724209, 4373865)}
NAMES = {'carme': 'El Carme (Ciutat Vella)', 'russafa': 'Russafa (Eixample)', 'algiros': 'Algirós', 'campanar': 'Campanar'}
import sys
OFFW = float(sys.argv[1]) if len(sys.argv) > 1 else 1.5
FIT = sys.argv[2] if len(sys.argv) > 2 else 'equilibrada'
M = 120  # margen para sombras que vienen de fuera
to_utm = Transformer.from_crs(4326, 25830, always_xy=True)

BZ = np.load('work/buildings.npz')
floors = BZ['floors'].astype(np.int32); ring_part = BZ['ring_part']; ring_hole = BZ['ring_hole']; ring_off = BZ['ring_off']; XY = BZ['xy']
hgt = np.where(floors > 0, np.minimum(floors * 3 + 1, 250), 0)
first = np.searchsorted(ring_part, np.arange(len(floors) + 1))
ring_min = np.array([XY[ring_off[r]:ring_off[r + 1]].min(0) for r in range(len(ring_part))])
ring_max = np.array([XY[ring_off[r]:ring_off[r + 1]].max(0) for r in range(len(ring_part))])

t = pd.read_pickle('work/trees.pkl')
def cls(s):
    if not isinstance(s, str): return None
    s = s.replace(' ', '').replace('m', '')
    return {'0/4': '0-4', '0-4': '0-4', '4/8': '4-8', '4-8': '4-8', '8/12': '8-12', '8-12': '8-12', '>12': '>12'}.get(s)
t['r'] = t.copa.map(cls).map({'0-4': 1.5, '4-8': 3.0, '8-12': 5.0, '>12': 6.5}).fillna(2.0)
t['h'] = t.altura.map(cls).map({'0-4': 3.0, '4-8': 6.0, '8-12': 10.0, '>12': 14.0}).fillna(2.2 * t.r + 1)
live = t[~t.estado.isin(['Falta', 'Tocón', 'Seco'])]
TX, TR, THC = live[['x', 'y']].to_numpy(), live.r.to_numpy(), 0.65 * live.h.to_numpy()

g = json.load(open('app/data/graph.json'))
NLL = np.array(g['nodes']) / 1e6


def raster(x0, y0, x1, y1):
    W, H = int(x1 - x0), int(y1 - y0); G = np.zeros((H, W), np.uint8)
    parts = np.unique(ring_part[(ring_max[:, 0] >= x0) & (ring_min[:, 0] <= x1) & (ring_max[:, 1] >= y0) & (ring_min[:, 1] <= y1)])
    for p in parts:
        if hgt[p] <= 0: continue
        rings = [(XY[ring_off[r]:ring_off[r + 1]], ring_hole[r]) for r in range(first[p], first[p + 1])]
        img = Image.new('L', (W, H), 0); dr = ImageDraw.Draw(img)
        for v, h in rings:
            if len(v) >= 3: dr.polygon(list(zip(v[:, 0] - x0, y1 - v[:, 1])), fill=0 if h else 1)
        m = np.asarray(img, bool)
        np.maximum(G, (m * hgt[p]).astype(np.uint8), out=G)
    return G


def bld_shadow(G, az, el):
    tanE = math.tan(math.radians(el)); sx, sy = math.sin(math.radians(az)), -math.cos(math.radians(az))
    H, W = G.shape; S = np.zeros_like(G, bool); last = None
    for tt in range(1, int(min(M, G.max() / tanE)) + 1):
        oc, orr = int(round(tt * sx)), int(round(tt * sy))
        if (orr, oc) == last: continue
        last = (orr, oc)
        r0, r1 = max(0, -orr), min(H, H - orr); c0, c1 = max(0, -oc), min(W, W - oc)
        if r1 <= r0 or c1 <= c0: break
        S[r0:r1, c0:c1] |= G[r0 + orr:r1 + orr, c0 + oc:c1 + oc] > tt * tanE
    return S


def tree_shadow(x0, y0, x1, y1, az, el):
    tanE = math.tan(math.radians(el)); d = np.array([-math.sin(math.radians(az)), -math.cos(math.radians(az))])
    C = TX + d[None, :] * (THC / tanE)[:, None]
    sel = (C[:, 0] > x0 - 8) & (C[:, 0] < x1 + 8) & (C[:, 1] > y0 - 8) & (C[:, 1] < y1 + 8)
    img = Image.new('L', (int(x1 - x0), int(y1 - y0)), 0); dr = ImageDraw.Draw(img)
    for (cx, cy), r in zip(C[sel], TR[sel]):
        dr.ellipse([cx - x0 - r, y1 - cy - r, cx - x0 + r, y1 - cy + r], fill=1)
    return np.asarray(img, bool)


def otsu(v):
    hist, edges = np.histogram(v, bins=256, range=(0, 255)); w = hist.cumsum(); m = (hist * np.arange(256)).cumsum()
    mt = m[-1]; wb = w; wf = w[-1] - w; mb = m / np.maximum(wb, 1); mf = (mt - m) / np.maximum(wf, 1)
    return int(np.argmax(wb * wf * (mb - mf) ** 2))


def metrics(obs, mod, mask):
    o, p = obs[mask], mod[mask]
    tp = np.sum(o & p); tn = np.sum(~o & ~p); fp = np.sum(~o & p); fn = np.sum(o & ~p)
    acc = (tp + tn) / max(len(o), 1); prec = tp / max(tp + fp, 1); rec = tp / max(tp + fn, 1)
    return {'exactitud': round(float(acc), 3), 'precision': round(float(prec), 3), 'sensibilidad': round(float(rec), 3),
            'F1': round(float(2 * prec * rec / max(prec + rec, 1e-9)), 3), 'equilibrada': round(float((rec + tn / max(tn + fp, 1)) / 2), 3), 'n': int(len(o))}


out = {}
for k, (x0, y0, x1, y1) in AREAS.items():
    im = np.asarray(Image.open(f'raw/orto/{k}.jpg').convert('RGB'), float)
    rgb = im.reshape(500, 4, 500, 4, 3).mean(axis=(1, 3))  # a 1 m
    L = 0.299 * rgb[..., 0] + 0.587 * rgb[..., 1] + 0.114 * rgb[..., 2]
    veg = (2 * rgb[..., 1] - rgb[..., 0] - rgb[..., 2]) > 12
    Gw = raster(x0 - M, y0 - M, x1 + M, y1 + M)
    Gin = Gw[M:M + 500, M:M + 500]
    bdil = Gin > 0
    for _ in range(1):
        bdil = bdil | np.roll(bdil, 1, 0) | np.roll(bdil, -1, 0) | np.roll(bdil, 1, 1) | np.roll(bdil, -1, 1)
    ground = ~bdil & ~veg
    from scipy.ndimage import distance_transform_edt
    dist_b = distance_transform_edt(Gin == 0)
    ground3 = ground & (dist_b > 3)
    thr = otsu(L[ground]); obs = L < thr
    # ajuste de la posición del sol (rejilla gruesa y fina) con la sombra de edificios
    best = None
    for az in range(90, 271, 6):
        for el in range(25, 78, 4):
            S = bld_shadow(Gw, az, el)[M:M + 500, M:M + 500]
            sc = metrics(obs, S, ground)[FIT]
            if best is None or sc > best[0]: best = (sc, az, el)
    _, a0, e0 = best
    for az in np.arange(a0 - 5, a0 + 5.1, 1.0):
        for el in np.arange(e0 - 4, e0 + 4.1, 1.0):
            S = bld_shadow(Gw, az, el)[M:M + 500, M:M + 500]
            sc = metrics(obs, S, ground)[FIT]
            if sc > best[0]: best = (sc, float(az), float(el))
    _, az, el = best
    Sb = bld_shadow(Gw, az, el)[M:M + 500, M:M + 500]
    St = tree_shadow(x0, y0, x1, y1, az, el)
    model = Sb | St
    # puntos de acera de la app dentro de la zona (muestreo de los enlaces cada 4 m, acera a 1,5 m de la fachada)
    pts = []
    for lk in g['links']:
        a, b = lk[0], lk[1]
        la, lo = g['nodes'][a]; coords = [(la, lo)]
        for j in range(0, len(lk[5]), 2): la += lk[5][j]; lo += lk[5][j + 1]; coords.append((la, lo))
        coords.append(tuple(g['nodes'][b]))
        c = np.array(coords) / 1e6
        if not ((c[:, 0] > 39.43).all() and True): pass
        xs, ys = to_utm.transform(c[:, 1], c[:, 0])
        if xs.max() < x0 or xs.min() > x1 or ys.max() < y0 or ys.min() > y1: continue
        for (xa, ya, xb, yb) in zip(xs[:-1], ys[:-1], xs[1:], ys[1:]):
            dx, dy = xb - xa, yb - ya; Lseg = math.hypot(dx, dy)
            if Lseg < 0.5: continue
            nx_, ny_ = -dy / Lseg, dx / Lseg
            for f in (np.arange(max(1, int(Lseg // 4))) + 0.5) / max(1, int(Lseg // 4)):
                px_, py_ = xa + dx * f, ya + dy * f
                for sg in (1, -1):
                    w = None
                    for kk in range(1, 26):
                        cc, rr = int(px_ + sg * nx_ * kk - x0 + M), int(y1 + M - (py_ + sg * ny_ * kk))
                        if 0 <= rr < Gw.shape[0] and 0 <= cc < Gw.shape[1] and Gw[rr, cc] > 0: w = kk; break
                    off = max(0.5, w - OFFW) if w else 5
                    qx, qy = px_ + sg * nx_ * off, py_ + sg * ny_ * off
                    if x0 <= qx < x1 and y0 <= qy < y1: pts.append((int(qx - x0), int(y1 - qy)))
    P = np.array(pts)
    pm = ground[P[:, 1], P[:, 0]]
    samp_obs, samp_mod, samp_bld = obs[P[:, 1], P[:, 0]][pm], model[P[:, 1], P[:, 0]][pm], St[P[:, 1], P[:, 0]][pm]
    samp = {'puntos': int(pm.sum()), 'acierto_modelo': round(float(np.mean(samp_obs == samp_mod)), 3),
            'acierto_solo_arboles': round(float(np.mean(samp_obs == samp_bld)), 3),
            'sombra_observada': round(float(samp_obs.mean()), 3), 'sombra_modelo': round(float(samp_mod.mean()), 3)}
    out[k] = {'zona': NAMES[k], 'sol_ajustado': {'acimut': az, 'elevacion': el}, 'umbral_luminancia': thr,
              'pixeles_modelo': metrics(obs, model, ground), 'pixeles_lejos_fachada': metrics(obs, model, ground3), 'pixeles_solo_arboles': metrics(obs, St, ground), 'aceras': samp}
    print(k, json.dumps(out[k], ensure_ascii=False))
    # imagen de comparación: verde = acierto sombra, rojo = el modelo la pone y no se ve, azul = se ve y el modelo no la pone
    vis = (rgb * 0.55).astype(np.uint8).copy()
    vis[ground & obs & model] = (40, 170, 90); vis[ground & ~obs & model] = (220, 60, 50); vis[ground & obs & ~model] = (60, 110, 230)
    Image.fromarray(np.concatenate([rgb.astype(np.uint8), vis], axis=1)).save(f'work/validacion_{k}.png')

json.dump(out, open(f'work/validacion_{OFFW}.json', 'w'), ensure_ascii=False, indent=1)
