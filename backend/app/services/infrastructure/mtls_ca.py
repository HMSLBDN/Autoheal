"""
AutoHeal DevOps — Enterprise Infrastructure Agent Mutual TLS (mTLS) CA Engine
Provides cryptographically secure X.509 Certificate Authority (CA) management,
Client Certificate issuance, rotation, CRL/revocation enforcement, and live TLS handshake verification.
"""

from datetime import datetime, timedelta, timezone
import hashlib
import ipaddress
import logging
import os
import ssl
import tempfile
from typing import Optional, Dict, Any, Tuple, List, Union
from uuid import UUID

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa, padding
from cryptography.x509.oid import NameOID, ExtendedKeyUsageOID
from sqlalchemy import select, update, and_
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.phase10 import AgentCertificate
from app.models.agent import InfrastructureAgent
from app.services.security.session_service import SecurityAuditService

logger = logging.getLogger(__name__)

# CA storage cache per organization in-process (or fallback generate)
_CA_KEY_CACHE: Dict[str, rsa.RSAPrivateKey] = {}
_CA_CERT_CACHE: Dict[str, x509.Certificate] = {}


class AgentCA:
    """
    Dedicated Certificate Authority engine for AutoHeal Infrastructure Agents.
    Enforces mTLS (mutual TLS) client certificate authentication.
    """

    @classmethod
    def get_or_create_org_ca(cls, organization_id: UUID) -> Tuple[rsa.RSAPrivateKey, x509.Certificate]:
        """
        Retrieves or generates an organization-dedicated Root Certificate Authority.
        """
        org_str = str(organization_id)
        if org_str in _CA_KEY_CACHE and org_str in _CA_CERT_CACHE:
            return _CA_KEY_CACHE[org_str], _CA_CERT_CACHE[org_str]

        # Generate fresh 2048-bit RSA key for CA
        ca_key = rsa.generate_private_key(
            public_exponent=65537,
            key_size=2048,
        )

        subject = issuer = x509.Name([
            x509.NameAttribute(NameOID.ORGANIZATION_NAME, f"AutoHeal-Org-{org_str[:8]}"),
            x509.NameAttribute(NameOID.ORGANIZATIONAL_UNIT_NAME, "Security Operations CA"),
            x509.NameAttribute(NameOID.COMMON_NAME, f"AutoHeal Root CA ({org_str[:8]})"),
        ])

        now = datetime.now(timezone.utc)
        ca_cert = (
            x509.CertificateBuilder()
            .subject_name(subject)
            .issuer_name(issuer)
            .public_key(ca_key.public_key())
            .serial_number(x509.random_serial_number())
            .not_valid_before(now - timedelta(days=1))
            .not_valid_after(now + timedelta(days=3650))  # 10 years validity
            .add_extension(
                x509.BasicConstraints(ca=True, path_length=None),
                critical=True,
            )
            .add_extension(
                x509.KeyUsage(
                    digital_signature=True,
                    content_commitment=False,
                    key_encipherment=False,
                    data_encipherment=False,
                    key_agreement=False,
                    key_cert_sign=True,
                    crl_sign=True,
                    encipher_only=False,
                    decipher_only=False,
                ),
                critical=True,
            )
            .sign(ca_key, hashes.SHA256())
        )

        _CA_KEY_CACHE[org_str] = ca_key
        _CA_CERT_CACHE[org_str] = ca_cert
        return ca_key, ca_cert

    @classmethod
    def get_org_ca_pem(cls, organization_id: UUID) -> str:
        """
        Exports Organization CA certificate in PEM format.
        """
        _, ca_cert = cls.get_or_create_org_ca(organization_id)
        return ca_cert.public_bytes(serialization.Encoding.PEM).decode("utf-8")

    @classmethod
    async def issue_agent_certificate(
        cls,
        db: AsyncSession,
        organization_id: UUID,
        agent_id: Union[str, UUID],
        common_name: Optional[str] = None,
        valid_days: int = 365,
    ) -> Tuple[AgentCertificate, str, str, str]:
        """
        Generates an X.509 client certificate for an infrastructure agent signed by org CA.
        Returns: (AgentCertificate model, cert_pem, private_key_pem, ca_cert_pem)
        """
        ca_key, ca_cert = cls.get_or_create_org_ca(organization_id)
        agent_id_str = str(agent_id)

        # Generate agent private key
        agent_key = rsa.generate_private_key(
            public_exponent=65537,
            key_size=2048,
        )

        cn = common_name or f"agent-{agent_id_str[:8]}"
        subject = x509.Name([
            x509.NameAttribute(NameOID.ORGANIZATION_NAME, f"AutoHeal-Org-{str(organization_id)[:8]}"),
            x509.NameAttribute(NameOID.ORGANIZATIONAL_UNIT_NAME, "Infrastructure Agents"),
            x509.NameAttribute(NameOID.COMMON_NAME, cn),
        ])

        now = datetime.now(timezone.utc)
        valid_to = now + timedelta(days=valid_days)
        serial_int = x509.random_serial_number()
        serial_hex = f"{serial_int:x}"

        cert = (
            x509.CertificateBuilder()
            .subject_name(subject)
            .issuer_name(ca_cert.subject)
            .public_key(agent_key.public_key())
            .serial_number(serial_int)
            .not_valid_before(now - timedelta(minutes=5))
            .not_valid_after(valid_to)
            .add_extension(
                x509.BasicConstraints(ca=False, path_length=None),
                critical=True,
            )
            .add_extension(
                x509.KeyUsage(
                    digital_signature=True,
                    content_commitment=False,
                    key_encipherment=True,
                    data_encipherment=False,
                    key_agreement=False,
                    key_cert_sign=False,
                    crl_sign=False,
                    encipher_only=False,
                    decipher_only=False,
                ),
                critical=True,
            )
            .add_extension(
                x509.ExtendedKeyUsage([ExtendedKeyUsageOID.CLIENT_AUTH]),
                critical=False,
            )
            .sign(ca_key, hashes.SHA256())
        )

        cert_pem = cert.public_bytes(serialization.Encoding.PEM).decode("utf-8")
        key_pem = agent_key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption(),
        ).decode("utf-8")
        ca_pem = ca_cert.public_bytes(serialization.Encoding.PEM).decode("utf-8")

        fingerprint = cert.fingerprint(hashes.SHA256()).hex()

        # Invalidate/revoke any existing unrevoked certs for this agent (rotation)
        await db.execute(
            update(AgentCertificate)
            .where(
                AgentCertificate.agent_id == agent_id_str,
                AgentCertificate.organization_id == organization_id,
                AgentCertificate.is_revoked == False,
            )
            .values(
                is_revoked=True,
                revoked_at=now,
                revocation_reason="Superseded by certificate rotation",
            )
        )

        db_cert = AgentCertificate(
            organization_id=organization_id,
            agent_id=agent_id_str,
            serial_number=serial_hex,
            fingerprint_sha256=fingerprint,
            subject_dn=cn,
            issuer_dn=ca_cert.subject.rfc4514_string(),
            valid_from=now,
            valid_to=valid_to,
            is_revoked=False,
            cert_pem=cert_pem,
        )
        db.add(db_cert)

        # Also update agent model fingerprint
        stmt_agent = select(InfrastructureAgent).where(InfrastructureAgent.id == agent_id_str)
        res_agent = await db.execute(stmt_agent)
        agent = res_agent.scalars().first()
        if agent:
            agent.public_key_fingerprint = f"sha256:{fingerprint[:16]}..."

        await db.commit()
        await db.refresh(db_cert)

        await SecurityAuditService.log_event(
            db=db,
            organization_id=organization_id,
            event_type="cert_rotated",
            severity="INFO",
            details={
                "agent_id": agent_id_str,
                "serial_number": serial_hex,
                "fingerprint": fingerprint,
                "valid_to": valid_to.isoformat(),
            },
        )

        return db_cert, cert_pem, key_pem, ca_pem

    @classmethod
    async def verify_agent_certificate(
        cls,
        db: AsyncSession,
        organization_id: UUID,
        cert_pem: str,
    ) -> Dict[str, Any]:
        """
        Verifies client certificate against Organization Root CA, checks validity period and database revocation status.
        """
        try:
            cert = x509.load_pem_x509_certificate(cert_pem.encode("utf-8"))
        except Exception as e:
            return {"valid": False, "reason": f"Malformed certificate PEM: {str(e)}"}

        now = datetime.now(timezone.utc)
        if now < cert.not_valid_before_utc:
            return {"valid": False, "reason": "Certificate is not yet valid."}
        if now > cert.not_valid_after_utc:
            return {"valid": False, "reason": "Certificate has expired."}

        # Verify signature with CA public key
        ca_key, ca_cert = cls.get_or_create_org_ca(organization_id)
        try:
            ca_public_key = ca_cert.public_key()
            ca_public_key.verify(
                cert.signature,
                cert.tbs_certificate_bytes,
                padding.PKCS1v15(),
                cert.signature_hash_algorithm,
            )
        except Exception as e:
            return {"valid": False, "reason": f"Cryptographic CA signature verification failed: {str(e)}"}

        fingerprint = cert.fingerprint(hashes.SHA256()).hex()

        # Check DB revocation status
        stmt = select(AgentCertificate).where(
            AgentCertificate.fingerprint_sha256 == fingerprint,
            AgentCertificate.organization_id == organization_id,
        )
        res = await db.execute(stmt)
        record = res.scalars().first()

        if not record:
            return {"valid": False, "reason": "Certificate fingerprint not registered in organization catalog."}

        if record.is_revoked:
            return {
                "valid": False,
                "reason": f"Certificate was revoked on {record.revoked_at} (Reason: {record.revocation_reason})",
            }

        return {
            "valid": True,
            "agent_id": str(record.agent_id),
            "fingerprint": fingerprint,
            "serial_number": record.serial_number,
            "subject_dn": record.subject_dn,
            "valid_to": record.valid_to.isoformat(),
        }

    @classmethod
    async def revoke_certificate(
        cls,
        db: AsyncSession,
        organization_id: UUID,
        agent_id: Union[str, UUID],
        reason: str = "Operator manual revocation",
    ) -> bool:
        """
        Revokes the active certificate for an infrastructure agent.
        """
        now = datetime.now(timezone.utc)
        agent_id_str = str(agent_id)
        stmt = (
            update(AgentCertificate)
            .where(
                AgentCertificate.agent_id == agent_id_str,
                AgentCertificate.organization_id == organization_id,
                AgentCertificate.is_revoked == False,
            )
            .values(
                is_revoked=True,
                revoked_at=now,
                revocation_reason=reason,
            )
        )
        result = await db.execute(stmt)
        await db.commit()

        if result.rowcount > 0:
            await SecurityAuditService.log_event(
                db=db,
                organization_id=organization_id,
                event_type="cert_revoked",
                severity="WARNING",
                details={
                    "agent_id": agent_id_str,
                    "reason": reason,
                },
            )
            return True
        return False

    @classmethod
    def test_live_mtls_handshake(
        cls,
        organization_id: UUID,
        client_cert_pem: str,
        client_key_pem: str,
    ) -> Dict[str, Any]:
        """
        Executes a real mutual TLS in-memory handshake negotiation
        with verify_mode=CERT_REQUIRED on the server side.
        """
        ca_key, ca_cert = cls.get_or_create_org_ca(organization_id)
        ca_pem = ca_cert.public_bytes(serialization.Encoding.PEM).decode("utf-8")

        # Generate temporary server cert signed by same CA
        srv_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        srv_name = x509.Name([
            x509.NameAttribute(NameOID.COMMON_NAME, "localhost"),
        ])
        now = datetime.now(timezone.utc)
        srv_cert = (
            x509.CertificateBuilder()
            .subject_name(srv_name)
            .issuer_name(ca_cert.subject)
            .public_key(srv_key.public_key())
            .serial_number(x509.random_serial_number())
            .not_valid_before(now - timedelta(minutes=5))
            .not_valid_after(now + timedelta(days=1))
            .sign(ca_key, hashes.SHA256())
        )
        srv_pem = srv_cert.public_bytes(serialization.Encoding.PEM).decode("utf-8")
        srv_key_pem = srv_key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption(),
        ).decode("utf-8")

        temp_files = []
        try:
            def _write_temp(data: str) -> str:
                f = tempfile.NamedTemporaryFile("w", delete=False)
                f.write(data)
                f.flush()
                f.close()
                temp_files.append(f.name)
                return f.name

            ca_file = _write_temp(ca_pem)
            srv_cert_file = _write_temp(srv_pem)
            srv_key_file = _write_temp(srv_key_pem)
            cli_cert_file = _write_temp(client_cert_pem)
            cli_key_file = _write_temp(client_key_pem)

            # Server context requiring client certificate
            srv_ctx = ssl.create_default_context(ssl.Purpose.CLIENT_AUTH)
            srv_ctx.verify_mode = ssl.CERT_REQUIRED
            srv_ctx.load_verify_locations(ca_file)
            srv_ctx.load_cert_chain(srv_cert_file, srv_key_file)

            # Client context
            cli_ctx = ssl.create_default_context(ssl.Purpose.SERVER_AUTH)
            cli_ctx.load_verify_locations(ca_file)
            cli_ctx.load_cert_chain(cli_cert_file, cli_key_file)

            incoming_srv = ssl.MemoryBIO()
            outgoing_srv = ssl.MemoryBIO()
            srv_ssl = srv_ctx.wrap_bio(incoming_srv, outgoing_srv, server_side=True)

            incoming_cli = ssl.MemoryBIO()
            outgoing_cli = ssl.MemoryBIO()
            cli_ssl = cli_ctx.wrap_bio(incoming_cli, outgoing_cli, server_side=False, server_hostname="localhost")

            # Pump handshake
            for _ in range(12):
                try:
                    cli_ssl.do_handshake()
                except ssl.SSLWantReadError:
                    pass
                read_cli = outgoing_cli.read()
                if read_cli:
                    incoming_srv.write(read_cli)

                try:
                    srv_ssl.do_handshake()
                except ssl.SSLWantReadError:
                    pass
                read_srv = outgoing_srv.read()
                if read_srv:
                    incoming_cli.write(read_srv)

            peer = srv_ssl.getpeercert()
            cipher = srv_ssl.cipher()
            version = srv_ssl.version()

            return {
                "handshake_success": bool(peer),
                "peer_certificate": peer,
                "cipher_used": cipher[0] if cipher else "Unknown",
                "protocol_version": version or "TLSv1.3",
            }
        except Exception as e:
            logger.error("mTLS Handshake test failed: %s", e)
            return {
                "handshake_success": False,
                "error": str(e),
            }
        finally:
            for p in temp_files:
                try:
                    os.unlink(p)
                except OSError:
                    pass

    @classmethod
    def test_live_tcp_socket_mtls_handshake(
        cls,
        organization_id: UUID,
        client_cert_pem: Optional[str] = None,
        client_key_pem: Optional[str] = None,
        custom_ca_pem: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Executes a real local TCP socket-level mutual TLS handshake
        over loopback (127.0.0.1) on an ephemeral port, verifying actual
        network-layer TLS handshake negotiation with client certificate authentication.
        """
        import socket
        import threading

        ca_key, ca_cert = cls.get_or_create_org_ca(organization_id)
        ca_pem = custom_ca_pem or ca_cert.public_bytes(serialization.Encoding.PEM).decode("utf-8")

        # Generate temporary server cert signed by CA
        srv_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        now = datetime.now(timezone.utc)
        srv_cert = (
            x509.CertificateBuilder()
            .subject_name(x509.Name([
                x509.NameAttribute(NameOID.COMMON_NAME, "127.0.0.1"),
                x509.NameAttribute(NameOID.ORGANIZATION_NAME, f"AutoHeal Server {str(organization_id)[:8]}"),
            ]))
            .issuer_name(ca_cert.subject)
            .public_key(srv_key.public_key())
            .serial_number(x509.random_serial_number())
            .not_valid_before(now - timedelta(minutes=5))
            .not_valid_after(now + timedelta(days=1))
            .add_extension(
                x509.SubjectAlternativeName([
                    x509.IPAddress(ipaddress.IPv4Address("127.0.0.1")),
                    x509.DNSName("localhost"),
                ]),
                critical=False,
            )
            .sign(ca_key, hashes.SHA256())
        )
        srv_pem = srv_cert.public_bytes(serialization.Encoding.PEM).decode("utf-8")
        srv_key_pem = srv_key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption(),
        ).decode("utf-8")

        temp_files = []
        try:
            def _write_temp(data: str) -> str:
                f = tempfile.NamedTemporaryFile("w", delete=False)
                f.write(data)
                f.flush()
                f.close()
                temp_files.append(f.name)
                return f.name

            ca_file = _write_temp(ca_pem)
            srv_cert_file = _write_temp(srv_pem)
            srv_key_file = _write_temp(srv_key_pem)

            # Server SSL context requiring client certificate
            server_ctx = ssl.create_default_context(ssl.Purpose.CLIENT_AUTH)
            server_ctx.verify_mode = ssl.CERT_REQUIRED
            server_ctx.load_verify_locations(ca_file)
            server_ctx.load_cert_chain(srv_cert_file, srv_key_file)

            # Client SSL context
            client_ctx = ssl.create_default_context(ssl.Purpose.SERVER_AUTH)
            client_ctx.load_verify_locations(ca_file)
            client_ctx.check_hostname = False

            if client_cert_pem and client_key_pem:
                cli_cert_file = _write_temp(client_cert_pem)
                cli_key_file = _write_temp(client_key_pem)
                client_ctx.load_cert_chain(cli_cert_file, cli_key_file)

            server_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            server_sock.bind(("127.0.0.1", 0))
            port = server_sock.getsockname()[1]
            server_sock.listen(1)

            result: Dict[str, Any] = {"handshake_success": False}
            server_error: List[Exception] = []

            def server_worker():
                try:
                    conn, _ = server_sock.accept()
                    with server_ctx.wrap_socket(conn, server_side=True) as ssl_conn:
                        peer = ssl_conn.getpeercert()
                        data = ssl_conn.recv(1024)
                        ssl_conn.sendall(b"MTLS_AUTH_CONFIRMED: " + data)
                        result["server_peer_cert"] = peer
                        result["cipher_used"] = ssl_conn.cipher()[0]
                        result["protocol"] = ssl_conn.version()
                except Exception as exc:
                    server_error.append(exc)
                finally:
                    server_sock.close()

            th = threading.Thread(target=server_worker, daemon=True)
            th.start()

            try:
                raw_client = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                raw_client.settimeout(3.0)
                raw_client.connect(("127.0.0.1", port))
                with client_ctx.wrap_socket(raw_client, server_hostname="127.0.0.1") as ssl_client:
                    ssl_client.sendall(b"PING_AGENT_NODE")
                    response = ssl_client.recv(1024)
                    if b"MTLS_AUTH_CONFIRMED" in response:
                        result["handshake_success"] = True
                        result["client_verified_response"] = response.decode("utf-8")
            except Exception as client_exc:
                result["client_error"] = str(client_exc)
            finally:
                th.join(timeout=3.0)
                if server_error:
                    result["server_error"] = str(server_error[0])

            return result
        except Exception as outer_exc:
            return {"handshake_success": False, "error": str(outer_exc)}
        finally:
            for p in temp_files:
                try:
                    os.unlink(p)
                except OSError:
                    pass
