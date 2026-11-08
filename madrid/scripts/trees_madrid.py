"""Árboles de Madrid para el cálculo de sombra: copa estimada a partir del perímetro del tronco.

El inventario municipal da la altura total y el perímetro del tronco, pero no el tamaño de la copa. El radio de la copa
se estima con la relación entre diámetro de copa y diámetro del tronco de los árboles urbanos aislados
(Coombes, Martin y Slater, 2019: el diámetro de copa es entre 24 y 27 veces el diámetro del tronco; se usa 25),
con límites: entre 0,75 m y 8 m, y no más de 0,6 veces la altura del árbol. Palmeras: radio fijo de 2,5 m.
Coníferas columnares (cipreses, tuyas, enebros): la mitad del radio.
Factor de sombra útil por tipo de planta (tabla de especies del inventario): frondosa 1, conífera 0,8,
subtropical 0,8, arbusto 0,5, palmera 0,35; herbáceas, tapizantes y cactus no cuentan.
Uso: python3 -I trees_madrid.py raw/arbolado_2026-07.csv raw/arbolado_tabla_1.xlsx work/trees.pkl
"""
import sys
import numpy as np, pandas as pd

src, especies, out = sys.argv[1:4]
t = pd.read_csv(src, sep=';', encoding='utf-8-sig', low_memory=False)
for c in ('X', 'Y', 'PERIMETRO', 'ALTURA_TOTAL'):
    t[c] = pd.to_numeric(t[c].astype(str).str.replace(',', '.'), errors='coerce')
sp = pd.read_excel(especies)[['Código', 'Tipo de planta']].rename(columns={'Código': 'CODIGO_ESPECIE', 'Tipo de planta': 'tipo'})
t = t.merge(sp, on='CODIGO_ESPECIE', how='left')
n0 = len(t)
# valores imposibles como desconocidos; se rellenan con la mediana de la especie (o la general)
t.loc[(t.ALTURA_TOTAL <= 0) | (t.ALTURA_TOTAL > 40), 'ALTURA_TOTAL'] = np.nan
t.loc[(t.PERIMETRO <= 0) | (t.PERIMETRO > 600), 'PERIMETRO'] = np.nan
fill_h = t.ALTURA_TOTAL.isna() | t.PERIMETRO.isna()
for c, dflt in (('ALTURA_TOTAL', 6.0), ('PERIMETRO', 45.0)):
    t[c] = t[c].fillna(t.groupby('ESPECIE')[c].transform('median')).fillna(dflt)
FAC = {'FRONDOSA': 1.0, 'CONIFERA': 0.8, 'SUBTROPICAL/TROPICAL': 0.8, 'ARBUSTO': 0.5, 'PALMACEA': 0.35}
t['f'] = t.tipo.map(FAC)
t.loc[t.tipo.isna(), 'f'] = 0.8
t = t[t.f.notna()].copy()
dbh = t.PERIMETRO / np.pi                      # cm
r = 25 * dbh / 100 / 2                          # m (diámetro de copa = 25 x diámetro del tronco)
r = np.minimum(np.minimum(r, 8.0), 0.6 * t.ALTURA_TOTAL)
r = np.maximum(r, 0.75)
col = t.ESPECIE.str.upper().str.match(r'^(CUPRESSUS|X ?CUPRESSOCYPARIS|CUPRESSOCYPARIS|THUJA|PLATYCLADUS|JUNIPERUS|CHAMAECYPARIS|CALOCEDRUS)')
r = np.where(col, np.maximum(0.75, r * 0.5), r)
r = np.where(t.tipo == 'PALMACEA', 2.5, r)
t['r'] = np.round(r, 2); t['h'] = t.ALTURA_TOTAL; t['x'] = t.X; t['y'] = t.Y
t[['ASSETNUM', 'NUM_PARQUE', 'NUM_DISTRITO', 'NUM_BARRIO', 'ESPECIE', 'tipo', 'x', 'y', 'r', 'h', 'f', 'PERIMETRO']].reset_index(drop=True).to_pickle(out)
print('árboles', n0, 'con sombra', len(t), 'altura o perímetro rellenado', int(fill_h.sum()))
print('radio de copa: mediana', float(np.median(t.r)), 'p90', float(np.percentile(t.r, 90)), 'máx', float(t.r.max()))
print('columnares', int(col.sum()), 'palmeras', int((t.tipo == 'PALMACEA').sum()))
print(t.groupby('tipo').r.median().round(2).to_dict())
