# Exile Voice Bridge

The bridge is the server-side process for Exile Voice. It polls The Isle Evrima RCON for player data, maps game players to Mumble/plugin identities, moves users into proximity channels if configured, and serves `UPDATE2` falloff packets to Exile Voice Mumble plugins.

## Layout

```text
exile_bridge/                Python package
tests/                       Unit tests
fixtures/                    Mock player data for local testing
config.example.json          Safe config template
identity_map.example.json    Fake identity map for tests
systemd/                     Example Linux service
docs/                        Setup and verification notes
```

## Local Smoke Test

```powershell
cd bridge
python -m unittest discover -s tests
python -m exile_bridge parse --file fixtures/sample_playerdata.txt
python -m exile_bridge run --config config.example.json --once
```

The example config uses `mode: mock`, so it does not connect to your live The Isle server.

## Live Server Setup

1. Copy `config.example.json` to `config.local.json`.
2. Set `mode` to `rcon`.
3. Fill in RCON host, port, and password.
4. Set `falloff_server.api_key` to the same value players use in `exile_voice.ini`.
5. Copy `identity_map.example.json` to `identity_map.local.json`.
6. Run `python -m exile_bridge run --config config.local.json`.

For Mumble verification and service setup, see `docs/VERIFY_FLOW.md` and `docs/VPS_QUICKSTART.md`.
