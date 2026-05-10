from __future__ import annotations

import re
import socket
import threading
import time
from dataclasses import dataclass

from .models import AudioState

MUMBLE_HASH_RE = re.compile(r"^[0-9a-f]{40}$")


@dataclass(frozen=True)
class FalloffSettings:
    enabled: bool
    host: str
    port: int
    api_key: str
    send_interval_sec: float

    @classmethod
    def from_dict(cls, data: dict) -> "FalloffSettings":
        return cls(
            enabled=bool(data.get("enabled", False)),
            host=str(data.get("host", "0.0.0.0")),
            port=int(data.get("port", 8890)),
            api_key=str(data.get("api_key", "CHANGE_ME_SHARED_KEY")),
            send_interval_sec=float(data.get("send_interval_sec", 1.0)),
        )


class FalloffServer:
    """TCP falloff server for Exile-compatible spatial audio clients.

    Expected client hello, based on the reversed plugin:
    HELLO <api_key> <local_mumble_hash> {"version":"1.0","features":["spatial"]}

    Outgoing update:
    UPDATE2 <speaker_hash> <gain> <pan>, <speaker_hash> <gain> <pan>
    """

    def __init__(self, settings: FalloffSettings):
        self.settings = settings
        self._sock: socket.socket | None = None
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._clients: dict[str, socket.socket] = {}
        self._lock = threading.Lock()
        self._last_send = 0.0

    def start(self) -> None:
        if not self.settings.enabled or self._thread:
            return
        self._thread = threading.Thread(target=self._serve, name="falloff-server", daemon=True)
        self._thread.start()
        print(f"[falloff] listening on {self.settings.host}:{self.settings.port}")

    def stop(self) -> None:
        self._stop.set()
        if self._sock:
            try:
                self._sock.close()
            except OSError:
                pass
        with self._lock:
            for client in self._clients.values():
                try:
                    client.close()
                except OSError:
                    pass
            self._clients.clear()

    def publish(self, matrix: dict[str, list[AudioState]]) -> None:
        if not self.settings.enabled:
            return
        now = time.monotonic()
        if now - self._last_send < self.settings.send_interval_sec:
            return
        self._last_send = now

        with self._lock:
            clients = dict(self._clients)

        listener_hashes = set(matrix.keys()) | set(clients.keys())
        for listener_hash in listener_hashes:
            client = clients.get(listener_hash.lower())
            if not client:
                continue
            states = matrix.get(listener_hash, [])
            line = self._format_update(states)
            try:
                client.sendall(line.encode("utf-8"))
            except OSError:
                self._drop_client(listener_hash)

    def connected_count(self) -> int:
        with self._lock:
            return len(self._clients)

    def connected_hashes(self) -> list[str]:
        with self._lock:
            return sorted(self._clients)

    def _serve(self) -> None:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self._sock = sock
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        sock.bind((self.settings.host, self.settings.port))
        sock.listen()
        sock.settimeout(0.5)
        while not self._stop.is_set():
            try:
                client, addr = sock.accept()
            except socket.timeout:
                continue
            except OSError:
                break
            threading.Thread(target=self._handle_client, args=(client, addr), daemon=True).start()

    def _handle_client(self, client: socket.socket, addr) -> None:
        client.settimeout(10.0)
        mumble_hash = ""
        try:
            hello = self._read_line(client)
            parts = hello.split(maxsplit=3)
            if len(parts) < 3 or parts[0] != "HELLO":
                client.sendall(b"ERR expected HELLO\n")
                client.close()
                return
            api_key = parts[1]
            mumble_hash = parts[2].lower()
            if self.settings.api_key and api_key != self.settings.api_key:
                client.sendall(b"ERR unauthorized\n")
                client.close()
                return
            if not MUMBLE_HASH_RE.match(mumble_hash):
                print(f"[falloff] rejecting client from {addr[0]}:{addr[1]}: "
                      f"hash {mumble_hash[:16]!r} is not a 40-char hex SHA-1; "
                      f"the user probably has no Mumble certificate")
                client.sendall(b"ERR invalid_hash mumble certificate hash required\n")
                client.close()
                mumble_hash = ""
                return
            with self._lock:
                old = self._clients.get(mumble_hash)
                if old:
                    try:
                        old.close()
                    except OSError:
                        pass
            self._clients[mumble_hash] = client
            client.sendall(b"OK\n")
            client.sendall(b"UPDATE2\n")
            client.settimeout(0.5)
            print(f"[falloff] client {mumble_hash} connected from {addr[0]}:{addr[1]}")
            while not self._stop.is_set():
                try:
                    line = self._read_line(client)
                except socket.timeout:
                    continue
                if not line:
                    break
                if line == "PING":
                    client.sendall(b"OK\n")
        except OSError:
            pass
        finally:
            if mumble_hash:
                self._drop_client(mumble_hash)
            try:
                client.close()
            except OSError:
                pass

    def _drop_client(self, mumble_hash: str) -> None:
        with self._lock:
            client = self._clients.pop(mumble_hash.lower(), None)
        if client:
            try:
                client.close()
            except OSError:
                pass

    @staticmethod
    def _read_line(client: socket.socket) -> str:
        data = bytearray()
        while True:
            chunk = client.recv(1)
            if not chunk:
                return ""
            if chunk == b"\n":
                return data.decode("utf-8", errors="replace").strip()
            data.extend(chunk)

    @staticmethod
    def _format_update(states: list[AudioState]) -> str:
        if not states:
            return "UPDATE2\n"
        payload = ", ".join(f"{s.speaker_hash} {s.gain:.4f} {s.pan:.4f}" for s in states)
        return f"UPDATE2 {payload}\n"
