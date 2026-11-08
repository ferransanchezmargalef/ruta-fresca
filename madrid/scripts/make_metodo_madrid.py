"""Genera app/metodo.html de Madrid (cómo funciona, datos, validación, sensibilidad, simulador y límites) a partir de los resultados reales.
Uso: python3 scripts/make_metodo_madrid.py  (desde la carpeta de Madrid)"""
import json, os, base64, statistics
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
os.chdir(ROOT)
WEB = os.environ.get('RF_WEB', 'app/')


def _datos(trabajo, informe):
    # resultados de validate_madrid.py y de la sensibilidad; si no se han vuelto a calcular, los publicados en informes/
    return trabajo if os.path.exists(trabajo) else informe


V = json.load(open(_datos('work/validacion_madrid_1.5.json', 'informes/validacion.json')))
S = json.load(open(_datos('work/sensibilidad.json', 'informes/sensibilidad.json')))
R = json.load(open('informes/resumen_calculo.json'))
SC = json.load(open(WEB + 'data/schools.json')); st = SC['stats']
PLN = json.load(open(WEB + 'data/plant.json'))
fmt = lambda n: f"{n:,}".replace(',', '.') if n >= 10000 else str(n)
dec1 = lambda x: f"{x:.1f}".replace('.', ',')
pct = lambda x: f"{round(100 * x)} %"

val_rows = ''.join(
    f"<tr><td>{v['zona']}</td><td>{pct(v['pixeles_modelo']['exactitud'])}</td><td>{pct(v['pixeles_modelo']['sensibilidad'])}</td>"
    f"<td>{pct(v['pixeles_solo_arboles']['sensibilidad'])}</td><td>{pct(v['aceras']['acierto_modelo'])}</td><td>{fmt(v['pixeles_modelo']['n'])}</td></tr>"
    for v in V.values())
acc = [v['pixeles_modelo']['exactitud'] for v in V.values()]
rec = [v['pixeles_modelo']['sensibilidad'] for v in V.values()]
centro = [v for k, v in V.items() if k != 'vallecas']
az = [v['sol_ajustado']['acimut'] for v in V.values()]; el = [v['sol_ajustado']['elevacion'] for v in V.values()]
sens_rows = ''.join(
    f"<tr><td>{r['variante']}</td><td>{r['sombra_13h_junio']} %</td><td>{r['sombra_17h_junio']} %</td><td>{str(r['rho_colegios']).replace('.', ',')}</td>"
    f"<td>{r['prioritarios_comunes']} ({r.get('prioritarios_variante', '')} en la variante)</td><td>{dec1(r['dif_media_tramos_13h'])} puntos</td></tr>" for r in S['variantes'])
_v = S['variantes']
_d13 = [abs(r['sombra_13h_junio'] - S['base']['sombra_13h_junio']) for r in _v]
_keep = [int(r['prioritarios_comunes'].split()[0]) for r in _v]
_worst = max(_v, key=lambda r: abs(r['sombra_13h_junio'] - S['base']['sombra_13h_junio']))
sens_txt = (f"Las cifras globales de sombra se mueven entre {min(_d13)} y {max(_d13)} puntos y el orden de los colegios apenas cambia "
            f"(correlación de {str(min(r['rho_colegios'] for r in _v)).replace('.', ',')} o más). De los {S['base']['prioritarios']} colegios prioritarios, cada variante "
            f"mantiene entre {min(_keep)} y {max(_keep)}; los que entran o salen están cerca del corte del 25 % con menos sombra. "
            f"La suposición que más pesa es dónde se mide la acera: con la acera a 2,5 m de la fachada, la sombra a las 13 h baja al {_worst['sombra_13h_junio']} %.")
datos = [
    ("Arbolado en parques y zonas verdes de Madrid (detalle)", "Ayuntamiento de Madrid", f"{fmt(R['arboles_registros'])} árboles de calle, de zonas verdes y de parques (inventario de julio de 2026), con especie, altura y perímetro del tronco"),
    ("Mobiliario urbano. Bancos", "Ayuntamiento de Madrid", f"{fmt(st['bancos'])} bancos en servicio"),
    ("Fuentes de agua para beber", "Ayuntamiento de Madrid", f"{fmt(st['fuentes'])} fuentes en servicio para personas"),
    ("Aseos públicos fijos con publicidad", "Ayuntamiento de Madrid", f"{st['aseos']} aseos"),
    ("Centros educativos en Madrid", "Ayuntamiento de Madrid", f"{fmt(len(SC['schools']))} colegios, institutos, escuelas infantiles y centros de educación especial (de los {fmt(R['centros_educativos_fichero'])} centros del fichero)"),
    ("Centros municipales de mayores", "Ayuntamiento de Madrid", f"{len(SC['mayores'])} centros"),
    ("Accidentes de tráfico de la ciudad de Madrid (2022 a 2025)", "Ayuntamiento de Madrid (Policía Municipal)", f"{fmt(R['accidentes_2022_2025'])} accidentes, {fmt(R['atropellos_expedientes'])} de ellos atropellos; {fmt(st['atropellos'])} atropellos con coordenadas"),
    ("Tráfico. Ubicación de los puntos de medida y Tráfico. Histórico de datos desde 2013 (junio de 2026)", "Ayuntamiento de Madrid", f"{fmt(R['puntos_trafico_urbanos'])} puntos de medida urbanos con datos de junio de 2026"),
    ("Callejero oficial del Ayuntamiento de Madrid", "Ayuntamiento de Madrid", f"{fmt(R['portales'])} portales de {fmt(R['calles'])} calles, para buscar por calle y número"),
    ("Barrios municipales de Madrid", "Ayuntamiento de Madrid", "131 barrios y 21 distritos"),
    ("IGUALA. Índice de vulnerabilidad territorial agregado (informe global)", "Ayuntamiento de Madrid", f"renta neta media por hogar de cada barrio ({SC['renta_year']}) e índice de vulnerabilidad de cada distrito ({SC['ivta_year']})"),
    ("Planes de gestión del arbolado de zonas verdes y del viario: plan de plantaciones 2025-2026", "Ayuntamiento de Madrid", f"{fmt(PLN['n_plan'])} árboles de calle y {fmt(PLN['n_zv'])} en zonas verdes, por calle y especie"),
    ("Edificios (Catastro INSPIRE, plantas sobre rasante)", "Dirección General del Catastro (CC BY 4.0)", f"{fmt(R['partes_edificio'])} partes de edificio del término municipal; descargado el 7 de noviembre de 2026"),
    ("Red peatonal, pasos de peatones y semáforos", "© personas colaboradoras de OpenStreetMap (ODbL)", f"extracto del 6 de noviembre de 2026: {fmt(R['segmentos_red'])} tramos ({fmt(R['km_red_osm'])} km) en el término municipal y {fmt(R['pasos_y_semaforos_osm'])} pasos de peatones y semáforos"),
    ("Ortofoto actualizada (solo para comprobar la sombra)", "Ayuntamiento de Madrid", "4 zonas de 500 × 500 m"),
]
datos_rows = ''.join(f"<tr><td>{a}</td><td>{b}</td><td>{c}</td></tr>" for a, b, c in datos)
sh = st['sombra_hora']; ds = sorted(SC['dstats'], key=lambda d: d['sombra_hora'][0][2])
y_ = lambda xs: xs[0] if len(xs) == 1 else ', '.join(xs[:-1]) + ' y ' + xs[-1]
d_lo = y_([d['n'] for d in ds if d['sombra_hora'][0][2] == ds[0]['sombra_hora'][0][2]])
d_hi = y_([d['n'] for d in ds if d['sombra_hora'][0][2] == ds[-1]['sombra_hora'][0][2]])

# simulador del plan de plantaciones
dec8 = lambda x: list(base64.b64decode(x))
shh0 = [s_['shh'] for s_ in SC['schools']]; isprio = [s_['prio'] for s_ in SC['schools']]
def plant_row(sc_):
    g = [x - y for x, y in zip(sc_['sc_shh'], shh0)]; gp = [x for x, q in zip(g, isprio) if q]
    pit = dec8(sc_['pit'])
    return {'n': len(sc_['trees']), 'sh13': sc_['stats1']['sombra_hora'][0][2], 'sin13': sc_['stats1']['sin_sombra_hora'][0][2], 'km': sc_['acera_km'],
            'acera': statistics.median(pit), 'col': sum(g) / len(g), 'prio': sum(gp) / len(gp), 'priomax': max(gp), 'cero': sum(1 for v in pit if v == 0)}
PR = [plant_row(x) for x in PLN['sc']]
B1 = PLN['base1']
plant_rows = (f"<tr><td>Ahora</td><td>—</td><td>{dec1(B1['sombra_hora'][0][2])} %</td><td>{dec1(B1['sin_sombra_hora'][0][2])} %</td><td>—</td><td>—</td><td>—</td></tr>" +
    ''.join(f"<tr><td>{nm}</td><td>{fmt(r['n'])}</td><td>{dec1(r['sh13'])} %</td><td>{dec1(r['sin13'])} %</td><td>{dec1(r['km'])} km ({round(r['acera'])} m por árbol)</td>"
            f"<td>+{dec1(r['col'])}</td><td>+{dec1(r['prio'])} (máx. +{r['priomax']})</td></tr>"
            for nm, r in zip(['Plan 2025-2026, cada árbol en su calle', 'Los mismos árboles junto a los colegios prioritarios'], PR)))
rr, hh = R['arbol_simulado_r'], R['arbol_simulado_h']

html = f"""<!DOCTYPE html>
<html lang="es"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Ruta fresca Madrid · Cómo funciona</title>
<link rel="preconnect" href="https://fonts.googleapis.com"><link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Bricolage+Grotesque:opsz,wght@12..96,700;12..96,800&family=Public+Sans:wght@400;600;700&display=swap" rel="stylesheet">
<style>
:root{{--paper:#f4f7f5;--panel:#fff;--ink:#13302a;--muted:#53675f;--line:#d2dcd7;--accent:#1f5f98;--s0:#cf5a26;--s2:#bfae7d;--s4:#235f98;
  --display:"Bricolage Grotesque","Avenir Next","Segoe UI",sans-serif;--body:"Public Sans","Helvetica Neue",Arial,sans-serif;color-scheme:light}}
@media (prefers-color-scheme:dark){{:root{{--paper:#0f1916;--panel:#14211d;--ink:#e3ece8;--muted:#9db1aa;--line:#2a3a35;--accent:#7fbbe6;--s0:#ff7f45;--s2:#d6c9a2;--s4:#4f93e6;color-scheme:dark}}}}
*{{box-sizing:border-box}} body{{margin:0;background:var(--paper);color:var(--ink);font:16px/1.6 var(--body)}}
main{{max-width:880px;margin:0 auto;padding:32px 22px 60px}}
h1{{font:800 40px/1.05 var(--display);margin:8px 0 6px;letter-spacing:-.02em}}
h1 span{{background:linear-gradient(90deg,var(--s0),var(--s2) 50%,var(--s4));-webkit-background-clip:text;background-clip:text;color:transparent}}
h2{{font:700 23px/1.2 var(--display);margin:38px 0 10px}} h3{{font:700 17px/1.3 var(--display);margin:22px 0 6px}}
p,li{{max-width:72ch}} a{{color:var(--accent)}} .lead{{font-size:18px;color:var(--muted)}}
.back{{font-weight:600}}
.tbl{{overflow-x:auto;border:1px solid var(--line);border-radius:10px;background:var(--panel)}}
table{{border-collapse:collapse;width:100%;font-size:14px;font-variant-numeric:tabular-nums}}
th,td{{text-align:left;padding:8px 10px;border-bottom:1px solid var(--line);vertical-align:top}} th{{font-weight:700;background:var(--paper)}}
tr:last-child td{{border-bottom:0}}
.box{{background:var(--panel);border:1px solid var(--line);border-radius:12px;padding:14px 18px}}
.cap{{font-size:13.5px;color:var(--muted)}}
</style></head><body><main>
<p><a class="back" href="index.html">← Volver a la web</a></p>
<h1><span>Ruta fresca Madrid</span>: cómo funciona</h1>
<p class="lead">Qué datos usa, cómo calcula la sombra y el riesgo de cada calle, cómo elige las rutas, cuánto acierta y qué no sabe hacer todavía.</p>

<h2>Qué hace</h2>
<p>Ruta fresca busca, para ir a pie por Madrid, el camino con más sombra y menos riesgo a una hora y un día concretos, y lo compara con el más corto. Tiene tres usos:</p>
<ul>
<li><b>Al cole:</b> de casa al colegio o a la escuela infantil, con la sombra a la hora de entrada o de salida.</li>
<li><b>Paso lento:</b> para personas mayores, que además necesitan parar; la ruta prefiere tramos con bancos, fuentes de beber y aseos cerca.</li>
<li><b>Ayuntamiento:</b> cuánta sombra tiene cada distrito, qué colegios tienen poca sombra alrededor y están en barrios de renta baja, dónde ha habido atropellos y cuánta sombra darían los árboles del plan de plantaciones 2025-2026, en su sitio o junto a esos colegios.</li>
</ul>
<p>Todo se calcula en el navegador: la web no pide ni guarda datos personales. Madrid es grande, así que las calles se cargan por cuadrículas de unos 2 km a medida que hacen falta; vista de lejos, la ciudad se dibuja en celdas de unos 250 m con la sombra media de sus calles.</p>

<h2>Datos</h2>
<div class="tbl"><table><tr><th>Conjunto</th><th>Fuente</th><th>Qué se usa</th></tr>{datos_rows}</table></div>
<p class="cap">Datos municipales descargados en noviembre de 2026 del <a href="https://datos.madrid.es/">portal de datos abiertos del Ayuntamiento de Madrid</a>, reutilizados según sus condiciones de uso (origen de los datos: Ayuntamiento de Madrid). La red peatonal deriva de OpenStreetMap y se comparte con la misma licencia (ODbL).</p>

<h2>Cómo se calcula la sombra</h2>
<h3>Cuándo</h3>
<p>Para dos días del curso escolar con calor: el <b>15 de junio</b>, con el sol más alto (el caso con menos sombra), y el <b>15 de septiembre</b>. Seis horas de cada día, en horario oficial de verano: 9, 11, 13, 15, 17 y 19 h. La posición del sol se calcula con el algoritmo de baja precisión del Astronomical Almanac (error menor de 0,1°).</p>
<h3>Edificios</h3>
<p>Cada parte de edificio del Catastro tiene su número de plantas sobre rasante. Su altura se estima en 3 m por planta más 1 m de planta baja, y se dibuja en un mapa de alturas de 1 × 1 m de toda la ciudad (el edificio más alto queda en {R['altura_max_m']} m). Un punto de la acera está a la sombra si, mirando hacia el sol, algún edificio queda por encima de la línea del sol.</p>
<h3>Árboles</h3>
<p>El inventario municipal da la altura de cada árbol y el perímetro del tronco, pero no el tamaño de la copa. La copa se estima con la relación que se observa en los árboles urbanos aislados: su diámetro es unas 25 veces el del tronco (Coombes, Martin y Slater, <i>Urban Forestry &amp; Urban Greening</i>, 2019, encontraron entre 24 y 27). El radio queda entre 0,75 y 8 m y nunca pasa de 0,6 veces la altura del árbol. Las palmeras llevan una copa fija de 2,5 m de radio y los cipreses, tuyas y enebros, que son estrechos, la mitad de la calculada. Los valores imposibles del inventario (alturas de más de 40 m, troncos de más de 6 m de perímetro) se sustituyen por la mediana de su especie.</p>
<p>La sombra de la copa se desplaza en la dirección contraria al sol según la altura del árbol. No todos dan la misma sombra: los de hoja ancha cuentan entero, coníferas y especies subtropicales un 80 %, arbustos la mitad y palmeras un 35 %. El inventario de Madrid no trae el estado de cada árbol, así que todos cuentan igual.</p>
<h3>Aceras</h3>
<p>Cada tramo de calle se mide cada 4 m en sus dos aceras. Si hay fachadas a menos de 25 m, la acera se sitúa a 1,5 m de la fachada; si no, a una distancia según el tipo de vía. Cada tramo toma la acera más sombreada, porque se puede cambiar de acera. En Madrid, OpenStreetMap dibuja aparte muchas aceras ({fmt(R['aceras_aparte'])} tramos): esas se miden sobre su propia línea. Los pasos cubiertos y los túneles peatonales ({fmt(R['cubiertos'])} tramos) cuentan como sombra.</p>
<p>La red cubre el término municipal donde hay ciudad: tramos a menos de 250 m de un edificio o a menos de 30 m de un árbol del inventario. Así quedan fuera el monte de El Pardo y los caminos rurales de las afueras, pero entran los parques con arbolado inventariado. No se usan los pasillos interiores de edificios.</p>
<p>Resultado: a las 13 h del 15 de junio, las aceras de las calles con edificios están a la sombra un {sh[0][2]} % de su longitud de media ({st['sombra_edif_hora'][0][2]} % solo por los edificios); a las 17 h, un {sh[0][4]} %. Por distritos, a las 13 h va del {ds[-1]['sombra_hora'][0][2]} % de {d_hi} al {ds[0]['sombra_hora'][0][2]} % de {d_lo}: los distritos con barrios nuevos de calles anchas tienen mucha menos sombra que el centro.</p>

<h2>Cómo se mide el riesgo</h2>
<ul>
<li><b>Nivel de tráfico de cada calle (0 a 3):</b> el mayor entre su clase de vía en OpenStreetMap, su límite de velocidad (40 km/h o más) y la intensidad medida por los puntos de tráfico municipales. Se usan los {fmt(R['puntos_trafico_urbanos'])} puntos urbanos con datos de junio de 2026, de lunes a viernes de 8 a 20 h. Cada punto se asigna a la calzada más cercana (a menos de 20 m) y su nivel pasa a toda esa vía de OpenStreetMap: 1 por debajo de la mediana ({R['p50_veh_h']} vehículos por hora), 2 desde la mediana y 3 desde el cuartil superior ({R['p75_veh_h']} vehículos por hora).</li>
<li><b>Aceras al lado de calles con tráfico:</b> las aceras que OpenStreetMap dibuja aparte toman el nivel de la calzada que tienen al lado, a menos de 15 m ({fmt(R['aceras_con_nivel'])} tramos de acera con algo de tráfico al lado).</li>
<li><b>Cruces peligrosos:</b> cuando la ruta atraviesa una calzada de nivel 2 o 3 en una intersección. Se mira si hay semáforo en un radio de 25 m (OpenStreetMap). En la ciudad hay {fmt(st['cruces_trafico'])} cruces con calles de tráfico, {fmt(st['cruces_sin_semaforo'])} de ellos sin semáforo.</li>
<li><b>Atropellos:</b> el fichero de accidentes de la Policía Municipal trae las coordenadas de cada accidente. De {fmt(R['atropellos_expedientes'])} atropellos de 2022 a 2025, {fmt(st['atropellos'])} tienen coordenadas válidas y {fmt(st['atropellos_red'])} quedan a menos de 15 m de un cruce o de un tramo de la red. Cada uno se asigna al cruce más cercano si está a menos de 15 m y, si no, al tramo.</li>
</ul>

<h2>Cómo se eligen las rutas</h2>
<p>Se usa el algoritmo A* sobre la red peatonal. El coste de cada tramo es su longitud multiplicada por un castigo por sol y otro por tráfico. Se suman costes fijos por cada cruce peligroso y cada atropello:</p>
<div class="box"><p style="margin:0">coste = longitud × (1 + a × (1 − sombra)) × (1 + 0,1 × k × tráfico) + k × (80 m por cruce sin semáforo, o 20 m con semáforo) + k × 30 m por atropello registrado (hasta 3)</p></div>
<p>El selector de <b>prioridad</b> cambia el peso: <i>Sombra</i> (a = 2, k = 0,5), <i>Equilibrio</i> (a = 1,5, k = 1) y <i>Seguridad</i> (a = 1, k = 2). En Paso lento, el peso de la sombra es un 80 % del anterior y los tramos con bancos, fuentes o aseos a menos de 20 m cuestan un 15 % menos. «La más corta» solo mira la longitud. El enfoque de penalizar el sol con un parámetro de aversión es el mismo que usa CoolWalks (Wolf, Vierø y Szell, <i>Scientific Reports</i>, 2025). Los pesos son decisiones de diseño y se pueden cambiar.</p>

<h2>Cuánto acierta</h2>
<h3>Comparación con la foto aérea</h3>
<p>Se ha comparado la sombra del modelo con la que se ve en la ortofoto municipal en cuatro zonas de 500 × 500 m: Lavapiés, Trafalgar, Goya y el Ensanche de Vallecas. Es una ortofoto verdadera, en la que los edificios no salen inclinados. Sombra observada: píxeles oscuros del suelo visible (umbral automático de Otsu), quitando edificios y vegetación. La hora del vuelo no se publica, así que la posición del sol se ajusta a cada imagen, como en València; sale un sol del sur ({round(min(az))}° a {round(max(az))}° de acimut) a entre {round(min(el))}° y {round(max(el))}° de altura. Después se comparan los píxeles de suelo uno a uno, a 1 m.</p>
<div class="tbl"><table><tr><th>Zona</th><th>Acierto (sombra o sol)</th><th>Sombras detectadas</th><th>Detectadas solo con árboles</th><th>Acierto en los puntos de acera</th><th>Píxeles de suelo</th></tr>{val_rows}</table></div>
<p>En las tres zonas del centro, el modelo acierta entre el {round(100 * min(v['pixeles_modelo']['exactitud'] for v in centro))} % y el {round(100 * max(v['pixeles_modelo']['exactitud'] for v in centro))} % del suelo visible y detecta entre el {round(100 * min(v['pixeles_modelo']['sensibilidad'] for v in centro))} % y el {round(100 * max(v['pixeles_modelo']['sensibilidad'] for v in centro))} % de las sombras, más que en València (entre el 64 % y el 72 % de acierto), donde la ortofoto tenía los edificios inclinados. En el Ensanche de Vallecas detecta menos sombras porque buena parte de lo que se ve oscuro no es sombra: el asfalto nuevo de las calzadas anchas es tan oscuro como una sombra y la comparación lo cuenta como tal; también se escapan las sombras pequeñas de árboles jóvenes.</p>
<h3>Sensibilidad</h3>
<p>Se ha repetido todo el cálculo cambiando las suposiciones principales:</p>
<div class="tbl"><table><tr><th>Variante</th><th>Sombra a las 13 h</th><th>Sombra a las 17 h</th><th>Orden de colegios (Spearman)</th><th>Colegios prioritarios que se mantienen</th><th>Diferencia media por tramo</th></tr>
<tr><td><b>Cálculo de la web</b></td><td>{S['base']['sombra_13h_junio']} %</td><td>{S['base']['sombra_17h_junio']} %</td><td>1</td><td>{S['base']['prioritarios']}</td><td>—</td></tr>{sens_rows}</table></div>
<p>{sens_txt}</p>

<h2>Simulador del plan de plantaciones</h2>
<p>El plan de plantaciones 2025-2026 da, para cada calle de cada distrito, la especie y el número de árboles, pero no el sitio exacto. La web pone cada árbol de calle en el punto de su calle donde más acera sombrearía entre las 13 y las 17 h de junio, en la línea de los alcorques (2 m más cerca de la calzada que la línea donde se mide la sombra) y a 8 m como mínimo de los otros árboles nuevos. Se han podido colocar {fmt(PLN['n'])} de los {fmt(PLN['n_plan'])} árboles de calle; el resto va en calles que no están en la red o en las que no cabían. Los {fmt(PLN['n_zv'])} árboles de zonas verdes no se simulan, porque el plan no dice en qué parte del parque van.</p>
<p>Cada árbol se simula ya crecido, con la copa y la altura de uno de cada cuatro árboles de calle de hoja ancha de Madrid (el percentil 75 del inventario: {dec1(rr)} m de radio de copa y {dec1(hh)} m de altura). No se usa el tamaño de cada especie porque muchas especies del plan son nuevas en las calles de Madrid y en el inventario solo hay ejemplares jóvenes. Cifras del 15 de junio:</p>
<div class="tbl"><table><tr><th>Escenario</th><th>Árboles</th><th>Sombra a las 13 h en aceras de calles con edificios</th><th>Calles casi sin sombra a las 13 h</th><th>Acera que gana sombra (de 13 a 17 h)</th><th>Colegios: subida media en 250 m</th><th>Los {PLN['n_prio']} colegios prioritarios</th></tr>{plant_rows}</table></div>
<p>Solo {fmt(PLN['near_prio'])} de los árboles de calle del plan ({round(100 * PLN['near_prio'] / PLN['n'])} %) quedan a menos de 250 m de alguno de los {PLN['n_prio']} colegios prioritarios, y esos colegios apenas ganan sombra. Con el mismo número de árboles repartido entre sus calles (unos {round(PR[1]['n'] / PLN['n_prio'])} por colegio), ganarían de media {dec1(PR[1]['prio'])} puntos de sombra en las horas de calor. La media de la ciudad casi no se mueve en ningún caso: unos miles de árboles se notan en la calle donde se plantan, no en el conjunto de {fmt(st['km_urbano'])} km de calles con edificios.</p>

<h2>Límites</h2>
<ul>
<li>No cuenta toldos, balcones, pérgolas ni la sombra de los propios árboles sobre los edificios. Tampoco la temperatura del suelo ni el viento.</li>
<li>La altura de los edificios se estima a partir de sus plantas, y el tamaño de las copas a partir del tronco: el inventario no trae la copa.</li>
<li>La posición de la acera es una aproximación, porque no hay un mapa municipal de aceras con su anchura.</li>
<li>La intensidad de tráfico se mide en puntos concretos y se extiende a toda la vía de OpenStreetMap en la que está cada punto.</li>
<li>Un atropello registrado no significa que el punto sea peligroso para todo el mundo ni a cualquier hora.</li>
<li>La vulnerabilidad de los barrios se mide con un solo indicador, la renta media por hogar, porque IGUALA publica su índice de vulnerabilidad por distrito, no por barrio.</li>
<li>La simulación del plan supone árboles ya crecidos, sanos y puestos donde más sombra darían en su calle. No sabe qué alcorques hay libres, ni las redes de servicios bajo la acera, ni los años que tarda un árbol en crecer.</li>
</ul>

<h2>Trabajos parecidos</h2>
<p><b>Cool Walks</b> (Barcelona Regional, 2021) propone rutas a la sombra en un barrio de Barcelona. En julio de 2026, el Área Metropolitana de Barcelona estrenó, en pruebas, un <b>buscador de itinerarios frescos</b> que tiene en cuenta la sombra de los edificios según la hora e indica los refugios climáticos. <b>CoolWalks</b> (Wolf, Vierø y Szell, <i>Scientific Reports</i>, 2025) estudia la posibilidad de caminar a la sombra de los edificios en Manhattan, Barcelona y València. Ruta fresca junta en una sola herramienta la sombra de cada árbol del inventario municipal según la hora, la seguridad vial con datos municipales (tráfico medido, cruces sin semáforo y atropellos), usos concretos para escolares y personas mayores, y una vista para el Ayuntamiento que cruza sombra, renta y plan de plantaciones para decidir dónde plantar. Hay también una versión para <a href="../">València</a>.</p>

<h2>Datos que se podrían mejorar</h2>
<ul>
<li>El inventario de arbolado no trae el tamaño de la copa ni el estado de cada árbol.</li>
<li>El plan de plantaciones da la calle y el número de árboles, pero no el alcorque. En el fichero, algunos nombres llevan «AV» donde va «au» (<i>Celtis AVstralis</i>, calle AVñón), seguramente por una sustitución automática.</li>
<li>No se ha encontrado en el portal un conjunto de alcorques vacíos, que permitiría simular dónde se puede plantar de verdad.</li>
<li>IGUALA publica su índice de vulnerabilidad por distrito; por barrio, solo indicadores descriptivos.</li>
</ul>

<h2>Reproducibilidad</h2>
<p>El cálculo se hace con scripts en Python (pyproj, shapely, scipy, numpy, pandas, Pillow, osmium) y la web con Leaflet 1.9.4. Los scripts leen los datos públicos, calculan la sombra y el riesgo, comprueban el modelo con la foto aérea y generan los ficheros que usa la web.</p>
<p class="cap">Ruta fresca Madrid · Ferran Sánchez-Margalef, noviembre de 2026. Origen de los datos: Ayuntamiento de Madrid. Edificios: Dirección General del Catastro (CC BY 4.0). Red peatonal: © personas colaboradoras de OpenStreetMap (ODbL).</p>
</main></body></html>"""
open(WEB + 'metodo.html', 'w', encoding='utf-8').write(html)
print('metodo.html', len(html.encode()) // 1024, 'KB')
