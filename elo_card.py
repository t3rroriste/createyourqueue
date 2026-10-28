"""
La carte de niveau affichée par /elo.
=====================================
Une image 1200 × 400, dessinée au trait près d'après la maquette : bandeau
coloré par le palier, avatar rond, pseudo, MMR en très gros, et un panneau
du bas qui porte la progression et la série.

Pourquoi une image et pas un embed : un embed dit la même chose en quatre
lignes grises que personne ne lit. Le MMR est ici le plus gros élément de
la carte — c'est lui qu'on lit sur un téléphone, où Discord réduit l'image
à moins de la moitié.

Le dessin est fait à chaque appel, jamais mis en cache : un MMR affiché
avec une seconde de retard est un MMR faux. Compter en millisecondes, donc
— aplats et dégradés droits, aucune ombre douce, aucun flou.

Si une police manque, `carte_disponible()` rend False et /elo garde son
embed d'origine. Une carte à moitié dessinée serait pire que pas de carte.
"""

from __future__ import annotations

import io
import math
import os
import unicodedata

try:
    from PIL import Image, ImageDraw, ImageFont
except ImportError:  # Pillow absent : le cog s'en passe proprement
    Image = ImageDraw = ImageFont = None


# --------------------------------------------------------------- les mesures
#
# Toutes en pixels, repère en haut à gauche. Elles viennent du découpage de
# la maquette : les changer ici les change partout.

LARGEUR, HAUTEUR = 1200, 400
RAYON_CARTE = 32

FOND = (18, 19, 23)             # #121317
PANNEAU = (27, 29, 34)          # #1B1D22
PISTE = (44, 47, 55)            # #2C2F37
FILET = (46, 49, 57)            # #2E3139
TEXTE = (244, 245, 247)         # #F4F5F7
TEXTE_DOUX = (154, 160, 171)    # #9AA0AB
TEXTE_CLAIR = (201, 205, 212)   # #C9CDD4
TEXTE_CLAN = (228, 230, 234)    # #E4E6EA
AVATAR_VIDE = (42, 45, 52)      # #2A2D34
FLAMME = (255, 181, 71)         # #FFB547

BANDEAU_H = 128
MARGE = 48
DROITE = LARGEUR - MARGE        # x de l'alignement à droite : 1152

AVATAR_DECOUPE = (40, 44, 184)  # x, y, diamètre du disque de fond
AVATAR = (48, 52, 168)          # x, y, diamètre de l'image

PANNEAU_Y, PANNEAU_H, PANNEAU_R = 264, 88, 20
PANNEAU_X = MARGE
PANNEAU_W = LARGEUR - 2 * MARGE

# Les sept paliers, dans l'ordre : nom interne, seuil, couleur.
# Ils doivent rester alignés sur DEFAULT_TIERS, dans mmr.py.
PALIERS = [
    ("bronze", 0, (205, 127, 50)),
    ("silver", 800, (192, 192, 192)),
    ("gold", 1000, (241, 196, 15)),
    ("platinum", 1200, (79, 195, 247)),
    ("diamond", 1400, (88, 101, 242)),
    ("champion", 1600, (155, 89, 182)),
    ("grand_champion", 1800, (231, 76, 60)),
]


# --------------------------------------------------------------- les polices
#
# Livrées avec le bot, dans assets/fonts/. Pillow ne sait pas enchaîner
# plusieurs polices tout seul : on choisit, graphème par graphème, la
# première dont la table de caractères contient le signe (voir `_segments`).

DOSSIER_POLICES = os.path.join(os.path.dirname(os.path.abspath(__file__)), "assets", "fonts")

_FICHIERS = {
    "sans_500": "Barlow-Medium.ttf",
    "sans_600": "Barlow-SemiBold.ttf",
    "sans_700": "Barlow-Bold.ttf",
    "etroite_700": "BarlowCondensed-Bold.ttf",
    # Noto n'est livré qu'en police VARIABLE : un seul fichier porte toutes
    # les graisses, qu'on choisit à l'ouverture. Deux fichiers statiques
    # auraient pesé plus lourd pour le même résultat.
    "kr_500": "NotoSansKR.ttf",
    "kr_700": "NotoSansKR.ttf",
    "emoji": "NotoEmoji.ttf",
}

# La graisse à demander aux polices variables, par clé.
_GRAISSES = {"kr_500": 500, "kr_700": 700, "emoji": 700}

_cache: dict[tuple[str, int], "ImageFont.FreeTypeFont"] = {}


def _chemin(cle: str) -> str:
    return os.path.join(DOSSIER_POLICES, _FICHIERS[cle])


def carte_disponible() -> bool:
    """Peut-on dessiner la carte ? Sinon /elo garde son embed.

    On exige Pillow et les trois polices latines. Le coréen et les emojis
    sont facultatifs : sans eux, un pseudo coréen perdra ses signes, pas la
    carte entière — et c'est un repli acceptable, pas une panne.
    """
    if Image is None:
        return False
    return all(os.path.isfile(_chemin(c)) for c in ("sans_500", "sans_600", "sans_700", "etroite_700"))


def _police(cle: str, taille: int):
    """Une police, gardée en mémoire : la relire à chaque texte coûterait
    plus cher que tout le reste du dessin réuni."""
    clef = (cle, taille)
    if clef not in _cache:
        chemin = _chemin(cle)
        if not os.path.isfile(chemin):
            return None
        police = ImageFont.truetype(chemin, taille)
        graisse = _GRAISSES.get(cle)
        if graisse is not None:
            # Police variable : sans ce réglage, elle sort en Regular, et le
            # pseudo coréen serait plus maigre que le pseudo latin à côté.
            try:
                police.set_variation_by_axes([graisse])
            except Exception:
                pass
        _cache[clef] = police
    return _cache[clef]


_absents: dict[object, bytes | None] = {}


def _absent(police):
    """Le dessin que cette police donne à un signe qu'elle n'a PAS.

    Un caractère absent sort en « carré d'absence » (.notdef), qui a de
    l'encre comme un vrai glyphe : chercher de l'encre ne distingue donc
    rien. On relève ici l'empreinte de ce carré, une fois par police, en
    demandant un caractère d'une zone à usage privé que personne ne dessine.
    """
    if police not in _absents:
        try:
            _absents[police] = police.getmask("").tobytes()
        except Exception:
            _absents[police] = None
    return _absents[police]


def _a_le_signe(police, signe: str) -> bool:
    """La police contient-elle ce caractère ?

    On compare au carré d'absence : s'ils se dessinent pareil, la police ne
    connaît pas le signe et il faut en essayer une autre. Sans ce test, un
    pseudo coréen sortait en file de carrés vides — la police latine
    acceptait de « dessiner » n'importe quoi.
    """
    if police is None:
        return False
    # Les espaces n'ont jamais d'encre : les prendre pour des signes
    # manquants les faisait disparaître, et les mots se collaient.
    if signe.isspace():
        return True
    try:
        masque = police.getmask(signe)
        if masque.getbbox() is None:
            return False
        vide = _absent(police)
        return vide is None or masque.tobytes() != vide
    except Exception:
        return False


def _ecriture(signe: str) -> str:
    """À quelle famille de police ce signe appartient-il ?

    Par plage Unicode, et non en interrogeant les polices : un caractère
    absent sort en carré d'absence, qui a de l'encre et une largeur comme
    un vrai glyphe. Toutes les ruses pour le détecter se trompent un jour —
    les plages, elles, ne bougent pas.
    """
    o = ord(signe)
    if (0x1100 <= o <= 0x11FF or 0x3130 <= o <= 0x318F or 0xA960 <= o <= 0xA97F
            or 0xAC00 <= o <= 0xD7FF):
        return "kr"                                   # hangul
    if (0x3040 <= o <= 0x30FF or 0x3400 <= o <= 0x4DBF or 0x4E00 <= o <= 0x9FFF
            or 0xF900 <= o <= 0xFAFF or 0xFF00 <= o <= 0xFF9F):
        return "kr"                                   # kana et idéogrammes
    if (0x1F000 <= o <= 0x1FAFF or 0x2600 <= o <= 0x27BF or 0x2B00 <= o <= 0x2BFF
            or 0xFE00 <= o <= 0xFE0F or 0x1F1E6 <= o <= 0x1F1FF):
        return "emoji"
    return "latin"


def _segments(texte: str, taille: int, graisse: str) -> list[tuple[str, object]]:
    """Découpe un texte en morceaux, chacun avec la police qui sait l'écrire.

    Pillow n'enchaîne pas les polices tout seul : sans ce découpage, un
    pseudo coréen sortirait en file de carrés vides, dessinés par la police
    latine qui accepte n'importe quoi.
    """
    latine = {"500": "sans_500", "600": "sans_600", "700": "sans_700",
              "etroite": "etroite_700"}[graisse]
    coreenne = "kr_700" if graisse in ("700", "etroite") else "kr_500"
    familles = {"latin": latine, "kr": coreenne, "emoji": "emoji"}

    # Si un fichier manque, on se rabat sur une autre graisse latine plutôt
    # que de perdre le texte : une carte dont le MMR a disparu parce qu'une
    # police n'a pas été livrée serait incompréhensible.
    replis = [latine, "sans_700", "sans_600", "sans_500"]

    morceaux: list[tuple[str, object]] = []
    for signe in texte:
        cle = familles[_ecriture(signe)]
        choisie = _police(cle, taille)
        if choisie is None:
            for secours in replis:
                p = _police(secours, taille)
                if p is not None and _a_le_signe(p, signe):
                    choisie = p
                    break
        if choisie is None:
            # Introuvable partout : on le retire. Un carré vide au milieu
            # d'un pseudo est pire que son absence.
            continue
        if morceaux and morceaux[-1][1] is choisie:
            morceaux[-1] = (morceaux[-1][0] + signe, choisie)
        else:
            morceaux.append((signe, choisie))
    return morceaux


def _largeur(morceaux) -> int:
    return sum(int(p.getlength(bout)) for bout, p in morceaux)


def _ecrire(dessin, xy, texte: str, taille: int, graisse: str, couleur,
            ancre_droite=False, ligne: int | None = None) -> int:
    """Écrit un texte, police par police, et rend sa largeur.

    `xy` est le coin haut-gauche — ou haut-droit si `ancre_droite`. On ne se
    sert pas des ancres de Pillow : elles ne valent que pour un seul appel,
    et un texte mélangeant deux polices en demande plusieurs.
    """
    morceaux = _segments(texte, taille, graisse)
    if not morceaux:
        return 0
    x, y = xy
    if ancre_droite:
        x -= _largeur(morceaux)
    if ligne is not None:
        # Pillow pose un texte par le haut de ses jambages, qui dépend de la
        # police ; la maquette, elle, raisonne en lignes. Sans cette
        # conversion, un nombre de 128 px posé à 128 px débordait de 40 px
        # sur ce qui le suit.
        montee, descente = morceaux[0][1].getmetrics()
        y += (ligne - (montee + descente)) // 2
    depart = x
    for bout, police in morceaux:
        dessin.text((x, y), bout, font=police, fill=couleur)
        x += int(police.getlength(bout))
    return x - depart


# ------------------------------------------------------------- les couleurs

def _melange(a, b, f: float):
    """a vers b, f entre 0 et 1."""
    return tuple(round(a[i] + (b[i] - a[i]) * f) for i in range(3))


def _luminance(c) -> float:
    def canal(v):
        v = v / 255
        return v / 12.92 if v <= 0.03928 else ((v + 0.055) / 1.055) ** 2.4
    r, v, b = (canal(x) for x in c)
    return 0.2126 * r + 0.7152 * v + 0.0722 * b


def _contraste(a, b) -> float:
    x, y = _luminance(a), _luminance(b)
    return (max(x, y) + 0.05) / (min(x, y) + 0.05)


def _encre_du_bandeau(couleur) -> tuple:
    """Blanc ou presque noir, selon ce qui se lit sur le bandeau.

    On teste la partie DROITE du dégradé (x 850 à 1200), où se posent le nom
    du palier et les repères : c'est là que la couleur est la plus franche,
    donc là que le blanc risque de disparaître. Un palier clair comme
    l'argent bascule ainsi en encre sombre.
    """
    au_texte = _melange(couleur, FOND, 0.55 * (1 - 850 / 1200))
    blanc_ok = min(_contraste((255, 255, 255), couleur),
                   _contraste((255, 255, 255), au_texte)) >= 3.5
    return (255, 255, 255) if blanc_ok else (14, 15, 18)


# ------------------------------------------------------------ les nombres

_SEPARATEURS = {"fr": " ", "de": ".", "en": ",", "ko": ",", "es": " "}


def _nombre(n: int, langue: str) -> str:
    """1480 devient « 1 480 » en français, « 1,480 » en anglais.

    L'espace est INSÉCABLE : un nombre ne se coupe pas en deux. On prend
    l'insécable ordinaire plutôt que la fine, pourtant plus juste en
    typographie française — la fine manque à beaucoup de polices et sort
    alors en carré vide, ce qui est bien pire qu'une espace un peu large.
    """
    s = str(n)
    if langue == "es" and len(s) <= 4:
        return s               # l'espagnol ne sépare pas les milliers à 4 chiffres
    sep = _SEPARATEURS.get(langue, " ")
    morceaux = []
    while len(s) > 3:
        morceaux.insert(0, s[-3:])
        s = s[:-3]
    morceaux.insert(0, s)
    return sep.join(morceaux)


# ---------------------------------------------------------------- le dessin

def _disque(dessin, x, y, d, couleur):
    dessin.ellipse([x, y, x + d - 1, y + d - 1], fill=couleur)


def _bandeau(image, couleur):
    """Le dégradé horizontal, colonne par colonne.

    1200 lignes verticales plutôt qu'un dégradé tout fait : Pillow n'en a
    pas, et une image redimensionnée coûterait plus cher que cette boucle.
    """
    bande = Image.new("RGB", (LARGEUR, 1))
    pixels = bande.load()
    for x in range(LARGEUR):
        pixels[x, 0] = _melange(couleur, FOND, 0.55 * (1 - x / LARGEUR))
    image.paste(bande.resize((LARGEUR, BANDEAU_H), Image.NEAREST), (0, 0))


def _coins_arrondis(image, rayon):
    """Le masque est appliqué EN DERNIER : dessiner sur une image déjà
    masquée laisserait des angles vifs sous les éléments posés après."""
    masque = Image.new("L", (LARGEUR * 2, HAUTEUR * 2), 0)
    ImageDraw.Draw(masque).rounded_rectangle(
        [0, 0, LARGEUR * 2 - 1, HAUTEUR * 2 - 1], radius=rayon * 2, fill=255)
    masque = masque.resize((LARGEUR, HAUTEUR), Image.LANCZOS)
    sortie = Image.new("RGBA", (LARGEUR, HAUTEUR), (0, 0, 0, 0))
    sortie.paste(image, (0, 0), masque)
    return sortie


def _avatar(image, octets: bytes | None, initiale: str):
    """L'avatar, découpé en rond. Tracé à 2× puis réduit : un cercle tracé
    directement à 168 px a l'escalier visible sur son bord."""
    x, y, d = AVATAR
    _disque(ImageDraw.Draw(image), *AVATAR_DECOUPE[:2], AVATAR_DECOUPE[2], FOND)

    if octets:
        try:
            photo = Image.open(io.BytesIO(octets)).convert("RGB").resize((d, d), Image.LANCZOS)
            masque = Image.new("L", (d * 2, d * 2), 0)
            ImageDraw.Draw(masque).ellipse([0, 0, d * 2 - 1, d * 2 - 1], fill=255)
            image.paste(photo, (x, y), masque.resize((d, d), Image.LANCZOS))
            return
        except Exception:
            pass          # avatar illisible : on retombe sur l'initiale

    _disque(ImageDraw.Draw(image), x, y, d, AVATAR_VIDE)
    dessin = ImageDraw.Draw(image)
    morceaux = _segments(initiale.upper(), 72, "700")
    largeur = _largeur(morceaux)
    _ecrire(dessin, (x + (d - largeur) // 2, y + 44), initiale.upper(), 72, "700", TEXTE_CLAIR)


def _couper(texte: str, taille: int, graisse: str, largeur_max: int) -> str:
    """Raccourcit un texte jusqu'à tenir dans sa boîte, « … » compris.

    Les pseudos Discord vont jusqu'à 32 caractères, emojis compris : même
    réduit à 44 px, un pseudo à rallonge dépasse sa boîte de 520 px et vient
    écrire par-dessus le MMR. On coupe donc, plutôt que de laisser deux
    textes se marcher dessus.
    """
    if _largeur(_segments(texte, taille, graisse)) <= largeur_max:
        return texte
    signes = list(texte)
    while signes:
        signes.pop()
        essai = "".join(signes).rstrip() + "…"
        if _largeur(_segments(essai, taille, graisse)) <= largeur_max:
            return essai
    return "…"


def _taille_du_pseudo(pseudo: str) -> int:
    """60, 52 ou 44 px selon l'encombrement réel du pseudo.

    Un idéogramme occupe environ 1,7 fois la largeur d'une lettre latine :
    compter les caractères ferait déborder « 한국어플레이어 » et rétrécirait
    « Nova » pour rien.
    """
    poids = 0.0
    for signe in pseudo:
        est_large = unicodedata.east_asian_width(signe) in ("W", "F")
        poids += 1.7 if est_large else 1.0
    if poids <= 13:
        return 60
    return 52 if poids <= 16 else 44


def dessiner(
    *,
    pseudo: str,
    mmr: int,
    palier_index: int,
    paliers: list | None = None,
    victoires: int = 0,
    defaites: int = 0,
    serie: int = 0,
    record: int = 0,
    clan: str = "",
    avatar: bytes | None = None,
    langue: str = "fr",
    textes: dict | None = None,
) -> bytes:
    """Rend la carte en PNG.

    `paliers` est la liste du serveur : (nom affiché, seuil, couleur RVB).
    Un serveur peut en avoir d'autres que ceux d'origine — on ne les
    recalcule donc jamais ici, on les reçoit. Sans liste, ceux d'origine.
    `palier_index` est le rang atteint dans cette liste.
    `textes` porte les libellés traduits ; sans lui, le français.
    """
    T = dict(_TEXTES_FR, **(textes or {}))
    echelle = paliers or [(T.get("tier_%s" % cle, cle), seuil, couleur)
                          for cle, seuil, couleur in PALIERS]
    langue = langue if langue in _SEPARATEURS else "fr"

    palier_index = max(0, min(len(echelle) - 1, palier_index))
    nom_palier, seuil, couleur = echelle[palier_index]
    suivant = echelle[palier_index + 1] if palier_index + 1 < len(echelle) else None

    image = Image.new("RGB", (LARGEUR, HAUTEUR), FOND)
    dessin = ImageDraw.Draw(image)

    # A — le bandeau, seul élément coloré par le palier
    _bandeau(image, couleur)
    encre = _encre_du_bandeau(couleur)

    # C — le nom du palier, en capitales, aligné à droite
    _ecrire(dessin, (DROITE, 22), nom_palier.upper(),
            44, "etroite", encre, ancre_droite=True, ligne=48)

    # D — un repère par palier, pleins jusqu'à celui atteint
    combien = len(echelle)
    x = DROITE - (combien * 24 + (combien - 1) * 6)
    for i in range(combien):
        plein = i <= palier_index
        teinte = encre if plein else _melange(encre, couleur, 0.72)
        dessin.rounded_rectangle([x, 84, x + 23, 91], radius=2, fill=teinte)
        x += 30

    # B — l'avatar
    _avatar(image, avatar, (pseudo or "?")[:1])

    # G — le MMR d'abord, bien qu'il s'affiche à droite : c'est lui qui
    # décide de la place qui reste au pseudo. Un MMR à quatre chiffres
    # mange 40 px de plus qu'à trois, et le pseudo doit s'arrêter avant.
    nombre = _nombre(mmr, langue)
    largeur_nombre = _ecrire(dessin, (DROITE, BANDEAU_H), nombre, 128, "etroite", TEXTE,
                             ancre_droite=True, ligne=128)
    # Le libellé s'assoit près de la ligne de base du nombre : il
    # l'accompagne, il ne flotte pas à côté.
    largeur_mmr = _ecrire(dessin, (DROITE - largeur_nombre - 14, BANDEAU_H + 58), "MMR", 26,
                          "600", TEXTE_DOUX, ancre_droite=True, ligne=32)

    # E — le pseudo. Sa boîte vaut 520 px dans la maquette, moins si le MMR
    # est venu plus à gauche : deux textes qui se chevauchent sont pires
    # qu'un pseudo coupé.
    boite = min(520, DROITE - largeur_nombre - 14 - largeur_mmr - 16 - 240)
    taille = _taille_du_pseudo(pseudo)
    _ecrire(dessin, (240, 142), _couper(pseudo, taille, "700", boite), taille, "700", TEXTE, ligne=72)

    # F — le sous-titre : clan, puis bilan
    x = 240
    if clan.strip():
        x += _ecrire(dessin, (x, 216), clan.strip(), 26, "600", TEXTE_CLAN, ligne=34)
        x += _ecrire(dessin, (x, 216), "  ·  ", 26, "500", TEXTE_DOUX, ligne=34)
    if victoires + defaites > 0:
        bilan = ("%d%s %d%s" % (victoires, T["w"], defaites, T["l"]) if langue == "ko"
                 else "%d %s – %d %s" % (victoires, T["w"], defaites, T["l"]))
    else:
        bilan = T["none"]
    _ecrire(dessin, (x, 216), bilan, 26, "500", TEXTE_DOUX, ligne=34)

    # H — le panneau du bas
    dessin.rounded_rectangle(
        [PANNEAU_X, PANNEAU_Y, PANNEAU_X + PANNEAU_W - 1, PANNEAU_Y + PANNEAU_H - 1],
        radius=PANNEAU_R, fill=PANNEAU)

    a_serie = serie > 0 or record > 0
    largeur_gauche = 660 if a_serie else 1048

    # I — la progression, ou le palier maximal
    if suivant is not None:
        reste = max(0, suivant[1] - mmr)
        total = max(1, suivant[1] - seuil)
        part = max(0.0, min(1.0, (mmr - seuil) / total))

        droite_x = PANNEAU_X + 28 + largeur_gauche
        pct = ("%d%%" if langue in ("en", "ko") else "%d %%") % round(part * 100)
        largeur_pct = _ecrire(dessin, (droite_x, 280), pct, 26, "500", TEXTE_DOUX,
                              ancre_droite=True, ligne=32)
        _ecrire(dessin, (droite_x - largeur_pct - 10, 280),
                _nombre(reste, langue) + T["pts"], 26, "600", TEXTE, ancre_droite=True, ligne=32)

        x = PANNEAU_X + 28
        x += _ecrire(dessin, (x, 280), T["next"], 26, "500", TEXTE_DOUX, ligne=32)
        _ecrire(dessin, (x + 10, 280), suivant[0], 26, "600", TEXTE, ligne=32)

        dessin.rounded_rectangle([PANNEAU_X + 28, 324, PANNEAU_X + 28 + largeur_gauche, 335],
                                 radius=6, fill=PISTE)
        if part > 0:
            rempli = max(12, int(largeur_gauche * part))
            dessin.rounded_rectangle([PANNEAU_X + 28, 324, PANNEAU_X + 28 + rempli, 335],
                                     radius=6, fill=TEXTE)
    else:
        _ecrire(dessin, (PANNEAU_X + 28, 278), T["top"], 26, "600", TEXTE, ligne=32)
        _ecrire(dessin, (PANNEAU_X + 28, 312),
                _nombre(mmr - seuil, langue) + T["pts"] + " " + T["above"], 26, "500",
                TEXTE_DOUX, ligne=32)

    # J — la série, à droite du filet
    if a_serie:
        filet_x = PANNEAU_X + 28 + largeur_gauche + 28
        dessin.line([filet_x, PANNEAU_Y + 8, filet_x, PANNEAU_Y + PANNEAU_H - 9], fill=FILET)
        x = filet_x + 28
        if serie > 0:
            haut = 282 if record > 0 else 292
            _flamme(dessin, x, haut + 7)
            largeur = _ecrire(dessin, (x + 36, haut), _nombre(serie, langue), 40, "etroite",
                              TEXTE, ligne=40)
            _ecrire(dessin, (x + 36 + largeur + (2 if langue == "ko" else 10), haut),
                    T["s1"] if serie == 1 else T["sN"], 26, "500", TEXTE_CLAIR, ligne=40)
            if record > 0:
                _ecrire(dessin, (x + 36, haut + 42),
                        "%s  %s" % (T["record"], _nombre(record, langue)), 24, "500",
                        TEXTE_DOUX, ligne=30)
        else:
            largeur = _ecrire(dessin, (x, 288), T["record"], 26, "500", TEXTE_DOUX, ligne=40)
            _ecrire(dessin, (x + largeur + 12, 288), _nombre(record, langue), 40, "etroite",
                    TEXTE, ligne=40)

    sortie = io.BytesIO()
    _coins_arrondis(image, RAYON_CARTE).save(sortie, format="PNG", optimize=False)
    return sortie.getvalue()


def _flamme(dessin, x: int, y: int):
    """La flamme de la série, tracée à la main : une icône de plus à livrer
    serait un fichier de plus à perdre."""
    points = [
        (x + 13, y), (x + 17, y + 7), (x + 21, y + 13), (x + 22, y + 19),
        (x + 20, y + 24), (x + 13, y + 26), (x + 6, y + 24), (x + 4, y + 18),
        (x + 6, y + 11), (x + 10, y + 7),
    ]
    dessin.polygon(points, fill=FLAMME)
    dessin.polygon([(x + 13, y + 10), (x + 17, y + 17), (x + 13, y + 22), (x + 9, y + 17)], fill=FOND)


# Les libellés par défaut. Le cog passe ceux de la langue du serveur ; ceux-ci
# servent de repli et disent, par leur seule présence, ce que `textes` attend.
_TEXTES_FR = {
    "next": "Prochain palier",
    "pts": " pts",
    "w": "V",
    "l": "D",
    "s1": "victoire d’affilée",
    "sN": "victoires d’affilée",
    "record": "Record",
    "top": "Palier maximal atteint",
    "above": "au-dessus du seuil",
    "none": "Aucun match joué",
    "tier_bronze": "Bronze",
    "tier_silver": "Argent",
    "tier_gold": "Or",
    "tier_platinum": "Platine",
    "tier_diamond": "Diamant",
    "tier_champion": "Champion",
    "tier_grand_champion": "Grand Champion",
}
