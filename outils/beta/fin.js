renderCityChips(); if(cities.length) updateCommunes();
setTheme(THEME);
$('#themeBtn').onclick = () => setTheme(THEME === 'dark' ? 'light' : 'dark');

/* Clic et survol des annonces sur la carte (une fois les couches créées) */
whenReady(() => {
map.on('click', 'ci-pins', e => { const f = e.features[0]; if(!f || addMode) return; const g = PIN_L[f.properties.n]; openListing(g[0], g.length > 1 ? g : currentList); });
map.on('mouseenter', 'ci-pins', e => { map.getCanvas().style.cursor = 'pointer'; const f = e.features[0]; if(f){ PIN_L[f.properties.n].forEach(l => { hlPin(l.id, true); hlCard(l.id, true); }); } });
map.on('mouseleave', 'ci-pins', () => { map.getCanvas().style.cursor = ''; hlPin(0, false); document.querySelectorAll('.card.hl').forEach(c => c.classList.remove('hl')); });
map.on('click', 'ci-clusters', async e => {
  const f = e.features[0]; if(!f || addMode) return;
  try { const z = await map.getSource('annonces').getClusterExpansionZoom(f.properties.cluster_id); map.easeTo({center:f.geometry.coordinates, zoom:z + .3, duration:500}); }
  catch(_) { map.easeTo({center:f.geometry.coordinates, zoom:map.getZoom() + 2}); }
});
map.on('mouseenter', 'ci-clusters', () => map.getCanvas().style.cursor = 'pointer');
map.on('mouseleave', 'ci-clusters', () => map.getCanvas().style.cursor = '');
});

/* =========================================================
   Deux environnements : Annonces / Transports
   La carte des transports (transports.html) est chargée telle quelle dans un cadre,
   au premier passage, puis reste ouverte : la bascule est immédiate et garde la position.
   ========================================================= */
let ENV = 'immo', tframe = null;
const hashOf = () => { const c = map.getCenter(); return `#${map.getZoom().toFixed(2)}/${c.lat.toFixed(5)}/${c.lng.toFixed(5)}`; };
function tcView(){
  try { const m = tframe.contentWindow.location.hash.match(/^#([\d.]+)\/(-?[\d.]+)\/(-?[\d.]+)/); return m ? {zoom:+m[1], center:[+m[3], +m[2]]} : null; } catch(_) { return null; }
}
function setEnv(e, quiet){
  if(e === ENV) return;
  ENV = e; store.set('env', e);
  document.querySelectorAll('[data-env]').forEach(b => { const on = b.dataset.env === e; b.setAttribute('aria-selected', on); b.tabIndex = on ? 0 : -1; });
  document.body.classList.toggle('env-tc', e === 'tc');
  if(e === 'tc'){
    setCitiesOpen(false); setLayersOpen(false);
    if(!tframe){
      tframe = document.createElement('iframe'); tframe.id = 'tframe'; tframe.title = 'Carte des transports';
      tframe.src = 'transports.html' + hashOf();
      tframe.addEventListener('load', () => { try { tframe.contentWindow.addEventListener('keydown', envKey); } catch(_) {} });
      $('#tcWrap').appendChild(tframe);
    } else { try { tframe.contentWindow.location.hash = hashOf(); } catch(_) {} }
    $('#tcWrap').inert = false;
  } else {
    const v = tframe && tcView(); if(v && !quiet) map.jumpTo(v);
    $('#tcWrap').inert = true;
    map.resize();
  }
}
function envKey(e){
  const t = e.target, typing = t && (t.isContentEditable || /^(INPUT|TEXTAREA|SELECT)$/.test(t.tagName));
  if(typing || e.ctrlKey || e.metaKey || e.altKey || (e.key !== 't' && e.key !== 'T')) return;
  if($('#modalBg').classList.contains('open')) return;
  e.preventDefault(); setEnv(ENV === 'tc' ? 'immo' : 'tc');
}
document.addEventListener('keydown', envKey);
$('#envSwitch').addEventListener('click', e => { const b = e.target.closest('[data-env]'); if(b) setEnv(b.dataset.env); });
$('#envSwitch').addEventListener('keydown', e => { if(e.key === 'ArrowLeft' || e.key === 'ArrowRight'){ e.preventDefault(); setEnv(ENV === 'tc' ? 'immo' : 'tc'); $(`[data-env=${ENV}]`).focus(); } });
$('#tcWrap').inert = true;
if(store.get('env', 'immo') === 'tc') setEnv('tc', true);
