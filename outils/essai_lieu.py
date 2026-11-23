import sys, os, json
sys.path.insert(0, 'collecte')
import collecte as C
from chiffrement import dechiffrer, chiffrer
cle = os.environ['CLE_CARTE']
d = dechiffrer(open('site/annonces.enc').read(), cle)
det = {c['code']: c for c in C.communes_detail(d['communes'])}
res = []
for x in d['annonces']:
    c = det.get(x['insee'])
    if not c: continue
    a = {'titre': x['titre'], 'desc': x['desc'], 'source': x['source'], 'ville': x['city'], 'prix': x['price'], 'lat': None, 'lng': None}
    if 'Noisy' in (x['desc'] or '')[:200] or 'LIVRY' in (x['desc'] or '')[:200] or 'Montreuil –' in (x['desc'] or '')[:50]:
        res.append('DBG ' + x['city'] + ' ' + str(C.commune_en_tete(dict(a), c)) + ' ' + str([(n, len(C.communes_nommees(n))) for n in ['Noisy le Sec', 'Montreuil', 'Livry sur Seine', 'Maison', 'Superbe']]))
    r = C.verifier_lieu(a, c, list(det.values()))
    if r is None or r is not c:
        res.append(f"{x['city']} -> {r['nom'] if r else 'ÉCARTÉE'} | {(x['titre'] or '')[:50]} | {(x['desc'] or '').split(chr(10))[0][:120]}")
os.makedirs('out', exist_ok=True)
open('out/res.enc', 'w').write(chiffrer({'res': res, 'journal': C.journal, 'index': len(C._index or {})}, cle))
print(len(res))
