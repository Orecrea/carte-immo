# Carte immo

Carte personnelle des maisons à vendre dans les villes choisies, avec temps de trajet, transports et favoris.

- `site/index.html` : la carte (publiée par GitHub Pages).
- `collecte/` : collecte automatique des annonces (Bien'ici, Espaces Atypiques), lancée matin et soir
  pendant un mois après chaque clic sur « Actualiser » dans la carte.
- `collecte/multi.py` : recherche hebdomadaire (lundi matin) des biens à deux logements à moins d'1 h de Paris,
  dans des communes équipées ; résultat dans l'onglet « Multi-logements » (`site/multi.enc`). Relance possible
  avec « Run workflow » sur l'action « Recherche multi-logements » (option « rapide » : sans relire les sites).
- Les annonces et les villes suivies sont **chiffrées** (`site/annonces.enc`, `etat/etat.enc`) :
  elles ne sont lisibles qu'avec le mot de passe de la carte, enregistré dans le secret `CLE_CARTE`.

Règles de collecte : maisons uniquement, 800 000 € maximum, pas de viager ni de « maison à construire »,
annonces mal localisées écartées, doublons regroupés (l'annonce la moins chère est gardée).
Les sites qui refusent la collecte automatique (Leboncoin, SeLoger, PAP…) ne sont pas interrogés :
la carte propose un lien direct vers leur recherche pour chaque ville.
