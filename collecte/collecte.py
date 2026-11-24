"""Collecte des annonces de maisons pour les communes suivies.

Usage : python collecte/collecte.py <mode>
  mode = auto      : passage planifié (ne fait rien si la date d'arrêt est passée)
         manuel    : lancé à la main ou par le bouton « Actualiser » (relance le compteur d'un mois)
Variables : CLE_CARTE (mot de passe de chiffrement), DEMANDE (corps du ticket « Actualiser », facultatif)

Fichiers :
  etat/fin.txt         date d'arrêt de la collecte automatique (lisible, sans donnée personnelle)
  etat/etat.enc        villes suivies, historique des prix, dernières annonces par site (chiffré)
  site/annonces.enc    ce que lit la carte (chiffré)
"""
import json, os, re, sys, math, hashlib, unicodedata, traceback, time, copy, threading, subprocess
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, os.path.dirname(__file__))
from chiffrement import chiffrer, dechiffrer
import sources

RACINE = Path(__file__).resolve().parent.parent
ETAT, FIN, SORTIE = RACINE / "etat/etat.enc", RACINE / "etat/fin.txt", RACINE / "site/annonces.enc"
PARTIEL = RACINE / "perso/partiel.enc"            # annonces déjà lues, pendant la collecte
DUREE = timedelta(days=30)
MAINTENANT = datetime.now(timezone.utc)
CLE = os.environ.get("CLE_CARTE", "")

journal = []


_tl = threading.local()


def log(m):
    """Journal détaillé (villes, prix…) : il ne va QUE dans le fichier chiffré, jamais dans les journaux
    publics de GitHub Actions. Ceux-ci n'affichent que des compteurs anonymes (voir resume_public)."""
    if not getattr(_tl, "muet", False):
        journal.append(m)


def sortir(code, message, publier=False):
    print(message)
    out = os.environ.get("GITHUB_OUTPUT")
    if out:
        with open(out, "a") as f:
            f.write(f"resultat={message}\npublier={'1' if publier else '0'}\n")
    sys.exit(code)


# ------------------------------------------------------------ utilitaires
def norm(t):
    return unicodedata.normalize("NFD", str(t or "")).encode("ascii", "ignore").decode().lower().strip()


def jours_depuis(iso):
    if not iso:
        return None
    try:
        d = datetime.fromisoformat(str(iso).replace("Z", "+00:00"))
        if d.tzinfo is None:
            d = d.replace(tzinfo=timezone.utc)
        return max(0, (MAINTENANT - d).days)
    except ValueError:
        return None


def get_json(url, **kw):
    s = sources.session()
    r = s.get(url, **kw)
    r.raise_for_status()
    return r.json()


def communes_detail(codes):
    """Nom, codes postaux, centre et contour officiels (geo.api.gouv.fr)."""
    out = []
    for code in codes:
        try:
            j = get_json(f"https://geo.api.gouv.fr/communes/{code}",
                         params={"fields": "nom,codesPostaux,centre,contour", "format": "json", "geometry": "contour"})
            out.append({"code": code, "nom": j["nom"], "codesPostaux": j.get("codesPostaux") or [],
                        "centre": (j.get("centre") or {}).get("coordinates"), "contour": j.get("contour")})
        except Exception as e:
            log(f"Commune {code} introuvable ({e})")
    return out


def voisines(code):
    """Communes limitrophes : points posés à 350 m à l'extérieur du contour, chacun rattaché à sa commune (geo.api.gouv.fr)."""
    try:
        g = get_json(f"https://geo.api.gouv.fr/communes/{code}", params={"fields": "contour", "format": "json", "geometry": "contour"}).get("contour")
    except Exception as e:
        log(f"Contour de {code} indisponible ({type(e).__name__})"); return []
    if not g:
        return []
    polys = [g["coordinates"]] if g["type"] == "Polygon" else g["coordinates"]
    km = lambda a, b: math.hypot((b[0] - a[0]) * math.cos(math.radians(a[1])) * 111.2, (b[1] - a[1]) * 111.2)
    pts = []
    for poly in polys:
        r = poly[0]
        seg = [km(r[i - 1], r[i]) for i in range(1, len(r))]
        per = sum(seg) or 1
        n = max(12, min(60, round(per * 2.5))); step = per / n
        acc, nxt = 0.0, 0.0
        for i in range(1, len(r)):
            (x0, y0), (x1, y1), d = r[i - 1], r[i], seg[i - 1]
            while d > 0 and nxt <= acc + d:
                t = (nxt - acc) / d; x = x0 + (x1 - x0) * t; y = y0 + (y1 - y0) * t; c = math.cos(math.radians(y))
                nx, ny = -(y1 - y0), (x1 - x0) * c; ln = math.hypot(nx, ny) or 1; off = .35 / 111
                px, py = x + nx / ln * off / c, y + ny / ln * off
                if dans_geom(px, py, g):
                    px, py = x - nx / ln * off / c, y - ny / ln * off
                if not dans_geom(px, py, g):
                    pts.append((py, px))
                nxt += step
            acc += d
    trouvees = {}
    for la, lo in pts[:200]:
        try:
            for c in get_json("https://geo.api.gouv.fr/communes", params={"lat": f"{la:.5f}", "lon": f"{lo:.5f}", "fields": "code,nom", "format": "json"}):
                if c["code"] != code:
                    trouvees[c["code"]] = c["nom"]
        except Exception:
            pass
    return [{"code": k, "name": v} for k, v in trouvees.items()]


def dans_ring(x, y, ring):
    ins, j = False, len(ring) - 1
    for i in range(len(ring)):
        xi, yi = ring[i]; xj, yj = ring[j]
        if (yi > y) != (yj > y) and x < (xj - xi) * (y - yi) / (yj - yi) + xi:
            ins = not ins
        j = i
    return ins


def dans_geom(lng, lat, g):
    if not g:
        return False
    polys = [g["coordinates"]] if g["type"] == "Polygon" else g["coordinates"] if g["type"] == "MultiPolygon" else []
    return any(dans_ring(lng, lat, p[0]) and not any(dans_ring(lng, lat, h) for h in p[1:]) for p in polys)


def point_dans_commune(c, graine):
    """Point stable (même annonce = même point) tiré dans le contour de la commune, pour les annonces sans position."""
    g = c.get("contour")
    if not g:
        lng, lat = c["centre"]
        return lat, lng
    pts = [pt for p in ([g["coordinates"]] if g["type"] == "Polygon" else g["coordinates"]) for pt in p[0]]
    x0, x1 = min(p[0] for p in pts), max(p[0] for p in pts)
    y0, y1 = min(p[1] for p in pts), max(p[1] for p in pts)
    h = int(hashlib.sha1(graine.encode()).hexdigest(), 16)
    cx, cy = c["centre"] if c.get("centre") else ((x0 + x1) / 2, (y0 + y1) / 2)
    for k in range(60):
        u, v = ((h >> (k * 4)) % 997) / 997, ((h >> (k * 4 + 80)) % 991) / 991
        x, y = cx + (u - .5) * (x1 - x0) * .6, cy + (v - .5) * (y1 - y0) * .6
        if dans_geom(x, y, g):
            return y, x
    return cy, cx


# ------------------------------------------------------------ enrichissement
ATOUTS = [
    ("Jardin", r"jardin"), ("Piscine", r"piscine"), ("Garage", r"garage"), ("Terrasse", r"terrasse"),
    ("Cave", r"\bcave\b"), ("Sous-sol", r"sous-sol|sous sol"), ("Véranda", r"v[ée]randa"),
    ("Cheminée", r"chemin[ée]e|insert|po[êe]le"), ("Plain-pied", r"plain[- ]pied"),
    ("Combles aménageables", r"combles? am[ée]nageable"), ("Pompe à chaleur", r"pompe [àa] chaleur|\bpac\b"),
    ("Panneaux solaires", r"panneaux? (solaire|photovolta)"), ("Dépendance", r"d[ée]pendance"),
    ("Logement indépendant", r"studio ind[ée]pendant|appartement ind[ée]pendant|logement ind[ée]pendant|deux maisons|2 maisons|g[îi]te"),
    ("Grenier", r"grenier"), ("Atelier", r"atelier"), ("Bureau", r"bureau"), ("Parking", r"parking|stationnement"),
    ("Balcon", r"balcon"), ("Buanderie", r"buanderie|cellier"), ("Proche gare", r"proche (de la )?gare|gare [àa] \d+"),
    ("Proche écoles", r"proche (des )?[ée]coles|[ée]coles? [àa] pied"), ("Travaux à prévoir", r"travaux [àa] pr[ée]voir|[àa] r[ée]nover|r[ée]novation compl[eè]te"),
]
TYPES = [("Longère", r"long[èe]re"), ("Maison de ville", r"maison de ville"), ("Pavillon", r"pavillon"),
         ("Villa", r"\bvilla\b"), ("Corps de ferme", r"corps de ferme|ancienne ferme"), ("Maison d'architecte", r"architecte"),
         ("Maison bourgeoise", r"bourgeoise|maison de ma[îi]tre"), ("Moulin", r"\bmoulin\b"), ("Chalet", r"chalet")]


def enrichir(a):
    t = norm(a.get("titre", "") + " " + a.get("desc", ""))
    a["atouts"] = [n for n, rx in ATOUTS if re.search(norm(rx), t)]
    a["type"] = next((n for n, rx in TYPES if re.search(norm(rx), norm(a.get("titre", "")))), None) or "Maison"
    if not a.get("terrain"):
        m = re.search(r"terrain (?:clos |arbor[ée] |plat )?(?:de |d'environ |d environ )?(\d[\d\s.]*)\s?m", t)
        a["terrain"] = sources.entier(m.group(1)) if m else None
    if not a.get("annee"):
        m = re.search(r"(?:construite?|batie?|construction) en (1[89]\d\d|20[0-2]\d)", t)
        a["annee"] = int(m.group(1)) if m else None
    if not a.get("dpe"):
        m = re.search(r"(?:dpe|classe energie|classe energetique)\s*:?\s*([a-g])\b", t)
        a["dpe"] = m.group(1).upper() if m else None
    if not a.get("chambres"):
        m = re.search(r"(\d+)\s*chambres", t)
        a["chambres"] = int(m.group(1)) if m else None
    return a


def rattacher(a, communes):
    """Trouve la commune suivie de l'annonce ; None si elle est hors des communes suivies."""
    if a.get("insee"):
        c = next((c for c in communes if c["code"] == a["insee"]), None)
        if c:
            return c
    if a.get("lat") and a.get("lng"):
        c = next((c for c in communes if dans_geom(a["lng"], a["lat"], c.get("contour"))), None)
        if c:
            return c
    v, cp = norm(a.get("ville")), str(a.get("cp") or "")
    return next((c for c in communes if norm(c["nom"]) == v and (not cp or cp in c["codesPostaux"])), None) \
        or next((c for c in communes if v and norm(c["nom"]).replace("-", " ") == v.replace("-", " ")), None)


def _mots(a):
    return set(re.findall(r"[a-z]{4,}", norm((a.get("titre") or "") + " " + (a.get("desc") or "")[:1500])))


LIEU_RX = re.compile(
    r"(?:sur la commune d[e'u]|commune d[e'u]|village d[e'u]|ville d[e'u]|bourg d[e'u]|"
    r"situ[ée]e?s? (?:au c(?:oe|œ)ur d[e'u] |en plein c(?:oe|œ)ur d[e'u] |dans le centre d[e'u] )?[àa]|"
    r"(?:au|en plein) c(?:oe|œ)ur d[e'u](?: la ville d[e'u]| village d[e'u])?)\s*"
    r"((?:Saint|Sainte|Le|La|Les|L')?[\s'-]?[A-ZÉÈÎ][a-zéèêëîïôûç]+(?:[\s'-](?:sur|sous|en|lès|les|le|la|de|du|des|d|et|aux?|[A-ZÉÈÎ][a-zéèêëîïôûç]+)){0,4})")
# noms de régions ou de pays qui sont aussi des noms de communes : jamais pris pour une adresse
PAS_UNE_COMMUNE = {norm(x) for x in ["Bretagne", "Normandie", "Champagne", "Bourgogne", "Provence", "Alsace", "Lorraine",
    "Picardie", "Auvergne", "Savoie", "Vendée", "Gironde", "Charente", "Touraine", "Sologne", "Beauce", "Brie", "Vexin",
    "Perche", "Berry", "Anjou", "Poitou", "Limousin", "Périgord", "Quercy", "Gascogne", "Béarn", "Corse", "France", "Europe",
    "Ville", "Village", "Centre", "Paris Centre"]}


_index = None


def communes_nommees(nom):
    """Communes françaises portant ce nom exact (homonymes compris) ; liste complète chargée une fois par collecte."""
    global _index
    if _index is None:
        _index = {}
        try:
            for x in get_json("https://geo.api.gouv.fr/communes", params={"fields": "nom,code,centre", "format": "json"}):
                _index.setdefault(norm(x["nom"]).replace("-", " "), []).append(x)
        except Exception as e:
            log(f"Liste des communes indisponible ({type(e).__name__})")
    return _index.get(norm(nom).replace("-", " "), [])


def km(p, q):
    return math.hypot((p[1] - q[1]) * 111, (p[0] - q[0]) * 111 * math.cos(math.radians(p[1])))


def verifier_lieu(a, c, communes):
    """Annonces mal localisées (ex. « Paris 10 » pour une maison en Champagne) :
    la commune citée dans le texte prime. Si elle est suivie, l'annonce y est déplacée ; sinon elle est écartée."""
    if a.get("lat") and a.get("lng") and c.get("centre") and km((a["lng"], a["lat"]), c["centre"]) > 25:
        return None                                    # coordonnées GPS loin de la commune annoncée
    texte_annonce = (a.get("titre") or "") + " . " + (a.get("desc") or "")[:1500]
    for m in LIEU_RX.finditer(texte_annonce):
        nom = re.sub(r"\s+", " ", m.group(1)).strip(" -'")
        n_ = norm(nom).replace("-", " ")
        if len(nom) < 3 or n_ in ("la", "le", "les") or norm(nom) in PAS_UNE_COMMUNE \
                or any((norm(x["nom"]).replace("-", " ") + " ").startswith(n_ + " ") for x in communes):
            continue                                   # « Cesson » pour Cesson-Sévigné, etc.
            continue
        suivie = next((x for x in communes if norm(x["nom"]).replace("-", " ") == norm(nom).replace("-", " ")), None)
        if suivie:
            if suivie is not c:
                a["insee"], a["ville"], a["lat"], a["lng"] = suivie["code"], suivie["nom"], None, None
            return suivie
        homonymes = communes_nommees(nom)
        if homonymes and c.get("centre") and all(km(h["centre"]["coordinates"], c["centre"]) > 5 for h in homonymes if h.get("centre")):
            log(f"Écartée : {a['source']} {a['ville']} {a['prix']} € (le texte situe le bien à {nom})")
            return None
    # « 10 kms de Meaux » : le bien n'est pas dans la commune annoncée
    m = re.search(r"(\d+)\s*kms?\s+(?:de|d')\s*" + re.escape(norm(c["nom"]).replace("-", " ")).replace("\\ ", "[ -]"), norm(texte_annonce[:400]))
    if m and int(m.group(1)) >= 3:
        log(f"Écartée : {a['source']} {a['ville']} {a['prix']} € (le texte la situe à {m.group(1)} km de la commune)")
        return None
    # nom de commune cité seul en tête d'annonce (« Longère 6 pièces 175 m² Le Chatelet en Brie »)
    autre = commune_en_tete(a, c)
    if autre:
        suivie = next((x for x in communes if x["code"] == autre["code"]), None)
        if suivie:
            a["insee"], a["ville"], a["lat"], a["lng"] = suivie["code"], suivie["nom"], None, None
            return suivie
        log(f"Écartée : {a['source']} {a['ville']} {a['prix']} € (le texte situe le bien à {autre['nom']})")
        return None
    return c


NOM_RX = re.compile(r"(?:(?:Saint|Sainte|Le|La|Les|L')[\s'-]?)?[A-ZÉÈÎ][a-zéèêëîïôûç]+(?:[\s'-]+(?:sur|sous|en|lès|les|le|la|de|du|des|d'|et|aux?|[A-ZÉÈÎ][a-zéèêëîïôûç]+))*")
MOTS_COURANTS = {norm(x) for x in ["Maison", "Située", "Situé", "Longère", "Investissement", "Rue", "Gare", "Centre", "Plein", "Pied",
    "Plain", "Proche", "Belle", "Beau", "Superbe", "Charmante", "Exclusivité", "Exclusivite", "Village", "Ville", "Quartier",
    "Propriété", "Pavillon", "Visite", "Terrain", "Jardin", "Coup", "Coeur", "Idéal", "Rare", "Vente", "Nouveau", "Prix", "Sous", "Sol"]}


def commune_en_tete(a, c):
    """Commune nommée en tête d'annonce comme lieu du bien (« Longère 175 m² Le Chatelet en Brie », « À Lizy-sur-Ourcq… »),
    à moins de 40 km. Les mentions de voisinage (« à 5 min de Meaux », « proche Melun », « limite Montreuil ») sont ignorées,
    et si la commune annoncée est elle-même citée comme lieu, on la garde."""
    tete = (a.get("titre") or "") + " | " + (a.get("desc") or "").strip().split("\n")[0][:160]
    tete = re.sub(r"\b[A-ZÉÈÊÎÂÔÛÇ]{2,}(?:[\s'-][A-ZÉÈÊÎÂÔÛÇ]{2,})*\b", lambda m: m.group(0).title(), tete)   # « RUEIL MALMAISON »
    nom_c, centre = norm(c["nom"]).replace("-", " "), c.get("centre")
    trouvee = None
    for m in NOM_RX.finditer(tete):
        avant = tete[:m.start()].rstrip()
        mot = norm(avant.split()[-1]) if avant.split() else ""
        if not (not avant or avant[-1] in "-–—|:/.(!²" or avant[-1].isdigit() or mot in ("a", "sur", "m2")):
            continue                                    # « proche Melun », « gare de Meaux », « Laforêt de Cesson »…
        mots = re.split(r"[\s'-]+", m.group(0).strip())
        while mots:
            n_ = norm(" ".join(mots)).replace("-", " ")
            if len(n_) < 4 or n_ in MOTS_COURANTS or n_ in PAS_UNE_COMMUNE:
                break
            if n_ == nom_c or (nom_c + " ").startswith(n_ + " "):
                return None                             # la commune annoncée est citée comme lieu : on la garde
            proches = [h for h in communes_nommees(n_)
                       if h.get("centre") and centre and km(h["centre"]["coordinates"], centre) <= 40]
            if proches:
                trouvee = trouvee or min(proches, key=lambda h: km(h["centre"]["coordinates"], centre))
                break
            mots = mots[:-1]
    return trouvee


def meme_bien(a, b):
    """Même maison publiée sur plusieurs sites, ou plusieurs fois sur un même site (plusieurs agences)."""
    if a["insee"] != b["insee"] or not (a.get("surf") and b.get("surf")) or abs(a["surf"] - b["surf"]) > 3:
        return False
    if a.get("pieces") and b.get("pieces") and a["pieces"] != b["pieces"]:
        return False
    if a.get("terrain") and b.get("terrain") and abs(a["terrain"] - b["terrain"]) > 0.1 * max(a["terrain"], b["terrain"]):
        return False
    if not a["approx"] and not b["approx"] and math.dist((a["lat"], a["lng"]), (b["lat"], b["lng"])) > 0.006:
        return False
    ecart = abs(a["prix"] - b["prix"]) / max(a["prix"], b["prix"])
    if ecart <= 0.015:
        return True
    # prix différents (frais d'agence) : il faut en plus des descriptions proches
    ma, mb = _mots(a), _mots(b)
    return ecart <= 0.08 and bool(ma) and bool(mb) and len(ma & mb) / len(ma | mb) >= 0.35


def regrouper(annonces):
    groupes = []
    for a in annonces:
        g = next((g for g in groupes if meme_bien(a, g[0])), None)
        (g.append(a) if g else groupes.append([a]))
    # annonce retenue : le meilleur prix, puis la plus récente ; les autres restent en liens secondaires
    for g in groupes:
        g.sort(key=lambda x: (x["prix"], jours_depuis(x.get("pub")) if jours_depuis(x.get("pub")) is not None else 9999))
    return groupes


def construire(brutes, communes, etat):
    """Annonces brutes -> maisons affichées (filtres, commune vérifiée, doublons regroupés, historique des prix)."""
    # plafond de prix, rattachement aux communes, localisation vérifiée, enrichissement
    gardees, ecartees, neufs = [], [], 0
    for a in brutes:
        if a["prix"] > sources.PRIX_MAX or sources.viager(a.get("titre"), a.get("desc")):
            continue
        if a.get("neuf") or sources.neuf(a.get("titre"), a.get("desc")):
            neufs += 1                                 # neuf, VEFA ou projet de construction : écarté d'office
            continue
        c = rattacher(a, communes)
        if not c:
            continue
        c = verifier_lieu(a, c, communes)
        if not c:
            ecartees.append(a)
            continue
        a["insee"], a["ville"] = c["code"], c["nom"]
        if not a.get("cp") and c["codesPostaux"]:
            a["cp"] = c["codesPostaux"][0]
        if not (a.get("lat") and a.get("lng")):
            a["lat"], a["lng"] = point_dans_commune(c, a["id"]); a["approx"] = True
        gardees.append(enrichir(a))

    # dédoublonnage, historique des prix
    sortie, aujourd = [], MAINTENANT.date().isoformat()
    for g in regrouper(gardees):
        base = g[0]                                   # meilleur prix (puis la plus récente)
        mid = next((etat["alias"][x["id"]] for x in g if x["id"] in etat["alias"]), base["id"])
        for x in g:
            etat["alias"][x["id"]] = mid
        h = etat["hist"].setdefault(mid, [])
        prix = min(x["prix"] for x in g)
        if not h or h[-1][1] != prix:
            h.append([aujourd, prix])
        etat["vu"].setdefault(mid, aujourd)
        pub = min((x["pub"] for x in g if x.get("pub")), default=None)
        jours = jours_depuis(pub)
        if jours is None:
            jours = jours_depuis(etat["vu"][mid]) or 0
        photos = []
        for x in g:
            photos += [p for p in x["photos"] if p not in photos] if x is base or not photos else []
        pick = lambda k: next((x[k] for x in g if x.get(k)), None)
        sortie.append({
            "id": mid, "lat": round(base["lat"], 6), "lng": round(base["lng"], 6), "approx": all(x["approx"] for x in g),
            "city": base["ville"], "cp": base["cp"], "insee": base["insee"], "type": base["type"],
            "surf": pick("surf"), "pieces": pick("pieces"), "chambres": pick("chambres"), "terrain": pick("terrain"),
            "price": prix, "year": pick("annee"), "dpe": pick("dpe"), "ges": pick("ges"),
            "atouts": sorted({t for x in g for t in x["atouts"]}), "titre": pick("titre"),
            "desc": max((x.get("desc") or "" for x in g), key=len)[:4000],
            "source": base["source"], "liens": [{"source": x["source"], "url": x["url"], "prix": x["prix"]} for x in g if x.get("url")],
            "photos": photos[:25], "days": jours, "neuf": any(x.get("neuf") for x in g),
            "pro": pick("pro"), "tf": pick("tf"), "hist": h[-10:],
        })
    if neufs:
        log(f"{neufs} annonce(s) de logement neuf ou de projet de construction écartée(s)")
    if ecartees:
        log(f"{len(ecartees)} annonce(s) écartée(s) car le bien est en réalité hors de vos communes")
    log(f"{len(sortie)} maison(s) après regroupement des doublons ({len(gardees)} annonces lues)")
    return sortie


# ------------------------------------------------------------ programme
def main():
    mode = sys.argv[1] if len(sys.argv) > 1 else "auto"
    if not CLE:
        sortir(0 if mode == "auto" else 1, "Mot de passe CLE_CARTE absent : ajoutez le secret dans les réglages du dépôt.")
    fin = None
    if FIN.exists():
        try:
            fin = datetime.fromisoformat(FIN.read_text().strip())
        except ValueError:
            pass
    if mode == "auto" and (not fin or MAINTENANT > fin):
        sortir(0, "Collecte automatique en pause (date d'arrêt dépassée). Cliquez sur Actualiser dans la carte pour la relancer.")
    if mode == "manuel":
        fin = MAINTENANT + DUREE

    etat = dechiffrer(ETAT.read_text(), CLE) if ETAT.exists() else {}
    etat.setdefault("hist", {}); etat.setdefault("alias", {}); etat.setdefault("cache", {}); etat.setdefault("vu", {})

    demande = os.environ.get("DEMANDE", "")
    fichier = os.environ.get("DEMANDE_FICHIER", "")
    if not demande and fichier and Path(fichier).exists():
        demande = Path(fichier).read_text()
    if demande:
        m = re.search(r"\{.*\}", demande, re.S)
        try:
            v = dechiffrer(m.group(0), CLE)
            etat["villes"] = v.get("villes", [])
            etat["communes"] = v.get("communes", [])
            log(f"Nouvelles villes reçues de la carte : {', '.join(c['name'] for c in etat['villes']) or 'aucune'}")
        except Exception as e:
            log(f"Demande illisible ({type(e).__name__}) : villes inchangées")

    codes = [c["code"] for c in etat.get("communes") or []] or [c["code"] for c in etat.get("villes") or []]
    # « + voisines » : les communes limitrophes sont toujours ajoutées ici, même si la carte ne les avait pas encore chargées
    for v in etat.get("villes") or []:
        if v.get("code") and v["code"] not in codes:
            codes.append(v["code"])
        if v.get("nb"):
            vs = voisines(v["code"])
            codes += [c["code"] for c in vs if c["code"] not in codes]
            log(f"{v.get('name', v['code'])} : {len(vs)} commune(s) limitrophe(s)")
    if not codes:
        log("Aucune ville choisie : ajoutez des villes dans la carte puis cliquez sur Actualiser.")
    communes = communes_detail(codes)
    log(f"{len(communes)} commune(s) suivie(s)")

    # les communes jamais lues (ou lues il y a le plus longtemps) passent en premier :
    # si le temps manque, ce sont les plus anciennes qui attendent la collecte suivante
    lu = etat.setdefault("lu", {})
    principales = [v.get("code") for v in etat.get("villes") or []]
    communes.sort(key=lambda c: (lu.get(c["code"], ""), c["code"] not in principales))
    sources.DEJA = {nom: {a["id"]: a for a in (etat["cache"].get(nom) or {}).get("annonces", []) if a.get("id")}
                    for nom in sources.SOURCES}
    sources.LIMITE = time.time() + float(os.environ.get("LIMITE_MIN", 33)) * 60      # GitHub coupe à 45 min : on garde de la marge pour enregistrer

    def lire(item):
        nom, f = item
        try:
            return nom, f(communes, log), None
        except Exception as e:
            return nom, None, e

    # annonces publiées au fur et à mesure (perso/partiel.enc) : la carte les affiche pendant la collecte
    fini = threading.Event()

    def instantane():
        brutes_p = []
        for nom in sources.SOURCES:
            cache = etat["cache"].get(nom) or {}
            faites = set(sources.ATTEINTES.get(nom, set()))
            brutes_p += [a for a in cache.get("annonces", []) if a.get("insee") in codes and a.get("insee") not in faites]
            brutes_p += list(sources.PARTIEL.get(nom, []))
        return [copie(a) for a in brutes_p]

    def copie(a):                                      # une annonce peut être en train d'être complétée par une source
        for _ in range(20):
            try:
                return copy.deepcopy(a)
            except RuntimeError:
                time.sleep(0.02)
        return copy.deepcopy(dict(a))

    def publier_partiel():
        _tl.muet = True
        attente = 30                                   # premier aperçu vite, puis toutes les ~75 s
        while not fini.wait(attente):
            attente = float(os.environ.get("PARTIEL_S", 75))
            try:
                sortie_p = construire(instantane(), communes, copy.deepcopy(etat))
                faites = set.intersection(*sources.ATTEINTES.values()) if sources.ATTEINTES else set()
                d = {"maj": datetime.now(timezone.utc).isoformat(timespec="seconds"), "fin": fin.isoformat(timespec="minutes"),
                     "villes": etat.get("villes", []), "communes": [c["code"] for c in communes], "sources": {}, "journal": [],
                     "partiel": {"debut": MAINTENANT.isoformat(timespec="seconds"), "faites": len(faites), "total": len(communes)},
                     "annonces": sortie_p}
                PARTIEL.parent.mkdir(parents=True, exist_ok=True)
                PARTIEL.write_text(chiffrer(d, CLE))
                g = ["git", "-c", "user.name=Collecte automatique", "-c", "user.email=41898282+github-actions[bot]@users.noreply.github.com"]
                subprocess.run(g + ["add", str(PARTIEL)], cwd=RACINE, check=True, capture_output=True)
                subprocess.run(g + ["commit", "-qm", "Annonces en cours de collecte"], cwd=RACINE, check=True, capture_output=True)
                for _ in range(3):
                    if subprocess.run(["git", "push", "-q", "origin", "HEAD:main"], cwd=RACINE, capture_output=True).returncode == 0:
                        break
                    subprocess.run(g + ["pull", "-q", "--rebase", "origin", "main"], cwd=RACINE, capture_output=True)
            except Exception as e:                     # un instantané raté n'empêche jamais la collecte : on réessaie vite
                print(f"(aperçu en cours de collecte non publié : {type(e).__name__} {e})", file=sys.stderr)
                attente = 5

    if os.environ.get("PARTIEL") == "1" and communes:
        threading.Thread(target=publier_partiel, daemon=True).start()

    bilan, brutes = {}, []
    with ThreadPoolExecutor(max_workers=len(sources.SOURCES)) as pool:   # les sites sont lus en même temps
        resultats = list(pool.map(lire, sources.SOURCES.items() if communes else []))
    fini.set()
    for nom, res, e in resultats:
        cache = etat["cache"].get(nom) or {}
        anciennes = [a for a in cache.get("annonces", []) if a.get("insee") in codes]
        if e is None:
            faites = sources.ATTEINTES.get(nom)
            if faites is not None:                    # communes pas encore lues ce coup-ci : on garde le résultat précédent
                gardees = [a for a in anciennes if a.get("insee") not in faites]
                res = res + gardees
            etat["cache"][nom] = {"date": MAINTENANT.isoformat(), "codes": codes, "annonces": res}
            bilan[nom] = {"ok": True, "n": len(res), "msg": f"{len(res)} annonce(s)"}
            log(f"{nom} : {len(res)} annonce(s)")
        else:
            res = anciennes
            raison = "site bloqué temporairement" if isinstance(e, sources.Bloque) else f"erreur ({type(e).__name__})"
            bilan[nom] = {"ok": False, "n": len(res), "msg": raison + (f", {len(res)} annonce(s) gardée(s) du {cache['date'][:10]}" if res else "")}
            log(f"{nom} : {raison} : {e}")
        brutes += res
    if sources.ATTEINTES:
        toutes = set.intersection(*sources.ATTEINTES.values())
        for code in toutes:
            lu[code] = MAINTENANT.isoformat()
        if len(toutes) < len(communes):
            log(f"{len(communes) - len(toutes)} commune(s) seront complétées à la prochaine collecte")

    sortie = construire(brutes, communes, etat)

    # nettoyage : on oublie les annonces disparues depuis plus de 90 jours
    actifs = {a["id"] for a in sortie}
    for mid in list(etat["hist"]):
        if mid not in actifs and etat["hist"][mid][-1][0] < (MAINTENANT - timedelta(days=90)).date().isoformat():
            etat["hist"].pop(mid, None); etat["vu"].pop(mid, None)

    donnees = {"maj": MAINTENANT.isoformat(timespec="minutes"), "fin": fin.isoformat(timespec="minutes"),
               "villes": etat.get("villes", []), "communes": [c["code"] for c in communes],
               "sources": bilan, "journal": journal[-40:], "annonces": sortie}
    SORTIE.parent.mkdir(parents=True, exist_ok=True); ETAT.parent.mkdir(parents=True, exist_ok=True)
    SORTIE.write_text(chiffrer(donnees, CLE))
    ETAT.write_text(chiffrer(etat, CLE))
    FIN.write_text(fin.isoformat(timespec="minutes"))
    print("Résumé : " + " ; ".join(f"site {i + 1} {'ok' if v['ok'] else 'indisponible'}" for i, v in enumerate(bilan.values()))
          + f" ; {len(communes)} commune(s) ; {len(sortie)} maison(s)")
    sortir(0, f"Collecte terminée : {len(sortie)} maisons. Collecte automatique jusqu'au {fin:%d/%m/%Y}.", publier=True)


if __name__ == "__main__":
    try:
        main()
    except SystemExit:
        raise
    except Exception as e:                       # aucun détail en clair dans le journal public
        sortir(1, f"La collecte a rencontré un problème ({type(e).__name__}).")
