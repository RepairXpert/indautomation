"""RepairXpert OBD-II MCP Server — First Automotive OBD MCP Server

Exposes vehicle OBD-II diagnostics as MCP tools. AI agents can read
diagnostic trouble codes, clear codes, read live sensor data, and get
expert diagnosis with fix steps from the RepairXpert automotive DTC database.

Supports two modes:
  - MOCK MODE (default): Returns realistic test data for development and demo
  - REAL MODE: Uses python-obd library with ELM327 adapter (serial/bluetooth)

Usage:
    python obd_mcp_server.py

Add to ~/.claude/.mcp.json:
    {
      "mcpServers": {
        "repairxpert-obd": {
          "command": "python",
          "args": ["C:/RepairXpertIndAutomation/obd_mcp_server.py"]
        }
      }
    }
"""
import json
import os
import random
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(PROJECT_ROOT))

# ---------------------------------------------------------------------------
# OBD Connection
# ---------------------------------------------------------------------------
OBD_MODE = os.environ.get("OBD_MODE", "mock")  # "mock" or "real"
OBD_PORT = os.environ.get("OBD_PORT", "")       # e.g. COM3, /dev/ttyUSB0
OBD_BAUD = int(os.environ.get("OBD_BAUD", "0")) or None

_obd_connection = None


def _get_obd():
    """Get or create OBD connection (real mode only)."""
    global _obd_connection
    if OBD_MODE != "real":
        return None
    if _obd_connection is not None:
        return _obd_connection
    try:
        import obd
        if OBD_PORT:
            _obd_connection = obd.OBD(OBD_PORT, baudrate=OBD_BAUD)
        else:
            _obd_connection = obd.OBD()  # auto-detect
        return _obd_connection
    except Exception as e:
        sys.stderr.write(f"OBD connection failed: {e}\n")
        return None


# ---------------------------------------------------------------------------
# Automotive DTC Database
# ---------------------------------------------------------------------------
AUTO_DTC_PATH = PROJECT_ROOT / "indauto" / "fault_db" / "automotive_dtcs.json"
_auto_dtc_cache = None


def _load_auto_dtcs():
    global _auto_dtc_cache
    if _auto_dtc_cache is not None:
        return _auto_dtc_cache
    if AUTO_DTC_PATH.exists():
        data = json.loads(AUTO_DTC_PATH.read_text(encoding="utf-8"))
        _auto_dtc_cache = data.get("faults", [])
    else:
        _auto_dtc_cache = []
    return _auto_dtc_cache


def _lookup_dtc(code):
    """Find DTC in automotive database. Returns first match."""
    code_upper = code.strip().upper()
    for entry in _load_auto_dtcs():
        if entry.get("code", "").upper() == code_upper:
            return entry
    return None


# ---------------------------------------------------------------------------
# Mock Data Generators
# ---------------------------------------------------------------------------
MOCK_DTCS = [
    {"code": "P0300", "description": "Random/Multiple Cylinder Misfire Detected", "status": "confirmed"},
    {"code": "P0171", "description": "System Too Lean (Bank 1)", "status": "confirmed"},
    {"code": "P0420", "description": "Catalyst System Efficiency Below Threshold (Bank 1)", "status": "pending"},
]

MOCK_FREEZE_FRAME = {
    "dtc_trigger": "P0300",
    "engine_rpm": 2150,
    "vehicle_speed_mph": 45,
    "coolant_temp_f": 198,
    "intake_air_temp_f": 85,
    "engine_load_pct": 42.5,
    "short_term_fuel_trim_pct": 8.2,
    "long_term_fuel_trim_pct": 12.5,
    "map_kpa": 68,
    "throttle_position_pct": 22.0,
    "fuel_system_status": "closed_loop",
    "timestamp": "captured at time of fault"
}

MOCK_VEHICLE_INFO = {
    "vin": "1HGBH41JXMN109186",
    "calibration_ids": ["37805-RNA-A840", "37805-RNA-A841"],
    "calibration_verification_numbers": ["0xABCD1234"],
    "ecu_name": "Honda ECM v3.2",
    "obd_standard": "OBD-II (CARB)",
    "protocol": "ISO 15765-4 (CAN 11/500)"
}

MOCK_PID_DATA = {
    "rpm": {"value": 780, "unit": "RPM", "description": "Engine RPM"},
    "speed": {"value": 0, "unit": "mph", "description": "Vehicle Speed"},
    "coolant_temp": {"value": 195, "unit": "F", "description": "Engine Coolant Temperature"},
    "intake_temp": {"value": 82, "unit": "F", "description": "Intake Air Temperature"},
    "maf": {"value": 3.8, "unit": "g/s", "description": "Mass Air Flow Rate"},
    "throttle_pos": {"value": 15.7, "unit": "%", "description": "Throttle Position"},
    "engine_load": {"value": 28.6, "unit": "%", "description": "Calculated Engine Load"},
    "fuel_pressure": {"value": 58, "unit": "PSI", "description": "Fuel Rail Pressure"},
    "timing_advance": {"value": 12.5, "unit": "degrees", "description": "Ignition Timing Advance"},
    "short_fuel_trim_1": {"value": 2.3, "unit": "%", "description": "Short Term Fuel Trim Bank 1"},
    "long_fuel_trim_1": {"value": 4.7, "unit": "%", "description": "Long Term Fuel Trim Bank 1"},
    "o2_voltage_b1s1": {"value": 0.45, "unit": "V", "description": "O2 Sensor Voltage Bank 1 Sensor 1"},
    "barometric_pressure": {"value": 101, "unit": "kPa", "description": "Barometric Pressure"},
    "catalyst_temp_b1s1": {"value": 752, "unit": "F", "description": "Catalyst Temperature Bank 1 Sensor 1"},
    "control_module_voltage": {"value": 14.1, "unit": "V", "description": "Control Module Voltage"},
    "fuel_level": {"value": 62, "unit": "%", "description": "Fuel Tank Level"},
    "ambient_temp": {"value": 78, "unit": "F", "description": "Ambient Air Temperature"},
    "commanded_egr": {"value": 0, "unit": "%", "description": "Commanded EGR"},
}


# ---------------------------------------------------------------------------
# Tool Handlers
# ---------------------------------------------------------------------------
def handle_read_dtcs(args):
    """Read diagnostic trouble codes from vehicle."""
    if OBD_MODE == "real":
        conn = _get_obd()
        if conn and conn.is_connected():
            try:
                import obd
                response = conn.query(obd.commands.GET_DTC)
                if response.is_null():
                    return [{"type": "text", "text": "No DTCs found. Vehicle systems OK."}]
                dtcs = []
                for code, desc in response.value:
                    db_entry = _lookup_dtc(code)
                    dtcs.append({
                        "code": code,
                        "description": desc or (db_entry["name"] if db_entry else "Unknown"),
                        "severity": db_entry["severity"] if db_entry else "unknown",
                    })
                lines = [f"DTCs Found: {len(dtcs)}\n"]
                for d in dtcs:
                    lines.append(f"  {d['code']} [{d['severity'].upper()}] — {d['description']}")
                return [{"type": "text", "text": "\n".join(lines)}]
            except Exception as e:
                return [{"type": "text", "text": f"Error reading DTCs: {e}"}]
        return [{"type": "text", "text": "OBD adapter not connected. Check ELM327 connection."}]

    # Mock mode
    include_pending = args.get("include_pending", True)
    dtcs = MOCK_DTCS if include_pending else [d for d in MOCK_DTCS if d["status"] != "pending"]
    lines = [f"DTCs Found: {len(dtcs)}  [MOCK MODE]\n"]
    for d in dtcs:
        db_entry = _lookup_dtc(d["code"])
        severity = db_entry["severity"] if db_entry else "unknown"
        lines.append(f"  {d['code']} [{severity.upper():8s}] ({d['status']}) — {d['description']}")
    lines.append(f"\nNote: Running in mock mode. Connect ELM327 adapter and set OBD_MODE=real for live data.")
    return [{"type": "text", "text": "\n".join(lines)}]


def handle_clear_dtcs(args):
    """Clear diagnostic trouble codes and reset MIL."""
    if OBD_MODE == "real":
        conn = _get_obd()
        if conn and conn.is_connected():
            try:
                import obd
                response = conn.query(obd.commands.CLEAR_DTC)
                return [{"type": "text", "text": "DTCs cleared. MIL (Check Engine Light) turned off.\n\nNote: If the underlying problem persists, codes will return within 1-3 drive cycles. Monitor readiness monitors with scan tool."}]
            except Exception as e:
                return [{"type": "text", "text": f"Error clearing DTCs: {e}"}]
        return [{"type": "text", "text": "OBD adapter not connected. Cannot clear codes."}]

    # Mock mode
    confirm = args.get("confirm", False)
    if not confirm:
        return [{"type": "text", "text": "WARNING: Clearing DTCs will turn off the Check Engine Light and reset all readiness monitors. This may affect emissions testing. Set confirm=true to proceed."}]
    return [{"type": "text", "text": "DTCs cleared successfully. [MOCK MODE]\n\nMIL (Check Engine Light) turned off.\nReadiness monitors reset — vehicle needs 2-3 drive cycles to complete all monitors.\n\nNote: Mock mode — no actual vehicle connection."}]


def handle_get_vehicle_info(args):
    """Get vehicle identification via Mode 09 PIDs."""
    if OBD_MODE == "real":
        conn = _get_obd()
        if conn and conn.is_connected():
            try:
                import obd
                info = {}
                for cmd_name, label in [("GET_VIN", "vin"), ("GET_CURRENT_DTC", "dtc_count")]:
                    cmd = getattr(obd.commands, cmd_name, None)
                    if cmd:
                        r = conn.query(cmd)
                        if not r.is_null():
                            info[label] = str(r.value)
                # Try VIN
                vin_cmd = getattr(obd.commands, "VIN", None)
                if vin_cmd:
                    r = conn.query(vin_cmd)
                    if not r.is_null():
                        info["vin"] = str(r.value)
                lines = ["Vehicle Information (Mode 09)\n"]
                for k, v in info.items():
                    lines.append(f"  {k}: {v}")
                return [{"type": "text", "text": "\n".join(lines)}]
            except Exception as e:
                return [{"type": "text", "text": f"Error reading vehicle info: {e}"}]
        return [{"type": "text", "text": "OBD adapter not connected."}]

    # Mock mode
    info = MOCK_VEHICLE_INFO
    lines = ["Vehicle Information (Mode 09)  [MOCK MODE]\n"]
    lines.append(f"  VIN: {info['vin']}")
    lines.append(f"  ECU Name: {info['ecu_name']}")
    lines.append(f"  OBD Standard: {info['obd_standard']}")
    lines.append(f"  Protocol: {info['protocol']}")
    lines.append(f"  Calibration IDs: {', '.join(info['calibration_ids'])}")
    lines.append(f"  CVN: {', '.join(info['calibration_verification_numbers'])}")
    lines.append(f"\nUse /vin endpoint to decode full vehicle specs from VIN.")
    return [{"type": "text", "text": "\n".join(lines)}]


def handle_read_pid(args):
    """Read a specific OBD-II PID."""
    pid_name = args.get("pid", "rpm").lower().replace(" ", "_").replace("-", "_")

    if OBD_MODE == "real":
        conn = _get_obd()
        if conn and conn.is_connected():
            try:
                import obd
                # Map common names to python-obd commands
                PID_MAP = {
                    "rpm": obd.commands.RPM,
                    "speed": obd.commands.SPEED,
                    "coolant_temp": obd.commands.COOLANT_TEMP,
                    "intake_temp": obd.commands.INTAKE_TEMP,
                    "maf": obd.commands.MAF,
                    "throttle_pos": obd.commands.THROTTLE_POS,
                    "engine_load": obd.commands.ENGINE_LOAD,
                    "fuel_pressure": obd.commands.FUEL_PRESSURE,
                    "timing_advance": obd.commands.TIMING_ADVANCE,
                    "short_fuel_trim_1": obd.commands.SHORT_FUEL_TRIM_1,
                    "long_fuel_trim_1": obd.commands.LONG_FUEL_TRIM_1,
                    "o2_voltage_b1s1": obd.commands.O2_B1S1,
                    "barometric_pressure": obd.commands.BAROMETRIC_PRESSURE,
                    "control_module_voltage": obd.commands.CONTROL_MODULE_VOLTAGE,
                    "fuel_level": obd.commands.FUEL_LEVEL,
                    "ambient_temp": obd.commands.AMBIANT_TEMP,
                }
                cmd = PID_MAP.get(pid_name)
                if not cmd:
                    available = ", ".join(sorted(PID_MAP.keys()))
                    return [{"type": "text", "text": f"Unknown PID '{pid_name}'. Available: {available}"}]
                r = conn.query(cmd)
                if r.is_null():
                    return [{"type": "text", "text": f"PID '{pid_name}' not supported by this vehicle."}]
                return [{"type": "text", "text": f"{pid_name}: {r.value}"}]
            except Exception as e:
                return [{"type": "text", "text": f"Error reading PID: {e}"}]
        return [{"type": "text", "text": "OBD adapter not connected."}]

    # Mock mode
    if pid_name == "all":
        lines = ["Live Sensor Data (All PIDs)  [MOCK MODE]\n"]
        for name, data in MOCK_PID_DATA.items():
            # Add slight randomness for realism
            val = data["value"]
            if isinstance(val, (int, float)):
                jitter = val * random.uniform(-0.03, 0.03)
                val = round(val + jitter, 1) if isinstance(data["value"], float) else int(val + jitter)
            lines.append(f"  {data['description']:40s} {val} {data['unit']}")
        return [{"type": "text", "text": "\n".join(lines)}]

    data = MOCK_PID_DATA.get(pid_name)
    if not data:
        available = ", ".join(sorted(MOCK_PID_DATA.keys()))
        return [{"type": "text", "text": f"Unknown PID '{pid_name}'. Available PIDs: {available}\n\nUse pid='all' to read all sensors at once."}]

    val = data["value"]
    if isinstance(val, (int, float)):
        jitter = val * random.uniform(-0.02, 0.02)
        val = round(val + jitter, 1) if isinstance(data["value"], float) else int(val + jitter)
    return [{"type": "text", "text": f"{data['description']}: {val} {data['unit']}  [MOCK MODE]"}]


def handle_get_freeze_frame(args):
    """Get freeze frame data captured at time of fault."""
    if OBD_MODE == "real":
        conn = _get_obd()
        if conn and conn.is_connected():
            try:
                import obd
                r = conn.query(obd.commands.FREEZE_DTC)
                if r.is_null():
                    return [{"type": "text", "text": "No freeze frame data stored."}]
                return [{"type": "text", "text": f"Freeze Frame DTC: {r.value}"}]
            except Exception as e:
                return [{"type": "text", "text": f"Error reading freeze frame: {e}"}]
        return [{"type": "text", "text": "OBD adapter not connected."}]

    # Mock mode
    ff = MOCK_FREEZE_FRAME
    lines = ["Freeze Frame Data  [MOCK MODE]\n"]
    lines.append(f"  Triggering DTC: {ff['dtc_trigger']}")
    lines.append(f"  Engine RPM: {ff['engine_rpm']}")
    lines.append(f"  Vehicle Speed: {ff['vehicle_speed_mph']} mph")
    lines.append(f"  Coolant Temp: {ff['coolant_temp_f']} F")
    lines.append(f"  Intake Air Temp: {ff['intake_air_temp_f']} F")
    lines.append(f"  Engine Load: {ff['engine_load_pct']}%")
    lines.append(f"  STFT: {ff['short_term_fuel_trim_pct']}%")
    lines.append(f"  LTFT: {ff['long_term_fuel_trim_pct']}%")
    lines.append(f"  MAP: {ff['map_kpa']} kPa")
    lines.append(f"  Throttle: {ff['throttle_position_pct']}%")
    lines.append(f"  Fuel System: {ff['fuel_system_status']}")
    lines.append(f"\nInterpretation: High LTFT ({ff['long_term_fuel_trim_pct']}%) suggests lean condition at time of misfire. Check vacuum leaks and fuel pressure.")
    return [{"type": "text", "text": "\n".join(lines)}]


def handle_diagnose_dtc(args):
    """Look up a DTC and return expert diagnosis."""
    code = args.get("code", "").strip().upper()
    if not code:
        return [{"type": "text", "text": "Please provide a DTC code (e.g. P0300, P0171)."}]

    entry = _lookup_dtc(code)
    if not entry:
        # Provide generic guidance
        prefix_info = {
            "P0": "Generic Powertrain (SAE standard)",
            "P1": "Manufacturer-Specific Powertrain",
            "P2": "Generic Powertrain (SAE extended)",
            "P3": "Generic Powertrain (SAE reserved)",
            "B0": "Generic Body",
            "B1": "Manufacturer-Specific Body",
            "C0": "Generic Chassis",
            "C1": "Manufacturer-Specific Chassis",
            "U0": "Generic Network Communication",
            "U1": "Manufacturer-Specific Network",
        }
        prefix = code[:2] if len(code) >= 2 else ""
        category = prefix_info.get(prefix, "Unknown category")
        return [{"type": "text", "text": f"DTC '{code}' not in RepairXpert database.\n\nCategory: {category}\n\nThe RepairXpert automotive DTC database covers 90+ of the most common OBD-II codes. This code may be manufacturer-specific. Check AllDataDIY or Mitchell1 for full coverage.\n\nTip: Try /vin to decode the vehicle first, then search by symptoms."}]

    lines = [f"DTC: {entry['code']} — {entry['name']}"]
    lines.append(f"Severity: {entry['severity'].upper()}")
    lines.append(f"System: {entry.get('equipment_type', 'engine')}")
    lines.append("")
    lines.append("Probable Causes:")
    for i, cause in enumerate(entry.get("probable_causes", []), 1):
        lines.append(f"  {i}. {cause}")
    lines.append("")
    lines.append("Fix Steps:")
    for i, step in enumerate(entry.get("fix_steps", []), 1):
        lines.append(f"  {i}. {step}")

    if entry.get("field_tricks"):
        lines.append(f"\nField Trick: {entry['field_tricks']}")

    return [{"type": "text", "text": "\n".join(lines)}]


# ---------------------------------------------------------------------------
# MCP Tool Definitions
# ---------------------------------------------------------------------------
def get_tools():
    return [
        {
            "name": "read_dtcs",
            "description": "Read diagnostic trouble codes (DTCs) from the vehicle's OBD-II system. Returns all stored and pending codes with severity and descriptions. Works in mock mode for testing or real mode with ELM327 adapter.",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "include_pending": {
                        "type": "boolean",
                        "description": "Include pending (not yet confirmed) DTCs. Default true.",
                        "default": True
                    }
                }
            }
        },
        {
            "name": "clear_dtcs",
            "description": "Clear all diagnostic trouble codes and turn off the MIL (Check Engine Light). WARNING: This resets readiness monitors which may affect emissions testing. Requires confirm=true to execute.",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "confirm": {
                        "type": "boolean",
                        "description": "Must be true to actually clear codes. Safety confirmation to prevent accidental clearing."
                    }
                },
                "required": ["confirm"]
            }
        },
        {
            "name": "get_vehicle_info",
            "description": "Get vehicle identification information via OBD-II Mode 09: VIN, calibration IDs, ECU name, OBD standard, and communication protocol. Use the VIN with the /vin endpoint for full vehicle decode.",
            "inputSchema": {
                "type": "object",
                "properties": {}
            }
        },
        {
            "name": "read_pid",
            "description": "Read a specific OBD-II PID (Parameter ID) for live sensor data. Available PIDs: rpm, speed, coolant_temp, intake_temp, maf, throttle_pos, engine_load, fuel_pressure, timing_advance, short_fuel_trim_1, long_fuel_trim_1, o2_voltage_b1s1, barometric_pressure, catalyst_temp_b1s1, control_module_voltage, fuel_level, ambient_temp, commanded_egr. Use pid='all' to read all sensors at once.",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "pid": {
                        "type": "string",
                        "description": "PID name to read (e.g. 'rpm', 'coolant_temp', 'maf', 'all')"
                    }
                },
                "required": ["pid"]
            }
        },
        {
            "name": "get_freeze_frame",
            "description": "Read freeze frame data — a snapshot of sensor values captured at the moment a DTC was set. Shows engine conditions at the time of the fault, critical for diagnosis. Includes RPM, speed, coolant temp, fuel trims, throttle position, and more.",
            "inputSchema": {
                "type": "object",
                "properties": {}
            }
        },
        {
            "name": "diagnose_dtc",
            "description": "Look up a DTC code in the RepairXpert automotive database and get expert diagnosis: probable causes ranked by likelihood, step-by-step fix instructions, severity rating, and field tricks from experienced technicians. Covers 90+ common OBD-II codes including P0xxx generic powertrain, manufacturer-specific Ford, GM, Toyota, and Honda codes.",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "code": {
                        "type": "string",
                        "description": "DTC code to diagnose (e.g. 'P0300', 'P0171', 'P1259')"
                    }
                },
                "required": ["code"]
            }
        }
    ]


TOOL_HANDLERS = {
    "read_dtcs": handle_read_dtcs,
    "clear_dtcs": handle_clear_dtcs,
    "get_vehicle_info": handle_get_vehicle_info,
    "read_pid": handle_read_pid,
    "get_freeze_frame": handle_get_freeze_frame,
    "diagnose_dtc": handle_diagnose_dtc,
}


# ---------------------------------------------------------------------------
# JSON-RPC 2.0 MCP Protocol (stdio transport)
# ---------------------------------------------------------------------------
def send_response(id, result):
    msg = json.dumps({"jsonrpc": "2.0", "id": id, "result": result})
    sys.stdout.write(f"Content-Length: {len(msg.encode())}\r\n\r\n{msg}")
    sys.stdout.flush()


def send_error(id, code, message):
    msg = json.dumps({"jsonrpc": "2.0", "id": id, "error": {"code": code, "message": message}})
    sys.stdout.write(f"Content-Length: {len(msg.encode())}\r\n\r\n{msg}")
    sys.stdout.flush()


def main():
    """Run OBD-II MCP server over stdio."""
    while True:
        try:
            header = ""
            while True:
                line = sys.stdin.readline()
                if not line:
                    return
                header += line
                if header.endswith("\r\n\r\n") or header.endswith("\n\n"):
                    break

            content_length = 0
            for h in header.strip().split("\n"):
                if h.lower().startswith("content-length:"):
                    content_length = int(h.split(":")[1].strip())

            if content_length == 0:
                continue

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
                        "name": "repairxpert-obd",
                        "version": "1.0.0",
                        "description": "OBD-II vehicle diagnostics — read codes, live data, expert diagnosis"
                    }
                })

            elif method == "notifications/initialized":
                pass

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
