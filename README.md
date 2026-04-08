# RepairXpert IndAutomation

[![RepairXpert/indautomation MCP server](https://glama.ai/mcp/servers/RepairXpert/indautomation/badges/score.svg)](https://glama.ai/mcp/servers/RepairXpert/indautomation)

<!-- mcp-name: io.github.repairxpert/indautomation -->

AI-powered equipment diagnosis. This repo ships **TWO** MCP servers — one for industrial automation, and the **first-ever automotive OBD-II MCP server** publicly available.

---

## MCP Servers

### 1. Industrial Automation (`mcp_server.py`)

Fault diagnosis for Allen-Bradley PLCs, conveyors, pilers, AS/RS, packaging lines, palletizers, VFDs, and CR30 relays.

| Tool | Description |
|------|-------------|
| `diagnose_fault` | AI fault diagnosis from symptoms or error codes |
| `search_parts` | Search replacement parts catalog (AutomationDirect, Grainger, Amazon) |
| `get_equipment_profile` | Equipment specs, components, maintenance history |
| `list_fault_codes` | Browse 313+ fault codes by category |
| `get_allen_bradley_fault` | Rockwell-specific fault lookup |
| `list_supported_equipment` | All supported equipment types and brands |
| `get_maintenance_checklist` | Preventive maintenance schedules |
| `get_parts_for_fault` | Parts needed to fix a specific code |

**Coverage:** 313 fault codes — 52 general industrial, 51 Allen-Bradley/Rockwell, 26 conveyors, 21 VFDs, 18 packaging, 11 AS/RS, 8 palletizers, 7 pilers, 7 CR30.

### 2. Automotive OBD-II (`obd_mcp_server.py`) — FIRST AUTOMOTIVE OBD MCP SERVER

Vehicle diagnostics via OBD-II. Works in mock mode out of the box (no hardware needed) or real mode with any ELM327 adapter (serial or Bluetooth).

| Tool | Description |
|------|-------------|
| `read_dtcs` | Read stored and pending diagnostic trouble codes |
| `clear_dtcs` | Clear DTCs and reset MIL (Check Engine Light) |
| `get_vehicle_info` | VIN, ECU name, calibration IDs, OBD protocol (Mode 09) |
| `read_pid` | Live sensor data: RPM, coolant temp, MAF, fuel trims, O2, etc. |
| `get_freeze_frame` | Sensor snapshot captured at time of fault |
| `diagnose_dtc` | Expert diagnosis: probable causes, fix steps, field tricks |

**Coverage:** 106 automotive DTCs — P0xxx generic powertrain, P1xxx/P2xxx manufacturer-specific (Ford, GM, Toyota, Honda), B/C/U body/chassis/network codes.

**Modes:**
- `OBD_MODE=mock` (default) — realistic test data, no hardware
- `OBD_MODE=real` — uses python-obd with ELM327 adapter (`OBD_PORT=COM3` or `/dev/ttyUSB0`)

---

## Quick Start

Add to your MCP client config (e.g. `~/.claude/.mcp.json`):

```json
{
  "mcpServers": {
    "repairxpert-indauto": {
      "command": "python",
      "args": ["C:/RepairXpertIndAutomation/mcp_server.py"]
    },
    "repairxpert-obd": {
      "command": "python",
      "args": ["C:/RepairXpertIndAutomation/obd_mcp_server.py"],
      "env": {
        "OBD_MODE": "mock"
      }
    }
  }
}
```

Restart your MCP client and both servers' tools will be available to the agent.

## Requirements

- Python 3.11+
- Industrial: `pip install -r requirements.txt`
- Automotive (real mode only): `pip install obd`

## Docker

```bash
docker build -t repairxpert-indauto .
docker run -p 8300:8300 repairxpert-indauto
```

## Why This Matters

- **Industrial MCP:** First industrial-automation MCP server with real Allen-Bradley/Rockwell fault coverage.
- **Automotive OBD MCP:** First OBD-II MCP server ever built. AI agents can now read and diagnose vehicle trouble codes the same way they query databases. Mock mode means developers can build against it without owning an ELM327 adapter.

Built by a working field tech, not a vendor.

## License

MIT
