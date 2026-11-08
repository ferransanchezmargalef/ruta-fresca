"""Resume las variantes de sensibilidad (work/sens_*/sens.json) frente al cálculo base: sombra media a las 13 y 17 h de junio,
orden de los colegios (Spearman), colegios prioritarios que se mantienen y diferencia media por tramo a las 13 h."""
import json, os
import numpy as np
from scipy.stats import spearmanr
os.chdir(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))
B = json.load(open('work/sens_base/sens.json'))
VAR = [('piso28', 'Altura por planta 2,8 m'), ('piso33', 'Altura por planta 3,3 m'), ('copa08', 'Copas un 20 % menores'),
       ('copa12', 'Copas un 20 % mayores'), ('acera10', 'Acera a 1 m de la fachada'), ('acera25', 'Acera a 2,5 m de la fachada')]
keys = sorted(B['shh']); b = np.array([B['shh'][k] for k in keys]); bl = np.array(B['lk_sh13'])
out = {'base': {'sombra_13h_junio': B['sombra_urb'][0][2], 'sombra_17h_junio': B['sombra_urb'][0][4], 'prioritarios': len(B['prio'])}, 'variantes': []}
for d, nm in VAR:
    f = f'work/sens_{d}/sens.json'
    if not os.path.exists(f): continue
    V = json.load(open(f)); v = np.array([V['shh'][k] for k in keys]); vl = np.array(V['lk_sh13'])
    com = len(set(B['prio']) & set(V['prio']))
    out['variantes'].append({'variante': nm, 'sombra_13h_junio': V['sombra_urb'][0][2], 'sombra_17h_junio': V['sombra_urb'][0][4],
                             'rho_colegios': round(float(spearmanr(b, v).correlation), 3), 'prioritarios_comunes': f'{com} de {len(B["prio"])}',
                             'prioritarios_variante': len(V['prio']), 'dif_media_tramos_13h': round(float(np.abs(vl - bl).mean()), 1)})
json.dump(out, open('work/sensibilidad.json', 'w'), ensure_ascii=False, indent=1)
print(json.dumps(out, ensure_ascii=False, indent=1))
