import json, time, urllib.request, urllib.parse
UA = {'User-Agent': 'carte-immo (usage prive)'}
def get(url, data=None, t=90):
    t0 = time.time(); r = urllib.request.urlopen(urllib.request.Request(url, data=data, headers=UA), timeout=t).read(); return r, time.time() - t0
API = 'https://data.iledefrance-mobilites.fr/api/explore/v2.1/catalog/datasets/'
for ds in ['emplacement-des-gares-idf']:
    try:
        meta, _ = get(API + ds); m = json.loads(meta)
        print(ds, 'champs', [(f['name'], f['type']) for f in m.get('fields', [])])
        b, dt = get(API + ds + '/exports/geojson?limit=-1&timezone=UTC'); j = json.loads(b)
        print(ds, len(j['features']), 'objets', round(dt, 1), 's', len(b) // 1000, 'ko')
        for f in j['features'][:3]: print('  ex', json.dumps(f['properties'], ensure_ascii=False)[:400])
        modes = {}
        for f in j['features']:
            p = f['properties']; k = str(p.get('mode') or p.get('res_com') or '?'); modes[k] = modes.get(k, 0) + 1
        print('  modes', sorted(modes.items(), key=lambda x: -x[1])[:20])
        near = [f['properties'] for f in j['features'] if f.get('geometry') and 2.40 < f['geometry']['coordinates'][0] < 2.48 and 48.85 < f['geometry']['coordinates'][1] < 48.89]
        print('  autour de Montreuil/Bagnolet/Les Lilas :', len(near), [ (p.get('nom_gares') or p.get('nom_zdl') or p.get('nom'), p.get('mode') or p.get('res_com')) for p in near][:40])
    except Exception as e: print(ds, 'ERREUR', e)
for code in ['93048', '93063', '93045', '75056', '77288']:
    q = f'[out:json][timeout:20];area["boundary"="administrative"]["admin_level"="8"]["ref:INSEE"="{code}"]->.a;(nwr["railway"~"^(station|halt|tram_stop)$"](area.a);nwr["public_transport"="station"](area.a););out center tags 2500;'
    for u in ['https://overpass-api.de/api/interpreter', 'https://overpass.kumi.systems/api/interpreter']:
        try:
            b, dt = get(u, ('data=' + urllib.parse.quote(q)).encode(), 60); els = json.loads(b)['elements']
            names = sorted({(e.get('tags', {}).get('name'), e.get('tags', {}).get('railway'), e.get('tags', {}).get('station')) for e in els})
            print(code, u.split('/')[2], len(els), 'elements', round(dt, 1), 's', names[:25]); break
        except Exception as e: print(code, u.split('/')[2], 'ERREUR', e)
