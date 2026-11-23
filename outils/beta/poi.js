function drawPoi(k, e, t, c){
  const name = t.name ? ' · ' + esc(t.name) : '', info = poiInfo(k, t), P = (lat, lng) => ({type:'Point', coordinates:[lng, lat]});
  const push = (geometry, props) => POIF[k].push({type:'Feature', geometry, properties:props});
  const line = () => e.geometry.map(p => [p.lon, p.lat]);
  if(k === 'futur'){
    const when = t.opening_date || t['opening_date:planned'] || t['start_date'];
    const extra = (t.ref ? ' (ligne ' + esc(t.ref) + ')' : '') + (when ? '<br>Ouverture prévue : ' + esc(when) : '');
    if(isStationLike(t)) push(P(c[0], c[1]), {kind:'icon', ic:`poi|${LAYERS.futur.color}|🚉|1`, tip:`<b>Station ${info.type.toLowerCase()}</b>${name}${extra}`});
    else if(e.type === 'way' && e.geometry) push({type:'LineString', coordinates:line()}, {tip:`<b>Ligne ${info.type.toLowerCase()}</b>${name}${extra}`});
    return;
  }
  if(k === 'verts'){
    if(e.type === 'way' && e.geometry && e.geometry.length > 2){ const r = line(); if(r[0][0] !== r.at(-1)[0] || r[0][1] !== r.at(-1)[1]) r.push(r[0]);
      push({type:'Polygon', coordinates:[r]}, {tip:`<b>${info.type}</b>${name}`}); }
    return;
  }
  if(k === 'transports'){
    push(P(c[0], c[1]), {kind:'stop', col:info.color, big:info.type !== 'Arrêt de bus' ? 1 : 0, tip:`<b>${info.type}</b>${name || ' · Arrêt sans nom'}${t.route_ref ? '<br>Lignes : ' + esc(t.route_ref) : ''}`});
    return;
  }
  push(P(c[0], c[1]), {kind:'icon', ic:`poi|${LAYERS[k].color}|${info.icon}|0`, tip:`<b>${info.type}</b>${name}`});
}
