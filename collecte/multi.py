"""Recherche hebdomadaire des biens « multi-logements » (demande d'Oré du 27/11/2026).

Critères :
  - terrain avec 2 logements : maison principale + maison secondaire, maison scindée en 2 parties distinctes,
    ou maison avec dépendance d'au moins 50 m² à aménager (repérage dans le texte : collecte/multi_detect.py) ;
  - à moins d'une heure de Paris en transports en commun (idéalement moins d'une heure jusqu'au métro
    La Motte-Picquet–Grenelle ou Bolivar / Colonel Fabien) ;
  - dans une commune, ou à moins de 5 km d'une commune, qui a école primaire, collège, lycée, médecin généraliste,
    psychologue ou psychiatre, orthophoniste et centre de loisirs (Base permanente des équipements de l'INSEE).
Prix : plafond de 800 000 € avec la tolérance de +15 % convenue pour cette recherche (920 000 €).
Neuf, VEFA, projets de construction et viager écartés ; doublons regroupés (l'annonce la moins chère est gardée).

Temps de trajet (approximation d'heure de pointe, suffisante pour délimiter une zone d'achat) :
  accès à la gare  = 5 min + 3 min par km à vol d'oiseau (vélo, bus ou voiture, attente comprise)
  gare -> Paris    = moyenne réelle des trains de 6 h-9 h et 18 h-21 h (horaires IDFM, site/transports.html) ;
                     celle des trains directs quand il y en a au moins 4 sur ces créneaux
  Paris -> métro   = 7 min + 2,5 min par km entre la gare parisienne d'arrivée et la station visée

Fichiers : etat/multi.enc (mémoire chiffrée de la recherche), site/multi.enc (ce que lit l'onglet « Multi-logements »).
Usage : python collecte/multi.py [auto|manuel]   (auto : ne fait rien si la recherche de la semaine est déjà faite)
"""
import csv, io, json, math, os, re, sys, threading, time, zipfile
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, os.path.dirname(__file__))
from chiffrement import chiffrer, dechiffrer
import sources
import collecte as C
from multi_detect import analyser

RACINE = C.RACINE
ETAT, SORTIE = RACINE / "etat/multi.enc", RACINE / "site/multi.enc"
TRANSPORTS = RACINE / "site/transports.html"
CLE = C.CLE
MAINTENANT = C.MAINTENANT
PRIX_MAX = 920_000                    # 800 000 € + 15 %
MAX_PARIS, RAYON_EQUIP = 60, 5.0      # minutes ; km
# départements autour de Paris où une gare peut être à moins d'une heure (Paris lui-même exclu)
DEPTS = ["77", "78", "91", "92", "93", "94", "95", "60", "28", "27", "45", "02", "10", "51", "89"]
CIBLES = {"La Motte-Picquet": (2.2984, 48.8496), "Bolivar / Colonel Fabien": (2.3723, 48.8792)}
# gares parisiennes d'arrivée (champ « via » de site/transports.html) : position approximative
VIA = {
    "Gare du Nord": (2.3553, 48.8809), "Gare Saint-Lazare": (2.3254, 48.8763), "Gare de Lyon": (2.3744, 48.8443),
    "Gare Montparnasse": (2.3205, 48.8412), "Bibliothèque François Mitterrand": (2.3767, 48.8298),
    "Cité Universitaire": (2.3384, 48.8210), "Gare de l'Est": (2.3592, 48.8768), "Nation": (2.3958, 48.8484),
    "Henri Farman": (2.2737, 48.8318), "Charles de Gaulle - Étoile": (2.2950, 48.8738), "Porte de Choisy": (2.3647, 48.8200),
    "Rosa Parks": (2.3734, 48.8968), "Porte de Clichy": (2.3134, 48.8946), "Pont Cardinet": (2.3150, 48.8880),
    "Maison Blanche": (2.3584, 48.8222), "Porte de Charenton": (2.4025, 48.8335), "Porte des Lilas": (2.4066, 48.8770),
    "Pont du Garigliano - Hôpital Européen G. Pompidou": (2.2701, 48.8392), "Gare d'Austerlitz": (2.3655, 48.8424),
    "Neuilly - Porte Maillot": (2.2826, 48.8781), "Porte de Saint-Ouen": (2.3290, 48.8975), "Porte de Pantin": (2.3920, 48.8885),
    "Porte de Versailles": (2.2876, 48.8323), "Porte de Vincennes": (2.4108, 48.8470), "Porte de la Villette": (2.3858, 48.8977),
    "Porte de Saint-Cloud": (2.2567, 48.8379), "Porte de Champerret": (2.2924, 48.8856), "Porte de Montreuil": (2.4105, 48.8535),
    "Porte de la Chapelle": (2.3594, 48.8975), "Porte de Vanves": (2.3054, 48.8277), "Porte d'Orléans": (2.3254, 48.8233),
    "Bercy": (2.3796, 48.8401), "Porte d'Ivry": (2.3693, 48.8215), "Michel-Ange - Molitor": (2.2617, 48.8449),
    "Porte de Bagnolet": (2.4087, 48.8645),
}
PARIS_CENTRE = (2.3522, 48.8566)

# équipements recherchés : libellés de la nomenclature TYPEQU de l'INSEE (BPE)
BPE_ZIP = "https://www.insee.fr/fr/statistiques/fichier/8217525/BPE25.zip"
EQUIP = {   # codes TYPEQU de la BPE 2025 (vérifiés le 27/11/2026 dans TYPEQU_2025.csv)
    "primaire": ("École primaire", ["C108", "C109"]),
    "college": ("Collège", ["C201"]),
    "lycee": ("Lycée", ["C301", "C302", "C303"]),
    "medecin": ("Médecin généraliste", ["D265", "D113", "D108"]),
    "psy": ("Psychologue ou psychiatre", ["D250", "D269", "D109"]),
    "ortho": ("Orthophoniste", ["D282"]),
    "loisirs": ("Centre de loisirs", ["D505"]),
}

journal = C.journal
log = C.log


def km(a, b):
    """Distance en km entre deux points (lng, lat)."""
    return math.hypot((a[0] - b[0]) * 111.2 * math.cos(math.radians((a[1] + b[1]) / 2)), (a[1] - b[1]) * 111.2)


# ------------------------------------------------------------ temps jusqu'à Paris
def gares():
    s = TRANSPORTS.read_text(encoding="utf-8")
    m = re.search(r"/\*TEMPS_PARIS_DEBUT\*/window\.TEMPS_PARIS = (.*?);/\*TEMPS_PARIS_FIN\*/", s, re.S)
    out = []                       # temps des trains directs s'il y en a au moins 4 aux heures de pointe
    for nom, lst in json.loads(m.group(1))["gares"].items():
        for e in lst:
            out.append({"nom": nom, "p": (e["x"], e["y"]), "m": e["d"] if e.get("d") and e.get("dn", 0) >= 4 else e["m"], "via": e.get("via"), "l": e.get("l") or []})
    return out


def noms_gares():
    """Nom lisible de chaque gare (la clé de transports.html est normalisée) : on garde la clé, en capitales initiales."""
    return lambda n: " ".join(w.capitalize() if len(w) > 2 or i == 0 else w for i, w in enumerate(n.split()))


def trajet(p, liste):
    """Meilleur trajet depuis le point p (lng, lat) : temps jusqu'à Paris et jusqu'aux deux stations visées."""
    best = None
    beau = noms_gares()
    for g in liste:
        d = km(p, g["p"])
        if d > 12:
            continue
        acces = 5 + 3 * d
        paris = acces + g["m"]
        v = VIA.get(g["via"], PARIS_CENTRE)
        cibles = {k: round(paris + 7 + 2.5 * km(v, c)) for k, c in CIBLES.items()}
        cand = {"paris": round(paris), "cible": min(cibles.values()), "cibles": cibles, "gare": beau(g["nom"]),
                "gare_km": round(d, 1), "train": g["m"], "via": g["via"], "lignes": g["l"][:2]}
        if not best or (cand["cible"], cand["paris"]) < (best["cible"], best["paris"]):
            best = cand
    if best:
        best["ideal"] = best["cible"] <= MAX_PARIS
    return best


# ------------------------------------------------------------ communes et équipements
def communes_zone(liste):
    toutes = []
    def dep(d):
        try:
            return C.get_json(f"https://geo.api.gouv.fr/departements/{d}/communes",
                              params={"fields": "nom,code,codesPostaux,centre,population", "format": "json"})
        except Exception as e:
            log(f"Département {d} indisponible ({type(e).__name__})"); return []
    with ThreadPoolExecutor(max_workers=6) as pool:
        for res in pool.map(dep, DEPTS):
            toutes += [c for c in res if c.get("centre")]
    for c in toutes:
        c["p"] = tuple(c["centre"]["coordinates"])
        c["trajet"] = trajet(c["p"], liste)
    return toutes


def bpe(etat):
    """{commune: [équipements présents]} d'après la BPE de l'INSEE ; mise en cache 30 jours dans etat."""
    cache = etat.get("bpe") or {}
    if cache.get("date") and (MAINTENANT - datetime.fromisoformat(cache["date"])).days < 30 and cache.get("communes"):
        return cache["communes"]
    s = sources.session()
    codes = {code: cle for cle, (_, lst) in EQUIP.items() for code in lst}
    z = s.get(BPE_ZIP, timeout=600)
    z.raise_for_status()
    zf = zipfile.ZipFile(io.BytesIO(z.content))
    nom = max((i for i in zf.infolist() if i.filename.lower().endswith(".csv")), key=lambda i: i.file_size).filename
    par = {}
    with zf.open(nom) as f:
        r = csv.reader(io.TextIOWrapper(f, encoding="utf-8-sig", errors="ignore"), delimiter=";")
        tete = [h.strip().upper() for h in next(r)]
        icom = next(i for i, h in enumerate(tete) if h in ("DEPCOM", "CODGEO", "COM", "CODE_COMMUNE"))
        ityp = tete.index("TYPEQU")
        for row in r:
            if len(row) <= max(icom, ityp):
                continue
            cle = codes.get(row[ityp])
            if cle:
                par.setdefault(row[icom][:5], set()).add(cle)
    communes = {k: sorted(v) for k, v in par.items()}
    etat["bpe"] = {"date": MAINTENANT.isoformat(), "communes": communes, "codes": codes}
    return communes


def equipements(c, toutes, eq):
    """Pour chaque équipement : sur place, ou commune la plus proche à moins de 5 km."""
    res, manque = {}, []
    proches = sorted(((km(c["p"], x["p"]), x) for x in toutes if x is not c), key=lambda t: t[0])
    for cle, (nom, _) in EQUIP.items():
        if cle in eq.get(c["code"], []):
            res[cle] = {"nom": nom, "ou": "sur place"}
            continue
        d, x = next(((d, x) for d, x in proches if d <= RAYON_EQUIP and cle in eq.get(x["code"], [])), (None, None))
        if x:
            res[cle] = {"nom": nom, "ou": f"{x['nom']} ({d:.0f} km)".replace("(0 km)", "(< 1 km)")}
        else:
            res[cle] = {"nom": nom, "ou": None}
            manque.append(cle)
    return res, manque


# ------------------------------------------------------------ programme
def semaine():
    """Rendez-vous de la semaine : lundi 6 h, heure de Paris."""
    from zoneinfo import ZoneInfo
    now = datetime.now(ZoneInfo("Europe/Paris"))
    lundi = (now - timedelta(days=now.weekday())).replace(hour=6, minute=0, second=0, microsecond=0)
    return lundi if lundi <= now else lundi - timedelta(days=7)


def main():
    mode = sys.argv[1] if len(sys.argv) > 1 else "auto"
    if not CLE:
        C.sortir(1, "Mot de passe CLE_CARTE absent.")
    etat = dechiffrer(ETAT.read_text(), CLE) if ETAT.exists() else {}
    for k in ("hist", "alias", "cache", "vu", "geo", "zones", "trouve"):
        etat.setdefault(k, {})
    if mode == "auto" and etat.get("maj") and datetime.fromisoformat(etat["maj"]) >= semaine():
        C.sortir(0, "Recherche multi-logements déjà faite cette semaine.")
    t0 = time.time()
    sources.PRIX_MAX = PRIX_MAX
    sources.ZONES = etat["zones"]

    liste = gares()
    toutes = communes_zone(liste)
    zone = [c for c in toutes if c["trajet"] and c["trajet"]["paris"] <= MAX_PARIS]
    log(f"{len(zone)} commune(s) à moins de {MAX_PARIS} min de Paris (sur {len(toutes)} autour de Paris)")
    try:
        eq = bpe(etat)
        bpe_ok = True
    except Exception as e:
        log(f"Équipements (BPE) indisponibles ({type(e).__name__}) : critère non appliqué cette semaine")
        eq, bpe_ok = {}, False
    retenues, equip = [], {}
    for c in zone:
        res, manque = equipements(c, toutes, eq) if bpe_ok else ({}, [])
        equip[c["code"]] = res
        if not manque:
            retenues.append(c)
    log(f"{len(retenues)} commune(s) avec tous les équipements (sur place ou à moins de {RAYON_EQUIP:.0f} km)")
    # les plus proches de Paris d'abord : si le temps manque, ce sont les plus lointaines qui attendent la semaine suivante
    retenues.sort(key=lambda c: (c["trajet"]["cible"], c["trajet"]["paris"]))
    codes = [c["code"] for c in retenues]
    communes = C.communes_detail(codes, etat["geo"])

    # collecte : mêmes sites que la carte ; communes déjà lues cette semaine gardées si le temps manque
    sources.LIMITE = t0 + float(os.environ.get("LIMITE_MIN", 170)) * 60
    bilan, brutes = {}, []
    def lire(item):
        nom, f = item
        try:
            return nom, f(communes, log), None
        except Exception as e:
            return nom, None, e
    with ThreadPoolExecutor(max_workers=len(sources.SOURCES)) as pool:
        resultats = list(pool.map(lire, sources.SOURCES.items() if communes else []))
    for nom, res, e in resultats:
        cache = etat["cache"].get(nom) or {}
        anciennes = [a for a in cache.get("annonces", []) if a.get("insee") in codes]
        if e is None:
            faites = sources.ATTEINTES.get(nom)
            if faites is not None:
                res = res + [a for a in anciennes if a.get("insee") not in faites]
            etat["cache"][nom] = {"date": MAINTENANT.isoformat(), "annonces": res}
            bilan[nom] = {"ok": True, "n": len(res), "msg": f"{len(res)} annonce(s)"}
        else:
            res = anciennes
            bilan[nom] = {"ok": False, "n": len(res), "msg": f"indisponible ({type(e).__name__})"}
        log(f"{nom} : {bilan[nom]['msg']}")
        brutes += res

    # pré-filtre : seules les annonces qui ressemblent à un multi-logement passent dans la chaîne commune
    candidates = [a for a in brutes if analyser(a.get("titre"), a.get("desc"), a.get("pieces"), a.get("surf"))]
    log(f"{len(candidates)} annonce(s) multi-logements repérée(s) sur {len(brutes)} lue(s)")
    sortie = C.construire(candidates, communes, etat)
    par_code = {c["code"]: c for c in retenues}
    gardees = []
    for a in sortie:
        m = analyser(a.get("titre"), a.get("desc"), a.get("pieces"), a.get("surf"))
        if not m:
            continue
        c = par_code.get(a["insee"])
        t = trajet((a["lng"], a["lat"]), liste) if not a["approx"] else (c["trajet"] if c else None)
        if not t or t["paris"] > MAX_PARIS:
            continue
        a["multi"] = m
        a["paris"] = t
        a["equip"] = equip.get(a["insee"], {})
        a["trouve"] = etat["trouve"].setdefault(a["id"], MAINTENANT.date().isoformat())
        gardees.append(a)
    gardees.sort(key=lambda a: (not a["paris"]["ideal"], -a["multi"]["score"], a["price"]))
    log(f"{len(gardees)} bien(s) multi-logements retenu(s)")

    etat["maj"] = MAINTENANT.isoformat(timespec="minutes")
    donnees = {"maj": etat["maj"], "fin": (MAINTENANT + timedelta(days=3650)).isoformat(timespec="minutes"),
               "villes": [], "communes": codes, "sources": bilan, "journal": journal[-60:], "annonces": gardees,
               "multi": {"communes": len(retenues), "zone": len(zone), "prix_max": PRIX_MAX, "bpe": bpe_ok,
                         "zones": [{"code": c["code"], "nom": c["nom"], "lng": c["p"][0], "lat": c["p"][1],
                                    "paris": c["trajet"]["paris"], "cible": c["trajet"]["cible"]} for c in retenues]}}
    SORTIE.write_text(chiffrer(donnees, CLE))
    ETAT.write_text(chiffrer(etat, CLE))
    print(f"Résumé : {len(zone)} communes à moins d'1 h, {len(retenues)} avec équipements, "
          f"{len(brutes)} annonces lues, {len(candidates)} candidates, {len(gardees)} biens retenus, "
          + " ; ".join(f"site {i + 1} {'ok' if v['ok'] else 'indisponible'}" for i, v in enumerate(bilan.values()))
          + f" ; {round((time.time() - t0) / 60)} min")
    C.sortir(0, f"Recherche multi-logements terminée : {len(gardees)} biens.", publier=True)


if __name__ == "__main__":
    try:
        main()
    except SystemExit:
        raise
    except Exception as e:                       # aucun détail en clair dans le journal public
        C.sortir(1, f"La recherche multi-logements a rencontré un problème ({type(e).__name__}).")
