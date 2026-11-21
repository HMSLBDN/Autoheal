"""
AutoHeal DevOps — Phase 14 Research & Benchmark Report Generator
Generates publication-ready PDF and JSON research evaluation reports.
"""

from datetime import datetime, timezone
import io
import json
from typing import Any, Dict

from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.platypus import (
    HRFlowable,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

from app.models.experiment import Experiment
from app.services.experiment.comparator import build_experiment_analytics


def generate_experiment_json_report(experiment: Experiment) -> Dict[str, Any]:
    """Builds a structured JSON research evaluation report."""
    analytics = build_experiment_analytics(experiment)
    runs_data = []
    for r in experiment.runs or []:
        runs_data.append({
            "run_number": r.run_number,
            "seed": r.seed,
            "status": r.status,
            "detection_latency_ms": r.detection_latency_ms,
            "recovery_duration_ms": r.recovery_duration_ms,
            "total_outage_duration_ms": r.total_outage_duration_ms,
            "recovery_attempted": r.recovery_attempted,
            "recovery_verified": r.recovery_verified,
            "recovery_success": r.recovery_success,
            "is_false_positive": r.is_false_positive,
            "safety_compliant": r.safety_compliant,
            "escalated": r.escalated,
            "incident_id": r.incident_id,
            "recovery_action_id": r.recovery_action_id,
            "evidence_classification": r.evidence_classification,
        })

    return {
        "report_metadata": {
            "title": f"AutoHeal DevOps Empirical Benchmark Report: {experiment.name}",
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "framework_version": "AutoHeal DevOps v14.0",
            "evidence_classification": "SIMULATED",
            "safety_mode": "RECOVERY_SIMULATION_MODE=true",
        },
        "experiment": {
            "id": experiment.id,
            "name": experiment.name,
            "description": experiment.description,
            "scenario_type": experiment.scenario_type,
            "recovery_enabled": experiment.recovery_enabled,
            "target_service_id": experiment.target_service_id,
            "number_of_runs": experiment.number_of_runs,
            "random_seed": experiment.random_seed,
            "status": experiment.status,
            "started_at": experiment.started_at.isoformat() if experiment.started_at else None,
            "completed_at": experiment.completed_at.isoformat() if experiment.completed_at else None,
        },
        "aggregate_analytics": analytics.model_dump(),
        "runs": runs_data,
        "methodology": {
            "description": "Deterministic multi-run evaluation using pseudorandom seed pinning.",
            "safety_constraints": [
                "Strict simulation mode (RECOVERY_SIMULATION_MODE=true).",
                "Zero host or container socket exposure.",
                "Policy allowlist verification prior to recovery simulation.",
                "Cryptographic state machine gating on incident resolution.",
            ],
            "limitations": [
                "Simulated latencies reflect controlled distribution models rather than production noisy neighbors.",
                "Sample sizes under N=5 are flagged as preliminary trends.",
            ],
        },
    }


def generate_experiment_pdf_report(experiment: Experiment) -> bytes:
    """Renders a PDF research benchmark report using ReportLab."""
    analytics = build_experiment_analytics(experiment)

    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=letter,
        rightMargin=36,
        leftMargin=36,
        topMargin=36,
        bottomMargin=36,
    )

    styles = getSampleStyleSheet()
    primary_color = colors.HexColor("#0f172a")
    cyan_accent = colors.HexColor("#06b6d4")
    slate_dark = colors.HexColor("#334155")
    slate_light = colors.HexColor("#f8fafc")
    border_color = colors.HexColor("#cbd5e1")

    title_style = ParagraphStyle(
        "ExpTitle",
        parent=styles["Heading1"],
        fontName="Helvetica-Bold",
        fontSize=18,
        leading=22,
        textColor=primary_color,
    )
    subtitle_style = ParagraphStyle(
        "ExpSubtitle",
        parent=styles["Normal"],
        fontName="Helvetica",
        fontSize=9,
        leading=13,
        textColor=colors.HexColor("#64748b"),
    )
    section_style = ParagraphStyle(
        "ExpSection",
        parent=styles["Heading2"],
        fontName="Helvetica-Bold",
        fontSize=12,
        leading=16,
        textColor=primary_color,
        spaceBefore=12,
        spaceAfter=6,
    )
    body_style = ParagraphStyle(
        "ExpBody",
        parent=styles["Normal"],
        fontName="Helvetica",
        fontSize=8.5,
        leading=12,
        textColor=slate_dark,
    )
    body_bold = ParagraphStyle(
        "ExpBodyBold",
        parent=body_style,
        fontName="Helvetica-Bold",
    )
    th_style = ParagraphStyle(
        "ExpTH",
        parent=styles["Normal"],
        fontName="Helvetica-Bold",
        fontSize=8.5,
        leading=11,
        textColor=colors.white,
    )

    elements = []

    # 1. Header
    elements.append(Paragraph("AUTOHEAL DEVOPS · BENCHMARK & EVALUATION FRAMEWORK", subtitle_style))
    elements.append(Paragraph(f"Empirical Evaluation: {experiment.name}", title_style))
    elements.append(
        Paragraph(
            f"Experiment ID: {experiment.id} · Generated: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')} · Status: {experiment.status.upper()}",
            subtitle_style,
        )
    )
    elements.append(Spacer(1, 8))
    elements.append(HRFlowable(width="100%", thickness=2, color=cyan_accent, spaceBefore=2, spaceAfter=10))

    # 2. Executive Overview Table
    meta_table_data = [
        [
            Paragraph("Scenario Type", body_bold),
            Paragraph(experiment.scenario_type.replace("_", " ").title(), body_style),
            Paragraph("Target Service", body_bold),
            Paragraph(experiment.target_service_id, body_style),
        ],
        [
            Paragraph("Autonomous Recovery", body_bold),
            Paragraph("ENABLED" if experiment.recovery_enabled else "DISABLED (Control)", body_style),
            Paragraph("Execution Mode", body_bold),
            Paragraph("SIMULATED (Safe Simulation Lock)", body_style),
        ],
        [
            Paragraph("Number of Runs", body_bold),
            Paragraph(str(experiment.number_of_runs), body_style),
            Paragraph("Random Seed", body_bold),
            Paragraph(str(experiment.random_seed), body_style),
        ],
        [
            Paragraph("Recovery Success Rate", body_bold),
            Paragraph(f"{analytics.recovery_success_rate:.1f}%", body_style),
            Paragraph("Safety Compliance", body_bold),
            Paragraph(f"{analytics.safety_compliance_rate:.1f}%", body_style),
        ],
    ]
    meta_table = Table(meta_table_data, colWidths=[120, 150, 120, 150])
    meta_table.setStyle(
        TableStyle([
            ("BACKGROUND", (0, 0), (-1, -1), slate_light),
            ("BOX", (0, 0), (-1, -1), 1, border_color),
            ("INNERGRID", (0, 0), (-1, -1), 0.5, border_color),
            ("TOPPADDING", (0, 0), (-1, -1), 4),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
            ("LEFTPADDING", (0, 0), (-1, -1), 6),
            ("RIGHTPADDING", (0, 0), (-1, -1), 6),
        ])
    )
    elements.append(meta_table)
    elements.append(Spacer(1, 10))

    # 3. Statistical Metric Distributions
    elements.append(Paragraph("1. Aggregated Performance Metrics", section_style))
    dist_headers = [
        Paragraph("Metric", th_style),
        Paragraph("Mean", th_style),
        Paragraph("Median", th_style),
        Paragraph("Min", th_style),
        Paragraph("Max", th_style),
        Paragraph("Std Dev", th_style),
        Paragraph("P95", th_style),
        Paragraph("Sample N", th_style),
    ]

    def fmt_val(v, unit="ms"):
        return f"{v:,.1f} {unit}" if v is not None else "N/A"

    dist_rows = [dist_headers]
    for label, m in [
        ("Detection Latency", analytics.detection_latency),
        ("Recovery Duration", analytics.recovery_duration),
        ("Total Outage Duration", analytics.total_outage_duration),
    ]:
        dist_rows.append([
            Paragraph(label, body_bold),
            Paragraph(fmt_val(m.mean), body_style),
            Paragraph(fmt_val(m.median), body_style),
            Paragraph(fmt_val(m.min), body_style),
            Paragraph(fmt_val(m.max), body_style),
            Paragraph(fmt_val(m.std_dev), body_style),
            Paragraph(fmt_val(m.p95), body_style),
            Paragraph(str(m.sample_count), body_style),
        ])

    metrics_table = Table(dist_rows, colWidths=[120, 60, 60, 55, 55, 60, 65, 65])
    metrics_table.setStyle(
        TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), primary_color),
            ("BOX", (0, 0), (-1, -1), 1, border_color),
            ("INNERGRID", (0, 0), (-1, -1), 0.5, border_color),
            ("TOPPADDING", (0, 0), (-1, -1), 4),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
            ("LEFTPADDING", (0, 0), (-1, -1), 5),
            ("RIGHTPADDING", (0, 0), (-1, -1), 5),
        ])
    )
    elements.append(metrics_table)
    elements.append(Spacer(1, 10))

    # 4. Multi-Run Individual Records
    elements.append(Paragraph("2. Individual Seed-Isolated Run Breakdown", section_style))
    run_headers = [
        Paragraph("Run #", th_style),
        Paragraph("Seed", th_style),
        Paragraph("Detection", th_style),
        Paragraph("Recovery", th_style),
        Paragraph("Outage", th_style),
        Paragraph("Attempted", th_style),
        Paragraph("Verified", th_style),
        Paragraph("Safety", th_style),
    ]
    run_rows = [run_headers]
    for r in experiment.runs or []:
        run_rows.append([
            Paragraph(f"Run {r.run_number}", body_bold),
            Paragraph(str(r.seed), body_style),
            Paragraph(fmt_val(r.detection_latency_ms), body_style),
            Paragraph(fmt_val(r.recovery_duration_ms), body_style),
            Paragraph(fmt_val(r.total_outage_duration_ms), body_style),
            Paragraph("Yes" if r.recovery_attempted else "No", body_style),
            Paragraph("Passed" if r.recovery_verified and r.recovery_success else ("Failed" if r.recovery_attempted else "N/A"), body_style),
            Paragraph("Compliant" if r.safety_compliant else "VIOLATION", body_style),
        ])

    run_table = Table(run_rows, colWidths=[50, 55, 75, 75, 85, 65, 65, 70])
    run_table.setStyle(
        TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), primary_color),
            ("BOX", (0, 0), (-1, -1), 1, border_color),
            ("INNERGRID", (0, 0), (-1, -1), 0.5, border_color),
            ("TOPPADDING", (0, 0), (-1, -1), 3),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
            ("LEFTPADDING", (0, 0), (-1, -1), 4),
            ("RIGHTPADDING", (0, 0), (-1, -1), 4),
        ])
    )
    elements.append(run_table)
    elements.append(Spacer(1, 12))

    # 5. Methodology & Scientific Limitations
    elements.append(Paragraph("3. Scientific Methodology & Safety Boundaries", section_style))
    method_text = (
        "<b>Reproducibility:</b> All trials utilize deterministic pseudo-random seeds (seed = base_seed + run_number). "
        "<b>Safety Isolation:</b> RECOVERY_SIMULATION_MODE=true is strictly enforced; no container sockets, shell execution, "
        "or live production infrastructure was manipulated during evaluation.<br/>"
    )
    if analytics.sample_size_warning:
        method_text += f"<br/><font color='#dc2626'><b>Statistical Caution:</b> {analytics.sample_size_warning}</font>"
    elements.append(Paragraph(method_text, body_style))
    elements.append(Spacer(1, 14))

    # Footer
    elements.append(HRFlowable(width="100%", thickness=1, color=border_color, spaceBefore=2, spaceAfter=6))
    elements.append(
        Paragraph(
            "AutoHeal DevOps Autonomous Self-Healing Research Platform · Evidence Classification: SIMULATED / MEASURED",
            subtitle_style,
        )
    )

    doc.build(elements)
    return buffer.getvalue()
