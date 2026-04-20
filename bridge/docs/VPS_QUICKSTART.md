# VPS Quickstart

This is the short production shape. Adjust paths and ports for your host.

## Install

```bash
sudo apt update
sudo apt install -y python3 python3-venv python3-pip

sudo mkdir -p /opt/exile-bridge
sudo cp -a bridge/. /opt/exile-bridge/
cd /opt/exile-bridge

python3 -m venv .venv
. .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

Install `zeroc-ice` only when `verify.enabled` or `mumble.adapter: ice` is used.

```bash
sudo apt install -y build-essential python3-dev libbz2-dev libssl-dev libexpat1-dev zlib1g-dev
python -m pip install zeroc-ice
```

## Configure

```bash
cp config.example.json config.local.json
cp identity_map.example.json identity_map.local.json
```

Edit `config.local.json` and set:

- `mode` to `rcon`
- RCON host, port, and password
- `falloff_server.api_key`
- `verify.game_log_file`
- Mumble Ice settings if verification is enabled

Open TCP port `8890` to players. Keep RCON and Murmur Ice private.

## Run

```bash
. .venv/bin/activate
python -m exile_bridge run --config config.local.json
```

## systemd

Copy `systemd/exile-bridge.service.example` to `/etc/systemd/system/exile-bridge.service`, edit paths if needed, then:

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now exile-bridge
sudo systemctl status exile-bridge --no-pager
```
