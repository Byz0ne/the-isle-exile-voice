# Exile Voice

Exile Voice is a community spatial voice stack for The Isle servers. It has two parts:

- `client-plugin/`: a native Mumble plugin players install on Windows.
- `bridge/`: a Python bridge that reads The Isle player positions, links players to Mumble identities, and publishes per-listener falloff updates.

The repo is structured so public source stays separate from local server files. Do not commit `config.local.json`, `identity_map.local.json`, logs, generated installers, or VPS secrets.

## How It Works

```text
The Isle server RCON/logs -> bridge -> falloff TCP protocol -> Mumble plugin -> Mumble audio callback
                                  |
                                  +-> optional Mumble Ice verification
```

Players install the plugin, join Mumble, join the game, then verify with the server. Once linked, the bridge calculates who each player should hear based on game positions and sends gain/pan updates to the plugin.

## Packages

- Client plugin: see `client-plugin/README.md`
- Server bridge: see `bridge/README.md`
- Shared falloff protocol: see `docs/FALLOFF_PROTOCOL.md`

## License

Project code is MIT licensed. Third-party Mumble API reference files are covered by their upstream license; see `THIRD_PARTY_NOTICES.md`.
