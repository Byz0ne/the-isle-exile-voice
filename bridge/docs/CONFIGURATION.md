# Bridge Configuration

Start from the safe template:

```bash
cp config.example.json config.local.json
cp identity_map.example.json identity_map.local.json
```

Keep both local files out of git. They contain server passwords, live player mappings, and shared API keys.

## Important Settings

- `mode`: use `mock` for local tests, `rcon` for a live The Isle server.
- `rcon.host`, `rcon.port`, `rcon.password`: The Isle RCON connection.
- `rcon.commands`: usually `PlayerList` and `PlayerData` are enough for live polling.
- `identity_map_file`: the file where verified Steam IDs are mapped to Mumble/plugin hashes.
- `proximity.audible_distance`: maximum 3D distance that can be heard.
- `proximity.fade_start`: distance where voice starts fading out.
- `proximity.pan_width`: distance used for left/right stereo pan strength.
- `falloff_server.port`: TCP port the client plugin connects to.
- `falloff_server.api_key`: shared key that must match each player's plugin config.
- `verify.enabled`: turns the `!verify` flow on or off.
- `verify.game_log_file`: The Isle server log path used to detect in-game `!verify`.
- `mumble.ice`: Murmur Ice connection used for Mumble chat callbacks and private messages.

## Recommended Live Defaults

Use `mumble.adapter: dry_run` while testing. Switch to `ice` only when Murmur Ice is configured and you want the bridge to create/move Mumble channels.

Use a long random value for `falloff_server.api_key`, for example:

```bash
openssl rand -hex 24
```
