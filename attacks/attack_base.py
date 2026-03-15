# #!/usr/bin/env python3
# """
# SWAT Attack Framework Base
# Base classes and common functionality for attack implementations.
# """

# import sys
# import time
# import logging
# from abc import ABC, abstractmethod
# from datetime import datetime
# from pathlib import Path
# from typing import Dict, List, Tuple, Any

# sys.path.append(str(Path(__file__).parent.parent))

# from config.swat_config import MODBUS_CONFIG, ATTACK_SCENARIOS, MITRE_ATTACK_MAPPING
# from utils.modbus_utils import ModbusClient, AttackMetadata, timestamp_to_str

# logging.basicConfig(
#     level=logging.INFO,
#     format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
# )
# logger = logging.getLogger(__name__)


# class BaseAttack(ABC):
#     """
#     Abstract base class for all attack implementations.
#     """
    
#     def __init__(self, modbus_client: ModbusClient, attack_config: dict):
#         """
#         Initialize attack.
        
#         Args:
#             modbus_client: Connected Modbus client
#             attack_config: Attack configuration dictionary
#         """
#         self.modbus = modbus_client
#         self.config = attack_config
#         self.attack_id = attack_config.get('id', 0)
#         self.attack_name = attack_config.get('name', 'Unknown')
#         self.mitre_id = attack_config.get('mitre_id', 'Unknown')
#         self.duration = attack_config.get('duration', 60)
#         self.parameters = attack_config.get('parameters', {})
        
#         self.running = False
#         self.start_time = None
#         self.execution_log = []
    
#     @abstractmethod
#     def execute(self):
#         """
#         Execute the attack.
#         Must be implemented by subclasses.
#         """
#         pass
    
#     def pre_attack(self):
#         """
#         Pre-attack setup.
#         Can be overridden by subclasses.
#         """
#         logger.info(f"Starting attack: {self.attack_name}")
#         logger.info(f"MITRE ID: {self.mitre_id}")
#         logger.info(f"Duration: {self.duration}s")
#         self.start_time = time.time()
#         self.running = True
    
#     def post_attack(self):
#         """
#         Post-attack cleanup.
#         Can be overridden by subclasses.
#         """
#         elapsed = time.time() - self.start_time
#         logger.info(f"Attack completed: {self.attack_name}")
#         logger.info(f"Actual duration: {elapsed:.1f}s")
#         self.running = False
    
#     def log_action(self, action: str, details: Dict = None):
#         """
#         Log attack action.
        
#         Args:
#             action: Action description
#             details: Additional details
#         """
#         log_entry = {
#             'timestamp': timestamp_to_str(),
#             'action': action,
#             'details': details or {}
#         }
#         self.execution_log.append(log_entry)
#         logger.debug(f"Action: {action}")
    
#     def check_timeout(self) -> bool:
#         """
#         Check if attack duration exceeded.
        
#         Returns:
#             True if timeout reached
#         """
#         if self.start_time:
#             elapsed = time.time() - self.start_time
#             return elapsed >= self.duration
#         return False
    
#     def read_register(self, address: int) -> int:
#         """
#         Read single holding register.
        
#         Args:
#             address: Register address
            
#         Returns:
#             Register value or None
#         """
#         result = self.modbus.read_holding_registers(address, count=1)
#         if result:
#             return result[0]
#         return None
    
#     def write_register(self, address: int, value: int) -> bool:
#         """
#         Write single holding register.
        
#         Args:
#             address: Register address
#             value: Value to write
            
#         Returns:
#             True if successful
#         """
#         return self.modbus.write_register(address, value)
    
#     def read_coil(self, address: int) -> bool:
#         """
#         Read single coil.
        
#         Args:
#             address: Coil address
            
#         Returns:
#             Boolean value or None
#         """
#         result = self.modbus.read_coils(address, count=1)
#         if result:
#             return result[0]
#         return None
    
#     def write_coil(self, address: int, value: bool) -> bool:
#         """
#         Write single coil.
        
#         Args:
#             address: Coil address
#             value: Boolean value
            
#         Returns:
#             True if successful
#         """
#         return self.modbus.write_coil(address, value)
    
#     def run(self):
#         """
#         Main attack execution wrapper.
#         """
#         try:
#             self.pre_attack()
#             self.execute()
#             self.post_attack()
#         except KeyboardInterrupt:
#             logger.warning("Attack interrupted by user")
#             self.running = False
#         except Exception as e:
#             logger.error(f"Attack error: {e}")
#             self.running = False
    
#     def get_execution_log(self) -> List[Dict]:
#         """Get execution log."""
#         return self.execution_log


# class AttackOrchestrator:
#     """
#     Orchestrate and manage attack execution.
#     """
    
#     def __init__(self, modbus_config: dict = None):
#         """
#         Initialize orchestrator.
        
#         Args:
#             modbus_config: Modbus configuration
#         """
#         self.config = modbus_config or MODBUS_CONFIG
#         self.modbus = ModbusClient(
#             host=self.config['host'],
#             port=self.config['port'],
#             timeout=self.config['timeout'],
#             retries=self.config['retries'],
#             unit_id=self.config['unit_id']
#         )
#         self.metadata = AttackMetadata()
#         self.attack_history = []
    
#     def connect(self) -> bool:
#         """
#         Connect to target system.
        
#         Returns:
#             True if connected
#         """
#         logger.info(f"Connecting to target at {self.config['host']}:{self.config['port']}")
#         return self.modbus.connect()
    
#     def disconnect(self):
#         """Disconnect from target."""
#         self.modbus.disconnect()
    
#     def execute_attack(self, attack_class, attack_config: dict):
#         """
#         Execute a single attack.
        
#         Args:
#             attack_class: Attack class to instantiate
#             attack_config: Attack configuration
#         """
#         # Update attack metadata
#         self.metadata.start_attack(
#             attack_id=attack_config['id'],
#             attack_name=attack_config['name'],
#             mitre_id=attack_config['mitre_id']
#         )
        
#         # Create and execute attack
#         attack = attack_class(self.modbus, attack_config)
#         attack.run()
        
#         # Stop attack tracking
#         self.metadata.stop_attack()
        
#         # Save to history
#         self.attack_history.append({
#             'config': attack_config,
#             'execution_log': attack.get_execution_log()
#         })
    
#     def execute_sequence(self, sequence_config: dict):
#         """
#         Execute attack sequence.
        
#         Args:
#             sequence_config: Sequence configuration
#         """
#         logger.info(f"Executing attack sequence: {sequence_config['name']}")
        
#         for stage in sequence_config['stages']:
#             # Wait for delay
#             if stage['delay'] > 0:
#                 logger.info(f"Waiting {stage['delay']}s before next stage...")
#                 time.sleep(stage['delay'])
            
#             # Get attack config
#             attack_name = stage['attack']
#             if attack_name in ATTACK_SCENARIOS:
#                 attack_config = ATTACK_SCENARIOS[attack_name]
#                 # Execute attack (would need to map to appropriate class)
#                 logger.info(f"Executing: {attack_config['name']}")
#             else:
#                 logger.warning(f"Unknown attack: {attack_name}")
    
#     def get_attack_statistics(self) -> Dict:
#         """Get attack execution statistics."""
#         return self.metadata.get_attack_statistics()


# class AttackLogger:
#     """
#     Specialized logger for attack execution.
#     """
    
#     def __init__(self, filepath: str):
#         """
#         Initialize attack logger.
        
#         Args:
#             filepath: Log file path
#         """
#         self.filepath = filepath
#         self.handler = logging.FileHandler(filepath)
#         self.handler.setFormatter(
#             logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
#         )
#         self.logger = logging.getLogger('attack_logger')
#         self.logger.addHandler(self.handler)
#         self.logger.setLevel(logging.INFO)
    
#     def log_attack_start(self, attack_name: str, mitre_id: str):
#         """Log attack start."""
#         self.logger.info(f"ATTACK START: {attack_name} (MITRE: {mitre_id})")
    
#     def log_attack_end(self, attack_name: str, duration: float):
#         """Log attack end."""
#         self.logger.info(f"ATTACK END: {attack_name} (Duration: {duration:.1f}s)")
    
#     def log_action(self, action: str, target: str, value: Any):
#         """Log attack action."""
#         self.logger.info(f"ACTION: {action} | Target: {target} | Value: {value}")
    
#     def close(self):
#         """Close logger."""
#         self.handler.close()


# class StateRecorder:
#     """
#     Record system state before and after attacks.
#     """
    
#     def __init__(self, modbus_client: ModbusClient):
#         """
#         Initialize state recorder.
        
#         Args:
#             modbus_client: Connected Modbus client
#         """
#         self.modbus = modbus_client
#         self.pre_attack_state = {}
#         self.post_attack_state = {}
    
#     def capture_state(self, label: str = 'state') -> Dict:
#         """
#         Capture current system state.
        
#         Args:
#             label: State label
            
#         Returns:
#             Dictionary of register/coil values
#         """
#         state = {
#             'timestamp': timestamp_to_str(),
#             'label': label,
#             'registers': {},
#             'coils': {}
#         }
        
#         # Read key registers (sample - expand as needed)
#         key_registers = [1, 8, 12, 21]  # LIT_101, LIT_301, LIT_401, PIT_501
#         for addr in key_registers:
#             result = self.modbus.read_holding_registers(addr, count=1)
#             if result:
#                 state['registers'][addr] = result[0]
        
#         # Read key coils
#         key_coils = [1, 14, 21]  # P_101, P_301, P_501
#         for addr in key_coils:
#             result = self.modbus.read_coils(addr, count=1)
#             if result:
#                 state['coils'][addr] = result[0]
        
#         return state
    
#     def record_pre_attack(self):
#         """Record state before attack."""
#         self.pre_attack_state = self.capture_state('pre_attack')
#         logger.info("Pre-attack state captured")
    
#     def record_post_attack(self):
#         """Record state after attack."""
#         self.post_attack_state = self.capture_state('post_attack')
#         logger.info("Post-attack state captured")
    
#     def compare_states(self) -> Dict:
#         """
#         Compare pre and post attack states.
        
#         Returns:
#             Dictionary of differences
#         """
#         differences = {
#             'registers': {},
#             'coils': {}
#         }
        
#         # Compare registers
#         for addr, pre_val in self.pre_attack_state.get('registers', {}).items():
#             post_val = self.post_attack_state.get('registers', {}).get(addr)
#             if post_val is not None and pre_val != post_val:
#                 differences['registers'][addr] = {
#                     'before': pre_val,
#                     'after': post_val,
#                     'delta': post_val - pre_val
#                 }
        
#         # Compare coils
#         for addr, pre_val in self.pre_attack_state.get('coils', {}).items():
#             post_val = self.post_attack_state.get('coils', {}).get(addr)
#             if post_val is not None and pre_val != post_val:
#                 differences['coils'][addr] = {
#                     'before': pre_val,
#                     'after': post_val
#                 }
        
#         return differences

#!/usr/bin/env python3
"""
SWAT Attack Framework Base
Base classes and common functionality for attack implementations.
"""

import sys
import time
import logging
from abc import ABC, abstractmethod
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Tuple, Any

sys.path.append(str(Path(__file__).parent.parent))

from config.swat_config import MODBUS_CONFIG, ATTACK_SCENARIOS
from utils.modbus_utils import ModbusClient, AttackMetadata, timestamp_to_str

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class BaseAttack(ABC):
    """
    Abstract base class for all attack implementations.
    """
    
    def __init__(self, modbus_client: ModbusClient, attack_config: dict):
        """
        Initialize attack.
        
        Args:
            modbus_client: Connected Modbus client
            attack_config: Attack configuration dictionary
        """
        self.modbus = modbus_client
        self.config = attack_config
        self.attack_id = attack_config.get('id', 0)
        self.attack_name = attack_config.get('name', 'Unknown')
        self.mitre_id = attack_config.get('mitre_id', 'Unknown')
        self.duration = attack_config.get('duration', 60)
        self.parameters = attack_config.get('parameters', {})
        
        self.running = False
        self.start_time = None
        self.execution_log = []
    
    @abstractmethod
    def execute(self):
        """
        Execute the attack.
        Must be implemented by subclasses.
        """
        pass
    
    def pre_attack(self):
        """
        Pre-attack setup.
        Can be overridden by subclasses.
        """
        logger.info(f"Starting attack: {self.attack_name}")
        logger.info(f"MITRE ID: {self.mitre_id}")
        logger.info(f"Duration: {self.duration}s")
        self.start_time = time.time()
        self.running = True
    
    def post_attack(self):
        """
        Post-attack cleanup.
        Can be overridden by subclasses.
        """
        elapsed = time.time() - self.start_time
        logger.info(f"Attack completed: {self.attack_name}")
        logger.info(f"Actual duration: {elapsed:.1f}s")
        self.running = False
    
    def log_action(self, action: str, details: Dict = None):
        """
        Log attack action.
        
        Args:
            action: Action description
            details: Additional details
        """
        log_entry = {
            'timestamp': timestamp_to_str(),
            'action': action,
            'details': details or {}
        }
        self.execution_log.append(log_entry)
        logger.debug(f"Action: {action}")
    
    def check_timeout(self) -> bool:
        """
        Check if attack duration exceeded.
        
        Returns:
            True if timeout reached
        """
        if self.start_time:
            elapsed = time.time() - self.start_time
            return elapsed >= self.duration
        return False
    
    def read_register(self, address: int) -> int:
        """
        Read single holding register.
        
        Args:
            address: Register address
            
        Returns:
            Register value or None
        """
        result = self.modbus.read_holding_registers(address, count=1)
        if result:
            return result[0]
        return None
    
    def write_register(self, address: int, value: int) -> bool:
        """
        Write single holding register.
        
        Args:
            address: Register address
            value: Value to write
            
        Returns:
            True if successful
        """
        return self.modbus.write_register(address, value)
    
    def read_coil(self, address: int) -> bool:
        """
        Read single coil.
        
        Args:
            address: Coil address
            
        Returns:
            Boolean value or None
        """
        result = self.modbus.read_coils(address, count=1)
        if result:
            return result[0]
        return None
    
    def write_coil(self, address: int, value: bool) -> bool:
        """
        Write single coil.
        
        Args:
            address: Coil address
            value: Boolean value
            
        Returns:
            True if successful
        """
        return self.modbus.write_coil(address, value)
    
    def run(self):
        """
        Main attack execution wrapper.
        """
        try:
            self.pre_attack()
            self.execute()
            self.post_attack()
        except KeyboardInterrupt:
            logger.warning("Attack interrupted by user")
            self.running = False
        except Exception as e:
            logger.error(f"Attack error: {e}")
            self.running = False
    
    def get_execution_log(self) -> List[Dict]:
        """Get execution log."""
        return self.execution_log


class AttackOrchestrator:
    """
    Orchestrate and manage attack execution.
    """
    
    def __init__(self, modbus_config: dict = None):
        """
        Initialize orchestrator.
        
        Args:
            modbus_config: Modbus configuration
        """
        self.config = MODBUS_CONFIG
        self.modbus = ModbusClient(
            host=self.config['host'],
            port=self.config['port'],
            timeout=self.config['timeout'],
            retries=self.config['retries'],
            unit_id=self.config['unit_id']
        )
        self.metadata = AttackMetadata()
        self.attack_history = []
    
    def connect(self) -> bool:
        """
        Connect to target system.
        
        Returns:
            True if connected
        """
        logger.info(f"Connecting to target at {self.config['host']}:{self.config['port']}")
        return self.modbus.connect()
    
    def disconnect(self):
        """Disconnect from target."""
        self.modbus.disconnect()
    
    def execute_attack(self, attack_class, attack_config: dict):
        """
        Execute a single attack.
        
        Args:
            attack_class: Attack class to instantiate
            attack_config: Attack configuration
        """
        # Update attack metadata
        self.metadata.start_attack(
            attack_id=attack_config['id'],
            attack_name=attack_config['name'],
            mitre_id=attack_config['mitre_id']
        )
        
        # Create and execute attack
        attack = attack_class(self.modbus, attack_config)
        attack.run()
        
        # Stop attack tracking
        self.metadata.stop_attack()
        
        # Save to history
        self.attack_history.append({
            'config': attack_config,
            'execution_log': attack.get_execution_log()
        })
    
    def execute_sequence(self, sequence_config: dict):
        """
        Execute attack sequence.
        
        Args:
            sequence_config: Sequence configuration
        """
        logger.info(f"Executing attack sequence: {sequence_config['name']}")
        
        for stage in sequence_config['stages']:
            # Wait for delay
            if stage['delay'] > 0:
                logger.info(f"Waiting {stage['delay']}s before next stage...")
                time.sleep(stage['delay'])
            
            # Get attack config
            attack_name = stage['attack']
            if attack_name in ATTACK_SCENARIOS:
                attack_config = ATTACK_SCENARIOS[attack_name]
                # Execute attack (would need to map to appropriate class)
                logger.info(f"Executing: {attack_config['name']}")
            else:
                logger.warning(f"Unknown attack: {attack_name}")
    
    def get_attack_statistics(self) -> Dict:
        """Get attack execution statistics."""
        return self.metadata.get_attack_statistics()


class AttackLogger:
    """
    Specialized logger for attack execution.
    """
    
    def __init__(self, filepath: str):
        """
        Initialize attack logger.
        
        Args:
            filepath: Log file path
        """
        self.filepath = filepath
        self.handler = logging.FileHandler(filepath)
        self.handler.setFormatter(
            logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
        )
        self.logger = logging.getLogger('attack_logger')
        self.logger.addHandler(self.handler)
        self.logger.setLevel(logging.INFO)
    
    def log_attack_start(self, attack_name: str, mitre_id: str):
        """Log attack start."""
        self.logger.info(f"ATTACK START: {attack_name} (MITRE: {mitre_id})")
    
    def log_attack_end(self, attack_name: str, duration: float):
        """Log attack end."""
        self.logger.info(f"ATTACK END: {attack_name} (Duration: {duration:.1f}s)")
    
    def log_action(self, action: str, target: str, value: Any):
        """Log attack action."""
        self.logger.info(f"ACTION: {action} | Target: {target} | Value: {value}")
    
    def close(self):
        """Close logger."""
        self.handler.close()


class StateRecorder:
    """
    Record system state before and after attacks.
    """
    
    def __init__(self, modbus_client: ModbusClient):
        """
        Initialize state recorder.
        
        Args:
            modbus_client: Connected Modbus client
        """
        self.modbus = modbus_client
        self.pre_attack_state = {}
        self.post_attack_state = {}
    
    def capture_state(self, label: str = 'state') -> Dict:
        """
        Capture current system state.
        
        Args:
            label: State label
            
        Returns:
            Dictionary of register/coil values
        """
        state = {
            'timestamp': timestamp_to_str(),
            'label': label,
            'registers': {},
            'coils': {}
        }
        
        # Read key registers (sample - expand as needed)
        key_registers = [1, 8, 12, 21]  # LIT_101, LIT_301, LIT_401, PIT_501
        for addr in key_registers:
            result = self.modbus.read_holding_registers(addr, count=1)
            if result:
                state['registers'][addr] = result[0]
        
        # Read key coils
        key_coils = [1, 14, 21]  # P_101, P_301, P_501
        for addr in key_coils:
            result = self.modbus.read_coils(addr, count=1)
            if result:
                state['coils'][addr] = result[0]
        
        return state
    
    def record_pre_attack(self):
        """Record state before attack."""
        self.pre_attack_state = self.capture_state('pre_attack')
        logger.info("Pre-attack state captured")
    
    def record_post_attack(self):
        """Record state after attack."""
        self.post_attack_state = self.capture_state('post_attack')
        logger.info("Post-attack state captured")
    
    def compare_states(self) -> Dict:
        """
        Compare pre and post attack states.
        
        Returns:
            Dictionary of differences
        """
        differences = {
            'registers': {},
            'coils': {}
        }
        
        # Compare registers
        for addr, pre_val in self.pre_attack_state.get('registers', {}).items():
            post_val = self.post_attack_state.get('registers', {}).get(addr)
            if post_val is not None and pre_val != post_val:
                differences['registers'][addr] = {
                    'before': pre_val,
                    'after': post_val,
                    'delta': post_val - pre_val
                }
        
        # Compare coils
        for addr, pre_val in self.pre_attack_state.get('coils', {}).items():
            post_val = self.post_attack_state.get('coils', {}).get(addr)
            if post_val is not None and pre_val != post_val:
                differences['coils'][addr] = {
                    'before': pre_val,
                    'after': post_val
                }
        
        return differences
