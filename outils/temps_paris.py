#!/usr/bin/env python3
"""Temps moyen de chaque gare d'Île-de-France jusqu'à Paris, d'après les horaires officiels (GTFS IDFM).

Pour chaque gare ou station hors de Paris (train, RER, métro, tram) : les trains directs d'un jour de semaine
qui en partent aux heures de pointe (6 h-9 h et 18 h-21 h) et entrent ensuite dans Paris. Le temps retenu est
la moyenne des durées jusqu'au premier arrêt dans Paris ; on garde aussi le nom de cet arrêt et la ligne.
Quand une gare a à la fois des trains directs (ou semi-directs) et des omnibus, nettement différents par le nombre
d'arrêts intermédiaires, on donne aussi le temps de chacun des deux groupes.
Résultat écrit dans site/transports.html, entre /*TEMPS_PARIS_DEBUT*/ et /*TEMPS_PARIS_FIN*/.

Usage : python3 outils/temps_paris.py [gtfs.zip] [site/transports.html]
"""
import csv, datetime as dt, io, json, os, re, statistics, sys, unicodedata, urllib.request, zipfile
from collections import defaultdict, Counter

GTFS_URLS = [
    'https://eu.ftp.opendatasoft.com/stif/GTFS/IDFM-gtfs.zip',
    'https://data.iledefrance-mobilites.fr/api/datasets/1.0/offre-horaires-tc-gtfs-idfm/attachments/idfm_gtfs_zip/',
]
PERIODES = [(6 * 3600, 9 * 3600), (18 * 3600, 21 * 3600)]
MODES = {'0': 'tram', '1': 'metro', '2': 'train', '7': 'funiculaire', '12': 'monorail'}
UA = {'User-Agent': 'carte-transports (usage prive)'}


def get(url, timeout=300):
    return urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=timeout).read()


def norm(s):
    s = unicodedata.normalize('NFD', s or '')
    s = ''.join(c for c in s if unicodedata.category(c) != 'Mn').lower()
    return re.sub(r'[^a-z0-9]+', ' ', s).strip()


def paris_poly():
    j = json.loads(get('https://geo.api.gouv.fr/communes/75056?fields=contour&format=json', 60))
    g = j['contour']
    return [p[0] for p in (g['coordinates'] if g['type'] == 'MultiPolygon' else [g['coordinates']])]


def inside(x, y, rings):
    for r in rings:
        ins, j = False, len(r) - 1
        for i in range(len(r)):
            xi, yi = r[i]; xj, yj = r[j]
            if (yi > y) != (yj > y) and x < (xj - xi) * (y - yi) / (yj - yi) + xi:
                ins = not ins
            j = i
        if ins:
            return True
    return False


def hms(t):
    h, m, s = (int(v) for v in t.split(':'))
    return h * 3600 + m * 60 + s


def lire(z, nom):
    with z.open(nom) as f:
        yield from csv.DictReader(io.TextIOWrapper(f, encoding='utf-8-sig'))


def jour_type(z):
    """Un mardi couvert par les horaires (le prochain, ou le premier de la période)."""
    debut, fin = None, None
    try:
        for r in lire(z, 'calendar.txt'):
            a, b = r['start_date'], r['end_date']
            debut = a if not debut or a < debut else debut
            fin = b if not fin or b > fin else fin
    except KeyError:
        pass
    d = dt.date.today() + dt.timedelta(days=1)
    if debut:
        d = max(d, dt.datetime.strptime(debut, '%Y%m%d').date())
    while d.weekday() != 1:
        d += dt.timedelta(days=1)
    return d


def services(z, d):
    ok, ds, jour = set(), d.strftime('%Y%m%d'), ['monday', 'tuesday', 'wednesday', 'thursday', 'friday', 'saturday', 'sunday'][d.weekday()]
    try:
        for r in lire(z, 'calendar.txt'):
            if r['start_date'] <= ds <= r['end_date'] and r[jour] == '1':
                ok.add(r['service_id'])
    except KeyError:
        pass
    try:
        for r in lire(z, 'calendar_dates.txt'):
            if r['date'] == ds:
                (ok.add if r['exception_type'] == '1' else ok.discard)(r['service_id'])
    except KeyError:
        pass
    return ok


def libelle(mode, n):
    if mode == 'train':
        return ('RER ' if n in ('A', 'B', 'C', 'D', 'E') else 'Ligne ') + n
    if mode == 'metro':
        return 'Métro ' + n
    if mode == 'tram':
        return n if n.upper().startswith('T') else 'Tram ' + n
    return n


def directs_omnibus(tr):
    """Sépare les trains directs des omnibus : plus grand écart dans le nombre d'arrêts intermédiaires.
    Retenu seulement si l'écart est d'au moins 3 arrêts, chaque groupe a 2 trains et les temps diffèrent d'au moins 5 min."""
    ns = sorted({n for _, n in tr})
    if len(ns) < 2:
        return None
    ecart, seuil = max((b - a, a) for a, b in zip(ns, ns[1:]))
    if ecart < 3:
        return None
    vite = [d for d, n in tr if n <= seuil]; lent = [d for d, n in tr if n > seuil]
    if len(vite) < 2 or len(lent) < 2 or statistics.mean(lent) - statistics.mean(vite) < 5:
        return None
    arr = lambda l: round(statistics.mean(l))
    return {'d': arr(vite), 'dn': len(vite), 'o': arr(lent), 'on': len(lent)}


def calcul(zbytes, rings):
    z = zipfile.ZipFile(io.BytesIO(zbytes))
    d = jour_type(z); actifs = services(z, d)
    print('jour retenu', d, '·', len(actifs), 'services actifs')
    lignes = {r['route_id']: (r.get('route_short_name') or r.get('route_long_name') or '', MODES.get(r['route_type']))
              for r in lire(z, 'routes.txt') if r['route_type'] in MODES}
    trips = {r['trip_id']: r['route_id'] for r in lire(z, 'trips.txt') if r['route_id'] in lignes and r['service_id'] in actifs}
    print(len(lignes), 'lignes ferrées,', len(trips), 'trains ce jour-là')
    arrets, parent = {}, {}
    for r in lire(z, 'stops.txt'):
        arrets[r['stop_id']] = (r['stop_name'], float(r['stop_lon']), float(r['stop_lat']))
        parent[r['stop_id']] = r.get('parent_station') or r['stop_id']
    a_paris = {}
    def dans_paris(sid):
        if sid not in a_paris:
            _, x, y = arrets[sid]; a_paris[sid] = inside(x, y, rings)
        return a_paris[sid]

    parcours = defaultdict(list)            # trip -> [(rang, arrivée, départ, arrêt)]
    for r in lire(z, 'stop_times.txt'):
        if r['trip_id'] in trips and r['departure_time']:
            parcours[r['trip_id']].append((int(r['stop_sequence']), hms(r['arrival_time'] or r['departure_time']), hms(r['departure_time']), r['stop_id']))
    durees, via, par_ligne = defaultdict(list), defaultdict(Counter), defaultdict(Counter)
    for tid, st in parcours.items():
        st.sort()
        nom_ligne, mode = lignes[trips[tid]]
        prochain = None                      # premier arrêt dans Paris à partir de la fin du parcours
        for i in range(len(st) - 1, -1, -1):
            _, arr, dep, sid = st[i]
            if dans_paris(sid):
                prochain = (arr, sid, i); continue
            if prochain and any(a <= dep % 86400 < b for a, b in PERIODES):
                g = parent[sid]
                durees[g].append(((prochain[0] - dep) / 60, prochain[2] - i - 1))
                via[g][arrets[parent[prochain[1]]][0] if parent[prochain[1]] in arrets else arrets[prochain[1]][0]] += 1
                par_ligne[g][(mode or '') + ':' + nom_ligne] += 1
    out = defaultdict(list)
    for g, tr in durees.items():
        if g not in arrets or len(tr) < 2:
            continue
        nom, x, y = arrets[g]
        ds = [d for d, _ in tr]
        ln = [libelle(*k.split(':', 1)) for k, _ in par_ligne[g].most_common(3)]
        e = {'x': round(x, 5), 'y': round(y, 5), 'm': round(statistics.mean(ds)), 'min': round(min(ds)),
             'via': via[g].most_common(1)[0][0], 'l': ln, 'n': len(ds)}
        e.update(directs_omnibus(tr) or {})
        out[norm(nom)].append(e)
    print(sum(len(v) for v in out.values()), 'gares avec un temps jusqu\'à Paris')
    return {'jour': d.isoformat(), 'gares': out}


def main():
    zpath = sys.argv[1] if len(sys.argv) > 1 and sys.argv[1].endswith('.zip') else None
    html = sys.argv[-1] if sys.argv[-1].endswith('.html') else 'site/transports.html'
    if zpath:
        zb = open(zpath, 'rb').read()
    else:
        zb = None
        for u in GTFS_URLS:
            try:
                zb = get(u); zipfile.ZipFile(io.BytesIO(zb)); print('GTFS :', u, len(zb) // 1_000_000, 'Mo'); break
            except Exception as e:
                print('GTFS indisponible :', u, e); zb = None
        if not zb:
            sys.exit('Aucune source GTFS disponible')
    rings = json.load(open(os.environ['PARIS_JSON'])) if os.environ.get('PARIS_JSON') else paris_poly()
    res = calcul(zb, rings)
    if not res['gares']:
        sys.exit('Aucun temps calculé : page inchangée')
    s = open(html, encoding='utf-8').read()
    bloc = '/*TEMPS_PARIS_DEBUT*/window.TEMPS_PARIS = ' + json.dumps(res, ensure_ascii=False, separators=(',', ':')) + ';/*TEMPS_PARIS_FIN*/'
    s2, n = re.subn(r'/\*TEMPS_PARIS_DEBUT\*/.*?/\*TEMPS_PARIS_FIN\*/', lambda m: bloc, s, flags=re.S)
    if n != 1:
        sys.exit('Bloc TEMPS_PARIS introuvable dans ' + html)
    open(html, 'w', encoding='utf-8').write(s2)
    print('écrit dans', html, len(bloc) // 1000, 'ko')


if __name__ == '__main__':
    main()
