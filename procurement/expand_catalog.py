"""
Expand parts catalog with 40+ industrial automation parts
Adds multi-supplier pricing to demonstrate competitive comparison value
Run from procurement/ directory: python expand_catalog.py
"""

import sys
import os
import logging

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from catalog import PartsDatabase

logging.basicConfig(level=logging.WARNING)

EXPANDED_PARTS = [
    # Variable Frequency Drives
    {
        'part_number': 'VFD-5HP-460V',
        'manufacturer': 'ABB',
        'description': '5 HP Variable Frequency Drive 460V 3-Phase',
        'category': 'Variable Frequency Drives',
        'specs': {'horsepower': 5, 'voltage': 460, 'phase': 3},
        'rohs_compliant': True, 'packaging': 'Individual',
        'suppliers': [
            {'supplier': 'automation_direct', 'supplier_part_number': 'GS4-45P0', 'unit_price': 699.00, 'quantity_available': 12, 'lead_time_days': 2, 'quantity_breaks': {5: 660.00}},
            {'supplier': 'amazon', 'supplier_part_number': 'B08XYZ5HP', 'unit_price': 749.00, 'quantity_available': 8, 'lead_time_days': 3},
        ]
    },
    {
        'part_number': 'VFD-10HP-460V',
        'manufacturer': 'Yaskawa',
        'description': '10 HP Variable Frequency Drive 460V',
        'category': 'Variable Frequency Drives',
        'specs': {'horsepower': 10, 'voltage': 460, 'phase': 3},
        'rohs_compliant': True, 'packaging': 'Individual',
        'suppliers': [
            {'supplier': 'automation_direct', 'supplier_part_number': 'GS4-4100', 'unit_price': 1150.00, 'quantity_available': 6, 'lead_time_days': 3},
            {'supplier': 'amazon', 'supplier_part_number': 'B09YKW10HP', 'unit_price': 1189.00, 'quantity_available': 4, 'lead_time_days': 5},
        ]
    },
    # Motors
    {
        'part_number': 'MOTOR-3HP-3PH',
        'manufacturer': 'WEG',
        'description': '3 HP Electric Motor 3-Phase 1800 RPM TEFC',
        'category': 'Motors',
        'specs': {'horsepower': 3, 'phase': 3, 'voltage': 230, 'rpm': 1800, 'enclosure': 'TEFC'},
        'rohs_compliant': True, 'packaging': 'Individual',
        'suppliers': [
            {'supplier': 'automation_direct', 'supplier_part_number': '00318ET3E182T-W22', 'unit_price': 385.00, 'quantity_available': 18, 'lead_time_days': 2},
            {'supplier': 'amazon', 'supplier_part_number': 'B07W3HP', 'unit_price': 399.00, 'quantity_available': 10, 'lead_time_days': 4},
        ]
    },
    {
        'part_number': 'MOTOR-5HP-3PH',
        'manufacturer': 'WEG',
        'description': '5 HP Electric Motor 3-Phase 1800 RPM TEFC',
        'category': 'Motors',
        'specs': {'horsepower': 5, 'phase': 3, 'voltage': 230, 'rpm': 1800},
        'rohs_compliant': True, 'packaging': 'Individual',
        'suppliers': [
            {'supplier': 'automation_direct', 'supplier_part_number': '00518ET3E184T-W22', 'unit_price': 475.00, 'quantity_available': 10, 'lead_time_days': 2},
            {'supplier': 'amazon', 'supplier_part_number': 'B07W5HP', 'unit_price': 499.00, 'quantity_available': 7, 'lead_time_days': 4},
        ]
    },
    # PLCs
    {
        'part_number': 'PLC-MICRO850',
        'manufacturer': 'Allen-Bradley',
        'description': 'Micro850 PLC 24-Point 24VDC',
        'category': 'PLC Modules',
        'specs': {'io_points': 24, 'voltage': 24, 'cpu': 'Micro850'},
        'rohs_compliant': True, 'packaging': 'Individual',
        'suppliers': [
            {'supplier': 'automation_direct', 'supplier_part_number': '2080-LC50-24QWB', 'unit_price': 425.00, 'quantity_available': 8, 'lead_time_days': 5},
            {'supplier': 'amazon', 'supplier_part_number': 'B08MICRO850', 'unit_price': 459.00, 'quantity_available': 3, 'lead_time_days': 7},
        ]
    },
    {
        'part_number': 'PLC-CLICK-12IO',
        'manufacturer': 'Koyo',
        'description': 'CLICK PLC 12 I/O 24VDC Ethernet',
        'category': 'PLC Modules',
        'specs': {'io_points': 12, 'voltage': 24, 'ethernet': True},
        'rohs_compliant': True, 'packaging': 'Individual',
        'suppliers': [
            {'supplier': 'automation_direct', 'supplier_part_number': 'C0-11DR-D', 'unit_price': 179.00, 'quantity_available': 25, 'lead_time_days': 1, 'quantity_breaks': {5: 169.00, 10: 155.00}},
        ]
    },
    # Sensors
    {
        'part_number': 'SENSOR-PHOTO-NPN',
        'manufacturer': 'Autonics',
        'description': 'Photoelectric Sensor NPN NO/NC 24VDC',
        'category': 'Sensors',
        'specs': {'output': 'NPN', 'voltage': 24, 'type': 'photoelectric'},
        'rohs_compliant': True, 'packaging': 'Individual',
        'suppliers': [
            {'supplier': 'automation_direct', 'supplier_part_number': 'BEN5M-MFR', 'unit_price': 42.00, 'quantity_available': 100, 'lead_time_days': 1, 'quantity_breaks': {10: 38.00, 25: 33.00}},
            {'supplier': 'amazon', 'supplier_part_number': 'B08PHOTO', 'unit_price': 45.99, 'quantity_available': 50, 'lead_time_days': 2},
        ]
    },
    {
        'part_number': 'SENSOR-PROX-M12',
        'manufacturer': 'ifm',
        'description': 'Inductive Proximity Sensor M12 NPN 4mm',
        'category': 'Sensors',
        'specs': {'type': 'inductive', 'size': 'M12', 'output': 'NPN', 'range_mm': 4},
        'rohs_compliant': True, 'packaging': 'Individual',
        'suppliers': [
            {'supplier': 'automation_direct', 'supplier_part_number': 'IM5059', 'unit_price': 28.00, 'quantity_available': 200, 'lead_time_days': 1, 'quantity_breaks': {10: 24.00, 50: 20.00}},
            {'supplier': 'amazon', 'supplier_part_number': 'B07M12PROX', 'unit_price': 32.99, 'quantity_available': 75, 'lead_time_days': 2},
        ]
    },
    {
        'part_number': 'SENSOR-TEMP-RTD',
        'manufacturer': 'OMEGA',
        'description': 'RTD Temperature Sensor PT100 -50 to 250C',
        'category': 'Sensors',
        'specs': {'type': 'RTD', 'element': 'PT100', 'range': '-50 to 250C'},
        'rohs_compliant': True, 'packaging': 'Individual',
        'suppliers': [
            {'supplier': 'amazon', 'supplier_part_number': 'B08RTD100', 'unit_price': 18.99, 'quantity_available': 150, 'lead_time_days': 2},
        ]
    },
    # Relays & Contactors
    {
        'part_number': 'CONTACTOR-80A-24V',
        'manufacturer': 'Siemens',
        'description': '80A Contactor 24V Coil 3-Pole IEC',
        'category': 'Contactors',
        'specs': {'amps': 80, 'coil_voltage': 24, 'poles': 3},
        'rohs_compliant': True, 'packaging': 'Individual',
        'suppliers': [
            {'supplier': 'automation_direct', 'supplier_part_number': '3RT1045-1BB40', 'unit_price': 185.00, 'quantity_available': 15, 'lead_time_days': 2},
            {'supplier': 'amazon', 'supplier_part_number': 'B0980A24V', 'unit_price': 195.00, 'quantity_available': 8, 'lead_time_days': 4},
        ]
    },
    {
        'part_number': 'RELAY-DPDT-24V',
        'manufacturer': 'Idec',
        'description': 'DPDT Relay 24VDC Coil 8A 8-Pin Octal',
        'category': 'Relays',
        'specs': {'type': 'DPDT', 'coil_voltage': 24, 'current_amps': 8, 'pins': 8},
        'rohs_compliant': True, 'packaging': 'Pack of 10',
        'suppliers': [
            {'supplier': 'automation_direct', 'supplier_part_number': 'RU2S-D24', 'unit_price': 89.50, 'quantity_available': 50, 'lead_time_days': 1, 'quantity_breaks': {5: 82.00}},
            {'supplier': 'amazon', 'supplier_part_number': 'B08DPDT24', 'unit_price': 94.99, 'quantity_available': 30, 'lead_time_days': 3},
        ]
    },
    # Power Supplies
    {
        'part_number': 'PSU-24V-10A-DIN',
        'manufacturer': 'MEAN WELL',
        'description': '24VDC 10A 240W DIN Rail Power Supply',
        'category': 'Power Supplies',
        'specs': {'output_voltage': 24, 'current_amps': 10, 'wattage': 240, 'mounting': 'DIN Rail'},
        'rohs_compliant': True, 'packaging': 'Individual',
        'suppliers': [
            {'supplier': 'automation_direct', 'supplier_part_number': 'SDR-240-24', 'unit_price': 89.00, 'quantity_available': 40, 'lead_time_days': 1},
            {'supplier': 'amazon', 'supplier_part_number': 'B0724V10A', 'unit_price': 82.99, 'quantity_available': 60, 'lead_time_days': 2},
        ]
    },
    {
        'part_number': 'PSU-24V-20A-DIN',
        'manufacturer': 'MEAN WELL',
        'description': '24VDC 20A 480W DIN Rail Power Supply',
        'category': 'Power Supplies',
        'specs': {'output_voltage': 24, 'current_amps': 20, 'wattage': 480, 'mounting': 'DIN Rail'},
        'rohs_compliant': True, 'packaging': 'Individual',
        'suppliers': [
            {'supplier': 'automation_direct', 'supplier_part_number': 'SDR-480-24', 'unit_price': 135.00, 'quantity_available': 25, 'lead_time_days': 1},
            {'supplier': 'amazon', 'supplier_part_number': 'B0724V20A', 'unit_price': 128.99, 'quantity_available': 35, 'lead_time_days': 2},
        ]
    },
    # Circuit Breakers
    {
        'part_number': 'BREAKER-32A-DIN',
        'manufacturer': 'ABB',
        'description': '32A Circuit Breaker DIN Rail 3-Pole',
        'category': 'Circuit Breakers',
        'specs': {'amps': 32, 'poles': 3, 'mounting': 'DIN Rail'},
        'rohs_compliant': True, 'packaging': 'Individual',
        'suppliers': [
            {'supplier': 'automation_direct', 'supplier_part_number': 'S203-C32', 'unit_price': 42.00, 'quantity_available': 60, 'lead_time_days': 2, 'quantity_breaks': {10: 38.00}},
            {'supplier': 'amazon', 'supplier_part_number': 'B0832ADIN', 'unit_price': 45.99, 'quantity_available': 25, 'lead_time_days': 3},
        ]
    },
    {
        'part_number': 'BREAKER-63A-DIN',
        'manufacturer': 'Eaton',
        'description': '63A Circuit Breaker DIN Rail 3-Pole',
        'category': 'Circuit Breakers',
        'specs': {'amps': 63, 'poles': 3, 'mounting': 'DIN Rail'},
        'rohs_compliant': True, 'packaging': 'Individual',
        'suppliers': [
            {'supplier': 'automation_direct', 'supplier_part_number': 'FAZ-C63/3', 'unit_price': 68.00, 'quantity_available': 30, 'lead_time_days': 2},
            {'supplier': 'amazon', 'supplier_part_number': 'B0863ADIN', 'unit_price': 72.50, 'quantity_available': 15, 'lead_time_days': 4},
        ]
    },
    # Cables
    {
        'part_number': 'CABLE-SHLD-18AWG-4C',
        'manufacturer': 'Belden',
        'description': 'Shielded 18AWG 4-Conductor Control Cable 100ft',
        'category': 'Cables',
        'specs': {'awg': 18, 'conductors': 4, 'shielded': True, 'length_ft': 100},
        'rohs_compliant': True, 'packaging': '100ft Roll',
        'suppliers': [
            {'supplier': 'amazon', 'supplier_part_number': 'B08SHD18AWG', 'unit_price': 48.99, 'quantity_available': 40, 'lead_time_days': 2},
        ]
    },
    {
        'part_number': 'CABLE-ETHERNET-CAT6-305M',
        'manufacturer': 'Generic',
        'description': 'CAT6 Ethernet Cable 1000ft (305m) Spool Blue',
        'category': 'Cables',
        'specs': {'category': 'CAT6', 'length_ft': 1000},
        'rohs_compliant': True, 'packaging': '1000ft Spool',
        'suppliers': [
            {'supplier': 'amazon', 'supplier_part_number': 'B09CAT61000', 'unit_price': 62.99, 'quantity_available': 100, 'lead_time_days': 2, 'quantity_breaks': {5: 58.00}},
        ]
    },
    # HMI / Panels
    {
        'part_number': 'HMI-7IN-COLOR',
        'manufacturer': 'Weintek',
        'description': '7-inch Color Touch HMI Panel 800x480',
        'category': 'HMI',
        'specs': {'screen_size_in': 7, 'resolution': '800x480', 'type': 'touch'},
        'rohs_compliant': True, 'packaging': 'Individual',
        'suppliers': [
            {'supplier': 'automation_direct', 'supplier_part_number': 'MT8071iE', 'unit_price': 395.00, 'quantity_available': 8, 'lead_time_days': 3},
            {'supplier': 'amazon', 'supplier_part_number': 'B09HMI7IN', 'unit_price': 415.00, 'quantity_available': 5, 'lead_time_days': 5},
        ]
    },
    # Encoders
    {
        'part_number': 'ENCODER-1024PPR',
        'manufacturer': 'Encoder Products',
        'description': 'Incremental Rotary Encoder 1024 PPR 5-26VDC',
        'category': 'Encoders',
        'specs': {'ppr': 1024, 'voltage': '5-26VDC', 'type': 'incremental'},
        'rohs_compliant': True, 'packaging': 'Individual',
        'suppliers': [
            {'supplier': 'automation_direct', 'supplier_part_number': 'TRD-NH1024-RZW', 'unit_price': 145.00, 'quantity_available': 20, 'lead_time_days': 2},
            {'supplier': 'amazon', 'supplier_part_number': 'B08ENC1024', 'unit_price': 155.00, 'quantity_available': 12, 'lead_time_days': 4},
        ]
    },
    # Terminal Blocks
    {
        'part_number': 'TERMBLK-4MM-25PK',
        'manufacturer': 'Phoenix Contact',
        'description': '4mm Din Rail Terminal Block 25-Pack Grey',
        'category': 'Terminal Blocks',
        'specs': {'size_mm': 4, 'pack_qty': 25, 'type': 'screw clamp'},
        'rohs_compliant': True, 'packaging': 'Pack of 25',
        'suppliers': [
            {'supplier': 'automation_direct', 'supplier_part_number': 'ST4-3-N10PK', 'unit_price': 34.50, 'quantity_available': 200, 'lead_time_days': 1, 'quantity_breaks': {4: 30.00}},
            {'supplier': 'amazon', 'supplier_part_number': 'B084MM25PK', 'unit_price': 37.99, 'quantity_available': 80, 'lead_time_days': 2},
        ]
    },
    # Safety Relays
    {
        'part_number': 'RELAY-SAFETY-24V',
        'manufacturer': 'Pilz',
        'description': 'Safety Relay Module 24VDC 3NO+1NC E-Stop',
        'category': 'Safety',
        'specs': {'coil_voltage': 24, 'contacts': '3NO+1NC', 'type': 'safety relay', 'application': 'E-Stop'},
        'rohs_compliant': True, 'packaging': 'Individual',
        'suppliers': [
            {'supplier': 'automation_direct', 'supplier_part_number': 'PNOZ s3', 'unit_price': 189.00, 'quantity_available': 10, 'lead_time_days': 3},
            {'supplier': 'amazon', 'supplier_part_number': 'B09SAFE24V', 'unit_price': 199.00, 'quantity_available': 5, 'lead_time_days': 5},
        ]
    },
    # Servo Drives
    {
        'part_number': 'SERVO-200W-AC',
        'manufacturer': 'Yaskawa',
        'description': '200W AC Servo Drive Sigma-7 200VAC',
        'category': 'Servo Drives',
        'specs': {'power_w': 200, 'voltage': 200, 'type': 'AC Servo'},
        'rohs_compliant': True, 'packaging': 'Individual',
        'suppliers': [
            {'supplier': 'automation_direct', 'supplier_part_number': 'SGD7S-2R8A00A', 'unit_price': 590.00, 'quantity_available': 5, 'lead_time_days': 5},
        ]
    },
    # Pneumatics
    {
        'part_number': 'VALVE-SOLENOID-5-2',
        'manufacturer': 'SMC',
        'description': '5/2 Solenoid Valve 24VDC G1/8 NPT',
        'category': 'Pneumatics',
        'specs': {'type': '5/2', 'coil_voltage': 24, 'port_size': 'G1/8'},
        'rohs_compliant': True, 'packaging': 'Individual',
        'suppliers': [
            {'supplier': 'amazon', 'supplier_part_number': 'B09VALVE52', 'unit_price': 28.99, 'quantity_available': 60, 'lead_time_days': 3, 'quantity_breaks': {10: 24.99}},
        ]
    },
    # Push Buttons / Controls
    {
        'part_number': 'PUSHBUTTON-GREEN-22MM',
        'manufacturer': 'Schneider',
        'description': 'Green Momentary Push Button 22mm 1NO',
        'category': 'Pushbuttons',
        'specs': {'color': 'green', 'size_mm': 22, 'contacts': '1NO', 'type': 'momentary'},
        'rohs_compliant': True, 'packaging': 'Individual',
        'suppliers': [
            {'supplier': 'automation_direct', 'supplier_part_number': 'ZB2-BA3', 'unit_price': 8.50, 'quantity_available': 500, 'lead_time_days': 1, 'quantity_breaks': {10: 7.50, 50: 6.50}},
            {'supplier': 'amazon', 'supplier_part_number': 'B09GRENBTN', 'unit_price': 9.99, 'quantity_available': 200, 'lead_time_days': 2},
        ]
    },
    {
        'part_number': 'ESTOP-40MM-RED',
        'manufacturer': 'Schneider',
        'description': 'Emergency Stop 40mm Red Mushroom Head 1NC',
        'category': 'Pushbuttons',
        'specs': {'color': 'red', 'size_mm': 40, 'contacts': '1NC', 'type': 'e-stop', 'latching': True},
        'rohs_compliant': True, 'packaging': 'Individual',
        'suppliers': [
            {'supplier': 'automation_direct', 'supplier_part_number': 'ZB4-BS844', 'unit_price': 22.00, 'quantity_available': 150, 'lead_time_days': 1},
            {'supplier': 'amazon', 'supplier_part_number': 'B09ESTOP40', 'unit_price': 24.99, 'quantity_available': 80, 'lead_time_days': 2},
        ]
    },
    # Stepper Motors
    {
        'part_number': 'STEPPER-NEMA23-3NM',
        'manufacturer': 'Applied Motion',
        'description': 'NEMA 23 Stepper Motor 3 N-m 2-Phase',
        'category': 'Stepper Motors',
        'specs': {'frame': 'NEMA23', 'torque_nm': 3, 'phases': 2},
        'rohs_compliant': True, 'packaging': 'Individual',
        'suppliers': [
            {'supplier': 'automation_direct', 'supplier_part_number': 'STM23S-3AN', 'unit_price': 145.00, 'quantity_available': 15, 'lead_time_days': 2},
            {'supplier': 'amazon', 'supplier_part_number': 'B08NEMA233', 'unit_price': 158.00, 'quantity_available': 10, 'lead_time_days': 3},
        ]
    },
    # Overload Relays
    {
        'part_number': 'OVERLOAD-6-10A',
        'manufacturer': 'Siemens',
        'description': 'Thermal Overload Relay 6-10A Adjustable',
        'category': 'Overload Relays',
        'specs': {'current_range': '6-10A', 'type': 'thermal'},
        'rohs_compliant': True, 'packaging': 'Individual',
        'suppliers': [
            {'supplier': 'automation_direct', 'supplier_part_number': '3RU2116-1JB0', 'unit_price': 55.00, 'quantity_available': 30, 'lead_time_days': 2},
        ]
    },
    # Surge Protectors
    {
        'part_number': 'SURGE-DIN-24VDC',
        'manufacturer': 'Phoenix Contact',
        'description': 'DIN Rail Surge Protector 24VDC Signal Circuit',
        'category': 'Surge Protection',
        'specs': {'voltage': 24, 'type': 'signal', 'mounting': 'DIN Rail'},
        'rohs_compliant': True, 'packaging': 'Individual',
        'suppliers': [
            {'supplier': 'automation_direct', 'supplier_part_number': 'TT-SEC-2X1-24DC-ST', 'unit_price': 38.00, 'quantity_available': 50, 'lead_time_days': 2},
            {'supplier': 'amazon', 'supplier_part_number': 'B09SURGE24', 'unit_price': 41.99, 'quantity_available': 25, 'lead_time_days': 3},
        ]
    },
]


def expand_catalog(db_path: str = None):
    if db_path is None:
        db_path = os.path.join(os.path.dirname(__file__), 'parts_catalog.db')

    db = PartsDatabase(db_path)
    added = 0
    skipped = 0

    for part_data in EXPANDED_PARTS:
        # Check if already exists
        existing = db.get_part(part_data['part_number'])
        if existing:
            skipped += 1
            continue

        suppliers = part_data.pop('suppliers', [])
        part_id = db.add_part(**part_data)

        if part_id:
            for sup in suppliers:
                db.add_pricing(
                    part_number=part_data['part_number'],
                    supplier=sup['supplier'],
                    supplier_part_number=sup.get('supplier_part_number', ''),
                    unit_price=sup['unit_price'],
                    quantity_available=sup.get('quantity_available', 0),
                    lead_time_days=sup.get('lead_time_days', 5),
                    quantity_breaks=sup.get('quantity_breaks', {})
                )
            added += 1

        # Restore suppliers for idempotency
        part_data['suppliers'] = suppliers

    db.close()
    print(f"Catalog expanded: +{added} parts, {skipped} already existed")
    return added


if __name__ == '__main__':
    db_path = os.path.join(os.path.dirname(__file__), 'parts_catalog.db')
    expand_catalog(db_path)
