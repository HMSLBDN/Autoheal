#!/usr/bin/env python3
"""
AutoHeal DevOps — Enterprise Software Bill of Materials (SBOM) Generator
Generates CycloneDX and SPDX specification compliant JSON SBOMs
for supply-chain security auditing and vulnerability management.
"""

from datetime import datetime, timezone
import hashlib
import json
import os
import sys
import uuid
from typing import List, Dict, Any


def get_python_components() -> List[Dict[str, Any]]:
    """Extracts installed Python packages and versions."""
    components = []
    try:
        import importlib.metadata
        for dist in importlib.metadata.distributions():
            name = dist.metadata["Name"]
            version = dist.metadata["Version"]
            purl = f"pkg:pypi/{name.lower()}@{version}"
            components.append({
                "type": "library",
                "name": name,
                "version": version,
                "purl": purl,
                "scope": "required",
                "licenses": [{"license": {"name": dist.metadata.get("License", "UNKNOWN")}}],
            })
    except Exception as e:
        print(f"Warning: could not inspect Python distributions: {e}")
    return components


def get_nodejs_components() -> List[Dict[str, Any]]:
    """Parses root package.json for Node.js frontend dependencies."""
    components = []
    pkg_json_path = os.path.join(os.path.dirname(__file__), "..", "package.json")
    if os.path.exists(pkg_json_path):
        try:
            with open(pkg_json_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            deps = data.get("dependencies", {})
            for name, ver in deps.items():
                clean_ver = ver.lstrip("^~")
                purl = f"pkg:npm/{name}@{clean_ver}"
                components.append({
                    "type": "library",
                    "name": name,
                    "version": clean_ver,
                    "purl": purl,
                    "scope": "required",
                })
        except Exception as e:
            print(f"Warning: could not parse package.json: {e}")
    return components


def generate_cyclonedx_sbom(components: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Generates CycloneDX v1.5 JSON formatted SBOM."""
    return {
        "bomFormat": "CycloneDX",
        "specVersion": "1.5",
        "serialNumber": f"urn:uuid:{uuid.uuid4()}",
        "version": 1,
        "metadata": {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "tools": [
                {
                    "vendor": "AutoHeal DevOps",
                    "name": "AutoHeal SBOM Engine",
                    "version": "1.0.0",
                }
            ],
            "component": {
                "type": "application",
                "name": "autoheal-devops-saas",
                "version": "1.0.0",
                "description": "AutoHeal Autonomous Self-Healing DevOps SaaS Platform",
            },
        },
        "components": components,
    }


def generate_spdx_sbom(components: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Generates SPDX 2.3 JSON formatted SBOM."""
    spdx_packages = []
    for c in components:
        spdx_packages.append({
            "SPDXID": f"SPDXRef-Package-{c['name'].replace('/', '-')}-{c['version']}",
            "name": c["name"],
            "versionInfo": c["version"],
            "downloadLocation": "NOASSERTION",
            "filesAnalyzed": False,
            "licenseConcluded": "NOASSERTION",
            "licenseDeclared": "NOASSERTION",
            "copyrightText": "NOASSERTION",
            "externalRefs": [
                {
                    "referenceCategory": "PACKAGE_MANAGER",
                    "referenceType": "purl",
                    "referenceLocator": c.get("purl", f"pkg:generic/{c['name']}@{c['version']}"),
                }
            ],
        })

    return {
        "spdxVersion": "SPDX-2.3",
        "dataLicense": "CC0-1.0",
        "SPDXID": "SPDXRef-DOCUMENT",
        "name": "AutoHeal-DevOps-SaaS",
        "documentNamespace": f"https://autoheal.dev/spdx/{uuid.uuid4()}",
        "creationInfo": {
            "created": datetime.now(timezone.utc).isoformat(),
            "creators": ["Tool: AutoHeal-SBOM-Generator-1.0"],
        },
        "packages": spdx_packages,
    }


def main():
    print("Generating Enterprise SBOMs (CycloneDX & SPDX)...")
    py_components = get_python_components()
    node_components = get_nodejs_components()
    all_components = py_components + node_components

    cyclonedx = generate_cyclonedx_sbom(all_components)
    spdx = generate_spdx_sbom(all_components)

    out_dir = os.path.join(os.path.dirname(__file__), "..", "monitoring", "sbom")
    os.makedirs(out_dir, exist_ok=True)

    cyclonedx_path = os.path.join(out_dir, "bom.cyclonedx.json")
    spdx_path = os.path.join(out_dir, "bom.spdx.json")

    with open(cyclonedx_path, "w", encoding="utf-8") as f:
        json.dump(cyclonedx, f, indent=2)

    with open(spdx_path, "w", encoding="utf-8") as f:
        json.dump(spdx, f, indent=2)

    print(f"Successfully generated CycloneDX SBOM: {cyclonedx_path} ({len(all_components)} components)")
    print(f"Successfully generated SPDX SBOM: {spdx_path} ({len(all_components)} packages)")


if __name__ == "__main__":
    main()
