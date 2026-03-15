# #!/usr/bin/env python3
# """
# Reconnaissance Attack
# MITRE ATT&CK ICS: T0802 - Automated Collection
# Scan Modbus network to discover devices and map registers/coils.
# """

# import sys
# import time
# import json
# import argparse
# from pathlib import Path

# sys.path.append(str(Path(__file__).parent.parent))

# from attacks.attack_base import BaseAttack, AttackOrchestrator, AttackLogger
# from config.swat_config import ATTACK_SCENARIOS, HOLDING_REGISTERS, COILS
# import logging

# logger = logging.getLogger(__name__)


# class ReconnaissanceAttack(BaseAttack):
#     """
#     Network reconnaissance via Modbus scanning.
#     """
    
#     def __init__(self, modbus_client, attack_config):
#         super().__init__(modbus_client, attack_config)
#         self.discovered_registers = {}
#         self.discovered_coils = {}
#         self.scan_range = self.parameters.get('scan_range', (0, 100))
#         self.delay = self.parameters.get('delay_between_scans', 0.1)
    
#     def scan_registers(self):
#         """
#         Scan for readable holding registers.
#         """
#         logger.info("Scanning holding registers...")
#         start, end = self.scan_range
        
#         for addr in range(start, end):
#             try:
#                 result = self.modbus.read_holding_registers(addr, count=1)
#                 if result is not None:
#                     value = result[0]
#                     self.discovered_registers[addr] = value
                    
#                     # Try to identify known registers
#                     var_name = self.identify_register(addr)
#                     self.log_action('register_discovered', {
#                         'address': addr,
#                         'value': value,
#                         'variable': var_name
#                     })
                    
#                     logger.info(f"  Register {addr}: {value} [{var_name}]")
                
#                 time.sleep(self.delay)
                
#                 if self.check_timeout():
#                     logger.info("Scan timeout reached")
#                     break
                    
#             except Exception as e:
#                 logger.debug(f"  Register {addr}: Not accessible ({e})")
        
#         logger.info(f"Discovered {len(self.discovered_registers)} readable registers")
    
#     def scan_coils(self):
#         """
#         Scan for readable coils.
#         """
#         logger.info("Scanning coils...")
#         start, end = self.scan_range
        
#         for addr in range(start, end):
#             try:
#                 result = self.modbus.read_coils(addr, count=1)
#                 if result is not None:
#                     value = result[0]
#                     self.discovered_coils[addr] = value
                    
#                     # Try to identify known coils
#                     var_name = self.identify_coil(addr)
#                     self.log_action('coil_discovered', {
#                         'address': addr,
#                         'value': value,
#                         'variable': var_name
#                     })
                    
#                     logger.info(f"  Coil {addr}: {value} [{var_name}]")
                
#                 time.sleep(self.delay)
                
#                 if self.check_timeout():
#                     logger.info("Scan timeout reached")
#                     break
                    
#             except Exception as e:
#                 logger.debug(f"  Coil {addr}: Not accessible ({e})")
        
#         logger.info(f"Discovered {len(self.discovered_coils)} readable coils")
    
#     def identify_register(self, address: int) -> str:
#         """
#         Try to identify register by address.
        
#         Args:
#             address: Register address
            
#         Returns:
#             Variable name or 'Unknown'
#         """
#         for var_name, info in HOLDING_REGISTERS.items():
#             if info['address'] == address:
#                 return var_name
#         return 'Unknown'
    
#     def identify_coil(self, address: int) -> str:
#         """
#         Try to identify coil by address.
        
#         Args:
#             address: Coil address
            
#         Returns:
#             Variable name or 'Unknown'
#         """
#         for var_name, info in COILS.items():
#             if info['address'] == address:
#                 return var_name
#         return 'Unknown'
    
#     def fingerprint_device(self):
#         """
#         Attempt to fingerprint the PLC/device.
#         """
#         logger.info("Fingerprinting device...")
        
#         # Read device identification (Modbus function 43/14)
#         # Note: Not all devices support this
#         try:
#             # Attempt to read device ID (vendor, product, version)
#             # This is a placeholder - actual implementation depends on device
#             self.log_action('fingerprint_attempted', {
#                 'method': 'modbus_device_identification'
#             })
#         except Exception as e:
#             logger.debug(f"Device fingerprinting failed: {e}")
    
#     def enumerate_function_codes(self):
#         """
#         Enumerate supported Modbus function codes.
#         """
#         logger.info("Enumerating supported function codes...")
        
#         supported_functions = []
#         test_functions = [1, 2, 3, 4, 5, 6, 15, 16, 23]  # Common Modbus functions
        
#         for func_code in test_functions:
#             try:
#                 # Test with minimal valid request
#                 if func_code in [1, 2]:  # Read coils/discrete inputs
#                     result = self.modbus.client.read_coils(0, 1)
#                 elif func_code in [3, 4]:  # Read registers
#                     result = self.modbus.client.read_holding_registers(0, 1)
#                 else:
#                     continue  # Skip write functions for safety
                
#                 if result and not result.isError():
#                     supported_functions.append(func_code)
#                     logger.info(f"  Function {func_code}: Supported")
                
#                 time.sleep(self.delay)
                
#             except Exception as e:
#                 logger.debug(f"  Function {func_code}: Not supported ({e})")
        
#         self.log_action('function_codes_enumerated', {
#             'supported': supported_functions
#         })
    
#     def export_findings(self, filepath: str):
#         """
#         Export reconnaissance findings to JSON.
        
#         Args:
#             filepath: Output file path
#         """
#         findings = {
#             'timestamp': time.strftime('%Y-%m-%d %H:%M:%S'),
#             'target': f"{self.modbus.host}:{self.modbus.port}",
#             'scan_range': self.scan_range,
#             'discovered_registers': [
#                 {
#                     'address': addr,
#                     'value': val,
#                     'variable': self.identify_register(addr)
#                 }
#                 for addr, val in self.discovered_registers.items()
#             ],
#             'discovered_coils': [
#                 {
#                     'address': addr,
#                     'value': val,
#                     'variable': self.identify_coil(addr)
#                 }
#                 for addr, val in self.discovered_coils.items()
#             ],
#             'execution_log': self.execution_log
#         }
        
#         with open(filepath, 'w') as f:
#             json.dump(findings, f, indent=2)
        
#         logger.info(f"Findings exported to {filepath}")
    
#     def execute(self):
#         """Execute reconnaissance attack."""
#         logger.info("Starting reconnaissance...")
        
#         # Fingerprint device
#         self.fingerprint_device()
        
#         # Enumerate function codes
#         if not self.check_timeout():
#             self.enumerate_function_codes()
        
#         # Scan registers
#         if self.parameters.get('scan_registers', True) and not self.check_timeout():
#             self.scan_registers()
        
#         # Scan coils
#         if self.parameters.get('scan_coils', True) and not self.check_timeout():
#             self.scan_coils()
        
#         # Generate summary
#         logger.info("=" * 60)
#         logger.info("RECONNAISSANCE SUMMARY")
#         logger.info("=" * 60)
#         logger.info(f"Registers discovered: {len(self.discovered_registers)}")
#         logger.info(f"Coils discovered: {len(self.discovered_coils)}")
#         logger.info(f"Total actions logged: {len(self.execution_log)}")
#         logger.info("=" * 60)


# def main():
#     """Main entry point for reconnaissance attack."""
#     parser = argparse.ArgumentParser(description='SWAT Reconnaissance Attack')
#     parser.add_argument('--host', required=True, help='Target PLC IP address')
#     parser.add_argument('--port', type=int, default=502, help='Modbus TCP port')
#     parser.add_argument('--start', type=int, default=0, help='Scan start address')
#     parser.add_argument('--end', type=int, default=100, help='Scan end address')
#     parser.add_argument('--delay', type=float, default=0.1, help='Delay between scans (seconds)')
#     parser.add_argument('--output', default='recon_findings.json', help='Output file for findings')
#     parser.add_argument('--duration', type=int, default=60, help='Maximum scan duration (seconds)')
    
#     args = parser.parse_args()
    
#     # Setup attack configuration
#     attack_config = ATTACK_SCENARIOS['reconnaissance'].copy()
#     attack_config['duration'] = args.duration
#     attack_config['parameters']['scan_range'] = (args.start, args.end)
#     attack_config['parameters']['delay_between_scans'] = args.delay
    
#     # Setup orchestrator
#     modbus_config = {
#         'host': args.host,
#         'port': args.port,
#         'timeout': 3,
#         'retries': 3,
#         'unit_id': 1
#     }
    
#     orchestrator = AttackOrchestrator(modbus_config)
    
#     if not orchestrator.connect():
#         logger.error("Failed to connect to target")
#         return 1
    
#     try:
#         # Execute attack
#         attack = ReconnaissanceAttack(orchestrator.modbus, attack_config)
#         attack.run()
        
#         # Export findings
#         attack.export_findings(args.output)
        
#     finally:
#         orchestrator.disconnect()
    
#     return 0


# if __name__ == '__main__':
#     sys.exit(main())

#!/usr/bin/env python3
"""
Reconnaissance Attack
MITRE ATT&CK ICS: T0802 - Automated Collection
Scan Modbus network to discover devices and map registers/coils.
"""

import sys
import time
import json
import argparse
from pathlib import Path

sys.path.append(str(Path(__file__).parent.parent))

from attacks.attack_base import BaseAttack, AttackOrchestrator, AttackLogger
from config.swat_config import ATTACK_SCENARIOS, HOLDING_REGISTERS, COILS
import logging

logger = logging.getLogger(__name__)


class ReconnaissanceAttack(BaseAttack):
    """
    Network reconnaissance via Modbus scanning.
    """
    
    def __init__(self, modbus_client, attack_config):
        super().__init__(modbus_client, attack_config)
        self.discovered_registers = {}
        self.discovered_coils = {}
        self.scan_range = self.parameters.get('scan_range', (0, 100))
        self.delay = self.parameters.get('delay_between_scans', 0.1)
    
    def scan_registers(self):
        """
        Scan for readable holding registers.
        """
        logger.info("Scanning holding registers...")
        start, end = self.scan_range
        
        for addr in range(start, end):
            try:
                result = self.modbus.read_holding_registers(addr, count=1)
                if result is not None:
                    value = result[0]
                    self.discovered_registers[addr] = value
                    
                    # Try to identify known registers
                    var_name = self.identify_register(addr)
                    self.log_action('register_discovered', {
                        'address': addr,
                        'value': value,
                        'variable': var_name
                    })
                    
                    logger.info(f"  Register {addr}: {value} [{var_name}]")
                
                time.sleep(self.delay)
                
                if self.check_timeout():
                    logger.info("Scan timeout reached")
                    break
                    
            except Exception as e:
                logger.debug(f"  Register {addr}: Not accessible ({e})")
        
        logger.info(f"Discovered {len(self.discovered_registers)} readable registers")
    
    def scan_coils(self):
        """
        Scan for readable coils.
        """
        logger.info("Scanning coils...")
        start, end = self.scan_range
        
        for addr in range(start, end):
            try:
                result = self.modbus.read_coils(addr, count=1)
                if result is not None:
                    value = result[0]
                    self.discovered_coils[addr] = value
                    
                    # Try to identify known coils
                    var_name = self.identify_coil(addr)
                    self.log_action('coil_discovered', {
                        'address': addr,
                        'value': value,
                        'variable': var_name
                    })
                    
                    logger.info(f"  Coil {addr}: {value} [{var_name}]")
                
                time.sleep(self.delay)
                
                if self.check_timeout():
                    logger.info("Scan timeout reached")
                    break
                    
            except Exception as e:
                logger.debug(f"  Coil {addr}: Not accessible ({e})")
        
        logger.info(f"Discovered {len(self.discovered_coils)} readable coils")
    
    def identify_register(self, address: int) -> str:
        """
        Try to identify register by address.
        
        Args:
            address: Register address
            
        Returns:
            Variable name or 'Unknown'
        """
        for var_name, info in HOLDING_REGISTERS.items():
            if info['address'] == address:
                return var_name
        return 'Unknown'
    
    def identify_coil(self, address: int) -> str:
        """
        Try to identify coil by address.
        
        Args:
            address: Coil address
            
        Returns:
            Variable name or 'Unknown'
        """
        for var_name, info in COILS.items():
            if info['address'] == address:
                return var_name
        return 'Unknown'
    
    def fingerprint_device(self):
        """
        Attempt to fingerprint the PLC/device.
        """
        logger.info("Fingerprinting device...")
        
        # Read device identification (Modbus function 43/14)
        # Note: Not all devices support this
        try:
            # Attempt to read device ID (vendor, product, version)
            # This is a placeholder - actual implementation depends on device
            self.log_action('fingerprint_attempted', {
                'method': 'modbus_device_identification'
            })
        except Exception as e:
            logger.debug(f"Device fingerprinting failed: {e}")
    
    def enumerate_function_codes(self):
        """
        Enumerate supported Modbus function codes.
        """
        logger.info("Enumerating supported function codes...")
        
        supported_functions = []
        test_functions = [1, 2, 3, 4, 5, 6, 15, 16, 23]  # Common Modbus functions
        
        for func_code in test_functions:
            try:
                # Test with minimal valid request
                if func_code in [1, 2]:  # Read coils/discrete inputs
                    result = self.modbus.client.read_coils(0, 1)
                elif func_code in [3, 4]:  # Read registers
                    result = self.modbus.client.read_holding_registers(0, 1)
                else:
                    continue  # Skip write functions for safety
                
                if result and not result.isError():
                    supported_functions.append(func_code)
                    logger.info(f"  Function {func_code}: Supported")
                
                time.sleep(self.delay)
                
            except Exception as e:
                logger.debug(f"  Function {func_code}: Not supported ({e})")
        
        self.log_action('function_codes_enumerated', {
            'supported': supported_functions
        })
    
    def export_findings(self, filepath: str):
        """
        Export reconnaissance findings to JSON.
        
        Args:
            filepath: Output file path
        """
        findings = {
            'timestamp': time.strftime('%Y-%m-%d %H:%M:%S'),
            'target': f"{self.modbus.host}:{self.modbus.port}",
            'scan_range': self.scan_range,
            'discovered_registers': [
                {
                    'address': addr,
                    'value': val,
                    'variable': self.identify_register(addr)
                }
                for addr, val in self.discovered_registers.items()
            ],
            'discovered_coils': [
                {
                    'address': addr,
                    'value': val,
                    'variable': self.identify_coil(addr)
                }
                for addr, val in self.discovered_coils.items()
            ],
            'execution_log': self.execution_log
        }
        
        with open(filepath, 'w') as f:
            json.dump(findings, f, indent=2)
        
        logger.info(f"Findings exported to {filepath}")
    
    def execute(self):
        """Execute reconnaissance attack."""
        logger.info("Starting reconnaissance...")
        
        # Fingerprint device
        self.fingerprint_device()
        
        # Enumerate function codes
        if not self.check_timeout():
            self.enumerate_function_codes()
        
        # Scan registers
        if self.parameters.get('scan_registers', True) and not self.check_timeout():
            self.scan_registers()
        
        # Scan coils
        if self.parameters.get('scan_coils', True) and not self.check_timeout():
            self.scan_coils()
        
        # Generate summary
        logger.info("=" * 60)
        logger.info("RECONNAISSANCE SUMMARY")
        logger.info("=" * 60)
        logger.info(f"Registers discovered: {len(self.discovered_registers)}")
        logger.info(f"Coils discovered: {len(self.discovered_coils)}")
        logger.info(f"Total actions logged: {len(self.execution_log)}")
        logger.info("=" * 60)


def main():
    """Main entry point for reconnaissance attack."""
    parser = argparse.ArgumentParser(description='SWAT Reconnaissance Attack')
    parser.add_argument('--host', required=True, help='Target PLC IP address')
    parser.add_argument('--port', type=int, default=502, help='Modbus TCP port')
    parser.add_argument('--start', type=int, default=0, help='Scan start address')
    parser.add_argument('--end', type=int, default=100, help='Scan end address')
    parser.add_argument('--delay', type=float, default=0.1, help='Delay between scans (seconds)')
    parser.add_argument('--output', default='recon_findings.json', help='Output file for findings')
    parser.add_argument('--duration', type=int, default=60, help='Maximum scan duration (seconds)')
    
    args = parser.parse_args()
    
    # Setup attack configuration
    attack_config = ATTACK_SCENARIOS['reconnaissance'].copy()
    attack_config['duration'] = args.duration
    attack_config['parameters']['scan_range'] = (args.start, args.end)
    attack_config['parameters']['delay_between_scans'] = args.delay
    
    # Setup orchestrator
    modbus_config = {
        'host': args.host,
        'port': args.port,
        'timeout': 3,
        'retries': 3,
        'unit_id': 1
    }
    
    orchestrator = AttackOrchestrator(modbus_config)
    
    if not orchestrator.connect():
        logger.error("Failed to connect to target")
        return 1
    
    try:
        # Execute attack
        attack = ReconnaissanceAttack(orchestrator.modbus, attack_config)
        attack.run()
        
        # Export findings
        attack.export_findings(args.output)
        
    finally:
        orchestrator.disconnect()
    
    return 0


if __name__ == '__main__':
    sys.exit(main())