"""RepairXpert Industrial Automation — MCP Server

Exposes fault diagnosis, parts search, equipment profiles, and fault code
listing as MCP tools. AI agents can discover and use these capabilities
to help field technicians diagnose industrial equipment faults.

Usage:
    python mcp_server.py

Add to ~/.claude/.mcp.json:
    {
      "mcpServers": {
        "repairxpert-indauto": {
          "command": "python",
          "args": ["C:/RepairXpertIndAutomation/mcp_server.py"]
        }
      }
    }
"""
import json
import sys
from pathlib import Path

# MCP protocol over stdio
# Implements JSON-RPC 2.0 per MCP spec

PROJECT_ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(PROJECT_ROOT))

from indauto.diagnosis.engine import load_fault_db, diagnose_fault
from indauto.parts.search import search_parts, get_parts_for_category

# Load config
import yaml
CONFIG_PATH = PROJECT_ROOT / "config.yaml"
CONFIG = {}
if CONFIG_PATH.exists():
    CONFIG = yaml.safe_load(CONFIG_PATH.read_text(encoding="utf-8"))

# Load equipment profiles
EQUIPMENT_PATH = PROJECT_ROOT / "indauto" / "fault_db" / "equipment.json"
EQUIPMENT = {}
if EQUIPMENT_PATH.exists():
    EQUIPMENT = json.loads(EQUIPMENT_PATH.read_text(encoding="utf-8"))


def get_tools():
    """Return MCP tool definitions."""
    return [
        {
            "name": "diagnose_fault",
            "description": "Diagnose an industrial equipment fault from a fault code, symptoms, and equipment type. Returns probable causes, step-by-step fix instructions, severity, confidence score, field tricks, and suggested replacement parts with supplier links. Covers 71 fault codes across pilers, conveyors, AS/RS, packaging lines, palletizers, and Allen-Bradley/Rockwell Automation systems.",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "equipment_type": {
                        "type": "string",
                        "description": "Equipment type: piler, conveyor, asrs, packaging, palletizer, allen-bradley, or leave empty for auto-detect"
                    },
                    "fault_code": {
                        "type": "string",
                        "description": "Fault code (e.g. '10036', 'E030', 'AB-PLC-MAJOR01') or natural language description of the fault"
                    },
                    "symptoms": {
                        "type": "string",
                        "description": "Free-text description of symptoms observed (e.g. 'belt slipping motor overheating intermittent stops')"
                    }
                },
                "required": ["fault_code"]
            }
        },
        {
            "name": "search_parts",
            "description": "Search the industrial parts catalog for replacement components. Returns parts with descriptions, part numbers, estimated prices, and buy links from AutomationDirect, Amazon, Grainger, McMaster-Carr, and other suppliers. Catalog covers proximity sensors, photoelectric sensors, VFDs, motor overload relays, safety relays, PLC batteries, limit switches, servo cables, pneumatic cylinders, and encoder wheels.",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Search query (e.g. 'proximity sensor', 'Allen-Bradley PowerFlex', 'VFD drive')"
                    }
                },
                "required": ["query"]
            }
        },
        {
            "name": "get_equipment_profile",
            "description": "Get detailed equipment profile including components, maintenance schedules, common fault codes, and supported brands. Available profiles: piler, conveyor, asrs, packaging, palletizer, allen-bradley.",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "equipment_type": {
                        "type": "string",
                        "description": "Equipment type to look up"
                    }
                },
                "required": ["equipment_type"]
            }
        },
        {
            "name": "list_fault_codes",
            "description": "List all fault codes in the database, optionally filtered by equipment type. Returns code, name, severity, and equipment type for each entry.",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "equipment_type": {
                        "type": "string",
                        "description": "Filter by equipment type (optional). Leave empty to list all 71 codes."
                    }
                }
            }
        },
        {
            "name": "get_allen_bradley_fault",
            "description": "Look up an Allen-Bradley / Rockwell Automation specific fault code. Covers ControlLogix major faults (AB-PLC-MAJOR01-04), PowerFlex VFD faults (AB-PF-F004-F013), GuardMaster safety relay (AB-GUARD-SIL), CR30 configurable relay (AB-CR30-FAULT), and EtherNet/IP communication (AB-EN2T-FAULT). Returns detailed Rockwell-specific diagnostic steps.",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "fault_code": {
                        "type": "string",
                        "description": "Allen-Bradley fault code (e.g. 'AB-PLC-MAJOR01', 'AB-PF-F004', 'AB-GUARD-SIL')"
                    }
                },
                "required": ["fault_code"]
            }
        },
        {
            "name": "list_supported_equipment",
            "description": "List all equipment types and brands supported by RepairXpert Industrial Automation. Returns equipment categories with brand coverage and fault code counts.",
            "inputSchema": {
                "type": "object",
                "properties": {}
            }
        },
        {
            "name": "get_maintenance_checklist",
            "description": "Get a preventive maintenance checklist for a specific equipment type. Returns daily, weekly, monthly, and annual maintenance tasks with specific procedures. Available for: piler, conveyor, asrs, packaging, palletizer, allen-bradley.",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "equipment_type": {
                        "type": "string",
                        "description": "Equipment type to get maintenance checklist for"
                    }
                },
                "required": ["equipment_type"]
            }
        },
        {
            "name": "get_parts_for_fault",
            "description": "Get the specific replacement parts commonly needed to fix a given fault code. Returns parts with descriptions, part numbers, pricing estimates, and direct purchase links from AutomationDirect, Amazon (affiliate), Grainger, and McMaster-Carr.",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "fault_code": {
                        "type": "string",
                        "description": "Fault code to look up parts for (e.g. '10036', 'AB-PF-F004')"
                    }
                },
                "required": ["fault_code"]
            }
        }
    ]


def handle_diagnose_fault(args):
    """Execute fault diagnosis."""
    result = diagnose_fault(
        equipment_type=args.get("equipment_type", ""),
        fault_code=args.get("fault_code", ""),
        symptoms=args.get("symptoms", ""),
        photo_analysis=None,
        config=CONFIG
    )
    # Format parts as readable text
    parts_text = ""
    if result.get("suggested_parts"):
        parts_lines = []
        for p in result["suggested_parts"][:5]:
            suppliers = p.get("suppliers", [])
            links = ", ".join(f"{s['name']}: {s['url']}" for s in suppliers[:3])
            parts_lines.append(f"  - {p['name']} ({p.get('part_number', 'N/A')}) — {links}")
        parts_text = "\nSuggested Parts:\n" + "\n".join(parts_lines)

    text = f"""Fault: {result['fault_code']} — {result['fault_name']}
Equipment: {result['equipment_type']}
Severity: {result['severity']}
Confidence: {result['confidence']:.0%}
Source: {result['source']}

Probable Causes:
{chr(10).join(f'  {i+1}. {c}' for i, c in enumerate(result['diagnosis'][:5]))}

Fix Steps:
{chr(10).join(f'  {i+1}. {s}' for i, s in enumerate(result['fix_steps'][:8]))}"""

    if result.get("field_trick"):
        text += f"\n\nField Trick: {result['field_trick']}"
    text += parts_text

    return [{"type": "text", "text": text}]


def handle_search_parts(args):
    """Search parts catalog."""
    query = args.get("query", "")
    result = search_parts(query)

    if not result.get("catalog_matches") and not result.get("search_urls"):
        return [{"type": "text", "text": f"No parts found for '{query}'."}]

    lines = [f"Parts Search: '{query}'\n"]

    if result.get("catalog_matches"):
        lines.append("Catalog Matches:")
        for p in result["catalog_matches"][:10]:
            lines.append(f"  - {p['name']} ({p.get('part_number', 'N/A')})")
            if p.get("description"):
                lines.append(f"    {p['description'][:120]}")
            for s in p.get("suppliers", [])[:3]:
                price = f" ~${s['est_price']}" if s.get("est_price") else ""
                lines.append(f"    {s['name']}{price}: {s['url']}")

    if result.get("search_urls"):
        lines.append("\nSupplier Search Links:")
        for name, url in result["search_urls"].items():
            lines.append(f"  - {name}: {url}")

    return [{"type": "text", "text": "\n".join(lines)}]


def handle_get_equipment_profile(args):
    """Get equipment profile."""
    eq_type = args.get("equipment_type", "").lower()
    profiles = EQUIPMENT.get("equipment", [])

    for profile in profiles:
        if eq_type in profile.get("type", "").lower() or eq_type in profile.get("name", "").lower():
            lines = [f"Equipment: {profile.get('name', eq_type)}"]
            lines.append(f"Type: {profile.get('type', 'N/A')}")

            if profile.get("components"):
                lines.append(f"\nKey Components: {', '.join(profile['components'][:15])}")
            if profile.get("brands"):
                lines.append(f"Brands: {', '.join(profile['brands'][:10])}")
            if profile.get("maintenance"):
                lines.append("\nMaintenance Schedule:")
                for m in profile["maintenance"][:6]:
                    lines.append(f"  - {m}")
            if profile.get("common_faults"):
                lines.append(f"\nCommon Fault Codes: {', '.join(str(f) for f in profile['common_faults'][:10])}")

            return [{"type": "text", "text": "\n".join(lines)}]

    return [{"type": "text", "text": f"No profile found for '{eq_type}'. Available: piler, conveyor, asrs, packaging, palletizer, allen-bradley"}]


def handle_list_fault_codes(args):
    """List all fault codes."""
    db = load_fault_db()
    eq_filter = args.get("equipment_type", "").lower()

    if eq_filter:
        db = [e for e in db if eq_filter in e.get("equipment_type", "").lower()
              or any(eq_filter in t.lower() for t in e.get("equipment_types", []))]

    lines = [f"Fault Codes ({len(db)} entries)" + (f" — filtered: {eq_filter}" if eq_filter else "")]
    lines.append("-" * 60)

    for entry in db:
        lines.append(f"  {entry['code']:20s} {entry['name']:35s} [{entry['severity']:8s}] {entry.get('equipment_type', '')}")

    return [{"type": "text", "text": "\n".join(lines)}]


def handle_get_allen_bradley_fault(args):
    """Look up AB-specific fault code."""
    code = args.get("fault_code", "").strip().upper()
    if not code.startswith("AB-"):
        code = f"AB-{code}"

    db = load_fault_db()
    for entry in db:
        if entry.get("code", "").upper() == code:
            result = f"""Allen-Bradley Fault: {entry['code']} — {entry['name']}
Severity: {entry.get('severity', 'medium')}
Equipment: {entry.get('equipment_type', 'allen-bradley')}

Description: {entry.get('description', 'N/A')}

Probable Causes:
{chr(10).join(f'  {i+1}. {c}' for i, c in enumerate(entry.get('probable_causes', [])[:6]))}

Fix Steps:
{chr(10).join(f'  {i+1}. {s}' for i, s in enumerate(entry.get('fix_steps', [])[:8]))}"""
            if entry.get("field_trick"):
                result += f"\n\nField Trick: {entry['field_trick']}"
            return [{"type": "text", "text": result}]

    # List available AB codes
    ab_codes = [e for e in db if e.get("code", "").startswith("AB-")]
    available = ", ".join(e["code"] for e in ab_codes[:15])
    return [{"type": "text", "text": f"Code '{code}' not found. Available AB codes: {available}"}]


def handle_list_supported_equipment(args):
    """List all supported equipment types."""
    db = load_fault_db()
    profiles = EQUIPMENT.get("equipment", [])

    # Count codes per equipment type
    type_counts = {}
    for entry in db:
        et = entry.get("equipment_type", "unknown")
        type_counts[et] = type_counts.get(et, 0) + 1
        for t in entry.get("equipment_types", []):
            if t != et:
                type_counts[t] = type_counts.get(t, 0) + 1

    lines = ["RepairXpert Industrial Automation — Supported Equipment\n"]
    lines.append(f"Total fault codes: {len(db)}")
    lines.append(f"Equipment profiles: {len(profiles)}\n")

    for profile in profiles:
        ptype = profile.get("type", "unknown")
        count = type_counts.get(ptype, 0)
        brands = ", ".join(profile.get("brands", [])[:8])
        lines.append(f"  {profile.get('name', ptype)}")
        lines.append(f"    Fault codes: {count}")
        lines.append(f"    Brands: {brands}")
        lines.append("")

    lines.append("Supported brands: Allen-Bradley/Rockwell, Siemens, Omron, FANUC, ABB, IFM, Banner, Pilz, SMC")
    return [{"type": "text", "text": "\n".join(lines)}]


def handle_get_maintenance_checklist(args):
    """Get PM checklist for equipment type."""
    eq_type = args.get("equipment_type", "").lower()
    profiles = EQUIPMENT.get("equipment", [])

    for profile in profiles:
        if eq_type in profile.get("type", "").lower() or eq_type in profile.get("name", "").lower():
            lines = [f"Preventive Maintenance Checklist: {profile.get('name', eq_type)}\n"]
            if profile.get("maintenance"):
                for task in profile["maintenance"]:
                    lines.append(f"  - {task}")
            else:
                lines.append("  No maintenance schedule defined for this equipment type.")
            return [{"type": "text", "text": "\n".join(lines)}]

    return [{"type": "text", "text": f"No PM checklist for '{eq_type}'. Available: piler, conveyor, asrs, packaging, palletizer, allen-bradley"}]


def handle_get_parts_for_fault(args):
    """Get parts needed for a specific fault code."""
    code = args.get("fault_code", "").strip().upper()
    db = load_fault_db()

    for entry in db:
        if entry.get("code", "").upper() == code:
            parts_category = entry.get("parts_category", "")
            if not parts_category:
                return [{"type": "text", "text": f"Fault {code} ({entry.get('name', '')}) has no associated parts category."}]

            parts = get_parts_for_category(parts_category)
            if not parts:
                return [{"type": "text", "text": f"No parts found for category '{parts_category}' (fault {code})."}]

            lines = [f"Parts for Fault {code} — {entry.get('name', '')}", f"Category: {parts_category}\n"]
            for p in parts[:8]:
                lines.append(f"  {p['name']} ({p.get('part_number', 'N/A')})")
                if p.get("description"):
                    lines.append(f"    {p['description'][:120]}")
                for s in p.get("suppliers", [])[:3]:
                    price = f" ~${s['est_price']}" if s.get("est_price") else ""
                    lines.append(f"    {s['name']}{price}: {s['url']}")
                lines.append("")
            return [{"type": "text", "text": "\n".join(lines)}]

    return [{"type": "text", "text": f"Fault code '{code}' not found in database."}]


TOOL_HANDLERS = {
    "diagnose_fault": handle_diagnose_fault,
    "search_parts": handle_search_parts,
    "get_equipment_profile": handle_get_equipment_profile,
    "list_fault_codes": handle_list_fault_codes,
    "get_allen_bradley_fault": handle_get_allen_bradley_fault,
    "list_supported_equipment": handle_list_supported_equipment,
    "get_maintenance_checklist": handle_get_maintenance_checklist,
    "get_parts_for_fault": handle_get_parts_for_fault,
}


def send_response(id, result):
    """Send JSON-RPC response."""
    msg = json.dumps({"jsonrpc": "2.0", "id": id, "result": result})
    sys.stdout.write(f"Content-Length: {len(msg.encode())}\r\n\r\n{msg}")
    sys.stdout.flush()


def send_error(id, code, message):
    """Send JSON-RPC error."""
    msg = json.dumps({"jsonrpc": "2.0", "id": id, "error": {"code": code, "message": message}})
    sys.stdout.write(f"Content-Length: {len(msg.encode())}\r\n\r\n{msg}")
    sys.stdout.flush()


def main():
    """Run MCP server over stdio."""
    while True:
        try:
            # Read Content-Length header
            header = ""
            while True:
                line = sys.stdin.readline()
                if not line:
                    return  # EOF
                header += line
                if header.endswith("\r\n\r\n") or header.endswith("\n\n"):
                    break

            # Parse content length
            content_length = 0
            for h in header.strip().split("\n"):
                if h.lower().startswith("content-length:"):
                    content_length = int(h.split(":")[1].strip())

            if content_length == 0:
                continue

            # Read body
            body = sys.stdin.read(content_length)
            request = json.loads(body)

            method = request.get("method", "")
            id = request.get("id")
            params = request.get("params", {})

            if method == "initialize":
                send_response(id, {
                    "protocolVersion": "2024-11-05",
                    "capabilities": {"tools": {}},
                    "serverInfo": {
                        "name": "repairxpert-indauto",
                        "version": "1.0.0"
                    }
                })

            elif method == "notifications/initialized":
                pass  # No response needed for notifications

            elif method == "tools/list":
                send_response(id, {"tools": get_tools()})

            elif method == "tools/call":
                tool_name = params.get("name", "")
                tool_args = params.get("arguments", {})

                handler = TOOL_HANDLERS.get(tool_name)
                if handler:
                    try:
                        content = handler(tool_args)
                        send_response(id, {"content": content})
                    except Exception as e:
                        send_response(id, {
                            "content": [{"type": "text", "text": f"Error: {e}"}],
                            "isError": True
                        })
                else:
                    send_error(id, -32601, f"Unknown tool: {tool_name}")

            elif method == "ping":
                send_response(id, {})

            else:
                if id is not None:
                    send_error(id, -32601, f"Unknown method: {method}")

        except json.JSONDecodeError:
            continue
        except Exception:
            continue


if __name__ == "__main__":
    main()
