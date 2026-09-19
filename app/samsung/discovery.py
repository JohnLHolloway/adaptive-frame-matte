"""SSDP discovery, plus explicit, rate-limited Samsung-port-only subnet discovery."""

import asyncio
import ipaddress
import socket
import time

import httpx


def validate_ip(value):
    address = ipaddress.ip_address(value)
    if (
        address.version != 4
        or not address.is_private
        or address.is_loopback
        or address.is_link_local
    ):
        raise ValueError("Enter a private LAN IPv4 address")
    if address.is_unspecified or address.is_multicast:
        raise ValueError("Enter a unicast TV address")
    return str(address)


async def device_info(ip):
    ip = validate_ip(ip)
    async with httpx.AsyncClient(timeout=3, trust_env=False, follow_redirects=False) as client:
        response = await client.get(f"http://{ip}:8001/api/v2/")
        response.raise_for_status()
        d = response.json().get("device", {})
    return {
        "ip": ip,
        "model": d.get("modelName", "Unknown"),
        "name": d.get("name", "Samsung TV"),
        "art_supported": str(d.get("FrameTVSupport", "")).lower() == "true",
    }


def ssdp():
    found = set()
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP) as sock:
        sock.settimeout(0.3)
        sock.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_TTL, 2)
        sock.sendto(
            b"M-SEARCH * HTTP/1.1\r\nHOST: 239.255.255.250:1900\r\n"
            b'MAN: "ssdp:discover"\r\nMX: 2\r\nST: ssdp:all\r\n\r\n',
            ("239.255.255.250", 1900),
        )
        until = time.monotonic() + 3
        while time.monotonic() < until:
            try:
                packet, source = sock.recvfrom(65535)
                if b"samsung" in packet.lower():
                    found.add(source[0])
            except TimeoutError:
                pass
    return found


async def discover(subnet=None):
    if subnet:
        network = ipaddress.ip_network(subnet, strict=False)
        if network.version != 4 or not network.is_private or network.prefixlen < 24:
            raise ValueError("Discovery is limited to a private /24 or smaller subnet")
        hosts = [str(ip) for ip in network.hosts()]
    else:
        hosts = await asyncio.to_thread(ssdp)
    sem = asyncio.Semaphore(8)

    async def check(ip):
        async with sem:
            try:
                _, writer = await asyncio.wait_for(asyncio.open_connection(ip, 8002), 0.5)
                writer.close()
                await writer.wait_closed()
                return await device_info(ip)
            except (OSError, TimeoutError, ValueError, httpx.HTTPError):
                return None

    return [r for r in await asyncio.gather(*(check(ip) for ip in hosts)) if r]
