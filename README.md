# Ruta fresca València

Autor: Ferran Sánchez-Margalef (2026).

Web: https://ferransanchezmargalef.github.io/ruta-fresca/

También hay una versión para Madrid, con sus propios datos y su propia página de método: https://ferransanchezmargalef.github.io/ruta-fresca/madrid/ (código, datos e informes en `madrid/`, ver `madrid/README.md`).

Web que busca, para ir a pie por València, el camino con más sombra y menos riesgo a una hora y un día concretos, y lo compara con el más corto. Usa datos abiertos del Ajuntament de València, del Catastro y de OpenStreetMap.

- **Al cole / A l'escola**: de casa al colegio, con la sombra a la hora de entrada o salida y los cruces peligrosos.
- **Paso lento / Pas lent**: para personas mayores; además de sombra, busca bancos, fuentes (también las de agua fría) y aseos.
- **Ayuntamiento / Ajuntament**: sombra por calles y caminos escolares, colegios donde plantar primero, alcorques vacíos y atropellos, y un simulador de plantación que calcula cuánta sombra darían los alcorques vacíos con un árbol habitual o grande.

Interfaz en castellano y valenciano. Todo se calcula en el navegador; la web no pide ni guarda datos personales. Se puede instalar en el móvil desde el navegador («Añadir a pantalla de inicio») y, una vez abierta, vuelve a cargar sin conexión.

## Estructura

```
index.html             la web (Leaflet 1.9.4 desde jsDelivr con SRI)
metodo.html            cómo funciona, datos, validación, simulador y límites
manifest.webmanifest   instalación en el móvil
sw.js                  copia local de la web y sus datos para cargar sin conexión
icons/                 iconos
data/graph.json        red peatonal con sombra por fecha y hora, nivel de tráfico, cruces y atropellos
data/schools.json      colegios, caminos escolares y estadísticas
data/pois.json         bancos, fuentes, aseos, fuentes PUSDAR, centros de mayores, alcorques y atropellos
data/calles.json       callejero municipal con rangos de portales (búsqueda por calle y número)
data/plant.json        simulación de plantación de los alcorques vacíos (se carga al usarla)
scripts/               cálculo de los datos, página de método e iconos
informes/              validación, sensibilidad, fuentes e informe de calidad de datos
madrid/                la versión de Madrid (web, datos, scripts e informes)
```

## Publicación

La web se publica con GitHub Pages desde la rama principal y la carpeta raíz del repositorio. No necesita servidor ni base de datos.

## Recalcular los datos

Requisitos: Python 3.10+, `numpy`, `pandas`, `scipy`, `shapely>=2`, `pyproj`, `pyshp`, `lxml`, `Pillow`, `networkx`, `rapidfuzz`.

1. Descarga los datos (ver `informes/fuentes.md`) en `raw/` y `work/`.
2. `python3 scripts/parse_catastro.py raw/catastro/A.ES.SDGC.BU.46900.buildingpart.gml work/buildings.npz`
3. `python3 scripts/geocode_acc.py` (sitúa los atropellos en el mapa)
4. `RF_OUT=data/ python3 scripts/build_v3.py` (sombra por fecha y hora, seguridad, colegios, callejero y simulación de plantación)
5. `python3 scripts/validate_shadows.py 1.5 equilibrada` (comparación con la ortofoto de 2018; es opcional si no se quiere repetir la validación)
6. `RF_WEB=./ python3 scripts/make_metodo.py` (página de método con los resultados; si no se han repetido la validación ni la sensibilidad, usa las de `informes/`)
7. `RF_WEB=./ python3 scripts/make_icons.py` (iconos)
8. `python3 scripts/comprobar_web.py` (pone al día la versión de `sw.js`, para que los móviles descarguen la web nueva, y prueba la web en Chromium, también sin conexión; necesita `playwright` con Chromium y `npm`)

Para la sensibilidad: `RF_LIGHT=1 RF_OUT=work/sens_x/ RF_FLOOR_H=2.8 python3 scripts/build_v3.py` (también `RF_CROWN_K`, `RF_WALL_OFF`).

## Licencias

- Código: MIT (ver `LICENSE`).
- Datos derivados: ver `DATA_LICENSE.md`. La red peatonal deriva de OpenStreetMap y se comparte con licencia ODbL.

## Atribuciones

Ajuntament de València, portal de datos abiertos (CC BY 4.0) · Dirección General del Catastro, Catastro INSPIRE (CC BY 4.0), descargado el 7 de noviembre de 2026 · © personas colaboradoras de OpenStreetMap (ODbL) · Leaflet (BSD-2-Clause).
