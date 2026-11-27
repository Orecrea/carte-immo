"""Diagnostic (temporaire) : sources de données publiques pour la recherche multi-logements."""
import json, re, urllib.request, urllib.parse
UA = {"User-Agent": "carte-immo (usage prive)"}
def get(u, t=60):
    return urllib.request.urlopen(urllib.request.Request(u, headers=UA), timeout=t)
for q in ["base permanente des équipements", "BPE équipements commune"]:
    try:
        j = json.load(get("https://www.data.gouv.fr/api/1/datasets/?page_size=12&q=" + urllib.parse.quote(q)))
        for d in j["data"]:
            print("DATASET", d["slug"], "|", (d.get("organization") or {}).get("name"))
            for r in d.get("resources", [])[:25]:
                print("   RES", r.get("format"), r.get("filesize"), "|", r.get("title"), "|", r.get("url"))
    except Exception as e:
        print("ERR", q, e)
for u in ["https://service.annuaire.sante.fr/annuaire-sante-webservices/V300/services/extraction/PS_LibreAcces",
          "https://www.insee.fr/fr/statistiques/8217525", "https://res.bienici.com/suggest.json?q=Pontoise"]:
    try:
        r = get(u); print("URL", u, r.status, r.headers.get("Content-Type"), r.headers.get("Content-Length"))
        if "insee" in u:
            print(re.findall(r'href="([^"]*fichier[^"]*)"', r.read().decode("utf-8", "ignore"))[:30])
        if "bienici" in u:
            print(r.read()[:300])
    except Exception as e:
        print("ERR", u, e)
