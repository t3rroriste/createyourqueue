"""
Web — Dashboard de configuration.
===================================
Un petit serveur HTTP qui tourne DANS le process du bot. C'est volontaire :
`guild_settings` garde toute la configuration dans des dictionnaires en
mémoire, sauvegardés en JSON. Un process séparé lirait un cache obsolète et
deux process écrivant le même fichier finiraient par se marcher dessus, malgré
l'écriture atomique de `json_store`.

En vivant dans le process du bot, le dashboard appelle exactement les mêmes
fonctions que les cogs — aucune logique métier n'est dupliquée.
"""
