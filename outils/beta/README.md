# Page de test `site/beta.html`

Version de la carte sous MapLibre (rendu par la carte graphique), avec thème sombre,
panneau « Mes villes » et bascule vers la carte des transports (`site/transports.html`, gardée telle quelle).

Elle est fabriquée à partir de `site/index.html` : après toute modification de la carte actuelle,
relancer

    python3 outils/beta/build.py site/index.html site/beta.html

Le script s'arrête avec un message si un passage de `index.html` qu'il remplace a changé.
Quand la version de test sera validée, `beta.html` remplacera `index.html` et ce dossier disparaîtra.

Sauvegardes (demandées par Oré le 23/11/2026) : `site/sauvegarde-carte-immo.html` (carte telle qu'avant la refonte)
et `site/sauvegarde-transports.html` (carte des transports d'origine), consultables en ligne au même endroit.
