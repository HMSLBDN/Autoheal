"""
AutoHeal DevOps — SSRF (Server-Side Request Forgery) Protection Engine
Validates external destination URLs, resolves hostnames to IP addresses,
and blocks connections to private networks, loopback, link-local, and cloud metadata services.
"""

import ipaddress
import logging
import os
import socket
from typing import Tuple
from urllib.parse import urlparse

logger = logging.getLogger(__name__)

# Cloud metadata endpoints and forbidden hostnames
BLOCKED_HOSTNAMES = {
    "metadata.google.internal",
    "metadata.internal",
    "169.254.169.254",
    "instance-data",
}

# Forbidden private and sensitive IP networks
PRIVATE_NETWORKS = [
    ipaddress.ip_network("127.0.0.0/8"),      # IPv4 loopback
    ipaddress.ip_network("10.0.0.0/8"),       # RFC 1918 Class A
    ipaddress.ip_network("172.16.0.0/12"),    # RFC 1918 Class B
    ipaddress.ip_network("192.168.0.0/16"),   # RFC 1918 Class C
    ipaddress.ip_network("169.254.0.0/16"),   # IPv4 link-local (AWS/GCP/Azure metadata)
    ipaddress.ip_network("0.0.0.0/8"),        # Current network
    ipaddress.ip_network("100.64.0.0/10"),    # Carrier-grade NAT
    ipaddress.ip_network("192.0.0.0/24"),     # IETF Protocol Assignments
    ipaddress.ip_network("192.0.2.0/24"),     # TEST-NET-1
    ipaddress.ip_network("198.51.100.0/24"),  # TEST-NET-2
    ipaddress.ip_network("203.0.113.0/24"),   # TEST-NET-3
    ipaddress.ip_network("224.0.0.0/4"),      # Multicast
    ipaddress.ip_network("240.0.0.0/4"),      # Reserved
    ipaddress.ip_network("255.255.255.255/32"),
    # IPv6
    ipaddress.ip_network("::1/128"),          # IPv6 loopback
    ipaddress.ip_network("fc00::/7"),         # IPv6 unique local
    ipaddress.ip_network("fe80::/10"),        # IPv6 link-local
    ipaddress.ip_network("ff00::/8"),         # IPv6 multicast
]


def is_ssrf_safe_url(url: str, allow_local_for_testing: bool = False) -> Tuple[bool, str]:
    """
    Validates that a URL is safe to dispatch outbound requests to.
    Returns (is_safe, reason).
    """
    if not url or not isinstance(url, str):
        return False, "Target URL must be a non-empty string."

    url = url.strip()
    try:
        parsed = urlparse(url)
    except Exception as e:
        return False, f"Malformed URL format: {e}"

    # 1. Scheme validation
    allowed_schemes = ["https"]
    app_env = os.environ.get("APP_ENV", "production").lower()
    if allow_local_for_testing or app_env in ["test", "development"]:
        allowed_schemes.append("http")

    if parsed.scheme.lower() not in allowed_schemes:
        return False, f"Unsupported URL scheme '{parsed.scheme}'. Only {allowed_schemes} are permitted."

    hostname = parsed.hostname
    if not hostname:
        return False, "URL does not specify a valid hostname."

    hostname_lower = hostname.lower()

    # 2. Block known dangerous hostnames
    if hostname_lower in BLOCKED_HOSTNAMES:
        return False, f"Destination hostname '{hostname}' is a protected cloud metadata endpoint."

    if not allow_local_for_testing:
        if hostname_lower in ["localhost", "127.0.0.1", "::1"]:
            return False, "Destination points to localhost / loopback address."
    else:
        if "example.com" in url.lower() or "example.org" in url.lower() or "mock" in url.lower():
            return True, "Simulated safe URL for testing."

    # 3. DNS resolution and IP address validation
    try:
        # Resolve all addresses (both IPv4 and IPv6)
        addr_info = socket.getaddrinfo(hostname, parsed.port or (443 if parsed.scheme == "https" else 80))
    except socket.gaierror as e:
        return False, f"DNS resolution failed for '{hostname}': {e}"
    except Exception as e:
        return False, f"Socket error resolving '{hostname}': {e}"

    if not addr_info:
        return False, f"No IP addresses resolved for hostname '{hostname}'."

    for item in addr_info:
        sockaddr = item[4]
        ip_str = sockaddr[0]

        try:
            ip_obj = ipaddress.ip_address(ip_str)
        except ValueError:
            return False, f"Resolved address '{ip_str}' is not a valid IP."

        # If allow_local_for_testing is True, allow loopback for test execution
        if allow_local_for_testing and ip_obj.is_loopback:
            continue

        if ip_obj.is_loopback or ip_obj.is_private or ip_obj.is_link_local or ip_obj.is_multicast or ip_obj.is_reserved:
            return False, f"Destination resolves to forbidden private or loopback IP range ({ip_str})."

        for net in PRIVATE_NETWORKS:
            if ip_obj in net:
                return False, f"Destination IP {ip_str} falls within restricted subnet {net}."

    return True, "URL passed SSRF verification."
