import asyncio
import ipaddress
import random
import socket
import struct
import sys
import threading
import time
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import AliasChoices, BaseModel, ConfigDict, Field, field_validator

from user import get_current_username

resolver_scanner_router = APIRouter(
    prefix="/resolver-scanner",
    tags=["resolver-scanner"],
    dependencies=[Depends(get_current_username)],
)

class ResolverScanRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    resolvers: list[str] = Field(..., min_length=1, description="IP or ip:port entries to test")
    domain: str = Field(default="example.com", min_length=1, max_length=253)
    expected_ip: str | None = Field(
        default=None,
        validation_alias=AliasChoices("expected_ip", "expected-ip"),
        description="Strict mode: only save resolvers that return this IP",
    )
    ports: list[int] = Field(default=[53], description="Ports to probe per resolver")
    timeout: float = Field(default=3.0, ge=0.2, le=30.0)
    concurrency: int = Field(default=500, ge=1, le=5000)
    num_sockets: int = Field(default=10, ge=1, le=200)

    @field_validator("domain")
    @classmethod
    def _validate_domain(cls, v: str) -> str:
        v = v.strip().rstrip(".")
        if not v:
            raise ValueError("domain cannot be empty")
        if any(len(lbl) == 0 or len(lbl) > 63 for lbl in v.split(".")):
            raise ValueError("domain has invalid labels")
        return v

    @field_validator("expected_ip")
    @classmethod
    def _validate_expected_ip(cls, v: str | None) -> str | None:
        if v is None:
            return None
        try:
            return str(ipaddress.IPv4Address(v.strip()))
        except ValueError as exc:
            raise ValueError("expected_ip must be a valid IPv4 address") from exc

    @field_validator("ports")
    @classmethod
    def _validate_ports(cls, v: list[int]) -> list[int]:
        if not v:
            raise ValueError("ports cannot be empty")
        for p in v:
            if not 1 <= p <= 65535:
                raise ValueError(f"invalid port {p}")
        return v


class ResolverScanResponse(BaseModel):
    status: str
    mode: str
    domain: str
    scanned: int
    found_count: int
    invalid_count: int
    duration_seconds: float
    rate_per_second: float
    found_resolvers: list[str]
    invalid_inputs: list[str]


#!DNS packet helpers
def _build_dns_a_query(domain: str, txid: int) -> bytes:
    header = struct.pack(">HHHHHH", txid, 0x0100, 1, 0, 0, 0)
    qname = b""
    for label in domain.rstrip(".").split("."):
        enc = label.encode("ascii")
        qname += bytes([len(enc)]) + enc
    qname += b"\x00"
    return header + qname + struct.pack(">HH", 1, 1)  #? qtype=A, qclass=IN


def _skip_name(data: bytes, offset: int) -> int:
    """Skip a DNS name (handles pointers and labels). Returns new offset."""
    while offset < len(data):
        length = data[offset]
        if length >= 0xC0:  
            return offset + 2
        if length == 0:    
            return offset + 1
        offset += 1 + length
    return offset


def _is_valid_dns_response(data: bytes, txid: int, expected_ip: str | None) -> bool:
    if len(data) < 12:
        return False
    if struct.unpack(">H", data[0:2])[0] != txid:
        return False

    flags   = struct.unpack(">H", data[2:4])[0]
    qr      = (flags >> 15) & 1
    rcode   = flags & 0xF
    ancount = struct.unpack(">H", data[6:8])[0]
    if qr != 1 or rcode != 0 or ancount == 0:
        return False

    qdcount = struct.unpack(">H", data[4:6])[0]
    offset = 12
    for _ in range(qdcount):
        offset = _skip_name(data, offset)
        offset += 4  #? qtype + qclass

    expected_bytes = socket.inet_aton(expected_ip) if expected_ip else None
    for _ in range(ancount):
        if offset >= len(data):
            break
        offset = _skip_name(data, offset)
        if offset + 10 > len(data):
            break
        rtype, rclass, _, rdlength = struct.unpack(">HHIH", data[offset:offset + 10])
        offset += 10
        if offset + rdlength > len(data):
            break
        if rtype == 1 and rclass == 1 and rdlength == 4:
            if expected_bytes is None or data[offset:offset + 4] == expected_bytes:
                return True
        offset += rdlength

    return False


class UDPScanner:
    def __init__(self, num_sockets: int, timeout: float, expected_ip: str | None, domain: str):
        self.num_sockets = num_sockets
        self.timeout = timeout
        self.expected_ip = expected_ip
        self.domain = domain
        self._pending: dict[int, tuple[asyncio.Future, str, int]] = {}
        self._sockets: list[socket.socket] = []
        self._recv_threads: list[threading.Thread] = []
        self._running = False
        self._loop: asyncio.AbstractEventLoop | None = None

    @staticmethod
    def _make_socket() -> socket.socket:
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.settimeout(1.0)
        sock.bind(("0.0.0.0", 0))
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_SNDBUF, 1 << 20)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, 1 << 20)
        if sys.platform == "win32":
            try:
                sock.ioctl(socket.SIO_UDP_CONNRESET, False)
            except (OSError, AttributeError, ValueError):
                pass
        return sock

    async def start(self) -> None:
        self._loop = asyncio.get_running_loop()
        self._running = True
        for _ in range(self.num_sockets):
            sock = self._make_socket()
            self._sockets.append(sock)
            t = threading.Thread(target=self._recv_loop, args=(sock,), daemon=True)
            t.start()
            self._recv_threads.append(t)

    def _resolve_future(self, txid: int, result: bool) -> None:
        entry = self._pending.get(txid)
        if entry and not entry[0].done():
            entry[0].set_result(result)

    def _recv_loop(self, sock: socket.socket) -> None:
        while self._running:
            try:
                data, addr = sock.recvfrom(4096)
            except socket.timeout:
                continue
            except OSError:
                if not self._running:
                    return
                continue
            if len(data) < 12:
                continue
            txid = struct.unpack(">H", data[0:2])[0]
            entry = self._pending.get(txid)
            if entry is not None:
                _, expected_ip, expected_port = entry
                #? Verify the response came from the IP:port we actually probed
                if addr[0] != expected_ip or addr[1] != expected_port:
                    continue
                result = _is_valid_dns_response(data, txid, self.expected_ip)
                try:
                    self._loop.call_soon_threadsafe(self._resolve_future, txid, result)
                except RuntimeError:
                    return  

    async def probe(self, ip: str, port: int) -> bool:
        txid = random.randint(1, 65535)
        attempts = 0
        while txid in self._pending:
            txid = random.randint(1, 65535)
            attempts += 1
            if attempts > 500:
                return False

        fut = self._loop.create_future()
        self._pending[txid] = (fut, ip, port)

        pkt = _build_dns_a_query(self.domain, txid)
        try:
            self._sockets[txid % self.num_sockets].sendto(pkt, (ip, port))
        except OSError:
            self._pending.pop(txid, None)
            fut.cancel()
            return False

        try:
            return await asyncio.wait_for(fut, timeout=self.timeout)
        except (asyncio.TimeoutError, asyncio.CancelledError):
            return False
        finally:
            self._pending.pop(txid, None)

    def stop(self) -> None:
        self._running = False
        for sock in self._sockets:
            try:
                sock.close()
            except Exception:
                pass
        for t in self._recv_threads:
            t.join(timeout=3.0)


#!queue worker
async def _worker(queue: asyncio.Queue, scanner: UDPScanner,
                  found: list[str], stats: dict[str, Any]) -> None:
    while True:
        item = await queue.get()
        if item is None:
            queue.task_done()
            break
        ip, port = item
        try:
            ok = await scanner.probe(ip, port)
            stats["done"] += 1
            if ok:
                found.append(f"{ip}:{port}")
        except Exception:
            stats["done"] += 1
        queue.task_done()


#!input parsing
def _parse_resolver(raw: str, default_ports: list[int]) -> list[tuple[str, int]] | None:
    line = raw.strip()
    if not line or line.startswith("#"):
        return None

    if line.startswith("[") and "]" in line:
        line = line.split("]", 1)[1].strip()

    host = line
    explicit_port: int | None = None

    if ":" in line:
        host_part, port_part = line.rsplit(":", 1)
        if host_part and port_part.isdigit():
            host = host_part.strip()
            explicit_port = int(port_part)

    try:
        ip = str(ipaddress.IPv4Address(host))
    except ValueError:
        return None

    ports = [explicit_port] if explicit_port is not None else default_ports
    if any(not 1 <= p <= 65535 for p in ports):
        return None

    return [(ip, p) for p in ports]


#!core async scan
async def _run_scan(req: ResolverScanRequest) -> dict[str, Any]:
    seen: set[tuple[str, int]] = set()
    targets: list[tuple[str, int]] = []
    invalid_format_inputs: list[str] = []

    for raw in req.resolvers:
        parsed = _parse_resolver(raw, req.ports)
        if parsed is None:
            invalid_format_inputs.append(raw)
            continue
        for pair in parsed:
            if pair not in seen:
                seen.add(pair)
                targets.append(pair)

    if not targets:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No valid resolver entries found",
        )

    found: list[str] = []
    stats: dict[str, Any] = {"done": 0}
    total = len(targets)

    scanner = UDPScanner(
        num_sockets=req.num_sockets,
        timeout=req.timeout,
        expected_ip=req.expected_ip,
        domain=req.domain,
    )
    await scanner.start()

    queue: asyncio.Queue = asyncio.Queue(maxsize=req.concurrency * 4)
    worker_tasks = [
        asyncio.create_task(_worker(queue, scanner, found, stats))
        for _ in range(min(req.concurrency, total))
    ]

    start = time.time()

    for ip, port in targets:
        await queue.put((ip, port))

    #? poison pills
    for _ in worker_tasks:
        await queue.put(None)

    await queue.join()

    for w in worker_tasks:
        w.cancel()
    await asyncio.gather(*worker_tasks, return_exceptions=True)

    scanner.stop()

    elapsed = max(time.time() - start, 0.000_001)

    found_set = set(found)
    invalid_targets = [f"{ip}:{port}" for ip, port in targets if f"{ip}:{port}" not in found_set]
    invalid_inputs = invalid_format_inputs + invalid_targets

    return {
        "status":             "success",
        "mode":               f"strict (expect {req.expected_ip})" if req.expected_ip else "open",
        "domain":             req.domain,
        "scanned":            total,
        "found_count":        len(found),
        "invalid_count":      len(invalid_inputs),
        "duration_seconds":   round(elapsed, 3),
        "rate_per_second":    round(total / elapsed, 2),
        "found_resolvers":    found,
        "invalid_inputs":     invalid_inputs,
    }

@resolver_scanner_router.post("/scan", response_model=ResolverScanResponse)
async def scan_resolvers(req: ResolverScanRequest) -> dict[str, Any]:
    return await _run_scan(req)