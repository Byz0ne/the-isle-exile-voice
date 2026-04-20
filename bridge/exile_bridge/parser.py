from __future__ import annotations

import json
import re
from typing import Any

from .models import Player, Vec3

NAME_KEYS = ("playerName", "PlayerName", "name", "Name", "player_name")
STEAM_KEYS = ("steamId", "SteamId", "SteamID", "steam_id", "PlayerSteamId", "PlayerSteamID", "PlayerID", "playerId")
EOS_KEYS = ("eosId", "EOSId", "EOSID", "eos_id")
POSITION_KEYS = ("PlayerLocation", "location", "Location", "position", "Position", "coordinates", "Coordinates")

KEY_VALUE_RE = re.compile(r"(?P<key>[A-Za-z_][A-Za-z0-9_ ]{0,32})\s*[:=]\s*(?P<value>\"[^\"]*\"|'[^']*'|[^\s,;]+)")
XYZ_RE = re.compile(
    r"(?:PlayerLocation|Location|Position|Coordinates)?\s*[:=]?\s*\(?\s*"
    r"X\s*=\s*(?P<x>-?\d+(?:\.\d+)?)\s*,?\s*"
    r"Y\s*=\s*(?P<y>-?\d+(?:\.\d+)?)\s*,?\s*"
    r"Z\s*=\s*(?P<z>-?\d+(?:\.\d+)?)",
    re.IGNORECASE,
)
CSV_COORD_RE = re.compile(
    r"(?P<x>-?\d+(?:\.\d+)?)\s*[,|]\s*(?P<y>-?\d+(?:\.\d+)?)\s*[,|]\s*(?P<z>-?\d+(?:\.\d+)?)"
)


def parse_players(text: str) -> list[Player]:
    json_players = _parse_json_players(text)
    player_list_players = _parse_player_list_blocks(text)
    text_players = _parse_text_players(text)

    merged: dict[str, Player] = {}
    for player in json_players + player_list_players + text_players:
        key = player.steam_id or player.eos_id or player.name.lower() or player.source_id
        if key in merged:
            merged[key] = _merge_player(merged[key], player)
        else:
            merged[key] = player

    return list(merged.values())


def _parse_player_list_blocks(text: str) -> list[Player]:
    players: list[Player] = []
    lines = [line.strip().strip(",") for line in text.splitlines()]
    idx = 0
    while idx < len(lines):
        if lines[idx].lower() != "playerlist":
            idx += 1
            continue
        idx += 1
        while idx + 1 < len(lines):
            steam_id = lines[idx].strip()
            name = lines[idx + 1].strip()
            if not steam_id or steam_id.lower().startswith(("=====", "playerlist", "[")):
                break
            if not steam_id.isdigit():
                break
            players.append(Player(source_id=steam_id, name=name, steam_id=steam_id))
            idx += 2
        continue
    return players


def _parse_json_players(text: str) -> list[Player]:
    data = _load_possible_json(text)
    if data is None:
        return []

    candidates: list[dict[str, Any]] = []
    _collect_player_dicts(data, candidates)
    players: list[Player] = []
    for idx, item in enumerate(candidates):
        player = _player_from_dict(item, f"json:{idx}")
        if player:
            players.append(player)
    return players


def _load_possible_json(text: str) -> Any | None:
    stripped = text.strip()
    if not stripped:
        return None
    for candidate in _json_candidates(stripped):
        try:
            return json.loads(candidate)
        except json.JSONDecodeError:
            continue
    return None


def _json_candidates(text: str) -> list[str]:
    candidates = [text]
    first_obj = text.find("{")
    last_obj = text.rfind("}")
    first_arr = text.find("[")
    last_arr = text.rfind("]")
    if first_obj >= 0 and last_obj > first_obj:
        candidates.append(text[first_obj : last_obj + 1])
    if first_arr >= 0 and last_arr > first_arr:
        candidates.append(text[first_arr : last_arr + 1])
    return candidates


def _collect_player_dicts(value: Any, out: list[dict[str, Any]]) -> None:
    if isinstance(value, dict):
        keys = set(value.keys())
        if keys.intersection(NAME_KEYS) or keys.intersection(STEAM_KEYS) or keys.intersection(EOS_KEYS):
            out.append(value)
        for key, child in value.items():
            if key in ("players", "playerDetails", "PlayerList", "PlayerData") and isinstance(child, list):
                for item in child:
                    if isinstance(item, dict):
                        out.append(item)
            else:
                _collect_player_dicts(child, out)
    elif isinstance(value, list):
        for child in value:
            _collect_player_dicts(child, out)


def _player_from_dict(item: dict[str, Any], source_id: str) -> Player | None:
    name = _first_string(item, NAME_KEYS)
    steam_id = _first_string(item, STEAM_KEYS)
    eos_id = _first_string(item, EOS_KEYS)
    position = _position_from_dict(item)

    if not (name or steam_id or eos_id or position):
        return None
    return Player(
        source_id=steam_id or eos_id or name or source_id,
        name=name,
        steam_id=steam_id,
        eos_id=eos_id,
        position=position,
    )


def _position_from_dict(item: dict[str, Any]) -> Vec3 | None:
    direct = _position_from_xyz_mapping(item)
    if direct:
        return direct
    for key in POSITION_KEYS:
        if key not in item:
            continue
        value = item[key]
        if isinstance(value, dict):
            found = _position_from_xyz_mapping(value)
            if found:
                return found
        if isinstance(value, (list, tuple)) and len(value) >= 2:
            try:
                z = float(value[2]) if len(value) > 2 else 0.0
                return Vec3(float(value[0]), float(value[1]), z)
            except (TypeError, ValueError):
                pass
        if isinstance(value, str):
            found = parse_position(value)
            if found:
                return found
    return None


def _position_from_xyz_mapping(item: dict[str, Any]) -> Vec3 | None:
    lower = {str(k).lower(): v for k, v in item.items()}
    if not {"x", "y"}.issubset(lower.keys()):
        return None
    try:
        return Vec3(float(lower["x"]), float(lower["y"]), float(lower.get("z", 0.0)))
    except (TypeError, ValueError):
        return None


def _first_string(item: dict[str, Any], keys: tuple[str, ...]) -> str:
    for key in keys:
        value = item.get(key)
        if value is not None:
            return str(value).strip().strip('"')
    return ""


def _parse_text_players(text: str) -> list[Player]:
    players: list[Player] = []
    for idx, raw_line in enumerate(text.splitlines()):
        line = raw_line.strip()
        if not line or line in ("PlayerData", "PlayerDataEnd"):
            continue
        player = _parse_player_line(line, idx)
        if player:
            players.append(player)
    return players


def _parse_player_line(line: str, idx: int) -> Player | None:
    fields = _fields_from_line(line)
    position = parse_position(line)
    name = _field_lookup(fields, NAME_KEYS)
    steam_id = _field_lookup(fields, STEAM_KEYS)
    eos_id = _field_lookup(fields, EOS_KEYS)

    if not name:
        name = _guess_name_from_line(line)

    if not (name or steam_id or eos_id or position):
        return None

    return Player(
        source_id=steam_id or eos_id or name or f"line:{idx}",
        name=name,
        steam_id=steam_id,
        eos_id=eos_id,
        position=position,
    )


def _fields_from_line(line: str) -> dict[str, str]:
    fields: dict[str, str] = {}
    for match in KEY_VALUE_RE.finditer(line):
        key = match.group("key").strip().replace(" ", "")
        value = match.group("value").strip().strip('"').strip("'").rstrip(")")
        fields[key] = value
    return fields


def _field_lookup(fields: dict[str, str], keys: tuple[str, ...]) -> str:
    lower = {k.lower(): v for k, v in fields.items()}
    for key in keys:
        value = lower.get(key.lower())
        if value:
            return value
    return ""


def _guess_name_from_line(line: str) -> str:
    if "|" in line:
        first = line.split("|", 1)[0].strip()
        if first and not first.lower().startswith(("x=", "playerlocation")):
            return first
    return ""


def parse_position(text: str) -> Vec3 | None:
    match = XYZ_RE.search(text)
    if not match:
        match = CSV_COORD_RE.search(text)
    if not match:
        return None
    return Vec3(float(match.group("x")), float(match.group("y")), float(match.group("z")))


def _merge_player(left: Player, right: Player) -> Player:
    return Player(
        source_id=left.source_id or right.source_id,
        name=left.name or right.name,
        steam_id=left.steam_id or right.steam_id,
        eos_id=left.eos_id or right.eos_id,
        position=right.position or left.position,
        mumble_name=left.mumble_name or right.mumble_name,
        mumble_hash=left.mumble_hash or right.mumble_hash,
    )
