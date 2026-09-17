"""
Garde-fous réseau pour les téléchargements déclenchés par un utilisateur
(URL d'avatar ou de bannière personnalisée fournie via /config).
"""

from __future__ import annotations

import ipaddress
import socket
from urllib.parse import urlparse

import aiohttp


def _is_public_hostname(hostname: str) -> bool:
    try:
        infos = socket.getaddrinfo(hostname, None)
    except socket.gaierror:
        return False
    if not infos:
        return False
    for info in infos:
        try:
            ip = ipaddress.ip_address(info[4][0])
        except ValueError:
            return False
        if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved or ip.is_multicast or ip.is_unspecified:
            return False
    return True


async def safe_fetch(url: str, *, max_bytes: int, timeout: int = 15) -> bytes | None:
    """Télécharge une URL utilisateur en refusant les cibles réseau internes
    (SSRF) et les réponses trop volumineuses. Retourne None si la requête
    est refusée ou échoue — jamais d'exception pour une entrée invalide."""
    url = url.strip()
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https") or not parsed.hostname:
        return None
    if not _is_public_hostname(parsed.hostname):
        return None

    try:
        async with aiohttp.ClientSession() as session:
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
