#!/usr/bin/env python3
"""Fabrique site/beta.html (MapLibre, thème sombre, panneau « Mes villes ») à partir de site/index.html."""
import re, sys, pathlib
HERE = pathlib.Path(__file__).parent
SRC, DST = pathlib.Path(sys.argv[1]), pathlib.Path(sys.argv[2])
s = SRC.read_text()

def rep(old, new, count=1):
    global s
    n = s.count(old)
    if n != count:
        sys.exit(f'ERREUR : {n} occurrence(s) au lieu de {count} pour :\n{old[:200]}')
    s = s.replace(old, new)

def rep_between(start, end, new, keep_end=True):
    global s
    i = s.index(start); j = s.index(end, i)
    s = s[:i] + new + (s[j:] if keep_end else s[j + len(end):])

# ---------- En-tête : MapLibre au lieu de Leaflet ----------
rep_between('<link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/leaflet/1.9.4/leaflet.min.css">', '<style>', '''<link rel="preconnect" href="https://tiles.openfreemap.org" crossorigin>
<link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/maplibre-gl/4.7.1/maplibre-gl.min.css">
<script src="https://cdnjs.cloudflare.com/ajax/libs/maplibre-gl/4.7.1/maplibre-gl.min.js"></script>
<script async src="https://cdnjs.cloudflare.com/ajax/libs/Turf.js/6.5.0/turf.min.js"></script>
<script>/* secours si cdnjs est inaccessible */
window.maplibregl || document.write('<link rel="stylesheet" href="https://unpkg.com/maplibre-gl@4.7.1/dist/maplibre-gl.css"><script src="https://unpkg.com/maplibre-gl@4.7.1/dist/maplibre-gl.js"><\\/script>');
</script>
<script>/* thème choisi appliqué avant l'affichage (pas d'éclair blanc) */
try { const t = JSON.parse(localStorage.getItem('carteimmo2.theme')); document.documentElement.dataset.theme = t || (matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light'); } catch(_) {}
</script>
''')
rep('<link rel="preconnect" href="https://server.arcgisonline.com" crossorigin>\n', '')

# ---------- Styles ----------
i0, i1 = s.index('<style>'), s.index('</style>')
css = s[i0:i1]
css = re.sub(r'background:#fff(?![0-9a-fA-F])', 'background:var(--panel)', css)
css = css.replace('background:var(--text)', 'background:var(--solid)')
css = css.replace('border-color:var(--text)', 'border-color:var(--solid)')
css = css.replace('border:1px solid var(--text)', 'border:1px solid var(--solid)')
css = css.replace('--header:60px;', '--header:60px; --solid:#18202f;')
css = re.sub(r'\.leaflet-div-icon\{[^}]*\}\n', '', css)
css = css.replace('.leaflet-popup-content-wrapper{border-radius:12px;box-shadow:var(--shadow)}', '')
css = css.replace('.leaflet-popup-content{margin:12px 14px;font:13px/1.45 Inter,system-ui,sans-serif}', '')
css = css.replace('.leaflet-container{font-family:Inter,system-ui,sans-serif;background:#eef0f3}', '#map{background:var(--mapbg)}')
css = css.replace('.leaflet-control-zoom{display:none}', '.maplibregl-ctrl-bottom-right .maplibregl-ctrl-group{display:none}')
css = css.replace('body.sheet-half .map-wrap .leaflet-bottom,body.sheet-full .map-wrap .leaflet-bottom{display:none}',
                  'body.sheet-half .map-wrap .maplibregl-ctrl-bottom-left,body.sheet-half .map-wrap .maplibregl-ctrl-bottom-right,body.sheet-full .map-wrap .maplibregl-ctrl-bottom-left,body.sheet-full .map-wrap .maplibregl-ctrl-bottom-right{display:none}')
css = css.replace('.map-wrap .leaflet-bottom{bottom:88px}', '.map-wrap .maplibregl-ctrl-bottom-left,.map-wrap .maplibregl-ctrl-bottom-right{bottom:88px}')
css = css.replace('body.sheet-full .map-wrap .leaflet-top{display:none}', 'body.sheet-full .map-wrap .map-ctl{display:none}')
assert 'leaflet' not in css, re.findall(r'.{40}leaflet.{40}', css)
css += (HERE / 'beta.css').read_text()
s = s[:i0] + css + s[i1:]

# ---------- En-tête : bouton thème, bouton « Mes villes » ----------
rep('''    <div class="suggest" id="suggest" role="listbox"></div>
  </div>
''', '''    <div class="suggest" id="suggest" role="listbox"></div>
  </div>
  <div class="cities-wrap" id="citiesWrap" hidden>
    <button class="cities-btn" id="citiesBtn" aria-expanded="false" aria-controls="citiesPanel"><span class="cdots" id="citiesDots"></span><span id="citiesTxt"></span><svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" aria-hidden="true"><path d="m6 9 6 6 6-6"/></svg></button>
    <div class="cities-panel" id="citiesPanel" role="dialog" aria-label="Mes villes">
      <div class="cp-head"><b>Mes villes</b><span id="citiesSum"></span></div>
      <div class="city-chips" id="cityChips"></div>
      <div class="cp-foot"><button class="link" id="citiesFit">Voir toutes mes villes sur la carte</button></div>
    </div>
  </div>
''')
rep('      <div class="city-chips" id="cityChips"></div>\n      <label for="q" class="sr">', '      <label for="q" class="sr">')
rep('''  <div class="hdr-actions">
''', '''  <div class="hdr-actions">
    <button class="hbtn theme-btn" id="themeBtn" aria-pressed="false" title="Passer en thème sombre" aria-label="Thème sombre"><svg class="moon" width="17" height="17" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" aria-hidden="true"><path d="M20 14.5A8 8 0 0 1 9.5 4a8 8 0 1 0 10.5 10.5z"/></svg><svg class="sun" width="17" height="17" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" aria-hidden="true"><circle cx="12" cy="12" r="4"/><path d="M12 2v2M12 20v2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M2 12h2M20 12h2M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4"/></svg></button>
''')

rep('''  <div class="logo"><div class="logo-mark">⌂</div><div class="logo-text">Carte<span>immo</span></div></div>
''', '''  <div class="logo"><div class="logo-mark">⌂</div><div class="logo-text">Carte<span>immo</span></div></div>
  <div class="env" id="envSwitch" role="tablist" aria-label="Choix de la carte (touche T)">
    <span class="env-glide" aria-hidden="true"></span>
    <button role="tab" data-env="immo" aria-selected="true" title="Annonces (touche T pour basculer)"><span class="ei">🏠</span><span class="el">Annonces</span></button>
    <button role="tab" data-env="tc" aria-selected="false" tabindex="-1" title="Transports (touche T pour basculer)"><span class="ei">🚆</span><span class="el">Transports</span></button>
  </div>
''')
rep('''  <div class="map-wrap">''', '''  <div class="tc-wrap" id="tcWrap"></div>
  <div class="map-wrap">''')

# ---------- Script : carte ----------
rep('''<script>
if(!window.L){
  document.getElementById('map').innerHTML = '<div class="map-error"><div><b>La carte n\\'a pas pu se charger</b>Ouvrez ce fichier dans Chrome, Firefox, Safari ou Edge, avec une connexion internet.<br>Un aperçu de fichier (messagerie, explorateur, application) bloque souvent les cartes.</div></div>';
  throw new Error('Leaflet indisponible');
}
''', '<script>\n')
rep("const FRANCE = L.latLngBounds([41.2, -5.6], [51.3, 9.8]);\n", '')
rep_between('/* =========================================================\n   Carte\n', '/* =========================================================\n   Arrêts de transport',
            (HERE / 'carte-maplibre.js').read_text() + '\n')
# transports IDFM : après la définition de cached() (mémoire durable des points d'intérêt)
rep('const POI_TTL = 14 * 864e5;\n', 'const POI_TTL = 14 * 864e5;\n' + (HERE / 'tc.js').read_text())

# Points d'intérêt : des objets GeoJSON au lieu de marqueurs HTML
rep('''  if(e.bounds) return [(e.bounds.minlat + e.bounds.maxlat)/2, (e.bounds.minlon + e.bounds.maxlon)/2];
  return null;''', '''  if(e.bounds) return [(e.bounds.minlat + e.bounds.maxlat)/2, (e.bounds.minlon + e.bounds.maxlon)/2];
  if(e.geometry && e.geometry.length) return [e.geometry.reduce((a, p) => a + p.lat, 0) / e.geometry.length, e.geometry.reduce((a, p) => a + p.lon, 0) / e.geometry.length];
  return null;''')
# Seuils d'affichage des couches : exprimés en zoom Leaflet (= zoom MapLibre + 1)
rep('''async function loadPoi(){
  const z = map.getZoom();''', '''async function loadPoi(){
  const z = zL();''')
rep_between('function drawPoi(k, e, t, c){', '\nlet poiTimer = null', (HERE / 'poi.js').read_text())
rep('''  const draw = (k, j) => {
    if(ctrl !== poiCtrl) return;
    LAYERS[k].group.clearLayers(); counts[k] = 0; const seen = new Set();''', '''  const draw = (k, j) => {
    if(ctrl !== poiCtrl) return;
    POIF[k] = []; counts[k] = 0; const seen = new Set();''')
rep('''      if(seen.has(dk)) return; seen.add(dk); counts[k]++; drawPoi(k, e, t, c);
    });
  };''', '''      if(seen.has(dk)) return; seen.add(dk); counts[k]++; drawPoi(k, e, t, c);
    });
    flushPoi();
  };''')
rep("const d = map.distance([l.lat, l.lng], [r.position.lat, r.position.lon]);", "const d = distM([l.lat, l.lng], [r.position.lat, r.position.lon]);")
rep("d = map.distance([l.lat, l.lng], c);", "d = distM([l.lat, l.lng], c);")
rep("const d = map.distance([o.lat, o.lng], [l.lat, l.lng]);", "const d = distM([o.lat, o.lng], [l.lat, l.lng]);")

# Regroupement des annonces : fait par la carte elle-même
rep_between('/* Groupe de marqueurs (regroupés à faible zoom) */', '/* =========================================================\n   Trajets', '')

# Zones de trajet
rep_between('function zoneBounds(z){', 'function renderZoneStatus(z){', (HERE / 'zones.js').read_text())
rep("else if(btn.hasAttribute('data-focus')) map.flyToBounds(zoneBounds(z).pad(.1), {duration:.6});",
    "else if(btn.hasAttribute('data-focus')) fitTo(zoneBounds(z).pad(.1), {duration:600});")
rep("const ctr = cc ? [cc.lat, cc.lng] : g ? L.geoJSON(g).getBounds().getCenter() : null;", "const ctr = cc ? [cc.lat, cc.lng] : g ? BB.geom(g).center() : null;")
rep("    if(made.length) map.flyToBounds(made.reduce((b, z) => b.extend(zoneBounds(z)), L.latLngBounds([])).pad(.2), {duration:.7});",
    "    if(made.length) fitTo(made.reduce((b, z) => b.add(zoneBounds(z)), new BB()).pad(.2));")
rep("  map.flyToBounds(zoneBounds(z).pad(.1), {duration:.7});", "  fitTo(zoneBounds(z).pad(.1));")
rep("map.on('click', e => { if(!addMode) return; addZone(e.latlng.lat, e.latlng.lng);",
    "map.on('click', e => { if(!addMode) return; addZone(e.lngLat.lat, e.lngLat.lng);")

# Annonces sur la carte
rep_between('function pinIcon(l, out){', '  // compteurs\n', (HERE / 'pins.js').read_text())
rep("if(!inside.some(l => map.getBounds().contains([l.lat, l.lng]))){ map.fitBounds(L.latLngBounds(inside.map(l => [l.lat, l.lng])).pad(.05), {maxZoom:14, animate:false}); }",
    "if(!inside.some(l => inView(l))){ fitTo(BB.of(inside.map(l => [l.lat, l.lng])).pad(.05), {maxZoom:14, duration:0}); }")
rep("const vis = inside.filter(l => vb.contains([l.lat, l.lng]));", "const vis = inside.filter(l => inView(l, vb));")
rep("map.flyToBounds(L.latLngBounds(lastInside.map(l => [l.lat, l.lng])).pad(.1), {duration:.7});", "fitTo(BB.of(lastInside.map(l => [l.lat, l.lng])).pad(.1));")
rep("function hlPin(id, on){ const el = document.querySelector(`.price-pin[data-pin=\"${id}\"]`); if(el) el.classList.toggle('hl', on); }",
    "function hlPin(id, on){ if(mapReady) map.setFilter('ci-pins-hl', ['==', ['get', 'n'], on && PIN_N.has(String(id)) ? PIN_N.get(String(id)) : -1]); }")
rep("  const m = markers[id]; if(m) m.setIcon(pinIcon(m._l, m._out));\n", "  updatePins();\n")
rep("  const pin = document.querySelector(`.price-pin[data-pin=\"${l.id}\"]`); if(pin) pin.classList.add('seen');", "  updatePins();")
rep("if(pts.length) map.flyToBounds(L.latLngBounds(pts).pad(.3), {maxZoom:15, duration:.6});", "if(pts.length) fitTo(BB.of(pts).pad(.3), {maxZoom:15, duration:600});")
rep("map.flyTo([l.lat, l.lng], 16, {duration:.6});", "map.flyTo({center:[l.lng, l.lat], zoom:15, duration:600});")

# Villes : contours colorés, panneau « Mes villes »
rep("const citiesLayer = L.layerGroup().addTo(map);\n", '')
rep_between('function drawCommunes(){', '\nconst q = $(\'#q\')', (HERE / 'villes.js').read_text())
rep("  if(e.key === 'Backspace' && !q.value && cities.length){ cities.pop(); renderCityChips(); updateCommunes(); return; }\n", '')
rep("  if(!cities.some(c => c.code === p.citycode)) cities.push({code:p.citycode, name:p.city || p.name, cp:p.postcode, lat, lng, nb:false});",
    "  if(!cities.some(c => c.code === p.citycode)) cities.push({code:p.citycode, name:p.city || p.name, cp:p.postcode, lat, lng, nb:false, col:nextCityColor()});")

# Bascule de thème
rep("renderCityChips(); if(cities.length) updateCommunes();", (HERE / 'fin.js').read_text())

assert not re.search(r'\bL\.[a-zA-Z]', s.split('<script>', 1)[1]), re.findall(r'.{60}\bL\.[a-zA-Z].{30}', s)
s = s.replace('<title>Carte immo</title>', '<title>Carte immo (test)</title>')
DST.write_text(s)
print('ok', len(s))
