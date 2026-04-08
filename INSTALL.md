# RepairXpert IndAutomation -- Plant Install Guide

Enterprise deployment: runs on your plant network, no cloud required.

## Prerequisites

- Docker Desktop (includes Docker Compose)
  - Windows: https://docs.docker.com/desktop/install/windows-install/
  - Linux: https://docs.docker.com/engine/install/
- LM Studio running on a machine accessible from the Docker host (for AI diagnostics)

## Quick Start

```bash
# Clone or copy this folder to the plant server, then:
./install.sh

# Or manually:
docker compose up -d
```

Open http://localhost:8300 in any browser on the network.

## Configuration

All settings are environment variables. Create a `.env` file next to `docker-compose.yml`:

```env
# Point to LM Studio on your network (default: host machine)
LM_STUDIO_URL=http://192.168.1.100:1234

# Optional: DeepSeek API key for cloud AI fallback
# Leave blank for fully offline operation
DEEPSEEK_API_KEY=

# Optional: Enable API docs at /docs
DEBUG=false
```

Docker Compose reads `.env` automatically.

## Plant Network Access

To make RepairXpert available to all machines on the plant network:

1. Find the server IP: `hostname -I` (Linux) or `ipconfig` (Windows)
2. Open port 8300 in the firewall
3. Techs access it at `http://<server-ip>:8300` from any device with a browser

## Offline / Air-Gapped Mode

RepairXpert works fully offline when:

1. LM Studio is running on the same machine or local network
2. `DEEPSEEK_API_KEY` is left blank (no cloud calls)
3. The Docker image is pre-built before going offline:
   ```bash
   docker compose build
   # Then copy the entire folder to the air-gapped machine
   docker compose up -d
   ```

The fault code database and diagnosis engine are bundled in the container.

## Commands

| Task | Command |
|------|---------|
| Start | `docker compose up -d` |
| Stop | `docker compose down` |
| View logs | `docker compose logs -f` |
| Restart | `docker compose restart` |
| Rebuild after update | `docker compose up -d --build` |
| Health check | `curl http://localhost:8300/api/health` |

## Data Persistence

Diagnosis logs are stored in a Docker volume (`diagnosis_logs`) and persist across container restarts. To back up:

```bash
docker cp repairxpert-indauto:/app/data ./backup_data
```

## Updating

```bash
# Pull latest files, then:
docker compose up -d --build
```
