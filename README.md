# RepairXpert IndAutomation

[![RepairXpert/indautomation MCP server](https://glama.ai/mcp/servers/RepairXpert/indautomation/badges/score.svg)](https://glama.ai/mcp/servers/RepairXpert/indautomation)

AI-powered industrial fault diagnosis MCP server. Helps field technicians diagnose equipment faults across Allen-Bradley PLCs, conveyors, pilers, AS/RS systems, packaging lines, and palletizers.

## MCP Tools

| Tool | Description |
|------|-------------|
| `diagnose_fault` | AI fault diagnosis from symptoms or error codes |
| `search_parts` | Search replacement parts catalog |
| `get_equipment_profile` | Equipment specs and maintenance history |
| `list_fault_codes` | Browse 78+ fault codes by category |
| `get_fault_detail` | Detailed fault info with repair procedures |
| `search_faults` | Full-text search across fault database |
| `decode_vin` | Decode equipment VIN/serial numbers |
| `get_diagnosis_history` | Past diagnosis records |

## Quick Start

Add to your MCP client config (e.g. `~/.claude/.mcp.json`):

```json
{
  "mcpServers": {
    "repairxpert-indauto": {
      "command": "python",
      "args": ["path/to/mcp_server.py"]
    }
  }
}
```

## Requirements

- Python 3.11+
- Dependencies: `pip install -r requirements.txt`

## Docker

```bash
docker build -t repairxpert-indauto .
docker run -p 8300:8300 repairxpert-indauto
```

## License

MIT
