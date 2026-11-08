# Ruta fresca Madrid

Autor: Ferran Sánchez-Margalef (2026).

Web: https://ferransanchezmargalef.github.io/ruta-fresca/madrid/

Web que busca, para ir a pie por Madrid, el camino con más sombra y menos riesgo a una hora y un día concretos, y lo compara con el más corto. Usa datos abiertos del Ayuntamiento de Madrid, del Catastro y de OpenStreetMap.

- **Al cole**: de casa al colegio o a la escuela infantil, con la sombra a la hora de entrada o salida, los cruces peligrosos y los atropellos registrados.
- **Paso lento**: para personas mayores; además de sombra, busca bancos, fuentes de beber y aseos públicos.
- **Ayuntamiento**: sombra por distritos, colegios con poca sombra en barrios de renta baja, atropellos, y un simulador que calcula cuánta sombra darían los árboles de calle del plan de plantaciones 2025-2026, en sus calles o junto a esos colegios.

Todo se calcula en el navegador; la web no pide ni guarda datos personales. Las calles se cargan por cuadrículas de unos 2 km cuando hacen falta. Se puede instalar en el móvil desde el navegador y vuelve a abrir sin conexión lo que ya se ha visto.

## Estructura

```
madrid/index.html             la web (Leaflet 1.9.4 desde jsDelivr con SRI)
madrid/metodo.html            cómo funciona, datos, validación, sensibilidad, simulador y límites
madrid/manifest.webmanifest   instalación en el móvil
madrid/sw.js                  copia local de la web y de los datos ya usados, para cargar sin conexión
madrid/icons/                 iconos
madrid/data/index.json        índice de cuadrículas, horas, fechas y posición del sol
madrid/data/t/*.json          red peatonal por cuadrículas: sombra por fecha y hora, tráfico, cruces, atropellos y bancos
madrid/data/overview.json     sombra media en celdas de unos 250 m (vista de lejos)
madrid/data/schools.json      colegios, centros de mayores, estadísticas de la ciudad y de cada distrito
madrid/data/pois.json         atropellos, fuentes de beber y aseos
madrid/data/calles.json       portales del callejero municipal (búsqueda por calle y número)
madrid/data/plant.json        simulación del plan de plantaciones (se carga al usarla)
madrid/src/                   plantilla de la web, manifiesto y service worker
madrid/scripts/               cálculo de los datos, validación, sensibilidad, página de método y montaje de la web
madrid/informes/              validación, sensibilidad, resumen del cálculo, fuentes e informe de calidad de datos
```

## Recalcular los datos

Requisitos: Python 3.10+, `numpy`, `pandas`, `scipy`, `shapely>=2`, `pyproj`, `pyshp`, `lxml`, `Pillow`, `networkx`, `osmium`, `openpyxl`; para probar la web, `playwright` con Chromium. Los pasos se ejecutan desde esta carpeta, `madrid/`, que durante el cálculo tiene también `raw/` (descargas), `work/` (intermedios) y `app/` (la web nueva); ninguna de las tres se sube al repositorio. Al terminar, el contenido de `app/` se copia aquí, en `madrid/`, que es lo que se publica. El ráster de alturas de toda la ciudad ocupa 1 GB y el cálculo completo necesita unos 5 GB de memoria.

1. Descarga los datos (ver `informes/fuentes.md`) en `raw/` con estos nombres: `raw/ayto2/` (`accidentes_2022.csv` … `accidentes_2025.csv`, `bancos_2026.csv`, `fuentes_2026.csv`, `aseos.csv`, `centros_educativos.csv`, `centros_mayores.csv`, `callejero_direcciones.csv`, `trafico_puntos.csv`, `iguala_informe_globales.xlsx`, `plan_plantaciones_2025-2026.csv`, `arbolado.csv`, `arbolado_tabla_1.xlsx`), `raw/barrios/BARRIOS.*`, `raw/trafico/06-2026.csv`, `raw/orto/<zona>.jpg` y el `.osm.pbf` y el `.gml` del Catastro.
2. `python3 -I ../scripts/parse_catastro.py raw/A.ES.SDGC.BU.28900.buildingpart.gml work/buildings.npz` (el mismo script que en València)
3. `python3 -I scripts/osm_extract.py raw/osm_madrid.pbf work/osm.json raw/osm_cross.json -3.90 40.30 -3.50 40.65`
4. `python3 -I scripts/trees_madrid.py raw/ayto2/arbolado.csv raw/ayto2/arbolado_tabla_1.xlsx work/trees.pkl`
5. `python3 -I scripts/trafico_madrid.py raw/trafico/06-2026.csv raw/ayto2/trafico_puntos.csv work/trafico_puntos.json`
6. `python3 -I scripts/atropellos_madrid.py work/atropellos.json raw/ayto2/accidentes_2022.csv raw/ayto2/accidentes_2023.csv raw/ayto2/accidentes_2024.csv raw/ayto2/accidentes_2025.csv`
7. `python3 -I scripts/build_madrid.py` (sombra por fecha y hora, seguridad, colegios, cuadrículas, callejero y simulador; unos 10 minutos)
8. `python3 -I scripts/validate_madrid.py` (comparación con la ortofoto; opcional)
9. `scripts/run_sens.sh` y `python3 scripts/resumen_sensibilidad.py` (sensibilidad; opcional, una hora)
10. `python3 scripts/elegir_ejemplos.py` (ejemplos que se ven al abrir la web)
11. `python3 scripts/make_metodo_madrid.py` y `python3 scripts/montar_web.py` (página de método, versión de `sw.js` y copia de prueba; necesita Leaflet 1.9.4 en `vendor/package`, de `npm pack leaflet@1.9.4`)
12. `python3 scripts/probar.py` (prueba la web en Chromium, también sin conexión)
13. `python3 -I scripts/estudio_entornos.py` (estudio de los entornos escolares: cifras en `work/estudio.json` y mapa en `work/estudio_mapa.png`; usa la web ya montada en `app/` y necesita además `matplotlib`)

## Atribuciones

Origen de los datos: Ayuntamiento de Madrid (portal de datos abiertos) · Dirección General del Catastro, Catastro INSPIRE (CC BY 4.0), descargado el 7 de noviembre de 2026 · © personas colaboradoras de OpenStreetMap (ODbL) · Leaflet (BSD-2-Clause).
