#!/usr/bin/env python3
"""
SWAT Data Logger - CROSS-PLATFORM VERSION with File-Based Metadata
Reads attack metadata from JSON file for proper labeling
Works on Windows, Linux, Mac
"""

import sys
import time
import signal
import argparse
import json
from datetime import datetime
from pathlib import Path

sys.path.append(str(Path(__file__).parent.parent))

from config.swat_config import (
    MODBUS_CONFIG, LOGGING_CONFIG, HOLDING_REGISTERS, COILS, CSV_COLUMNS
)
from utils.modbus_utils import (
    ModbusClientOptimized as ModbusClient,
    DataValidator, DataScaler, CSVLogger,
    timestamp_to_str
)

import logging

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(LOGGING_CONFIG.get('log_path', 'logs/swat_system.log')),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)


class AttackMetadataFileReader:

    def __init__(self, filepath: str):
        self.filepath = Path(filepath)
        self.last_data = {
            'ATTACK_ID': 0,
            'ATTACK_NAME': 'Normal',
            'MITRE_ID': 'T0000 '
        }
        self.last_mtime = 0

    def get_current_attack_info(self) -> dict:
        """Safe metadata reader (Windows + Linux reliable)."""

        try:
            if not self.filepath.exists():
                return self.last_data

            mtime = self.filepath.stat().st_mtime

            # Only read file if it changed
            if mtime == self.last_mtime:
                return self.last_data

            self.last_mtime = mtime

            with open(self.filepath, 'r', encoding='utf-8') as f:
                text = f.read().strip()

            if not text:
                return self.last_data

            data = json.loads(text)

            new_data = {
                'ATTACK_ID': int(data.get('ATTACK_ID', 0)),
                'ATTACK_NAME': str(data.get('ATTACK_NAME', 'Normal')),
                'MITRE_ID': str(data.get('MITRE_ID', ''))
            }

            if new_data != self.last_data:
                logger.info(f"[LOGGER] Attack changed → {new_data['ATTACK_NAME']}")
                self.last_data = new_data

        except json.JSONDecodeError:
            # Ignore partial writes safely
            pass
        except Exception as e:
            logger.debug(f"Metadata read error: {e}")

        return self.last_data


class SWATDataLoggerOptimized:
    """
    Optimized data logger with bulk reads and file-based metadata.
    Cross-platform compatible.
    """
    
    def __init__(self, config: dict = None, metadata_file: str = None):
        self.config = config or MODBUS_CONFIG
        self.running = False
        
        self.modbus = ModbusClient(
            host=self.config['host'],
            port=self.config['port'],
            timeout=self.config['timeout'],
            retries=self.config['retries'],
            unit_id=self.config['unit_id']
        )
        
        self.csv_logger = CSVLogger(
            filepath=LOGGING_CONFIG['csv_path'],
            columns=CSV_COLUMNS,
            buffer_size=LOGGING_CONFIG['buffer_size']
        )
        
        self.validator = DataValidator(rules={})
        self.scaler = DataScaler()
        
        # File-based metadata reader
        if metadata_file:
            self.attack_metadata = AttackMetadataFileReader(metadata_file)
            logger.info(f"Using metadata file: {metadata_file}")
        else:
            self.attack_metadata = AttackMetadataFileReader()
        
        # Build address maps for bulk read efficiency
        self._build_address_maps()
        
        self.stats = {
            'total_polls': 0,
            'successful_polls': 0,
            'failed_polls': 0,
            'anomalies_detected': 0,
            'start_time': None,
            'bulk_read_time': 0,
        }
    
    def _build_address_maps(self):
        """Build address-to-variable mapping for O(1) lookup."""
        self.register_map = {}
        self.coil_map = {}
        
        for var_name, reg_info in HOLDING_REGISTERS.items():
            addr = reg_info['address']
            scale = reg_info.get('scale', 1)
            unit = reg_info.get('unit', '')
            self.register_map[addr] = (var_name, scale, unit)
        
        for var_name, coil_info in COILS.items():
            addr = coil_info['address']
            self.coil_map[addr] = var_name
        
        logger.info(f"Address maps: {len(self.register_map)} registers, {len(self.coil_map)} coils")
    
    def connect(self) -> bool:
        logger.info(f"Connecting to SWAT at {self.config['host']}:{self.config['port']}")
        return self.modbus.connect()
    
    def disconnect(self):
        self.modbus.disconnect()
        self.csv_logger.close()
    
    def read_all_registers_bulk(self) -> dict:
        """Read ALL registers in ONE call (bulk read)."""
        data = {}
        
        min_addr = 0
        count = 52   # Registers 0-51 (includes Chlorine_Residual at 51)
        
        start_time = time.time()
        result = self.modbus.read_holding_registers(address=min_addr, count=count)
        read_time = time.time() - start_time
        
        if result is None:
            logger.error(f"Failed to bulk read {count} registers")
            return data
        
        for addr, (var_name, scale, unit) in self.register_map.items():
            offset = addr - min_addr
            raw_value = result[offset]
            
            if scale == 1:
                physical_value = raw_value
            else:
                physical_value = self.scaler.scale_value(raw_value, scale)
            
            data[var_name] = physical_value
        
        self.stats['bulk_read_time'] += read_time
        logger.debug(f"Bulk read {count} registers in {read_time*1000:.1f}ms")
        
        return data
    
    def read_all_coils_bulk(self) -> dict:
        """Read ALL coils in ONE call (bulk read)."""
        data = {}
        
        min_addr = 0
        count = 28   # Coils 0-27 (includes High_Level_Alarm=25, High_Pressure_Alarm=26, System_Run=27)
        
        start_time = time.time()
        result = self.modbus.read_coils(address=min_addr, count=count)
        read_time = time.time() - start_time
        
        if result is None:
            logger.error(f"Failed to bulk read {count} coils")
            return data
        
        for addr, var_name in self.coil_map.items():
            offset = addr - min_addr
            data[var_name] = bool(result[offset])
        
        self.stats['bulk_read_time'] += read_time
        logger.debug(f"Bulk read {count} coils in {read_time*1000:.1f}ms")
        
        return data
    
    def poll_system(self) -> dict:
        """Poll entire SWAT system using BULK reads."""
        self.stats['total_polls'] += 1
        
        try:
            data = {'Timestamp': timestamp_to_str()}
            
            # BULK READ: All registers in 1 call
            register_data = self.read_all_registers_bulk()
            data.update(register_data)
            
            # BULK READ: All coils in 1 call
            coil_data = self.read_all_coils_bulk()
            data.update(coil_data)
            
            # READ ATTACK METADATA FROM FILE
            attack_info = self.attack_metadata.get_current_attack_info()
            data.update(attack_info)
            
            # Log attack status changes
            if attack_info['ATTACK_ID'] != 0:
                logger.debug(f"Attack active: {attack_info['ATTACK_NAME']} (ID: {attack_info['ATTACK_ID']})")
                
            if self.stats['total_polls'] % 50 == 0:
                logger.info(f"Metadata read → {attack_info}")
            
            self.stats['successful_polls'] += 1
            return data
            
        except Exception as e:
            logger.error(f"Error polling system: {e}", exc_info=True)
            self.stats['failed_polls'] += 1
            return None
    
    def log_data(self, data: dict):
        if data:
            self.csv_logger.log_row(data)
    
    def run(self, duration: float = None, poll_interval: float = None):
        if not self.connect():
            logger.error("Failed to connect")
            return
        
        self.running = True
        self.stats['start_time'] = datetime.now()
        poll_interval = poll_interval or LOGGING_CONFIG['poll_interval']
        
        logger.info(f"Starting OPTIMIZED logging (interval: {poll_interval}s, metadata file enabled)")
        if duration:
            logger.info(f"Duration: {duration}s")
        
        start_time = time.time()
        
        try:
            while self.running:
                if duration and (time.time() - start_time) >= duration:
                    logger.info("Duration reached")
                    break
                
                poll_start = time.time()
                data = self.poll_system()
                
                if data:
                    self.log_data(data)
                    
                    if self.stats['total_polls'] % 100 == 0:
                        self.print_status()
                
                elapsed = time.time() - poll_start
                sleep_time = max(0, poll_interval - elapsed)
                time.sleep(sleep_time)
                
        except KeyboardInterrupt:
            logger.info("Interrupted by user")
        except Exception as e:
            logger.error(f"Error in main loop: {e}", exc_info=True)
        finally:
            self.stop()
    
    def stop(self):
        logger.info("Stopping logger")
        self.running = False
        self.print_final_statistics()
        self.disconnect()
    
    def print_status(self):
        success_rate = 0
        if self.stats['total_polls'] > 0:
            success_rate = (self.stats['successful_polls'] / self.stats['total_polls']) * 100
        
        logger.info(f"Polls={self.stats['total_polls']}, Success={success_rate:.1f}%")
    
    def print_final_statistics(self):
        if self.stats['start_time'] is None:
            return
            
        runtime = (datetime.now() - self.stats['start_time']).total_seconds()
        avg_poll_rate = self.stats['total_polls'] / runtime if runtime > 0 else 0
        
        logger.info("=" * 70)
        logger.info("FINAL STATISTICS (OPTIMIZED BULK READING)")
        logger.info("=" * 70)
        logger.info(f"Runtime: {runtime:.1f}s")
        logger.info(f"Total Polls: {self.stats['total_polls']}")
        logger.info(f"Successful: {self.stats['successful_polls']}")
        logger.info(f"Failed: {self.stats['failed_polls']}")
        
        if self.stats['total_polls'] > 0:
            success_pct = (self.stats['successful_polls']/self.stats['total_polls']*100)
            logger.info(f"Success Rate: {success_pct:.2f}%")
        
        logger.info(f"Average Poll Rate: {avg_poll_rate:.2f} Hz")
        logger.info(f"CSV Rows Written: {self.csv_logger.total_rows}")
        logger.info("=" * 70)


def main():
    parser = argparse.ArgumentParser(description='SWAT Data Logger (Cross-Platform)')
    parser.add_argument('--host', default='192.168.5.194', help='PLC IP')
    parser.add_argument('--port', type=int, default=1502, help='Modbus port')
    parser.add_argument('--duration', type=float, default=None, help='Duration (seconds)')
    parser.add_argument('--interval', type=float, default=LOGGING_CONFIG['poll_interval'], help='Poll interval')
    parser.add_argument('--output', default=LOGGING_CONFIG['csv_path'], help='Output CSV')
    parser.add_argument('--metadata-file', default=None, help='Attack metadata JSON file')
    
    args = parser.parse_args()
    
    config = MODBUS_CONFIG.copy()
    config['host'] = args.host
    config['port'] = args.port
    
    LOGGING_CONFIG['csv_path'] = args.output
    
    logger_instance = SWATDataLoggerOptimized(config=config, metadata_file=args.metadata_file)
    
    def signal_handler(sig, frame):
        logger.info("Shutdown signal received")
        logger_instance.stop()
        sys.exit(0)
    
    signal.signal(signal.SIGINT, signal_handler)
    try:
        signal.signal(signal.SIGTERM, signal_handler)
    except AttributeError:
        # SIGTERM not available on Windows
        pass
    
    logger_instance.run(duration=args.duration, poll_interval=args.interval)


if __name__ == '__main__':
    main()