"""
AutoHeal DevOps — Restricted Infrastructure Agent Allowlist
Defines the strictly permissible operations and parameter schemas for remote agents.
Never allows arbitrary shell scripts or unconstrained parameters.
"""

import re
from typing import Any, Dict, Set, Tuple

# Approved actions that remote infrastructure agents are permitted to execute
ALLOWED_AGENT_ACTIONS: Set[str] = {
    "restart_service",
    "scale_service",
    "rollback_deployment",
    "clear_cache",
}

# Parameter constraints per action
ACTION_PARAMETER_SCHEMAS: Dict[str, Dict[str, Any]] = {
    "restart_service": {
        "grace_period_seconds": {"type": int, "min": 0, "max": 60, "default": 10},
    },
    "scale_service": {
        "replicas": {"type": int, "min": 1, "max": 10, "required": True},
    },
    "rollback_deployment": {
        "target_revision": {"type": str, "pattern": r"^[a-zA-Z0-9_\-\.]{1,64}$", "default": "previous"},
    },
    "clear_cache": {
        "cache_tier": {"type": str, "pattern": r"^(redis|memcached|session)$", "default": "redis"},
        "key_prefix": {"type": str, "pattern": r"^[a-zA-Z0-9_\-\:]{1,32}$", "default": "cache:*"},
    },
}

# Shell metacharacters forbidden across all inputs
FORBIDDEN_CHARS_PATTERN = re.compile(r"[;&|`$><\n\r\t\\]")


def validate_agent_action(action_type: str, parameters: Dict[str, Any]) -> Tuple[bool, str, Dict[str, Any]]:
    """
    Validates an action type and its parameters against the strict infrastructure allowlist.
    Returns: (is_valid: bool, error_message: str, sanitized_parameters: dict)
    """
    clean_action = action_type.strip().lower()
    if clean_action not in ALLOWED_AGENT_ACTIONS:
        return (
            False,
            f"Action '{action_type}' is not permitted. Allowed actions: {sorted(list(ALLOWED_AGENT_ACTIONS))}",
            {},
        )

    schema = ACTION_PARAMETER_SCHEMAS.get(clean_action, {})
    sanitized: Dict[str, Any] = {}

    for param_name, constraints in schema.items():
        expected_type = constraints.get("type")
        val = parameters.get(param_name)

        if val is None:
            if constraints.get("required", False):
                return False, f"Missing required parameter '{param_name}' for action '{clean_action}'.", {}
            sanitized[param_name] = constraints.get("default")
            continue

        # Type checking
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
            val = val.strip()
            # Check for shell metacharacters
            if FORBIDDEN_CHARS_PATTERN.search(val):
                return False, f"Security violation: Illegal characters detected in parameter '{param_name}'.", {}
            # Check pattern
            pattern = constraints.get("pattern")
            if pattern and not re.match(pattern, val):
                return False, f"Parameter '{param_name}' does not match permitted pattern '{pattern}'.", {}
            sanitized[param_name] = val

        else:
            sanitized[param_name] = val

    # Disallow unexpected parameters
    for extra_key in parameters.keys():
        if extra_key not in schema:
            return False, f"Unrecognized parameter '{extra_key}' for action '{clean_action}'.", {}

    return True, "", sanitized
