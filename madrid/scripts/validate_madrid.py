"""Validación de la sombra de Madrid con la ortofoto municipal (servpub.madrid.es, capa ORTOFOTO_MADRID, recortes de 500 x 500 m
a 0,25 m por píxel en raw/orto/<zona>.jpg).

Para cada zona:
1. Sombra observada: píxeles oscuros (umbral de Otsu) del suelo visible; se excluyen los edificios (Catastro, +1 m) y la vegetación.
2. Sombra del modelo: la misma lógica que la web (edificios por plantas + copas de árbol desplazadas), con la posición del sol en el
   momento del vuelo. La hora del vuelo no se publica, así que la posición del sol (acimut y elevación) se ajusta a la imagen con la
   sombra de los edificios, igual que en València.
3. Se compara píxel a píxel (1 m) y en los puntos de acera que usa la web.
Uso: python3 -I scripts/validate_madrid.py [desplazamiento de la acera, 1,5 m por defecto]
Salida: work/validacion_madrid.json y work/validacion_<zona>.png (comparación visual)."""
import json, math, sys, os
import numpy as np, pandas as pd
from PIL import Image, ImageDraw
from pyproj import Transformer
from scipy.ndimage import distance_transform_edt

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
os.chdir(ROOT)
AREAS = {'lavapies': (440254, 4473129), 'chamberi': (440165, 4475860), 'goya': (442406, 4474899), 'vallecas': (448134, 4469030)}
NAMES = {'lavapies': 'Lavapiés (Centro)', 'chamberi': 'Trafalgar (Chamberí)', 'goya': 'Goya (Salamanca)', 'vallecas': 'Ensanche de Vallecas'}
OFFW = float(sys.argv[1]) if len(sys.argv) > 1 else 1.5
FIT = 'equilibrada'
M = 150   # margen para las sombras que vienen de fuera de la zona
to_utm = Transformer.from_crs(4326, 25830, always_xy=True)

BZ = np.load('work/buildings.npz')
floors = BZ['floors'].astype(np.int32); ring_part = BZ['ring_part']; ring_hole = BZ['ring_hole']; ring_off = BZ['ring_off']; XY = BZ['xy']
hgt = np.where(floors > 0, np.minimum(floors * 3 + 1, 250), 0)
first = np.searchsorted(ring_part, np.arange(len(floors) + 1))
rmin = np.minimum.reduceat(XY, ring_off[:-1]); rmax = np.maximum.reduceat(XY, ring_off[:-1])
T = pd.read_pickle('work/trees.pkl')
TX, TR, THC = T[['x', 'y']].to_numpy(), T.r.to_numpy(), 0.65 * T.h.to_numpy()
IX = json.load(open('app/data/index.json'))


def raster(x0, y0, x1, y1):
    W, H = int(x1 - x0), int(y1 - y0); G = np.zeros((H, W), np.uint8)
    parts = np.unique(ring_part[(rmax[:, 0] >= x0) & (rmin[:, 0] <= x1) & (rmax[:, 1] >= y0) & (rmin[:, 1] <= y1)])
    for p in parts:
        if hgt[p] <= 0: continue
        img = Image.new('L', (W, H), 0); dr = ImageDraw.Draw(img)
        for r in range(first[p], first[p + 1]):
            v = XY[ring_off[r]:ring_off[r + 1]]
            if len(v) >= 3: dr.polygon(list(zip(v[:, 0] - x0, y1 - v[:, 1])), fill=0 if ring_hole[r] else 1)
        np.maximum(G, (np.asarray(img, bool) * hgt[p]).astype(np.uint8), out=G)
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
    sel = (C[:, 0] > x0 - 9) & (C[:, 0] < x1 + 9) & (C[:, 1] > y0 - 9) & (C[:, 1] < y1 + 9)
    img = Image.new('L', (int(x1 - x0), int(y1 - y0)), 0); dr = ImageDraw.Draw(img)
    for (cx, cy), r in zip(C[sel], TR[sel]):
        dr.ellipse([cx - x0 - r, y1 - cy - r, cx - x0 + r, y1 - cy + r], fill=1)
    return np.asarray(img, bool)


def otsu(v):
    hist, _ = np.histogram(v, bins=256, range=(0, 255)); w = hist.cumsum(); m = (hist * np.arange(256)).cumsum()
    mt = m[-1]; wb = w; wf = w[-1] - w; mb = m / np.maximum(wb, 1); mf = (mt - m) / np.maximum(wf, 1)
    return int(np.argmax(wb * wf * (mb - mf) ** 2))


def metrics(obs, mod, mask):
    o, p = obs[mask], mod[mask]
    tp = np.sum(o & p); tn = np.sum(~o & ~p); fp = np.sum(~o & p); fn = np.sum(o & ~p)
    acc = (tp + tn) / max(len(o), 1); prec = tp / max(tp + fp, 1); rec = tp / max(tp + fn, 1)
    return {'exactitud': round(float(acc), 3), 'precision': round(float(prec), 3), 'sensibilidad': round(float(rec), 3),
            'F1': round(float(2 * prec * rec / max(prec + rec, 1e-9)), 3), 'equilibrada': round(float((rec + tn / max(tn + fp, 1)) / 2), 3), 'n': int(len(o))}


def links_in(x0, y0, x1, y1):
    """Geometría (UTM) de los enlaces de la web que tocan la zona, leída de las cuadrículas."""
    lo0, la0 = Transformer.from_crs(25830, 4326, always_xy=True).transform(x0 - 50, y0 - 50)
    lo1, la1 = Transformer.from_crs(25830, 4326, always_xy=True).transform(x1 + 50, y1 + 50)
    out = []
    for i in range(int((la0 - IX['lat0']) // IX['tlat']), int((la1 - IX['lat0']) // IX['tlat']) + 1):
        for j in range(int((lo0 - IX['lon0']) // IX['tlon']), int((lo1 - IX['lon0']) // IX['tlon']) + 1):
            fn = f'app/data/t/{i}_{j}.json'
            if not os.path.exists(fn): continue
            t = json.load(open(fn)); nd = {g: (a, b) for g, a, b in t['nodes']}
            for L in t['links']:
                la, lo = nd[L[0]]; c = [(la, lo)]
                for q in range(0, len(L[5]), 2): la += L[5][q]; lo += L[5][q + 1]; c.append((la, lo))
                c.append(nd[L[1]]); c = np.array(c) / 1e6
                xs, ys = to_utm.transform(c[:, 1], c[:, 0])
                if xs.max() < x0 or xs.min() > x1 or ys.max() < y0 or ys.min() > y1: continue
                out.append(np.c_[xs, ys])
    return out


out = {}
for k, (x0, y0) in AREAS.items():
    x1, y1 = x0 + 500, y0 + 500
    im = np.asarray(Image.open(f'raw/orto/{k}.jpg').convert('RGB'), float)
    f_ = im.shape[0] // 500
    rgb = im[:500 * f_, :500 * f_].reshape(500, f_, 500, f_, 3).mean(axis=(1, 3))   # a 1 m
    Lum = 0.299 * rgb[..., 0] + 0.587 * rgb[..., 1] + 0.114 * rgb[..., 2]
    veg = (2 * rgb[..., 1] - rgb[..., 0] - rgb[..., 2]) > 12
    Gw = raster(x0 - M, y0 - M, x1 + M, y1 + M)
    Gin = Gw[M:M + 500, M:M + 500]
    bdil = Gin > 0
    bdil = bdil | np.roll(bdil, 1, 0) | np.roll(bdil, -1, 0) | np.roll(bdil, 1, 1) | np.roll(bdil, -1, 1)
    ground = ~bdil & ~veg
    ground3 = ground & (distance_transform_edt(Gin == 0) > 3)
    thr = otsu(Lum[ground]); obs = Lum < thr
    best = None
    for az in range(90, 271, 6):
        for el in range(25, 78, 4):
            sc = metrics(obs, bld_shadow(Gw, az, el)[M:M + 500, M:M + 500], ground)[FIT]
            if best is None or sc > best[0]: best = (sc, az, el)
    _, a0, e0 = best
    for az in np.arange(a0 - 5, a0 + 5.1, 1.0):
        for el in np.arange(e0 - 4, e0 + 4.1, 1.0):
            sc = metrics(obs, bld_shadow(Gw, az, el)[M:M + 500, M:M + 500], ground)[FIT]
            if sc > best[0]: best = (sc, float(az), float(el))
    _, az, el = best
    Sb = bld_shadow(Gw, az, el)[M:M + 500, M:M + 500]
    St = tree_shadow(x0, y0, x1, y1, az, el)
    model = Sb | St
    # puntos de acera de la web dentro de la zona (enlaces cada 4 m, acera a OFFW m de la fachada)
    pts = []
    for P in links_in(x0, y0, x1, y1):
        for (xa, ya), (xb, yb) in zip(P[:-1], P[1:]):
            dx, dy = xb - xa, yb - ya; Ls = math.hypot(dx, dy)
            if Ls < 0.5: continue
            nx_, ny_ = -dy / Ls, dx / Ls; n = max(1, int(math.ceil(Ls / 4)))
            for f in (np.arange(n) + 0.5) / n:
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
    so, sm, st = obs[P[:, 1], P[:, 0]][pm], model[P[:, 1], P[:, 0]][pm], St[P[:, 1], P[:, 0]][pm]
    samp = {'puntos': int(pm.sum()), 'acierto_modelo': round(float(np.mean(so == sm)), 3), 'acierto_solo_arboles': round(float(np.mean(so == st)), 3),
            'sombra_observada': round(float(so.mean()), 3), 'sombra_modelo': round(float(sm.mean()), 3)}
    out[k] = {'zona': NAMES[k], 'sol_ajustado': {'acimut': az, 'elevacion': el}, 'umbral_luminancia': thr,
              'pixeles_modelo': metrics(obs, model, ground), 'pixeles_lejos_fachada': metrics(obs, model, ground3),
              'pixeles_solo_arboles': metrics(obs, St, ground), 'aceras': samp}
    print(k, json.dumps(out[k], ensure_ascii=False), flush=True)
    # comparación visual: verde = acierto de sombra, rojo = el modelo la pone y no se ve, azul = se ve y el modelo no la pone
    vis = (rgb * 0.55).astype(np.uint8).copy()
    vis[ground & obs & model] = (40, 170, 90); vis[ground & ~obs & model] = (220, 60, 50); vis[ground & obs & ~model] = (60, 110, 230)
    Image.fromarray(np.concatenate([rgb.astype(np.uint8), vis], axis=1)).save(f'work/validacion_{k}.png')
json.dump(out, open(f'work/validacion_madrid_{OFFW}.json', 'w'), ensure_ascii=False, indent=1)
