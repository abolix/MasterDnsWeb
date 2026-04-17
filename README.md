# MasterDnsWeb

MasterDnsWeb is a web panel for managing your **MasterDnsVPN** instances on a Linux server.
You get a clean dashboard where you can create, configure, start, and stop VPN instances — all from your browser.

---

## What You Need

- A Linux server running **Ubuntu** (any recent version)
- The release archive: `MasterDnsWeb-linux-amd64.tar.gz`
- Root access (required to manage system services)

---

## Installation

### 1. Extract the archive

```bash
tar -xzf MasterDnsWeb-linux-amd64.tar.gz
cd MasterDnsWeb
```

You will see this folder:

```
MasterDnsWeb/
  MasterDnsWeb     ← the web panel (run this)
  MasterDnsVPN     ← the VPN client binary
  .env             ← your settings
```

### 2. Edit your settings

Open `.env` in any text editor:

```bash
nano .env
```

The only things you **must** change before starting:

```env
ADMIN_USERNAME=admin
ADMIN_PASSWORD=changeme   ← change this to something strong
```

Everything else already has safe defaults. Save and close.

### 3. Start the panel

```bash
sudo ./MasterDnsWeb
```

> **Why sudo?** The panel needs root access to create and control system services for each VPN instance.

The panel is now running. Open your browser and go to:

```
http://<your-server-ip>:8000
```

Log in with the username and password you set in `.env`.

---

## How to Keep It Running (Optional)

If you want the panel to start automatically when your server reboots, create a system service.

Run this command (replace `/root/MasterDnsWeb` with your actual folder path):

```bash
sudo nano /etc/systemd/system/masterdnsweb.service
```

Paste this inside:

```ini
[Unit]
Description=MasterDnsWeb Panel
After=network.target

[Service]
WorkingDirectory=/root/MasterDnsWeb
ExecStart=/root/MasterDnsWeb/MasterDnsWeb
Restart=always
RestartSec=5
User=root

[Install]
WantedBy=multi-user.target
```

Then run:

```bash
sudo systemctl daemon-reload
sudo systemctl enable masterdnsweb
sudo systemctl start masterdnsweb
```

---

## Using the Panel

### Creating an instance

1. Go to the **Instances** page
2. Click **New Instance** and give it a name
3. Click the instance to open its **Configuration** page

### Configuring an instance

Paste your `client_config.toml` content into the **Configuration** text box.
Two fields are always required:

```toml
DOMAINS = ["your-domain.com"]
ENCRYPTION_KEY = "your-key-here"
```

All other fields from your config file are accepted — just paste the whole thing.

Add your resolver IPs in the **Resolvers** box (one per line), then click **Apply & Restart**.

### Starting / stopping

Use the **Start**, **Stop**, and **Restart** buttons on the Instances page.
Each instance runs as a separate system service in the background.

---

## Folder Layout After First Run

The panel creates these folders automatically next to the binary:

```
MasterDnsWeb/
  MasterDnsWeb           ← web panel binary
  MasterDnsVPN           ← VPN client binary
  .env                   ← your settings
  data/                  ← instance profiles (auto-created)
  runtime/
    my-instance/         ← working files per instance (auto-created)
      client_config.toml
      client_resolvers.txt
      MasterDnsVPN
```

---

## Settings Reference

All settings live in the `.env` file next to the binary.

| Setting | Default | Description |
|---|---|---|
| `ADMIN_USERNAME` | `admin` | Login username |
| `ADMIN_PASSWORD` | `changeme` | Login password — **change this** |
| `SECRET_KEY` | *(generated at build)* | Signs login sessions — do not share |
| `HOST` | `0.0.0.0` | Address the panel listens on |
| `PORT` | `8000` | Port the panel listens on |
| `COOKIE_SECURE` | `false` | Set to `true` if using HTTPS |
| `MASTERVPN_SERVICE_USER` | `root` | System user that runs VPN instances |
| `MASTERVPN_SERVICE_EXEC_START` | *(auto)* | Full path to `MasterDnsVPN` — only needed if it is not in the same folder |

---

## How It Works

```mermaid
flowchart TB
    U[You — Browser] --> PANEL[MasterDnsWeb\nport 8000]

    PANEL --> AUTH[Login and Session]
    PANEL --> CFG[Instance Profiles\nstored in data/]
    PANEL --> SVC[Service Manager]
    PANEL --> STATS[Server Stats\nCPU · RAM · Disk]

    SVC --> RUNTIME[runtime/instance-name/\nclient_config.toml\nclient_resolvers.txt\nMasterDnsVPN]
    SVC --> SYSTEMD[systemd\nmasterdnsvpn-instance.service]

    SYSTEMD --> VPN[MasterDnsVPN Process]
    RUNTIME --> VPN
```

---

## Troubleshooting

**Panel won't start**
Make sure you are running with `sudo`. The panel needs root to manage system services.

**Can't reach the panel in browser**
Check that your server's firewall allows port `8000` (or whatever `PORT` you set in `.env`).

**"MasterDnsVPN binary was not found"**
Make sure `MasterDnsVPN` is in the same folder as `MasterDnsWeb`. If it is somewhere else, set `MASTERVPN_SERVICE_EXEC_START` in `.env` to the full path.

**Instance won't start**
Open the instance in the panel and check the logs section for more details.
