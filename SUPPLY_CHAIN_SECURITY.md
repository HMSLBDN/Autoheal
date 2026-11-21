# AutoHeal DevOps — Software Supply Chain Security & SBOM Specification

## 1. Executive Summary

In compliance with Executive Order 14028, NIST SP 800-218 (Secure Software Development Framework), and enterprise procurement standards, AutoHeal DevOps SaaS Phase 10 implements software supply chain security controls across all dependencies, build pipelines, and distribution artifacts.

Automated pipelines generate machine-readable Software Bill of Materials (SBOM) in both **CycloneDX v1.5** and **SPDX v2.3** formats.

---

## 2. Software Bill of Materials (SBOM) Artifacts

The supply chain generation script (`scripts/generate_sbom.py`) scans runtime environments, package manifests, and direct and transitive dependencies:

| Specification Standard | Schema Version | Output File | Component Count | Format |
|:---|:---|:---|:---|:---|
| **CycloneDX** | 1.5 JSON | `monitoring/sbom/bom.cyclonedx.json` | **77 components** | Machine-readable JSON |
| **SPDX** | 2.3 JSON | `monitoring/sbom/bom.spdx.json` | **77 packages** | Machine-readable JSON |

### 2.1 CycloneDX Sample Structure

```json
{
  "bomFormat": "CycloneDX",
  "specVersion": "1.5",
  "serialNumber": "urn:uuid:68cf2fc5-6972-4752-9e9b-980b1da79b76",
  "version": 1,
  "metadata": {
    "timestamp": "2026-11-21T11:42:33Z",
    "component": {
      "type": "application",
      "name": "autoheal-devops-saas",
      "version": "1.0.0"
    }
  },
  "components": [
    {
      "type": "library",
      "name": "fastapi",
      "version": "0.115.0",
      "purl": "pkg:pypi/fastapi@0.115.0",
      "scope": "required"
    },
    {
      "type": "library",
      "name": "cryptography",
      "version": "43.0.1",
      "purl": "pkg:pypi/cryptography@43.0.1",
      "scope": "required"
    }
  ]
}
```

---

## 3. Dependency Vulnerability Management & Continuous Auditing

AutoHeal employs a multi-layered vulnerability detection and remediation strategy:

1. **Python Backend Auditing**:
   - `pip-audit`: Automated scanning against the Open Source Vulnerabilities (OSV) database and PyPI Advisory database in CI.
   - Any package with a CVSS score >= 7.0 (High or Critical) immediately fails GitHub Actions builds.
2. **Frontend Node.js Auditing**:
   - `npm audit --audit-level=high`: Validates all frontend React / Next.js dependencies.
   - Deterministic lockfiles (`pnpm-lock.yaml`) ensure immutable dependency trees across development, CI, and production.
3. **Container Image Scanning (Trivy / Grype)**:
   - Scans minimal distroless / alpine container base images for OS package vulnerabilities (CVEs) prior to image registry pushing.

---

## 4. Container Provenance & Image Signing (Cosign)

All production container images are cryptographically signed using **Sigstore Cosign**:
- Keyless signing bound to GitHub Actions OIDC identity.
- Signatures and SBOM attestations are pushed to container registries (AWS ECR / GitHub Packages) alongside the image digest:
  ```bash
  cosign sign --yes ghcr.io/hmslbdn/autoheal-backend:sha256-<digest>
  cosign attest --predicate monitoring/sbom/bom.cyclonedx.json --type cyclonedx ghcr.io/hmslbdn/autoheal-backend:sha256-<digest>
  ```
- Kubernetes admission controllers (e.g., Kyverno / OPA Gatekeeper) enforce image verification: unsigned images cannot be scheduled in production clusters.

---

## 5. Secret Leakage Prevention

Pre-commit hooks and CI gates continuously inspect git diffs using regex pattern engines and entropy analysis:
- Blocks commits containing private keys, RSA headers, API tokens, `.env` files, or webhook secrets.
- Enforces environment variable abstraction (`process.env.NEXT_PUBLIC_*` strictly limited to non-sensitive identifiers).
