"""Sonde ponctuelle (test, non branchée à la carte) : quels sites de réseaux d'agences sont lisibles depuis GitHub ?
Requêtes simples et identifiées, une par page, aucune protection contournée."""
import os, re, time, requests

UA = "carte-immo/1.0 (outil de recherche personnel ; quelques requetes par jour)"
URLS = {
    "orpi": ["https://www.orpi.com/annonces-immobilieres-ile-de-france/vente-maison/", "https://www.orpi.com/robots.txt"],
    "laforet": ["https://www.laforet.com/region/achat-maison-ile-de-france", "https://www.laforet.com/robots.txt"],
    "century21": ["https://www.century21.fr/", "https://www.century21.fr/annonces/f/achat-maison/r-ile_de_france/", "https://www.century21.fr/robots.txt"],
    "guyhoquet": ["https://www.guy-hoquet.com/", "https://www.guy-hoquet.com/robots.txt"],
    "stephaneplaza": ["https://www.stephaneplazaimmobilier.com/", "https://www.stephaneplazaimmobilier.com/immobilier-acheter", "https://www.stephaneplazaimmobilier.com/robots.txt"],
    "squarehabitat": ["https://www.squarehabitat.fr/", "https://www.squarehabitat.fr/robots.txt"],
    "iad": ["https://www.iadfrance.fr/", "https://www.iadfrance.fr/annonces/maison/vente/ile-de-france", "https://www.iadfrance.fr/robots.txt"],
    "nestenn": ["https://nestenn.com/ile-de-france", "https://nestenn.com/robots.txt"],
    "era": ["https://www.erafrance.com/", "https://www.erafrance.com/robots.txt"],
    "capifrance": ["https://www.capifrance.fr/", "https://www.capifrance.fr/robots.txt"],
    "foncia": ["https://fr.foncia.com/achat/ile-de-france/maison", "https://fr.foncia.com/robots.txt"],
    "lesiteimmo": ["https://www.lesiteimmo.com/acheter/maison/ile-de-france", "https://www.lesiteimmo.com/robots.txt"],
    "nestoria": ["https://www.nestoria.fr/ile-de-france/maison/vente", "https://www.nestoria.fr/robots.txt"],
    "ladresse": ["https://www.ladresse.com/", "https://www.ladresse.com/robots.txt"],
    "arthurimmo": ["https://www.arthurimmo.com/", "https://www.arthurimmo.com/robots.txt"],
    "citya": ["https://www.citya.com/", "https://www.citya.com/robots.txt"],
}

os.makedirs("sonde/pages", exist_ok=True)
s = requests.Session()
s.headers.update({"User-Agent": UA, "Accept-Language": "fr-FR,fr;q=0.9"})
lignes = []
for nom, urls in URLS.items():
    for i, u in enumerate(urls):
        try:
            r = s.get(u, timeout=30)
            t = r.text
            bot = bool(re.search(r"datadome|captcha-delivery|cf-chl|just a moment|px-captcha|incapsula", t[:20000], re.I))
            ld = len(re.findall(r"application/ld\+json", t))
            nxt = "__NEXT_DATA__" in t or "__NUXT__" in t
            prix = len(re.findall(r"\d{3}[\s \xa0.]\d{3}\s?(?:€|&euro;)", t))
            l = f"{nom}\t{r.status_code}\t{len(t)}\tbot={bot}\tld={ld}\tnext={nxt}\tprix={prix}\t{r.url}"
            with open(f"sonde/pages/{nom}-{i}.{'txt' if u.endswith('.txt') else 'html'}", "w") as f:
                f.write(t)
        except Exception as e:
            l = f"{nom}\tERR\t{type(e).__name__}\t{u}"
        print(l)
        lignes.append(l)
        time.sleep(1)
with open("sonde/reco.tsv", "w") as f:
    f.write("\n".join(lignes) + "\n")
