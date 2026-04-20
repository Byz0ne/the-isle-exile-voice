from __future__ import annotations

import argparse
from pathlib import Path

from .bridge import Bridge, probe_rcon
from .config import AppConfig
from .parser import parse_players


def main() -> int:
    parser = argparse.ArgumentParser(prog="exile_bridge")
    sub = parser.add_subparsers(dest="command", required=True)

    run_p = sub.add_parser("run", help="Run the proximity bridge")
    run_p.add_argument("--config", required=True)
    run_p.add_argument("--once", action="store_true")

    parse_p = sub.add_parser("parse", help="Parse player data and print what the bridge can see")
    parse_p.add_argument("--file", required=True)

    probe_p = sub.add_parser("probe-rcon", help="Probe RCON commands and save a transcript")
    probe_p.add_argument("--config", required=True)

    args = parser.parse_args()
    if args.command == "run":
        config = AppConfig.load(args.config)
        Bridge(config).run(once=args.once)
        return 0
    if args.command == "parse":
        text = Path(args.file).read_text(encoding="utf-8")
        players = parse_players(text)
        for player in players:
            pos = "no-position"
            if player.position:
                pos = f"X={player.position.x:.1f} Y={player.position.y:.1f} Z={player.position.z:.1f}"
            print(f"{player.display_name} steam={player.steam_id or '-'} eos={player.eos_id or '-'} {pos}")
        return 0
    if args.command == "probe-rcon":
        config = AppConfig.load(args.config)
        out_path = probe_rcon(config)
        print(f"Wrote RCON transcript: {out_path}")
        return 0
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
