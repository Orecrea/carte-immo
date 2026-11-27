"""Diagnostic (temporaire) : BPE 2025 de l'INSEE pour la recherche multi-logements."""
import csv, io, re, urllib.request, zipfile, time
UA = {"User-Agent": "carte-immo (usage prive)"}
get = lambda u, t=300: urllib.request.urlopen(urllib.request.Request(u, headers=UA), timeout=t).read()
B = "https://www.insee.fr"
t = get(B + "/fr/metadonnees/source/fichier/TYPEQU_2025.csv").decode("utf-8-sig", "ignore")
print(t[:300])
for l in t.splitlines():
    if re.search(r"(?i)cole|coll[eè]ge|lyc[ée]e|g[ée]n[ée]ral|omnipra|psych|orthoph|loisir|mineurs|centre social|maison de sant|centre de sant|urgence", l):
        print("TYPEQU", l)
t0 = time.time(); z = get(B + "/fr/statistiques/fichier/8217525/BPE25.zip"); print("zip", len(z) // 1e6, "Mo", round(time.time() - t0), "s")
zf = zipfile.ZipFile(io.BytesIO(z))
for i in zf.infolist(): print("MEMBRE", i.filename, i.file_size)
nom = max(zf.infolist(), key=lambda i: i.file_size).filename
with zf.open(nom) as f:
    for k, l in enumerate(io.TextIOWrapper(f, encoding="utf-8", errors="ignore")):
        if k < 3: print("LIGNE", l[:400])
        else: break
