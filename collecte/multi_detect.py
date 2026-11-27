"""Repérage des biens « multi-logements » dans le texte des annonces (demande d'Oré du 27/11/2026).

Trois familles recherchées :
  - deux_maisons : terrain avec une maison principale et une seconde maison (maison d'amis, de gardien, gîte…)
  - divisee      : maison scindée en deux logements distincts (bi-famille, studio ou appartement indépendant…)
  - dependance   : dépendance d'au moins 50 m² à aménager (grange, atelier, bâtiment annexe…)

Chaque indice a un poids : 3 = net, 2 = probable, 1 = simple piste. Une annonce est retenue à partir de 3 points.
Le texte est normalisé (minuscules, sans accents) avant la recherche.
"""
import re, unicodedata


def norm(t):
    t = unicodedata.normalize("NFD", str(t or "")).encode("ascii", "ignore").decode().lower()
    return re.sub(r"[ \t  ]+", " ", t.replace("’", "'"))


def _esp(rx):
    """Les espaces des motifs acceptent plusieurs espaces ou un saut de ligne ; « ? » après un espace : espace facultatif."""
    return rx.replace(" ?", r"\s*").replace(" ", r"\s+")


NB2 = r"(?:deux|2|seconde?|deuxieme|2e|2eme|2 eme)"
LOGT = r"(?:studio|appartement|appart|logement|duplex|f1|f2|f3|t1|t2|t3|t1 bis|loft)"

# (identifiant, famille, poids, motif) ; poids 3 = net, 2 = probable, 1 = simple piste
INDICES = [
    # --- deux maisons sur le terrain
    ("2maisons", "deux_maisons", 3, rf"\b{NB2} (?:maisons|habitations|pavillons|batisses)\b(?! (?:de ville|mitoyennes?|voisines?|plus loin|de la|du|des|d'))"),
    ("maison_amis", "deux_maisons", 3, r"\bmaison (?:d'? ?amis?|de gardiens?|d'? ?invites?|annexe)\b"),
    ("petite_maison", "deux_maisons", 3, r"\b(?:petite|seconde|deuxieme) maison (?:independante|sur le terrain|dans le (?:jardin|parc))"),
    ("maisonnette", "deux_maisons", 2, r"\bmaisonnette\b"),
    ("gite", "deux_maisons", 3, r"\bgites?\b"),
    ("poolhouse", "deux_maisons", 1, r"\bpool ?house\b"),
    # --- maison scindée en deux logements
    ("2logements", "divisee", 3, rf"\b(?:{NB2} (?:logements|appartements|parties (?:habitables|independantes|distinctes)|unites d'habitation)\b)(?! (?:situes dans|au total|dont))"),
    ("logt_indep", "divisee", 3, rf"\b{LOGT} (?:independant|indepandant|attenant|separe)e?s?\b"),
    ("bifamille", "divisee", 3, r"\bbi-? ?famil|\bkangourou\b"),
    ("intergeneration", "divisee", 2, r"\bintergenerationnel"),
    ("divisible", "divisee", 3, r"\b(?:divisibles?|divisee|separee) en (?:deux|2) (?:logements|appartements|habitations|parties|lots|unites)\b|\bpossibilite de (?:faire |creer )?(?:deux|2) (?:logements|appartements)"),
    ("divisee", "divisee", 1, r"\b(?:divisibles?|divisee) en (?:deux|2)\b"),
    ("2cuisines", "divisee", 3, rf"\b{NB2} cuisines\b"),
    ("entree_indep", "divisee", 1, r"\bentrees? independantes?\b|\b(?:deux|2) entrees\b"),
    ("locatif", "divisee", 1, r"\b(?:revenus? locatifs?|actuellement loue|partie louee|loyer mensuel)\b"),
    # --- dépendance à aménager
    ("dep_amenager", "dependance", 2, r"\b(?:grange|dependance|batiment|atelier|ecurie|bergerie|hangar|remise)s? (?:a amenager|amenageables?|transformables?|a rehabiliter)\b"),
    ("corps_ferme", "dependance", 1, r"\bcorps de ferme\b"),
    ("dependance", "dependance", 1, r"\bdependances?\b"),
]
INDICES = [(i, c, p, re.compile(_esp(rx))) for i, c, p, rx in INDICES]

# « grange de 120 m² », « dépendance d'environ 80m2 », « atelier attenant (60 m²) » : surface collée au mot (pas de virgule entre)
SURF_RX = re.compile(_esp(
    r"\b(grange|dependance|batiment annexe|atelier|ecurie|bergerie|hangar|remise|annexe|studio|maison d'amis|maisonnette|gite|second logement)s?"
    r"(?: (?:attenante?|independante?|amenageable|a amenager|separee?|indep\.?|d'une surface|d'environ|de plus de|de pres de|totale?|au sol|de|d'|:|\(|env\.?|environ|d'env\.?))* ?"
    r"(\d{2,4})(?:[.,]\d+)? ?(?:m2|m\b|metres? carres)"))
NON = re.compile(r"\b(?:pas de dependance|sans dependance|ni dependance)\b")
NOMS = {"deux_maisons": "Deux maisons", "divisee": "Maison divisée en 2 logements", "dependance": "Dépendance ≥ 50 m²"}


def extrait(t, m, n=70):
    a, b = max(0, m.start() - n), min(len(t), m.end() + n)
    return ("…" if a else "") + t[a:b].strip().replace("\n", " ") + ("…" if b < len(t) else "")


def ajouter(extraits, brut, m):
    """Extrait autour de l'indice, sans répéter un passage déjà cité."""
    if len(extraits) >= 4 or any(abs(m.start() - x[0]) < 90 for x in extraits):
        return
    extraits.append((m.start(), extrait(brut, m)))


def analyser(titre, desc, pieces=None, surf=None):
    """Renvoie None si rien de probant, sinon {score, cats:[...], noms:[...], extraits:[...]}"""
    brut = (str(titre or "") + ". " + str(desc or ""))
    t = norm(brut)
    if not t.strip():
        return None
    points, extraits, ids, fort = {}, [], [], 0
    for ident, cat, poids, rx in INDICES:
        m = rx.search(t)
        if m:
            ids.append(ident); fort = max(fort, poids)
            points[cat] = points.get(cat, 0) + poids
            if poids >= 2:
                ajouter(extraits, brut, m)
    # surfaces : une dépendance ou un second logement d'au moins 50 m² est un indice net
    for m in SURF_RX.finditer(t):
        mot, surf_dep = m.group(1), int(m.group(2))
        if 50 <= surf_dep < 1000:
            cat = "deux_maisons" if mot in ("studio", "maison d'amis", "maisonnette", "gite", "second logement") else "dependance"
            ids.append("surface"); fort = 3
            points[cat] = points.get(cat, 0) + 3
            ajouter(extraits, brut, m)
            break
    if NON.search(t):
        points.pop("dependance", None)
    score = sum(points.values())
    # retenu : un indice net (3 points), ou plusieurs indices qui se recoupent (4 points dont un probable)
    if not points or not (fort >= 3 or (score >= 4 and fort >= 2)):
        return None
    cats = sorted(points, key=lambda c: -points[c])
    return {"score": score, "cats": cats, "noms": [NOMS[c] for c in cats if points[c] >= 2], "extraits": [e for _, e in sorted(extraits)], "ids": ids}


if __name__ == "__main__":                       # petits essais : python collecte/multi_detect.py
    essais = [
        ("Propriété avec deux maisons", "Sur un terrain de 2000 m², maison principale de 150 m² et maison d'amis de 60 m²."),
        ("Maison 6 pièces", "Belle maison familiale avec jardin et garage."),
        ("Longère", "Longère avec grange attenante de 120 m² à aménager."),
        ("Maison bi-famille", "Idéal bi-famille : rez-de-chaussée et étage avec entrées indépendantes."),
        ("Maison", "Maison avec studio indépendant loué 600 €."),
        ("Pavillon", "Pavillon indépendant sur sous-sol total, garage 20 m²."),
        ("Maison", "Maison sans dépendance, terrain 500 m²."),
        ("Maison", "Maison de 120 m² avec garage, atelier, séjour de 50 m² et dépendances."),
        ("Longère", "Longère de 160 m², grenier aménageable, à 2 maisons de la gare."),
        ("Maison", "Au calme, loin des autres maisons, résidence secondaire idéale avec gîte rural."),
        ("Maison", "Corps de ferme avec grange à aménager et dépendances."),
    ]
    for ti, de in essais:
        print(ti, "->", analyser(ti, de))
