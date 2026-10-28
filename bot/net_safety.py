"""
Garde-fous réseau pour les téléchargements déclenchés par un utilisateur
(URL d'avatar ou de bannière personnalisée fournie via /config).
"""

from __future__ import annotations

import ipaddress
import socket
from urllib.parse import urlparse

import aiohttp


def is_public_address(address: str) -> bool:
    try:
        return ipaddress.ip_address(address.split("%")[0]).is_global
    except ValueError:
        return False


class PublicOnlyResolver(aiohttp.ThreadedResolver):
    """Résolution DNS hors de la boucle, qui refuse toute adresse interne.

    Le contrôle se fait sur l'adresse à laquelle aiohttp va vraiment se
    connecter : un nom qui change de réponse entre deux résolutions ne passe pas."""

    async def resolve(self, host: str, port: int = 0, family: socket.AddressFamily = socket.AF_INET):
        infos = await super().resolve(host, port, family)
        if not infos or not all(is_public_address(info["host"]) for info in infos):
            raise OSError(f"adresse non publique refusée : {host}")
        return infos


async def safe_fetch(url: str, *, max_bytes: int, timeout: int = 15) -> bytes | None:
    """Télécharge une URL utilisateur en refusant les cibles réseau internes
    (SSRF) et les réponses trop volumineuses. Retourne None si la requête
    est refusée ou échoue — jamais d'exception pour une entrée invalide."""
    url = url.strip()
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https") or not parsed.hostname:
        return None
    # Une adresse IP écrite en clair ne passe pas par le résolveur.
    try:
        ipaddress.ip_address(parsed.hostname)
    except ValueError:
        pass
    else:
        if not is_public_address(parsed.hostname):
            return None

    try:
        connector = aiohttp.TCPConnector(resolver=PublicOnlyResolver())
        async with aiohttp.ClientSession(connector=connector) as session:
            async with session.get(
                url, timeout=aiohttp.ClientTimeout(total=timeout), allow_redirects=False
            ) as resp:
                if resp.status != 200:
                    return None
                if resp.content_length is not None and resp.content_length > max_bytes:
                    return None
                data = bytearray()
                async for chunk in resp.content.iter_chunked(65536):
                    data.extend(chunk)
                    if len(data) > max_bytes:
                        return None
                return bytes(data)
    except Exception:
        return None
