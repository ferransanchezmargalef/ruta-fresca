"""Lee el GML INSPIRE de Catastro (BuildingPart) y guarda polígonos y plantas sobre rasante en un .npz compacto.
Uso: python3 -I parse_catastro.py <buildingpart.gml> <salida.npz>"""
import sys
import numpy as np
from lxml import etree

GML = '{http://www.opengis.net/gml/3.2}'
BU = '{http://inspire.jrc.ec.europa.eu/schemas/bu-ext2d/2.0}'
src, dst = sys.argv[1], sys.argv[2]

floors, part_of_ring, ring_is_hole, ring_off, coords = [], [], [], [0], []
n = 0
for _, el in etree.iterparse(src, events=('end',), tag=BU + 'BuildingPart', huge_tree=True):
    nf = el.find('.//' + BU + 'numberOfFloorsAboveGround')
    try:
        f = int(nf.text) if nf is not None and nf.text else 0
    except ValueError:
        f = 0
    pid = len(floors)
    floors.append(f)
    for patch in el.iter(GML + 'PolygonPatch'):
        for kind, path in (('ext', GML + 'exterior/' + GML + 'LinearRing/' + GML + 'posList'),
                           ('hole', GML + 'interior/' + GML + 'LinearRing/' + GML + 'posList')):
            for pl in patch.findall(path):
                v = np.array(pl.text.split(), dtype=np.float64).reshape(-1, 2)
                coords.append(v)
                ring_off.append(ring_off[-1] + len(v))
                part_of_ring.append(pid)
                ring_is_hole.append(kind == 'hole')
    el.clear()
    while el.getprevious() is not None:
        del el.getparent()[0]
    n += 1
    if n % 50000 == 0:
        print('partes', n, flush=True)

xy = np.concatenate(coords)
np.savez_compressed(dst, floors=np.array(floors, np.int16), ring_part=np.array(part_of_ring, np.int32),
                    ring_hole=np.array(ring_is_hole, bool), ring_off=np.array(ring_off, np.int64), xy=xy)
fl = np.array(floors)
print('partes', len(fl), 'anillos', len(part_of_ring), 'huecos', int(np.sum(ring_is_hole)), 'vértices', len(xy))
print('plantas: p50', np.percentile(fl, 50), 'p90', np.percentile(fl, 90), 'max', fl.max(), 'ceros', int((fl == 0).sum()))
print('bbox', xy.min(0), xy.max(0))
