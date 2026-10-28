# Prompt pour Claude Design — la carte `/elo`

> À coller tel quel. Tout ce qui suit s'adresse à Claude Design.

---

## 0. Ce qu'on demande

Dessiner **la carte de niveau d'un joueur**, affichée par la commande
`/elo` du bot Discord CreateYourQueue. Aujourd'hui, `/elo` répond par un
embed Discord ordinaire : un titre, une ligne de palier, deux champs. On
veut à la place **une image**, large et lisible, de la famille de celle-ci
— une bannière horizontale, un dégradé en haut, l'avatar rond qui chevauche
la bordure, le pseudo en très gros, et une barre d'informations en bas :

```
┌──────────────────────────────────────────────────────────┐
│  ░░ dégradé ░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░  │
│    ╭────╮                                                │
│    │ 🧑 │   @pseudo                                       │
│    ╰────╯   sous-titre                                    │
│                                                           │
│  ┌────────────────────────────────────────────────────┐  │
│  │ [ÉTIQUETTE]  texte                      265        │  │
│  │                                         légende    │  │
│  └────────────────────────────────────────────────────┘  │
└──────────────────────────────────────────────────────────┘
```

**Mais ce n'est qu'un point de départ de composition, pas un modèle à
copier.** Cette carte-là annonce un mot ; la nôtre annonce un niveau, une
progression et une série. Le contenu est différent, donc la hiérarchie
doit l'être aussi.

---

## 1. Ce que la carte doit porter

Toutes ces valeurs existent déjà dans le bot. Aucune n'est à inventer, et
aucune autre n'est disponible.

### Toujours présent

| Donnée | Exemple | D'où elle vient |
|---|---|---|
| Pseudo affiché sur le serveur | `Nova` | Discord |
| Avatar | rond, 256 px | Discord |
| **Points de MMR** | `1 480` | `get_player_mmr()` |
| **Palier actuel** | `Diamant`, icône `🔷`, couleur `#5865F2` | `mmr.tier_for()` |
| **Palier suivant et ce qui en sépare** | `Champion — 120 points` | `mmr.next_tier()` |
| **Progression dans le palier** | `62 %` | `mmr.progress()` rend (fait, total) |
| Victoires / défaites | `34 / 19` | stats du classement |

### Présent seulement parfois — et c'est le cœur du travail

| Donnée | Quand elle existe | Exemple |
|---|---|---|
| **Série en cours** | `streak > 0` | `5 victoires d'affilée` |
| **Meilleure série** | `max_streak > 0` | `record : 9` |
| **Clan** | le joueur est dans un clan | `Alpha` |
| **Palier maximal atteint** | aucun palier au-dessus | « sommet » |

**Dessine ces états, ne les suppose pas.** Il me faut, explicitement :

1. un joueur **sans clan** et **sans série** — le cas le plus courant ;
2. un joueur **avec clan et série** — la carte pleine ;
3. un joueur **au palier le plus bas**, à 0 point, progression nulle ;
4. un joueur **au palier maximal**, où « palier suivant » n'a plus de sens.

Une mise en page qui ne tient que dans le cas 2 ne sert à rien : c'est le
cas 1 qui s'affichera le plus souvent.

---

## 2. Les sept paliers, avec leurs couleurs

Ce sont celles du bot, à l'identique (`mmr.py`, `DEFAULT_TIERS`) :

| Palier | Seuil | Couleur | Icône |
|---|---|---|---|
| Bronze | 0 | `#CD7F32` | 🥉 |
| Argent | 800 | `#C0C0C0` | 🥈 |
| Or | 1000 | `#F1C40F` | 🥇 |
| Platine | 1200 | `#4FC3F7` | 💎 |
| Diamant | 1400 | `#5865F2` | 🔷 |
| Champion | 1600 | `#9B59B6` | 👑 |
| Grand Champion | 1800 | `#E74C3C` | 🏆 |

**La carte doit changer de peau selon le palier** — c'est ce qui donne
envie de monter. Le dégradé du haut, et lui seul, porte la couleur du
palier. Le reste de la carte reste sombre et stable : sept cartes qui
changeraient entièrement de couleur deviendraient sept designs à tenir.

Montre-moi **au moins trois paliers** rendus, dont un clair (Argent) et un
sombre (Diamant), pour qu'on voie que le texte reste lisible sur les deux.

---

## 3. Les contraintes qui tiennent

- **Format** : image horizontale, **1200 × 400 px** (comme le modèle), à
  rendre lisible **réduite à 550 px de large** — c'est la largeur réelle
  d'une image dans Discord sur un écran d'ordinateur. Tout ce qui n'est
  pas lisible à cette taille est à grossir ou à retirer.
- **Sur téléphone**, Discord réduit encore. Le pseudo, les points et le
  palier doivent rester lisibles ; le reste peut s'effacer.
- **Fond sombre**, comme le modèle : la carte s'affiche dans Discord, qui
  est sombre chez la grande majorité des gens.
- **Les pseudos Discord sont imprévisibles** : 32 caractères possibles,
  emojis compris, et des alphabets non latins. Dis ce qui se passe à
  `@Xx_LeSuperPseudoTresLong_xX` — rétrécissement, coupe, passage à la
  ligne — et dessine-le.
- **Aucune donnée inventée.** Pas de « rang mondial », pas de graphique
  d'évolution, pas de pourcentage de victoires sur 30 jours : rien de tout
  cela n'existe dans le bot. Si tu penses qu'une de ces valeurs manque,
  dis-le dans ta note plutôt que de la dessiner.
- **Les cinq langues** : français, anglais, espagnol, allemand, coréen.
  L'allemand est long (« Nächste Stufe »), le coréen change de hauteur de
  ligne. Aucune étiquette ne doit être calibrée au caractère près sur le
  français.

---

## 4. Ce qu'il faut livrer

1. **Les quatre états** de la section 1, et **trois paliers** de la
   section 2, rendus.
2. **Le découpage précis** : positions, tailles, graisses, couleurs. C'est
   un programme qui dessinera cette carte, pas un humain dans un éditeur —
   il lui faut des nombres.
3. **Les polices**, avec leur solution de repli. Le bot tourne sur un
   serveur Linux sans polices installées : toute police doit être livrée
   en fichier, ou remplacée par une pile système.
4. **Une note courte** sur ce que tu as écarté et pourquoi.

---

## 5. Une question technique à trancher, et elle change le dessin

Une image dans Discord **ne se met pas à jour toute seule**. Deux chemins,
et ils n'imposent pas les mêmes contraintes :

- **Rendu à la demande** : la carte est fabriquée à chaque `/elo`, donc
  toujours juste. Elle doit se fabriquer en moins d'une seconde, sinon la
  commande expire. Favorise un dessin simple : aplats, dégradés droits,
  pas d'ombres portées douces ni de flou.
- **Rendu puis message modifié** : le bot garde le message et le refait
  quand le MMR, la série ou le clan changent. Plus souple pour le dessin,
  mais ça multiplie les images à stocker et les modifications de messages.

**Dessine pour le premier cas** — la contrainte est plus dure, et un dessin
qui la respecte marche aussi dans le second. Dis dans ta note ce que tu
ferais de plus si on choisissait le second.
