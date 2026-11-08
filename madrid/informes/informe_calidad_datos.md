# Informe de calidad de datos para el portal de datos abiertos del Ayuntamiento de Madrid

Proyecto: Ruta fresca Madrid. Fecha de las comprobaciones: 8 de noviembre de 2026.

Al construir la web hemos encontrado cuatro cosas que, si se corrigen o se añaden, harían más útiles los datos para cualquier persona que los reutilice.

## 1. Plan de plantaciones 2025-2026: nombres alterados y sin ubicación

En el fichero del plan de plantaciones (conjunto «Planes de gestión del arbolado de zonas verdes y del viario») algunos textos llevan «AV» donde debería ir «au»: *Celtis AVstralis*, *Acer x freemanii 'AVtumn Blaze'*, calle «AVñón», «MAVDES». Parece el resultado de una sustitución automática de «Avenida». Además, el plan dice la calle y el número de árboles, pero no el alcorque ni las coordenadas, así que no se puede saber dónde irá cada árbol.

**Propuesta:** corregir los textos y añadir, para cada árbol, el código del alcorque o sus coordenadas.

## 2. Inventario de arbolado sin copa ni estado

El inventario (conjunto «Arbolado en parques y zonas verdes de Madrid (detalle)») trae la altura y el perímetro del tronco, pero no el diámetro de la copa ni el estado del árbol, que son lo que más importa para calcular la sombra. También hay valores imposibles: 10 árboles con más de 40 m de altura (el mayor, 1.755 m) y 6 con más de 6 m de perímetro de tronco (el mayor, 7.500 cm); 1.217 árboles no tienen altura y 279 no tienen perímetro.

**Propuesta:** añadir el diámetro de copa y el estado, como hacen otros inventarios municipales, y revisar esos valores.

## 3. Vulnerabilidad por barrio

IGUALA publica el índice de vulnerabilidad territorial agregado por distrito. Por barrio solo publica indicadores descriptivos (renta, población extranjera, abstención…). Para decidir dónde actuar primero, el barrio es la escala útil: un distrito como Fuencarral-El Pardo junta barrios muy distintos.

**Propuesta:** publicar el índice también por barrio, como hacía el ranking de vulnerabilidad de barrios hasta 2020.

## 4. Alcorques vacíos

No hemos encontrado en el portal un conjunto con los alcorques vacíos (sin árbol) de las calles. Es el dato que permite saber dónde se puede plantar sin obra.

**Propuesta:** publicar los alcorques vacíos, con su ubicación y tamaño, o añadirlos al inventario de arbolado.
