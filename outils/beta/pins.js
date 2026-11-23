/* Annonces : une seule source de données, dessinée par la carte graphique (regroupement natif) */
let PIN_N = new Map(), PIN_L = [], pinShown = [], pinInside = new Set();
/* Plusieurs annonces au même endroit (souvent le centre de la commune) : une seule étiquette « 3 maisons · dès 255 k€ » */
function pinFeatures(){
  PIN_N = new Map(); PIN_L = [];
  const groups = new Map();
  pinShown.forEach(l => { const k = l.lat.toFixed(4) + ',' + l.lng.toFixed(4); (groups.get(k) || groups.set(k, []).get(k)).push(l); });
  return FC([...groups.values()].map((g, n) => {
    g.sort((a, b) => a.price - b.price);
    g.forEach(l => PIN_N.set(String(l.id), n)); PIN_L[n] = g;
    const l = g[0], fav = g.some(x => favs[x.id]) ? 1 : 0, out = g.some(x => pinInside.has(x)) ? 0 : 1, seen = g.every(x => vus[x.id]) ? 1 : 0;
    return {type:'Feature', id:n, geometry:{type:'Point', coordinates:[l.lng, l.lat]},
            properties:{n, p:g.length > 1 ? `${g.length} maisons · dès ${short(l.price)}` : short(l.price), fav, out, seen, sk:fav ? 3 : out ? 0 : seen ? 1 : 2}};
  }));
}
function updatePins(){ setSrc('annonces', pinFeatures()); }
function renderListings(){
  const ok = LISTINGS.filter(l => passCriteria(l) && !isHidden(l) && (!F.unseen || !vus[l.id]));
  let inside = ok.filter(l => inArea(l) && inCities(l));
  renderNews(inside);
  if(newsOnly) inside = inside.filter(isNews);
  renderHidden();
  const sorters = {recent:(a,b)=>a.days-b.days, pasc:(a,b)=>a.price-b.price, pdesc:(a,b)=>b.price-a.price,
                   ppm:(a,b)=>a.price/(a.surf||1e9)-b.price/(b.surf||1e9), surf:(a,b)=>(b.surf||0)-(a.surf||0), trip:(a,b)=>bestTrip(a)-bestTrip(b)};
  inside.sort(sorters[F.sort] || sorters.recent);
  currentList = inside;

  // carte
  pinInside = new Set(inside);
  pinShown = F.outside ? ok : inside;
  updatePins();
  cityCounts(inside);

