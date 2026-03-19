#!/usr/bin/env python3
"""
matlab_bridge/ws_server.py
Broadcasts live sensor + coil data to the HTML dashboard via WebSocket.

Usage:
    python matlab_bridge/ws_server.py --plc-host 192.168.5.195 --plc-port 1502
"""
import asyncio
import json
import sys
import argparse
import logging
from pathlib import Path

sys.path.append(str(Path(__file__).parent.parent))

import websockets
from config.swat_config import MODBUS_CONFIG, HOLDING_REGISTERS, COILS
from utils.modbus_utils import ModbusClientOptimized as ModbusClient

log = logging.getLogger('WSServer')
logging.basicConfig(level=logging.INFO,
                    format='%(asctime)s [%(levelname)s] %(message)s')

CONNECTED = set()
latest_payload: str = '{}'   # always holds the most recent sensor snapshot


async def broadcast_loop(plc_host: str, plc_port: int) -> None:
    """
    Read registers + coils from CODESYS in a background thread every 100 ms,
    store in latest_payload, and push to all connected WebSocket clients.

    Uses asyncio.to_thread so the blocking Modbus calls never touch the
    event loop — WebSocket accept/send always stays responsive.
    """
    global latest_payload

    reg_map  = {name: info['address'] for name, info in HOLDING_REGISTERS.items()}
    coil_map = {name: info['address'] for name, info in COILS.items()}
    max_reg  = max(reg_map.values())
    max_coil = max(coil_map.values())

    mb = ModbusClient(host=plc_host, port=plc_port, timeout=3, retries=2,
                      unit_id=MODBUS_CONFIG['unit_id'])

    # Connect once — retry loop handles reconnects
    connected = await asyncio.to_thread(mb.connect)
    if not connected:
        log.error(f'Cannot connect to CODESYS at {plc_host}:{plc_port}')
        return

    log.info(f'Connected to CODESYS {plc_host}:{plc_port}')
    log.info('Broadcasting on ws://0.0.0.0:8765')

    def _read_modbus():
        """Blocking Modbus read — runs in thread pool."""
        regs  = mb.read_holding_registers(address=0, count=max_reg  + 1)
        coils = mb.read_coils(address=0,             count=max_coil + 1)
        return regs, coils

    while True:
        try:
            # Run blocking IO in thread so event loop stays free
            regs, coils = await asyncio.to_thread(_read_modbus)

            if regs is not None and coils is not None:
                payload = {}
                for name, addr in reg_map.items():
                    payload[name] = int(regs[addr])
                for name, addr in coil_map.items():
                    payload[name] = bool(coils[addr])
                latest_payload = json.dumps(payload)

            # Push to all connected clients
            if CONNECTED:
                msg = latest_payload
                await asyncio.gather(
                    *[ws.send(msg) for ws in list(CONNECTED)],
                    return_exceptions=True
                )

        except Exception as e:
            log.warning(f'Broadcast error: {e}')
            # Try to reconnect
            try:
                await asyncio.to_thread(mb.connect)
            except Exception:
                pass

        await asyncio.sleep(0.1)


async def handler(websocket) -> None:
    CONNECTED.add(websocket)
    log.info(f'Client connected: {websocket.remote_address}  '
             f'(total: {len(CONNECTED)})')
    try:
        # Send current snapshot immediately on connect
        await websocket.send(latest_payload)
        await websocket.wait_closed()
    finally:
        CONNECTED.discard(websocket)
        log.info(f'Client disconnected (total: {len(CONNECTED)})')


async def main_async(plc_host: str, plc_port: int) -> None:
    async with websockets.serve(handler, '0.0.0.0', 8765):
        await broadcast_loop(plc_host, plc_port)


def main() -> None:
    parser = argparse.ArgumentParser(description='SWaT WebSocket broadcast server')
    parser.add_argument('--plc-host', default=MODBUS_CONFIG['host'],
                        help='CODESYS PLC IP')
    parser.add_argument('--plc-port', type=int, default=MODBUS_CONFIG['port'],
                        help='CODESYS Modbus port')
    args = parser.parse_args()
    asyncio.run(main_async(args.plc_host, args.plc_port))


if __name__ == '__main__':
    main()