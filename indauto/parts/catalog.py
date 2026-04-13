"""Parts catalog — maps fault categories to replacement parts with supplier buy links.

Each category contains a list of parts, each with multiple supplier options
sorted by relevance for industrial automation purchasing.
"""

# Affiliate tag placeholders — replace with real affiliate IDs when enrolled
AMAZON_TAG = "repairxpert-20"
AUTOMATIONDIRECT_AFF = ""  # AutomationDirect doesn't do traditional affiliates — use direct links

PARTS_CATALOG: dict[str, list[dict]] = {

    "proximity_sensor": [
        {
            "name": "Allen-Bradley 872C Inductive Prox Sensor 18mm",
            "part_no": "872C-D5NP18-D4",
            "description": "3-wire DC NPN, 18mm barrel, 5mm sensing range, shielded",
            "suppliers": [
                {"name": "AutomationDirect", "url": "https://www.automationdirect.com/adc/shopping/catalog/sensors_-z-_encoders/proximity_sensors/18mm_round/ak1-ap-3h", "est_price": 42.00},
                {"name": "Amazon", "url": f"https://www.amazon.com/s?k=872C-D5NP18-D4+inductive+proximity+sensor&tag={AMAZON_TAG}", "est_price": 65.00},
                {"name": "Grainger", "url": "https://www.grainger.com/search?searchQuery=872C-D5NP18-D4", "est_price": 78.00},
            ],
        },
        {
            "name": "IFM Efector IFS204 Inductive Sensor 12mm",
            "part_no": "IFS204",
            "description": "12mm flush mount, 4mm range, M12 connector, PNP NO",
            "suppliers": [
                {"name": "AutomationDirect", "url": "https://www.automationdirect.com/adc/shopping/catalog/sensors_-z-_encoders/proximity_sensors/12mm_round", "est_price": 38.00},
                {"name": "Amazon", "url": f"https://www.amazon.com/s?k=IFM+IFS204+inductive+sensor&tag={AMAZON_TAG}", "est_price": 45.00},
                {"name": "Digikey", "url": "https://www.digikey.com/en/products/filter/proximity-sensors/528?s=IFS204", "est_price": 52.00},
            ],
        },
        {
            "name": "Balluff BES 18mm Inductive Sensor",
            "part_no": "BES M18MI-PSC80B-S04K",
            "description": "18mm barrel, 8mm range, PNP NO, M12 connector",
            "suppliers": [
                {"name": "AutomationDirect", "url": "https://www.automationdirect.com/adc/shopping/catalog/sensors_-z-_encoders/proximity_sensors/18mm_round", "est_price": 48.00},
                {"name": "McMaster-Carr", "url": "https://www.mcmaster.com/proximity-sensors/thread-size~m18", "est_price": 55.00},
                {"name": "Amazon", "url": f"https://www.amazon.com/s?k=Balluff+BES+18mm+inductive+proximity+sensor&tag={AMAZON_TAG}", "est_price": 50.00},
            ],
        },
    ],

    "photoelectric_sensor": [
        {
            "name": "Banner QS18VP6D Photoelectric Sensor",
            "part_no": "QS18VP6D",
            "description": "Diffuse mode, 18mm barrel, 100mm range, PNP",
            "suppliers": [
                {"name": "AutomationDirect", "url": "https://www.automationdirect.com/adc/shopping/catalog/sensors_-z-_encoders/photoelectric_sensors", "est_price": 65.00},
                {"name": "Amazon", "url": f"https://www.amazon.com/s?k=Banner+QS18+photoelectric+sensor&tag={AMAZON_TAG}", "est_price": 72.00},
                {"name": "Grainger", "url": "https://www.grainger.com/search?searchQuery=QS18VP6D+photoelectric", "est_price": 85.00},
            ],
        },
        {
            "name": "IFM Efector O5D100 Photoelectric Sensor",
            "part_no": "O5D100",
            "description": "Diffuse reflection, M18, 50-1000mm range, IO-Link",
            "suppliers": [
                {"name": "AutomationDirect", "url": "https://www.automationdirect.com/adc/shopping/catalog/sensors_-z-_encoders/photoelectric_sensors", "est_price": 85.00},
                {"name": "Amazon", "url": f"https://www.amazon.com/s?k=IFM+O5D100+photoelectric+sensor&tag={AMAZON_TAG}", "est_price": 95.00},
                {"name": "Digikey", "url": "https://www.digikey.com/en/products/filter/optical-sensors/529?s=O5D100", "est_price": 90.00},
            ],
        },
    ],

    "vfd_drive": [
        {
            "name": "Allen-Bradley PowerFlex 525 AC Drive 1HP",
            "part_no": "25B-D2P3N114",
            "description": "1HP, 480V, 3-phase, built-in EtherNet/IP, EMC filter",
            "suppliers": [
                {"name": "AutomationDirect", "url": "https://www.automationdirect.com/adc/shopping/catalog/drives_-a-_soft_starters/ac_variable_frequency_drives_(vfd)", "est_price": 395.00},
                {"name": "Amazon", "url": f"https://www.amazon.com/s?k=PowerFlex+525+AC+drive+1HP&tag={AMAZON_TAG}", "est_price": 450.00},
                {"name": "Grainger", "url": "https://www.grainger.com/search?searchQuery=PowerFlex+525+variable+frequency+drive", "est_price": 520.00},
            ],
        },
        {
            "name": "ABB ACS580 General Purpose Drive 2HP",
            "part_no": "ACS580-01-05A7-4",
            "description": "2HP, 480V, built-in safe torque off, adaptive programming",
            "suppliers": [
                {"name": "AutomationDirect", "url": "https://www.automationdirect.com/adc/shopping/catalog/drives_-a-_soft_starters/ac_variable_frequency_drives_(vfd)", "est_price": 425.00},
                {"name": "Amazon", "url": f"https://www.amazon.com/s?k=ABB+ACS580+variable+frequency+drive&tag={AMAZON_TAG}", "est_price": 480.00},
                {"name": "Grainger", "url": "https://www.grainger.com/search?searchQuery=ABB+ACS580+drive", "est_price": 550.00},
            ],
        },
        {
            "name": "GS20 AC Drive 1HP (Budget Option)",
            "part_no": "GS20-20P5",
            "description": "1HP, 230V, sensorless vector, compact size — good replacement for testing",
            "suppliers": [
                {"name": "AutomationDirect", "url": "https://www.automationdirect.com/adc/shopping/catalog/drives_-a-_soft_starters/ac_variable_frequency_drives_(vfd)/gs20_series/gs20-20p5", "est_price": 149.00},
                {"name": "Amazon", "url": f"https://www.amazon.com/s?k=GS20+variable+frequency+drive+1HP&tag={AMAZON_TAG}", "est_price": 175.00},
            ],
        },
    ],

    "motor_overload_relay": [
        {
            "name": "Allen-Bradley 193-T1AC Overload Relay",
            "part_no": "193-T1AC16",
            "description": "Bimetallic overload, 11.3-16A, Class 10, manual/auto reset",
            "suppliers": [
                {"name": "AutomationDirect", "url": "https://www.automationdirect.com/adc/shopping/catalog/motor_controls/overload_relays", "est_price": 42.00},
                {"name": "Amazon", "url": f"https://www.amazon.com/s?k=thermal+overload+relay+16A+motor+protection&tag={AMAZON_TAG}", "est_price": 25.00},
                {"name": "Grainger", "url": "https://www.grainger.com/search?searchQuery=193-T1AC+overload+relay", "est_price": 55.00},
            ],
        },
        {
            "name": "Schneider LRD16 Thermal Overload Relay",
            "part_no": "LRD16",
            "description": "9-13A, Class 10, for TeSys D contactors",
            "suppliers": [
                {"name": "AutomationDirect", "url": "https://www.automationdirect.com/adc/shopping/catalog/motor_controls/overload_relays", "est_price": 35.00},
                {"name": "Amazon", "url": f"https://www.amazon.com/s?k=Schneider+LRD16+thermal+overload+relay&tag={AMAZON_TAG}", "est_price": 28.00},
                {"name": "McMaster-Carr", "url": "https://www.mcmaster.com/overload-relays", "est_price": 45.00},
            ],
        },
    ],

    "safety_relay": [
        {
            "name": "Allen-Bradley Guardmaster 440R-N23126",
            "part_no": "440R-N23126",
            "description": "Dual-channel safety relay, 24VDC, 3 N.O. + 1 N.C., Cat 4 / PLe",
            "suppliers": [
                {"name": "AutomationDirect", "url": "https://www.automationdirect.com/adc/shopping/catalog/safety/safety_relays", "est_price": 125.00},
                {"name": "Amazon", "url": f"https://www.amazon.com/s?k=safety+relay+dual+channel+24VDC&tag={AMAZON_TAG}", "est_price": 95.00},
                {"name": "Grainger", "url": "https://www.grainger.com/search?searchQuery=440R+safety+relay+guardmaster", "est_price": 155.00},
            ],
        },
        {
            "name": "Pilz PNOZ X3 Safety Relay",
            "part_no": "774310",
            "description": "24VDC/AC, 3 N.O. + 1 N.C., E-stop and safety gate monitoring",
            "suppliers": [
                {"name": "AutomationDirect", "url": "https://www.automationdirect.com/adc/shopping/catalog/safety/safety_relays", "est_price": 145.00},
                {"name": "Amazon", "url": f"https://www.amazon.com/s?k=Pilz+PNOZ+X3+safety+relay&tag={AMAZON_TAG}", "est_price": 135.00},
                {"name": "McMaster-Carr", "url": "https://www.mcmaster.com/safety-relays", "est_price": 165.00},
            ],
        },
    ],

    "plc_battery": [
        {
            "name": "Allen-Bradley 1756-BA2 PLC Battery",
            "part_no": "1756-BA2",
            "description": "ControlLogix battery module, 3V lithium, 2-year life",
            "suppliers": [
                {"name": "AutomationDirect", "url": "https://www.automationdirect.com/adc/shopping/catalog/programmable_controllers/plc_batteries", "est_price": 22.00},
                {"name": "Amazon", "url": f"https://www.amazon.com/s?k=1756-BA2+Allen+Bradley+PLC+battery&tag={AMAZON_TAG}", "est_price": 18.00},
                {"name": "Grainger", "url": "https://www.grainger.com/search?searchQuery=1756-BA2+PLC+battery", "est_price": 28.00},
            ],
        },
        {
            "name": "Mitsubishi Q6BAT PLC Battery",
            "part_no": "Q6BAT",
            "description": "MELSEC-Q series, 3.6V lithium, ER17330V",
            "suppliers": [
                {"name": "Amazon", "url": f"https://www.amazon.com/s?k=Q6BAT+Mitsubishi+PLC+battery&tag={AMAZON_TAG}", "est_price": 12.00},
                {"name": "Digikey", "url": "https://www.digikey.com/en/products/filter/batteries/90?s=Q6BAT", "est_price": 15.00},
                {"name": "AutomationDirect", "url": "https://www.automationdirect.com/adc/shopping/catalog/programmable_controllers/plc_batteries", "est_price": 14.00},
            ],
        },
        {
            "name": "Siemens 6ES7971-0BA02 PLC Battery",
            "part_no": "6ES7971-0BA02",
            "description": "S7-300/400 backup battery, 3.6V lithium AA",
            "suppliers": [
                {"name": "Amazon", "url": f"https://www.amazon.com/s?k=6ES7971+Siemens+PLC+battery&tag={AMAZON_TAG}", "est_price": 15.00},
                {"name": "Mouser", "url": "https://www.mouser.com/Search/Refine?Keyword=6ES7971-0BA02", "est_price": 18.00},
            ],
        },
    ],

    "encoder": [
        {
            "name": "Omron E6B2-CWZ6C Rotary Encoder",
            "part_no": "E6B2-CWZ6C-1024P/R",
            "description": "Incremental, 1024 PPR, 5-24VDC, NPN open collector",
            "suppliers": [
                {"name": "AutomationDirect", "url": "https://www.automationdirect.com/adc/shopping/catalog/sensors_-z-_encoders/encoders/incremental_encoders", "est_price": 85.00},
                {"name": "Amazon", "url": f"https://www.amazon.com/s?k=Omron+E6B2+rotary+encoder+1024&tag={AMAZON_TAG}", "est_price": 75.00},
                {"name": "Digikey", "url": "https://www.digikey.com/en/products/filter/encoders/166?s=E6B2-CWZ6C", "est_price": 95.00},
            ],
        },
        {
            "name": "Autonics E40S8-1024-3-T-24 Encoder",
            "part_no": "E40S8-1024-3-T-24",
            "description": "40mm body, 1024 PPR, totem pole output, 8mm shaft",
            "suppliers": [
                {"name": "AutomationDirect", "url": "https://www.automationdirect.com/adc/shopping/catalog/sensors_-z-_encoders/encoders/incremental_encoders/trd-s_series", "est_price": 65.00},
                {"name": "Amazon", "url": f"https://www.amazon.com/s?k=Autonics+E40S+rotary+encoder+1024+PPR&tag={AMAZON_TAG}", "est_price": 58.00},
            ],
        },
    ],

    "pneumatic_valve": [
        {
            "name": "SMC SY3120 Solenoid Valve",
            "part_no": "SY3120-5LZD-M5",
            "description": "5/2 way, 24VDC, M5 ports, direct piping, 0.15-0.7 MPa",
            "suppliers": [
                {"name": "AutomationDirect", "url": "https://www.automationdirect.com/adc/shopping/catalog/pneumatic_components/directional_control_valves", "est_price": 32.00},
                {"name": "Amazon", "url": f"https://www.amazon.com/s?k=SMC+SY3120+solenoid+valve+24VDC&tag={AMAZON_TAG}", "est_price": 28.00},
                {"name": "McMaster-Carr", "url": "https://www.mcmaster.com/pneumatic-solenoid-valves", "est_price": 45.00},
                {"name": "Grainger", "url": "https://www.grainger.com/search?searchQuery=SMC+SY3120+solenoid+valve", "est_price": 42.00},
            ],
        },
        {
            "name": "Festo VUVG Solenoid Valve",
            "part_no": "VUVG-LK14-M52-AT-G18-1R8L",
            "description": "5/2 way, 24VDC, G1/8 ports, spring return",
            "suppliers": [
                {"name": "AutomationDirect", "url": "https://www.automationdirect.com/adc/shopping/catalog/pneumatic_components/directional_control_valves", "est_price": 55.00},
                {"name": "Amazon", "url": f"https://www.amazon.com/s?k=Festo+VUVG+solenoid+valve&tag={AMAZON_TAG}", "est_price": 62.00},
                {"name": "Grainger", "url": "https://www.grainger.com/search?searchQuery=Festo+VUVG+solenoid+valve", "est_price": 70.00},
            ],
        },
        {
            "name": "Air Pressure Regulator + Filter Combo",
            "part_no": "AW30-03BG",
            "description": "SMC AW series, 3/8 NPT, 5-125 PSI, with gauge and bowl guard",
            "suppliers": [
                {"name": "AutomationDirect", "url": "https://www.automationdirect.com/adc/shopping/catalog/pneumatic_components/air_preparation_(frl)", "est_price": 38.00},
                {"name": "Amazon", "url": f"https://www.amazon.com/s?k=SMC+air+filter+regulator+3%2F8&tag={AMAZON_TAG}", "est_price": 32.00},
                {"name": "McMaster-Carr", "url": "https://www.mcmaster.com/air-filter-regulators", "est_price": 48.00},
            ],
        },
    ],

    "thermocouple": [
        {
            "name": "Type K Thermocouple Probe 6 inch",
            "part_no": "TC-K-NPT-U-72",
            "description": "Type K, 1/4 NPT, ungrounded, 6 inch length, -200 to 1250C",
            "suppliers": [
                {"name": "AutomationDirect", "url": "https://www.automationdirect.com/adc/shopping/catalog/process_control_-a-_measurement/temperature_sensors/thermocouples", "est_price": 22.00},
                {"name": "Amazon", "url": f"https://www.amazon.com/s?k=type+K+thermocouple+probe+1%2F4+NPT+stainless&tag={AMAZON_TAG}", "est_price": 12.00},
                {"name": "McMaster-Carr", "url": "https://www.mcmaster.com/thermocouples/thermocouple-type~k", "est_price": 28.00},
                {"name": "Omega", "url": "https://www.omega.com/en-us/temperature-measurement/temperature-probes/thermocouple-probes/c/thermocouple-probes", "est_price": 25.00},
            ],
        },
        {
            "name": "Type J Thermocouple Probe 6 inch",
            "part_no": "TC-J-NPT-U-72",
            "description": "Type J, 1/4 NPT, ungrounded, 6 inch, -210 to 760C",
            "suppliers": [
                {"name": "AutomationDirect", "url": "https://www.automationdirect.com/adc/shopping/catalog/process_control_-a-_measurement/temperature_sensors/thermocouples", "est_price": 20.00},
                {"name": "Amazon", "url": f"https://www.amazon.com/s?k=type+J+thermocouple+probe+stainless&tag={AMAZON_TAG}", "est_price": 10.00},
                {"name": "Omega", "url": "https://www.omega.com/en-us/temperature-measurement/temperature-probes/thermocouple-probes/c/thermocouple-probes", "est_price": 22.00},
            ],
        },
    ],

    "contactor": [
        {
            "name": "Allen-Bradley 100-C09D10 Contactor",
            "part_no": "100-C09D10",
            "description": "9A, 120VAC coil, 3-pole, 1 N.O. aux contact",
            "suppliers": [
                {"name": "AutomationDirect", "url": "https://www.automationdirect.com/adc/shopping/catalog/motor_controls/iec_contactors_-a-_starters", "est_price": 45.00},
                {"name": "Amazon", "url": f"https://www.amazon.com/s?k=IEC+contactor+9A+120V+coil&tag={AMAZON_TAG}", "est_price": 35.00},
                {"name": "Grainger", "url": "https://www.grainger.com/search?searchQuery=100-C09+contactor", "est_price": 65.00},
            ],
        },
        {
            "name": "Schneider LC1D09G7 Contactor",
            "part_no": "LC1D09G7",
            "description": "9A, 120VAC coil, TeSys D, 3-pole",
            "suppliers": [
                {"name": "AutomationDirect", "url": "https://www.automationdirect.com/adc/shopping/catalog/motor_controls/iec_contactors_-a-_starters", "est_price": 38.00},
                {"name": "Amazon", "url": f"https://www.amazon.com/s?k=Schneider+LC1D09+contactor&tag={AMAZON_TAG}", "est_price": 30.00},
                {"name": "McMaster-Carr", "url": "https://www.mcmaster.com/contactors", "est_price": 52.00},
            ],
        },
    ],

    "fuse": [
        {
            "name": "Bussmann FRN-R-30 Time-Delay Fuse",
            "part_no": "FRN-R-30",
            "description": "30A, 250V, Class RK5, dual element time-delay",
            "suppliers": [
                {"name": "AutomationDirect", "url": "https://www.automationdirect.com/adc/shopping/catalog/circuit_protection/fuses", "est_price": 8.00},
                {"name": "Amazon", "url": f"https://www.amazon.com/s?k=Bussmann+FRN-R-30+fuse+time+delay&tag={AMAZON_TAG}", "est_price": 6.50},
                {"name": "Grainger", "url": "https://www.grainger.com/search?searchQuery=FRN-R-30+fuse", "est_price": 10.00},
                {"name": "McMaster-Carr", "url": "https://www.mcmaster.com/fuses/fuse-class~rk5/", "est_price": 9.00},
            ],
        },
        {
            "name": "Bussmann FRN-R-15 Time-Delay Fuse",
            "part_no": "FRN-R-15",
            "description": "15A, 250V, Class RK5, motor circuit protection",
            "suppliers": [
                {"name": "AutomationDirect", "url": "https://www.automationdirect.com/adc/shopping/catalog/circuit_protection/fuses", "est_price": 7.00},
                {"name": "Amazon", "url": f"https://www.amazon.com/s?k=Bussmann+FRN-R-15+fuse&tag={AMAZON_TAG}", "est_price": 5.50},
                {"name": "Grainger", "url": "https://www.grainger.com/search?searchQuery=FRN-R-15+fuse", "est_price": 9.00},
            ],
        },
    ],

    "limit_switch": [
        {
            "name": "Allen-Bradley 802T-AP Limit Switch",
            "part_no": "802T-AP",
            "description": "NEMA Type 4, lever type, 1 N.O. + 1 N.C., plug-in",
            "suppliers": [
                {"name": "AutomationDirect", "url": "https://www.automationdirect.com/adc/shopping/catalog/sensors_-z-_encoders/limit_switches", "est_price": 65.00},
                {"name": "Amazon", "url": f"https://www.amazon.com/s?k=802T+limit+switch+lever+type&tag={AMAZON_TAG}", "est_price": 55.00},
                {"name": "Grainger", "url": "https://www.grainger.com/search?searchQuery=802T-AP+limit+switch", "est_price": 82.00},
            ],
        },
        {
            "name": "Omron D4N-4132 Safety Limit Switch",
            "part_no": "D4N-4132",
            "description": "Top plunger, 1 N.C. + 1 N.O., M20 conduit entry",
            "suppliers": [
                {"name": "AutomationDirect", "url": "https://www.automationdirect.com/adc/shopping/catalog/sensors_-z-_encoders/limit_switches", "est_price": 28.00},
                {"name": "Amazon", "url": f"https://www.amazon.com/s?k=Omron+D4N+limit+switch&tag={AMAZON_TAG}", "est_price": 22.00},
            ],
        },
    ],

    "servo_drive": [
        {
            "name": "Allen-Bradley Kinetix 5500 Servo Drive",
            "part_no": "2198-H008-ERS2",
            "description": "0.8kW, 480V, integrated safe torque off, EtherNet/IP",
            "suppliers": [
                {"name": "Grainger", "url": "https://www.grainger.com/search?searchQuery=Kinetix+5500+servo+drive", "est_price": 1250.00},
                {"name": "Amazon", "url": f"https://www.amazon.com/s?k=Kinetix+5500+servo+drive&tag={AMAZON_TAG}", "est_price": 1100.00},
            ],
        },
        {
            "name": "Yaskawa SGD7S Sigma-7 Servo Amplifier",
            "part_no": "SGD7S-R90A00A002",
            "description": "100W, single-phase 200V, EtherCAT, STO built-in",
            "suppliers": [
                {"name": "AutomationDirect", "url": "https://www.automationdirect.com/adc/shopping/catalog/motion_control/servo_systems", "est_price": 385.00},
                {"name": "Amazon", "url": f"https://www.amazon.com/s?k=Yaskawa+Sigma-7+servo+drive&tag={AMAZON_TAG}", "est_price": 420.00},
            ],
        },
    ],

    "conveyor_belt": [
        {
            "name": "Intralox Series 400 Flat Top Belt (per ft)",
            "part_no": "S400-FT-12",
            "description": "12 inch wide, acetal flat top, food-grade option available",
            "suppliers": [
                {"name": "McMaster-Carr", "url": "https://www.mcmaster.com/conveyor-belts", "est_price": 35.00},
                {"name": "Grainger", "url": "https://www.grainger.com/search?searchQuery=flat+top+conveyor+belt+12+inch", "est_price": 42.00},
                {"name": "Amazon", "url": f"https://www.amazon.com/s?k=flat+top+modular+conveyor+belt+12+inch&tag={AMAZON_TAG}", "est_price": 30.00},
            ],
        },
    ],

    "conveyor_motor": [
        {
            "name": "Baldor/ABB 1HP TEFC Motor",
            "part_no": "EM3554T",
            "description": "1HP, 1765RPM, 143TC frame, 230/460V, TEFC, premium efficiency",
            "suppliers": [
                {"name": "AutomationDirect", "url": "https://www.automationdirect.com/adc/shopping/catalog/motors/ac_motors", "est_price": 285.00},
                {"name": "Amazon", "url": f"https://www.amazon.com/s?k=Baldor+1HP+TEFC+motor+143TC&tag={AMAZON_TAG}", "est_price": 310.00},
                {"name": "Grainger", "url": "https://www.grainger.com/search?searchQuery=EM3554T+motor", "est_price": 345.00},
            ],
        },
    ],

    "network_module": [
        {
            "name": "Allen-Bradley 1756-EN2T EtherNet/IP Module",
            "part_no": "1756-EN2T",
            "description": "ControlLogix EtherNet/IP module, dual port, DLR capable",
            "suppliers": [
                {"name": "Amazon", "url": f"https://www.amazon.com/s?k=1756-EN2T+ethernet+module&tag={AMAZON_TAG}", "est_price": 850.00},
                {"name": "Grainger", "url": "https://www.grainger.com/search?searchQuery=1756-EN2T", "est_price": 1050.00},
            ],
        },
        {
            "name": "Siemens CM 1542-1 PROFINET Module",
            "part_no": "6GK7542-1AX00-0XE0",
            "description": "S7-1500 PROFINET IO controller, 2-port switch",
            "suppliers": [
                {"name": "Amazon", "url": f"https://www.amazon.com/s?k=Siemens+PROFINET+communication+module&tag={AMAZON_TAG}", "est_price": 650.00},
                {"name": "Mouser", "url": "https://www.mouser.com/Search/Refine?Keyword=6GK7542-1AX00", "est_price": 720.00},
            ],
        },
        {
            "name": "Managed Industrial Ethernet Switch 8-Port",
            "part_no": "SE2-SW5U",
            "description": "8-port managed switch, DIN rail, 10/100 Mbps, IGMP snooping",
            "suppliers": [
                {"name": "AutomationDirect", "url": "https://www.automationdirect.com/adc/shopping/catalog/communications/industrial_ethernet/ethernet_switches", "est_price": 145.00},
                {"name": "Amazon", "url": f"https://www.amazon.com/s?k=industrial+managed+ethernet+switch+8+port+DIN+rail&tag={AMAZON_TAG}", "est_price": 120.00},
                {"name": "Mouser", "url": "https://www.mouser.com/Networking-Solutions/Ethernet-Switches/_/N-1z0w34g?Keyword=industrial+managed+switch", "est_price": 155.00},
            ],
        },
    ],

    "hydraulic_pump": [
        {
            "name": "Eaton Vickers V20 Vane Pump",
            "part_no": "V20-1P9P-1C11",
            "description": "Fixed displacement, 1.0 GPM, 1800 RPM, 1000 PSI",
            "suppliers": [
                {"name": "McMaster-Carr", "url": "https://www.mcmaster.com/hydraulic-pumps", "est_price": 285.00},
                {"name": "Amazon", "url": f"https://www.amazon.com/s?k=Eaton+Vickers+V20+vane+pump&tag={AMAZON_TAG}", "est_price": 310.00},
                {"name": "Grainger", "url": "https://www.grainger.com/search?searchQuery=Vickers+V20+hydraulic+pump", "est_price": 350.00},
            ],
        },
    ],

    "barcode_scanner": [
        {
            "name": "Cognex DataMan 8072 Fixed Scanner",
            "part_no": "DM8072",
            "description": "High-speed fixed-mount, 1D/2D, liquid lens, EtherNet/IP",
            "suppliers": [
                {"name": "Amazon", "url": f"https://www.amazon.com/s?k=Cognex+DataMan+8000+fixed+barcode+scanner&tag={AMAZON_TAG}", "est_price": 1800.00},
                {"name": "Grainger", "url": "https://www.grainger.com/search?searchQuery=Cognex+DataMan+barcode+scanner", "est_price": 2100.00},
            ],
        },
        {
            "name": "Keyence SR-2000 Barcode Reader",
            "part_no": "SR-2000",
            "description": "Ultra-compact, autofocus, 1D/2D, EtherNet/IP + serial",
            "suppliers": [
                {"name": "Amazon", "url": f"https://www.amazon.com/s?k=Keyence+SR-2000+barcode+reader&tag={AMAZON_TAG}", "est_price": 1500.00},
                {"name": "Grainger", "url": "https://www.grainger.com/search?searchQuery=Keyence+barcode+reader", "est_price": 1700.00},
            ],
        },
    ],

    "stretch_wrap_film": [
        {
            "name": "Machine Stretch Wrap Film 20 inch",
            "part_no": "MSW-20-80-5000",
            "description": "20 inch x 5000 ft, 80 gauge, cast film, machine grade",
            "suppliers": [
                {"name": "Amazon", "url": f"https://www.amazon.com/s?k=machine+stretch+wrap+film+20+inch+80+gauge&tag={AMAZON_TAG}", "est_price": 35.00},
                {"name": "Grainger", "url": "https://www.grainger.com/search?searchQuery=machine+stretch+wrap+20+inch", "est_price": 42.00},
            ],
        },
    ],

    "label_printer": [
        {
            "name": "Zebra ZT411 Industrial Label Printer",
            "part_no": "ZT41142-T010000Z",
            "description": "203 dpi, 4 inch wide, thermal transfer, USB/Ethernet/Serial",
            "suppliers": [
                {"name": "Amazon", "url": f"https://www.amazon.com/s?k=Zebra+ZT411+industrial+label+printer&tag={AMAZON_TAG}", "est_price": 1250.00},
                {"name": "Grainger", "url": "https://www.grainger.com/search?searchQuery=Zebra+ZT411+label+printer", "est_price": 1400.00},
            ],
        },
    ],

    "vision_camera": [
        {
            "name": "Cognex In-Sight 2000 Vision Sensor",
            "part_no": "IS2000M-120-40-000",
            "description": "Fixed-focus, monochrome, built-in lighting, EasyBuilder interface",
            "suppliers": [
                {"name": "Amazon", "url": f"https://www.amazon.com/s?k=Cognex+In-Sight+vision+sensor&tag={AMAZON_TAG}", "est_price": 2200.00},
                {"name": "Grainger", "url": "https://www.grainger.com/search?searchQuery=Cognex+vision+sensor", "est_price": 2500.00},
            ],
        },
    ],

    "scale_load_cell": [
        {
            "name": "Rice Lake RL75016 S-Beam Load Cell",
            "part_no": "RL75016-500",
            "description": "500 lb capacity, S-beam, 3mV/V, NTEP certified",
            "suppliers": [
                {"name": "Amazon", "url": f"https://www.amazon.com/s?k=S-beam+load+cell+500+lb+NTEP&tag={AMAZON_TAG}", "est_price": 185.00},
                {"name": "McMaster-Carr", "url": "https://www.mcmaster.com/load-cells", "est_price": 220.00},
                {"name": "Grainger", "url": "https://www.grainger.com/search?searchQuery=S-beam+load+cell", "est_price": 245.00},
            ],
        },
    ],

    "light_curtain": [
        {
            "name": "Banner EZ-SCREEN LS Light Curtain",
            "part_no": "LS2TP30-450Q88",
            "description": "Type 4, 30mm resolution, 450mm protective height, PNP OSSD",
            "suppliers": [
                {"name": "AutomationDirect", "url": "https://www.automationdirect.com/adc/shopping/catalog/safety/safety_light_curtains", "est_price": 425.00},
                {"name": "Amazon", "url": f"https://www.amazon.com/s?k=Banner+EZ-SCREEN+light+curtain&tag={AMAZON_TAG}", "est_price": 480.00},
                {"name": "Grainger", "url": "https://www.grainger.com/search?searchQuery=Banner+safety+light+curtain", "est_price": 550.00},
            ],
        },
    ],

    "teach_pendant": [
        {
            "name": "Robot Teach Pendant E-Stop Button Assembly",
            "part_no": "TP-ESTOP-ASM",
            "description": "Replacement E-stop mushroom button + contact block for teach pendant",
            "suppliers": [
                {"name": "Amazon", "url": f"https://www.amazon.com/s?k=emergency+stop+push+button+mushroom+22mm+NC&tag={AMAZON_TAG}", "est_price": 12.00},
                {"name": "AutomationDirect", "url": "https://www.automationdirect.com/adc/shopping/catalog/pushbuttons_-z-_pilot_lights/22mm_push_buttons/e-stop", "est_price": 15.00},
                {"name": "McMaster-Carr", "url": "https://www.mcmaster.com/emergency-stop-buttons", "est_price": 18.00},
            ],
        },
    ],

    "connector": [
        {
            "name": "Phoenix Contact M12 4-Pin A-Coded Sensor Cable, 5m",
            "part_no": "SAC-4P-5,0-PUR/M12FS",
            "description": "M12 female straight to flying leads, 4-pin A-coded, 5m PUR jacket, IP67",
            "suppliers": [
                {"name": "AutomationDirect", "url": "https://www.automationdirect.com/adc/shopping/catalog/cables/m12_cordsets", "est_price": 28.00},
                {"name": "Digikey", "url": "https://www.digikey.com/en/products/result?keywords=SAC-4P-5%2C0-PUR%2FM12FS", "est_price": 32.00},
                {"name": "Amazon", "url": f"https://www.amazon.com/s?k=Phoenix+Contact+M12+4-pin+sensor+cable+5m&tag={AMAZON_TAG}", "est_price": 35.00},
            ],
        },
        {
            "name": "Turck M12 5-Pin Male Right-Angle Cable, 2m",
            "part_no": "RKC 5T-2/S90",
            "description": "M12 male right-angle to flying leads, 5-pin, 2m, oil-resistant PUR",
            "suppliers": [
                {"name": "AutomationDirect", "url": "https://www.automationdirect.com/adc/shopping/catalog/cables/m12_cordsets/m12_5-pin", "est_price": 24.00},
                {"name": "Digikey", "url": "https://www.digikey.com/en/products/result?keywords=Turck+RKC+5T-2", "est_price": 27.00},
                {"name": "Mouser", "url": "https://www.mouser.com/Search/Refine?Keyword=Turck+RKC+5T-2%2FS90", "est_price": 26.00},
            ],
        },
        {
            "name": "Allen-Bradley 889D 4-Pin DC Micro Cordset, 10m",
            "part_no": "889D-F4AC-10",
            "description": "M12 4-pin DC micro female straight cordset, 10m, PVC, IP67, A-B branded",
            "suppliers": [
                {"name": "AutomationDirect", "url": "https://www.automationdirect.com/adc/shopping/catalog/cables/m12_cordsets/m12_4-pin", "est_price": 38.00},
                {"name": "Amazon", "url": f"https://www.amazon.com/s?k=Allen-Bradley+889D-F4AC-10+cordset&tag={AMAZON_TAG}", "est_price": 52.00},
                {"name": "Grainger", "url": "https://www.grainger.com/search?searchQuery=889D-F4AC-10", "est_price": 64.00},
            ],
        },
        {
            "name": "Wago 221 Lever-Nut Splicing Connector Assortment",
            "part_no": "221-2401",
            "description": "2/3/5-conductor lever splice, 24-12 AWG, UL listed, panel-friendly. 60-pack",
            "suppliers": [
                {"name": "Amazon", "url": f"https://www.amazon.com/s?k=Wago+221+lever+nut+assortment+60+pack&tag={AMAZON_TAG}", "est_price": 28.00},
                {"name": "AutomationDirect", "url": "https://www.automationdirect.com/adc/shopping/catalog/wiring_solutions/wire_connectors", "est_price": 32.00},
                {"name": "Grainger", "url": "https://www.grainger.com/search?searchQuery=Wago+221-2401", "est_price": 36.00},
            ],
        },
        {
            "name": "Harting Han 10A Power Connector Kit",
            "part_no": "09200100301",
            "description": "10-pin industrial rectangular power connector, top entry, panel mount + hood",
            "suppliers": [
                {"name": "Digikey", "url": "https://www.digikey.com/en/products/result?keywords=Harting+09200100301", "est_price": 88.00},
                {"name": "Mouser", "url": "https://www.mouser.com/Search/Refine?Keyword=Harting+09200100301", "est_price": 92.00},
                {"name": "Grainger", "url": "https://www.grainger.com/search?searchQuery=Harting+Han+10A", "est_price": 110.00},
            ],
        },
        {
            "name": "RJ45 Cat6 Industrial Ethernet Patch Cord, 3m",
            "part_no": "STP-XAUE-CAT6-3M",
            "description": "Shielded Cat6 patch cord, M12-D to RJ45, industrial PoE-rated, 3m",
            "suppliers": [
                {"name": "AutomationDirect", "url": "https://www.automationdirect.com/adc/shopping/catalog/communications/industrial_ethernet_cables", "est_price": 42.00},
                {"name": "Amazon", "url": f"https://www.amazon.com/s?k=industrial+M12+RJ45+Cat6+patch+cord+3m&tag={AMAZON_TAG}", "est_price": 38.00},
                {"name": "Digikey", "url": "https://www.digikey.com/en/products/result?keywords=M12+D-coded+Cat6+patch+cord", "est_price": 45.00},
            ],
        },
    ],

    "tool": [
        {
            "name": "Fluke 87V Industrial True-RMS Multimeter",
            "part_no": "FLUKE-87V",
            "description": "True-RMS DMM with temperature, frequency, low-pass filter for VFD measurement. The field-tech standard.",
            "suppliers": [
                {"name": "AutomationDirect", "url": "https://www.automationdirect.com/adc/shopping/catalog/test_equipment/digital_multimeters", "est_price": 459.00},
                {"name": "Amazon", "url": f"https://www.amazon.com/s?k=Fluke+87V+industrial+multimeter&tag={AMAZON_TAG}", "est_price": 489.00},
                {"name": "Grainger", "url": "https://www.grainger.com/search?searchQuery=Fluke+87V", "est_price": 519.00},
            ],
        },
        {
            "name": "Fluke T6-1000 Electrical Tester (FieldSense)",
            "part_no": "FLUKE-T6-1000",
            "description": "Non-contact voltage + current measurement up to 1000V AC. No test leads in the bus bar.",
            "suppliers": [
                {"name": "Amazon", "url": f"https://www.amazon.com/s?k=Fluke+T6-1000+electrical+tester&tag={AMAZON_TAG}", "est_price": 379.00},
                {"name": "AutomationDirect", "url": "https://www.automationdirect.com/adc/shopping/catalog/test_equipment", "est_price": 395.00},
                {"name": "Grainger", "url": "https://www.grainger.com/search?searchQuery=Fluke+T6-1000", "est_price": 425.00},
            ],
        },
        {
            "name": "Klein Tools 11-in-1 Screwdriver / Nut Driver",
            "part_no": "32500",
            "description": "Cushion-grip multi-bit driver: Phillips, slotted, square, Torx, plus 1/4 and 5/16 nut drivers",
            "suppliers": [
                {"name": "Amazon", "url": f"https://www.amazon.com/s?k=Klein+Tools+32500+11-in-1&tag={AMAZON_TAG}", "est_price": 22.00},
                {"name": "Grainger", "url": "https://www.grainger.com/search?searchQuery=Klein+32500", "est_price": 28.00},
                {"name": "McMaster-Carr", "url": "https://www.mcmaster.com/products/screwdrivers/multi-bit-screwdrivers", "est_price": 30.00},
            ],
        },
        {
            "name": "Knipex Cobra Adjustable Pliers Set, 3-piece",
            "part_no": "00 20 09 V01",
            "description": "7\", 10\", 12\" Cobra water-pump pliers — German tool kit staple for plant and panel work",
            "suppliers": [
                {"name": "Amazon", "url": f"https://www.amazon.com/s?k=Knipex+Cobra+pliers+set+3+piece&tag={AMAZON_TAG}", "est_price": 89.00},
                {"name": "McMaster-Carr", "url": "https://www.mcmaster.com/products/pliers/water-pump-pliers", "est_price": 105.00},
                {"name": "Grainger", "url": "https://www.grainger.com/search?searchQuery=Knipex+Cobra+set", "est_price": 119.00},
            ],
        },
        {
            "name": "Wera 950/9 Hex-Plus Allen Key Set, Metric",
            "part_no": "950/9 Hex-Plus 1",
            "description": "9-piece L-key set, 1.5–10 mm, Hex-Plus geometry — won't cam out on stripped fasteners",
            "suppliers": [
                {"name": "Amazon", "url": f"https://www.amazon.com/s?k=Wera+950+9+Hex-Plus+metric&tag={AMAZON_TAG}", "est_price": 38.00},
                {"name": "McMaster-Carr", "url": "https://www.mcmaster.com/products/hex-keys", "est_price": 45.00},
                {"name": "Grainger", "url": "https://www.grainger.com/search?searchQuery=Wera+950+Hex-Plus", "est_price": 52.00},
            ],
        },
        {
            "name": "Klein 11055 Wire Stripper / Cutter, 10-18 AWG",
            "part_no": "11055",
            "description": "Solid + stranded wire stripper for control panel work. 10-18 AWG solid, 12-20 AWG stranded.",
            "suppliers": [
                {"name": "Amazon", "url": f"https://www.amazon.com/s?k=Klein+11055+wire+stripper&tag={AMAZON_TAG}", "est_price": 18.00},
                {"name": "AutomationDirect", "url": "https://www.automationdirect.com/adc/shopping/catalog/wiring_solutions/wire_strippers", "est_price": 22.00},
                {"name": "Grainger", "url": "https://www.grainger.com/search?searchQuery=Klein+11055", "est_price": 28.00},
            ],
        },
        {
            "name": "Phoenix Contact CRIMPFOX 6 Ratcheting Crimper",
            "part_no": "1212045",
            "description": "Ratcheting ferrule crimper, 0.25-6 mm² wire, color-coded sleeves. Required for European panel wiring.",
            "suppliers": [
                {"name": "Digikey", "url": "https://www.digikey.com/en/products/result?keywords=Phoenix+Contact+CRIMPFOX+6", "est_price": 88.00},
                {"name": "Amazon", "url": f"https://www.amazon.com/s?k=Phoenix+Contact+CRIMPFOX+6+1212045&tag={AMAZON_TAG}", "est_price": 95.00},
                {"name": "Mouser", "url": "https://www.mouser.com/Search/Refine?Keyword=CRIMPFOX+6", "est_price": 92.00},
            ],
        },
        {
            "name": "FLIR ONE Pro Thermal Imaging Camera (USB-C / Lightning)",
            "part_no": "FLIR-ONE-PRO",
            "description": "Phone-attached thermal camera, 19,200 px, MSX overlay. Hot bearings, panel hot spots, motor surface temp.",
            "suppliers": [
                {"name": "Amazon", "url": f"https://www.amazon.com/s?k=FLIR+ONE+Pro+thermal+camera&tag={AMAZON_TAG}", "est_price": 419.00},
                {"name": "Grainger", "url": "https://www.grainger.com/search?searchQuery=FLIR+ONE+Pro", "est_price": 449.00},
                {"name": "AutomationDirect", "url": "https://www.automationdirect.com/adc/shopping/catalog/test_equipment/thermal_imagers", "est_price": 469.00},
            ],
        },
    ],
}

# Mapping aliases — so multiple category names can resolve to the same parts list
CATEGORY_ALIASES: dict[str, str] = {
    "prox_sensor": "proximity_sensor",
    "prox": "proximity_sensor",
    "photo_sensor": "photoelectric_sensor",
    "photoelectric": "photoelectric_sensor",
    "vfd": "vfd_drive",
    "drive": "vfd_drive",
    "overload": "motor_overload_relay",
    "overload_relay": "motor_overload_relay",
    "safety": "safety_relay",
    "estop": "safety_relay",
    "e_stop": "safety_relay",
    "battery": "plc_battery",
    "plc_bat": "plc_battery",
    "pneumatic": "pneumatic_valve",
    "air_valve": "pneumatic_valve",
    "solenoid_valve": "pneumatic_valve",
    "tc": "thermocouple",
    "temp_sensor": "thermocouple",
    "servo": "servo_drive",
    "belt": "conveyor_belt",
    "motor": "conveyor_motor",
    "network": "network_module",
    "ethernet": "network_module",
    "profinet": "network_module",
    "devicenet": "network_module",
    "hydraulic": "hydraulic_pump",
    "scanner": "barcode_scanner",
    "barcode": "barcode_scanner",
    "film": "stretch_wrap_film",
    "wrap": "stretch_wrap_film",
    "printer": "label_printer",
    "label": "label_printer",
    "camera": "vision_camera",
    "vision": "vision_camera",
    "load_cell": "scale_load_cell",
    "scale": "scale_load_cell",
    "weight": "scale_load_cell",
    "connectors": "connector",
    "cable": "connector",
    "cables": "connector",
    "cordset": "connector",
    "cordsets": "connector",
    "m12": "connector",
    "m8": "connector",
    "rj45": "connector",
    "ethernet_cable": "connector",
    "tools": "tool",
    "multimeter": "tool",
    "dmm": "tool",
    "fluke": "tool",
    "klein": "tool",
    "knipex": "tool",
    "screwdriver": "tool",
    "pliers": "tool",
    "crimper": "tool",
    "wire_stripper": "tool",
    "thermal_camera": "tool",
    "flir": "tool",
    "hand_tool": "tool",
}


def get_parts_for_category(category: str) -> list[dict]:
    """Look up replacement parts for a fault category.

    Args:
        category: Fault parts_category string (e.g., 'proximity_sensor', 'vfd_drive')

    Returns:
        List of part dicts with name, part_no, description, suppliers.
        Empty list if no match found.
    """
    if not category:
        return []
    key = CATEGORY_ALIASES.get(category, category)
    return PARTS_CATALOG.get(key, [])


def get_all_categories() -> list[str]:
    """Return all available parts category names."""
    return sorted(PARTS_CATALOG.keys())
