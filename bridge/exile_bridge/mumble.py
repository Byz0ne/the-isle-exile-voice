from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from .models import ChannelAssignment, Player


class MumbleAdapter(Protocol):
    def sync(self, players: list[Player], assignments: dict[str, ChannelAssignment]) -> None:
        ...


class DryRunMumbleAdapter:
    def __init__(self, print_every_tick: bool = True):
        self.print_every_tick = print_every_tick
        self.previous: dict[str, str] = {}

    def sync(self, players: list[Player], assignments: dict[str, ChannelAssignment]) -> None:
        lines: list[str] = []
        for player in players:
            assignment = assignments.get(player.identity_key)
            if not assignment:
                continue
            old = self.previous.get(player.identity_key)
            changed = old != assignment.channel_name
            self.previous[player.identity_key] = assignment.channel_name
            if self.print_every_tick or changed:
                mumble = player.mumble_name or player.mumble_hash or "(unmapped mumble)"
                pos = "no-position"
                if player.position:
                    pos = f"X={player.position.x:.1f} Y={player.position.y:.1f} Z={player.position.z:.1f}"
                marker = "MOVE" if changed else "keep"
                lines.append(f"{marker} {player.display_name} -> {assignment.channel_name} [{mumble}] {pos}")
        if lines:
            print("[mumble:dry-run]")
            for line in lines:
                print(f"  {line}")


@dataclass(frozen=True)
class IceSettings:
    host: str
    port: int
    secret: str
    server_id: int
    slice_path: str
    create_channels: bool
    match_by: tuple[str, ...]

    @classmethod
    def from_dict(cls, data: dict) -> "IceSettings":
        return cls(
            host=str(data.get("host", "127.0.0.1")),
            port=int(data.get("port", 6502)),
            secret=str(data.get("secret", "")),
            server_id=int(data.get("server_id", 1)),
            slice_path=str(data.get("slice_path", "Murmur.ice")),
            create_channels=bool(data.get("create_channels", True)),
            match_by=tuple(data.get("match_by", ["hash", "name"])),
        )


class IceMumbleAdapter:
    """Best-effort Murmur Ice adapter.

    This is intentionally isolated so the rest of the bridge runs without ZeroC Ice.
    It should be tested against the actual Mumble Server package because Slice
    paths and proxy names vary between installations.
    """

    def __init__(self, settings: IceSettings, root_channel: str):
        self.settings = settings
        self.root_channel = root_channel
        self._ice = None
        self._murmur = None
        self._communicator = None
        self._server = None

    def sync(self, players: list[Player], assignments: dict[str, ChannelAssignment]) -> None:
        self._connect_once()
        users = self._server.getUsers()
        channels = self._channel_name_map()
        root_id = channels.get(self.root_channel, 0)

        for assignment in assignments.values():
            if assignment.channel_name not in channels:
                if not self.settings.create_channels:
                    continue
                channel_id = self._server.addChannel(assignment.channel_name, root_id)
                channels[assignment.channel_name] = channel_id

        for player in players:
            assignment = assignments.get(player.identity_key)
            if assignment is None:
                continue
            user_state = self._find_user(users, player)
            if user_state is None:
                continue
            target_channel = channels.get(assignment.channel_name)
            if target_channel is None or getattr(user_state, "channel", None) == target_channel:
                continue
            user_state.channel = target_channel
            self._server.setState(user_state)

    def _connect_once(self) -> None:
        if self._server is not None:
            return
        try:
            import Ice  # type: ignore
        except ImportError as exc:
            raise RuntimeError("Install zeroc-ice before using mumble.adapter=ice") from exc

        init_data = Ice.InitializationData()
        if self.settings.secret:
            init_data.properties = Ice.createProperties()
            init_data.properties.setProperty("Ice.ImplicitContext", "Shared")
        self._communicator = Ice.initialize([], init_data)
        if self.settings.secret:
            self._communicator.getImplicitContext().put("secret", self.settings.secret)
        Ice.loadSlice(build_slice_args(Ice, self.settings.slice_path))
        import Murmur  # type: ignore

        self._ice = Ice
        self._murmur = Murmur
        proxy = self._communicator.stringToProxy(f"Meta:tcp -h {self.settings.host} -p {self.settings.port}")
        meta = Murmur.MetaPrx.checkedCast(proxy)
        if not meta:
            raise RuntimeError("Could not connect to Murmur Ice Meta proxy")
        self._server = meta.getServer(self.settings.server_id)

    def _channel_name_map(self) -> dict[str, int]:
        tree = self._server.getTree()
        out: dict[str, int] = {}

        def walk(node) -> None:
            out[getattr(node, "name", "")] = getattr(node, "id", 0)
            for child in getattr(node, "children", []):
                walk(child)

        walk(tree)
        return out

    def _find_user(self, users, player: Player):
        for user in users.values():
            if "hash" in self.settings.match_by and player.mumble_hash:
                if getattr(user, "hash", "").lower() == player.mumble_hash.lower():
                    return user
            if "name" in self.settings.match_by and player.mumble_name:
                if getattr(user, "name", "").lower() == player.mumble_name.lower():
                    return user
        return None


def make_mumble_adapter(config: dict, root_channel: str) -> MumbleAdapter:
    adapter = str(config.get("adapter", "dry_run")).lower()
    if adapter == "dry_run":
        return DryRunMumbleAdapter(bool(config.get("dry_run_print_every_tick", True)))
    if adapter == "ice":
        return IceMumbleAdapter(IceSettings.from_dict(config.get("ice", {})), root_channel)
    raise ValueError(f"Unknown mumble.adapter: {adapter}")


def build_slice_args(ice_module, slice_path: str) -> str:
    include_dirs = [Path(slice_path).parent, Path(".")]
    get_slice_dir = getattr(ice_module, "getSliceDir", None)
    if callable(get_slice_dir):
        try:
            include_dirs.append(Path(get_slice_dir()))
        except Exception:
            pass
    include_dirs.extend(
        Path(p)
        for p in (
            "/usr/share/Ice/slice",
            "/usr/share/ice/slice",
            "/usr/local/share/Ice/slice",
        )
    )

    parts: list[str] = []
    seen: set[str] = set()
    for include_dir in include_dirs:
        key = str(include_dir)
        if key in seen:
            continue
        seen.add(key)
        parts.append(f'-I"{key}"')
    parts.append(f'"{slice_path}"')
    return " ".join(parts)
