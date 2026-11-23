"""Lecture des annonces de maisons sur chaque site.

Chaque source reçoit la liste des communes suivies et renvoie des annonces au format commun :
  id, source, url, titre, desc, prix, surf, pieces, chambres, terrain, annee, dpe, ges,
  photos[], lat, lng, approx (position approximative), ville, cp, insee, pub (date ISO), neuf, pro
Une source qui échoue lève une exception : elle est notée dans le journal, sans bloquer les autres.
"""
import json, re, time, random, html
from datetime import datetime, timezone

import requests

# Requêtes simples et identifiées : on ne contourne aucune protection anti-robot.
# Un site qui refuse (403, captcha) est noté « refuse la collecte » et n'est pas forcé.
UA = "carte-immo/1.0 (outil de recherche personnel ; quelques requetes par jour)"
MAX_PAR_COMMUNE = 300          # garde-fou par site et par commune
PRIX_MAX = 800_000             # au-delà, les annonces sont ignorées dès la collecte (choix d'Oré)


LIMITE = None                  # heure (time.time()) à laquelle chaque site s'arrête, pour finir avant la limite de GitHub
ATTEINTES = {}                 # site -> codes des communes effectivement lues (les autres gardent l'ancien résultat)


def parcourir(nom, communes, log):
    """Parcourt les communes tant qu'il reste du temps ; note celles qui ont été lues."""
    faites = ATTEINTES.setdefault(nom, set())
    for i, c in enumerate(communes):
        if LIMITE and time.time() > LIMITE:
            log(f"{nom} : temps écoulé, {len(communes) - i} commune(s) reportée(s) à la prochaine collecte")
            return
        yield c
        faites.add(c["code"])


class Bloque(Exception):
    """Le site refuse la connexion (protection anti-robot)."""


class _Session(requests.Session):
    def request(self, *a, **kw):
        kw.setdefault("timeout", 30)
        return super().request(*a, **kw)


def session():
    s = _Session()
    s.headers.update({"User-Agent": UA, "Accept-Language": "fr-FR,fr;q=0.9"})
    return s


def pause(a=1.0, b=2.5):
    time.sleep(random.uniform(a, b))


def get(s, url, **kw):
    r = s.get(url, **kw)
    if r.status_code in (403, 429) or "captcha-delivery" in r.text[:3000] or "datadome" in r.text[:3000].lower():
        raise Bloque(f"accès refusé ({r.status_code})")
    r.raise_for_status()
    return r


def nombre(x):
    if x is None:
        return None
    if isinstance(x, (int, float)):
        return x
    if isinstance(x, list):
        return nombre(x[0]) if x else None
    m = re.search(r"\d[\d\s.  ]*(?:,\d+)?", str(x))
    if not m:
        return None
    t = re.sub(r"[\s.  ]", "", m.group(0)).replace(",", ".")
    try:
        v = float(t)
        return int(v) if v.is_integer() else v
    except ValueError:
        return None


def entier(x):
    v = nombre(x)
    return int(round(v)) if v is not None else None


def lettre(x):
    x = (str(x or "").strip().upper())[:1]
    return x if x in "ABCDEFG" and x else None


def slug(t):
    import unicodedata
    t = unicodedata.normalize("NFD", t).encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z0-9]+", "-", t).strip("-")


def texte(t):
    """Texte lisible : sans balises HTML ni entités, sauts de ligne conservés."""
    t = re.sub(r"<br\s*/?>|</p>", "\n", str(t or ""), flags=re.I)
    t = html.unescape(re.sub(r"<[^>]+>", "", t))
    return re.sub(r"\n{3,}", "\n\n", re.sub(r"[ \t]+", " ", t)).strip()


def a_construire(titre, desc=""):
    """Offres « terrain + maison à construire » des constructeurs : ce ne sont pas des maisons existantes."""
    t = (str(titre or "") + " " + str(desc or "")[:300]).lower()
    return bool(re.search(r"(?:&agrave;|à|a) construire|projet de (?:construction|maison)|terrain \+ maison|maison \+ terrain"
                          r"|contrat de construction|\bccmi\b", t))


def viager(titre, desc=""):
    """Ventes en viager : écartées d'office (choix d'Oré)."""
    return "viager" in (str(titre or "") + " " + str(desc or "")).lower()


# ---------------------------------------------------------------- Bien'ici
def bienici(communes, log):
    s = session()
    out = []
    for c in parcourir("Bien'ici", communes, log):
        r = get(s, "https://res.bienici.com/suggest.json", params={"q": c["nom"]}).json()
        zones = [z for z in r if c["code"] in (z.get("insee_codes") or [z.get("insee_code")])] or \
                [z for z in r if set(z.get("postalCodes") or []) & set(c["codesPostaux"] or [])
                 and slug(z.get("name", "")) == slug(c["nom"])]
        if not zones:
            log(f"Bien'ici : commune introuvable ({c['nom']})")
            continue
        zid = zones[0]["zoneIds"]
        page, n = 0, 0
        while n < MAX_PAR_COMMUNE:
            f = {"size": 100, "from": page * 100, "showAllModels": False, "filterType": "buy",
                 "propertyType": ["house"], "maxPrice": PRIX_MAX, "sortBy": "publicationDate", "sortOrder": "desc",
                 "onTheMarket": [True], "zoneIdsByTypes": {"zoneIds": zid}}
            j = get(s, "https://www.bienici.com/realEstateAds.json", params={"filters": json.dumps(f)}).json()
            ads = j.get("realEstateAds") or []
            for a in ads:
                pos = (a.get("blurInfo") or {}).get("position") or (a.get("blurInfo") or {}).get("centroid") or {}
                exact = (a.get("blurInfo") or {}).get("type") == "exact"
                prix = entier(a.get("price"))
                if not prix or a_construire(a.get("title"), a.get("description")):
                    continue
                out.append({
                    "id": "bi-" + str(a["id"]), "source": "Bien'ici",
                    "url": f"https://www.bienici.com/annonce/vente/{slug(a.get('city') or c['nom'])}/maison/{a.get('roomsQuantity') or 1}pieces/{a['id']}",
                    "titre": texte(a.get("title")), "desc": texte(a.get("description")),
                    "prix": prix, "surf": entier(a.get("surfaceArea")), "pieces": entier(a.get("roomsQuantity")),
                    "chambres": entier(a.get("bedroomsQuantity")), "terrain": entier(a.get("landSurfaceArea")),
                    "annee": entier(a.get("yearOfConstruction")),
                    "dpe": lettre(a.get("energyClassification")), "ges": lettre(a.get("greenhouseGazClassification")),
                    "photos": [p.get("url") for p in a.get("photos") or [] if p.get("url")],
                    "lat": pos.get("lat"), "lng": pos.get("lon") or pos.get("lng"), "approx": not exact,
                    "ville": a.get("city") or c["nom"], "cp": a.get("postalCode"), "insee": c["code"],
                    "pub": a.get("publicationDate"), "neuf": bool(a.get("newProperty")),
                    "pro": a.get("accountType") != "particulier" if a.get("accountType") else None,
                })
            n += len(ads)
            if len(ads) < 100 or n >= (j.get("total") or 0):
                break
            page += 1
            pause()
        pause()
    return out


# ---------------------------------------------------------------- Espaces Atypiques
# Respecte le fichier robots.txt du site : liste des annonces lue dans le plan du site (sitemap),
# puis fiche de chaque annonce située dans une commune suivie.
def espaces_atypiques(communes, log):
    s = session()
    base = "https://www.espaces-atypiques.com"
    idx = get(s, base + "/sitemap_index.xml").text
    plans = [u for u in re.findall(r"<loc>([^<]+)</loc>", idx) if "/vente-sitemap" in u]
    cibles = {(cp, slug(c["nom"])): c for c in communes for cp in c["codesPostaux"] or []}
    urls = []
    for plan in plans:
        try:
            contenu = get(s, plan).text
        except (requests.HTTPError, requests.ConnectionError, requests.Timeout):
            log(f"Espaces Atypiques : une partie du plan du site est indisponible ({plan.rsplit('/', 1)[-1]})")
            continue
        for u in re.findall(r"<loc>([^<]+/ventes/[^<]+)</loc>", contenu):
            m = re.search(r"/ventes/(\d{5})-([a-z0-9-]+)", u)
            if m and any(m.group(1) == cp and m.group(2).startswith(sl + "-") for cp, sl in cibles):
                urls.append((u, next(c for (cp, sl), c in cibles.items() if m.group(1) == cp and m.group(2).startswith(sl + "-"))))
        pause(.3, .8)
    out = []
    for u, c in urls[:200]:
        if LIMITE and time.time() > LIMITE:
            log("Espaces Atypiques : temps écoulé, lecture des fiches interrompue")
            break
        try:
            t = get(s, u).text
        except (requests.HTTPError, requests.ConnectionError, requests.Timeout):   # une fiche lente ne bloque plus les autres
            continue
        m = re.search(r'\{[^{}]*"prix_vente"[^{}]*\}', t)
        if not m:
            continue
        d = json.loads(m.group(0))
        if d.get("status") not in (None, "", "envente") or (d.get("type_de_bien") or "").lower() not in ("maison", "propriété", "propriete", "demeure", "longère", "longere", "villa", "ferme", ""):
            continue
        prix = entier(d.get("prix_vente"))
        if not prix or prix > PRIX_MAX:
            continue
        titre = html.unescape((re.search(r'property="og:title" content="([^"]*)"', t) or [None, ""])[1]).split(" à ")[0]
        desc = ""
        for ld in re.findall(r'<script[^>]*ld\+json[^>]*>(.*?)</script>', t, re.S):
            if "RealEstateListing" in ld:
                try:
                    desc = json.loads(ld).get("description") or ""
                except ValueError:
                    pass
        pub = (re.search(r'"datePublished":"([^"]+)"', t) or [None, None])[1]
        ref = str(d.get("reference") or u.rstrip("/").split("-")[-1])
        photos = []
        for ph in re.findall(r'https://www\.espaces-atypiques\.com/wp-content/uploads/\d+/' + re.escape(ref) + r'/[^"\' )]+?\.(?:jpg|jpeg|webp)', t):
            ph = re.sub(r"-\d+x\d+(?=\.\w+$)", "", ph)          # version pleine taille
            if ph not in photos:
                photos.append(ph)
        out.append({
            "id": "ea-" + ref, "source": "Espaces Atypiques", "url": u, "titre": texte(titre), "desc": texte(desc),
            "prix": prix, "surf": entier(d.get("surface")), "pieces": entier(d.get("nb_pieces")),
            "chambres": entier(d.get("nb_chambres")), "terrain": entier(d.get("terrain")), "annee": None,
            "dpe": None, "ges": None, "tf": entier(d.get("taxe_fonciere")), "photos": photos[:25],
            "lat": None, "lng": None, "approx": True, "ville": d.get("ville") or c["nom"], "cp": d.get("cp"),
            "insee": c["code"], "pub": pub, "neuf": False, "pro": True,
        })
        pause(.8, 1.8)
    log(f"Espaces Atypiques : {len(urls)} annonce(s) dans vos communes, {len(out)} maison(s) en vente")
    return out


# ---------------------------------------------------------------- Notaires de France (immobilier.notaires.fr)
# Interface publique du site ; robots.txt demande 10 s entre deux requêtes.
def notaires(communes, log):
    s = session()
    api = "https://www.immobilier.notaires.fr/pub-services/inotr-www-annonces/v1/annonces"
    out = []
    for c in parcourir("Notaires de France", communes, log):
        page, pages = 1, 1
        while page <= min(pages, 4):
            j = get(s, api, params={"page": page, "parPage": 100, "typeTransactions": "VENTE", "typeBiens": "MAI",
                                    "prixMax": PRIX_MAX, "viager": "NON", "ville": c["code"]}).json()
            pages = j.get("nbPages") or 1
            for a in j.get("annonceResumeDto") or []:
                if a.get("inseeCommune") != c["code"] or a.get("viager") == "OUI":
                    continue
                prix = entier(a.get("prixTotal") or a.get("prixAffiche"))     # prix frais de négociation inclus
                if not prix:
                    continue
                desc = texte(a.get("descriptionFr"))
                out.append({
                    "id": "not-" + str(a.get("annonceId") or a.get("id")), "source": "Notaires de France",
                    "url": a.get("urlDetailAnnonceFr"), "titre": f"Maison {a.get('nbPieces') or ''} pièces".replace("  ", " "),
                    "desc": desc, "prix": prix, "surf": entier(a.get("surface")), "pieces": entier(a.get("nbPieces")),
                    "chambres": None, "terrain": entier(a.get("surfaceTerrain")), "annee": None, "dpe": None, "ges": None,
                    "photos": [a["urlPhotoPrincipale"]] if a.get("urlPhotoPrincipale") else [],
                    "lat": None, "lng": None, "approx": True, "ville": a.get("communeNom") or c["nom"],
                    "cp": a.get("codePostal"), "insee": c["code"], "pub": a.get("dateCreation"),
                    "neuf": a.get("ancienNeuf") == "NEUF", "pro": True,
                })
            page += 1
            time.sleep(10)
    return out


# ---------------------------------------------------------------- Lecture générique des données structurées (schema.org)
def _ld_blocs(t):
    for m in re.findall(r'<script[^>]*application/ld\+json[^>]*>(.*?)</script>', t, re.S):
        try:
            yield json.loads(m)
        except ValueError:
            continue


def _ld_annonces(o):
    """Toutes les fiches RealEstateListing / House / SingleFamilyResidence trouvées dans un bloc JSON-LD."""
    if isinstance(o, list):
        for x in o:
            yield from _ld_annonces(x)
    elif isinstance(o, dict):
        t = o.get("@type")
        t = t if isinstance(t, list) else [t]
        if any(x in ("RealEstateListing", "House", "SingleFamilyResidence", "Residence", "Accommodation", "Offer") for x in t) and (o.get("offers") or o.get("price") or o.get("url")):
            yield o
            return
        for k in ("@graph", "itemListElement", "item", "mainEntity"):
            if k in o:
                yield from _ld_annonces(o[k])


def _val(x):
    if isinstance(x, dict):
        return x.get("value") or x.get("@value")
    return x


def ld_vers_annonce(o, source, prefixe, c):
    offre = o.get("offers") or {}
    offre = offre[0] if isinstance(offre, list) and offre else offre
    bien = o.get("about") or o.get("itemOffered") or offre.get("itemOffered") or o.get("mainEntity") or o
    bien = bien[0] if isinstance(bien, list) and bien else bien
    adr = bien.get("address") or o.get("address") or {}
    geo = bien.get("geo") or o.get("geo") or {}
    img = o.get("image") or bien.get("image") or []
    img = [img] if isinstance(img, (str, dict)) else img
    photos = [i.get("url") or i.get("contentUrl") if isinstance(i, dict) else i for i in img]
    prix = entier(offre.get("price") or o.get("price"))
    url = o.get("url") or offre.get("url") or ""
    return {
        "id": prefixe + "-" + (re.findall(r"\d{4,}", url) or [slug(url)[-24:]])[-1], "source": source, "url": url,
        "titre": texte(o.get("name") or bien.get("name")), "desc": texte(o.get("description") or bien.get("description")),
        "prix": prix, "surf": entier(_val(bien.get("floorSize"))), "pieces": entier(bien.get("numberOfRooms")),
        "chambres": entier(bien.get("numberOfBedrooms")), "terrain": None, "annee": entier(bien.get("yearBuilt")),
        "dpe": None, "ges": None, "photos": [p for p in photos if p and str(p).startswith("http")][:25],
        "lat": nombre(geo.get("latitude")), "lng": nombre(geo.get("longitude")), "approx": True,
        "ville": adr.get("addressLocality") or c["nom"] if isinstance(adr, dict) else c["nom"],
        "cp": adr.get("postalCode") if isinstance(adr, dict) else None, "insee": None,
        "pub": o.get("datePosted") or o.get("datePublished"), "neuf": False, "pro": True,
    }


# ---------------------------------------------------------------- SAFTI (réseau de mandataires)
def safti(communes, log):
    s = session()
    out, vus = [], set()
    for c in parcourir("SAFTI", communes, log):
        for cp in (c["codesPostaux"] or [])[:3]:
            r = s.get(f"https://www.safti.fr/annonces/achat/maison/{slug(c['nom'])}-{cp}")
            if r.status_code in (403, 429):
                raise Bloque(f"accès refusé ({r.status_code})")
            if r.status_code != 200:
                continue
            for bloc in _ld_blocs(r.text):
                for o in _ld_annonces(bloc):
                    a = ld_vers_annonce(o, "SAFTI", "safti", c)
                    if a["prix"] and a["id"] not in vus and "/maison/" in a["url"]:
                        vus.add(a["id"]); out.append(a)
            pause()
    if out:
        log(f"SAFTI : exemple lu {json.dumps({k: out[0][k] for k in ('titre', 'prix', 'surf', 'pieces', 'ville', 'cp', 'lat')}, ensure_ascii=False)}")
    return out


# Sites testés le 20/11/2026 depuis GitHub : Leboncoin, SeLoger, Logic-Immo, PAP, Figaro Immo,
# Ouest-France Immo et AVendreALouer refusent la collecte automatique. Ils ne sont pas interrogés :
# la carte propose à la place un lien direct vers leur recherche pour chaque ville.
SOURCES = {"Bien'ici": bienici, "Espaces Atypiques": espaces_atypiques, "Notaires de France": notaires, "SAFTI": safti}
