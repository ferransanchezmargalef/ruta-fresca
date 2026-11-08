"""Atropellos a peatones de 2022 a 2025 en Madrid (accidentes de tráfico con víctimas o daños, Policía Municipal).
Cada fila del fichero es una persona implicada; un atropello es un expediente con tipo_accidente "Atropello a persona".
Uso: python3 -I atropellos_madrid.py work/atropellos.json raw/ayto2/accidentes_2022.csv ... 
"""
import sys, json
import pandas as pd, numpy as np

out, files = sys.argv[1], sys.argv[2:]
rows = []
for f in files:
    d = pd.read_csv(f, sep=';', encoding='utf-8-sig', dtype=str)
    d = d[d.tipo_accidente.str.strip().str.lower() == 'atropello a persona']
    for c in ('coordenada_x_utm', 'coordenada_y_utm'):
        d[c] = pd.to_numeric(d[c].str.replace('.', '', regex=False).str.replace(',', '.', regex=False), errors='coerce') if d[c].str.contains(',', na=False).any() else pd.to_numeric(d[c], errors='coerce')
    peat = d[d.tipo_persona.str.strip().str.lower() == 'peatón']
    grave = peat.cod_lesividad.isin(['3', '4'])       # 3: ingreso superior a 24 horas, 4: fallecido en 24 horas
    g = d.groupby('num_expediente').agg(x=('coordenada_x_utm', 'first'), y=('coordenada_y_utm', 'first'), fecha=('fecha', 'first'),
                                        loc=('localizacion', 'first'))
    gp = peat.assign(gr=grave).groupby('num_expediente').agg(peatones=('tipo_persona', 'size'), graves=('gr', 'sum'),
                                                                 menores=('rango_edad', lambda s: int(s.str.contains('Menor|De 0 a|De 6 a|De 10 a|De 15 a 17', regex=True).sum())),
                                                                 mayores=('rango_edad', lambda s: int(s.str.contains('De 65|De 70|De 75|Más de 74|Mas de 74|De 80', regex=True).sum())))
    g = g.join(gp, how='left').fillna({'peatones': 0, 'graves': 0, 'menores': 0, 'mayores': 0})
    g['year'] = f[-8:-4]
    print(f, 'expedientes', len(g), 'sin coordenadas', int(g.x.isna().sum()), 'peatones', int(g.peatones.sum()), 'graves', int(g.graves.sum()))
    rows.append(g)
A = pd.concat(rows)
A = A[A.x.between(420000, 460000) & A.y.between(4460000, 4502000)]
print('atropellos con coordenadas', len(A), 'por año', A.year.value_counts().sort_index().to_dict())
print('edades (valores):', sorted(pd.concat([pd.read_csv(f, sep=';', encoding='utf-8-sig', dtype=str, usecols=['rango_edad']) for f in files[:1]]).rango_edad.dropna().unique())[:30])
json.dump([{'x': round(float(r.x), 1), 'y': round(float(r.y), 1), 'g': int(r.graves > 0), 'm': int(r.menores > 0), 'v': int(r.mayores > 0), 'a': int(r.year)}
           for r in A.itertuples()], open(out, 'w'))
