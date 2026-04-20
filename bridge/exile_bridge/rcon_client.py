from __future__ import annotations

import socket
import time
from dataclasses import dataclass

EVRIMA_AUTH = 0x01
EVRIMA_EXEC_COMMAND = 0x02

EVRIMA_COMMAND_BYTES: dict[str, int] = {
    "announce": 0x10,
    "directmessage": 0x11,
    "serverdetails": 0x12,
    "getserverdetails": 0x12,
    "wipecorpses": 0x13,
    "getplayables": 0x14,
    "updateplayables": 0x15,
    "togglemigrations": 0x19,
    "ban": 0x20,
    "banplayer": 0x20,
    "togglegrowthmultiplier": 0x21,
    "setgrowthmultiplier": 0x22,
    "togglenetupdatedistancechecks": 0x23,
    "kick": 0x30,
    "kickplayer": 0x30,
    "playerlist": 0x40,
    "getplayerlist": 0x40,
    "save": 0x50,
    "pause": 0x60,
    "playerdata": 0x77,
    "getplayerdata": 0x77,
    "togglewhitelist": 0x81,
    "addwhitelist": 0x82,
    "addwhitelistid": 0x82,
    "removewhitelist": 0x83,
    "removewhitelistid": 0x83,
    "toggleglobalchat": 0x84,
    "togglehumans": 0x86,
    "toggleai": 0x90,
    "disableaiclasses": 0x91,
    "aidensity": 0x92,
    "getqueuestatus": 0x93,
    "toggleailearning": 0x94,
    "custom": 0x70,
}


@dataclass(frozen=True)
class RconSettings:
    host: str
    port: int
    password: str
    protocol: str = "evrima"
    line_ending: str = "\n"
    send_password_first: bool = True
    read_idle_ms: int = 350
    read_timeout_sec: float = 4.0

    @classmethod
    def from_dict(cls, data: dict) -> "RconSettings":
        ending = str(data.get("line_ending", "\\n")).encode("utf-8").decode("unicode_escape")
        return cls(
            host=str(data.get("host", "127.0.0.1")),
            port=int(data.get("port", 8888)),
            password=str(data.get("password", "")),
            protocol=str(data.get("protocol", "evrima")).lower(),
            line_ending=ending,
            send_password_first=bool(data.get("send_password_first", True)),
            read_idle_ms=int(data.get("read_idle_ms", 350)),
            read_timeout_sec=float(data.get("read_timeout_sec", 4.0)),
        )


class TheIsleRconClient:
    """RCON client for The Isle Evrima probing.

    Evrima uses a tiny byte-framed protocol instead of Source-style or plain
    text RCON. A legacy text mode is left available for experiments by setting
    ``rcon.protocol`` to ``text`` in the config.
    """

    def __init__(self, settings: RconSettings):
        self.settings = settings
        self.sock: socket.socket | None = None

    def __enter__(self) -> "TheIsleRconClient":
        self.connect()
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.close()

    def connect(self) -> str:
        self.sock = socket.create_connection((self.settings.host, self.settings.port), timeout=self.settings.read_timeout_sec)
        self.sock.settimeout(self.settings.read_idle_ms / 1000.0)
        if self.settings.protocol == "evrima":
            return self._connect_evrima()

        banner = self._read_until_idle()
        if self.settings.send_password_first:
            self._send_line(self.settings.password)
            auth = self._read_until_idle()
            return banner + auth
        return banner

    def command(self, command: str) -> str:
        if self.settings.protocol == "evrima":
            self._send_bytes(build_evrima_command_packet(command))
            return self._read_until_idle()

        self._send_line(command)
        return self._read_until_idle()

    def close(self) -> None:
        if self.sock is not None:
            try:
                self.sock.close()
            finally:
                self.sock = None

    def _send_line(self, text: str) -> None:
        self._send_bytes((text + self.settings.line_ending).encode("utf-8", errors="replace"))

    def _send_bytes(self, payload: bytes) -> None:
        if self.sock is None:
            raise RuntimeError("RCON socket is not connected")
        self.sock.sendall(payload)

    def _connect_evrima(self) -> str:
        self._send_bytes(build_evrima_auth_packet(self.settings.password))
        auth = self._read_until_idle()
        if "incorrect password" in auth.lower():
            raise PermissionError("Evrima RCON rejected the configured password")
        if "password accepted" not in auth.lower():
            raise PermissionError(f"Evrima RCON auth did not confirm success: {auth!r}")
        return auth

    def _read_until_idle(self) -> str:
        if self.sock is None:
            raise RuntimeError("RCON socket is not connected")
        chunks: list[bytes] = []
        deadline = time.monotonic() + self.settings.read_timeout_sec
        while time.monotonic() < deadline:
            try:
                chunk = self.sock.recv(65535)
            except socket.timeout:
                break
            if not chunk:
                break
            chunks.append(chunk)
        return b"".join(chunks).decode("utf-8", errors="replace")


def build_evrima_auth_packet(password: str) -> bytes:
    return bytes([EVRIMA_AUTH]) + password.encode("utf-8", errors="replace") + b"\x00"


def build_evrima_command_packet(command: str) -> bytes:
    command_byte, args = parse_evrima_command(command)
    return bytes([EVRIMA_EXEC_COMMAND, command_byte]) + args.encode("utf-8", errors="replace") + b"\x00"


def parse_evrima_command(command: str) -> tuple[int, str]:
    raw = command.strip()
    if not raw:
        raise ValueError("Empty Evrima RCON command")

    full_name = normalize_evrima_command_name(raw)
    if full_name in EVRIMA_COMMAND_BYTES:
        return EVRIMA_COMMAND_BYTES[full_name], ""

    head, _, tail = raw.partition(" ")
    name = normalize_evrima_command_name(head)
    if name not in EVRIMA_COMMAND_BYTES:
        raise ValueError(f"Unknown Evrima RCON command: {command}")
    return EVRIMA_COMMAND_BYTES[name], tail.strip()


def normalize_evrima_command_name(command: str) -> str:
    return "".join(ch for ch in command.lower() if ch.isalnum())
