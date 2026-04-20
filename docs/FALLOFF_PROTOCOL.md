# Exile Falloff Protocol

The plugin speaks a small line-based TCP protocol. It is intentionally simple so community servers can implement compatible bridges.

## Client Hello

After connecting, the plugin sends:

```text
HELLO <api_key> <local_mumble_hash> {"version":"1.0","client":"exile_voice","features":["spatial"]}
```

Fields:

- `api_key`: shared key from `exile_voice.ini`
- `local_mumble_hash`: Mumble certificate hash, or the generated Exile client ID when Mumble reports an empty hash
- JSON metadata: currently informational

## Server Updates

The bridge sends one update line per listener:

```text
UPDATE2 <speaker_hash> <gain> <pan>, <speaker_hash> <gain> <pan>
```

Example:

```text
UPDATE2 bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb 1.0000 0.2000
```

No audible speakers:

```text
UPDATE2
```

`gain` is clamped from `0.0` to `1.0`.

`pan` is clamped from `-1.0` to `1.0`:

- `-1.0`: left
- `0.0`: center
- `1.0`: right

## Identity Mapping

The bridge must know which game player maps to which Mumble identity hash. A typical verification flow is:

1. Player joins the game server and Mumble.
2. Player types `!verify` in game.
3. Bridge sends an in-game code to that Steam ID.
4. Player types `!verify CODE` in Mumble.
5. Bridge stores Steam ID, game name, Mumble name, and Mumble/plugin hash.

Once mapped, the bridge can compute proximity and send per-speaker `UPDATE2` states.
