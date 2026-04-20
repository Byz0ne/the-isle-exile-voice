from __future__ import annotations

import time
from pathlib import Path

from .config import AppConfig
from .falloff_server import FalloffServer, FalloffSettings
from .identity import IdentityMap
from .models import Player
from .mumble import MumbleAdapter, make_mumble_adapter
from .parser import parse_players
from .proximity import ProximityConfig, ProximityEngine
from .rcon_client import RconSettings, TheIsleRconClient
from .verification import VerificationManager, VerifySettings


class Bridge:
    def __init__(self, config: AppConfig):
        self.config = config
        self.mode = str(config.get("mode", "mock")).lower()
        self.poll_interval = float(config.get("poll_interval_sec", 3.0))
        self.identity_path = config.path_value("identity_map_file", "identity_map.example.json")
        self.identity = IdentityMap.load(self.identity_path)
        self.proximity = ProximityEngine(ProximityConfig.from_dict(config.get("proximity", {})))
        mumble_config = config.get("mumble", {})
        self.mumble: MumbleAdapter = make_mumble_adapter(mumble_config, str(mumble_config.get("root_channel", "The Isle - Lobby")))
        self.falloff = FalloffServer(FalloffSettings.from_dict(config.get("falloff_server", {})))
        self.verifier = VerificationManager(
            VerifySettings.from_config(config),
            self.identity_path,
            RconSettings.from_dict(config.get("rcon", {})),
            plugin_hashes=self.falloff.connected_hashes,
        )

    def run(self, once: bool = False) -> None:
        self.falloff.start()
        self.verifier.start()
        try:
            while True:
                self.tick()
                if once:
                    break
                time.sleep(self.poll_interval)
        finally:
            self.verifier.stop()
            self.falloff.stop()

    def tick(self) -> None:
        players = self.fetch_players()
        self.verifier.update_players(players)
        self.verifier.poll_game_chat()
        self.identity = IdentityMap.load(self.identity_path)
        players = [self.identity.apply(player) for player in players]
        assignments = self.proximity.assign_channels(players)
        matrix = self.proximity.audio_matrix(players)

        mapped = sum(1 for p in players if p.mumble_hash)
        print(
            f"[bridge] parsed {len(players)} players; {sum(1 for p in players if p.position)} with positions; "
            f"{mapped} mapped to mumble hashes; {self.falloff.connected_count()} plugin clients; "
            f"{len(matrix)} falloff listeners"
        )
        self.mumble.sync(players, assignments)
        self.falloff.publish(matrix)

        if matrix:
            for listener_hash, states in matrix.items():
                summary = ", ".join(f"{s.speaker_hash[:8]} gain={s.gain:.2f} pan={s.pan:.2f}" for s in states)
                print(f"[falloff:dry-view] {listener_hash[:8]} hears {summary or 'nobody'}")

    def fetch_players(self) -> list[Player]:
        if self.mode == "mock":
            fixture = self.config.path_value("mock.fixture", "fixtures/sample_playerdata.txt")
            return parse_players(fixture.read_text(encoding="utf-8"))
        if self.mode == "rcon":
            return self._fetch_players_rcon()
        raise ValueError(f"Unknown mode: {self.mode}")

    def _fetch_players_rcon(self) -> list[Player]:
        settings = RconSettings.from_dict(self.config.get("rcon", {}))
        commands = list(self.config.get("rcon.commands", ["PlayerData"]))
        transcript: list[str] = []
        with TheIsleRconClient(settings) as client:
            for command in commands:
                response = client.command(str(command))
                transcript.append(f"===== {command} =====\n{response}")
        return parse_players("\n".join(transcript))


def probe_rcon(config: AppConfig) -> Path:
    settings = RconSettings.from_dict(config.get("rcon", {}))
    commands = list(config.get("rcon.commands", []))
    log_dir = config.ensure_log_dir()
    out_path = log_dir / f"rcon_probe_{time.strftime('%Y%m%d_%H%M%S')}.txt"

    lines: list[str] = []
    with TheIsleRconClient(settings) as client:
        lines.append("===== AUTH/BANNER =====")
        for command in commands:
            lines.append(f"===== COMMAND: {command} =====")
            try:
                lines.append(client.command(str(command)))
            except Exception as exc:
                lines.append(f"ERROR: {exc}")
    out_path.write_text("\n".join(lines), encoding="utf-8")
    return out_path
