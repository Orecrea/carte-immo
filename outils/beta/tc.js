
/* =========================================================
   Transports d'Île-de-France sur la carte des annonces : données officielles IDFM
   (les mêmes que la carte des transports), dessinées par la carte graphique.
   Remplace les tuiles ÖPNVKarte, que MapLibre ne peut pas afficher (serveur sans autorisation d'accès croisé).
   ========================================================= */
const TC_API = 'https://data.iledefrance-mobilites.fr/api/explore/v2.1/catalog/datasets/';
const TC_DS = {rail:'traces-du-reseau-ferre-idf', gares:'emplacement-des-gares-idf', bus:'traces-des-lignes-regulieres-de-bus-en-ile-de-france', arrets:'arrets'};
const TC_MODE = {metro:'#1d6fd0', tram:'#2a9d5c', rer:'#d6402e', train:'#7a5aa6', tzen:'#0f9d9a', cable:'#8b5a2b'};
const TC_METRO = {M1:'#FFCD00', M2:'#003CA6', M3:'#837902', M3BIS:'#6EC4E8', M4:'#CF009E', M5:'#FF7E2E', M6:'#6ECA97', M7:'#FA9ABA', M7BIS:'#6ECA97',
  M8:'#E19BDF', M9:'#B6BD00', M10:'#C9910D', M11:'#704B1C', M12:'#007852', M13:'#6EC4E8', M14:'#62259D'};
const tcPick = (p, re) => { for(const k of Object.keys(p)) if(re.test(k) && p[k] != null && p[k] !== '' && typeof p[k] !== 'object') return p[k]; return null; };
function tcColor(p, fb){
  for(const k of Object.keys(p)) if(/colou?r|couleur|hexa/i.test(k) && !/text|texte|print|cmyk/i.test(k)){
    const v = String(p[k] || '').trim(); if(/^[0-9a-f]{6}$/i.test(v)) return '#' + v; if(/^#[0-9a-f]{3,8}$/i.test(v)) return v; }
  return fb;
}
function tcKind(p){
  const mode = String(tcPick(p, /^(mode|transportmode|route_type|type)/i) || '').toLowerCase(), label = String(tcPick(p, /^res_com$/i) || tcPick(p, /^(indice|short_?name|nom_?ligne)/i) || '');
  const lab = label + ' ' + mode + ' ' + String(tcPick(p, /name|nom/i) || '');
  if(/t\s?-?\s?zen|bhns/i.test(lab)) return ['tzen', label];
  if(/c[âa]ble|t[ée]l[ée]ph[ée]rique/i.test(lab)) return ['cable', label];
  if(/metro|subway|métro/.test(mode)) return ['metro', label];
  if(/tram/.test(mode)) return ['tram', label];
  if(/^rer/i.test(label) || /^rer/i.test(mode) || /^[A-E]$/.test(label)) return ['rer', label];
  return ['train', label];
}
async function tcGeo(ds, where, signal){
  const r = await fetch(TC_API + ds + '/exports/geojson?limit=-1&timezone=UTC' + (where ? '&where=' + encodeURIComponent(where) : ''), {signal});
  if(!r.ok) throw new Error('IDFM ' + r.status); return r.json();
}
/* Le nom du champ géographique varie selon les jeux : on le lit dans leur description, comme la carte des transports. */
const tcFields = {};
async function tcBoxWhere(ds, [w, s, e, n]){
  if(!tcFields[ds]){
    const f = ((await (await fetch(TC_API + ds)).json()).fields) || [], sh = f.find(x => x.type === 'geo_shape'), pt = f.find(x => x.type === 'geo_point_2d');
    if(!sh && !pt) throw new Error('IDFM ' + ds + ' sans champ géographique');
    tcFields[ds] = sh ? {n:sh.name, t:'shape'} : {n:pt.name, t:'point'};
  }
  const g = tcFields[ds];
  return g.t === 'point' ? `in_bbox(${g.n},${s},${w},${n},${e})` : `intersects(${g.n},geom'${tcPoly([w, s, e, n])}')`;
}
let tcLoaded = false, tcBusBox = null, tcStopBox = null, tcCtl = null;
async function loadTcNetwork(){
  if(tcLoaded) return; tcLoaded = true;
  try {
    const [rail, gares] = await Promise.all([
      cached('idfm-rail-v1', () => tcGeo(TC_DS.rail)),
      cached('idfm-gares-v1', () => tcGeo(TC_DS.gares))
    ]);
    rail.features.forEach(f => { const p = f.properties || (f.properties = {}), [k, label] = tcKind(p);
      const mk = k === 'metro' ? 'M' + String(label).toUpperCase().replace(/\s/g, '').replace(/^M/, '') : '';
      f.properties = {k, c:TC_METRO[mk] || tcColor(p, TC_MODE[k]), w:k === 'train' ? 2 : k === 'tram' || k === 'tzen' ? 2.4 : 3}; });
    const seen = new Set();
    gares.features = gares.features.filter(f => { if(!f.geometry || f.geometry.type !== 'Point') return false;
      const p = f.properties || {}, n = String(tcPick(p, /^(nom_?gares?|nom_?zda|nom|name|stop_?name)/i) || tcPick(p, /(nom|name)/i) || '');
      const key = n + Math.round(f.geometry.coordinates[0] * 300) + Math.round(f.geometry.coordinates[1] * 300); if(seen.has(key)) return false; seen.add(key);
      const [k] = tcKind(p); f.properties = {n, k}; return true; });
    setSrc('tc-rail', rail); setSrc('tc-gares', gares);
  } catch(e){ tcLoaded = false; setStatus('Transports IDFM indisponibles pour le moment'); }
}
const tcGrow = b => { const dx = (b.getEast() - b.getWest()) * .4, dy = (b.getNorth() - b.getSouth()) * .4; return [b.getWest() - dx, b.getSouth() - dy, b.getEast() + dx, b.getNorth() + dy]; };
const tcIn = (b, L) => L && b.getWest() >= L[0] && b.getSouth() >= L[1] && b.getEast() <= L[2] && b.getNorth() <= L[3];
const tcPoly = ([w, s, e, n]) => `POLYGON((${[[w,s],[e,s],[e,n],[w,n],[w,s]].map(p => p.join(' ')).join(',')}))`;
async function loadTcViewport(){
  if(!LAYERS.transports.on) return;
  loadTcNetwork();
  const z = map.getZoom(), vb = map.getBounds();
  if(z < 12 || (tcIn(vb, tcBusBox) && (z < 14 || tcIn(vb, tcStopBox)))) return;
  if(tcCtl) tcCtl.abort(); const ctl = tcCtl = new AbortController(), box = tcGrow(vb);
  try {
    if(!tcIn(vb, tcBusBox)){
      const fc = await tcGeo(TC_DS.bus, await tcBoxWhere(TC_DS.bus, box), ctl.signal);
      fc.features.forEach(f => { const p = f.properties || {}; f.properties = {c:tcColor(p, '#e09a1a'), n:String(tcPick(p, /(short_?name|shortname|indice|nom_?ligne|name)/i) || '')}; });
      setSrc('tc-bus', fc); tcBusBox = box;
    }
    if(z >= 14 && !tcIn(vb, tcStopBox)){
      const wh = await tcBoxWhere(TC_DS.arrets, box);
      const fc = await tcGeo(TC_DS.arrets, wh + ' and arrtype="bus"', ctl.signal).catch(e => { if(e.name === 'AbortError') throw e; return tcGeo(TC_DS.arrets, wh, ctl.signal); });
      fc.features.forEach(f => { const p = f.properties || {}; f.properties = {n:String(tcPick(p, /^(arrname|nom|name)/i) || '')}; });
      setSrc('tc-arrets', fc); tcStopBox = box;
    }
  } catch(e){ if(e.name !== 'AbortError') setStatus('Bus IDFM indisponibles pour le moment'); }
}
map.on('moveend', () => { clearTimeout(loadTcViewport.t); loadTcViewport.t = setTimeout(loadTcViewport, 300); });
