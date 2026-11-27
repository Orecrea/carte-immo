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


NB2 = r"(?:deux|2|seconde?|deuxieme|2e|2eme|2 eme|autre)"
LOGT = r"(?:studio|appartement|appart|logement|duplex|f1|f2|f3|t1|t2|t3|t1 bis|loft|habitation)"

INDICES = [
    # --- deux maisons sur le terrain
    ("deux_maisons", 3, rf"\b{NB2} (?:maisons?|habitations?|pavillons?|batisses?)\b"),
    ("deux_maisons", 3, r"\bmaison (?:d'? ?amis?|de gardiens?|d'? ?invites?|annexe|secondaire|de famille independante)\b"),
    ("deux_maisons", 3, r"\b(?:petite|seconde|deuxieme|autre) maison (?:independante|sur le terrain|dans le (?:jardin|parc))"),
    ("deux_maisons", 2, r"\bmaisonnette\b"),
    ("deux_maisons", 2, r"\bgites?\b"),
    ("deux_maisons", 2, r"\bpool ?house\b"),
    ("deux_maisons", 1, r"\bchambres? d'hotes?\b"),
    # --- maison scindée en deux logements
    ("divisee", 3, rf"\b{NB2} (?:logements|appartements|lots|parties (?:habitables|independantes|distinctes)|unites d'habitation|foyers)\b"),
    ("divisee", 3, rf"\b{LOGT} (?:independant|indepandant|attenant|separe|annexe)e?s?\b"),
    ("divisee", 3, r"\bbi-? ?famil|\bintergenerationnel|\bkangourou\b|\bmaison de famille pour deux\b"),
    ("divisee", 3, r"\bdivisibles? en (?:deux|2)\b|\bdivisee en (?:deux|2)\b|\bpossibilite de (?:faire |creer )?(?:deux|2) (?:logements|appartements)"),
    ("divisee", 3, rf"\b{NB2} cuisines\b"),
    ("divisee", 2, r"\bentrees? independantes?\b|\b(?:deux|2) entrees\b"),
    ("divisee", 2, r"\b(?:revenus? locatifs?|actuellement loue|partie louee|location saisonniere|loyer mensuel)\b"),
    ("divisee", 1, r"\b(?:deux|2) salles? (?:d'eau|de bains?)\b"),
    # --- dépendance à aménager
    ("dependance", 2, r"\b(?:grange|dependance|batiment|atelier|ecurie|bergerie|hangar|remise|grenier)s? (?:a amenager|amenageables?|a renover|transformables?|a rehabiliter)\b"),
    ("dependance", 2, r"\bcorps de ferme\b"),
    ("dependance", 1, r"\bancienne ferme\b|\blongere\b"),
    ("dependance", 1, r"\bdependances?\b"),
]
INDICES = [(c, p, re.compile(_esp(rx))) for c, p, rx in INDICES]

# « grange de 120 m² », « dépendance d'environ 80m2 », « atelier attenant (60 m²) »
SURF_RX = re.compile(_esp(
    r"\b(grange|dependance|batiment|atelier|ecurie|bergerie|hangar|remise|annexe|longere|chai|cellier|garage|grenier|"
    r"studio|appartement|maison d'amis|maisonnette|gite|second logement)s?\b[^.;\n]{0,45}?(\d{2,4})(?:[.,]\d+)? ?(?:m2|m\b|metres? carres)"))
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
    points, extraits, vus = {}, [], set()
    for cat, poids, rx in INDICES:
        m = rx.search(t)
        if m and (cat, rx.pattern) not in vus:
            vus.add((cat, rx.pattern))
            points[cat] = points.get(cat, 0) + poids
            if poids >= 2:
                ajouter(extraits, brut, m)
    # surfaces : une dépendance ou un second logement d'au moins 50 m² est un indice net
    for m in SURF_RX.finditer(t):
        mot, s = m.group(1), int(m.group(2))
        if mot == "garage" and s < 60:
            continue
        if s >= 50 and s < 2000:
            cat = "dependance" if mot not in ("studio", "appartement", "maison d'amis", "maisonnette", "gite", "second logement") else "deux_maisons"
            points[cat] = points.get(cat, 0) + 3
            ajouter(extraits, brut, m)
            break
    if NON.search(t):
        points.pop("dependance", None)
    # grande maison avec beaucoup de pièces : simple piste, qui s'ajoute aux autres
    if pieces and surf and pieces >= 9 and surf >= 220:
        points["divisee"] = points.get("divisee", 0) + 1
    score = sum(points.values())
    if score < 3 or max(points.values(), default=0) < 2:
        return None
    cats = sorted(points, key=lambda c: -points[c])
    return {"score": score, "cats": cats, "noms": [NOMS[c] for c in cats if points[c] >= 2], "extraits": [e for _, e in sorted(extraits)]}


if __name__ == "__main__":                       # petits essais : python collecte/multi_detect.py
    essais = [
        ("Propriété avec deux maisons", "Sur un terrain de 2000 m², maison principale de 150 m² et maison d'amis de 60 m²."),
        ("Maison 6 pièces", "Belle maison familiale avec jardin et garage."),
        ("Longère", "Longère avec grange attenante de 120 m² à aménager."),
        ("Maison bi-famille", "Idéal bi-famille : rez-de-chaussée et étage avec entrées indépendantes."),
        ("Maison", "Maison avec studio indépendant loué 600 €."),
        ("Pavillon", "Pavillon indépendant sur sous-sol total, garage 20 m²."),
        ("Maison", "Maison sans dépendance, terrain 500 m²."),
    ]
    for ti, de in essais:
        print(ti, "->", analyser(ti, de))
