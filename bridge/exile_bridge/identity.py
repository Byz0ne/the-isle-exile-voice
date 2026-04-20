from __future__ import annotations

import json
from pathlib import Path

from .models import Player


class IdentityMap:
    def __init__(self, rows: list[dict]):
        self.by_steam: dict[str, dict] = {}
        self.by_eos: dict[str, dict] = {}
        self.by_name: dict[str, dict] = {}
        self.by_hash: dict[str, dict] = {}

        for row in rows:
            steam_id = clean(row.get("steam_id"))
            eos_id = clean(row.get("eos_id"))
            game_name = clean(row.get("game_name"))
            mumble_name = clean(row.get("mumble_name"))
            mumble_hash = clean(row.get("mumble_hash"))

            if steam_id:
                self.by_steam[steam_id] = row
            if eos_id:
                self.by_eos[eos_id.lower()] = row
            if game_name:
                self.by_name[game_name.lower()] = row
            if mumble_name:
                self.by_name[mumble_name.lower()] = row
            if mumble_hash:
                self.by_hash[mumble_hash.lower()] = row

    @classmethod
    def load(cls, path: Path) -> "IdentityMap":
        if not path.exists():
            return cls([])
        with path.open("r", encoding="utf-8") as f:
            data = json.load(f)
        return cls(list(data.get("players", [])))

    def apply(self, player: Player) -> Player:
        row = None
        if player.steam_id:
            row = self.by_steam.get(player.steam_id)
        if row is None and player.eos_id:
            row = self.by_eos.get(player.eos_id.lower())
        if row is None and player.name:
            row = self.by_name.get(player.name.lower())
        if row is None:
            return player

        player.mumble_name = clean(row.get("mumble_name")) or player.mumble_name
        player.mumble_hash = clean(row.get("mumble_hash")) or player.mumble_hash
        if not player.name:
            player.name = clean(row.get("game_name")) or player.name
        if not player.steam_id:
            player.steam_id = clean(row.get("steam_id")) or player.steam_id
        if not player.eos_id:
            player.eos_id = clean(row.get("eos_id")) or player.eos_id
        return player


def clean(value: object) -> str:
    if value is None:
        return ""
    return str(value).strip().strip('"')
