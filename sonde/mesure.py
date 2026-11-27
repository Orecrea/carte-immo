"""Sonde ponctuelle (test, non branchée à la carte) : parmi les maisons d'Île-de-France publiées par chaque réseau,
combien sont absentes de Bien'ici ? Échantillon pris sur les premières pages IDF de chaque site, puis recherche
de chaque bien sur Bien'ici (même commune, prix à ±3 %, surface à ±5 % quand elle est connue)."""
import html, json, re, time, unicodedata
import requests

UA = "carte-immo/1.0 (outil de recherche personnel ; quelques requetes par jour)"
PRIX_MAX = 800_000
ECH = 40
s = requests.Session()
s.headers.update({"User-Agent": UA, "Accept-Language": "fr-FR,fr;q=0.9"})


def slug(t):
    t = unicodedata.normalize("NFKD", str(t)).encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z0-9]+", "-", t).strip("-")


def entier(x):
    x = re.sub(r"[^\d,.]", "", str(x or "")).replace(",", ".")
    try:
        return int(float(x)) if x else None
    except ValueError:
        return None


def page(u):
    time.sleep(1.2)
    r = s.get(u, timeout=30)
    return r.status_code, r.text


def cartes(t, motif, base):
    """Découpe la page entre deux liens d'annonce et lit prix / surface / code postal dans le texte de chaque carte."""
    pos = [(m.start(), m.group(1)) for m in re.finditer(motif, t)]
    vus, out = set(), []
    for i, (p, u) in enumerate(pos):
        if u in vus:
            continue
        vus.add(u)
        fin = next((q for q, v in pos[i + 1:] if v != u), p + 6000)
        txt = html.unescape(re.sub(r"<[^>]+>", " ", t[p:fin]))
        txt = re.sub(r"[\s \xa0]+", " ", txt)
        prix = re.search(r"(?<![\w.,])(\d{1,3}(?: \d{3})+) ?€", txt)
        surf = re.search(r"(\d+(?:[.,]\d+)?) ?m(?:²|2)", txt + " " + u)
        out.append({"url": base + u, "prix": entier(prix.group(1)) if prix else None,
                    "surf": entier(surf.group(1)) if surf else None, "txt": txt[:300]})
    return out


def orpi(n):
    t = page(f"https://www.orpi.com/annonces-immobilieres-ile-de-france/vente-maison/?page={n}")[1]
    out = []
    for m in re.findall(r'<script[^>]*application/ld\+json[^>]*>(.*?)</script>', t, re.S):
        try:
            o = json.loads(m)
        except ValueError:
            continue
        for it in o.get("itemListElement", []) if isinstance(o, dict) else []:
            u = it.get("url", "")
            g = re.search(r"maison-t\d+-(.+)-(\d{5})-", u)
            if g:
                out.append({"url": u, "prix": entier(((it.get("item") or {}).get("offers") or {}).get("price")),
                            "ville": g.group(1), "cp": g.group(2), "surf": None})
    # surface lue dans la carte HTML quand elle y est
    for a in out:
        k = t.find(a["url"].replace("https://www.orpi.com", ""))
        m = re.search(r"(\d+(?:[.,]\d+)?)\s*m(?:²|2)", html.unescape(re.sub(r"<[^>]+>", " ", t[k:k + 4000]))) if k > 0 else None
        a["surf"] = entier(m.group(1)) if m else None
    return out


def laforet(n):
    t = page(f"https://www.laforet.com/region/achat-maison-ile-de-france?page={n}")[1]
    out, vus = [], set()
    for m in re.finditer(r'data-gtm-item-id-param="(\d+)"[^>]*?data-gtm-item-city-param="([^"]*)"[^>]*?data-gtm-item-zipcode-param="(\d{5})"[^>]*?data-gtm-item-price-param="(\d+)"[^>]*?data-gtm-item-size-param="([\d.]*)"', t, re.S):
        if m.group(1) in vus:
            continue
        vus.add(m.group(1))
        out.append({"url": f"laforet #{m.group(1)}", "ville": m.group(2), "cp": m.group(3), "prix": int(m.group(4)), "surf": entier(m.group(5))})
    return out


def iad(n):
    t = page(f"https://www.iadfrance.fr/annonces/ile-de-france/vente/maison?page={n}")[1]
    out, vus = [], set()
    for m in re.finditer(r'href="(/annonce/maison-vente-[^"]+)"', t):
        u = m.group(1)
        if u in vus:
            continue
        vus.add(u)
        avant = re.sub(r"[\s\u202f\xa0]+", " ", html.unescape(re.sub(r"<[^>]+>", " ", t[max(0, m.start() - 1500):m.start()])))
        apres = re.sub(r"[\s\u202f\xa0]+", " ", html.unescape(re.sub(r"<[^>]+>", " ", t[m.start():m.start() + 1500])))
        prix = re.findall(r"(?<![\w.,])(\d{1,3}(?: \d{3})+) ?€", avant)
        g = re.search(r"Maison à (.+?) \((\d{5})\)", apres)
        sf = re.search(r"(\d+(?:[.,]\d+)?) m² ", apres)
        out.append({"url": "https://www.iadfrance.fr" + u, "prix": entier(prix[-1]) if prix else None,
                    "ville": g.group(1) if g else None, "cp": g.group(2) if g else None, "surf": entier(sf.group(1)) if sf else None})
    return out


def lesiteimmo(n):
    t = page(f"https://www.lesiteimmo.com/acheter/maison/ile-de-france?page={n}")[1]
    out = cartes(t, r'href="(/acheter/maison[^"/]*/[a-z0-9-]+-\d{5}/\d+)"', "https://www.lesiteimmo.com")
    for a in out:
        g = re.search(r"/([a-z0-9-]+)-(\d{5})/\d+$", a["url"])
        a["ville"], a["cp"] = g.group(1), g.group(2)
    return out


ZONES = {}


def zone(ville, cp):
    k = (ville, cp)
    if k not in ZONES:
        time.sleep(0.6)
        r = s.get("https://res.bienici.com/suggest.json", params={"q": ville.replace("-", " ")}, timeout=30).json()
        z = [x for x in r if x.get("type") == "city" or x.get("zoneIds")]
        bon = [x for x in z if cp and cp in (x.get("postalCodes") or [])] or \
              [x for x in z if slug(x.get("name", "")) == slug(ville)]
        ZONES[k] = bon[0]["zoneIds"] if bon else None
    return ZONES[k]


def sur_bienici(a):
    zid = zone(a["ville"], a.get("cp"))
    if not zid:
        return None
    p = a["prix"]
    f = {"size": 50, "from": 0, "filterType": "buy", "propertyType": ["house", "townhouse", "castle", "loft"],
         "minPrice": int(p * 0.97), "maxPrice": int(p * 1.03) + 1, "onTheMarket": [True], "zoneIdsByTypes": {"zoneIds": zid}}
    time.sleep(0.8)
    ads = s.get("https://www.bienici.com/realEstateAds.json", params={"filters": json.dumps(f)}, timeout=30).json().get("realEstateAds") or []
    for x in ads:
        sx = x.get("surfaceArea")
        if not a.get("surf") or not sx or abs(sx - a["surf"]) <= max(3, 0.05 * a["surf"]):
            return True
    return False


SITES = {"Orpi": orpi, "Laforêt": laforet, "iad": iad, "Lesiteimmo": lesiteimmo}
res, lignes = {}, []
for nom, f in SITES.items():
    ech = []
    for n in range(1, 6):
        try:
            got = f(n)
        except Exception as e:
            lignes.append(f"{nom} page {n} : erreur {type(e).__name__}")
            break
        lignes.append(f"{nom} page {n} : {len(got)} annonce(s) lue(s)")
        ech += [a for a in got if a.get("prix") and a["prix"] <= PRIX_MAX and a.get("ville")]
        if len(ech) >= ECH or not got:
            break
    ech = ech[:ECH]
    ok = non = inc = 0
    absentes = []
    for a in ech:
        try:
            r = sur_bienici(a)
        except Exception:
            r = None
        if r is None:
            inc += 1
        elif r:
            ok += 1
        else:
            non += 1
            absentes.append(f"   {a['prix']} € {a.get('surf')} m² {a['ville']} {a.get('cp') or ''} {a['url']}")
    l = f"{nom} : {len(ech)} maisons ≤ 800 k€ testées, {ok} déjà sur Bien'ici, {non} absentes, {inc} commune non trouvée"
    print(l, flush=True)
    lignes += [l] + absentes
with open("sonde/mesure.txt", "w") as fo:
    fo.write("\n".join(lignes) + "\n")
