# Verification Flow

Verification links a The Isle player to a Mumble/plugin identity. Without this link the bridge can see a game position, but it cannot know which Mumble voice stream belongs to that player.

## Player Flow

1. Join the The Isle server.
2. Join the server's Mumble.
3. Make sure the Exile Voice Mumble plugin is enabled.
4. In game, type `!verify`.
5. The bridge sends a short code through RCON direct message.
6. In Mumble chat, type `!verify CODE`.

After this, the bridge writes the mapping to `identity_map.local.json`.

## Server Requirements

- `verify.enabled` must be `true`.
- `verify.game_chat_enabled` must be `true` if players start from in-game chat.
- `verify.game_log_file` must point at the active The Isle log.
- Murmur Ice must be enabled so the bridge can listen to Mumble chat.
- The falloff server must be reachable so the bridge can use plugin hashes when Mumble has no certificate hash.

## Notes

Some Mumble setups expose an empty certificate hash. In that case the client plugin creates a stable `exile_voice_client_id.txt`, sends that ID to the falloff server, and the bridge can use it during verification when exactly one matching plugin client is connected.
