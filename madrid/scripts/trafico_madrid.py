"""Intensidad media de tráfico por punto de medida en junio de 2026 (días laborables, de 8 a 20 h), en vehículos por hora.
Uso: python3 -I trafico_madrid.py raw/trafico/06-2026.csv raw/ayto2/trafico_puntos.csv work/trafico_puntos.json
"""
import sys, json
import pandas as pd, numpy as np

src, puntos, out = sys.argv[1:4]
acc = None
for ch in pd.read_csv(src, sep=';', usecols=['id', 'fecha', 'tipo_elem', 'intensidad', 'error'], chunksize=2_000_000,
                      dtype={'id': 'int32', 'tipo_elem': 'category', 'error': 'category'}):
    ch = ch[ch.error == 'N']
    f = pd.to_datetime(ch.fecha, format='%Y-%m-%d %H:%M:%S')
    ch = ch[(f.dt.dayofweek < 5) & (f.dt.hour >= 8) & (f.dt.hour < 20)]
    ch = ch.assign(i=pd.to_numeric(ch.intensidad, errors='coerce')).dropna(subset=['i'])
    g = ch.groupby('id').i.agg(['sum', 'count'])
    acc = g if acc is None else acc.add(g, fill_value=0)
acc['imh'] = acc['sum'] / acc['count']     # intensidad en vehículos/hora (los datos de 15 min ya vienen en veh/h)
P = pd.read_csv(puntos, sep=';', encoding='cp1252')
P = P.merge(acc[['imh', 'count']], left_on='id', right_index=True, how='inner')
P = P[P['count'] >= 200]
print('puntos con datos', len(P), 'por tipo', P.tipo_elem.value_counts().to_dict())
print('intensidad (veh/h): mediana', round(P.imh.median()), 'p75', round(P.imh.quantile(.75)), 'p90', round(P.imh.quantile(.9)))
json.dump([{'id': int(r.id), 't': r.tipo_elem, 'x': round(float(r.utm_x), 1), 'y': round(float(r.utm_y), 1), 'imh': round(float(r.imh), 1),
            'n': str(r.nombre)} for r in P.itertuples()], open(out, 'w'), ensure_ascii=False)
