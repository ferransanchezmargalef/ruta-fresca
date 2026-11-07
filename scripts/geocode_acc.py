"""Sitúa en el mapa los atropellos 2022-2025 del Ajuntament de València.
El fichero municipal solo trae la dirección escrita ("C/ A cruce C/ B" o "AV A 23") en castellano;
los ejes de calle municipales (con códigos y rangos de portales) traen el nombre oficial en valenciano.
- Cruces: se buscan las dos calles y se acepta el punto si sus ejes se tocan (< 20 m).
- Portales: se busca la calle (coincidencia exigente) y se interpola el número en su rango de portales.
Salida: work/atropellos.json"""
import json, re, unicodedata, collections
import numpy as np, pandas as pd, shapefile
from shapely.geometry import LineString, MultiLineString
from shapely.ops import nearest_points
from rapidfuzz import process, fuzz

R = 'raw/'
TR = {  # castellano -> valenciano (tokens frecuentes en el callejero)
    'JUAN': 'JOAN', 'BAUTISTA': 'BAPTISTA', 'PADRE': 'PARE', 'SAN': 'SANT', 'SANTO': 'SANT', 'JOSE': 'JOSEP', 'FRANCISCO': 'FRANCESC',
    'VICENTE': 'VICENT', 'PEDRO': 'PERE', 'MIGUEL': 'MIQUEL', 'JAIME': 'JAUME', 'JORGE': 'JORDI', 'PABLO': 'PAU', 'ANTONIO': 'ANTONI',
    'LUIS': 'LLUIS', 'BERNARDO': 'BERNAT', 'CRISTOBAL': 'CRISTOFOL', 'ESTEBAN': 'ESTEVE', 'NICOLAS': 'NICOLAU', 'MATEO': 'MATEU',
    'ANDRES': 'ANDREU', 'FERNANDO': 'FERRAN', 'CATOLICO': 'CATOLIC', 'PRIMADO': 'PRIMAT', 'CRUCES': 'CREUS', 'AYUNTAMIENTO': 'AJUNTAMENT',
    'PROFESOR': 'PROFESSOR', 'MAESTRO': 'MESTRE', 'CAMINO': 'CAMI', 'PUENTE': 'PONT', 'PUERTO': 'PORT', 'REINO': 'REGNE',
    'CATALUNA': 'CATALUNYA', 'ARAGON': 'ARAGO', 'CASTILLA': 'CASTELLA', 'CORTES': 'CORTS', 'VALENCIANAS': 'VALENCIANES', 'VIRGEN': 'VERGE',
    'NUESTRA': 'NOSTRA', 'SENORA': 'SENYORA', 'HERMANOS': 'GERMANS', 'OBISPO': 'BISBE', 'ARZOBISPO': 'ARQUEBISBE', 'MUSICO': 'MUSIC',
    'MEDICO': 'METGE', 'INGENIERO': 'ENGINYER', 'ARQUITECTO': 'ARQUITECTE', 'CONDE': 'COMTE', 'DUQUE': 'DUC', 'REY': 'REI',
    'PRINCIPE': 'PRINCEP', 'PLAZA': 'PLACA', 'AVENIDA': 'AVINGUDA', 'CALLE': 'CARRER', 'PASEO': 'PASSEIG', 'PUERTA': 'PORTA',
    'MERCADO': 'MERCAT', 'PUEBLO': 'POBLE', 'NUEVO': 'NOU', 'NUEVA': 'NOVA', 'VIEJO': 'VELL', 'VIEJA': 'VELLA', 'ALTO': 'ALT', 'BAJO': 'BAIX',
    'GRANDE': 'GRAN', 'ISLAS': 'ILLES', 'ISLA': 'ILLA', 'BALEARES': 'BALEARS', 'SENOR': 'SENYOR', 'JUSTICIA': 'JUSTICIA', 'CABALLEROS': 'CAVALLERS',
    'CABALLERO': 'CAVALLER', 'MARQUES': 'MARQUES', 'BARON': 'BARO', 'CARDENAL': 'CARDENAL', 'GUILLERMO': 'GUILLEM', 'GABRIEL': 'GABRIEL',
    'JOAQUIN': 'JOAQUIM', 'GASPAR': 'GASPAR', 'BALTASAR': 'BALTASAR', 'AMBROSIO': 'AMBROS', 'IGNACIO': 'IGNASI', 'JERONIMO': 'JERONI',
    'RAFAEL': 'RAFAEL', 'BENITO': 'BENET', 'FELIPE': 'FELIP', 'ENRIQUE': 'ENRIC', 'MARTIN': 'MARTI', 'TOMAS': 'TOMAS', 'BARTOLOME': 'BARTOMEU',
    'SEBASTIAN': 'SEBASTIA', 'JULIAN': 'JULIA', 'CIRILO': 'CIRIL', 'EUGENIA': 'EUGENIA', 'VINA': 'VINYA', 'HUERTA': 'HORTA', 'ACEQUIA': 'SEQUIA',
    'MOLINO': 'MOLI', 'RIO': 'RIU', 'MAR': 'MAR', 'PLAYA': 'PLATJA', 'MONTANA': 'MUNTANYA', 'MONTANARES': 'MUNTANYARS', 'ESCUELA': 'ESCOLA',
    'IGLESIA': 'ESGLESIA', 'CRUZ': 'CREU', 'ROSARIO': 'ROSER', 'SAGRADO': 'SAGRAT', 'CORAZON': 'COR', 'SANTISIMO': 'SANTISSIM',
    'CRISTO': 'CRIST', 'PIO': 'PIUS', 'RUZAFA': 'RUSSAFA', 'CUENCA': 'CONCA', 'CHILE': 'XILE', 'LLANO': 'PLA', 'ZAIDIA': 'SAIDIA',
    'BARCAS': 'BARQUES', 'BLANQUERIAS': 'BLANQUERIA', 'IBIZA': 'EIVISSA', 'NARANJOS': 'TARONGERS', 'EXPOSICION': 'EXPOSICIO', 'ALAMEDA': 'ALBEREDA',
    'FUENSANTA': 'FONTSANTA', 'MARCELINO': 'MARCELI', 'HONORATO': 'HONORAT', 'MARIANO': 'MARIA', 'RICARDO': 'RICARD', 'ALFONSO': 'ALFONS', 'MANUEL': 'MANUEL',
    'PATRIARCA': 'PATRIARCA', 'GUARDIA': 'GUARDIA', 'CIVIL': 'CIVIL', 'MARTIR': 'MARTIR', 'BEATO': 'BEAT', 'ARTES': 'ARTS', 'OFICIOS': 'OFICIS', 'PINTOR': 'PINTOR', 'LEALTAD': 'LLEIALTAT', 'LIBERTAD': 'LLIBERTAT', 'CIUDAD': 'CIUTAT', 'UNIVERSIDAD': 'UNIVERSITAT', 'ESTACION': 'ESTACIO',
    'HOSPITAL': 'HOSPITAL', 'CONVENTO': 'CONVENT', 'PUENTES': 'PONTS', 'TORRES': 'TORRES', 'CAMPO': 'CAMP', 'OLIVO': 'OLIVERA', 'NARANJO': 'TARONGER',
}
STOP = {'DE', 'DEL', 'LA', 'EL', 'LOS', 'LAS', 'Y', 'I', 'D', 'L', 'DELS', 'LES', 'ELS', 'LO', 'A', 'AL', 'EN', 'SA', 'NA', 'EN'}
TYPES_ES = {'C/': 'CARRER', 'AV': 'AVINGUDA', 'PL': 'PLACA', 'GV': 'GRAN VIA', 'PG': 'PASSEIG', 'CTRA': 'CARRETERA', 'CAMI': 'CAMI',
            'LLOC': 'LLOC', 'JARDIN': 'JARDI', 'CRA': 'CARRETERA', 'ENTD': 'ENTRADA', 'PTGE': 'PASSATGE', 'SENDA': 'SENDA', 'CV': 'CARRETERA',
            'TRAV': 'TRAVESSIA', 'CN': 'CAMI'}


def strip_acc(s):
    s = unicodedata.normalize('NFD', s.upper())
    return ''.join(c for c in s if unicodedata.category(c) != 'Mn')


def norm(s, translate=True):
    s = strip_acc(s.replace('L·L', 'LL').replace('l·l', 'll').replace('·', '')).replace('Ç', 'C')
    s = re.sub(r"[^A-Z0-9 ]", " ", s)
    toks = [t for t in s.split() if t not in STOP]
    if translate:
        toks = [TR.get(t, t) for t in toks]
    return ' '.join(toks)


# ---------------- ejes de calle ----------------
rd = shapefile.Reader(R + 'eixos/UrbanismoEInfraestructuras__223', encoding='utf-8')
geoms = collections.defaultdict(list); vname = {}; vtype = {}; segs = collections.defaultdict(list)
for sh, rec in zip(rd.shapes(), rd.records()):
    d = rec.as_dict()
    if d['codvia'] is None or not sh.points: continue
    cv = int(d['codvia']); pts = np.array(sh.points)
    parts = list(sh.parts) + [len(pts)]
    for a, b in zip(parts[:-1], parts[1:]):
        if b - a >= 2:
            ls = LineString(pts[a:b]); geoms[cv].append(ls)
            segs[cv].append((ls, d['lf_add'], d['lt_add'], d['rf_add'], d['rt_add']))
    vname[cv] = d['nomcalle'] or ''; vtype[cv] = norm(d['tipcalle'] or '', False)
geom = {cv: MultiLineString(v) for cv, v in geoms.items()}
cvs = list(vname.keys()); keys = [norm(vname[c]) for c in cvs]
print('ejes', sum(len(v) for v in geoms.values()), 'calles', len(cvs))

# nombres oficiales en castellano del listado municipal (incompleto: 2.000 filas) -> código
lc = pd.read_csv(R + 'llistat_carrers-3.csv', sep=';', encoding='latin-1')
es2cv = collections.defaultdict(set)
for _, r in lc.iterrows():
    if int(r.CODVIA) in geom: es2cv[norm(str(r.NOMOFICIAL))].add(int(r.CODVIA))


def parse_street(s):
    s = s.strip(); toks = s.split()
    if not toks: return None, ''
    t = strip_acc(toks[0])
    if t in TYPES_ES: return TYPES_ES[t], ' '.join(toks[1:])
    return None, s


def candidates(name, typ, k=5):
    q = norm(name)
    out = {}
    for cv in es2cv.get(q, ()): out[cv] = 100.0
    for _, score, i in process.extract(q, keys, scorer=fuzz.token_sort_ratio, limit=k):
        cv = cvs[i]
        sc = score + (4 if typ and vtype.get(cv) == norm(typ, False) else 0)
        out[cv] = max(out.get(cv, 0), sc)
    return sorted(out.items(), key=lambda x: -x[1])


acc = pd.read_csv(R + 'accidentes_2022-2025.csv', sep=';', encoding='latin-1')
acc.columns = ['fecha', 'grav', 'ubic', 'tipo', 'unid', 'fact']
at = acc[acc.tipo.str.contains('ATROPELLO A PERSONA', na=False)].copy()
GRAV = {'SIN HERIDOS': 0, 'CON HERIDOS LEVES': 1, 'CON HERIDOS BAJA GRAVEDAD': 2, 'CON HERIDOS GRAVES': 3, 'CON FALLECIDOS': 4}
res, stat, examples, fails = [], collections.Counter(), [], []
for _, r in at.iterrows():
    u = str(r.ubic)
    parts = re.split(r'\s+cruce\s+', u, flags=re.I)
    pt = None; how = None
    if len(parts) == 2:
        (ta, na), (tb, nb) = parse_street(parts[0]), parse_street(parts[1])
        ca = [c for c in candidates(na, ta) if c[1] >= 70][:4]; cb = [c for c in candidates(nb, tb) if c[1] >= 70][:4]
        best = None
        for a, sa in ca:
            for b, sb in cb:
                if a == b: continue
                d = geom[a].distance(geom[b])
                if d < 30 and (best is None or sa + sb > best[0]):
                    p1, p2 = nearest_points(geom[a], geom[b]); best = (sa + sb, (p1.x + p2.x) / 2, (p1.y + p2.y) / 2, a, b)
        if best: pt = best[1:3]; how = 'cruce'; ex = (u, vname[best[3]], vname[best[4]])
        stat['cruce_ok' if best else 'cruce_no'] += 1
        if not best: fails.append(('cruce', u, [vname[c] for c, _ in ca[:2]], [vname[c] for c, _ in cb[:2]]))
    else:
        m = re.match(r'^(.*?)[\s,]+(\d+)\s*[A-Z]{0,3}\s*$', u)
        if m:
            t, nm = parse_street(m.group(1)); n = int(m.group(2))
            got = None
            cands = candidates(nm, t)
            for cv, sc in cands:
                if sc < 80: break
                for ls, lf, lt, rf, rt in segs[cv]:
                    for f_, t_ in ((lf, lt), (rf, rt)):
                        if not f_ or not t_: continue
                        lo, hi = min(f_, t_), max(f_, t_)
                        if lo <= n <= hi and int(lo) % 2 == n % 2:
                            fr = 0.5 if hi == lo else (n - f_) / (t_ - f_)
                            p = ls.interpolate(min(max(fr, 0), 1), normalized=True); got = (p.x, p.y, cv); break
                    if got: break
                if got: break
            if not got and cands and cands[0][1] >= 90:
                cv = cands[0][0]; bestd = None
                for ls, lf, lt, rf, rt in segs[cv]:
                    for f_, t_ in ((lf, lt), (rf, rt)):
                        if not f_ or not t_: continue
                        dd = min(abs(n - f_), abs(n - t_))
                        if dd <= 20 and (bestd is None or dd < bestd[0]):
                            fr = 0.5 if t_ == f_ else min(max((n - f_) / (t_ - f_), 0), 1)
                            p = ls.interpolate(fr, normalized=True); bestd = (dd, p.x, p.y)
                if bestd: got = (bestd[1], bestd[2], cv)
            if got: pt = got[:2]; how = 'num'; ex = (u, vname[got[2]])
            stat['num_ok' if got else 'num_no'] += 1
            if not got: fails.append(('num', u, [(vname[c], round(sc)) for c, sc in candidates(nm, t)[:2]]))
        else:
            stat['sin_numero'] += 1; fails.append(('sin', u))
    if pt:
        res.append({'x': round(pt[0], 1), 'y': round(pt[1], 1), 'a': int(str(r.fecha)[:4]), 'g': GRAV.get(r.grav, 1), 'h': how})
        if len(examples) < 14 and len(examples) % 1 == 0 and np.random.rand() < 0.02: examples.append(ex)
print('atropellos', len(at), 'ubicados', len(res), dict(stat))
for e in examples: print('  ', e)
json.dump(res, open('work/atropellos.json', 'w'))
import random; random.seed(5)
for f in random.sample(fails, min(15, len(fails))): print('FALLO', f)
