"""Diagnostic temporaire : fréquence de chaque indice multi-logements sur les annonces déjà lues (compteurs seulement)."""
import os, sys
from collections import Counter
sys.path.insert(0, "collecte")
from chiffrement import dechiffrer
from multi_detect import analyser
e = dechiffrer(open("etat/multi.enc").read(), os.environ["CLE_CARTE"])
annonces = [a for c in e["cache"].values() for a in c.get("annonces", [])]
ids, seul, gardes, cats = Counter(), Counter(), 0, Counter()
for a in annonces:
    m = analyser(a.get("titre"), a.get("desc"), a.get("pieces"), a.get("surf"))
    if m:
        gardes += 1
        ids.update(set(m["ids"])); cats.update(m["noms"])
        if len(set(m["ids"])) == 1:
            seul.update(m["ids"])
print("annonces", len(annonces), "retenues", gardes)
print("indices", ids.most_common())
print("seul indice", seul.most_common())
print("familles", cats.most_common())
