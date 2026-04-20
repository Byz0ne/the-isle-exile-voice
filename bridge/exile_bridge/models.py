from __future__ import annotations

from dataclasses import dataclass
from math import sqrt
from typing import Optional


@dataclass(frozen=True)
class Vec3:
    x: float
    y: float
    z: float = 0.0

    def distance_2d(self, other: "Vec3") -> float:
        return sqrt((self.x - other.x) ** 2 + (self.y - other.y) ** 2)

    def distance_3d(self, other: "Vec3") -> float:
        return sqrt((self.x - other.x) ** 2 + (self.y - other.y) ** 2 + (self.z - other.z) ** 2)


@dataclass
class Player:
    source_id: str
    name: str = ""
    steam_id: Optional[str] = None
    eos_id: Optional[str] = None
    position: Optional[Vec3] = None
    mumble_name: Optional[str] = None
    mumble_hash: Optional[str] = None

    @property
    def display_name(self) -> str:
        return self.name or self.steam_id or self.eos_id or self.source_id

    @property
    def identity_key(self) -> str:
        return self.steam_id or self.eos_id or self.name.lower() or self.source_id


@dataclass(frozen=True)
class AudioState:
    speaker_hash: str
    gain: float
    pan: float


@dataclass(frozen=True)
class ChannelAssignment:
    player_key: str
    channel_name: str
