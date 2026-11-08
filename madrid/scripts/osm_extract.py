"""Extrae de un .osm.pbf (Geofabrik) las vías con highway y los nodos de cruces y semáforos dentro de un recuadro,
en el mismo formato JSON que devuelve Overpass (lo que espera el cálculo de Ruta fresca).
Uso: python3 osm_extract.py <entrada.pbf> <osm.json> <osm_cross.json> lon0 lat0 lon1 lat1"""
import json, sys
import osmium

src, out_ways, out_cross = sys.argv[1:4]
lon0, lat0, lon1, lat1 = map(float, sys.argv[4:8])
inside = lambda lo, la: lon0 <= lo <= lon1 and lat0 <= la <= lat1


class H(osmium.SimpleHandler):
    def __init__(self):
        super().__init__()
        self.ways, self.nodes, self.cross = [], {}, []

    def node(self, n):
        t = n.tags
        hw, cr = t.get('highway', ''), t.get('crossing')
        if (hw in ('traffic_signals', 'crossing') or cr) and n.location.valid() and inside(n.location.lon, n.location.lat):
            self.cross.append({'type': 'node', 'id': n.id, 'lat': round(n.location.lat, 7), 'lon': round(n.location.lon, 7),
                               'tags': {k: v for k, v in (('highway', hw), ('crossing', cr), ('crossing:signals', t.get('crossing:signals'))) if v}})

    def way(self, w):
        if 'highway' not in w.tags:
            return
        locs = [(nd.ref, nd.location) for nd in w.nodes]
        if not any(l.valid() and inside(l.lon, l.lat) for _, l in locs):
            return
        ids = []
        for ref, l in locs:
            if l.valid():
                self.nodes[ref] = (round(l.lon, 7), round(l.lat, 7))
                ids.append(ref)
        self.ways.append({'type': 'way', 'id': w.id, 'nodes': ids, 'tags': dict(w.tags)})


h = H()
h.apply_file(src, locations=True)
els = [{'type': 'node', 'id': i, 'lat': la, 'lon': lo} for i, (lo, la) in h.nodes.items()] + h.ways
json.dump({'elements': els}, open(out_ways, 'w'), separators=(',', ':'))
json.dump({'elements': h.cross}, open(out_cross, 'w'), separators=(',', ':'))
print('vías', len(h.ways), 'nodos', len(h.nodes), 'cruces y semáforos', len(h.cross))
