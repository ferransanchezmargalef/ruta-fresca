"""Genera app/metodo.html (cómo funciona, datos, validación y límites) a partir de los resultados reales."""
import json, os
WEB = os.environ.get('RF_WEB', 'app/')

V = json.load(open('work/validacion_1.5.json'))
S = json.load(open('work/sensibilidad.json'))
SC = json.load(open(WEB + 'data/schools.json')); st = SC['stats']
P = json.load(open(WEB + 'data/pois.json'))
fmt = lambda n: f"{n:,}".replace(',', '.')
pct = lambda x: f"{round(100 * x)} %"

val_rows = ''.join(
    f"<tr><td>{v['zona']}</td><td>{pct(v['pixeles_modelo']['exactitud'])}</td><td>{pct(v['pixeles_modelo']['sensibilidad'])}</td>"
    f"<td>{pct(v['pixeles_solo_arboles']['sensibilidad'])}</td><td>{pct(v['aceras']['acierto_modelo'])}</td><td>{fmt(v['pixeles_modelo']['n'])}</td></tr>"
    for v in V.values())
acc = [v['pixeles_modelo']['exactitud'] for v in V.values()]
rec = [v['pixeles_modelo']['sensibilidad'] for v in V.values()]
rec_t = [v['pixeles_solo_arboles']['sensibilidad'] for v in V.values()]
sens_rows = ''.join(
    f"<tr><td>{r['variante']}</td><td>{r['sombra_13h_junio']} %</td><td>{r['sombra_17h_junio']} %</td><td>{str(r['rho_colegios']).replace('.', ',')}</td>"
    f"<td>{r['prioritarios_comunes']}</td><td>{str(r['dif_media_tramos_13h']).replace('.', ',')} puntos</td></tr>" for r in S['variantes'])
datos = [
    ("Arbolado (inventario municipal)", "Ajuntament de València", "CC BY 4.0", f"{fmt(st['arboles'])} registros; {fmt(st['arboles_sombra'])} árboles vivos con copa y {fmt(st['alcorques'])} alcorques de calle sin árbol"),
    ("Bancos, fuentes de agua potable y urinarios", "Ajuntament de València", "CC BY 4.0", f"{fmt(st['bancos'])} bancos, {fmt(st['fuentes'])} fuentes y {fmt(st['urinarios'])} urinarios"),
    ("Fuentes PUSDAR (agua filtrada y fría)", "Ajuntament de València", "CC BY 4.0", f"{len(P['pusdar'])} fuentes en el conjunto publicado"),
    ("Centros educativos", "Ajuntament de València", "CC BY 4.0", f"{fmt(len(SC['schools']))} centros de infantil, primaria, secundaria y educación especial"),
    ("Caminos escolares (Colecamins)", "Ajuntament de València", "CC BY 4.0", f"{len(SC['camins'])} caminos escolares señalizados"),
    ("Vulnerabilidad por barrios y límites de los barrios", "Ajuntament de València", "CC BY 4.0", "índice global de vulnerabilidad de cada barrio"),
    ("Equipamientos para personas mayores", "Ajuntament de València", "CC BY 4.0", f"{len(P['mayores'])} centros con coordenadas"),
    ("Accidentes de tráfico 2022-2025", "Ajuntament de València", "CC BY 4.0", f"34.244 accidentes, de ellos {fmt(st['atropellos_total'])} atropellos; {fmt(st['atropellos'])} situados por su dirección"),
    ("Intensidad de tráfico por tramos", "Ajuntament de València", "CC BY 4.0", "394 tramos con aforo"),
    ("Velocidad de las calles", "Ajuntament de València", "CC BY 4.0", "12.877 tramos con su límite (50, 30, 20, peatonal…)"),
    ("Ejes de calle (callejero con rangos de portales)", "Ajuntament de València", "CC BY 4.0", "13.012 tramos de 3.262 calles"),
    ("Edificios (Catastro INSPIRE, plantas sobre rasante)", "Dirección General del Catastro", "CC BY 4.0", "214.624 partes de edificio; descargado el 7 de noviembre de 2026"),
    ("Red peatonal, pasos peatonales y semáforos", "© personas colaboradoras de OpenStreetMap", "ODbL", "43.620 vías y 16.789 pasos y semáforos"),
    ("Ortofoto 2018 (solo para validar)", "Ajuntament de València, geoportal", "—", "4 zonas de 500 × 500 m"),
]
datos_rows = ''.join(f"<tr><td>{a}</td><td>{b}</td><td>{c}</td><td>{d}</td></tr>" for a, b, c, d in datos)
sh = st['sombra_hora']

# simulador de plantación: cifras sacadas de app/data/plant.json y app/data/graph.json
import base64, statistics
PLN = json.load(open(WEB + 'data/plant.json')); GR = json.load(open(WEB + 'data/graph.json'))
dec8 = lambda x: list(base64.b64decode(x))
LEN = [l[2] for l in GR['links']]
dec1 = lambda x: f"{x:.1f}".replace('.', ',')
shh0 = [s_['shh'] for s_ in SC['schools']]; isprio = [s_['prio'] for s_ in SC['schools']]
def plant_row(sc_):
    idx = [int.from_bytes(base64.b64decode(sc_['idx'])[4 * j:4 * j + 4], 'little') for j in range(len(base64.b64decode(sc_['idx'])) // 4)]
    a, b = dec8(GR['sh'][2]), dec8(sc_['sh'][2]); num = den = 0.0
    for j, i in enumerate(idx):
        if b[j] != a[i]: num += (b[j] - a[i]) * LEN[i]; den += LEN[i]
    g = [x - y for x, y in zip(sc_['sc_shh'], shh0)]; gp = [x for x, q in zip(g, isprio) if q]
    pit = dec8(sc_['pit'])
    return {'sh13': sc_['stats1']['sombra_hora'][0][2], 'sin13': sc_['stats1']['sin_sombra_hora'][0][2], 'tramos': round(num / den),
            'acera': round(statistics.median(pit)), 'cero': sum(1 for v in pit if v == 0), 'col': sum(g) / len(g), 'colmax': max(g), 'prio': sum(gp) / len(gp), 'priomax': max(gp)}
PR = [plant_row(x) for x in PLN['sc']]
B1 = PLN['base1']
pits_prio = sum(s_['pits'] for s_ in SC['schools'] if s_['prio']) / sum(isprio)
pits_rest = sum(s_['pits'] for s_ in SC['schools'] if not s_['prio']) / (len(isprio) - sum(isprio))
plant_rows = (f"<tr><td>Ahora</td><td>{dec1(B1['sombra_hora'][0][2])} %</td><td>{dec1(B1['sin_sombra_hora'][0][2])} %</td><td>—</td><td>—</td><td>—</td><td>—</td></tr>" +
    ''.join(f"<tr><td>{nm}</td><td>{dec1(r['sh13'])} %</td><td>{dec1(r['sin13'])} %</td><td>+{r['tramos']} puntos</td><td>{r['acera']} m</td><td>+{dec1(r['col'])} (máx. +{r['colmax']})</td><td>+{dec1(r['prio'])} (máx. +{r['priomax']})</td></tr>"
            for nm, r in zip(['Árbol habitual (copa y altura de 4 a 8 m)', 'Árbol grande (copa y altura de 8 a 12 m)'], PR)))

html = f"""<!DOCTYPE html>
<html lang="es"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Ruta fresca · Cómo funciona</title>
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
.back{{font-weight:600}} code{{font-size:14px;background:var(--panel);border:1px solid var(--line);border-radius:5px;padding:1px 5px}}
.tbl{{overflow-x:auto;border:1px solid var(--line);border-radius:10px;background:var(--panel)}}
table{{border-collapse:collapse;width:100%;font-size:14px;font-variant-numeric:tabular-nums}}
th,td{{text-align:left;padding:8px 10px;border-bottom:1px solid var(--line);vertical-align:top}} th{{font-weight:700;background:var(--paper)}}
tr:last-child td{{border-bottom:0}}
.box{{background:var(--panel);border:1px solid var(--line);border-radius:12px;padding:14px 18px}}
.cap{{font-size:13.5px;color:var(--muted)}}
</style></head><body><main>
<p><a class="back" href="index.html">← Volver a la app</a></p>
<h1><span>Ruta fresca</span>: cómo funciona</h1>
<p class="lead">Qué datos usa, cómo calcula la sombra y el riesgo de cada calle, cómo elige las rutas, cuánto acierta y qué no sabe hacer todavía.</p>

<h2>Qué hace</h2>
<p>Ruta fresca busca, para ir a pie por València, el camino con más sombra y menos riesgo a una hora y un día concretos, y lo compara con el más corto. Tiene tres usos:</p>
<ul>
<li><b>Al cole:</b> de casa al colegio, con la sombra a la hora de entrada o de salida.</li>
<li><b>Paso lento:</b> para personas mayores, que además necesitan parar; la ruta prefiere tramos con bancos, fuentes y aseos cerca.</li>
<li><b>Ayuntamiento:</b> dónde falta sombra alrededor de los colegios, cuánta sombra tiene cada camino escolar oficial, dónde están los alcorques vacíos y los atropellos, y cuánta sombra darían los alcorques vacíos si se plantaran.</li>
</ul>
<p>Todo se calcula en el navegador: la app no pide ni guarda datos personales.</p>

<h2>Datos</h2>
<div class="tbl"><table><tr><th>Conjunto</th><th>Fuente</th><th>Licencia</th><th>Qué se usa</th></tr>{datos_rows}</table></div>
<p class="cap">Datos municipales descargados en noviembre de 2026 del portal de datos abiertos del Ajuntament de València. La red peatonal deriva de OpenStreetMap y se comparte con la misma licencia (ODbL).</p>

<h2>Cómo se calcula la sombra</h2>
<h3>Cuándo</h3>
<p>Para dos días del curso escolar con calor: el <b>15 de junio</b>, con el sol más alto (el caso con menos sombra), y el <b>15 de septiembre</b>. Seis horas de cada día, en horario oficial de verano: 9, 11, 13, 15, 17 y 19 h. La posición del sol se calcula con el algoritmo de baja precisión del Astronomical Almanac (error menor de 0,1°).</p>
<h3>Edificios</h3>
<p>Cada parte de edificio del Catastro tiene su número de plantas sobre rasante. Su altura se estima en 3 m por planta más 1 m de planta baja, y se dibuja en un mapa de alturas de 1 × 1 m de toda la ciudad. Un punto de la acera está a la sombra si, mirando hacia el sol, algún edificio queda por encima de la línea del sol.</p>
<h3>Árboles</h3>
<p>Cada árbol vivo del inventario proyecta una copa circular con el radio de su clase de copa (de 1,5 a 6,5 m). La sombra se desplaza en la dirección contraria al sol según la altura de la copa. No todos los árboles dan la misma sombra: caducifolios y perennes cuentan entero, coníferas un 80 %, arbustos la mitad y palmeras un 35 %. Los árboles en mal estado cuentan menos, y los alcorques vacíos, tocones y árboles secos no dan sombra.</p>
<h3>Aceras</h3>
<p>Cada tramo de calle se mide cada 4 m en sus dos aceras. Si hay fachadas a menos de 25 m, la acera se sitúa a 1,5 m de la fachada; si no, a una distancia según el tipo de vía. Cada tramo toma la acera más sombreada, porque se puede cambiar de acera.</p>
<p>Resultado: a las 13 h del 15 de junio, las aceras de las calles con edificios están a la sombra un {sh[0][2]} % de su longitud de media; a las 17 h, un {sh[0][4]} %. La mayor parte la dan los edificios. Los árboles marcan la diferencia en avenidas anchas y zonas abiertas.</p>

<h2>Cómo se mide el riesgo</h2>
<ul>
<li><b>Nivel de tráfico de cada calle (0 a 3):</b> el mayor entre su clase de vía en OpenStreetMap, su límite de velocidad municipal (40-50 km/h) y, si tiene aforo municipal, su intensidad de tráfico frente al resto de tramos aforados.</li>
<li><b>Cruces peligrosos:</b> cuando la ruta atraviesa una calle de nivel 2 o 3 en una intersección. Se mira si hay semáforo en un radio de 25 m (OpenStreetMap). En la ciudad hay {fmt(st['cruces_trafico'])} cruces con calles de tráfico, {fmt(st['cruces_sin_semaforo'])} de ellos sin semáforo.</li>
<li><b>Atropellos:</b> el fichero municipal de accidentes no trae coordenadas, solo la dirección («C/ A cruce C/ B» o «AV A 23»), en castellano, mientras que el callejero municipal está en valenciano. Se emparejan los nombres con reglas de traducción y búsqueda aproximada. Un cruce se acepta solo si los ejes de las dos calles se tocan (a menos de 30 m), y un portal solo si su número cae en el rango de portales del tramo. Así se han situado {fmt(st['atropellos'])} de los {fmt(st['atropellos_total'])} atropellos de 2022-2025 ({round(100 * st['atropellos'] / st['atropellos_total'])} %). Cada atropello se asigna al cruce más cercano si está a menos de 15 m y, si no, al tramo.</li>
</ul>

<h2>Cómo se eligen las rutas</h2>
<p>Se usa el algoritmo A* sobre la red peatonal. El coste de cada tramo es su longitud multiplicada por un castigo por sol y otro por tráfico. Se suman costes fijos por cada cruce peligroso y cada atropello:</p>
<div class="box"><p style="margin:0">coste = longitud × (1 + a × (1 − sombra)) × (1 + 0,1 × k × tráfico) + k × (80 m por cruce sin semáforo, o 20 m con semáforo) + k × 30 m por atropello registrado (hasta 3)</p></div>
<p>El selector de <b>prioridad</b> cambia el peso: <i>Sombra</i> (a = 2, k = 0,5), <i>Equilibrio</i> (a = 1,5, k = 1) y <i>Seguridad</i> (a = 1, k = 2). En Paso lento, el peso de la sombra es un 80 % del anterior y los tramos con bancos, fuentes o aseos a menos de 20 m cuestan un 15 % menos. «La más corta» solo mira la longitud. El enfoque de penalizar el sol con un parámetro de aversión es el mismo que usa CoolWalks (Wolf, Vierø y Szell, <i>Scientific Reports</i>, 2025). Los pesos concretos son decisiones de diseño y pueden cambiarse; la tabla de sensibilidad muestra que las conclusiones no dependen de ellos.</p>

<h2>Cuánto acierta</h2>
<h3>Comparación con la foto aérea</h3>
<p>Se ha comparado la sombra del modelo con la que se ve en la ortofoto municipal de 2018 en cuatro zonas de 500 × 500 m. Sombra observada: píxeles oscuros del suelo visible (umbral automático de Otsu), quitando edificios y vegetación. La hora del vuelo no se publica, así que se ajusta la posición del sol (dos números) a cada imagen. Después se comparan miles de píxeles de suelo.</p>
<div class="tbl"><table><tr><th>Zona</th><th>Acierto (sombra o sol)</th><th>Sombras detectadas</th><th>Detectadas solo con árboles</th><th>Acierto en los puntos de acera</th><th>Píxeles de suelo</th></tr>{val_rows}</table></div>
<p>El modelo acierta entre el {round(100 * min(acc))} % y el {round(100 * max(acc))} % del suelo visible. Detecta entre el {round(100 * min(rec))} % y el {round(100 * max(rec))} % de las sombras observadas; con solo árboles detectaría entre el {round(100 * min(rec_t))} % y el {round(100 * max(rec_t))} %. Los errores se concentran junto a las fachadas: en una ortofoto los edificios altos aparecen inclinados y tapan parte de la acera. También influye que el arbolado es de 2026 y la foto de 2018. Por eso la comparación en los puntos de acera es más baja.</p>
<h3>Sensibilidad</h3>
<p>Se ha repetido todo el cálculo cambiando las suposiciones principales:</p>
<div class="tbl"><table><tr><th>Variante</th><th>Sombra a las 13 h</th><th>Sombra a las 17 h</th><th>Orden de colegios (Spearman)</th><th>Colegios prioritarios que se mantienen</th><th>Diferencia media por tramo</th></tr>
<tr><td><b>Cálculo de la app</b></td><td>{S['base']['sombra_13h_junio']} %</td><td>{S['base']['sombra_17h_junio']} %</td><td>1</td><td>{S['base']['prioritarios']}</td><td>—</td></tr>{sens_rows}</table></div>
<p>Las cifras globales se mueven unos pocos puntos. El orden de los colegios y la lista de prioritarios apenas cambian. Las conclusiones de la app no dependen de esas suposiciones.</p>

<h2>Simulador de plantación</h2>
<p>La vista del Ayuntamiento simula un árbol ya crecido y sano en cada uno de los {fmt(PLN['n'])} alcorques de calle sin árbol, con el mismo modelo de sombra que el resto de árboles. Hay dos tamaños: el <b>árbol habitual</b>, con la clase de copa y de altura más frecuentes entre los árboles de calle del inventario (de 4 a 8 m; radio de copa de 3 m y 6 m de altura en el cálculo), y un <b>árbol grande</b>, de 8 a 12 m (radio de 5 m y 10 m de altura). Cifras del 15 de junio:</p>
<div class="tbl"><table><tr><th>Escenario</th><th>Sombra a las 13 h en aceras de calles con edificios</th><th>Calles casi sin sombra a las 13 h</th><th>Subida en los tramos donde se planta (13 h)</th><th>Acera que gana sombra por árbol (mediana, 13 a 17 h)</th><th>Colegios: subida media en 250 m (13 a 17 h)</th><th>Los {sum(isprio)} colegios prioritarios</th></tr>{plant_rows}</table></div>
<p>Plantar los alcorques vacíos se nota mucho en la calle donde se planta, pero mueve poco la media de la ciudad. {fmt(PR[0]['cero'])} de los {fmt(PLN['n'])} alcorques ({round(100 * PR[0]['cero'] / PLN['n'])} %) apenas darían sombra nueva a la acera con el árbol habitual, porque a esas horas ya está a la sombra o porque la sombra del árbol cae fuera de ella. Los colegios prioritarios tienen menos alcorques vacíos cerca ({round(pits_prio)} de media, frente a {round(pits_rest)} en el resto) y ganarían poco: para darles sombra harían falta alcorques nuevos, además de reponer los que faltan. El mapa destaca el 25 % de alcorques que más sombra darían.</p>

<h2>Límites</h2>
<ul>
<li>No cuenta toldos, balcones, pérgolas ni la sombra de los propios árboles sobre los edificios. Tampoco la temperatura del suelo ni el viento.</li>
<li>La altura de los edificios se estima a partir de sus plantas. No hay datos de altura real de las copas, solo clases.</li>
<li>La posición de la acera es una aproximación, porque no hay un mapa municipal de aceras con su anchura.</li>
<li>La foto aérea de comparación es de 2018 y no se sabe la hora del vuelo.</li>
<li>Sin coordenadas en el fichero de accidentes, {fmt(st['atropellos_total'] - st['atropellos'])} atropellos no se han podido situar con seguridad. Un atropello registrado no significa que el punto sea peligroso para todo el mundo ni a cualquier hora.</li>
<li>Los refugios climáticos municipales no están: no hay un conjunto de datos abierto y el enlace oficial a su mapa no funciona.</li>
<li>La simulación de plantación supone árboles ya crecidos y sanos en todos los alcorques vacíos de calle. No tiene en cuenta el tamaño de cada alcorque, las redes de servicios bajo la acera ni los años que tarda un árbol en crecer.</li>
</ul>

<h2>Trabajos parecidos</h2>
<p><b>Cool Walks</b> (Barcelona Regional, 2021) propone rutas a la sombra en un barrio de Barcelona. En julio de 2026, el Área Metropolitana de Barcelona estrenó, en pruebas, un <b>buscador de itinerarios frescos</b> que tiene en cuenta la sombra de los edificios según la hora e indica los refugios climáticos. <b>CoolWalks</b> (Wolf, Vierø y Szell, <i>Scientific Reports</i>, 2025) estudia la posibilidad de caminar a la sombra de los edificios en Manhattan, Barcelona y València. Ruta fresca junta en una sola herramienta:</p>
<ul>
<li>la sombra de cada árbol del inventario municipal, según su tipo, estado y la hora;</li>
<li>la seguridad vial con datos municipales (velocidad, tráfico, cruces sin semáforo y atropellos);</li>
<li>usos concretos para escolares y personas mayores;</li>
<li>una vista para el Ayuntamiento que cruza sombra, alcorques vacíos y vulnerabilidad para decidir dónde plantar.</li>
</ul>
<p>Como referencia de arbolado urbano se puede usar la regla 3-30-300 (Konijnendijk, 2021), que pide al menos un 30 % de copa de árbol en cada barrio.</p>

<h2>Datos que se podrían mejorar</h2>
<ul>
<li>El fichero de accidentes 2022-2025 no trae coordenadas.</li>
<li>El listado de calles en CSV trae justo 2.000 filas, menos calles de las que hay en el callejero (3.262).</li>
<li>El conjunto de fuentes PUSDAR tiene {len(P['pusdar'])} fuentes; el Ayuntamiento habla de 77 fuentes urbanas PUSDAR.</li>
<li>La red de refugios climáticos no tiene conjunto abierto y el enlace a su mapa da error.</li>
</ul>

<h2>Reproducibilidad</h2>
<p>El cálculo se hace con scripts en Python (pyproj, shapely, scipy, numpy, Pillow) y la app con Leaflet 1.9.4. Los scripts descargan los datos públicos, calculan la sombra y el riesgo, comprueban el modelo con la foto aérea y generan los ficheros que usa la app.</p>
<p class="cap">Ruta fresca · Ferran Sánchez-Margalef, noviembre de 2026. Atribuciones: Ajuntament de València (CC BY 4.0); Dirección General del Catastro (CC BY 4.0); © personas colaboradoras de OpenStreetMap (ODbL).</p>
</main></body></html>"""
open(WEB + 'metodo.html', 'w', encoding='utf-8').write(html)
print('metodo.html', len(html.encode()) // 1024, 'KB')
