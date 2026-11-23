/* =========================================================
   Carte (MapLibre : rendu par la carte graphique, fond vectoriel)
   ========================================================= */
const store = {
  get(k, d){ try { const v = localStorage.getItem('carteimmo2.' + k); return v ? JSON.parse(v) : d; } catch(_) { return d; } },
  set(k, v){ try { localStorage.setItem('carteimmo2.' + k, JSON.stringify(v)); } catch(_) {} }
};
const EMPTY = {type:'FeatureCollection', features:[]};
const FC = features => ({type:'FeatureCollection', features});

/* Distance en mètres entre deux points [lat, lng] */
function distM(a, b){
  const r = Math.PI / 180, dLa = (b[0] - a[0]) * r, dLo = (b[1] - a[1]) * r;
  const s = Math.sin(dLa / 2) ** 2 + Math.cos(a[0] * r) * Math.cos(b[0] * r) * Math.sin(dLo / 2) ** 2;
  return 2 * 6371000 * Math.asin(Math.min(1, Math.sqrt(s)));
}
/* Emprise (rectangle) : remplace les « bounds » de Leaflet */
class BB {
  constructor(){ this.w = Infinity; this.s = Infinity; this.e = -Infinity; this.n = -Infinity; }
  static of(pts){ const b = new BB(); pts.forEach(p => b.ext(p[0], p[1])); return b; }          // points [lat, lng]
  static geom(g){ const b = new BB(); b.geom(g); return b; }
  ext(lat, lng){ if(lat < this.s) this.s = lat; if(lat > this.n) this.n = lat; if(lng < this.w) this.w = lng; if(lng > this.e) this.e = lng; return this; }
  geom(g){ if(!g) return this; const walk = c => typeof c[0] === 'number' ? this.ext(c[1], c[0]) : c.forEach(walk); walk(g.coordinates); return this; }
  add(b){ if(b.ok()){ this.ext(b.s, b.w); this.ext(b.n, b.e); } return this; }
  ok(){ return this.w <= this.e && this.s <= this.n; }
  pad(r){ const b = new BB(), dy = (this.n - this.s) * r, dx = (this.e - this.w) * r; b.s = this.s - dy; b.n = this.n + dy; b.w = this.w - dx; b.e = this.e + dx; return b; }
  center(){ return [(this.s + this.n) / 2, (this.w + this.e) / 2]; }
  arr(){ return [[this.w, this.s], [this.e, this.n]]; }
}
/* Les zooms sont exprimés comme avant (échelle Leaflet) : zoom MapLibre + 1 */
const zL = () => map.getZoom() + 1;
function fitTo(b, o = {}){
  if(!b || !b.ok()) return;
  const pad = matchMedia('(max-width:860px)').matches ? 24 : 40;
  if(b.n - b.s < 1e-6 && b.e - b.w < 1e-6){ map.flyTo({center:[b.w, b.s], zoom:Math.min((o.maxZoom || 16) - 1, 15), duration:o.duration ?? 700}); return; }
  map.fitBounds(b.arr(), {padding:pad, maxZoom:(o.maxZoom || 19) - 1, duration:o.duration ?? 700});
}
const inView = (l, vb = map.getBounds()) => vb.contains([l.lng, l.lat]);

if(!window.maplibregl){
  document.getElementById('map').innerHTML = '<div class="map-error"><div><b>La carte n\'a pas pu se charger</b>Ouvrez ce fichier dans Chrome, Firefox, Safari ou Edge, avec une connexion internet.<br>Un aperçu de fichier (messagerie, explorateur, application) bloque souvent les cartes.</div></div>';
  throw new Error('MapLibre indisponible');
}

/* ---------- Thème clair / sombre ---------- */
let THEME = store.get('theme', null) || (matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light');
document.documentElement.dataset.theme = THEME;

/* ---------- Fonds ---------- */
const OSM = '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>';
const STYLE_URL = 'https://tiles.openfreemap.org/styles/positron';
const STYLE_SECOURS = {             // si OpenFreeMap ne répond pas : fond en images (Esri)
  version:8, glyphs:'https://tiles.openfreemap.org/fonts/{fontstack}/{range}.pbf',
  sources:{esri:{type:'raster', tileSize:256, maxzoom:16, attribution:'Fond &copy; Esri, HERE, Garmin, ' + OSM,
    tiles:['https://server.arcgisonline.com/ArcGIS/rest/services/Canvas/World_Light_Gray_Base/MapServer/tile/{z}/{y}/{x}']},
    esril:{type:'raster', tileSize:256, maxzoom:16, tiles:['https://server.arcgisonline.com/ArcGIS/rest/services/Canvas/World_Light_Gray_Reference/MapServer/tile/{z}/{y}/{x}']}},
  layers:[{id:'bg', type:'background', paint:{'background-color':'#eef0f3'}}, {id:'esri', type:'raster', source:'esri'}, {id:'esril', type:'raster', source:'esril'}]
};
const BASES = {plan:{label:'Plan'}, sat:{label:'Satellite'}};
let baseKey = store.get('base', 'plan'); if(!BASES[baseKey]) baseKey = 'plan';

const savedView = store.get('vue', null);
const map = new maplibregl.Map({
  container:'map', style:STYLE_URL,
  center: savedView && savedView.c ? [savedView.c[1], savedView.c[0]] : [2.3522, 48.8566],
  zoom: savedView && savedView.c ? savedView.z - 1 : 10,
  minZoom:4, maxZoom:19, maxBounds:[[-7.2, 40.2], [11.4, 52.2]],
  dragRotate:false, pitchWithRotate:false, touchPitch:false, fadeDuration:120,
  attributionControl:{compact:true}
});
map.touchZoomRotate.disableRotation();
map.keyboard.disableRotation && map.keyboard.disableRotation();
map.on('moveend', () => { const c = map.getCenter(); store.set('vue', {c:[+c.lat.toFixed(5), +c.lng.toFixed(5)], z:+zL().toFixed(2)}); });
map.addControl(new maplibregl.NavigationControl({showCompass:false}), 'bottom-right');
map.addControl(new maplibregl.ScaleControl({unit:'metric'}), 'bottom-left');
let secours = false, styleOnce = false;
map.on('error', e => {
  if(secours || styleOnce || !e || !e.error || e.sourceId || e.tile) return;
  secours = true; map.setStyle(STYLE_SECOURS);
  setStatus('Fond vectoriel indisponible : fond de secours utilisé');
});

/* Sources et couches : on garde la dernière donnée voulue, appliquée dès que la carte est prête */
let mapReady = false;
const PENDING = {}, VIS = {};
function setSrc(id, data){ PENDING[id] = data; if(mapReady && map.getSource(id)) map.getSource(id).setData(data); }
function vis(ids, on){ [].concat(ids).forEach(id => { VIS[id] = on; if(mapReady && map.getLayer(id)) map.setLayoutProperty(id, 'visibility', on ? 'visible' : 'none'); }); }

/* ---------- Couches d'intérêt ---------- */
const LAYERS = {
  transports:{label:'Transports',        icon:'🚌', color:'#f4a100', minZoom:0, on:false, tile:true,
              desc:'Toutes les lignes de train, métro, tram et bus avec leurs arrêts'},
  futur:     {label:'Stations et lignes futures', icon:'🚧', color:'#8e44ad', minZoom:11, on:false, sub:true,
              desc:'En travaux ou en projet (ex. Grand Paris Express)'},
  velo:      {label:'Pistes cyclables', icon:'🚲', color:'#1c7ed6', minZoom:0, on:false, tile:true,
              desc:'Pistes et bandes cyclables, en bleu'},
  ecoles:    {label:'Écoles',            icon:'🏫', color:'#d1495b', minZoom:13, on:false,
              desc:'Maternelles, écoles, collèges et lycées (annuaire officiel de l\'Éducation nationale)'},
  commerces: {label:'Commerces',         icon:'🛒', color:'#2b7a78', minZoom:15, on:false,
              desc:'Supermarchés, supérettes, boulangeries, pharmacies'},
  verts:     {label:'Espaces verts',     icon:'🌳', color:'#3a9d4a', minZoom:14, on:false,
              desc:'Parcs et jardins publics'},
  activites: {label:'Activités enfants', icon:'⚽', color:'#5b6ee1', minZoom:14, on:false,
              desc:'Centres sportifs, piscines, aires de jeux, MJC, médiathèques, écoles de musique et de danse'}
};
/* Chaque couche garde ses objets (points, lignes, surfaces) ; tout est dessiné par trois couches de la carte */
const POIF = {};
Object.keys(LAYERS).forEach(k => { POIF[k] = []; LAYERS[k].group = {clearLayers(){ POIF[k] = []; flushPoi(); }}; });
let poiFlushT = 0;
function flushPoi(){
  cancelAnimationFrame(poiFlushT);
  poiFlushT = requestAnimationFrame(() => {
    const all = Object.values(POIF).flat();
    setSrc('poi', FC(all.filter(f => f.geometry.type === 'Point')));
    setSrc('poi-lines', FC(all.filter(f => f.geometry.type === 'LineString')));
    setSrc('poi-areas', FC(all.filter(f => f.geometry.type === 'Polygon')));
  });
}
store.get('couches', []).forEach(k => { if(LAYERS[k]) LAYERS[k].on = true; });
const saveLayers = () => store.set('couches', Object.keys(LAYERS).filter(k => LAYERS[k].on));
const LAYERS_ICON = '<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linejoin="round" aria-hidden="true"><path d="M12 3 2 8l10 5 10-5-10-5z"/><path d="m2 13 10 5 10-5"/><path d="m2 17.5 10 5 10-5" opacity=".55"/></svg>';

function setBase(k){
  baseKey = k; store.set('base', k);
  vis('sat', k === 'sat');
  document.querySelectorAll('[name=base]').forEach(r => r.checked = r.value === k);
}
function syncPt(){
  vis(['tc-bus', 'tc-rail-casing', 'tc-rail', 'tc-arrets', 'tc-gares', 'tc-gares-label'], LAYERS.transports.on);
  if(LAYERS.transports.on && typeof loadTcViewport === 'function') loadTcViewport();
  vis('velo', LAYERS.velo.on);
}

/* ---------- Risque inondation ---------- */
const GEORISQUES_WMS = 'https://www.georisques.gouv.fr/services';
const FLOOD_SCEN = [
  {layer:'ALEA_SYNT_01_01FOR_FXX,ALEA_SYNT_03_01FOR_FXX', label:'Crue fréquente', sub:'environ tous les 10 à 30 ans', color:'#08519c'},
  {layer:'ALEA_SYNT_01_02MOY_FXX,ALEA_SYNT_03_02MOY_FXX', label:'Crue moyenne',   sub:'environ tous les 100 ans', color:'#3182bd'},
  {layer:'ALEA_SYNT_01_04FAI_FXX,ALEA_SYNT_03_04FAI_FXX', label:'Crue extrême',   sub:'environ tous les 1 000 ans', color:'#9ecae1'}
];
const wmsUrl = layers => GEORISQUES_WMS + '?SERVICE=WMS&VERSION=1.1.1&REQUEST=GetMap&LAYERS=' + encodeURIComponent(layers)
  + '&STYLES=&FORMAT=image/png&TRANSPARENT=true&SRS=EPSG:3857&WIDTH=256&HEIGHT=256&BBOX={bbox-epsg-3857}';

// Montée des eaux : terrain sous le niveau choisi, calculé dans la page à partir des tuiles d'altitude (Terrarium, AWS Open Data)
maplibregl.addProtocol('niveau', async (params, ctrl) => {
  const m = params.url.match(/niveau:\/\/(\d+)\/(\d+)\/(\d+)\/([\d.]+)/), lv = +m[4];
  const r = await fetch(`https://s3.amazonaws.com/elevation-tiles-prod/terrarium/${m[1]}/${m[2]}/${m[3]}.png`, {signal:ctrl.signal});
  if(!r.ok) throw new Error('altitude');
  const img = await createImageBitmap(await r.blob()), cv = document.createElement('canvas');
  cv.width = cv.height = 256; const ctx = cv.getContext('2d'); ctx.drawImage(img, 0, 0, 256, 256);
  const dem = ctx.getImageData(0, 0, 256, 256), d = dem.data, out = ctx.createImageData(256, 256), o = out.data;
  for(let i = 0; i < d.length; i += 4){
    const h = d[i] * 256 + d[i + 1] + d[i + 2] / 256 - 32768;
    if(h > 0.1 && h <= lv){ const k = 1 - h / Math.max(lv, .5); o[i] = 30; o[i + 1] = 110 - 50 * k; o[i + 2] = 220; o[i + 3] = 140 + 90 * k; }
  }
  ctx.putImageData(out, 0, 0);
  const blob = await new Promise(res => cv.toBlob(res, 'image/png'));
  return {data: await blob.arrayBuffer()};
});
const seaTiles = lv => [`niveau://{z}/{x}/{y}/${lv}`];

const FLOOD = Object.assign({on:false, mode:'tri', scen:2, sea:2}, store.get('inondation', {}));
const saveFlood = () => store.set('inondation', FLOOD);
let seaT = null;
function applyFlood(){
  FLOOD_SCEN.forEach((f, i) => vis('flood' + i, FLOOD.on && FLOOD.mode === 'tri' && i < FLOOD.scen));
  vis('sea', FLOOD.on && FLOOD.mode === 'sea');
  if(FLOOD.on && FLOOD.mode === 'sea') setSeaLevel(FLOOD.sea);
}
let seaShown = null;
function setSeaLevel(v){
  clearTimeout(seaT);
  seaT = setTimeout(() => { if(!mapReady || seaShown === v) return; seaShown = v; map.getSource('sea').setTiles(seaTiles(v)); }, 120);
}

/* ---------- Menu « Couches » et messages (au-dessus de la carte) ---------- */
const ctlBox = document.createElement('div'); ctlBox.className = 'map-ctl';
ctlBox.innerHTML = `<div class="layers" id="layersBox"><button class="layers-btn" id="layersBtn" title="Couches d'intérêt" aria-label="Couches d'intérêt" aria-expanded="false">${LAYERS_ICON}<span class="ltitle">Couches d'intérêt</span></button>
    <div class="layers-panel">
      <div class="bases"><span class="flabel">Fond de carte</span><div class="seg2">${Object.entries(BASES).map(([k, b]) =>
        `<label><input type="radio" name="base" value="${k}"><span>${b.label}</span></label>`).join('')}</div></div>
      ${Object.entries(LAYERS).map(([k,c]) => `
        <label class="lrow${c.sub ? ' sub' : ''}" data-k="${k}"><input type="checkbox" data-layer="${k}" ${c.on?'checked':''}>
          <span><b>${c.icon} ${c.label}</b><small>${c.desc}</small>
          <small class="zh">Zoomez davantage pour les afficher</small></span></label>`).join('')}
      <div class="flood" id="floodBox">
        <label class="lrow"><input type="checkbox" id="floodOn"><span><b>🌊 Risque d'inondation</b><small>Zones inondables et simulation de montée des eaux</small></span></label>
        <div class="flood-opts">
          <label><input type="radio" name="fmode" value="tri" checked> Zones inondables officielles</label>
          <div id="triBox">
            <input type="range" min="1" max="3" step="1" value="2" id="scen">
            <div class="fl-legend" id="triLegend"></div>
            <small style="color:var(--muted)">Source Géorisques. Couvre les territoires à risque cartographiés, pas toute la France.</small>
          </div>
          <label style="margin-top:8px"><input type="radio" name="fmode" value="sea"> Montée du niveau de la mer</label>
          <div id="seaBox" style="display:none">
            <input type="range" min="0" max="10" step="0.5" value="2" id="sea">
            <div>Niveau : <span class="flood-val" id="seaVal">+2 m</span></div>
            <small style="color:var(--muted)">Terrain situé sous ce niveau. Ne tient pas compte des digues.</small>
          </div>
        </div>
      </div>
    </div></div><div class="map-status" id="mapStatus" style="display:none"></div>`;
document.querySelector('.map-wrap').appendChild(ctlBox);
function setStatus(t){ const el = document.getElementById('mapStatus'); el.textContent = t || ''; el.style.display = t ? '' : 'none'; }

function renderTriLegend(){
  document.getElementById('triLegend').innerHTML = FLOOD_SCEN.map((f,i) =>
    `<div style="opacity:${i < FLOOD.scen ? 1 : .35}"><i style="background:${f.color}"></i>${f.label} <span style="color:var(--muted)">· ${f.sub}</span></div>`).join('');
}
function updateLayerMenu(){
  const z = zL();
  document.querySelectorAll('.lrow[data-k]').forEach(r => r.classList.toggle('dim', LAYERS[r.dataset.k].on && z < LAYERS[r.dataset.k].minZoom));
}
function setLayersOpen(on){ const b = document.getElementById('layersBox'); b.classList.toggle('open', on); document.getElementById('layersBtn').setAttribute('aria-expanded', on); }
document.getElementById('layersBtn').onclick = () => setLayersOpen(!document.getElementById('layersBox').classList.contains('open'));
map.on('click', () => setLayersOpen(false));
map.on('dragstart', () => setLayersOpen(false));
document.querySelectorAll('[data-layer]').forEach(cb => cb.onchange = () => {
  const k = cb.dataset.layer; LAYERS[k].on = cb.checked;
  if(k === 'transports' || k === 'velo') syncPt();
  if(cb.checked && zL() < LAYERS[k].minZoom){ map.easeTo({zoom:LAYERS[k].minZoom - 1}); toast(`Carte rapprochée pour afficher : ${LAYERS[k].label.toLowerCase()}`); }
  poiKey = ''; loadPoi(); saveLayers();
});
document.getElementById('floodOn').onchange = e => { FLOOD.on = e.target.checked; document.getElementById('floodBox').classList.toggle('on', FLOOD.on); applyFlood(); saveFlood(); };
document.querySelectorAll('[name=fmode]').forEach(r => r.onchange = () => {
  FLOOD.mode = r.value;
  document.getElementById('triBox').style.display = FLOOD.mode === 'tri' ? '' : 'none';
  document.getElementById('seaBox').style.display = FLOOD.mode === 'sea' ? '' : 'none';
  applyFlood(); saveFlood();
});
document.getElementById('scen').oninput = e => { FLOOD.scen = +e.target.value; renderTriLegend(); applyFlood(); saveFlood(); };
document.getElementById('sea').oninput = e => { FLOOD.sea = +e.target.value; document.getElementById('seaVal').textContent = '+' + String(FLOOD.sea).replace('.',',') + ' m'; if(FLOOD.on) setSeaLevel(FLOOD.sea); saveFlood(); };
document.getElementById('floodOn').checked = FLOOD.on; document.getElementById('floodBox').classList.toggle('on', FLOOD.on);
document.querySelector(`[name=fmode][value=${FLOOD.mode}]`).checked = true;
document.getElementById('triBox').style.display = FLOOD.mode === 'tri' ? '' : 'none';
document.getElementById('seaBox').style.display = FLOOD.mode === 'sea' ? '' : 'none';
document.getElementById('scen').value = FLOOD.scen; document.getElementById('sea').value = FLOOD.sea;
document.getElementById('seaVal').textContent = '+' + String(FLOOD.sea).replace('.',',') + ' m';
renderTriLegend();
document.querySelectorAll('[name=base]').forEach(r => r.onchange = () => setBase(r.value));

/* ---------- Dessins faits dans la page (étiquettes de prix, icônes) ---------- */
const DPR = 2;
function canvas(w, h){ const c = document.createElement('canvas'); c.width = w * DPR; c.height = h * DPR; const x = c.getContext('2d'); x.scale(DPR, DPR); return [c, x]; }
function rrect(x, X, Y, w, h, r){ x.beginPath(); x.moveTo(X + r, Y); x.arcTo(X + w, Y, X + w, Y + h, r); x.arcTo(X + w, Y + h, X, Y + h, r); x.arcTo(X, Y + h, X, Y, r); x.arcTo(X, Y, X + w, Y, r); x.closePath(); }
/* Pastille de prix étirable (icon-text-fit) : marge de 3 px pour l'ombre */
function pillImage(fill, stroke, sw){
  const W = 34, H = 26, [c, x] = canvas(W, H);
  x.shadowColor = 'rgba(16,24,40,.28)'; x.shadowBlur = 3; x.shadowOffsetY = 1;
  rrect(x, 3, 2, W - 6, H - 6, (H - 6) / 2); x.fillStyle = fill; x.fill();
  x.shadowColor = 'transparent'; x.lineWidth = sw; x.strokeStyle = stroke; x.stroke();
  const d = x.getImageData(0, 0, W * DPR, H * DPR);
  return [d, {pixelRatio:DPR, stretchX:[[13 * DPR, 21 * DPR]], stretchY:[[12 * DPR, 13 * DPR]], content:[12 * DPR, 6 * DPR, 22 * DPR, 18 * DPR]}];
}
function pinImages(){
  const dark = THEME === 'dark';
  return {
    'pin':      pillImage(dark ? '#232b38' : '#ffffff', dark ? 'rgba(255,255,255,.16)' : 'rgba(16,24,40,.14)', 1),
    'pin-seen': pillImage(dark ? '#1a2029' : '#eef0f3', dark ? 'rgba(255,255,255,.10)' : 'rgba(16,24,40,.10)', 1),
    'pin-fav':  pillImage(dark ? '#232b38' : '#ffffff', '#e0245e', 2),
    'pin-hl':   pillImage(dark ? '#f2f4f7' : '#18202f', dark ? '#f2f4f7' : '#18202f', 1)
  };
}
function poiImage(id){   // id = « poi|couleur|emoji|1 si en projet »
  const [, color, emoji, fut] = id.split('|'), S = 26, [c, x] = canvas(S, S);
  x.shadowColor = 'rgba(0,0,0,.3)'; x.shadowBlur = 3; x.shadowOffsetY = 1;
  x.beginPath(); x.arc(S / 2, S / 2, 11, 0, Math.PI * 2); x.fillStyle = fut === '1' ? '#f6effa' : '#fff'; x.fill();
  x.shadowColor = 'transparent'; x.lineWidth = 2; x.strokeStyle = color; if(fut === '1') x.setLineDash([3, 2]); x.stroke();
  x.font = '13px "Apple Color Emoji","Segoe UI Emoji","Noto Color Emoji",sans-serif'; x.textAlign = 'center'; x.textBaseline = 'middle';
  x.fillText(emoji, S / 2, S / 2 + 1);
  return [x.getImageData(0, 0, S * DPR, S * DPR), {pixelRatio:DPR}];
}
function putImage(id, [img, opt]){ if(map.hasImage(id)) map.removeImage(id); map.addImage(id, img, opt); }
map.on('styleimagemissing', e => { if(e.id.startsWith('poi|')) putImage(e.id, poiImage(e.id)); });

/* ---------- Thème sombre du fond : on recolore le style vectoriel ---------- */
const parseCv = document.createElement('canvas').getContext('2d');
function toRGBA(s){
  parseCv.fillStyle = '#000'; parseCv.fillStyle = s; const v = parseCv.fillStyle;
  if(v[0] === '#') return [parseInt(v.slice(1, 3), 16), parseInt(v.slice(3, 5), 16), parseInt(v.slice(5, 7), 16), 1];
  const m = v.match(/[\d.]+/g); return m ? [+m[0], +m[1], +m[2], m[3] == null ? 1 : +m[3]] : null;
}
function darkColor(s, prop){
  if(typeof s !== 'string' || !/^(#|rgb|hsl)/i.test(s)) return s;
  const c = toRGBA(s); if(!c) return s;
  let [r, g, b, a] = c.map((v, i) => i < 3 ? v / 255 : v);
  const mx = Math.max(r, g, b), mn = Math.min(r, g, b), l = (mx + mn) / 2, d = mx - mn;
  let h = 0, sat = d ? d / (1 - Math.abs(2 * l - 1)) : 0;
  if(d){ h = mx === r ? ((g - b) / d) % 6 : mx === g ? (b - r) / d + 2 : (r - g) / d + 4; h *= 60; if(h < 0) h += 360; }
  // clair -> sombre ; les textes restent lisibles (clairs), les halos deviennent sombres
  let L = prop === 'text-color' ? .72 + (1 - l) * .2 : prop === 'text-halo-color' ? .1 : .1 + (1 - l) * .22;
  if(prop === 'fill-color' && /water|eau/i.test(String(darkColor.layer))) L = .2;
  sat = Math.min(sat, .35);
  const C = (1 - Math.abs(2 * L - 1)) * sat, X = C * (1 - Math.abs((h / 60) % 2 - 1)), m = L - C / 2;
  const [R, G, B] = h < 60 ? [C, X, 0] : h < 120 ? [X, C, 0] : h < 180 ? [0, C, X] : h < 240 ? [0, X, C] : h < 300 ? [X, 0, C] : [C, 0, X];
  return `rgba(${Math.round((R + m) * 255)},${Math.round((G + m) * 255)},${Math.round((B + m) * 255)},${a})`;
}
const mapColors = (v, fn) => Array.isArray(v) ? v.map(x => mapColors(x, fn)) : fn(v);
const COLOR_PROPS = ['background-color', 'fill-color', 'fill-outline-color', 'line-color', 'text-color', 'text-halo-color', 'fill-extrusion-color'];
let BASE_PAINT = null;
function rememberBase(){
  if(BASE_PAINT) return;
  BASE_PAINT = [];
  map.getStyle().layers.forEach(l => { if(l.id.startsWith('ci-') || !l.paint) return;
    COLOR_PROPS.forEach(p => { const v = l.paint[p]; if(v != null) BASE_PAINT.push({id:l.id, p, v}); }); });
}
function applyMapTheme(){
  if(!mapReady) return;
  rememberBase();
  const dark = THEME === 'dark';
  BASE_PAINT.forEach(({id, p, v}) => { darkColor.layer = id; try { map.setPaintProperty(id, p, dark ? mapColors(v, c => darkColor(c, p)) : v); } catch(_) {} });
  Object.entries(pinImages()).forEach(([k, v]) => putImage(k, v));
  map.setPaintProperty('ci-pins', 'text-color', ['case', ['==', ['get', 'seen'], 1], dark ? '#8d96a6' : '#5b6474', dark ? '#e8ecf2' : '#18202f']);
  map.setPaintProperty('ci-pins-hl', 'text-color', dark ? '#18202f' : '#ffffff');
  map.setPaintProperty('ci-clusters', 'circle-color', dark ? '#e8ecf2' : '#18202f');
  map.setPaintProperty('ci-clusters', 'circle-stroke-color', dark ? 'rgba(232,236,242,.22)' : 'rgba(24,32,47,.18)');
  map.setPaintProperty('ci-cluster-n', 'text-color', dark ? '#18202f' : '#ffffff');
  ['ci-communes-main', 'ci-communes-nb'].forEach(id => map.setPaintProperty(id, 'line-color', ['coalesce', ['get', 'c'], dark ? '#c9d1dd' : '#18202f']));
  map.setPaintProperty('tc-rail-casing', 'line-color', dark ? '#141a22' : '#ffffff');
  map.setPaintProperty('tc-gares-label', 'text-color', dark ? '#e8ecf2' : '#1b2330');
  map.setPaintProperty('tc-gares-label', 'text-halo-color', dark ? '#141a22' : '#ffffff');
}
function setTheme(t){
  THEME = t; store.set('theme', t); document.documentElement.dataset.theme = t;
  const b = document.getElementById('themeBtn'); if(b){ b.setAttribute('aria-pressed', t === 'dark'); b.title = t === 'dark' ? 'Passer en thème clair' : 'Passer en thème sombre'; }
  applyMapTheme();
}

/* ---------- Mise en place des couches (au chargement du style) ---------- */
let BOLD = ['Noto Sans Bold'];
function setupLayers(){
  const st = map.getStyle(), fonts = new Set();
  st.layers.forEach(l => { const f = l.layout && l.layout['text-font']; if(Array.isArray(f) && typeof f[0] === 'string') f.forEach(x => fonts.add(x)); });
  const bold = [...fonts].find(f => /bold/i.test(f)) || [...fonts].find(f => /medium|semibold/i.test(f)) || [...fonts][0];
  if(bold) BOLD = [bold];
  const firstSymbol = (st.layers.find(l => l.type === 'symbol') || {}).id;
  const src = (id, o) => map.addSource(id, Object.assign({type:'geojson', data:PENDING[id] || EMPTY}, o || {}));
  const ras = (id, tiles, o) => map.addSource(id, Object.assign({type:'raster', tiles, tileSize:256}, o));
  const lay = (l, before) => { l.layout = Object.assign({visibility:VIS[l.id] === false ? 'none' : 'visible'}, l.layout || {}); if(VIS[l.id] === undefined && l.hidden){ l.layout.visibility = 'none'; } delete l.hidden; map.addLayer(l, before); };

  // sous les noms de lieux du fond
  ras('sat', ['https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}'], {maxzoom:19, attribution:'Imagerie &copy; Esri'});
  lay({id:'sat', type:'raster', source:'sat', hidden:true}, firstSymbol);
  FLOOD_SCEN.forEach((f, i) => { ras('flood' + i, [wmsUrl(f.layer)], {attribution:'Inondation : &copy; <a href="https://www.georisques.gouv.fr">Géorisques</a>'});
    lay({id:'flood' + i, type:'raster', source:'flood' + i, paint:{'raster-opacity':.6, 'raster-fade-duration':0}, hidden:true}, firstSymbol); });
  ras('sea', seaTiles(FLOOD.sea), {maxzoom:15, attribution:'Altitudes : Mapzen Terrarium (AWS Open Data)'}); seaShown = FLOOD.sea;
  lay({id:'sea', type:'raster', source:'sea', paint:{'raster-opacity':.6}, hidden:true}, firstSymbol);
  src('poi-areas');
  lay({id:'ci-green', type:'fill', source:'poi-areas', paint:{'fill-color':'#6cc070', 'fill-opacity':.35, 'fill-outline-color':'#3a9d4a'}}, firstSymbol);
  ras('velo', ['a', 'b', 'c'].map(s => `https://${s}.tile-cyclosm.openstreetmap.fr/cyclosm-lite/{z}/{x}/{y}.png`), {maxzoom:20, attribution:'Pistes cyclables : <a href="https://www.cyclosm.org">CyclOSM</a>'});
  lay({id:'velo', type:'raster', source:'velo', hidden:true}, firstSymbol);

  // au-dessus du fond
  src('communes');
  lay({id:'ci-communes-fill', type:'fill', source:'communes', paint:{'fill-color':['coalesce', ['get', 'c'], '#18202f'], 'fill-opacity':['case', ['==', ['get', 'main'], 1], .05, .03]}});
  lay({id:'ci-communes-nb', type:'line', source:'communes', filter:['!=', ['get', 'main'], 1], layout:{'line-join':'round'},
       paint:{'line-color':['coalesce', ['get', 'c'], '#18202f'], 'line-width':1.6, 'line-opacity':.85, 'line-dasharray':[3.5, 2.5]}});
  lay({id:'ci-communes-main', type:'line', source:'communes', filter:['==', ['get', 'main'], 1], layout:{'line-join':'round'},
       paint:{'line-color':['coalesce', ['get', 'c'], '#18202f'], 'line-width':2.5}});
  src('zones');
  lay({id:'ci-zones-fill', type:'fill', source:'zones', paint:{'fill-color':['get', 'c'], 'fill-opacity':['case', ['==', ['get', 'approx'], 1], .04, .14]}});
  lay({id:'ci-zones-line', type:'line', source:'zones', filter:['!=', ['get', 'approx'], 1], paint:{'line-color':['get', 'c'], 'line-width':2}});
  lay({id:'ci-zones-dash', type:'line', source:'zones', filter:['==', ['get', 'approx'], 1], paint:{'line-color':['get', 'c'], 'line-width':1.5, 'line-dasharray':[2.7, 4]}});
  src('poi-lines');
  lay({id:'ci-futur', type:'line', source:'poi-lines', layout:{'line-cap':'butt'}, paint:{'line-color':'#8e44ad', 'line-width':4, 'line-opacity':.8, 'line-dasharray':[2, 1.5]}});
  // transports IDFM (sous les annonces)
  src('tc-bus'); src('tc-rail'); src('tc-gares'); src('tc-arrets');
  const TCV = LAYERS.transports.on;
  lay({id:'tc-bus', type:'line', source:'tc-bus', minzoom:12, layout:{'line-cap':'round', visibility:TCV ? 'visible' : 'none'}, paint:{'line-color':['get', 'c'], 'line-width':['interpolate', ['linear'], ['zoom'], 12, 1, 16, 2.5], 'line-opacity':.7}});
  lay({id:'tc-rail-casing', type:'line', source:'tc-rail', layout:{'line-cap':'round', 'line-join':'round', visibility:TCV ? 'visible' : 'none'}, paint:{'line-color':'#ffffff', 'line-opacity':.75, 'line-width':['interpolate', ['linear'], ['zoom'], 8, ['+', ['get', 'w'], 1], 14, ['+', ['*', ['get', 'w'], 1.8], 2]]}});
  lay({id:'tc-rail', type:'line', source:'tc-rail', layout:{'line-cap':'round', 'line-join':'round', visibility:TCV ? 'visible' : 'none'}, paint:{'line-color':['get', 'c'], 'line-width':['interpolate', ['linear'], ['zoom'], 8, ['*', ['get', 'w'], .6], 14, ['*', ['get', 'w'], 1.8]]}});
  lay({id:'tc-arrets', type:'circle', source:'tc-arrets', minzoom:14, layout:{visibility:TCV ? 'visible' : 'none'}, paint:{'circle-radius':3, 'circle-color':'#fff', 'circle-stroke-color':'#e09a1a', 'circle-stroke-width':1.5}});
  lay({id:'tc-gares', type:'circle', source:'tc-gares', minzoom:10, layout:{visibility:TCV ? 'visible' : 'none'}, paint:{'circle-radius':['interpolate', ['linear'], ['zoom'], 10, 2.5, 15, 6], 'circle-color':'#fff', 'circle-stroke-color':'#1b2330', 'circle-stroke-width':['interpolate', ['linear'], ['zoom'], 10, 1.2, 15, 2]}});
  lay({id:'tc-gares-label', type:'symbol', source:'tc-gares', minzoom:13, layout:{'text-field':['get', 'n'], 'text-font':BOLD, 'text-size':11.5, 'text-offset':[0, 1.1], 'text-anchor':'top', 'text-optional':true, visibility:TCV ? 'visible' : 'none'},
       paint:{'text-color':'#1b2330', 'text-halo-color':'#ffffff', 'text-halo-width':1.5}});
  src('poi');
  lay({id:'ci-stops', type:'circle', source:'poi', filter:['==', ['get', 'kind'], 'stop'],
       paint:{'circle-color':['get', 'col'], 'circle-radius':['case', ['==', ['get', 'big'], 1], 6.5, 5], 'circle-stroke-color':'#fff', 'circle-stroke-width':2}});
  lay({id:'ci-poi', type:'symbol', source:'poi', filter:['==', ['get', 'kind'], 'icon'], layout:{'icon-image':['get', 'ic'], 'icon-allow-overlap':true, 'icon-ignore-placement':true}});

  // annonces : regroupées jusqu'au niveau du quartier, étiquettes de prix ensuite
  src('annonces', {cluster:true, clusterMaxZoom:15, clusterRadius:42});
  lay({id:'ci-clusters', type:'circle', source:'annonces', filter:['has', 'point_count'],
       paint:{'circle-color':'#18202f', 'circle-radius':['step', ['get', 'point_count'], 18, 10, 20, 50, 23], 'circle-stroke-width':5, 'circle-stroke-color':'rgba(24,32,47,.18)'}});
  lay({id:'ci-cluster-n', type:'symbol', source:'annonces', filter:['has', 'point_count'],
       layout:{'text-field':['get', 'point_count_abbreviated'], 'text-font':BOLD, 'text-size':13, 'text-allow-overlap':true}, paint:{'text-color':'#fff'}});
  Object.entries(pinImages()).forEach(([k, v]) => putImage(k, v));
  const pinLayout = img => ({'icon-image':img, 'icon-text-fit':'both', 'icon-text-fit-padding':[3, 7, 3, 7], 'text-field':['get', 'p'], 'text-font':BOLD, 'text-size':12, 'text-max-width':30,
    'icon-allow-overlap':true, 'text-allow-overlap':true, 'icon-ignore-placement':true, 'text-ignore-placement':true, 'symbol-sort-key':['get', 'sk']});
  lay({id:'ci-pins', type:'symbol', source:'annonces', filter:['!', ['has', 'point_count']],
       layout:pinLayout(['case', ['==', ['get', 'fav'], 1], 'pin-fav', ['==', ['get', 'seen'], 1], 'pin-seen', 'pin']),
       paint:{'text-color':'#18202f', 'icon-opacity':['case', ['==', ['get', 'out'], 1], .45, 1], 'text-opacity':['case', ['==', ['get', 'out'], 1], .45, 1]}});
  lay({id:'ci-pins-hl', type:'symbol', source:'annonces', filter:['==', ['get', 'n'], -1], layout:pinLayout('pin-hl'), paint:{'text-color':'#fff'}});
  // les traits (et non les annonces) ne gênent pas le clic : seuls les points sont interactifs
  mapReady = true;
  BASE_PAINT = null; applyMapTheme();
  Object.entries(VIS).forEach(([id, on]) => map.getLayer(id) && map.setLayoutProperty(id, 'visibility', on ? 'visible' : 'none'));
}
map.on('style.load', () => { styleOnce = true; try { setupLayers(); } catch(e){ console.error(e); setStatus('Erreur d\'affichage de la carte : rechargez la page'); } });

/* ---------- Bulles d'information au survol ---------- */
function whenReady(fn){ if(mapReady) fn(); else map.once('style.load', () => fn()); }
const tip = new maplibregl.Popup({closeButton:false, closeOnClick:false, className:'ci-tip', offset:12, maxWidth:'280px'});
whenReady(() => ['ci-stops', 'ci-poi', 'ci-futur', 'ci-green'].forEach(id => {
  map.on('mousemove', id, e => { const f = e.features[0]; if(!f || !f.properties.tip) return; map.getCanvas().style.cursor = 'help'; tip.setLngLat(e.lngLat).setHTML(f.properties.tip).addTo(map); });
  map.on('mouseleave', id, () => { map.getCanvas().style.cursor = ''; tip.remove(); });
  map.on('click', id, e => { const f = e.features[0]; if(f && f.properties.tip) tip.setLngLat(e.lngLat).setHTML(f.properties.tip).addTo(map); });
}));
map.on('movestart', () => tip.remove());

setBase(baseKey); syncPt(); applyFlood();
