"""Diagnostic temporaire : nombre d'annonces retenues par indice (compteurs seulement)."""
import os, sys
from collections import Counter
sys.path.insert(0, "collecte")
from chiffrement import dechiffrer
from multi_detect import analyser
e = dechiffrer(open("etat/multi.enc").read(), os.environ["CLE_CARTE"])
annonces = {a["id"]: a for c in e["cache"].values() for a in c.get("annonces", [])}.values()
ids, n, fam = Counter(), 0, Counter()
for a in annonces:
    m = analyser(a.get("titre"), a.get("desc"), a.get("pieces"), a.get("surf"))
    if m:
        n += 1; ids.update(set(m["ids"])); fam.update(m["noms"][:1])
print("annonces distinctes", len(annonces), "retenues", n)
print(ids.most_common()); print(fam.most_common())
