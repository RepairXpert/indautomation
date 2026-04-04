"""
Initialize catalog with sample parts data
Loads parts from IndAutomation's existing 500+ part catalog
"""

import logging
from .catalog import PartsDatabase

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)

# Sample parts from IndAutomation catalog
SAMPLE_PARTS = [
    {
        'part_number': 'VFD-3HP-380V',
        'manufacturer': 'ABB',
        'description': '3 HP Variable Frequency Drive 380V',
        'category': 'Variable Frequency Drives',
        'specs': {
            'horsepower': 3,
            'voltage': 380,
            'phase': 3,
            'output_frequency': '0-60Hz'
        },
        'datasheet_url': 'https://automationdirect.com/datasheets/vfd-3hp.pdf',
        'rohs_compliant': True,
        'packaging': 'Individual',
        'suppliers': [
            {
                'supplier': 'automation_direct',
                'supplier_part_number': 'VFD-3HP-ABB',
                'unit_price': 450.00,
                'quantity_available': 25,
                'lead_time_days': 2,
                'quantity_breaks': {10: 420.00, 25: 395.00}
            }
        ]
    },
    {
        'part_number': 'MOTOR-1HP-3PH',
        'manufacturer': 'WEG',
        'description': '1 HP Electric Motor 3-Phase',
        'category': 'Motors',
        'specs': {
            'horsepower': 1,
            'phase': 3,
            'voltage': 230,
            'rpm': 1800
        },
        'rohs_compliant': True,
        'packaging': 'Individual',
        'suppliers': [
            {
                'supplier': 'automation_direct',
                'supplier_part_number': 'MOTOR-1HP-WEG',
                'unit_price': 180.00,
                'quantity_available': 50,
                'lead_time_days': 1,
                'quantity_breaks': {20: 165.00, 50: 150.00}
            }
        ]
    },
    {
        'part_number': 'PLC-24IO-24VDC',
        'manufacturer': 'Siemens',
        'description': 'PLC Module 24 I/O 24VDC',
        'category': 'PLC Modules',
        'specs': {
            'inputs': 12,
            'outputs': 12,
            'voltage': 24,
            'memory': '8KB'
        },
        'rohs_compliant': True,
        'packaging': 'Individual',
        'suppliers': [
            {
                'supplier': 'automation_direct',
                'supplier_part_number': 'PLC-24IO-SIEMENS',
                'unit_price': 325.00,
                'quantity_available': 15,
                'lead_time_days': 3,
                'quantity_breaks': {5: 310.00, 10: 290.00}
            }
        ]
    },
    {
        'part_number': 'SENSOR-PROX-M18',
        'manufacturer': 'Balluff',
        'description': 'Proximity Sensor M18 2-Wire',
        'category': 'Sensors',
        'specs': {
            'type': 'Inductive',
            'size': 'M18',
            'connection': '2-Wire',
            'range': '8mm'
        },
        'rohs_compliant': True,
        'packaging': 'Individual',
        'suppliers': [
            {
                'supplier': 'automation_direct',
                'supplier_part_number': 'SENSOR-PROX-M18-BLF',
                'unit_price': 65.00,
                'quantity_available': 200,
                'lead_time_days': 1,
                'quantity_breaks': {50: 55.00, 100: 48.00}
            }
        ]
    },
    {
        'part_number': 'RELAY-24V-COIL',
        'manufacturer': 'Phoenix Contact',
        'description': 'Industrial Relay 24V Coil',
        'category': 'Relays',
        'specs': {
            'coil_voltage': 24,
            'contacts': '4 CO',
            'current_rating': '10A'
        },
        'rohs_compliant': True,
        'packaging': 'Individual',
        'suppliers': [
            {
                'supplier': 'automation_direct',
                'supplier_part_number': 'RELAY-24V-PHOE',
                'unit_price': 28.00,
                'quantity_available': 500,
                'lead_time_days': 1,
                'quantity_breaks': {100: 24.00, 250: 21.00}
            }
        ]
    },
    {
        'part_number': 'CABLE-CAT6-100M',
        'manufacturer': 'Belden',
        'description': 'CAT6 Ethernet Cable 100m Spool',
        'category': 'Cables',
        'specs': {
            'type': 'CAT6',
            'length': '100m',
            'gauge': '23AWG'
        },
        'rohs_compliant': True,
        'packaging': 'Spool',
        'suppliers': [
            {
                'supplier': 'automation_direct',
                'supplier_part_number': 'CABLE-CAT6-BELDEN',
                'unit_price': 85.00,
                'quantity_available': 30,
                'lead_time_days': 2,
                'quantity_breaks': {5: 80.00, 10: 75.00}
            }
        ]
    },
    {
        'part_number': 'CONTACTOR-32A-24V',
        'manufacturer': 'Eaton',
        'description': '32A Contactor 24V Coil 3-Pole',
        'category': 'Contactors',
        'specs': {
            'current': '32A',
            'coil_voltage': 24,
            'poles': 3,
            'mounting': 'DIN Rail'
        },
        'rohs_compliant': True,
        'packaging': 'Individual',
        'suppliers': [
            {
                'supplier': 'automation_direct',
                'supplier_part_number': 'CONTACTOR-32A-EATON',
                'unit_price': 120.00,
                'quantity_available': 40,
                'lead_time_days': 2,
                'quantity_breaks': {10: 110.00, 25: 100.00}
            }
        ]
    },
    {
        'part_number': 'BREAKER-20A-DIN',
        'manufacturer': 'Schneider Electric',
        'description': '20A Circuit Breaker DIN Rail',
        'category': 'Circuit Breakers',
        'specs': {
            'rating': '20A',
            'voltage': 240,
            'type': 'Single Pole',
            'mounting': 'DIN Rail'
        },
        'rohs_compliant': True,
        'packaging': 'Individual',
        'suppliers': [
            {
                'supplier': 'automation_direct',
                'supplier_part_number': 'BREAKER-20A-SCHN',
                'unit_price': 35.00,
                'quantity_available': 150,
                'lead_time_days': 1,
                'quantity_breaks': {50: 32.00, 100: 29.00}
            }
        ]
    },
    {
        'part_number': 'GEARBOX-RATIO-10',
        'manufacturer': 'Neugart',
        'description': 'Planetary Gearbox Ratio 10:1',
        'category': 'Gearboxes',
        'specs': {
            'type': 'Planetary',
            'ratio': '10:1',
            'output_torque': '50Nm'
        },
        'rohs_compliant': True,
        'packaging': 'Individual',
        'suppliers': [
            {
                'supplier': 'automation_direct',
                'supplier_part_number': 'GEARBOX-10-NEUG',
                'unit_price': 275.00,
                'quantity_available': 12,
                'lead_time_days': 5,
                'quantity_breaks': {}
            }
        ]
    },
    {
        'part_number': 'FASTENER-M8-SS',
        'manufacturer': 'Fastenal',
        'description': 'Stainless Steel M8 Bolt Pack (50)',
        'category': 'Fasteners',
        'specs': {
            'size': 'M8',
            'material': 'Stainless Steel 316',
            'length': '25mm',
            'quantity_per_pack': 50
        },
        'rohs_compliant': True,
        'packaging': 'Pack',
        'suppliers': [
            {
                'supplier': 'automation_direct',
                'supplier_part_number': 'FASTENER-M8-FAST',
                'unit_price': 12.00,
                'quantity_available': 500,
                'lead_time_days': 1,
                'quantity_breaks': {100: 10.50, 250: 9.00}
            }
        ]
    }
]


def initialize_catalog():
    """Initialize catalog with sample parts"""
    db = PartsDatabase()

    logger.info(f"Importing {len(SAMPLE_PARTS)} sample parts...")

    try:
        db.bulk_import_parts(SAMPLE_PARTS)
        logger.info("Sample parts imported successfully")

        # Print summary
        cursor = db.conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM parts")
        total_parts = cursor.fetchone()[0]

        cursor.execute("SELECT COUNT(*) FROM pricing")
        total_prices = cursor.fetchone()[0]

        logger.info(f"Catalog now contains {total_parts} parts and {total_prices} price entries")

    except Exception as e:
        logger.error(f"Failed to initialize catalog: {e}")
    finally:
        db.close()


if __name__ == "__main__":
    initialize_catalog()
