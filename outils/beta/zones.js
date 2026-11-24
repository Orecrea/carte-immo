function zoneBounds(z){
  if(z.poly) return BB.geom(z.poly);
  const b = new BB(), r = approxRadius(z);
  usedOrigins(z).forEach(o => { const dy = r / 111320, dx = r / (111320 * Math.cos(o.lat * Math.PI / 180)); b.ext(o.lat - dy, o.lng - dx); b.ext(o.lat + dy, o.lng + dx); });
  return b;
}
let zoneMarkers = [];
function drawZones(){
  const feats = [];
  zones.forEach(z => {
    if(z.poly) feats.push({type:'Feature', geometry:z.poly, properties:{c:z.color, approx:0}});
    else usedOrigins(z).forEach(o => feats.push({type:'Feature', geometry:circleGeom(o.lat, o.lng, approxRadius(z)), properties:{c:z.color, approx:1}}));
  });
  setSrc('zones', FC(feats));
  // points de départ : peu nombreux, déplaçables à la main -> marqueurs HTML
  zoneMarkers.forEach(m => m.remove()); zoneMarkers = [];
  zones.forEach(z => usedOrigins(z).forEach(o => {
    const el = document.createElement('div'); el.className = 'zone-dot' + (z.kind === 'stations' ? ' st' : ''); el.style.background = z.color;
    el.title = `${o.name || z.name} · ${legsLabel(z)}`;
    const m = new maplibregl.Marker({element:el, draggable:z.kind === 'point'}).setLngLat([o.lng, o.lat]).addTo(map);
    if(z.kind === 'point') m.on('dragend', () => { const p = m.getLngLat(); o.lat = p.lat; o.lng = p.lng; reverseName(z); saveZones(); computeZone(z); });
    zoneMarkers.push(m);
  }));
}
