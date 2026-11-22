"""
Generates mutual TLS (mTLS) certificates for AutoHeal Phase 16 Docker Agent & L7 NGINX Proxy.
Certificates generated:
- ca.crt / ca.key: Internal Test Root Certificate Authority
- proxy.crt / proxy.key: Server certificate with SAN DNS:autoheal_socket_proxy
- agent.crt / agent.key: Client certificate with Subject CN=autoheal_docker_agent
"""
import os
import datetime
from pathlib import Path
from cryptography import x509
from cryptography.x509.oid import NameOID
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
import ipaddress


def generate_mtls_certificates(output_dir: Path) -> dict:
    output_dir.mkdir(parents=True, exist_ok=True)
    
    # 1. Generate Root CA
    ca_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    ca_subject = x509.Name([
        x509.NameAttribute(NameOID.COMMON_NAME, "AutoHeal Internal Test CA"),
        x509.NameAttribute(NameOID.ORGANIZATION_NAME, "AutoHeal DevOps"),
    ])
    now = datetime.datetime.now(datetime.timezone.utc)
    ca_cert = (
        x509.CertificateBuilder()
        .subject_name(ca_subject)
        .issuer_name(ca_subject)
        .public_key(ca_key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now)
        .not_valid_after(now + datetime.timedelta(days=365))
        .add_extension(x509.BasicConstraints(ca=True, path_length=None), critical=True)
        .sign(ca_key, hashes.SHA256())
    )

    ca_key_path = output_dir / "ca.key"
    ca_crt_path = output_dir / "ca.crt"
    with open(ca_key_path, "wb") as f:
        f.write(ca_key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.TraditionalOpenSSL,
            encryption_algorithm=serialization.NoEncryption()
        ))
    with open(ca_crt_path, "wb") as f:
        f.write(ca_cert.public_bytes(serialization.Encoding.PEM))

    # 2. Generate Proxy Server Certificate
    proxy_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    proxy_subject = x509.Name([
        x509.NameAttribute(NameOID.COMMON_NAME, "autoheal_socket_proxy"),
    ])
    proxy_cert = (
        x509.CertificateBuilder()
        .subject_name(proxy_subject)
        .issuer_name(ca_subject)
        .public_key(proxy_key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now)
        .not_valid_after(now + datetime.timedelta(days=365))
        .add_extension(
            x509.SubjectAlternativeName([
                x509.DNSName("autoheal_socket_proxy"),
                x509.DNSName("localhost"),
                x509.IPAddress(ipaddress.IPv4Address("127.0.0.1")),
            ]),
            critical=False,
        )
        .sign(ca_key, hashes.SHA256())
    )

    proxy_key_path = output_dir / "proxy.key"
    proxy_crt_path = output_dir / "proxy.crt"
    with open(proxy_key_path, "wb") as f:
        f.write(proxy_key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.TraditionalOpenSSL,
            encryption_algorithm=serialization.NoEncryption()
        ))
    with open(proxy_crt_path, "wb") as f:
        f.write(proxy_cert.public_bytes(serialization.Encoding.PEM))

    # 3. Generate Agent Client Certificate
    agent_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    agent_subject = x509.Name([
        x509.NameAttribute(NameOID.COMMON_NAME, "autoheal_docker_agent"),
    ])
    agent_cert = (
        x509.CertificateBuilder()
        .subject_name(agent_subject)
        .issuer_name(ca_subject)
        .public_key(agent_key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now)
        .not_valid_after(now + datetime.timedelta(days=365))
        .add_extension(
            x509.SubjectAlternativeName([
                x509.DNSName("autoheal_docker_agent"),
            ]),
            critical=False,
        )
        .sign(ca_key, hashes.SHA256())
    )

    agent_key_path = output_dir / "agent.key"
    agent_crt_path = output_dir / "agent.crt"
    with open(agent_key_path, "wb") as f:
        f.write(agent_key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.TraditionalOpenSSL,
            encryption_algorithm=serialization.NoEncryption()
        ))
    with open(agent_crt_path, "wb") as f:
        f.write(agent_cert.public_bytes(serialization.Encoding.PEM))

    return {
        "ca_crt": ca_crt_path,
        "ca_key": ca_key_path,
        "proxy_crt": proxy_crt_path,
        "proxy_key": proxy_key_path,
        "agent_crt": agent_crt_path,
        "agent_key": agent_key_path,
    }


if __name__ == "__main__":
    certs_dir = Path(__file__).parent / "certs"
    paths = generate_mtls_certificates(certs_dir)
    print(f"Generated certificates successfully in {certs_dir.resolve()}:")
    for name, path in paths.items():
        print(f"  {name}: {path.name}")
