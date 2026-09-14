"""
Cog : Temp Bot
===============
Commandes spécifiques pour le bot temporaire (waiting message, etc.)
"""

import discord
from discord import app_commands
from discord.ext import commands

from config import OWNER_ID

class TempBot(commands.Cog):
    """Commandes spécifiques pour le bot temporaire."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        # Stocker les IDs des messages waiting par salon pour pouvoir les mettre à jour
        self.waiting_messages = {}  # {channel_id: message_id}

    async def _is_owner(self, user: discord.abc.User) -> bool:
        if OWNER_ID and user.id == OWNER_ID:
            return True
        return await self.bot.is_owner(user)

    @app_commands.command(name="waiting", description="Envoie le message d'attente (owner uniquement)")
    async def waiting(self, interaction: discord.Interaction) -> None:
        """Envoie le message d'attente et supprime la commande (owner uniquement)."""
        
        
        # Propriétaire : OWNER_ID dans .env, ou le propriétaire de l'application Discord
        if not await self._is_owner(interaction.user):
            await interaction.response.send_message("Cette commande est réservée au owner du bot.", ephemeral=True)
            return
        
        # Supprimer le message de commande
        try:
            await interaction.response.defer(ephemeral=True)
            await interaction.delete_original_response()
        except discord.HTTPException:
            pass
        
        # Créer l'embed style webhook
        embed = discord.Embed(
            title="**🚧‎ ‎ ‎ ‎ ‎Coming soon ...‎‎ ‎ ‎ ‎ ‎ 🚧**",
            description=(
                ">>> 🇫🇷 : Le serveur Discord est en cours de création. Veuillez patienter.\n"
                "🇺🇸 : The Discord server is currently under construction. Please wait."
            ),
            color=0x000000  # Noir
        )
        embed.set_footer(text="L'equipe CYQ")
        
        # Vérifier s'il y a déjà un message waiting dans ce salon
        channel_id = interaction.channel.id
        if channel_id in self.waiting_messages:
            try:
                # Supprimer l'ancien message
                old_message_id = self.waiting_messages[channel_id]
                old_message = await interaction.channel.fetch_message(old_message_id)
                await old_message.delete()
            except discord.HTTPException:
                pass  # L'ancien message n'existe plus ou ne peut pas être supprimé
        
        # Envoyer le nouveau message
        message = await interaction.channel.send(embed=embed)
        
        # Stocker l'ID du nouveau message
        self.waiting_messages[channel_id] = message.id


async def setup(bot: commands.Bot):
    await bot.add_cog(TempBot(bot))
