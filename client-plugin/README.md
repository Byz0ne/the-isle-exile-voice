# Exile Voice Mumble Plugin

Exile Voice is a native Mumble plugin for The Isle community servers. It connects to an Exile-compatible falloff server and applies per-speaker volume and stereo pan updates to incoming Mumble voice.

This package is the clean open-source Mumble client plugin. It intentionally excludes local testing folders, server secrets, built binaries, review mining output, and one-off VPS files.

## What It Does

- Loads in Mumble as `Exile Voice - Spatial Audio`.
- Connects to a falloff server over TCP, default port `8890`.
- Sends a `HELLO` containing the local Mumble identity hash.
- Receives `UPDATE2` packets containing speaker hash, gain, and pan.
- Applies gain and stereo pan inside Mumble's audio callback.
- Creates `exile_voice_client_id.txt` if Mumble reports an empty certificate hash.

## Repository Layout

```text
src/                            Plugin source
installer/                      Small Windows installer source
config/exile_voice.example.ini  Player-editable config template
third_party/mumble/             Mumble plugin API reference headers/docs
docs/                           Client setup notes
build.ps1                       Windows build script using Zig
```

## Player Install

For normal players, ship the built `ExileVoicePluginSetup.exe`.

1. Close Mumble.
2. Run `ExileVoicePluginSetup.exe`.
3. Restart Mumble.
4. Open Mumble settings, go to Plugins, and enable `Exile Voice - Spatial Audio`.
5. Join the server's Mumble and complete your server's verification flow.

The installer writes files to:

```text
%APPDATA%\Mumble\Mumble\Plugins\
```

If `exile_voice.ini` already exists, the installer keeps it instead of overwriting player settings.

## Build From Source

Install Zig or point the build script to a Zig executable.

```powershell
.\build.ps1
```

Alternative:

```powershell
.\build.ps1 -ZigPath C:\path\to\zig.exe
```

Outputs are written to `dist/`:

```text
dist/exile_voice.dll
dist/exile_voice.ini
dist/ExileVoicePluginSetup.exe
```

## Configuration

Copy `config/exile_voice.example.ini` to the Mumble plugin folder as `exile_voice.ini`, or let the installer create it.

The common settings are:

```ini
server_host=YOUR_SERVER_IP_OR_HOSTNAME
server_port=8890
api_key=CHANGE_ME_SHARED_KEY
enabled=1
debug_log=1
```

Use your own server host, port, and API key before distributing a public build.

## Server Side

This package contains the client Mumble plugin. It expects a compatible bridge/falloff server that can map game players to Mumble identities and send `UPDATE2` audio state packets.

See `../docs/FALLOFF_PROTOCOL.md` for the small TCP protocol.

## License

Exile Voice plugin and installer code are MIT licensed. The Mumble API reference files are third-party material; see `THIRD_PARTY_NOTICES.md`.
