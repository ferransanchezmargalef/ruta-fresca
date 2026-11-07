# Fuentes y descarga de datos

Datos descargados el 7 de noviembre de 2026.

## Ajuntament de València (portal CKAN: https://opendata.vlci.valencia.es)

Se consultan con la API CKAN (`/api/3/action/package_show?id=...`). Las capas geográficas se sirven desde `https://geoportal.valencia.es/server/rest/services/OPENDATA/...` (ArcGIS REST, máximo 1.000-2.000 registros por consulta, se pagina con `resultOffset`).

| Conjunto (id CKAN) | Uso |
|---|---|
| arbolado (inventario de arbolado) | sombra de árboles, alcorques vacíos |
| bancos, fuentes de agua potable, urinarios | puntos de descanso |
| pudsar-sources (fuentes PUSDAR) | fuentes de agua fría |
| centros educativos | colegios |
| colecamins (caminos escolares) | sombra de los caminos escolares |
| vulnerabilidad por barrios, barrios | prioridad de plantación, límite municipal |
| equipamientos de personas mayores | destinos de Paso lento |
| siniestros-de-trafico-2022-2025 | atropellos |
| intensitat-transit-trams-intensidad-trafico-tramos | nivel de tráfico |
| velocitat-carrers-velocidad-calles (`geoportal.valencia.es/apps/OpenData/Trafico/Trafico__223.zip`) | límite de velocidad |
| eixos-lineals-dels-carrers (`geoportal.valencia.es/apps/OpenData/UrbanismoEInfraestructuras/UrbanismoEInfraestructuras__223.zip`) | callejero, rangos de portales, ubicación de atropellos |
| FotoAerea_2018 (MapServer `export`) | solo validación |

## Catastro (https://www.catastro.hacienda.gob.es/INSPIRE/buildings/ES.SDGC.BU.atom.xml)

Fichero del municipio de València: `INSPIRE/Buildings/46/46900-VALENCIA/A.ES.SDGC.BU.46900.zip` (partes de edificio con plantas sobre rasante).

## OpenStreetMap (Overpass API)

- Red peatonal: vías `highway` dentro de 39.425,-0.430,39.510,-0.305.
- Pasos peatonales y semáforos: nodos `highway=traffic_signals`, `highway=crossing` y `crossing=*` dentro de 39.40,-0.44,39.52,-0.29.
