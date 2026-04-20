from __future__ import annotations

import unittest
from tempfile import TemporaryDirectory
from pathlib import Path

from exile_bridge.identity import IdentityMap
from exile_bridge.falloff_server import FalloffServer
from exile_bridge.models import AudioState
from exile_bridge.parser import parse_players
from exile_bridge.proximity import ProximityConfig, ProximityEngine
from exile_bridge.rcon_client import build_evrima_auth_packet, build_evrima_command_packet
from exile_bridge.verification import normalize_mumble_text, parse_theisle_chat_line, upsert_identity_mapping


ROOT = Path(__file__).resolve().parents[1]


class ParserTests(unittest.TestCase):
    def test_sample_playerdata_parses_positions(self) -> None:
        text = (ROOT / "fixtures" / "sample_playerdata.txt").read_text(encoding="utf-8")
        players = parse_players(text)
        self.assertEqual(len(players), 3)
        self.assertEqual(players[0].steam_id, "76561198000000001")
        self.assertIsNotNone(players[0].position)
        self.assertEqual(players[0].position.x, 1000.0)

    def test_json_playerdetails_parses(self) -> None:
        text = '{"playerDetails":[{"playerName":"A","steamId":"1","PlayerLocation":{"X":1,"Y":2,"Z":3}}]}'
        players = parse_players(text)
        self.assertEqual(len(players), 1)
        self.assertEqual(players[0].name, "A")
        self.assertEqual(players[0].position.y, 2.0)

    def test_rcon_playerlist_pairs_parse(self) -> None:
        text = """===== COMMAND: PlayerList =====
PlayerList
76561198000001001,
TestPlayer,
"""
        players = parse_players(text)
        self.assertEqual(len(players), 1)
        self.assertEqual(players[0].steam_id, "76561198000001001")
        self.assertEqual(players[0].name, "TestPlayer")

    def test_rcon_playerdata_playerid_and_location_parse(self) -> None:
        text = "Name: TestPlayer, PlayerID: 76561198000001001, Gender: Female, Location: X=483129.590 Y=-76220.472 Z=23256.202, Class: Dryosaurus"
        players = parse_players(text)
        self.assertEqual(len(players), 1)
        self.assertEqual(players[0].steam_id, "76561198000001001")
        self.assertEqual(players[0].name, "TestPlayer")
        self.assertIsNotNone(players[0].position)
        self.assertAlmostEqual(players[0].position.x, 483129.590)


class ProximityTests(unittest.TestCase):
    def test_audio_matrix_hears_near_not_far(self) -> None:
        text = (ROOT / "fixtures" / "sample_playerdata.txt").read_text(encoding="utf-8")
        players = parse_players(text)
        identity = IdentityMap.load(ROOT / "identity_map.example.json")
        players = [identity.apply(player) for player in players]
        engine = ProximityEngine(
            ProximityConfig(
                audible_distance=30000.0,
                fade_start=12000.0,
                shard_size=45000.0,
                channel_prefix="TransportShard_",
                unknown_channel="Lobby",
                hash_salt="test",
                pan_width=20000.0,
            )
        )
        matrix = engine.audio_matrix(players)
        near_hash = "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
        self.assertIn(near_hash, matrix)
        heard = {state.speaker_hash for state in matrix[near_hash]}
        self.assertIn("bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb", heard)
        self.assertNotIn("cccccccccccccccccccccccccccccccccccccccc", heard)


class RconPacketTests(unittest.TestCase):
    def test_evrima_auth_packet(self) -> None:
        self.assertEqual(build_evrima_auth_packet("pw"), b"\x01pw\x00")

    def test_evrima_command_alias_packets(self) -> None:
        self.assertEqual(build_evrima_command_packet("PlayerList"), b"\x02\x40\x00")
        self.assertEqual(build_evrima_command_packet("Get Player List"), b"\x02\x40\x00")
        self.assertEqual(build_evrima_command_packet("GetQueueStatus"), b"\x02\x93\x00")

    def test_evrima_command_packet_with_args(self) -> None:
        self.assertEqual(build_evrima_command_packet("announce Hello dinos"), b"\x02\x10Hello dinos\x00")


class FalloffServerTests(unittest.TestCase):
    def test_update2_format_empty_clears_client_audio(self) -> None:
        self.assertEqual(FalloffServer._format_update([]), "UPDATE2\n")

    def test_update2_format_gain_pan_payload(self) -> None:
        states = [AudioState("abcdef", 0.5, -0.25)]
        self.assertEqual(FalloffServer._format_update(states), "UPDATE2 abcdef 0.5000 -0.2500\n")


class VerificationTests(unittest.TestCase):
    def test_normalize_mumble_text_strips_html(self) -> None:
        self.assertEqual(normalize_mumble_text("<b>!verify</b>&nbsp;123456"), "!verify 123456")

    def test_parse_theisle_chat_line(self) -> None:
        line = "[2026.04.19-22.06.16:245][755]LogTheIsleChatData: [2026.04.19-22.06.16] [Spatial] [GROUP-610886864] TestPlayer [76561198000001001]: !Verify test"
        message = parse_theisle_chat_line(line)
        self.assertIsNotNone(message)
        self.assertEqual(message.channel, "Spatial")
        self.assertEqual(message.group, "GROUP-610886864")
        self.assertEqual(message.game_name, "TestPlayer")
        self.assertEqual(message.steam_id, "76561198000001001")
        self.assertEqual(message.text, "!Verify test")

    def test_upsert_identity_mapping_creates_and_updates_player(self) -> None:
        with TemporaryDirectory() as tmp:
            path = Path(tmp) / "identity_map.local.json"
            upsert_identity_mapping(
                path,
                steam_id="76561198000001001",
                game_name="TestPlayer",
                mumble_name="TestPlayer",
                mumble_hash="firsthash",
            )
            identity = IdentityMap.load(path)
            self.assertEqual(identity.by_steam["76561198000001001"]["mumble_hash"], "firsthash")

            upsert_identity_mapping(
                path,
                steam_id="76561198000001001",
                game_name="TestPlayer",
                mumble_name="TestPlayerNew",
                mumble_hash="secondhash",
            )
            identity = IdentityMap.load(path)
            self.assertEqual(len(identity.by_steam), 1)
            self.assertEqual(identity.by_steam["76561198000001001"]["mumble_name"], "TestPlayerNew")
            self.assertEqual(identity.by_steam["76561198000001001"]["mumble_hash"], "secondhash")


if __name__ == "__main__":
    unittest.main()
