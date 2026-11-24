/* Couleur propre à chaque ville, reprise par son contour et ses communes voisines */
const CITY_COLORS = ['#3b5bdb', '#0c8599', '#d9480f', '#9c36b5', '#2b8a3e', '#c2255c', '#5f3dc4', '#e67700', '#1971c2', '#087f5b'];
function nextCityColor(){ const used = cities.map(c => c.col); return CITY_COLORS.find(c => !used.includes(c)) || CITY_COLORS[cities.length % CITY_COLORS.length]; }
cities.forEach(c => { if(!c.col) c.col = nextCityColor(); });
const cityColor = code => { const c = cities.find(x => x.code === code); return c ? c.col : null; };
function communeColor(c){ return cityColor(c.main ? c.code : c.parent) || '#18202f'; }
function drawCommunes(){
  setSrc('communes', FC(activeCommunes.filter(c => c.geom).map(c => ({type:'Feature', geometry:c.geom, properties:{main:c.main ? 1 : 0, c:communeColor(c)}}))));
  if(fitCities && activeCommunes.length && !lastLoad0) lastLoad0 = true;
  if(fitCities && activeCommunes.length){ const b = new BB(); activeCommunes.forEach(c => b.geom(c.geom)); fitTo(b.pad(.05)); fitCities = false; }
  $('#allStations').disabled = !cities.length;
}
/* Nombre de maisons par ville (voisines comprises) */
let CITY_N = {}, CITY_TOTAL = 0;
function cityCounts(inside){
  CITY_N = {}; CITY_TOTAL = inside.length;
  inside.forEach(l => { const c = activeCommunes.find(x => inGeom(l.lng, l.lat, x.geom)); if(!c) return; const k = c.main ? c.code : c.parent; CITY_N[k] = (CITY_N[k] || 0) + 1; });
  paintCitiesBtn();
  document.querySelectorAll('#cityChips [data-n]').forEach(el => { const n = CITY_N[el.dataset.n] || 0; el.textContent = n + ' maison' + (n > 1 ? 's' : ''); });
}
function paintCitiesBtn(){
  const n = cities.length;
  $('#citiesWrap').hidden = !n;
  $('#citiesTxt').innerHTML = `<b>${n} ville${n > 1 ? 's' : ''}</b><span class="cmeta"> · ${CITY_TOTAL} maison${CITY_TOTAL > 1 ? 's' : ''}</span>`;
  $('#citiesDots').innerHTML = cities.slice(0, 5).map(c => `<i style="background:${c.col}"></i>`).join('');
  $('#citiesSum').textContent = `${CITY_TOTAL} maison${CITY_TOTAL > 1 ? 's' : ''} avec vos critères`;
}
function renderCityChips(){
  if(typeof renderTripCities === 'function') renderTripCities();
  $('#cityChips').innerHTML = cities.map(c => {
    const nbs = activeCommunes.filter(x => !x.main && x.parent === c.code).length;
    return `<div class="crow" style="--cc:${c.col}">
      <button class="cname" data-go="${c.code}" title="Centrer la carte sur ${esc(c.name)}"><i></i><span><b>${esc(c.name)}</b><small>${c.cp ? esc(c.cp) + ' · ' : ''}<span data-n="${c.code}">${CITY_N[c.code] || 0} maison${(CITY_N[c.code] || 0) > 1 ? 's' : ''}</span>${c.nb && nbs ? ` · ${nbs} voisine${nbs > 1 ? 's' : ''}` : ''}</small></span></button>
      <button class="nbt${c.nb ? ' on' : ''}" data-nb="${c.code}" aria-pressed="${!!c.nb}" title="Inclure les communes limitrophes de ${esc(c.name)}">+ voisines</button>
      <button class="crm" data-rm="${c.code}" aria-label="Retirer ${esc(c.name)}">×</button></div>`;
  }).join('');
  $('#allStations').disabled = !cities.length;
  $('#q').placeholder = cities.length ? 'Ajouter une ville…' : 'Villes recherchées (plusieurs possibles)…';
  paintCitiesBtn();
  store.set('cities', cities); updateSyncNote();
}
function setCitiesOpen(on){ $('#citiesWrap').classList.toggle('open', on); $('#citiesBtn').setAttribute('aria-expanded', on); }
$('#citiesBtn').onclick = e => { e.stopPropagation(); setCitiesOpen(!$('#citiesWrap').classList.contains('open')); };
document.addEventListener('click', e => { if(!e.target.closest('#citiesWrap')) setCitiesOpen(false); });
document.addEventListener('keydown', e => { if(e.key === 'Escape') setCitiesOpen(false); });
$('#citiesFit').onclick = () => { const b = new BB(); activeCommunes.forEach(c => b.geom(c.geom)); fitTo(b.pad(.05)); setCitiesOpen(false); };
$('#cityChips').addEventListener('click', e => {
  const go = e.target.closest('[data-go]');
  if(go){ const b = new BB(); activeCommunes.filter(c => c.code === go.dataset.go || c.parent === go.dataset.go).forEach(c => b.geom(c.geom)); fitTo(b.pad(.08)); if(matchMedia('(max-width:860px)').matches) setCitiesOpen(false); return; }
  const nbb = e.target.closest('[data-nb]');
  if(nbb){ const c = cities.find(x => x.code === nbb.dataset.nb); c.nb = !c.nb; renderCityChips(); updateCommunes(); return; }
  const b = e.target.closest('[data-rm]'); if(!b) return;
  const i = cities.findIndex(c => c.code === b.dataset.rm), c = cities[i];
  cities.splice(i, 1); renderCityChips(); updateCommunes();
  toast(`${c.name} retirée`, () => { cities.splice(i, 0, c); renderCityChips(); updateCommunes(); });
});
