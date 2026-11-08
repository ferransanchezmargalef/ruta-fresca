# Fuentes y descarga de datos (Madrid)

Datos descargados del 6 al 8 de noviembre de 2026.

## Ayuntamiento de Madrid (portal CKAN: https://datos.madrid.es)

Se consultan con la API CKAN (`/api/3/action/package_show?id=...`) y se descargan los recursos de cada conjunto. Las descargas se hicieron despacio, una a una, porque el portal bloquea durante unos minutos a quien pide muchos ficheros seguidos.

| Conjunto (id CKAN) | Fichero usado | Uso |
|---|---|---|
| Arbolado en parques y zonas verdes de Madrid (detalle) (`300761-0-arbolado-especies`) | inventario de julio de 2026 y tabla de especies | sombra de los árboles |
| Mobiliario urbano. Bancos (`300095-0-mobiliario-bancos`) | bancos 2026 | puntos de descanso |
| Fuentes de agua para beber (`300051-0-fuentes`) | fuentes 2026 | puntos de descanso |
| Aseos públicos fijos con publicidad (`300103-0-aseos-publicos-operativos`) | aseos | puntos de descanso |
| Centros educativos en Madrid (`300614-0-centros-educativos`) | centros educativos | colegios |
| Centros municipales de mayores (`200337-0-centros-mayores`) | centros de mayores | destinos de Paso lento |
| Accidentes de tráfico de la ciudad de Madrid (`300228-0-accidentes-trafico-detalle`) | 2022, 2023, 2024 y 2025 | atropellos |
| Tráfico. Ubicación de los puntos de medida del tráfico (`202468-0-intensidad-trafico`) | puntos de medida | nivel de tráfico |
| Tráfico. Histórico de datos del tráfico desde 2013 (`208627-0-transporte-ptomedida-historico`) | `06-2026.zip` | nivel de tráfico |
| Callejero oficial del Ayuntamiento de Madrid (`213605-0-callejero-oficial-madrid`) | direcciones (portales) | búsqueda por calle y número |
| Barrios municipales de Madrid (`300496-0-barrios-madrid`) | `Barrios.zip` (shapefile, ETRS89 UTM 30N) | término municipal, distritos y barrios |
| IGUALA. Índice de vulnerabilidad territorial agregado (`300577-0-iguala-vulnerabilidad`) | `informe_globales.xlsx` | renta por barrio, índice por distrito |
| Planes de gestión del arbolado de zonas verdes y del viario (`300142-0-poda-arbolado`) | plan de plantaciones 2025-2026 | simulador |
| Ortofoto actualizada (`300740-0-ortofoto-cubierta-mosaico`) | WMS `servpub.madrid.es/georaster/ORTOFOTOS/ORTOFOTO_MADRID/ows`, capa `ORTOFOTO_MADRID`, 4 recortes de 500 × 500 m a 0,25 m | solo validación |

## Catastro (https://www.catastro.hacienda.gob.es/INSPIRE/buildings/ES.SDGC.BU.atom.xml)

Fichero del municipio de Madrid: `A.ES.SDGC.BU.28900` (partes de edificio con plantas sobre rasante), descargado el 7 de noviembre de 2026.

## OpenStreetMap (extracto de Geofabrik)

Extracto de la Comunidad de Madrid del 6 de noviembre de 2026 (`.osm.pbf`), recortado con `scripts/osm_extract.py` al recuadro -3,90 40,30 -3,50 40,65:

- Red peatonal: vías `highway` caminables (aceras, calles, sendas, escaleras, calles peatonales…).
- Pasos de peatones y semáforos: nodos `highway=traffic_signals`, `highway=crossing` y `crossing=*`.
