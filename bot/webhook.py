"""
Webhook sortant — le résultat d'un match part où l'organisateur veut.
=====================================================================
Le bot sait tout d'un match et ne le disait qu'à Discord. Un serveur qui
tient son propre site, sa feuille de calcul ou son overlay de stream devait
recopier les scores à la main.

Une URL par serveur, réglée dans le panneau. À la fin de chaque match, le
bot y POSTe la fiche que `history.record_match` vient d'enregistrer — la
même, pas une seconde description qui pourrait diverger.

Trois précautions, et elles comptent :

- **L'adresse est vérifiée** avant d'être acceptée (`url_acceptable`). En
  https seulement, et jamais vers une adresse interne : une URL comme
  `http://127.0.0.1:3000/` ou `http://169.254.169.254/` ferait du bot un
  relais vers le réseau de l'hébergeur, pour quiconque peut configurer un
  serveur. C'est une SSRF, et elle se referme ici.
- **L'envoi ne bloque rien.** Il part en tâche de fond : un serveur distant
  qui met trente secondes à répondre ne doit pas retarder l'annonce des
  résultats dans Discord.
- **Un échec est silencieux côté joueurs.** Il va dans les logs du bot. Le
  match a eu lieu ; que le site d'à côté l'ait reçu ou non ne regarde pas
  ceux qui viennent de jouer.
"""

from __future__ import annotations

import asyncio
import ipaddress
import logging
import socket
from urllib.parse import urlparse

import aiohttp
import discord

log = logging.getLogger("bot.webhook")

# Le temps qu'on accorde au serveur distant. Court : ce n'est pas une
# conversation, c'est un dépôt.
TIMEOUT = 8

# Les tâches en vol. asyncio ne garde qu'une référence FAIBLE sur une tâche
# lancée par create_task : sans ce jeu, le ramasse-miettes peut l'emporter
# avant l'envoi.
_en_vol: set[asyncio.Task] = set()


def _adresse_interne(hote: str) -> bool:
    """L'hôte désigne-t-il une machine du réseau local ?

    On résout le nom : `interne.example.com` qui pointe sur 10.0.0.1 est
    tout aussi dangereux que `10.0.0.1` écrit en clair. Une résolution qui
    échoue est traitée comme interne — on refuse plutôt que de tenter.
    """
    try:
        infos = socket.getaddrinfo(hote, None)
    except (socket.gaierror, UnicodeError):
        return True
    for info in infos:
        try:
            ip = ipaddress.ip_address(info[4][0])
        except ValueError:
            return True
        if (ip.is_private or ip.is_loopback or ip.is_link_local
                or ip.is_reserved or ip.is_multicast or ip.is_unspecified):
            return True
    return False


def url_acceptable(url: str) -> bool:
    """L'URL peut-elle servir de webhook ? Appelée AVANT d'enregistrer.

    Vérifier à l'envoi seulement laisserait une adresse refusée dans la
    configuration, et le panneau l'afficherait comme un réglage valide.
    """
    if not url:
        return False
    if len(url) > 500:
        return False
    try:
        morceaux = urlparse(url)
    except ValueError:
        return False
    # https seulement : le résultat d'un match porte des identifiants
    # Discord, et http les promènerait en clair.
    if morceaux.scheme != "https" or not morceaux.hostname:
        return False
    return not _adresse_interne(morceaux.hostname)


def _charge(guild: discord.Guild, fiche: dict) -> dict:
    """Ce qui part : la fiche du match, plus de quoi savoir d'où elle vient.

    Les pseudos accompagnent les identifiants. Le destinataire n'a pas de
    jeton Discord pour les traduire lui-même, et une liste d'identifiants
    nus n'est lisible par personne.
    """
    noms = {}
    for uid in (fiche.get("players") or {}):
        membre = guild.get_member(int(uid))
        noms[uid] = membre.display_name if membre else None
    return {
        "guild": {"id": str(guild.id), "name": guild.name},
        "match": fiche,
        "names": noms,
    }


async def _poster(url: str, charge: dict) -> None:
    try:
        delai = aiohttp.ClientTimeout(total=TIMEOUT)
        async with aiohttp.ClientSession(timeout=delai) as session:
            async with session.post(
                url, json=charge,
                headers={"User-Agent": "CreateYourQueue (https://cyqbot.eu)"},
            ) as reponse:
                if reponse.status >= 400:
                    log.warning(f"Webhook refusé ({reponse.status}) par {url}")
    except (aiohttp.ClientError, asyncio.TimeoutError) as e:
        log.warning(f"Webhook non remis à {url} : {e}")


def envoyer_webhook(bot, guild: discord.Guild, fiche: dict) -> None:
    """Envoie la fiche du match, si ce serveur a une URL. Ne bloque pas."""
    from guild_settings import get_webhook_url

    url = get_webhook_url(guild.id)
    if not url:
        return
    tache = asyncio.create_task(_poster(url, _charge(guild, fiche)))
    _en_vol.add(tache)
    tache.add_done_callback(_en_vol.discard)
