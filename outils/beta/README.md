# Carte MapLibre : comment elle a été fabriquée

Depuis le 24/11/2026, **`site/index.html` est la carte MapLibre** (thème sombre, panneau « Mes villes »,
bascule vers la carte des transports `site/transports.html`). On la modifie désormais **directement** :
plus de Leaflet (`L.*`), `map.getZoom()` = zoom Leaflet − 1 (voir `zL()`), annonces, zones et points
d'intérêt dessinés par des couches GeoJSON (`setSrc`, `vis`).

Elle a été générée une dernière fois par

    python3 outils/beta/build.py site/sauvegarde-carte-leaflet.html site/index.html

à partir de la dernière carte Leaflet, gardée en sauvegarde dans `site/sauvegarde-carte-leaflet.html`.
Ce script et ce dossier ne servent plus que de trace ; `site/beta.html` (même carte, titre « test »)
sera supprimée quand Oré aura validé la nouvelle carte principale.

Sauvegardes (ne jamais modifier) : `site/sauvegarde-carte-leaflet.html` (carte Leaflet du 24/11, juste avant la bascule),
`site/sauvegarde-carte-immo.html` (carte du 23/11, avant la refonte) et `site/sauvegarde-transports.html`
(carte des transports d'origine).
