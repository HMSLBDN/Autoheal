"""
Restricted Docker Agent — Server-Side Allowlist Engine
Enforces independent server-side container allowlists and operation allowlists.
The backend is NEVER trusted as the sole security boundary.
"""

from typing import Any, Dict, Set, Tuple

# Approved container identifiers (only designated local test containers permitted)
APPROVED_CONTAINERS: Set[str] = {
    "autoheal_test_service",
    "test-service",
}

# Explicitly prohibited containers (core infrastructure services must NEVER be targeted)
CRITICAL_PROTECTED_CONTAINERS: Set[str] = {
    "db",
    "postgres",
    "redis",
    "backend",
    "frontend",
    "celery_worker",
    "celery_beat",
    "prometheus",
    "alertmanager",
    "grafana",
    "node_exporter",
    "cadvisor",
    "otel_collector",
    "jaeger",
}

# Approved operations
ALLOWED_OPERATIONS: Set[str] = {
    "inspect_container",
    "get_container_state",
    "get_container_health",
    "restart_container",
    "verify_container_health",
}

# Parameter constraints per operation
OPERATION_PARAMETER_SCHEMAS: Dict[str, Dict[str, Any]] = {
    "restart_container": {
        "timeout_seconds": {"type": int, "min": 1, "max": 60, "default": 15},
    },
    "inspect_container": {},
    "get_container_state": {},
    "get_container_health": {},
    "verify_container_health": {
        "health_endpoint": {"type": str, "default": "/health"},
        "expected_status": {"type": int, "default": 200},
    },
}


def validate_operation_allowlist(
    target_container: str,
    action_type: str,
    parameters: Dict[str, Any],
    custom_approved_containers: Set[str] = None,
) -> Tuple[bool, str, Dict[str, Any]]:
    """
    Independently validates target container and requested operation against strict allowlists.
    Returns: (is_allowed: bool, rejection_reason: str, sanitized_parameters: dict)
    """
    clean_container = target_container.strip()
    clean_action = action_type.strip().lower()

    # 1. Container Allowlist Validation
    effective_approved = custom_approved_containers if custom_approved_containers is not None else APPROVED_CONTAINERS

    if clean_container in CRITICAL_PROTECTED_CONTAINERS:
        return (
            False,
            f"Security violation: Container '{clean_container}' is a protected core infrastructure service. Recovery operations are strictly forbidden.",
            {},
        )

    if clean_container not in effective_approved:
        return (
            False,
            f"Access denied: Container '{clean_container}' is not registered in the approved target allowlist. Permitted: {sorted(list(effective_approved))}",
            {},
        )

    # 2. Action Type Allowlist Validation
    if clean_action not in ALLOWED_OPERATIONS:
        return (
            False,
            f"Security violation: Action '{action_type}' is not in the approved operations allowlist. Permitted: {sorted(list(ALLOWED_OPERATIONS))}",
            {},
        )

    # 3. Parameter Schema Validation
    schema = OPERATION_PARAMETER_SCHEMAS.get(clean_action, {})
    sanitized: Dict[str, Any] = {}

    for param_name, constraints in schema.items():
        val = parameters.get(param_name)
        if val is None:
            sanitized[param_name] = constraints.get("default")
            continue

        expected_type = constraints.get("type")
        if expected_type == int:
            try:
                val = int(val)
            except (ValueError, TypeError):
                return False, f"Parameter '{param_name}' must be an integer.", {}
            if "min" in constraints and val < constraints["min"]:
                return False, f"Parameter '{param_name}' must be >= {constraints['min']}.", {}
            if "max" in constraints and val > constraints["max"]:
                return False, f"Parameter '{param_name}' must be <= {constraints['max']}.", {}
            sanitized[param_name] = val
        elif expected_type == str:
            if not isinstance(val, str):
                return False, f"Parameter '{param_name}' must be a string.", {}
            val_clean = val.strip()
            # Disallow control characters
            if any(ch in val_clean for ch in (";", "&", "|", "`", "$", "\n", "\r", " ")):
                return False, f"Illegal characters detected in parameter '{param_name}'.", {}
            sanitized[param_name] = val_clean

    # Disallow unexpected parameters
    for extra_key in parameters.keys():
        if extra_key not in schema:
            return False, f"Unrecognized parameter '{extra_key}' for action '{clean_action}'.", {}

    return True, "", sanitized
