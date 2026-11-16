"""
AutoHeal DevOps — Incident PDF Report Generator (ReportLab)
Generates downloadable, structured incident post-mortem PDF documents.
"""

from datetime import datetime, timezone
import io
from typing import TYPE_CHECKING

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

if TYPE_CHECKING:
    from app.models.incident import Incident


def generate_incident_pdf(incident: "Incident") -> bytes:
    """
    Renders an incident report into binary PDF bytes using ReportLab.
    """
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=letter,
        rightMargin=40,
        leftMargin=40,
        topMargin=40,
        bottomMargin=40,
    )

    styles = getSampleStyleSheet()

    # Custom styles
    primary_color = colors.HexColor("#080b12")
    accent_color = colors.HexColor("#35d6c5")
    dark_gray = colors.HexColor("#334155")
    light_gray = colors.HexColor("#f8fafc")
    border_gray = colors.HexColor("#cbd5e1")

    title_style = ParagraphStyle(
        "DocTitle",
        parent=styles["Heading1"],
        fontName="Helvetica-Bold",
        fontSize=20,
        leading=24,
        textColor=primary_color,
    )
    subtitle_style = ParagraphStyle(
        "DocSubtitle",
        parent=styles["Normal"],
        fontName="Helvetica",
        fontSize=10,
        leading=14,
        textColor=colors.HexColor("#64748b"),
    )
    section_title = ParagraphStyle(
        "SectionHeading",
        parent=styles["Heading2"],
        fontName="Helvetica-Bold",
        fontSize=13,
        leading=17,
        textColor=primary_color,
        spaceBefore=12,
        spaceAfter=6,
    )
    body_style = ParagraphStyle(
        "BodyDark",
        parent=styles["Normal"],
        fontName="Helvetica",
        fontSize=9,
        leading=13,
        textColor=dark_gray,
    )
    body_bold = ParagraphStyle(
        "BodyDarkBold",
        parent=body_style,
        fontName="Helvetica-Bold",
    )
    table_header = ParagraphStyle(
        "TableHeader",
        parent=styles["Normal"],
        fontName="Helvetica-Bold",
        fontSize=9,
        leading=12,
        textColor=colors.white,
    )

    elements = []

    # 1. Header Banner
    elements.append(Paragraph("AUTOHEAL DEVOPS", subtitle_style))
    elements.append(Paragraph(f"Incident Post-Mortem Report: {incident.id}", title_style))
    elements.append(
        Paragraph(
            f"Generated: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')} · Confidential",
            subtitle_style,
        )
    )
    elements.append(Spacer(1, 10))
    elements.append(HRFlowable(width="100%", thickness=2, color=accent_color, spaceBefore=4, spaceAfter=14))

    # 2. Executive Incident Overview Table
    overview_data = [
        [
            Paragraph("Incident ID", body_bold),
            Paragraph(incident.id, body_style),
            Paragraph("Affected Service", body_bold),
            Paragraph(incident.service_name, body_style),
        ],
        [
            Paragraph("Severity", body_bold),
            Paragraph(incident.severity.upper(), body_style),
            Paragraph("Current Status", body_bold),
            Paragraph(incident.status.upper(), body_style),
        ],
        [
            Paragraph("Detected At", body_bold),
            Paragraph(incident.detected_at.strftime("%Y-%m-%d %H:%M:%S UTC"), body_style),
            Paragraph("Resolved At", body_bold),
            Paragraph(
                incident.resolved_at.strftime("%Y-%m-%d %H:%M:%S UTC") if incident.resolved_at else "Unresolved",
                body_style,
            ),
        ],
        [
            Paragraph("Error Rate", body_bold),
            Paragraph(f"{incident.error_rate:.2f}%", body_style),
            Paragraph("Alert Threshold", body_bold),
            Paragraph(f"{incident.threshold:.2f}%", body_style),
        ],
    ]

    overview_table = Table(overview_data, colWidths=[100, 166, 110, 156])
    overview_table.setStyle(
        TableStyle([
            ("BACKGROUND", (0, 0), (-1, -1), light_gray),
            ("BOX", (0, 0), (-1, -1), 1, border_gray),
            ("INNERGRID", (0, 0), (-1, -1), 0.5, border_gray),
            ("TOPPADDING", (0, 0), (-1, -1), 5),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
            ("LEFTPADDING", (0, 0), (-1, -1), 8),
            ("RIGHTPADDING", (0, 0), (-1, -1), 8),
        ])
    )
    elements.append(overview_table)
    elements.append(Spacer(1, 14))

    # 3. Diagnosis & Probable Cause
    elements.append(Paragraph("1. Diagnosis & Root Cause Analysis", section_title))
    diag_data = [
        [Paragraph("Probable Cause", body_bold), Paragraph(incident.probable_cause or "Analysis pending", body_style)],
        [Paragraph("Recommended Action", body_bold), Paragraph(incident.recommended_action or "No action recorded", body_style)],
    ]
    diag_table = Table(diag_data, colWidths=[130, 402])
    diag_table.setStyle(
        TableStyle([
            ("BACKGROUND", (0, 0), (0, -1), colors.HexColor("#f1f5f9")),
            ("BACKGROUND", (1, 0), (1, -1), colors.white),
            ("BOX", (0, 0), (-1, -1), 1, border_gray),
            ("INNERGRID", (0, 0), (-1, -1), 0.5, border_gray),
            ("TOPPADDING", (0, 0), (-1, -1), 6),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
            ("LEFTPADDING", (0, 0), (-1, -1), 8),
            ("RIGHTPADDING", (0, 0), (-1, -1), 8),
        ])
    )
    elements.append(diag_table)
    elements.append(Spacer(1, 14))

    # 4. Correlated Evidence
    elements.append(Paragraph("2. Correlated Diagnostic Evidence", section_title))
    evidence_rows = [
        [
            Paragraph("Kind", table_header),
            Paragraph("Evidence Signal", table_header),
            Paragraph("Detail", table_header),
            Paragraph("Timestamp", table_header),
        ]
    ]

    if incident.evidence:
        for ev in incident.evidence:
            evidence_rows.append([
                Paragraph(ev.kind.upper(), body_bold),
                Paragraph(ev.title, body_style),
                Paragraph(ev.detail, body_style),
                Paragraph(ev.timestamp.strftime("%H:%M:%S"), body_style),
            ])
    else:
        evidence_rows.append([
            Paragraph("—", body_style),
            Paragraph("No evidence items attached", body_style),
            Paragraph("—", body_style),
            Paragraph("—", body_style),
        ])

    ev_table = Table(evidence_rows, colWidths=[80, 160, 212, 80])
    ev_table.setStyle(
        TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), primary_color),
            ("BOX", (0, 0), (-1, -1), 1, border_gray),
            ("INNERGRID", (0, 0), (-1, -1), 0.5, border_gray),
            ("TOPPADDING", (0, 0), (-1, -1), 5),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
            ("LEFTPADDING", (0, 0), (-1, -1), 6),
            ("RIGHTPADDING", (0, 0), (-1, -1), 6),
        ])
    )
    elements.append(ev_table)
    elements.append(Spacer(1, 14))

    # 5. Incident Event Timeline
    elements.append(Paragraph("3. Incident Event Timeline", section_title))
    event_rows = [
        [
            Paragraph("Timestamp", table_header),
            Paragraph("Phase / Event Label", table_header),
            Paragraph("Event Details", table_header),
        ]
    ]

    if incident.events:
        for ev in incident.events:
            event_rows.append([
                Paragraph(ev.timestamp.strftime("%H:%M:%S"), body_style),
                Paragraph(ev.label, body_bold),
                Paragraph(ev.detail, body_style),
            ])
    else:
        event_rows.append([
            Paragraph("—", body_style),
            Paragraph("No timeline events logged", body_style),
            Paragraph("—", body_style),
        ])

    timeline_table = Table(event_rows, colWidths=[90, 160, 282])
    timeline_table.setStyle(
        TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), primary_color),
            ("BOX", (0, 0), (-1, -1), 1, border_gray),
            ("INNERGRID", (0, 0), (-1, -1), 0.5, border_gray),
            ("TOPPADDING", (0, 0), (-1, -1), 5),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
            ("LEFTPADDING", (0, 0), (-1, -1), 6),
            ("RIGHTPADDING", (0, 0), (-1, -1), 6),
        ])
    )
    elements.append(timeline_table)
    elements.append(Spacer(1, 14))

    # 6. Recovery Actions & Outcomes
    elements.append(Paragraph("4. Executed & Pending Recovery Actions", section_title))
    rec_rows = [
        [
            Paragraph("Action ID", table_header),
            Paragraph("Operation", table_header),
            Paragraph("Requested By", table_header),
            Paragraph("Status", table_header),
            Paragraph("Verification", table_header),
        ]
    ]

    if incident.recovery_actions:
        for rec in incident.recovery_actions:
            rec_rows.append([
                Paragraph(rec.id, body_bold),
                Paragraph(rec.action, body_style),
                Paragraph(rec.requested_by, body_style),
                Paragraph(rec.status.upper(), body_style),
                Paragraph(rec.verification.upper(), body_style),
            ])
    else:
        rec_rows.append([
            Paragraph("—", body_style),
            Paragraph("No recovery actions triggered", body_style),
            Paragraph("—", body_style),
            Paragraph("—", body_style),
            Paragraph("—", body_style),
        ])

    rec_table = Table(rec_rows, colWidths=[70, 180, 100, 92, 90])
    rec_table.setStyle(
        TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), primary_color),
            ("BOX", (0, 0), (-1, -1), 1, border_gray),
            ("INNERGRID", (0, 0), (-1, -1), 0.5, border_gray),
            ("TOPPADDING", (0, 0), (-1, -1), 5),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
            ("LEFTPADDING", (0, 0), (-1, -1), 6),
            ("RIGHTPADDING", (0, 0), (-1, -1), 6),
        ])
    )
    elements.append(rec_table)
    elements.append(Spacer(1, 20))

    # 7. Document Footer
    elements.append(HRFlowable(width="100%", thickness=1, color=border_gray, spaceBefore=4, spaceAfter=8))
    elements.append(
        Paragraph(
            "AutoHeal DevOps Autonomous Self-Healing Platform · All operations are policy-gated and cryptographically audited.",
            subtitle_style,
        )
    )

    doc.build(elements)
    return buffer.getvalue()
