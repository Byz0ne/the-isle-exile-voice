from __future__ import annotations

import hashlib
import math
from dataclasses import dataclass

from .models import AudioState, ChannelAssignment, Player


@dataclass(frozen=True)
class ProximityConfig:
    audible_distance: float
    fade_start: float
    shard_size: float
    channel_prefix: str
    unknown_channel: str
    hash_salt: str
    pan_width: float

    @classmethod
    def from_dict(cls, data: dict) -> "ProximityConfig":
        return cls(
            audible_distance=float(data.get("audible_distance", 30000.0)),
            fade_start=float(data.get("fade_start", 12000.0)),
            shard_size=float(data.get("shard_size", 45000.0)),
            channel_prefix=str(data.get("channel_prefix", "TransportShard_")),
            unknown_channel=str(data.get("unknown_channel", "The Isle - Lobby")),
            hash_salt=str(data.get("hash_salt", "CHANGE_ME_RANDOM_SALT")),
            pan_width=float(data.get("pan_width", 20000.0)),
        )


class ProximityEngine:
    def __init__(self, config: ProximityConfig):
        self.config = config

    def assign_channels(self, players: list[Player]) -> dict[str, ChannelAssignment]:
        out: dict[str, ChannelAssignment] = {}
        for player in players:
            if player.position is None:
                channel = self.config.unknown_channel
            else:
                cell_x = math.floor(player.position.x / self.config.shard_size)
                cell_y = math.floor(player.position.y / self.config.shard_size)
                token = self._cell_token(cell_x, cell_y)
                channel = f"{self.config.channel_prefix}{token}"
            out[player.identity_key] = ChannelAssignment(player.identity_key, channel)
        return out

    def audio_matrix(self, players: list[Player]) -> dict[str, list[AudioState]]:
        matrix: dict[str, list[AudioState]] = {}
        listeners = [p for p in players if p.mumble_hash and p.position is not None]
        speakers = [p for p in players if p.mumble_hash and p.position is not None]

        for listener in listeners:
            states: list[AudioState] = []
            for speaker in speakers:
                if listener.identity_key == speaker.identity_key:
                    continue
                distance = listener.position.distance_2d(speaker.position)
                gain = self._gain(distance)
                if gain <= 0.0:
                    continue
                pan = self._pan(listener, speaker)
                states.append(AudioState(speaker.mumble_hash or "", gain, pan))
            matrix[listener.mumble_hash or ""] = states
        return matrix

    def _gain(self, distance: float) -> float:
        if distance >= self.config.audible_distance:
            return 0.0
        if distance <= self.config.fade_start:
            return 1.0
        span = max(1.0, self.config.audible_distance - self.config.fade_start)
        return clamp(1.0 - ((distance - self.config.fade_start) / span), 0.0, 1.0)

    def _pan(self, listener: Player, speaker: Player) -> float:
        if not listener.position or not speaker.position:
            return 0.0
        dx = speaker.position.x - listener.position.x
        return clamp(dx / max(1.0, self.config.pan_width), -1.0, 1.0)

    def _cell_token(self, cell_x: int, cell_y: int) -> str:
        raw = f"{self.config.hash_salt}:{cell_x}:{cell_y}".encode("utf-8")
        return hashlib.sha1(raw).hexdigest()[:8]


def clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))
