"""ClanWar : l'abandon pendant la partie, et les tickets « Problème » qui
continuent en message privé entre le staff et le membre."""

import unittest
from types import SimpleNamespace
from unittest import mock

import discord

import guild_settings as gs
from cogs import clan_tickets, clan_war
from i18n import t

GID = 4242


class FakeResponse:
    def __init__(self):
        self.messages = []
        self.edits = []
        self.modals = []

    async def send_message(self, content=None, **kwargs):
        self.messages.append((content, kwargs))

    async def edit_message(self, **kwargs):
        self.edits.append(kwargs)

    async def send_modal(self, modal):
        self.modals.append(modal)

    async def defer(self, **kwargs):
        pass


class FakeMessage:
    def __init__(self, message_id, channel, **kwargs):
        self.id = message_id
        self.channel = channel
        self.guild = getattr(channel, "guild", None)
        self.content = kwargs.get("content")
        self.embeds = [kwargs["embed"]] if kwargs.get("embed") else []
        self.view = kwargs.get("view")
        self.edits = []

    async def edit(self, **kwargs):
        self.edits.append(kwargs)


class FakeChannel:
    def __init__(self, channel_id=900, guild=None):
        self.id = channel_id
        self.guild = guild
        self.name = f"salon-{channel_id}"
        self.sent = []
        self._next = channel_id * 10

    async def send(self, content=None, **kwargs):
        self._next += 1
        message = FakeMessage(self._next, self, content=content, **kwargs)
        self.sent.append(message)
        return message

    def get_partial_message(self, message_id):
        return next(m for m in self.sent if m.id == message_id)


class FakeUser:
    def __init__(self, uid, name="Membre"):
        self.id = uid
        self.name = name
        self.display_name = name
        self.bot = False
        self.mention = f"<@{uid}>"
        self.display_avatar = SimpleNamespace(url="https://cdn.example/avatar.png")
        self.dms = []
        self.guild_permissions = SimpleNamespace(manage_guild=True)

    async def send(self, content=None, **kwargs):
        self.dms.append((content, kwargs))

    def __str__(self):
        return self.name


class FakeGuild:
    def __init__(self):
        self.id = GID
        self.name = "Serveur de test"
        self.channels = {}
        self.members = {}

    def get_channel(self, channel_id):
        return self.channels.get(channel_id)

    def get_member(self, user_id):
        return self.members.get(user_id)


class FakeInteraction:
    def __init__(self, guild, user, *, message=None, interaction_id=777):
        self.id = interaction_id
        self.guild = guild
        self.guild_id = guild.id
        self.user = user
        self.message = message
        self.response = FakeResponse()
        self.followup = SimpleNamespace(send=self._followup)
        self.followups = []

    async def _followup(self, content=None, **kwargs):
        self.followups.append((content, kwargs))


class ClanWarCase(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        for patcher in (mock.patch.object(gs, "_settings", {}),
                        mock.patch.object(gs, "save_settings"),
                        mock.patch.object(clan_war, "send_log")):
            patcher.start()
            self.addCleanup(patcher.stop)

        self.guild = FakeGuild()
        self.clan1 = {"id": "c1", "name": "Alpha", "leader_id": 1, "members": [1, 2]}
        self.clan2 = {"id": "c2", "name": "Bravo", "leader_id": 3, "members": [3, 4]}
        # Le salon de liaison de chaque clan, et le ménage que le cog y fait.
        self.clan_channels = {"c1": FakeChannel(901, self.guild), "c2": FakeChannel(902, self.guild)}
        for channel in self.clan_channels.values():
            self.guild.channels[channel.id] = channel
        self.wiped = []
        self.cog = SimpleNamespace(bot=None, active_war_sessions={},
                                   clan_channel=self.clan_channel,
                                   wipe_clan_channel=self.wipe_clan_channel)
        self.session = clan_war.ClanWarSession(self.cog, self.guild, self.clan1, self.clan2, 2)
        self.cog.active_war_sessions[str(GID)] = self.session

    def clan_channel(self, guild, clan):
        return self.clan_channels.get(clan["id"])

    async def wipe_clan_channel(self, channel, clan, *, keep_menus=True):
        self.wiped.append(channel.id)
        channel.sent.clear()

    def only_embed(self, channel):
        """L'unique message qui reste dans un salon de clan."""
        self.assertEqual(len(channel.sent), 1, [m.embeds[0].title for m in channel.sent])
        return channel.sent[0].embeds[0]

    async def start_match(self):
        """Lance la partie sans toucher aux vocaux ni attendre les 15 secondes."""
        session = self.session
        for name in ("_create_team_voice_channels", "_create_match_text_channel",
                     "_monitor_leader_timeout"):
            patcher = mock.patch.object(session, name, mock.AsyncMock())
            patcher.start()
            self.addCleanup(patcher.stop)
        with mock.patch("asyncio.sleep", mock.AsyncMock()):
            await session._start_match()


class SalonsDeClanTest(ClanWarCase):
    """Les salons de liaison ne gardent qu'un message de guerre à la fois."""

    async def test_le_lancement_efface_la_preparation_et_laisse_le_score(self):
        for channel in self.clan_channels.values():
            await channel.send(embed=discord.Embed(title="préparation"))

        await self.start_match()

        self.assertEqual(sorted(self.wiped), [901, 902], "les deux salons sont nettoyés")
        for channel in self.clan_channels.values():
            embed = self.only_embed(channel)
            self.assertEqual(embed.title, t(GID, "clan.war_score_title"))
            self.assertIn("Alpha", embed.description)

    async def test_le_score_est_modifie_jamais_republie(self):
        await self.start_match()
        messages = [channel.sent[0] for channel in self.clan_channels.values()]

        self.session.clan1_points = 3
        await self.session.update_score_messages()

        for channel, message in zip(self.clan_channels.values(), messages):
            self.assertEqual(len(channel.sent), 1, "aucun nouveau message")
            self.assertIn("`3`", message.edits[-1]["embed"].description)

    async def test_la_fin_ne_laisse_que_le_tableau_des_resultats(self):
        await self.start_match()
        self.session.clan1_points, self.session.clan2_points = 5, 2

        await self.session.finish(t(GID, "clan.war_forfeit_desc", winner="Alpha", loser="Bravo"))

        for channel in self.clan_channels.values():
            embed = self.only_embed(channel)
            self.assertEqual(embed.title, t(GID, "clan.war_result_title"))
            self.assertEqual(embed.fields[0].name, t(GID, "clan.war_result_score"))
            self.assertIn("`5`", embed.fields[0].value)
        self.assertTrue(self.session.ended)

    async def test_capitaines_et_mmr_seulement_quand_ils_sont_allumes(self):
        await self.start_match()
        self.session.players = {"clan1": [1, 2], "clan2": [3, 4]}

        gs.set_mmr_config(GID, enabled=False, captains=False)
        plain = self.session.result_embed("fin")
        self.assertEqual([field.name for field in plain.fields], [t(GID, "clan.war_result_score")])

        gs.set_mmr_config(GID, enabled=True, captains=True)
        gs.set_player_mmr(GID, 1, 1234)
        full = self.session.result_embed("fin")
        names = [field.name for field in full.fields]
        self.assertIn(t(GID, "clan.war_result_captains"), names)
        self.assertIn(t(GID, "clan.war_result_team", clan="Alpha"), names)
        mmr_field = next(f for f in full.fields if f.name == t(GID, "clan.war_result_team", clan="Alpha"))
        self.assertIn("1234", mmr_field.value)
        self.assertIn("<@2>", mmr_field.value, "tous les joueurs de l'équipe sont listés")


class AbandonTest(ClanWarCase):
    async def test_une_partie_lancee_n_est_pas_une_guerre_terminee(self):
        await self.start_match()
        self.assertTrue(self.session.match_started)
        self.assertFalse(self.session.ended, "le ClanWar ne doit pas être considéré comme fini")
        saved = gs.get_clan_war_session(GID)
        self.assertTrue(saved["match_started"], "la session reste sur le disque pendant la partie")

    async def test_le_chef_peut_abandonner_pendant_la_partie(self):
        await self.start_match()
        view = clan_war.AbandonConfirmView(self.session, self.clan1["leader_id"])
        interaction = FakeInteraction(self.guild, FakeUser(1, "Chef"))
        await view.confirm.callback(interaction)

        said = interaction.response.edits[-1]["embed"].description
        self.assertEqual(said, t(GID, "clan.war_abandon_done"))
        self.assertNotEqual(said, t(GID, "clan.war_gone"))
        self.assertTrue(self.session.ended, "l'abandon termine bien la guerre")
        self.assertIsNone(gs.get_clan_war_session(GID))
        self.assertEqual(self.cog.active_war_sessions, {})

    async def test_un_abandon_apres_la_fin_previent_que_le_defi_est_clos(self):
        self.session.ended = True
        view = clan_war.AbandonConfirmView(self.session, self.clan1["leader_id"])
        interaction = FakeInteraction(self.guild, FakeUser(1, "Chef"))
        await view.confirm.callback(interaction)
        self.assertEqual(interaction.response.edits[-1]["embed"].description, t(GID, "clan.war_gone"))

    async def test_la_session_relue_garde_la_partie_en_cours(self):
        await self.start_match()
        self.session.clan1_points = 2
        data = self.session.to_dict()
        data["notification_messages"] = {"111": 222}

        with mock.patch.object(clan_war, "get_clan", lambda gid, cid:
                               self.clan1 if cid == "c1" else self.clan2):
            copy = clan_war.ClanWarSession.from_dict(self.cog, self.guild, data)
        self.assertTrue(copy.match_started)
        self.assertFalse(copy.ended)
        self.assertEqual(copy.clan1_points, 2)
        self.assertEqual(copy.notification_messages, {111: 222},
                         "les identifiants de salon relus sont des entiers")


class TicketTest(ClanWarCase):
    async def asyncSetUp(self):
        await super().asyncSetUp()
        self.staff_channel = FakeChannel(guild=self.guild)
        self.guild.channels[self.staff_channel.id] = self.staff_channel
        gs.set_ticket_config(GID, {"enabled": True, "staff_channel_id": self.staff_channel.id})
        self.member = FakeUser(7, "Joueur")
        self.staff = FakeUser(9, "Modo")
        self.guild.members = {7: self.member, 9: self.staff}
        self.bot = SimpleNamespace(guilds=[self.guild],
                                   get_channel=lambda cid: self.guild.get_channel(cid))

    async def open_ticket(self) -> dict:
        modal = clan_tickets.TicketProblemModal(self.session)
        modal.problem_type._value = "Triche"
        modal.description._value = "L'adversaire triche."
        interaction = FakeInteraction(self.guild, self.member, interaction_id=555)
        await modal.on_submit(interaction)
        return gs.get_clan_ticket(GID, "555")

    async def reply(self, ticket: dict, text: str) -> FakeInteraction:
        message = self.staff_channel.sent[0]
        modal = clan_tickets.TicketResponseModal(ticket["id"], message)
        modal.response._value = text
        interaction = FakeInteraction(self.guild, self.staff, message=message)
        await modal.on_submit(interaction)
        return interaction

    async def test_le_ticket_arrive_dans_le_salon_staff_avec_ses_boutons(self):
        ticket = await self.open_ticket()
        self.assertIsNotNone(ticket)
        self.assertEqual(ticket["user_id"], 7)
        self.assertFalse(ticket["closed"])
        self.assertIsNone(ticket["taken_by"])

        message = self.staff_channel.sent[0]
        self.assertEqual(message.id, ticket["message_id"])
        self.assertIn("Triche", message.embeds[0].title)
        self.assertEqual([item.custom_id for item in message.view.children],
                         ["cyq:clanticket:reply:555", "cyq:clanticket:close:555"])

    async def test_la_premiere_reponse_previent_le_membre_puis_lui_parle(self):
        ticket = await self.open_ticket()
        await self.reply(ticket, "On regarde ça.")

        self.assertEqual(len(self.member.dms), 2)
        taken = self.member.dms[0][1]["embed"]
        self.assertEqual(taken.title, t(GID, "clan.ticket_taken_title"))
        self.assertIn(self.staff.mention, taken.description)

        said = self.member.dms[1][0]
        self.assertTrue(said.startswith(f"**{self.staff.mention}"), said)
        self.assertTrue(said.endswith("On regarde ça."), said)
        self.assertEqual(gs.get_clan_ticket(GID, "555")["taken_by"], 9)

        # La réponse suivante ne répète pas la prise en charge.
        await self.reply(ticket, "C'est réglé.")
        self.assertEqual(len(self.member.dms), 3)
        self.assertTrue(self.member.dms[2][0].endswith("C'est réglé."))

    async def test_le_mp_du_membre_revient_dans_le_salon_staff(self):
        await self.open_ticket()
        message = SimpleNamespace(author=self.member, content="Il recommence !",
                                  channel=mock.Mock(spec=discord.DMChannel),
                                  attachments=[], created_at=discord.utils.utcnow(),
                                  add_reaction=mock.AsyncMock())
        await clan_tickets.forward_member_message(self.bot, message)

        forwarded = self.staff_channel.sent[-1].embeds[0]
        self.assertEqual(forwarded.description, "Il recommence !")
        self.assertIn(str(self.staff_channel.id), forwarded.fields[0].value)
        message.add_reaction.assert_awaited_once()

    async def test_un_ticket_cloture_ne_transmet_plus_rien(self):
        ticket = await self.open_ticket()
        gs.update_clan_ticket(GID, ticket["id"], closed=True)
        message = SimpleNamespace(author=self.member, content="Encore moi",
                                  channel=mock.Mock(spec=discord.DMChannel),
                                  attachments=[], created_at=discord.utils.utcnow(),
                                  add_reaction=mock.AsyncMock())
        await clan_tickets.forward_member_message(self.bot, message)
        self.assertEqual(len(self.staff_channel.sent), 1, "seul le ticket d'origine est là")


if __name__ == "__main__":
    unittest.main()
