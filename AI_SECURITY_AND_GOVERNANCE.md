# AutoHeal DevOps — AI Security & Governance

## Security Standards & Threat Mitigation

### 1. Prompt Injection Sanitization
Incident titles, log excerpts, and alert labels are treated as untrusted user inputs.
The regex pattern filters adversarial injection attempts prior to prompt interpolation:
```python
PROMPT_INJECTION_PATTERN = re.compile(
    r"(ignore\s+all\s+previous|system\s*:|assistant\s*:|disregard\s+|you\s+are\s+now|override\s+rules)",
    re.IGNORECASE,
)
```
Filtered phrases are replaced with `[FILTERED]`, and inputs are truncated to 500 characters to prevent token exhaustion attacks.

### 2. Multi-Tenant Data Isolation
- Queries for anomalies, forecasts, historical similarity, correlations, and risk scores are strictly scoped to `organization_id`.
- Tenant A cannot query, infer, or observe Tenant B's incident history or model outputs.
- No cross-tenant model training or fine-tuning occurs on customer data.

### 3. Human-in-the-Loop Governance
- AI recommendations are strictly advisory.
- AutoHeal prohibits direct autonomous execution by LLMs.
- Remediation actions must be validated by the Policy Engine and approved by an authorized operator.
- `RECOVERY_SIMULATION_MODE=true` is maintained by default in development and staging environments.

### 4. Synthetic Data Transparency
- Benchmarks and evaluation results evaluated on test corpora are explicitly stamped with `is_synthetic = True`.
- Production reporting clearly distinguishes synthetic test scenarios from verified production telemetry.
