"""Le déroulé d'un duel (cogs/duel.py) sur un faux serveur Discord : défi dans
un fil privé, vocal réservé aux joueurs, annonce, répartition par team, fin
du duel — et les limites de Discord respectées dans les 5 langues."""

import os
import re
import shutil
import subprocess
import time
import unittest
from types import SimpleNamespace
from unittest import mock

import discord

import guild_settings as gs
import i18n
from cogs import duel
from i18n import LANGUAGES, t

GID = 1


# ----------------------------------------------------------------------
# Faux Discord : juste ce que le cog utilise
# ----------------------------------------------------------------------
class FakeRole:
    def __init__(self, role_id):
        self.id = role_id


class FakeMember:
    def __init__(self, guild, uid, *, bot=False, admin=False):
        self.guild = guild
        self.id = uid
        self.bot = bot
        self.mention = f"<@{uid}>"
        self.guild_permissions = SimpleNamespace(administrator=admin)

    async def move_to(self, channel, *, reason=None):
        before = next((c for c in self.guild.channels.values() if self in c.members), None)
        if before is not None:
            before.members.remove(self)
        if channel is not None:
            channel.members.append(self)


class FakeMessage:
    def __init__(self, message_id, content=None, **kwargs):
        self.id = message_id
        self.content = content
        self.embed = kwargs.get("embed")
        self.view = kwargs.get("view")
        self.allowed_mentions = kwargs.get("allowed_mentions")
        self.webhook = None
        self.edits = []

    async def edit(self, **kwargs):
        self.edits.append(kwargs)


class FakeWebhook:
    def __init__(self, channel, name):
        self.channel = channel
        self.name = name
        self.token = "jeton"

    async def send(self, content=None, *, wait=False, **kwargs):
        message = FakeMessage(self.channel.guild.new_id(), content, **kwargs)
        message.webhook = self.name
        self.channel.sent.append(message)
        return message

    async def edit_message(self, message_id, **kwargs):
        message = next((m for m in self.channel.sent if m.id == message_id and m.webhook), None)
        if message is None:
            raise discord.NotFound(SimpleNamespace(status=404, reason="Not Found"), "message inconnu")
        message.edits.append(kwargs)


class FakeThread:
    def __init__(self, guild, thread_id, name="fil"):
        self.guild = guild
        self.id = thread_id
        self.name = name
        self.mention = f"<#{thread_id}>"
        self.added = []
        self.sent = []
        self.deleted = False

    async def add_user(self, user):
        self.added.append(user.id)

    async def send(self, content=None, **kwargs):
        message = FakeMessage(self.guild.new_id(), content, **kwargs)
        self.sent.append(message)
        return message

    async def fetch_message(self, message_id):
        return next(m for m in self.sent if m.id == message_id)

    async def delete(self):
        self.deleted = True


class FakeChannel:
    def __init__(self, guild, channel_id, name, kind, *, category=None, overwrites=None, user_limit=0):
        self.guild = guild
        self.id = channel_id
        self.name = name
        self.type = kind
        self.category = category
        self.overwrites = overwrites or {}
        self.user_limit = user_limit
        self.members = []
        self.mention = f"<#{channel_id}>"
        self.thread_kwargs = []
        self.sent = []
        self.hooks = []

    def permissions_for(self, member):
        return discord.Permissions.all()

    async def webhooks(self):
        return list(self.hooks)

    async def create_webhook(self, *, name, avatar=None, reason=None):
        hook = FakeWebhook(self, name)
        self.hooks.append(hook)
        return hook

    async def send(self, content=None, **kwargs):
        message = FakeMessage(self.guild.new_id(), content, **kwargs)
        self.sent.append(message)
        return message

    def get_partial_message(self, message_id):
        return next(m for m in self.sent if m.id == message_id)

    async def delete(self, *, reason=None):
        self.guild.channels.pop(self.id, None)
        self.guild.deleted.append(self)

    async def create_thread(self, **kwargs):
        self.thread_kwargs.append(kwargs)
        thread = FakeThread(self.guild, self.guild.new_id(), kwargs.get("name"))
        self.guild.threads[thread.id] = thread
        return thread


class FakeGuild:
    def __init__(self):
        self.id = GID
        self.name = "Serveur de test"
        self.icon = None
        self.voice_client = None
        self.channels = {}
        self.threads = {}
        self.members = {}
        self.created = []
        self.deleted = []
        self._next_id = 1000
        self.default_role = FakeRole(GID)
        self.me = FakeMember(self, 999, bot=True)

    def new_id(self):
        self._next_id += 1
        return self._next_id

    def add_channel(self, name, kind, **kwargs):
        channel = FakeChannel(self, self.new_id(), name, kind, **kwargs)
        self.channels[channel.id] = channel
        return channel

    def get_channel(self, channel_id):
        return self.channels.get(channel_id)

    def get_thread(self, thread_id):
        return self.threads.get(thread_id)

    async def fetch_channel(self, channel_id):
        raise discord.NotFound(SimpleNamespace(status=404, reason="Not Found"), "introuvable")

    def get_member(self, uid):
        return self.members.get(uid)

    async def create_voice_channel(self, name, *, category=None, overwrites=None, user_limit=0, reason=None):
        channel = self.add_channel(name, discord.ChannelType.voice, category=category,
                                   overwrites=overwrites, user_limit=user_limit)
        self.created.append(channel)
        return channel


class FakeResponse:
    def __init__(self):
        self.send_message = mock.AsyncMock()
        self.edit_message = mock.AsyncMock()
        self.defer = mock.AsyncMock()
        self.send_modal = mock.AsyncMock()

    def is_done(self):
        return False


class FakeInteraction:
    def __init__(self, guild, user, *, message_id=None, channel_id=None):
        self.guild = guild
        self.guild_id = guild.id
        self.user = user
        self.message = SimpleNamespace(id=message_id)
        self.channel_id = channel_id
        self.response = FakeResponse()
        self.edit_original_response = mock.AsyncMock()


async def run_each(items, action, **_kwargs):
    """throttled_each sans les pauses : les tests n'attendent pas."""
    for item in items:
        await action(item)
    return len(items), 0


# ----------------------------------------------------------------------
class DuelCase(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        for patcher in (mock.patch.object(gs, "_settings", {}),
                        mock.patch.object(gs, "save_settings"),
                        mock.patch.object(duel, "throttled_each", run_each)):
            patcher.start()
            self.addCleanup(patcher.stop)

        self.guild = guild = FakeGuild()
        self.category = guild.add_channel("Duels", discord.ChannelType.category)
        self.requests = guild.add_channel("demandes-duel", discord.ChannelType.text)
        gs.set_duel_config(GID, enabled=True, category_id=self.category.id, requests_channel_id=self.requests.id)
        for uid in range(1, 9):
            guild.members[uid] = FakeMember(guild, uid)

        self.alpha = self.make_team("Alpha", "🔴", leader=1, mates=[2], duels=3)
        self.bravo = self.make_team("Bravo", "🔵", leader=3, mates=[4], duels=1)

        self.cog = duel.Duel(SimpleNamespace(guilds=[guild], user=None, add_view=lambda *a, **k: None))
        self.cog.play_announce = mock.AsyncMock()

    def make_team(self, name, color, *, leader, mates, duels):
        team = gs.create_duel_team(GID, name=name, color=color, leader_id=leader, invited=mates, duels=duels)
        for uid in mates:
            gs.accept_duel_invite(GID, team["id"], uid)
        return team

    def member(self, uid):
        return self.guild.members[uid]

    async def join(self, channel, *uids):
        """Un joueur entre dans un vocal : Discord prévient le cog."""
        for uid in uids:
            member = self.member(uid)
            before = next((c for c in self.guild.channels.values() if member in c.members), None)
            await member.move_to(channel)
            await self.cog.on_voice_state_update(member, SimpleNamespace(channel=before),
                                                 SimpleNamespace(channel=channel))

    async def start(self):
        thread = FakeThread(self.guild, self.guild.new_id())
        self.guild.threads[thread.id] = thread
        session = await self.cog.start_duel(self.guild, self.alpha, self.bravo, thread.id)
        return session, self.guild.get_channel(session["voice_id"]), thread

    async def start_and_launch(self):
        session, lobby, thread = await self.start()
        await self.join(lobby, 1, 2, 3, 4)
        return session, lobby, thread


class DuelFlowTest(DuelCase):
    async def test_accepted_duel_opens_a_voice_only_for_its_players(self):
        session, lobby, thread = await self.start()
        self.assertEqual(lobby.name, "duel-01")
        self.assertIs(lobby.category, self.category)
        self.assertEqual(lobby.user_limit, 4)
        everyone = lobby.overwrites[self.guild.default_role]
        self.assertEqual((everyone.view_channel, everyone.connect), (False, False))
        for uid in (1, 2, 3, 4):
            self.assertTrue(lobby.overwrites[self.member(uid)].connect)
        self.assertNotIn(self.member(5), lobby.overwrites)
        self.assertEqual(sorted(thread.added), [1, 2, 3, 4])
        self.assertEqual(session["phase"], "waiting")
        self.cog.play_announce.assert_not_awaited()

    async def test_duel_starts_only_once_everyone_is_there(self):
        session, lobby, _ = await self.start()
        await self.join(lobby, 1, 2, 3)
        self.cog.play_announce.assert_not_awaited()
        self.assertEqual(session["phase"], "waiting")

        await self.join(lobby, 4)
        self.cog.play_announce.assert_awaited_once_with(lobby)
        self.assertEqual(session["phase"], "playing")

        alpha_voice = self.guild.get_channel(session["voice_a_id"])
        bravo_voice = self.guild.get_channel(session["voice_b_id"])
        self.assertEqual((alpha_voice.name, alpha_voice.user_limit), ("🔴 Alpha", 2))
        self.assertEqual((bravo_voice.name, bravo_voice.user_limit), ("🔵 Bravo", 2))
        self.assertEqual(sorted(m.id for m in alpha_voice.members), [1, 2])
        self.assertEqual(sorted(m.id for m in bravo_voice.members), [3, 4])
        self.assertIn(lobby.id, self.guild.channels, "duel-01 reste ouvert pour jouer ensemble")
        self.assertNotIn(self.member(3), alpha_voice.overwrites, "un adversaire n'entre pas dans le vocal de l'autre team")

    async def test_the_split_happens_once_even_if_players_keep_moving(self):
        session, lobby, _ = await self.start_and_launch()
        alpha_voice = self.guild.get_channel(session["voice_a_id"])
        await self.join(lobby, 1)
        await self.join(alpha_voice, 1)
        self.cog.play_announce.assert_awaited_once()
        self.assertEqual(len(self.guild.created), 3)

    async def test_duel_ends_when_voices_are_empty_and_consumes_a_duel(self):
        session, lobby, thread = await self.start_and_launch()
        channels = [session["voice_id"], session["voice_a_id"], session["voice_b_id"]]
        for uid in (1, 2, 3, 4):
            await self.join(None, uid)

        # Le départ du dernier joueur a démarré le délai à l'heure réelle.
        now = time.time()
        await self.cog.tick(self.guild, now=now)
        self.assertIn("1", gs.get_duel_sessions(GID), "on laisse une minute pour revenir")
        await self.cog.tick(self.guild, now=now + duel.EMPTY_GRACE + 1)

        self.assertEqual(gs.get_duel_sessions(GID), {})
        self.assertTrue(all(cid not in self.guild.channels for cid in channels))
        self.assertEqual(gs.get_duel_team(GID, self.alpha["id"])["duels_left"], 2)
        self.assertIsNone(gs.get_duel_team(GID, self.bravo["id"]), "Bravo avait choisi un seul duel")
        self.assertIn(t(GID, "duel.end_finished"), thread.sent[-1].embed.description)

        self.assertFalse(thread.deleted)
        await self.cog.tick(self.guild, now=10**12)
        self.assertTrue(thread.deleted, "le fil disparaît après son délai de lecture")

    async def test_nobody_comes_cancels_without_consuming(self):
        session, lobby, _ = await self.start()
        await self.join(lobby, 1)
        await self.cog.tick(self.guild, now=session["created_at"] + duel.JOIN_TIMEOUT + 1)
        self.assertEqual(gs.get_duel_sessions(GID), {})
        self.assertNotIn(lobby.id, self.guild.channels)
        self.assertEqual(gs.get_duel_team(GID, self.alpha["id"])["duels_left"], 3)
        self.assertIsNotNone(gs.get_duel_team(GID, self.bravo["id"]))

    async def test_restart_during_the_split_counts_as_started(self):
        session, _, _ = await self.start()
        session["voice_a_id"] = 12345
        await self.cog.check_session(self.guild, session, now=0)
        self.assertEqual(session["phase"], "playing")

    async def test_only_the_leads_can_end_the_duel(self):
        session, _, thread = await self.start_and_launch()
        stranger = FakeInteraction(self.guild, self.member(2), channel_id=thread.id)
        await self.cog.stop_from_button(stranger)
        stranger.response.send_message.assert_awaited_once()
        self.assertIn("1", gs.get_duel_sessions(GID))

        lead = FakeInteraction(self.guild, self.member(3), channel_id=thread.id)
        await self.cog.stop_from_button(lead)
        self.assertEqual(gs.get_duel_sessions(GID), {})


class HistoryTest(DuelCase):
    def history(self, message):
        """Le texte du message public du duel : celui de l'embed publié, ou
        celui de la dernière modification."""
        payload = message.edits[-1] if message.edits else {"embed": message.embed}
        embed = payload.get("embed")
        if embed is not None:
            return embed.description or ""
        return payload.get("content") or message.content or ""

    def assert_no_winner_yet(self, message):
        text = self.history(message)
        self.assertIn(t(GID, "duel.live_title"), text)
        self.assertTrue(text.endswith(f"**{t(GID, 'duel.live_winner')}** :"), text)

    async def test_one_message_follows_the_whole_duel_rematch_included(self):
        session, lobby, thread = await self.start()
        self.assertEqual(len(self.requests.sent), 1)
        message = self.requests.sent[0]
        self.assertEqual(message.webhook, "DuelBot", "envoyé par le webhook, pas par le bot")
        self.assertFalse(message.allowed_mentions.users, "les leads sont cités sans être pingés")
        self.assertIn("> <@1> **(Alpha)** Vs <@3> **(Bravo)**", self.history(message))
        self.assert_no_winner_yet(message)

        await self.join(lobby, 1, 2, 3, 4)
        self.assert_no_winner_yet(message)

        await self.cog.stop_from_button(FakeInteraction(self.guild, self.member(1), channel_id=thread.id))
        self.assert_no_winner_yet(message)
        end = thread.sent[-1]
        self.assertEqual({c.custom_id for c in end.view.children},
                         {"cyq:duel:rematch", "cyq:duel:close", "cyq:duel:win_a", "cyq:duel:win_b"})

        # Un joueur qui n'est pas lead ne vote pas ; un lead seul ne suffit pas.
        stranger = FakeInteraction(self.guild, self.member(2), message_id=end.id, channel_id=thread.id)
        await self.cog.vote_winner(stranger, "a")
        self.assert_no_winner_yet(message)
        await self.cog.vote_winner(FakeInteraction(self.guild, self.member(1), message_id=end.id,
                                                   channel_id=thread.id), "a")
        self.assert_no_winner_yet(message)
        # Bravo (1 duel) est dissoute à la fin : son lead vote quand même.
        await self.cog.vote_winner(FakeInteraction(self.guild, self.member(3), message_id=end.id,
                                                   channel_id=thread.id), "a")
        text = self.history(message)
        self.assertIn(t(GID, "duel.live_done"), text)
        self.assertTrue(text.endswith(f"**{t(GID, 'duel.live_winner')}** : <@1> **(Alpha)**"), text)

        for uid in (1, 2, 3, 4):
            await self.cog.vote_rematch(FakeInteraction(self.guild, self.member(uid), message_id=end.id,
                                                        channel_id=thread.id))
        self.assertEqual(len(self.requests.sent), 1, "la relance modifie le même message")
        self.assert_no_winner_yet(message)
        self.assertEqual(len(self.requests.hooks), 1, "un seul webhook DuelBot par salon")

    async def test_an_existing_duelbot_webhook_is_reused(self):
        existing = await self.requests.create_webhook(name="DuelBot")
        await self.start()
        self.assertEqual(self.requests.hooks, [existing])

    async def test_without_manage_webhooks_the_bot_posts_the_history_itself(self):
        async def refused(**_kwargs):
            raise discord.Forbidden(SimpleNamespace(status=403, reason="Forbidden"), "webhook refusé")

        with mock.patch.object(self.requests, "create_webhook", refused):
            await self.start()
            self.assertEqual(len(self.requests.sent), 1, "l'historique est publié quand même")
            message = self.requests.sent[0]
            self.assertIsNone(message.webhook, "publié par le bot, faute de webhook")
            self.assertIn("> <@1> **(Alpha)** Vs <@3> **(Bravo)**", self.history(message))

            record = next(iter(gs.get_duel_history(GID).values()))
            record["games"][-1].update(state="won", winner="a")
            await self.cog.update_history(self.guild, record)
            self.assertEqual(len(self.requests.sent), 1, "le même message est modifié")
            self.assertIn(t(GID, "duel.live_done"), self.history(message))

    async def test_an_old_history_message_is_replaced(self):
        _, lobby, _ = await self.start()
        record = next(iter(gs.get_duel_history(GID).values()))
        old = await self.requests.send(embed="ancien historique")
        record["message_id"] = old.id
        await self.join(lobby, 1, 2, 3, 4)
        self.assertNotEqual(record["message_id"], old.id)
        self.assertEqual(self.requests.sent[-1].webhook, "DuelBot")

    async def test_an_admin_decides_alone_and_a_deleted_thread_closes_the_vote(self):
        _, lobby, thread = await self.start()
        await self.join(lobby, 1, 2, 3, 4)
        await self.cog.stop_from_button(FakeInteraction(self.guild, self.member(1), channel_id=thread.id))
        message, end = self.requests.sent[0], thread.sent[-1]

        await self.cog.tick(self.guild, now=10**12)
        self.assertIn(t(GID, "duel.live_undecided"), self.history(message))

        late = FakeInteraction(self.guild, FakeMember(self.guild, 50, admin=True), message_id=end.id,
                               channel_id=thread.id)
        await self.cog.vote_winner(late, "b")
        late.response.send_message.assert_awaited_once()
        self.assertIn(t(GID, "duel.live_undecided"), self.history(message))

    async def test_end_button_deletes_the_thread_and_updates_the_history(self):
        _, lobby, thread = await self.start()
        await self.join(lobby, 1, 2, 3, 4)
        await self.cog.stop_from_button(FakeInteraction(self.guild, self.member(1), channel_id=thread.id))
        message, end = self.requests.sent[0], thread.sent[-1]
        self.assertIn("cyq:duel:close", {c.custom_id for c in end.view.children})

        player = FakeInteraction(self.guild, self.member(2), message_id=end.id, channel_id=thread.id)
        await self.cog.close_from_button(player)
        player.response.send_message.assert_awaited_once()
        self.assertFalse(thread.deleted, "un joueur qui n'est pas lead ne ferme pas le fil")

        lead = FakeInteraction(self.guild, self.member(3), message_id=end.id, channel_id=thread.id)
        await self.cog.close_from_button(lead)
        self.assertTrue(thread.deleted)
        self.assertIn(t(GID, "duel.live_undecided"), self.history(message))
        self.assertNotIn((GID, thread.id), self.cog._rematch)

    async def test_end_button_refuses_while_a_rematch_is_playing(self):
        _, lobby, thread = await self.start()
        await self.join(lobby, 1, 2, 3, 4)
        await self.cog.stop_from_button(FakeInteraction(self.guild, self.member(1), channel_id=thread.id))
        end = thread.sent[-1]
        for uid in (1, 2, 3, 4):
            await self.cog.vote_rematch(FakeInteraction(self.guild, self.member(uid), message_id=end.id,
                                                        channel_id=thread.id))
        lead = FakeInteraction(self.guild, self.member(1), message_id=end.id, channel_id=thread.id)
        await self.cog.close_from_button(lead)
        lead.response.send_message.assert_awaited_once()
        self.assertFalse(thread.deleted)

    async def test_nobody_comes_marks_the_game_cancelled(self):
        session, lobby, _ = await self.start()
        await self.cog.tick(self.guild, now=session["created_at"] + duel.JOIN_TIMEOUT + 1)
        text = self.history(self.requests.sent[0])
        self.assertIn(t(GID, "duel.live_done"), text)
        self.assertIn(t(GID, "duel.live_cancelled"), text)


class ChallengeTest(DuelCase):
    async def test_challenge_rules(self):
        solo = self.make_team("Charlie", "🟢", leader=5, mates=[], duels=1)
        pending = gs.create_duel_team(GID, name="Delta", color="🟡", leader_id=6, invited=[7], duels=1)
        rule = duel.challenge_error
        self.assertIsNone(rule(GID, self.alpha, self.bravo, 1))
        self.assertEqual(rule(GID, None, self.bravo, 8), "duel.err_no_team")
        self.assertEqual(rule(GID, self.alpha, self.bravo, 2), "duel.err_lead_only")
        self.assertEqual(rule(GID, self.alpha, self.alpha, 1), "duel.err_self")
        self.assertEqual(rule(GID, self.alpha, None, 1), "duel.err_target_gone")
        self.assertEqual(rule(GID, self.alpha, solo, 1), "duel.err_size")
        self.assertEqual(rule(GID, self.alpha, pending, 1), "duel.err_target_pending")
        self.assertEqual(rule(GID, pending, self.alpha, 6), "duel.err_team_pending")
        await self.start()
        self.assertEqual(rule(GID, self.alpha, self.bravo, 1), "duel.err_in_duel")
        self.assertEqual(rule(GID, self.bravo, self.alpha, 3), "duel.err_in_duel")
        self.assertEqual(rule(GID, solo, self.alpha, 5), "duel.err_size")

    async def test_challenge_goes_to_a_private_thread_seen_only_by_the_leads(self):
        interaction = FakeInteraction(self.guild, self.member(1))
        await self.cog.send_challenge(interaction, self.bravo, from_panel=False)

        options = self.requests.thread_kwargs[0]
        self.assertEqual(options["type"], discord.ChannelType.private_thread)
        self.assertFalse(options["invitable"])
        thread = next(iter(self.guild.threads.values()))
        self.assertEqual(sorted(thread.added), [1, 3])
        request = gs.get_duel_requests(GID)[0]
        self.assertEqual((request["from_team"], request["to_team"]), (self.alpha["id"], self.bravo["id"]))
        self.assertEqual(thread.sent[0].content, "<@3>")
        players = thread.sent[0].embed.fields[0].value
        self.assertIn("<@1>", players)
        self.assertIn("<@2>", players)
        interaction.edit_original_response.assert_awaited_once()

        again = FakeInteraction(self.guild, self.member(1))
        await self.cog.send_challenge(again, self.bravo, from_panel=False)
        self.assertEqual(len(gs.get_duel_requests(GID)), 1, "pas de second fil pour le même défi")
        again.response.send_message.assert_awaited_once()

    async def test_only_the_challenged_lead_answers_and_accepting_starts_the_duel(self):
        await self.cog.send_challenge(FakeInteraction(self.guild, self.member(1)), self.bravo, from_panel=False)
        thread = next(iter(self.guild.threads.values()))
        message_id = thread.sent[0].id

        for uid in (1, 4, 8):
            intruder = FakeInteraction(self.guild, self.member(uid), message_id=message_id, channel_id=thread.id)
            await self.cog.answer_challenge(intruder, accepted=True)
            intruder.response.send_message.assert_awaited_once_with(t(GID, "duel.req_not_for_you"), ephemeral=True)
        self.assertEqual(gs.get_duel_sessions(GID), {})

        lead = FakeInteraction(self.guild, self.member(3), message_id=message_id, channel_id=thread.id)
        await self.cog.answer_challenge(lead, accepted=True)
        self.assertEqual(gs.get_duel_requests(GID), [])
        session = gs.get_duel_sessions(GID)["1"]
        self.assertEqual(session["thread_id"], thread.id, "le fil du défi devient celui du duel")
        self.assertEqual(sorted(set(thread.added)), [1, 2, 3, 4])

    async def test_declining_closes_the_thread_later(self):
        await self.cog.send_challenge(FakeInteraction(self.guild, self.member(1)), self.bravo, from_panel=False)
        thread = next(iter(self.guild.threads.values()))
        lead = FakeInteraction(self.guild, self.member(3), message_id=thread.sent[0].id, channel_id=thread.id)
        await self.cog.answer_challenge(lead, accepted=False)
        self.assertEqual(gs.get_duel_requests(GID), [])
        self.assertEqual(gs.get_duel_sessions(GID), {})
        self.assertIn("<@1>", thread.sent[-1].content, "le lead qui a défié est prévenu")
        await self.cog.tick(self.guild, now=10**12)
        self.assertTrue(thread.deleted)

    async def test_disabled_system_refuses_everything(self):
        gs.set_duel_config(GID, enabled=False)
        interaction = FakeInteraction(self.guild, self.member(1))
        await self.cog.send_challenge(interaction, self.bravo, from_panel=False)
        interaction.response.send_message.assert_awaited_once()
        self.assertEqual(self.requests.thread_kwargs, [])


class TeamInviteTest(DuelCase):
    async def test_builder_creates_a_pending_team_and_invites_in_a_private_thread(self):
        builder = duel.TeamBuilderView(self.cog, GID, 5)
        builder.lead_added, builder.name, builder.mates, builder.duels = True, "Charlie", [6, 7], 0
        interaction = FakeInteraction(self.guild, self.member(5))
        await self.cog.finish_team(interaction, builder)

        team = gs.duel_team_named(GID, "charlie")
        self.assertEqual((team["status"], team["members"], team["invited"]), ("pending", [5], [6, 7]))
        thread = self.guild.threads[team["invite_thread_id"]]
        self.assertEqual(sorted(thread.added), [5, 6, 7])
        message_id = team["invite_message_id"]

        stranger = FakeInteraction(self.guild, self.member(8), message_id=message_id)
        await self.cog.answer_invite(stranger, accepted=True)
        stranger.response.send_message.assert_awaited_once_with(t(GID, "duel.inv_not_for_you"), ephemeral=True)

        await self.cog.answer_invite(FakeInteraction(self.guild, self.member(6), message_id=message_id), accepted=True)
        self.assertEqual(team["status"], "pending")
        await self.cog.answer_invite(FakeInteraction(self.guild, self.member(7), message_id=message_id), accepted=True)
        self.assertEqual((team["status"], team["members"]), ("ready", [5, 6, 7]))

    async def test_one_refusal_cancels_the_team(self):
        team = gs.create_duel_team(GID, name="Echo", color="🟣", leader_id=5, invited=[6], duels=1)
        gs.set_duel_team_fields(GID, team["id"], invite_message_id=77, invite_thread_id=None)
        await self.cog.answer_invite(FakeInteraction(self.guild, self.member(6), message_id=77), accepted=False)
        self.assertIsNone(gs.duel_team_named(GID, "Echo"))

    async def test_unanswered_invitations_expire(self):
        team = gs.create_duel_team(GID, name="Echo", color="🟣", leader_id=5, invited=[6], duels=1)
        await self.cog.tick(self.guild, now=team["created_at"] + duel.INVITE_TTL + 1)
        self.assertIsNone(gs.duel_team_named(GID, "Echo"))
        self.assertIsNotNone(gs.get_duel_team(GID, self.alpha["id"]), "une team prête n'expire pas")


class DiscordLimitsTest(DuelCase):
    """Discord refuse un message entier pour un libellé trop long : on
    vérifie chaque bouton, menu et embed, dans chaque langue."""

    def component_problems(self, view):
        problems = []
        for item in view.children:
            label = getattr(item, "label", None) or ""
            placeholder = getattr(item, "placeholder", None) or ""
            options = getattr(item, "options", None) or []
            if len(label) > 80 or len(placeholder) > 150 or len(options) > 25:
                problems.append(label or placeholder)
            if len(getattr(item, "custom_id", "") or "") > 100:
                problems.append(item.custom_id)
            problems += [o.label for o in options if len(o.label) > 100 or len(o.description or "") > 100]
        return problems

    def embed_problems(self, embed):
        texts = [embed.title or "", embed.description or "", embed.footer.text or ""]
        texts += [field.name for field in embed.fields] + [field.value for field in embed.fields]
        problems = [text[:60] for text in texts
                    if re.search(r"\{\w+\}", text) or re.search(r"\bduel\.[a-z_]+", text)]
        if (len(embed) > 6000 or len(embed.title or "") > 256 or len(embed.description or "") > 4096
                or any(len(f.name) > 256 or len(f.value) > 1024 for f in embed.fields)):
            problems.append(f"embed trop long : {embed.title}")
        return problems

    async def test_every_panel_fits_in_every_language(self):
        big = self.make_team("Zzzzzzzzzzzzzzzzzzzzzzzz", "🟦", leader=5, mates=[6, 7, 8, 9], duels=5)
        session, _, _ = await self.start_and_launch()
        for lang in LANGUAGES:
            with self.subTest(lang=lang), mock.patch.dict(i18n._guild_langs, {GID: lang}):
                builder = duel.TeamBuilderView(self.cog, GID, 5)
                builder.lead_added, builder.name, builder.mates = True, big["name"], [6, 7, 8, 9]
                views = [
                    builder, duel.MatesPicker(builder), duel.DuelConfigView(self.guild),
                    duel.DuelPanelView(self.cog, GID, 1), duel.DuelPanelView(self.cog, GID, 2),
                    duel.DuelPanelView(self.cog, GID, 8),
                    duel.TeamInviteView(self.cog, GID), duel.DuelAnswerView(self.cog, GID),
                    duel.DuelEndView(self.cog, GID),
                    duel.DuelRematchView(self.cog, GID, 10, 10, labels=duel.winner_labels(GID, session)),
                ]
                for view in views:
                    self.assertEqual(self.component_problems(view), [], type(view).__name__)

                self.assertLessEqual(len(duel.TeamNameModal(builder).title), 45)

                panels = [
                    builder.embed("notice"), duel.team_embed(GID, big), duel.invite_embed(GID, big),
                    duel.request_embed(GID, big, big, duel.MAX_ROUNDS), duel.lobby_embed(GID, session),
                    duel.started_embed(GID, session), duel.panel_embed(GID, 1), duel.panel_embed(GID, 8),
                    duel.config_embed(self.guild),
                ]
                for embed in panels:
                    self.assertEqual(self.embed_problems(embed), [])
                record = next(iter(gs.get_duel_history(GID).values()))
                for game in ({"state": "waiting"}, {"state": "won", "winner": "b"},
                             {"state": "cancelled"}, {"state": "undecided"}):
                    text = duel.live_message(GID, {**record, "name_b": big["name"], "games": [game]})
                    self.assertLessEqual(len(text), 2000)
                    self.assertNotRegex(text, r"\{\w+\}|\bduel\.[a-z_]+")
                for key in ("err_size", "err_size_max", "err_already_sent", "err_target_in_duel"):
                    text = duel.error_text(GID, f"duel.{key}", big, self.alpha)
                    self.assertNotRegex(text, r"\{\w+\}")


class AnnounceTest(unittest.TestCase):
    def test_duel_announce_exists_in_every_language(self):
        self.assertEqual(set(duel.DUEL_ANNOUNCE_FILES), set(LANGUAGES))
        for lang, path in duel.DUEL_ANNOUNCE_FILES.items():
            with self.subTest(lang=lang):
                self.assertTrue(os.path.exists(path), path)
                self.assertGreater(os.path.getsize(path), 1000)

    def test_announce_follows_the_server_language_with_a_fallback(self):
        for lang in LANGUAGES:
            with mock.patch.dict(i18n._guild_langs, {GID: lang}):
                self.assertEqual(duel.duel_announce_path(GID), duel.DUEL_ANNOUNCE_FILES[lang])
        with mock.patch.object(duel.os.path, "exists", return_value=False):
            self.assertEqual(duel.duel_announce_path(GID), duel.voice_announce_path(GID))

    @unittest.skipUnless(shutil.which("ffprobe"), "ffprobe absent")
    def test_announce_files_are_readable_audio(self):
        for path in duel.DUEL_ANNOUNCE_FILES.values():
            with self.subTest(path=path):
                seconds = subprocess.run(
                    ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", path],
                    capture_output=True, text=True, check=True,
                ).stdout.strip()
                self.assertGreater(float(seconds), 2)


if __name__ == "__main__":
    unittest.main()
