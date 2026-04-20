# Install And Test Guide

## Build The Installer

From this folder:

```powershell
.\build.ps1
```

If Zig is not on `PATH`:

```powershell
.\build.ps1 -ZigPath C:\path\to\zig.exe
```

## Install Locally

1. Close Mumble.
2. Run `dist\ExileVoicePluginSetup.exe`.
3. Start Mumble.
4. Open Settings > Plugins.
5. Enable `Exile Voice - Spatial Audio`.
6. Join your Mumble server.

## Check The Log

When `debug_log=1`, the plugin writes:

```text
%APPDATA%\Mumble\Mumble\Plugins\exile_voice.log
```

Watch it with:

```powershell
Get-Content "$env:APPDATA\Mumble\Mumble\Plugins\exile_voice.log" -Tail 40 -Wait
```

Healthy output looks like:

```text
falloff_connect_attempt host=YOUR_SERVER port=8890
connected to falloff YOUR_SERVER:8890
received UPDATE2 with 0 speakers
```

`0 speakers` is normal when nobody nearby is talking or when you are alone.

## Player Support Checklist

- Mumble was restarted after install.
- `Exile Voice - Spatial Audio` is enabled.
- Any old spatial plugin for the same server is disabled.
- `exile_voice.ini` has the right `server_host`, `server_port`, and `api_key`.
- The server bridge is listening on the configured port.
- The player completed the server verification flow.
