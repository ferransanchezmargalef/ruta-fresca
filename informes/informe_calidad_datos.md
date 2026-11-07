# Informe de calidad de datos para el portal de datos abiertos del Ajuntament de València

Proyecto: Ruta fresca València. Fecha de las comprobaciones: 7 de noviembre de 2026.

Al construir la aplicación hemos encontrado cuatro cosas que, si se corrigen, harían más útiles los datos para cualquier persona que los reutilice.

## 1. Accidentes de tráfico 2022-2025 sin coordenadas

El conjunto «Accidentes de tráfico 2022-2025» (34.244 registros) solo trae la ubicación escrita, por ejemplo «C/ JUAN BAUTISTA LLOVERA cruce C/ PADRE PORTA» o «AV PERIS Y VALERO 133». Los nombres están en castellano, mientras que el callejero municipal (ejes de calle) usa la denominación oficial en valenciano. El fichero está codificado en ISO-8859-1 sin indicarlo.

Para situarlos hemos tenido que emparejar los nombres con reglas de traducción y búsqueda aproximada. Hemos situado 1.472 de los 1.632 atropellos (90 %).

**Propuesta:** añadir las coordenadas (ETRS89 / UTM 30N) o, al menos, el código de vía (`codvia`) y el número de portal; publicar el CSV en UTF-8.

## 2. Listado de calles truncado

El CSV del conjunto «Llistat dels carrers» trae exactamente 2.000 filas. La capa de ejes de calle tiene 3.262 calles distintas, así que el listado parece cortado por un límite de exportación.

**Propuesta:** regenerar el CSV completo.

## 3. Fuentes PUSDAR incompletas

El conjunto de fuentes PUSDAR del portal recoge 25 fuentes. Una noticia municipal sobre las medidas contra el calor habla de 77 fuentes urbanas PUSDAR.

**Propuesta:** actualizar el conjunto con todas las fuentes y, si es posible, su estado (en servicio o no).

## 4. Red de refugios climáticos sin datos abiertos

La red municipal de refugios climáticos (40 equipamientos en julio de 2026) no tiene un conjunto de datos abierto. El enlace oficial «Consulta AQUÍ toda la información de la RED DE REFUGIOS CLIMÁTICOS», en la página de Energías renovables y cambio climático de valencia.es, lleva a climaienergia.com y devuelve un error 404.

**Propuesta:** publicar los refugios como conjunto abierto, con ubicación, horario, periodo de apertura y accesibilidad, y corregir el enlace.
