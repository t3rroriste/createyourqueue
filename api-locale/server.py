#!/usr/bin/env python3
"""
CreateYourQueue — API de connexion Discord.

Ce serveur fait deux choses :
  1. il sert le site statique (le dossier « site » voisin)
  2. il expose /api/* sur la MÊME origine, auth comprise

Le point 1 n'est pas un confort. Un cookie de session posé par une autre
origine que celle du site est un cookie tiers : Safari le refuse par défaut,
Chrome s'y met, et il faudrait SameSite=None + HTTPS pour y échapper. Tout
servir depuis une seule origine supprime le problème au lieu de le contourner.

Aucune dépendance : bibliothèque standard uniquement. `python server.py`.

Rien de secret ne sort d'ici. Le CLIENT_SECRET sert à l'échange du code côté
serveur, le jeton Discord reste en mémoire, et le navigateur ne reçoit qu'un
identifiant de session opaque.
"""

import hmac
import json
import mimetypes
import os
import secrets
import sys
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

RACINE = Path(__file__).resolve().parent
DOSSIER_DATA = RACINE / "data"
FICHIER_REGLAGES = DOSSIER_DATA / "guilds.json"

# Pour essayer le bandeau « Le bot ne répond pas » sans éteindre quoi que ce
# soit : CYQ_BOT_OFF=1 avant de lancer le serveur. Le réglage n'existe QUE
# dans cette API de développement ; le PHP, lui, constate.
BOT_ETEINT = os.environ.get("CYQ_BOT_OFF") == "1"

API = "https://discord.com/api/v10"
MANAGE_GUILD = 1 << 5
DUREE_SESSION = 7 * 24 * 3600
DUREE_STATE = 10 * 60


# =============================== configuration ===============================

def charger_env() -> None:
    """Lit .env s'il existe. Les vraies variables d'environnement gagnent."""
    chemin = RACINE / ".env"
    if not chemin.exists():
        return
    for ligne in chemin.read_text(encoding="utf-8").splitlines():
        ligne = ligne.strip()
        if not ligne or ligne.startswith("#") or "=" not in ligne:
            continue
        cle, _, val = ligne.partition("=")
        cle, val = cle.strip(), val.strip().strip('"').strip("'")
        os.environ.setdefault(cle, val)


charger_env()

CLIENT_ID = os.environ.get("DISCORD_CLIENT_ID", "")
CLIENT_SECRET = os.environ.get("DISCORD_CLIENT_SECRET", "")
BOT_TOKEN = os.environ.get("DISCORD_BOT_TOKEN", "")
PORT = int(os.environ.get("PORT", "3000"))
PUBLIC_URL = os.environ.get("PUBLIC_URL", "").rstrip("/")
PROD = os.environ.get("ENV", "").lower() == "production"
# Somme des bits Discord demandés quand le bot rejoint un serveur. Doit
# rester alignée sur INVITE_PERMISSIONS dans site/assets/js/config.js.
INVITE_PERMISSIONS = os.environ.get("INVITE_PERMISSIONS", "1099780064336")

# ------------------------------- le bot ------------------------------------
#
# Ouvrir une queue n'est PAS une écriture de réglage : c'est une action qui
# vit dans le bot — des boutons qui répondent, des équipes qui se composent,
# un salon vocal, un état qui dure. Ce serveur ne sait pas faire ça et ne
# doit pas essayer : il relaie la demande au bot et rapporte sa réponse.
#
# Le bot ouvre déjà une API pour ce panneau (cogs/dashboard_api.py) : elle
# écoute sur DASHBOARD_API_HOST:DASHBOARD_API_PORT et contrôle chaque requête
# par l'en-tête X-API-Key. C'est elle qu'on appelle, pas Discord.
#
#   BOT_API_BASE    racine de cette API, par exemple http://127.0.0.1:8080
#   BOT_API_KEY     la DASHBOARD_API_KEY du bot, à l'identique
#
# Sans BOT_API_BASE, la route répond 503 et le panneau le dit : aucune
# action n'est jamais inventée côté site.
BOT_API_BASE = os.environ.get("BOT_API_BASE", "").rstrip("/")
BOT_API_KEY = os.environ.get("BOT_API_KEY", "")
BOT_API_TIMEOUT = float(os.environ.get("BOT_API_TIMEOUT", "10"))

# ----------------------------- les deux origines -----------------------------
#
# En local, ce serveur sert le site ET l'API : une seule origine, rien à
# déclarer. En ligne, le site est sur LWS (qui ne fait tourner que des
# fichiers) et l'API ailleurs : deux origines, et deux conséquences.
#
#   APP_URL         où renvoyer le navigateur à la fin de la connexion.
#                   Vide = même origine, donc des chemins relatifs.
#                   Exemple : https://dashboard.cyqbot.eu
#
#   ALLOWED_ORIGINS qui a le droit d'appeler /api depuis une autre origine.
#                   Liste séparée par des virgules, comparée au caractère
#                   près : une origine non listée n'obtient aucun en-tête
#                   CORS, donc le navigateur refuse la réponse.
#
# À savoir sur le cookie de session : api.cyqbot.eu et dashboard.cyqbot.eu
# sont deux ORIGINES différentes mais un seul SITE — même domaine
# enregistrable. `SameSite=Lax` suffit donc, et le cookie n'est pas un
# cookie tiers. C'est tout l'intérêt de mettre l'API sur un sous-domaine
# plutôt que sur un domaine à part : avec api.autrechose.com, il faudrait
# `SameSite=None`, que Safari et les navigateurs stricts jettent.
APP_URL = os.environ.get("APP_URL", "").rstrip("/")
ORIGINES = [o.strip().rstrip("/") for o in
            os.environ.get("ALLOWED_ORIGINS", "").split(",") if o.strip()]


def _dossier_site() -> Path:
    """Le dossier servi comme racine web.

    `SITE_DIR` l'emporte si elle est posée — utile pour servir un
    instantané d'archive et comparer. Sinon c'est `site/`, le dossier
    voisin : depuis la réunion des deux dépôts, il n'y a plus qu'une seule
    copie du site, et c'est exactement celle qui part sur LWS. Il n'y a donc
    plus d'écart possible entre ce qu'on développe et ce qu'on publie.
    """
    choix = os.environ.get("SITE_DIR", "").strip()
    if choix:
        return Path(choix).expanduser().resolve()
    return (RACINE.parent / "site").resolve()


SITE = _dossier_site()


def _prefixe_app() -> str:
    """Où vivent login.html, servers.html et dashboard.html, vu du navigateur.

    Le site est scindé : la vitrine à la racine, le panneau dans un dossier
    qui porte le nom de son sous-domaine. Les redirections de fin de
    connexion doivent viser le bon endroit — et continuer de marcher sur une
    arborescence à plat, où tout est à la racine. On le déduit du disque
    plutôt que de le supposer.
    """
    if APP_URL:
        # L'application est servie par un autre hôte (LWS) : on y renvoie en
        # absolu, puisqu'un chemin relatif resterait sur l'API.
        return APP_URL + "/"
    for candidat in ("dashboard.cyqbot.eu", ""):
        if (SITE / candidat / "login.html").is_file():
            return "/" + (candidat + "/" if candidat else "")
    return "/"


APP = _prefixe_app()


def base_url() -> str:
    return PUBLIC_URL or f"http://localhost:{PORT}"


def redirect_uri() -> str:
    return base_url() + "/api/auth/callback"


# ================================= sessions ==================================

# En mémoire, volontairement. Un redémarrage déconnecte tout le monde, ce qui
# est acceptable pour une préversion fermée et évite de poser une base de
# données avant d'en avoir besoin. Voir le README pour la suite.
_sessions: dict[str, dict] = {}
_verrou = threading.Lock()


def creer_session(donnees: dict) -> str:
    sid = secrets.token_urlsafe(32)
    with _verrou:
        _sessions[sid] = {**donnees, "expire": time.time() + DUREE_SESSION}
    return sid


def lire_session(sid: str | None) -> dict | None:
    if not sid:
        return None
    with _verrou:
        s = _sessions.get(sid)
        if not s:
            return None
        if s["expire"] < time.time():
            del _sessions[sid]
            return None
        return s


# Combien de temps la liste des serveurs reste valable. Même valeur que
# CACHE_GUILDES dans site/api/index.php : les deux implémentations doivent
# se tromper de la même façon, sinon ce qu'on corrige ici ne se voit pas là.
CACHE_GUILDES = 30


def mes_guildes(s: dict) -> tuple[list | None, tuple[int, dict] | None]:
    """La liste des serveurs de la personne, gardée quelques secondes.

    Rend (liste, None) ou (None, (code, charge)) — à l'appelant de servir
    l'erreur, parce que lui seul sait s'il répond à /guilds ou à une route
    de guilde.

    POURQUOI CE CACHE. Presque toutes les routes commencent par demander
    cette liste à Discord, et ouvrir le panneau d'un serveur enchaîne
    quatre routes — la fiche, le journal, les matchs, l'activité. Cinq
    appels à `/users/@me/guilds` pour une seule page, et deux
    rechargements nerveux suffisent à ce que Discord réponde 429. Le
    panneau annonçait alors « L'API n'a pas répondu » : l'API répondait
    très bien, c'est nous qui comptions mal.

    Le cache vit DANS la session, donc par personne et côté serveur. 30
    secondes, parce que cette liste n'est pas un confort d'affichage :
    c'est elle qui décide, via `peut_gerer`, qui a le droit de régler
    quoi. La garder longtemps serait un contrôle d'accès périmé.
    """
    cache = s.get("guildes")
    if cache and (time.time() - cache[0]) < CACHE_GUILDES:
        return cache[1], None
    try:
        liste = appel_discord("/users/@me/guilds", s["access_token"])
    except urllib.error.HTTPError as e:
        if e.code == 401:
            return None, (401, {"error": "UNAUTHORIZED"})
        # 429 se dit, il ne se déguise pas en panne : le PHP le renvoie tel
        # quel, et le panneau a un message pour lui. Le traduire en 502
        # ici, c'était faire mentir l'API de développement sur un cas que
        # la production connaît.
        if e.code == 429:
            return None, (429, {"error": "RATE"})
        return None, (502, {"error": "DISCORD_UNAVAILABLE"})
    except Exception:
        return None, (502, {"error": "DISCORD_UNAVAILABLE"})
    s["guildes"] = (time.time(), liste)
    return liste, None


def menage() -> None:
    """Sans ça le dictionnaire grossit indéfiniment sur un serveur qui tourne."""
    while True:
        time.sleep(3600)
        maintenant = time.time()
        with _verrou:
            for sid in [k for k, v in _sessions.items() if v["expire"] < maintenant]:
                del _sessions[sid]


# ================================== Discord ==================================

def appel_discord(chemin: str, jeton: str, type_jeton: str = "Bearer"):
    req = urllib.request.Request(
        API + chemin,
        headers={"Authorization": f"{type_jeton} {jeton}", "Accept": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=15) as r:
        return json.loads(r.read().decode("utf-8"))


def appel_bot(chemin: str, corps: dict, methode: str = "POST"):
    """Relaie une action au bot. Rend (code HTTP, données).

    Le contrat est celui du bot (cogs/dashboard_api.py), pas celui-ci : c'est
    lui qui ouvre la queue. Tout ce qui est tenu ici, c'est de ne rien
    inventer en cas de silence (502) et de laisser passer son refus tel
    quel, code compris, pour que le panneau sache dire « une queue tourne
    déjà » plutôt que « erreur ».
    """
    if not BOT_API_BASE:
        return 503, {"error": "BOT_API_ABSENTE"}

    # Une lecture n'a pas de corps : en envoyer un vide ferait refuser la
    # requete par certains serveurs, et n'a de toute facon aucun sens.
    donnees = None if corps is None else json.dumps(corps).encode("utf-8")
    entetes = {"Accept": "application/json"}
    if donnees is not None:
        entetes["Content-Type"] = "application/json"
    if BOT_API_KEY:
        entetes["X-API-Key"] = BOT_API_KEY

    req = urllib.request.Request(BOT_API_BASE + chemin, data=donnees,
                                 headers=entetes, method=methode)
    try:
        with urllib.request.urlopen(req, timeout=BOT_API_TIMEOUT) as r:
            brut = r.read().decode("utf-8") or "{}"
            try:
                return r.status, json.loads(brut)
            except ValueError:
                return r.status, {}
    except urllib.error.HTTPError as e:
        try:
            return e.code, json.loads(e.read().decode("utf-8"))
        except Exception:
            return e.code, {"error": "BOT_REFUS"}
    except Exception:
        # Bot éteint, port fermé, délai dépassé : rien n'a été ouvert.
        return 502, {"error": "BOT_INJOIGNABLE"}


def peut_gerer(g: dict) -> bool:
    if g.get("owner"):
        return True
    try:
        return (int(g.get("permissions", "0")) & MANAGE_GUILD) == MANAGE_GUILD
    except (TypeError, ValueError):
        return False


def icon_url(gid: str, h: str | None, taille: int = 64) -> str | None:
    if not h:
        return None
    ext = "gif" if h.startswith("a_") else "png"
    return f"https://cdn.discordapp.com/icons/{gid}/{h}.{ext}?size={taille}"


# ============================== réglages stockés =============================

# Un fichier JSON, pas une base. C'est assez pour une préversion et ça se
# remplace sans toucher au reste : seules ces deux fonctions lisent et
# écrivent. Voir le README avant d'ouvrir le site à du monde.
_verrou_fichier = threading.Lock()


"""Ce que ce serveur ajoute à la fin de config.js quand il le sert.

Le fichier du site déclare `API_BASE` vide, et c'est la valeur juste EN
LIGNE : l'hébergement LWS ne sert que des fichiers, rien ne répond sous
/api. Ici, c'est ce serveur qui sert la page, et lui répond — il le dit
donc lui-même, au moment de servir le fichier. Rien n'est modifié sur le
disque, donc rien n'est à défaire avant une mise en ligne.
"""
ANNONCE_API = """
/* ---- ajouté à la volée par api/server.py --------------------------------
   Le site et l'API partagent cette origine : l'API répond sous /api.
   Le fichier n'est pas modifié sur le disque. */
window.CYQ_CONFIG.API_BASE = '/api';
"""


def lire_reglages() -> dict:
    try:
        return json.loads(FICHIER_REGLAGES.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def ecrire_reglages(tout: dict) -> None:
    DOSSIER_DATA.mkdir(parents=True, exist_ok=True)
    tmp = FICHIER_REGLAGES.with_suffix(".tmp")
    tmp.write_text(json.dumps(tout, indent=2, ensure_ascii=False), encoding="utf-8")
    tmp.replace(FICHIER_REGLAGES)   # écriture atomique


# ================================= serveur ===================================

# Mémoire courte des serveurs où le bot se trouve : (horodatage, ensemble).
_bot_guildes_cache = (0.0, None)


def guildes_du_bot():
    """Les serveurs OÙ LE BOT SE TROUVE, demandés à Discord.

    Pourquoi ne pas se fier à l'enregistrement local : `botPresent` n'y est
    écrit qu'au retour d'une autorisation portant `guild_id`, c'est-à-dire
    quand le bot a été ajouté DEPUIS ce panneau. Un bot invité autrement —
    un lien collé dans Discord, une invitation antérieure à ce site — n'y
    figure pas, et son serveur s'affichait « Bot absent » alors qu'il y
    était.

    Une seule requête couvre tous les serveurs ; interroger `/guilds/{id}`
    en ferait une par ligne de la liste.

    Renvoie None quand on NE SAIT PAS — pas de jeton de bot, ou Discord
    muet. L'appelant retombe alors sur l'enregistrement local, au lieu
    d'affirmer que le bot est absent de partout.
    """
    global _bot_guildes_cache

    if not BOT_TOKEN:
        return None

    # 60 s : la durée que l'interface annonce déjà à qui vient d'inviter le
    # bot. Sans ce cache, afficher la liste coûterait une requête de plus à
    # chaque fois.
    quand, vu = _bot_guildes_cache
    if vu is not None and (time.time() - quand) < 60:
        return vu

    ids = set()
    apres = ""
    try:
        # Discord renvoie 200 guildes au plus par page. Sans pagination, un
        # bot présent sur davantage de serveurs perdrait les suivants — et
        # ce sont les plus récemment rejoints. Le plafond de 25 tours évite
        # une boucle sans fin si l'API répond de travers.
        for _ in range(25):
            url = "/users/@me/guilds?limit=200" + (f"&after={apres}" if apres else "")
            lot = appel_discord(url, BOT_TOKEN, "Bot")
            if not lot:
                break
            for g in lot:
                if g.get("id"):
                    ids.add(str(g["id"]))
            if len(lot) < 200:
                break
            apres = str(lot[-1].get("id") or "")
            if not apres:
                break
    except Exception:
        return None

    _bot_guildes_cache = (time.time(), ids)
    return ids


class Handler(BaseHTTPRequestHandler):
    server_version = "cyq"
    sys_version = ""

    # ------------------------------ utilitaires ------------------------------

    def cookies(self) -> dict:
        brut = self.headers.get("Cookie")
        if not brut:
            return {}
        out = {}
        for part in brut.split(";"):
            cle, _, val = part.partition("=")
            out[cle.strip()] = urllib.parse.unquote(val.strip())
        return out

    def poser_cookie(self, nom: str, valeur: str, max_age: int) -> None:
        bouts = [
            f"{nom}={urllib.parse.quote(valeur)}",
            "Path=/",
            "HttpOnly",               # inaccessible au JavaScript de la page
            "SameSite=Lax",           # suffisant : site et API sur une seule origine
            f"Max-Age={max_age}",
        ]
        if PROD:
            bouts.append("Secure")
        self._cookies_a_poser.append("; ".join(bouts))

    def effacer_cookie(self, nom: str) -> None:
        self._cookies_a_poser.append(f"{nom}=; Path=/; HttpOnly; SameSite=Lax; Max-Age=0")

    def entetes_cors(self) -> dict:
        """Les en-têtes qui autorisent le site à lire la réponse.

        Jamais `*` : avec `Allow-Credentials`, la norme l'interdit, et le
        navigateur rejetterait la réponse. On renvoie l'origine demandée,
        et seulement si elle figure dans la liste.

        `Vary: Origin` n'est pas décoratif : sans lui, un cache placé devant
        le serveur pourrait resservir à une origine la réponse autorisée
        pour une autre.
        """
        origine = (self.headers.get("Origin") or "").rstrip("/")
        if not origine or origine not in ORIGINES:
            return {"Vary": "Origin"}
        return {
            "Access-Control-Allow-Origin": origine,
            "Access-Control-Allow-Credentials": "true",
            "Vary": "Origin",
        }

    def repondre(self, code: int, corps: bytes = b"", type_mime: str = "application/json",
                 entetes: dict | None = None) -> None:
        self.send_response(code)
        self.send_header("Content-Type", type_mime)
        self.send_header("Content-Length", str(len(corps)))
        self.send_header("X-Content-Type-Options", "nosniff")
        for k, v in self.entetes_cors().items():
            self.send_header(k, v)
        for c in self._cookies_a_poser:
            self.send_header("Set-Cookie", c)
        for k, v in (entetes or {}).items():
            self.send_header(k, v)
        self.end_headers()
        if corps and self.command != "HEAD":
            self.wfile.write(corps)

    def json_out(self, code: int, donnees) -> None:
        self.repondre(code, json.dumps(donnees, ensure_ascii=False).encode("utf-8"))

    def rediriger(self, vers: str) -> None:
        self.repondre(302, b"", "text/plain", {"Location": vers})

    def session(self) -> dict | None:
        return lire_session(self.cookies().get("cyq_sid"))

    def corps_json(self):
        try:
            n = int(self.headers.get("Content-Length") or 0)
        except ValueError:
            return None
        if n <= 0 or n > 262144:
            return None
        try:
            return json.loads(self.rfile.read(n).decode("utf-8"))
        except (ValueError, UnicodeDecodeError):
            return None

    # -------------------------------- routage --------------------------------

    def do_GET(self):
        self._cookies_a_poser = []
        chemin = urllib.parse.urlparse(self.path).path
        params = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)

        if chemin == "/api/auth/login":
            return self.login()
        if chemin == "/api/auth/callback":
            return self.callback(params)
        if chemin == "/api/me":
            return self.me()
        if chemin == "/api/guilds":
            return self.guilds()
        if chemin.startswith("/api/guilds/"):
            reste = chemin[len("/api/guilds/"):]
            if reste and "/" not in reste:
                return self.guild(reste)
            # Ce dont le bot se souvient : historique, fiche de joueur,
            # releve d'activite, journal. Des LECTURES, donc ici et non
            # dans do_POST — c'est l'oubli qui les faisait toutes repondre
            # 404 au panneau.
            memoire = self.route_memoire(chemin)
            if memoire is not None:
                return memoire
            return self.json_out(404, {"error": "NOT_FOUND"})
        if chemin.startswith("/api/"):
            return self.json_out(404, {"error": "NOT_FOUND"})
        return self.fichier(chemin)

    do_HEAD = do_GET

    def do_OPTIONS(self):
        """La requête de vérification que le navigateur envoie avant un PATCH
        venu d'une autre origine. Sans réponse ici, l'enregistrement des
        réglages échouerait avant même de partir."""
        self._cookies_a_poser = []
        self.repondre(204, b"", "text/plain", {
            "Access-Control-Allow-Methods": "GET, POST, PATCH, OPTIONS",
            "Access-Control-Allow-Headers": "Content-Type",
            "Access-Control-Max-Age": "86400",
        })

    def do_POST(self):
        self._cookies_a_poser = []
        chemin = urllib.parse.urlparse(self.path).path
        if chemin == "/api/auth/logout":
            sid = self.cookies().get("cyq_sid")
            if sid:
                with _verrou:
                    _sessions.pop(sid, None)
            self.effacer_cookie("cyq_sid")
            return self.repondre(204)
        for geste in ("open", "close"):
            fin = "/queue/" + geste
            if chemin.startswith("/api/guilds/") and chemin.endswith(fin):
                gid = chemin[len("/api/guilds/"):-len(fin)]
                if gid and "/" not in gid:
                    return self.queue_geste(gid, geste)
        if chemin.startswith("/api/guilds/") and chemin.endswith("/bans"):
            gid = chemin[len("/api/guilds/"):-len("/bans")]
            if gid and "/" not in gid:
                return self.bans_geste(gid)
        if chemin == "/contact.php":
            return self.contact()
        return self.json_out(404, {"error": "NOT_FOUND"})

    def do_PATCH(self):
        self._cookies_a_poser = []
        chemin = urllib.parse.urlparse(self.path).path
        if chemin.startswith("/api/guilds/") and chemin.endswith("/settings"):
            gid = chemin[len("/api/guilds/"):-len("/settings")]
            if gid and "/" not in gid:
                return self.patch_settings(gid)
        return self.json_out(404, {"error": "NOT_FOUND"})

    # ------------------------------- connexion -------------------------------

    def login(self):
        """L'URL Discord est construite ICI, pas dans la page : le paramètre
        state doit être tiré au sort côté serveur et retrouvé au retour, sinon
        n'importe quel site peut déclencher la connexion à votre place."""
        state = secrets.token_urlsafe(16)
        self.poser_cookie("cyq_state", state, DUREE_STATE)
        # Un seul écran pour les deux : `identify guilds` ouvre la session, et
        # `bot applications.commands` fait apparaître le choix du serveur où
        # ajouter le bot. Discord accepte de combiner les deux dans une même
        # autorisation, et renvoie alors guild_id en plus du code.
        q = urllib.parse.urlencode({
            "client_id": CLIENT_ID,
            "response_type": "code",
            "redirect_uri": redirect_uri(),
            "scope": "identify guilds bot applications.commands",
            "permissions": INVITE_PERMISSIONS,
            "state": state,
        })
        self.rediriger("https://discord.com/oauth2/authorize?" + q)

    def callback(self, params):
        code = (params.get("code") or [None])[0]
        state = (params.get("state") or [None])[0]
        attendu = self.cookies().get("cyq_state")
        self.effacer_cookie("cyq_state")

        if params.get("error"):
            return self.rediriger(APP + "servers.html?auth=refus")
        if not code:
            return self.rediriger(APP + "servers.html?auth=incomplet")
        # Comparaison à temps constant : une comparaison naïve fuit la valeur.
        if not attendu or not state or not hmac.compare_digest(attendu, state):
            return self.rediriger(APP + "servers.html?auth=state")

        try:
            donnees = urllib.parse.urlencode({
                "client_id": CLIENT_ID,
                "client_secret": CLIENT_SECRET,
                "grant_type": "authorization_code",
                "code": code,
                "redirect_uri": redirect_uri(),
            }).encode()
            req = urllib.request.Request(
                API + "/oauth2/token", data=donnees,
                headers={"Content-Type": "application/x-www-form-urlencoded"},
            )
            with urllib.request.urlopen(req, timeout=15) as r:
                jeton = json.loads(r.read().decode("utf-8"))

            moi = appel_discord("/users/@me", jeton["access_token"])
        except urllib.error.HTTPError as e:
            # Le corps peut contenir des éléments du secret : on n'en journalise rien.
            print(f"  Échange du code refusé par Discord (HTTP {e.code})")
            return self.rediriger(APP + "servers.html?auth=echange")
        except Exception as e:
            print(f"  Connexion impossible : {type(e).__name__}")
            return self.rediriger(APP + "servers.html?auth=erreur")

        avatar = moi.get("avatar")
        sid = creer_session({
            "access_token": jeton["access_token"],
            "user_id": moi["id"],
            "user_name": moi.get("global_name") or moi.get("username"),
            "avatar_url": (f"https://cdn.discordapp.com/avatars/{moi['id']}/{avatar}.png?size=64"
                           if avatar else None),
        })
        self.poser_cookie("cyq_sid", sid, DUREE_SESSION)

        # Avec le scope `bot`, Discord indique le serveur ou le bot vient d'etre
        # ajoute. On le NOTE, mais on n'y emmene pas d'office : on arrive
        # toujours sur le choix du serveur. Ouvrir directement le panneau de
        # ce serveur-la etait une supposition de trop — on se connecte le plus
        # souvent pour regler un serveur deja configure.
        gid = (params.get("guild_id") or [None])[0]
        if gid and gid.isdigit():
            with _verrou_fichier:
                tout = lire_reglages()
                tout[gid] = {**tout.get(gid, {}), "botPresent": True}
                ecrire_reglages(tout)

        self.rediriger(APP + "servers.html")

    # ---------------------------------- api ----------------------------------

    def me(self):
        s = self.session()
        if not s:
            return self.json_out(401, {"error": "UNAUTHORIZED"})
        self.json_out(200, {"id": s["user_id"], "name": s["user_name"],
                            "avatarUrl": s["avatar_url"]})

    def guilds(self):
        s = self.session()
        if not s:
            return self.json_out(401, {"error": "UNAUTHORIZED"})
        brut, erreur = mes_guildes(s)
        if erreur:
            return self.json_out(*erreur)

        reglages = lire_reglages()

        # La présence du bot vient de Discord quand on peut la lui demander,
        # de l'enregistrement local sinon. Ce repli peut se tromper PAR
        # DÉFAUT — dire « absent » d'un bot présent — jamais dans l'autre
        # sens : la ligne propose alors de l'inviter, ce qui ne casse rien
        # s'il est déjà là.
        presents = guildes_du_bot()

        liste = []
        for g in brut:
            if not peut_gerer(g):
                continue
            enr = reglages.get(g["id"], {})
            liste.append({
                "id": g["id"],
                "name": g["name"],
                "iconUrl": icon_url(g["id"], g.get("icon")),
                "memberCount": g.get("approximate_member_count"),
                "canManage": True,
                "botPresent": bool(enr.get("botPresent"))
                if presents is None else str(g["id"]) in presents,
                "configured": bool(enr.get("settings")),
                "updatedAt": enr.get("updatedAt"),
                "missingPermissions": enr.get("missingPermissions", []),
            })
        self.json_out(200, liste)

    def guilde_geree(self, gid: str):
        """Vérifie que la personne gère VRAIMENT ce serveur. Sans ce contrôle,
        n'importe quel compte connecté lirait et modifierait la configuration
        de n'importe quelle guilde en changeant l'identifiant dans l'URL."""
        s = self.session()
        if not s:
            self.json_out(401, {"error": "UNAUTHORIZED"})
            return None, None
        mes, erreur = mes_guildes(s)
        if erreur:
            self.json_out(*erreur)
            return None, None

        g = next((x for x in mes if x["id"] == gid), None)
        if not g or not peut_gerer(g):
            self.json_out(403, {"error": "FORBIDDEN"})
            return None, None
        return s, g

    def guild(self, gid: str):
        s, g = self.guilde_geree(gid)
        if not g:
            return
        enr = lire_reglages().get(gid, {})
        rep = {
            "id": g["id"],
            "name": g["name"],
            "iconUrl": icon_url(g["id"], g.get("icon"), 128),
            "memberCount": g.get("approximate_member_count"),
            # Les boosts et la date d'arrivée du bot viennent du BOT, qui
            # n'existe pas derrière ce serveur-ci : ce sont les deux seuls
            # champs de la fiche qu'on ne peut pas honorer en
            # développement. `null` et pas `0` — le panneau affiche alors
            # son état vide réel, qui est exactement ce qu'il affichera en
            # production quand le bot dort. Un zéro se lirait « aucun
            # boost », ce qui serait une réponse inventée.
            "boosts": None,
            "botSince": None,
            "me": {"name": s["user_name"]},
            # En production, ce champ dit si le bot a répondu : sans lui, le
            # panneau servait la copie du site comme une lecture fraîche.
            # Ici il n'y a pas de bot derrière les réglages — ce serveur EST
            # la vérité — donc vrai, sauf quand on veut justement voir ce que
            # le panneau affiche quand le bot dort : CYQ_BOT_OFF=1.
            "botJoignable": not BOT_ETEINT,
            "settings": enr.get("settings"),
            "presets": enr.get("presets", []),
            "permissions": enr.get("permissions"),
            "missingPermissions": enr.get("missingPermissions", []),
            "botRolePosition": enr.get("botRolePosition"),
            "channels": [], "voiceChannels": [], "categories": [], "roles": [],
        }

        # Salons et rôles ne sont lisibles qu'avec un jeton de BOT : le jeton
        # utilisateur n'y donne pas accès. Sans DISCORD_BOT_TOKEN, on renvoie
        # des listes vides — les menus seront vides, mais rien ne ment.
        if BOT_TOKEN:
            try:
                salons = appel_discord(f"/guilds/{gid}/channels", BOT_TOKEN, "Bot")
                roles = appel_discord(f"/guilds/{gid}/roles", BOT_TOKEN, "Bot")
                nom = lambda c: {"id": c["id"], "name": c["name"]}
                # Types Discord : 0 textuel · 2 vocal · 4 catégorie ·
                # 5 annonces · 13 conférence. Annonces et conférences se
                # comportent comme un textuel et un vocal — le bot y écrit
                # et y déplace des joueurs — et elles étaient ignorées.
                rep["channels"] = [nom(c) for c in salons if c.get("type") in (0, 5)]
                rep["voiceChannels"] = [nom(c) for c in salons if c.get("type") in (2, 13)]
                rep["categories"] = [nom(c) for c in salons if c.get("type") == 4]
                rep["roles"] = [
                    {"id": r["id"], "name": r["name"], "position": r["position"]}
                    for r in sorted(roles, key=lambda r: -r["position"])
                    if not r.get("managed") and r["name"] != "@everyone"
                ]
            except Exception as e:
                # Le bot n'est pas sur ce serveur, ou il lui manque un droit.
                # Le repli ci-dessous rattrape ce cas.
                print(f"  Salons/rôles indisponibles pour {gid} : {type(e).__name__}")

        # LE REPLI SUR LE BOT. Sans DISCORD_BOT_TOKEN — le cas normal en
        # développement — les quatre listes restaient vides EN SILENCE : tous
        # les menus de salons et de rôles du panneau étaient muets, et la
        # section Anti-lien n'affichait qu'un filtre sans rien à filtrer.
        # Le bot tient déjà ces listes. On les lui redemande.
        #
        # Le même repli existe dans site/api/index.php, et il doit y rester
        # identique : une réponse qui diffère entre les deux implémentations,
        # c'est un écran qui marche en local et pas en ligne.
        if not all((rep["channels"], rep["voiceChannels"],
                    rep["categories"], rep["roles"])):
            code_opt, opt = appel_bot(f"/api/guilds/{gid}/options", {}, "GET")
            if code_opt == 200 and isinstance(opt, dict):
                def repli(brut):
                    """Champ par champ : le front attend {id, name} en
                    chaînes, et une entrée mal formée doit disparaître plutôt
                    que d'arriver dans un menu sous la forme « undefined »."""
                    sortie = []
                    for e in brut if isinstance(brut, list) else []:
                        if not isinstance(e, dict) or "id" not in e or "name" not in e:
                            continue
                        un = {"id": str(e["id"]), "name": str(e["name"])}
                        if "position" in e:
                            un["position"] = int(e["position"])
                        sortie.append(un)
                    return sortie

                if not rep["channels"]:
                    rep["channels"] = repli(opt.get("text"))
                if not rep["voiceChannels"]:
                    rep["voiceChannels"] = repli(opt.get("voice"))
                if not rep["categories"]:
                    rep["categories"] = repli(opt.get("category"))
                if not rep["roles"]:
                    rep["roles"] = repli(opt.get("role"))

        self.json_out(200, rep)

    def patch_settings(self, gid: str):
        s, g = self.guilde_geree(gid)
        if not g:
            return
        corps = self.corps_json()
        if not isinstance(corps, dict):
            return self.json_out(400, {"error": "BAD_BODY"})
        with _verrou_fichier:
            tout = lire_reglages()
            actuel = tout.get(gid, {})
            tout[gid] = {
                **actuel,
                "settings": {**actuel.get("settings", {}), **corps},
                "updatedAt": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            }
            ecrire_reglages(tout)
        self.repondre(204)

    MEMOIRE = ("matches", "activity", "audit")

    def route_memoire(self, chemin: str):
        """Relaie une lecture au bot. Rend None si ce n'en est pas une.

        Les parametres sont RECOPIES un par un, jamais relayes en bloc :
        passer la chaine de requete telle quelle laisserait n'importe qui
        ajouter ce qu'il veut a l'URL appelee chez le bot.
        """
        if not chemin.startswith("/api/guilds/"):
            return None
        reste = chemin[len("/api/guilds/"):].split("/")
        if len(reste) < 2 or not reste[0].isdigit():
            return None
        gid = reste[0]

        if len(reste) == 2 and reste[1] in self.MEMOIRE:
            cible = "/api/guilds/%s/%s" % (gid, reste[1])
        elif len(reste) == 3 and reste[1] == "players" and reste[2].isdigit():
            cible = "/api/guilds/%s/players/%s" % (gid, reste[2])
        else:
            return None

        s, g = self.guilde_geree(gid)
        if not g:
            return True   # guilde_geree a deja repondu

        permis = []
        requete = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
        for nom in ("limit", "offset", "days", "player", "season"):
            valeurs = requete.get(nom) or []
            if valeurs and str(valeurs[0]).isdigit():
                permis.append((nom, valeurs[0]))
        if permis:
            cible += "?" + urllib.parse.urlencode(permis)

        code, rep = appel_bot(cible, None, methode="GET")
        if code == 503:
            self.json_out(503, {"error": rep.get("error", "BOT_API_ABSENTE")})
            return True
        if code == 0 or code == 502:
            self.json_out(502, {"error": "BOT_INJOIGNABLE"})
            return True
        self.json_out(code, rep)
        return True

    def bans_geste(self, gid: str):
        """Exclut ou reintegre un joueur. Un GESTE, pas un reglage : envoyer
        la liste entiere effacerait ce qu'un autre onglet vient d'ajouter."""
        s, g = self.guilde_geree(gid)
        if not g:
            return
        corps = self.corps_json()
        if not isinstance(corps, dict):
            return self.json_out(400, {"error": "BAD_BODY"})
        gestes = {}
        for geste in ("add", "remove", "lift"):
            liste = corps.get(geste) or []
            if not isinstance(liste, list):
                return self.json_out(400, {"error": "BAD_BODY"})
            propre = [str(u) for u in liste if str(u).isdigit()]
            if len(propre) != len(liste):
                return self.json_out(400, {"error": "BAD_BODY"})
            if propre:
                gestes[geste] = propre
        if not gestes:
            return self.json_out(400, {"error": "BAD_BODY"})
        gestes["reason"] = str(corps.get("reason") or "")[:200]

        code, rep = appel_bot("/api/guilds/" + gid, {
            "bans": gestes,
            "actor": {"id": s["user_id"], "name": s["user_name"]},
        }, methode="PATCH")
        if code == 503:
            return self.json_out(503, {"error": rep.get("error", "BOT_API_ABSENTE")})
        if code in (0, 502):
            return self.json_out(502, {"error": "BOT_INJOIGNABLE"})
        self.json_out(code, rep)

    def queue_geste(self, gid: str, geste: str):
        """Ouvre ou ferme la queue de ce serveur, selon `geste`.

        Rien n'est transmis d'autre que QUI agit. Le bot ouvre la queue avec
        la configuration qu'il a deja, exactement comme le bouton
        « Publier » du panneau `/queue` ; il la ferme comme le bouton
        « Annuler ». Si le site envoyait ses propres reglages, deux verites
        cohabiteraient et la queue ouverte ne serait ni l'une ni l'autre.

        C'est aussi le bot qui dit ce qui empeche d'agir — salon manquant,
        queue deja en cours, aucune queue a fermer. Le refaire ici, sur un
        enregistrement qui n'est pas le sien, reviendrait a refuser des
        gestes parfaitement possibles.
        """
        s, g = self.guilde_geree(gid)
        if not g:
            return

        qui = {"id": s.get("user_id"), "name": s.get("user_name")}
        corps = {"openedBy": qui} if geste == "open" else {"closedBy": qui}
        code, rep = appel_bot(f"/api/guilds/{gid}/queue/{geste}", corps)

        if code in (200, 201):
            if geste == "open":
                return self.json_out(200, {
                    "channelId": rep.get("channelId"),
                    "messageUrl": rep.get("messageUrl"),
                    "capacity": rep.get("capacity"),
                })
            return self.json_out(200, {
                "queueName": rep.get("queueName"),
                "players": rep.get("players"),
            })
        if code == 409:
            # Le motif du bot passe tel quel : already_open, no_channel,
            # setup_incomplete, no_config, no_queue, missing_permissions.
            defaut = "already_open" if geste == "open" else "no_queue"
            return self.json_out(409, {"error": rep.get("error", defaut)})
        if code == 503:
            return self.json_out(503, {"error": rep.get("error", "BOT_API_ABSENTE")})
        return self.json_out(502, {"error": rep.get("error", "BOT_INJOIGNABLE")})

    # ------------------------------- le contact ------------------------------

    def contact(self):
        """Le pendant de `site/contact.php`, pour pouvoir essayer le
        formulaire de support en local.

        Il N'ENVOIE RIEN. Un serveur de développement qui expédie du courrier
        pour de vrai, c'est la boîte de contact remplie de brouillons le jour
        où on met au point la page. Le message est écrit dans le journal, et
        c'est là qu'on va le lire.

        En revanche il refuse EXACTEMENT ce que refuse le PHP, avec les mêmes
        motifs : c'est tout l'intérêt d'avoir les deux côtés d'accord. Les
        états d'erreur de la page ne se vérifient que si on peut les
        provoquer ici."""
        BORNES = {
            "nom": (2, 80),
            "email": (5, 190),
            "sujet": (2, 120),
            "message": (10, 5000),
        }
        corps = self.corps_json()
        if not isinstance(corps, dict):
            return self.json_out(400, {"error": "BAD_REQUEST"})

        # Le piège à robots : rempli, on répond le succès sans rien faire.
        if str(corps.get("site") or "").strip():
            return self.repondre(204)

        valeurs = {}
        for champ, (mini, maxi) in BORNES.items():
            v = corps.get(champ, "")
            if not isinstance(v, str):
                return self.json_out(400, {"error": "BAD_REQUEST"})
            v = v.strip()
            if champ != "message":
                v = v.replace("\r", " ").replace("\n", " ").replace("\0", " ").strip()
            if len(v) < mini:
                return self.json_out(
                    400, {"error": "CHAMP_MANQUANT" if not v else "TROP_COURT"})
            if len(v) > maxi:
                return self.json_out(400, {"error": "TROP_LONG"})
            valeurs[champ] = v

        # Le même contrôle qu'en PHP, en moins fin : `filter_var` connaît des
        # cas tordus que cette expression ignore. Assez pour le développement,
        # et c'est le PHP qui fait foi.
        courriel = valeurs["email"]
        if courriel.count("@") != 1 or " " in courriel:
            return self.json_out(400, {"error": "EMAIL_INVALIDE"})
        avant, apres = courriel.split("@")
        if not avant or "." not in apres or apres.startswith(".") or apres.endswith("."):
            return self.json_out(400, {"error": "EMAIL_INVALIDE"})

        # Un interrupteur pour voir la page échouer sans rien casser : un
        # sujet qui commence par ECHEC rejoue « l'envoi a échoué », et un
        # sujet qui commence par QUOTA rejoue le dépassement de quota.
        #
        # Le déclencheur est dans le SUJET et non dans l'adresse, parce que
        # la page poste sur « contact.php » tout court : un paramètre
        # d'URL n'arriverait jamais ici, sauf à faire porter au JS de
        # production un bout de code qui ne sert qu'au développement.
        if valeurs["sujet"].startswith("ECHEC"):
            return self.json_out(502, {"error": "ENVOI_IMPOSSIBLE"})
        if valeurs["sujet"].startswith("QUOTA"):
            return self.json_out(429, {"error": "TROP_DE_DEMANDES"})

        # flush : la sortie de Python est tamponnée dès qu'elle ne va pas
        # dans un terminal — lancé par l'éditeur ou redirigé dans un fichier,
        # le message n'apparaissait qu'à l'arrêt du serveur, c'est-à-dire
        # trop tard pour servir à quoi que ce soit.
        print(
            "\n--- contact (non envoyé) ---------------------------------\n"
            f"  pour    : contact@cyqbot.eu\n"
            f"  de      : {valeurs['nom']} <{valeurs['email']}>\n"
            f"  sujet   : {valeurs['sujet']}\n"
            f"  langue  : {corps.get('langue') or '?'}\n"
            f"  message : {valeurs['message'][:400]}\n"
            "----------------------------------------------------------\n",
            flush=True,
        )
        return self.repondre(204)

    # -------------------------------- le site --------------------------------

    def fichier(self, chemin: str):
        rel = urllib.parse.unquote(chemin).lstrip("/") or "index.html"
        cible = (SITE / rel).resolve()
        # Traversée de répertoire : sans ce contrôle, ../../.env est servable.
        if not cible.is_relative_to(SITE):
            return self.repondre(403, b"Interdit", "text/plain; charset=utf-8")
        if cible.is_dir():
            cible = cible / "index.html"
        if not cible.is_file():
            return self.repondre(404, b"Introuvable", "text/plain; charset=utf-8")

        type_mime = mimetypes.guess_type(str(cible))[0] or "application/octet-stream"
        if type_mime.startswith("text/") or type_mime in (
            "application/javascript", "application/json",
        ):
            type_mime += "; charset=utf-8"

        corps = cible.read_bytes()

        # config.js déclare API_BASE vide : c'est la valeur juste EN LIGNE, où
        # l'hébergement LWS ne sert que des fichiers et où rien ne répond sous
        # /api. Mais ici, c'est ce serveur qui sert la page, et lui répond.
        # Il le dit donc lui-même, au moment de servir le fichier, plutôt que
        # de demander qu'on modifie le site — une modification qu'on oublierait
        # ensuite de défaire avant la mise en ligne, et qui enverrait chaque
        # visiteur sur un /api inexistant.
        # Les deux sites ont chacun leur copie de config.js — la vitrine et le
        # panneau sont servis depuis deux dossiers. On reconnaît le fichier à
        # sa place plutôt qu'à un chemin unique, sinon seule la première
        # copie recevrait l'annonce.
        if cible.name == "config.js" and cible.parent.name == "js":
            corps += ANNONCE_API.encode("utf-8")

        self.repondre(200, corps, type_mime)

    def log_message(self, fmt, *args):
        pass    # le journal par défaut noie la sortie utile


# ================================= démarrage =================================

def main() -> None:
    manquant = [n for n, v in (("DISCORD_CLIENT_ID", CLIENT_ID),
                               ("DISCORD_CLIENT_SECRET", CLIENT_SECRET)) if not v]
    if manquant:
        print("\n  Il manque : " + ", ".join(manquant))
        print("  Copiez .env.example vers .env, remplissez-le, puis relancez.\n")
        sys.exit(1)
    if not SITE.is_dir():
        print(f"\n  Dossier du site introuvable : {SITE}\n")
        sys.exit(1)

    threading.Thread(target=menage, daemon=True).start()

    print(f"\n  Site + API : {base_url()}")
    print(f"  Redirect à déclarer dans Discord : {redirect_uri()}")
    if not BOT_TOKEN:
        print("  (DISCORD_BOT_TOKEN absent : les listes de salons et de rôles resteront vides)")
    print("")
    ThreadingHTTPServer(("0.0.0.0", PORT), Handler).serve_forever()


if __name__ == "__main__":
    main()
