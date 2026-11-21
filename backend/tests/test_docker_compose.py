"""
AutoHeal DevOps — Dockerfile and Compose Configuration Syntax Validation Tests
"""

from pathlib import Path
import pytest
import yaml


def _find_repo_root() -> Path:
    current = Path(__file__).resolve()
    for candidate in [current.parent.parent.parent, current.parent.parent, current.parent, Path("/")]:
        if (candidate / "docker-compose.yml").exists() and (candidate / "docker-compose.dev.yml").exists():
            return candidate
    return current.parent.parent.parent


def test_docker_compose_production_structure():
    compose_path = _find_repo_root() / "docker-compose.yml"
    assert compose_path.exists(), "docker-compose.yml must exist"

    with open(compose_path, "r", encoding="utf-8") as f:
        config = yaml.safe_load(f)

    services = config.get("services", {})
    required_services = [
        "frontend",
        "backend",
        "celery_worker",
        "celery_beat",
        "db",
        "redis",
        "prometheus",
        "alertmanager",
        "grafana",
        "node_exporter",
        "cadvisor",
    ]

    for svc in required_services:
        assert svc in services, f"Required service '{svc}' missing in docker-compose.yml"

    # Security check: PostgreSQL and Redis must not have public exposed ports in production
    assert "ports" not in services["db"], "PostgreSQL must not expose ports to host in production docker-compose.yml"
    assert "ports" not in services["redis"], "Redis must not expose ports to host in production docker-compose.yml"

    # Security check: Zero Docker socket mounts
    for svc_name, svc_conf in services.items():
        volumes = svc_conf.get("volumes", [])
        for vol in volumes:
            vol_str = vol if isinstance(vol, str) else vol.get("source", "")
            assert "docker.sock" not in vol_str, f"Security violation: Docker socket mounted in service '{svc_name}'!"


def test_docker_compose_development_structure():
    compose_dev_path = _find_repo_root() / "docker-compose.dev.yml"
    assert compose_dev_path.exists(), "docker-compose.dev.yml must exist"

    with open(compose_dev_path, "r", encoding="utf-8") as f:
        config = yaml.safe_load(f)

    services = config.get("services", {})
    assert "db" in services
    assert "redis" in services
    assert "backend" in services
    assert "checkout-api" in services
    assert "customer-web" in services
    assert "payments-api" in services

    # Security check: All published development ports must explicitly bind to localhost (127.0.0.1)
    for svc_name, svc_conf in services.items():
        ports = svc_conf.get("ports", [])
        for port in ports:
            port_str = port if isinstance(port, str) else str(port)
            assert port_str.startswith("127.0.0.1:"), (
                f"Security violation in dev compose: Service '{svc_name}' port '{port_str}' "
                f"must bind explicitly to '127.0.0.1' to prevent external network exposure!"
            )


def test_dockerfiles_exist_and_non_root():
    root = _find_repo_root()
    if (root / "backend").exists():
        backend_dir = root / "backend"
    elif Path("/app/Dockerfile.celery_worker").exists():
        backend_dir = Path("/app")
    else:
        backend_dir = root

    dockerfiles = [
        root / "Dockerfile" if (root / "Dockerfile").exists() else backend_dir / "Dockerfile",
        backend_dir / "Dockerfile",
        backend_dir / "Dockerfile.celery_worker",
        backend_dir / "Dockerfile.celery_beat",
    ]

    for df in dockerfiles:
        assert df.exists(), f"Dockerfile {df} must exist"
        content = df.read_text(encoding="utf-8")
        assert "USER " in content, f"Dockerfile {df.name} must run as an unprivileged non-root USER!"
