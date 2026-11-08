#!/bin/bash
# Sensibilidad del cálculo de sombra de Madrid: cada variante recalcula la sombra con un parámetro cambiado (unos 10 minutos cada una).
cd "$(dirname "$0")/.."
run() { [ -f work/sens_$1/sens.json ] && return; mkdir -p work/sens_$1/; env RF_LIGHT=1 RF_OUT=work/sens_$1/ $2 python3 -I scripts/build_madrid.py > work/sens_$1/log.txt 2>&1; echo "$1 $(date +%T)" >> work/sens_progress.txt; }
run base ""
run piso28 "RF_FLOOR_H=2.8"
run piso33 "RF_FLOOR_H=3.3"
run copa08 "RF_CROWN_K=0.8"
run copa12 "RF_CROWN_K=1.2"
run acera10 "RF_WALL_OFF=1.0"
run acera25 "RF_WALL_OFF=2.5"
echo ALL >> work/sens_progress.txt
