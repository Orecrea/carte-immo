"""Diagnostic temporaire : mots exacts qui déclenchent chaque indice (compteurs seulement, aucun texte d'annonce)."""
import os, re, sys
from collections import Counter, defaultdict
sys.path.insert(0, "collecte")
from chiffrement import dechiffrer
import multi_detect as D
e = dechiffrer(open("etat/multi.enc").read(), os.environ["CLE_CARTE"])
annonces = {a["id"]: a for c in e["cache"].values() for a in c.get("annonces", [])}.values()
mots = defaultdict(Counter)
ctx = defaultdict(Counter)
for a in annonces:
    t = D.norm((a.get("titre") or "") + ". " + (a.get("desc") or ""))
    for ident, cat, poids, rx in D.INDICES:
        m = rx.search(t)
        if m:
            mots[ident][re.sub(r"\s+", " ", m.group(0))] += 1
            # 3 mots avant / après, pour voir le contexte (mots courants seulement)
            av = " ".join(re.findall(r"[a-z']+", t[max(0, m.start() - 30):m.start()])[-3:])
            ap = " ".join(re.findall(r"[a-z']+", t[m.end():m.end() + 30])[:3])
            ctx[ident][av + " [_] " + ap] += 1
    m = D.SURF_RX.search(t)
    if m:
        mots["surface"][re.sub(r"\d+", "N", re.sub(r"\s+", " ", m.group(0)))] += 1
print("annonces distinctes", len(annonces))
for k in mots:
    print(k, sum(mots[k].values()), mots[k].most_common(12))
    print("   contexte", [x for x in ctx[k].most_common(8) if x[1] > 1])
