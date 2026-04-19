import asyncio
import os
import re
import shutil
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fastapi import APIRouter, WebSocket, WebSocketDisconnect, status
from jose import JWTError, jwt

from system_stats import SystemStatsService
from user import SECRET_KEY, ALGORITHM, SESSION_COOKIE_NAME

try:
    import psutil
except ModuleNotFoundError:
    psutil = None

ws_router = APIRouter(tags=["websocket"])


def _authenticate_ws(websocket: WebSocket) -> str | None:
    token = websocket.cookies.get(SESSION_COOKIE_NAME)
    if not token:
        token = websocket.query_params.get("token")
    if not token:
        return None
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        return payload.get("username")
    except JWTError:
        return None


class NetworkStats:
    _prev: dict[str, tuple[int, int]] = {}
    _prev_time: float = 0.0

    @classmethod
    def _read_proc_net_dev(cls) -> dict[str, tuple[int, int]]:
        result: dict[str, tuple[int, int]] = {}
        try:
            with open("/proc/net/dev", "r", encoding="utf-8") as fh:
                for line in fh:
                    if ":" not in line:
                        continue
                    iface, rest = line.split(":", 1)
                    iface = iface.strip()
                    if iface == "lo":
                        continue
                    fields = rest.split()
                    result[iface] = (int(fields[0]), int(fields[8]))
        except (OSError, IndexError, ValueError):
            pass
        return result

    @classmethod
    def get_rates(cls) -> dict[str, Any]:
        now = time.monotonic()
        current = cls._read_proc_net_dev()

        total_rx = sum(rx for rx, _ in current.values())
        total_tx = sum(tx for _, tx in current.values())

        rx_rate = 0.0
        tx_rate = 0.0

        if cls._prev_time > 0:
            dt = now - cls._prev_time
            if dt > 0:
                prev_rx = sum(rx for rx, _ in cls._prev.values())
                prev_tx = sum(tx for _, tx in cls._prev.values())
                rx_rate = max(0.0, (total_rx - prev_rx) / dt)
                tx_rate = max(0.0, (total_tx - prev_tx) / dt)

        cls._prev = current
        cls._prev_time = now

        return {
            "download_bytes": total_rx,
            "upload_bytes": total_tx,
            "download_speed": round(rx_rate, 1),   # bytes/sec
            "upload_speed": round(tx_rate, 1),
        }


def _get_instance_pid(name: str) -> int:
    from service_controller import ServiceController
    validated = ServiceController.validate_name(name)
    svc = f"{ServiceController.service_name_prefix()}-{validated}.service"
    try:
        result = subprocess.run(
            ["systemctl", "show", svc, "--property=MainPID"],
            capture_output=True, text=True, timeout=5, check=False,
        )
        for line in result.stdout.strip().splitlines():
            if line.startswith("MainPID="):
                return int(line.split("=", 1)[1])
    except Exception:
        pass
    return 0


def _read_proc_net_dev_for_pid(pid: int) -> dict[str, tuple[int, int]]:
    result: dict[str, tuple[int, int]] = {}
    try:
        with open(f"/proc/{pid}/net/dev", "r", encoding="utf-8") as fh:
            for line in fh:
                if ":" not in line:
                    continue
                iface, rest = line.split(":", 1)
                iface = iface.strip()
                if iface == "lo":
                    continue
                fields = rest.split()
                result[iface] = (int(fields[0]), int(fields[8]))
    except (OSError, IndexError, ValueError):
        pass
    return result


#? { instance_name: (timestamp, rx_bytes, tx_bytes) }
_instance_net_prev: dict[str, tuple[float, int, int]] = {}

def _get_instance_network(name: str, pid: int) -> dict[str, Any]:
    now = time.monotonic()
    ifaces = _read_proc_net_dev_for_pid(pid)

    rx = sum(r for r, _ in ifaces.values())
    tx = sum(t for _, t in ifaces.values())

    rx_rate = 0.0
    tx_rate = 0.0

    prev = _instance_net_prev.get(name)
    if prev:
        dt = now - prev[0]
        if dt > 0:
            rx_rate = max(0.0, (rx - prev[1]) / dt)
            tx_rate = max(0.0, (tx - prev[2]) / dt)

    _instance_net_prev[name] = (now, rx, tx)

    return {
        "download_bytes": rx,
        "upload_bytes": tx,
        "download_speed": round(rx_rate, 1),
        "upload_speed": round(tx_rate, 1),
    }


@ws_router.websocket("/ws/system")
async def ws_system_stats(websocket: WebSocket):
    username = _authenticate_ws(websocket)
    if not username:
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return
    await websocket.accept()

    NetworkStats.get_rates()

    try:
        while True:
            stats = SystemStatsService.collect()
            network = NetworkStats.get_rates()

            payload = {
                "type": "system_stats",
                "cpu_usage_percent": stats.cpu_usage_percent,
                "memory": stats.memory.model_dump(),
                "disk": stats.disk.model_dump(),
                "network": network,
                "collected_at": stats.collected_at.isoformat(),
            }

            await websocket.send_json(payload)
            try:
                await asyncio.wait_for(websocket.receive_text(), timeout=2.0)
            except asyncio.TimeoutError:
                pass
    except WebSocketDisconnect:
        pass
    except Exception:
        try:
            await websocket.close()
        except Exception:
            pass


@ws_router.websocket("/ws/instance/{name}")
async def ws_instance_stats(websocket: WebSocket, name: str):
    username = _authenticate_ws(websocket)
    if not username:
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return
    await websocket.accept()

    try:
        while True:
            pid = await asyncio.to_thread(_get_instance_pid, name)

            if pid <= 0:
                payload: dict[str, Any] = {
                    "type": "instance_stats",
                    "name": name,
                    "running": False,
                    "cpu": 0,
                    "memory": 0,
                    "uptime_seconds": 0,
                    "network": {
                        "download_bytes": 0,
                        "upload_bytes": 0,
                        "download_speed": 0,
                        "upload_speed": 0,
                    },
                    "collected_at": datetime.now(timezone.utc).isoformat(),
                }
            else:
                cpu = 0.0
                mem = 0.0
                uptime = 0

                if psutil:
                    try:
                        proc = psutil.Process(pid)
                        cpu = proc.cpu_percent(interval=0.3)
                        mem = proc.memory_percent()
                        uptime = max(0, int(time.time() - proc.create_time()))
                    except (psutil.NoSuchProcess, psutil.AccessDenied):
                        pass

                network = await asyncio.to_thread(
                    _get_instance_network, name, pid,
                )

                payload = {
                    "type": "instance_stats",
                    "name": name,
                    "running": True,
                    "cpu": round(cpu, 1),
                    "memory": round(mem, 1),
                    "uptime_seconds": uptime,
                    "network": network,
                    "collected_at": datetime.now(timezone.utc).isoformat(),
                }

            await websocket.send_json(payload)

            try:
                await asyncio.wait_for(websocket.receive_text(), timeout=2.0)
            except asyncio.TimeoutError:
                pass
    except WebSocketDisconnect:
        pass
    except Exception:
        try:
            await websocket.close()
        except Exception:
            pass


@ws_router.websocket("/ws/instance/{name}/logs")
async def ws_instance_logs(websocket: WebSocket, name: str):
    username = _authenticate_ws(websocket)
    if not username:
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return
    await websocket.accept()

    from service_controller import ServiceController

    try:
        validated = ServiceController.validate_name(name)
    except Exception:
        await websocket.send_json({"type": "error", "message": "Invalid instance name"})
        await websocket.close()
        return

    unit_name = f"{ServiceController.service_name_prefix()}-{validated}.service"

    if not shutil.which("journalctl"):
        await websocket.send_json({"type": "error", "message": "journalctl not available"})
        await websocket.close()
        return

    cmd: list[str] = [
        "journalctl", "-u", unit_name,
        "-f", "-n", "50",
        "--no-pager", "-o", "short-iso",
    ]
    if ServiceController._needs_sudo() and shutil.which("sudo"):
        cmd = ["sudo", "-n", *cmd]

    process: asyncio.subprocess.Process | None = None

    try:
        process = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )

        async def _reader():
            assert process and process.stdout
            while True:
                line = await process.stdout.readline()
                if not line:
                    break
                decoded = line.decode("utf-8", errors="replace").strip()
                if not decoded:
                    continue
                is_dns = bool(
                    re.search(
                        r"dns|resolv|query|lookup|nameserver|valid",
                        decoded,
                        re.IGNORECASE,
                    )
                )
                await websocket.send_json({
                    "type": "log",
                    "line": decoded,
                    "is_dns": is_dns,
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                })

        reader_task = asyncio.create_task(_reader())

        try:
            while True:
                msg = await websocket.receive_text()
                if msg == "close":
                    break
        except WebSocketDisconnect:
            pass
        finally:
            reader_task.cancel()
            try:
                await reader_task
            except asyncio.CancelledError:
                pass
    except WebSocketDisconnect:
        pass
    except Exception:
        try:
            await websocket.close()
        except Exception:
            pass
    finally:
        if process:
            try:
                process.terminate()
                await asyncio.wait_for(process.wait(), timeout=3)
            except Exception:
                try:
                    process.kill()
                except Exception:
                    pass