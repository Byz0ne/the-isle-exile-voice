from __future__ import annotations

import html
import json
import re
import secrets
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from .config import AppConfig
from .models import Player
from .mumble import IceSettings, build_slice_args
from .rcon_client import RconSettings, TheIsleRconClient

VERIFY_CODE_RE = re.compile(r"^\d{6}$")
HTML_TAG_RE = re.compile(r"<[^>]+>")


@dataclass(frozen=True)
class VerifySettings:
    enabled: bool
    command: str
    code_ttl_sec: int
    ice: IceSettings
    game_chat_enabled: bool
    game_command: str
    game_log_file: Path
    game_code_mumble_fallback: bool
    game_code_display_sec: int
    game_code_repeat_interval_sec: int
    game_message_prefix: str

    @classmethod
    def from_config(cls, config: AppConfig) -> "VerifySettings":
        data = config.get("verify", {})
        mumble_data = config.get("mumble", {})
        ice_data = data.get("ice") or mumble_data.get("ice", {})
        return cls(
            enabled=bool(data.get("enabled", False)),
            command=str(data.get("command", "!verify")).lower(),
            code_ttl_sec=int(data.get("code_ttl_sec", 300)),
            ice=IceSettings.from_dict(ice_data),
            game_chat_enabled=bool(data.get("game_chat_enabled", True)),
            game_command=str(data.get("game_command", data.get("command", "!verify"))).lower(),
            game_log_file=config.path_value(
                "verify.game_log_file",
                "/opt/theisle/server/TheIsle/Saved/Logs/TheIsle.log",
            ),
            game_code_mumble_fallback=bool(data.get("game_code_mumble_fallback", True)),
            game_code_display_sec=int(data.get("game_code_display_sec", 60)),
            game_code_repeat_interval_sec=int(data.get("game_code_repeat_interval_sec", 8)),
            game_message_prefix=str(data.get("game_message_prefix", "\n\n")),
        )


@dataclass
class PendingVerification:
    code: str
    steam_id: str
    game_name: str
    mumble_name: str
    mumble_hash: str
    expires_at: float


@dataclass(frozen=True)
class GameChatMessage:
    channel: str
    group: str
    game_name: str
    steam_id: str
    text: str


class VerificationManager:
    def __init__(
        self,
        settings: VerifySettings,
        identity_path: Path,
        rcon_settings: RconSettings,
        plugin_hashes: Callable[[], list[str]] | None = None,
        now: Callable[[], float] = time.time,
    ):
        self.settings = settings
        self.identity_path = identity_path
        self.rcon_settings = rcon_settings
        self.plugin_hashes = plugin_hashes or (lambda: [])
        self.now = now
        self._players_by_name: dict[str, Player] = {}
        self._pending: dict[str, PendingVerification] = {}
        self._lock = threading.Lock()
        self._ice = None
        self._murmur = None
        self._communicator = None
        self._adapter = None
        self._server = None
        self._servers = []
        self._callback_prx = None
        self._game_log_offset: int | None = None

    def start(self) -> None:
        if not self.settings.enabled:
            return
        self._init_game_chat_log()
        self._connect_ice_callback()
        print(f"[verify] listening for Mumble chat command {self.settings.command!r}")
        if self.settings.game_chat_enabled:
            print(f"[verify] watching The Isle chat log: {self.settings.game_log_file}")

    def stop(self) -> None:
        if self._callback_prx is not None:
            for server in self._servers:
                try:
                    server.removeCallback(self._callback_prx)
                except Exception:
                    pass
        if self._communicator is not None:
            try:
                self._communicator.destroy()
            except Exception:
                pass

    def update_players(self, players: list[Player]) -> None:
        with self._lock:
            self._players_by_name = {p.name.lower(): p for p in players if p.name and p.steam_id}
            self._expire_locked()

    def poll_game_chat(self) -> None:
        if not self.settings.enabled or not self.settings.game_chat_enabled:
            return

        path = self.settings.game_log_file
        try:
            size = path.stat().st_size
        except OSError:
            return

        if self._game_log_offset is None:
            self._game_log_offset = size
            return
        if size < self._game_log_offset:
            self._game_log_offset = 0

        try:
            with path.open("r", encoding="utf-8", errors="replace") as f:
                f.seek(self._game_log_offset)
                chunk = f.read()
                self._game_log_offset = f.tell()
        except OSError as exc:
            print(f"[verify] could not read game chat log: {exc}")
            return

        for line in chunk.splitlines():
            message = parse_theisle_chat_line(line)
            if message is not None:
                self.handle_game_chat_message(message)

    def handle_game_chat_message(self, message: GameChatMessage) -> None:
        text = normalize_mumble_text(message.text)
        command, _, _arg = text.partition(" ")
        if command.lower() not in {self.settings.game_command, self.settings.command, "!verifiy"}:
            return

        print(
            f"[verify] game chat command from {message.game_name}/{message.steam_id} "
            f"channel={message.channel!r} text={text!r}"
        )
        if self._is_already_verified(message.steam_id):
            self._send_game_message(
                message.steam_id,
                f"{self.settings.game_message_prefix}Exile Voice: you are already verified. If you need help contact staff in Discord.",
            )
            return

        player = Player(source_id=message.steam_id, name=message.game_name, steam_id=message.steam_id)
        self._issue_code_for_player(player, mumble_name="", mumble_hash="", mumble_session=None)

    def handle_mumble_message(self, state, message_text: str) -> None:
        if not self.settings.enabled:
            return

        text = normalize_mumble_text(message_text)
        command, _, arg = text.partition(" ")
        if command.lower() != self.settings.command:
            return

        session = int(getattr(state, "session", -1))
        mumble_name = str(getattr(state, "name", "")).strip()
        mumble_hash = str(getattr(state, "hash", "")).strip().lower()
        arg = arg.strip()
        print(f"[verify] chat command from {mumble_name or '(unknown)'} hash={mumble_hash[:8] or '-'} text={text!r}")

        if not mumble_hash:
            mumble_hash = self._lookup_hash_for_session(session)
            if mumble_hash:
                print(f"[verify] resolved hash {mumble_hash[:8]} for session {session} via Ice getState")

        if not mumble_hash:
            print(f"[verify] cannot continue: Mumble session {session} has no certificate hash")
            self._send_mumble(
                session,
                "Verification failed: your Mumble client has no certificate hash. "
                "In Mumble open Configure -> Certificate Wizard and create a certificate, "
                "reconnect, then try again.",
            )
            return

        connected = {h.lower() for h in self.plugin_hashes()}
        if connected and mumble_hash not in connected:
            print(f"[verify] hash {mumble_hash[:8]} for session {session} is not in the falloff client list "
                  f"(connected={[h[:8] for h in connected]})")
            self._send_mumble(
                session,
                "Verification failed: your Exile Voice plugin is not connected to the bridge. "
                "Load the plugin in Mumble (Configure -> Plugins, enable Exile Voice), "
                "wait a few seconds, then try again.",
            )
            return

        if VERIFY_CODE_RE.match(arg):
            self._complete_code(session, mumble_name, mumble_hash, arg)
            return

        game_name = arg or mumble_name
        self._issue_code(session, mumble_name, mumble_hash, game_name)

    def _issue_code(self, session: int, mumble_name: str, mumble_hash: str, game_name: str) -> None:
        with self._lock:
            self._expire_locked()
            player = self._players_by_name.get(game_name.lower())

        if player is None or not player.steam_id:
            self._send_mumble(
                session,
                f"Verification failed: I cannot see a connected The Isle player named {game_name!r}. "
                f"Join the game first, or type {self.settings.command} YourGameName.",
            )
            return

        self._issue_code_for_player(player, mumble_name=mumble_name, mumble_hash=mumble_hash, mumble_session=session)

    def _complete_code(self, session: int, mumble_name: str, mumble_hash: str, code: str) -> None:
        with self._lock:
            self._expire_locked()
            pending = self._pending.get(code)

        if pending is None:
            self._send_mumble(
                session,
                f"Verification failed: code is wrong or expired. Type {self.settings.command} to request a new code.",
            )
            return
        if pending.mumble_hash and pending.mumble_hash != mumble_hash:
            self._send_mumble(session, "Verification failed: that code belongs to another Mumble identity.")
            return

        upsert_identity_mapping(
            self.identity_path,
            steam_id=pending.steam_id,
            game_name=pending.game_name,
            mumble_name=mumble_name or pending.mumble_name,
            mumble_hash=mumble_hash,
        )
        with self._lock:
            self._pending.pop(code, None)
        print(f"[verify] linked {pending.game_name}/{pending.steam_id} -> {mumble_name}/{mumble_hash[:8]}")
        self._send_mumble(session, f"Verified {pending.game_name}. Spatial voice is linked.")

    def _new_code(self) -> str:
        with self._lock:
            existing = set(self._pending)
        for _ in range(20):
            code = str(secrets.randbelow(900000) + 100000)
            if code not in existing:
                return code
        raise RuntimeError("Could not allocate verification code")

    def _issue_code_for_player(
        self,
        player: Player,
        mumble_name: str,
        mumble_hash: str,
        mumble_session: int | None,
    ) -> None:
        if not player.steam_id:
            return

        code = self._new_code()
        pending = PendingVerification(
            code=code,
            steam_id=player.steam_id,
            game_name=player.name,
            mumble_name=mumble_name,
            mumble_hash=mumble_hash,
            expires_at=self.now() + self.settings.code_ttl_sec,
        )
        with self._lock:
            self._pending[code] = pending

        game_message = f"{self.settings.game_message_prefix}Verify code {code}. In Mumble type {self.settings.command} {code}"
        try:
            response = self._send_game_message(player.steam_id, game_message)
        except Exception as exc:
            with self._lock:
                self._pending.pop(code, None)
            if mumble_session is not None:
                self._send_mumble(mumble_session, f"Verification failed: could not send in-game code by RCON: {exc}")
            else:
                print(f"[verify] could not send in-game code by RCON: {exc}")
            return

        print(f"[verify] issued code {code} for {player.name}/{player.steam_id} -> {mumble_name or '(pending mumble)'}/{mumble_hash[:8] or '-'}")
        if response.strip():
            print(f"[verify:rcon] {response.strip()}")
        self._start_game_message_repeater(player.steam_id, game_message, code)
        if mumble_session is None and self.settings.game_code_mumble_fallback:
            self._send_code_to_matching_mumble_user(player.name, code)
        if mumble_session is not None:
            self._send_mumble(mumble_session, f"I sent a verify code to {player.name} in The Isle. Type {self.settings.command} CODE here.")

    def _send_game_message(self, steam_id: str, message: str) -> str:
        with TheIsleRconClient(self.rcon_settings) as client:
            return client.command(f"directmessage {steam_id},{message}")

    def _start_game_message_repeater(self, steam_id: str, message: str, code: str) -> None:
        display_sec = max(0, self.settings.game_code_display_sec)
        interval_sec = max(1, self.settings.game_code_repeat_interval_sec)
        if display_sec <= interval_sec:
            return

        def run() -> None:
            deadline = self.now() + display_sec
            while self.now() + interval_sec < deadline:
                time.sleep(interval_sec)
                with self._lock:
                    if code not in self._pending:
                        return
                try:
                    response = self._send_game_message(steam_id, message)
                except Exception as exc:
                    print(f"[verify] could not repeat in-game code by RCON: {exc}")
                    return
                if response.strip():
                    print(f"[verify:rcon-repeat] {response.strip()}")

        thread = threading.Thread(target=run, name=f"verify-code-repeat-{code}", daemon=True)
        thread.start()

    def _send_code_to_matching_mumble_user(self, game_name: str, code: str) -> None:
        if self._server is None or not game_name:
            return
        try:
            users = list(self._server.getUsers().values())
        except Exception as exc:
            print(f"[verify] could not list Mumble users for fallback code delivery: {exc}")
            return

        matches = [
            user for user in users
            if str(getattr(user, "name", "")).strip().lower() == game_name.strip().lower()
        ]
        if len(matches) != 1:
            print(f"[verify] did not send Mumble fallback code for {game_name}: {len(matches)} matching users")
            return

        session = int(getattr(matches[0], "session", -1))
        self._send_mumble(session, f"Exile Voice code for {game_name}: {code}. Type {self.settings.command} {code} here.")
        print(f"[verify] also sent code {code} to matching Mumble user {game_name}")

    def _is_already_verified(self, steam_id: str) -> bool:
        if not self.identity_path.exists():
            return False
        try:
            data = json.loads(self.identity_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return False
        for row in data.get("players", []):
            if str(row.get("steam_id", "")).strip() == steam_id and str(row.get("mumble_hash", "")).strip():
                return True
        return False

    def _expire_locked(self) -> None:
        now = self.now()
        expired = [code for code, pending in self._pending.items() if pending.expires_at <= now]
        for code in expired:
            self._pending.pop(code, None)

    def _send_mumble(self, session: int, text: str) -> None:
        if self._server is None or session < 0:
            return
        try:
            self._server.sendMessage(session, text)
        except Exception as exc:
            print(f"[verify] could not send Mumble message to session {session}: {exc}")

    def _lookup_hash_for_session(self, session: int) -> str:
        if self._server is None or session < 0:
            return ""
        try:
            state = self._server.getState(session)
        except Exception as exc:
            print(f"[verify] could not getState({session}): {exc}")
            return ""
        return str(getattr(state, "hash", "")).strip().lower()

    def _connect_ice_callback(self) -> None:
        try:
            import Ice  # type: ignore
        except ImportError as exc:
            raise RuntimeError("Install zeroc-ice before enabling verify.enabled") from exc

        init_data = Ice.InitializationData()
        if self.settings.ice.secret:
            init_data.properties = Ice.createProperties()
            init_data.properties.setProperty("Ice.ImplicitContext", "Shared")
        self._communicator = Ice.initialize([], init_data)
        if self.settings.ice.secret:
            self._communicator.getImplicitContext().put("secret", self.settings.ice.secret)
        Ice.loadSlice(build_slice_args(Ice, self.settings.ice.slice_path))
        import Murmur  # type: ignore

        self._ice = Ice
        self._murmur = Murmur
        proxy = self._communicator.stringToProxy(f"Meta:tcp -h {self.settings.ice.host} -p {self.settings.ice.port}")
        meta = Murmur.MetaPrx.checkedCast(proxy)
        if not meta:
            raise RuntimeError("Could not connect to Murmur Ice Meta proxy")
        booted_servers = list(meta.getBootedServers())
        if not booted_servers:
            booted_servers = [meta.getServer(self.settings.ice.server_id)]
        self._servers = booted_servers
        self._server = self._select_server(booted_servers)

        manager = self

        class VerifyCallback(Murmur.ServerCallback):  # type: ignore[name-defined]
            def userConnected(self, state, current=None):
                pass

            def userDisconnected(self, state, current=None):
                pass

            def userStateChanged(self, state, current=None):
                pass

            def userTextMessage(self, state, message, current=None):
                try:
                    manager.handle_mumble_message(state, getattr(message, "text", ""))
                except Exception as exc:
                    print(f"[verify] error while handling Mumble text message: {exc}")

            def channelCreated(self, state, current=None):
                pass

            def channelRemoved(self, state, current=None):
                pass

            def channelStateChanged(self, state, current=None):
                pass

        self._adapter = self._communicator.createObjectAdapterWithEndpoints("ExileVerifyCallback", "tcp -h 127.0.0.1")
        servant = VerifyCallback()
        callback_proxy = self._adapter.addWithUUID(servant)
        self._adapter.activate()
        self._callback_prx = Murmur.ServerCallbackPrx.checkedCast(callback_proxy)
        if not self._callback_prx:
            raise RuntimeError("Could not cast Mumble callback proxy")

        registered_ids: list[int] = []
        for server in self._servers:
            server.addCallback(self._callback_prx)
            registered_ids.append(int(server.id()))
        print(f"[verify] registered callback on Mumble server ids: {registered_ids}")
        self._print_current_mumble_users()

    def _select_server(self, servers):
        for server in servers:
            if int(server.id()) == self.settings.ice.server_id:
                return server
        return servers[0]

    def _print_current_mumble_users(self) -> None:
        if self._server is None:
            return
        try:
            users = self._server.getUsers()
        except Exception as exc:
            print(f"[verify] could not list Mumble users: {exc}")
            return
        if not users:
            print("[verify] no Mumble users currently connected")
            return
        print("[verify] current Mumble users:")
        for user in users.values():
            print(
                f"  session={getattr(user, 'session', '?')} "
                f"name={getattr(user, 'name', '')!r} "
                f"hash={str(getattr(user, 'hash', ''))[:8]}"
            )

    def _init_game_chat_log(self) -> None:
        if not self.settings.game_chat_enabled:
            return
        try:
            self._game_log_offset = self.settings.game_log_file.stat().st_size
        except OSError:
            self._game_log_offset = 0


def normalize_mumble_text(text: str) -> str:
    no_tags = HTML_TAG_RE.sub("", text)
    return " ".join(html.unescape(no_tags).split())


CHAT_LINE_RE = re.compile(
    r"LogTheIsleChatData:\s+\[[^\]]+\]\s+"
    r"\[(?P<channel>[^\]]+)\]\s+"
    r"\[(?P<group>[^\]]+)\]\s+"
    r"(?P<name>.+?)\s+\[(?P<steam_id>\d+)\]:\s+"
    r"(?P<text>.*)$",
    re.IGNORECASE,
)


def parse_theisle_chat_line(line: str) -> GameChatMessage | None:
    match = CHAT_LINE_RE.search(line)
    if not match:
        return None
    return GameChatMessage(
        channel=match.group("channel").strip(),
        group=match.group("group").strip(),
        game_name=match.group("name").strip(),
        steam_id=match.group("steam_id").strip(),
        text=match.group("text").strip(),
    )


def upsert_identity_mapping(path: Path, steam_id: str, game_name: str, mumble_name: str, mumble_hash: str) -> None:
    data = {"players": []}
    if path.exists():
        with path.open("r", encoding="utf-8") as f:
            loaded = json.load(f)
        if isinstance(loaded, dict) and isinstance(loaded.get("players"), list):
            data = loaded

    rows = data.setdefault("players", [])
    target = None
    for row in rows:
        if str(row.get("steam_id", "")).strip() == steam_id:
            target = row
            break
    if target is None:
        for row in rows:
            if str(row.get("game_name", "")).strip().lower() == game_name.lower():
                target = row
                break
    if target is None:
        target = {}
        rows.append(target)

    target["steam_id"] = steam_id
    target["game_name"] = game_name
    target["mumble_name"] = mumble_name
    target["mumble_hash"] = mumble_hash

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
