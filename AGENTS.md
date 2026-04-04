# RepairXpert Industrial Automation — AI Agent Integration

## Overview

RepairXpert IndAutomation is an AI-powered industrial fault diagnosis system with 71 fault codes, 6 equipment profiles, 500+ replacement parts, and photo-based diagnosis. It helps field technicians diagnose and repair industrial equipment faster.

## MCP Server

Connect via stdio:

```json
{
  "mcpServers": {
    "repairxpert-indauto": {
      "command": "python",
      "args": ["C:/RepairXpertIndAutomation/mcp_server.py"]
    }
  }
}
```

## Available Tools (8 total)

### `diagnose_fault`
Diagnose industrial equipment faults from codes, symptoms, or natural language descriptions.
- **Input:** `equipment_type` (optional), `fault_code` (required), `symptoms` (optional)
- **Output:** Fault name, probable causes, fix steps, severity, confidence, field tricks, suggested parts with buy links
- **Coverage:** Pilers, conveyors, AS/RS, packaging, palletizers, Allen-Bradley/Rockwell systems

### `search_parts`
Search the replacement parts catalog with links to AutomationDirect, Amazon, Grainger, McMaster-Carr, Digikey, Mouser.
- **Input:** `query` (required)
- **Output:** Matching parts with descriptions, part numbers, prices, and supplier URLs

### `get_equipment_profile`
Get detailed equipment profiles including components, maintenance schedules, common faults, and supported brands.
- **Input:** `equipment_type` (required)
- **Available:** piler, conveyor, asrs, packaging, palletizer, allen-bradley

### `list_fault_codes`
List all 71 fault codes, optionally filtered by equipment type.
- **Input:** `equipment_type` (optional)
- **Output:** Code, name, severity, equipment type for each entry

## Equipment Coverage

| Type | Codes | Brands |
|------|-------|--------|
| Piler/Stacker | 10036-10038, 40001 | Alvey, Columbia, TopTier, FANUC |
| Conveyor | 20010-20012, 50001-50002 | Hytrol, Dorner, Interroll, Dematic |
| AS/RS | 80001, E030, 60001 | Dematic, Swisslog, Daifuku |
| Packaging | 70002-70003, E040 | Sealed Air, ProMach |
| Allen-Bradley | 27 codes (AB-PLC-*, AB-PF-*, AB-GUARD-*, AB-CR30-*, AB-EN2T-*) | Rockwell Automation |

### `get_allen_bradley_fault`
Look up Allen-Bradley/Rockwell specific fault codes with detailed Rockwell diagnostic steps.
- **Input:** `fault_code` (required) — e.g. 'AB-PLC-MAJOR01', 'AB-PF-F004'
- **Output:** Description, causes, fix steps, field tricks for Rockwell systems

### `list_supported_equipment`
List all equipment types and brands supported with fault code counts.
- **Input:** none
- **Output:** Equipment profiles with brand coverage

### `get_maintenance_checklist`
Get preventive maintenance checklist for an equipment type (daily/weekly/monthly/annual tasks).
- **Input:** `equipment_type` (required)
- **Output:** PM tasks with specific procedures

### `get_parts_for_fault`
Get replacement parts needed for a specific fault code with purchase links.
- **Input:** `fault_code` (required)
- **Output:** Parts with AutomationDirect, Amazon affiliate, Grainger links

## API Endpoint

REST API also available at `http://localhost:8300/api/diagnose` (POST).

## Registries

- Official MCP Registry: registry.modelcontextprotocol.io
- Smithery: smithery.ai
- mcp.so

## License

Proprietary. Contact: Eric West / RepairXpert
