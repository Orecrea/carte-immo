/* Annonces : une seule source de données, dessinée par la carte graphique (regroupement natif) */
let PIN_N = new Map(), PIN_L = [], pinShown = [], pinInside = new Set();
function pinFeatures(){
  PIN_N = new Map(); PIN_L = [];
  return FC(pinShown.map((l, n) => {
    PIN_N.set(String(l.id), n); PIN_L[n] = l;
    const fav = favs[l.id] ? 1 : 0, out = pinInside.has(l) ? 0 : 1;
    return {type:'Feature', id:n, geometry:{type:'Point', coordinates:[l.lng, l.lat]},
            properties:{n, p:short(l.price), fav, out, seen:vus[l.id] ? 1 : 0, sk:fav ? 3 : out ? 0 : vus[l.id] ? 1 : 2}};
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

