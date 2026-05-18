"""PDF hesap özeti üretimi — reportlab ile."""
import logging
from io import BytesIO
from pathlib import Path
from datetime import datetime
from typing import List, Dict
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import mm
from reportlab.lib import colors
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, PageBreak

logger = logging.getLogger(__name__)


def generate_statement_pdf(
    title: str,
    subtitle: str,
    summary_rows: List[Dict],
    detail_rows: List[Dict],
    detail_headers: List[str],
) -> bytes:
    buf = BytesIO()
    doc = SimpleDocTemplate(
        buf, pagesize=A4,
        leftMargin=18*mm, rightMargin=18*mm,
        topMargin=18*mm, bottomMargin=18*mm,
        title=title,
    )
    styles = getSampleStyleSheet()
    h1 = ParagraphStyle("h1", parent=styles["Heading1"], fontName="Helvetica-Bold", fontSize=20, leading=26, textColor=colors.HexColor("#1D1D1F"), spaceAfter=4)
    sub = ParagraphStyle("sub", parent=styles["Normal"], fontName="Helvetica", fontSize=10, leading=14, textColor=colors.HexColor("#86868B"), spaceAfter=18)
    label = ParagraphStyle("label", parent=styles["Normal"], fontName="Helvetica-Bold", fontSize=8, leading=12, textColor=colors.HexColor("#86868B"), spaceAfter=2)
    value = ParagraphStyle("value", parent=styles["Normal"], fontName="Helvetica-Bold", fontSize=14, leading=18, textColor=colors.HexColor("#1D1D1F"), spaceAfter=8)
    body = ParagraphStyle("body", parent=styles["Normal"], fontName="Helvetica", fontSize=9, leading=13)

    flow = []
    flow.append(Paragraph("EY FINANS PLATFORM", ParagraphStyle("brand", fontName="Helvetica-Bold", fontSize=9, textColor=colors.HexColor("#86868B"), spaceAfter=8)))
    flow.append(Paragraph(title, h1))
    flow.append(Paragraph(subtitle, sub))

    # Özet tablosu
    if summary_rows:
        summary_data = [[Paragraph(f"<b>{r['label']}</b>", body), Paragraph(str(r['value']), body)] for r in summary_rows]
        t = Table(summary_data, colWidths=[60*mm, 100*mm])
        t.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#FAFAFA")),
            ("BOX", (0, 0), (-1, -1), 0.5, colors.HexColor("#E5E5EA")),
            ("INNERGRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#E5E5EA")),
            ("LEFTPADDING", (0, 0), (-1, -1), 10),
            ("RIGHTPADDING", (0, 0), (-1, -1), 10),
            ("TOPPADDING", (0, 0), (-1, -1), 8),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
        ]))
        flow.append(t)
        flow.append(Spacer(1, 16))

    # Detay tablosu
    if detail_rows:
        flow.append(Paragraph("<b>Hareket Dökümü</b>", ParagraphStyle("dh", fontName="Helvetica-Bold", fontSize=11, textColor=colors.HexColor("#1D1D1F"), spaceAfter=8)))
        header_cells = [Paragraph(f"<b>{h}</b>", ParagraphStyle("th", fontName="Helvetica-Bold", fontSize=8, textColor=colors.HexColor("#86868B"))) for h in detail_headers]
        data = [header_cells]
        for r in detail_rows:
            row = [Paragraph(str(r.get(h, "")), body) for h in detail_headers]
            data.append(row)
        col_widths = [25*mm, 50*mm, 50*mm, 30*mm, 25*mm][:len(detail_headers)]
        # Eşit dağılım fallback
        if len(col_widths) < len(detail_headers):
            col_widths = [180*mm / len(detail_headers)] * len(detail_headers)
        t = Table(data, colWidths=col_widths, repeatRows=1)
        t.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#FAFAFA")),
            ("BOX", (0, 0), (-1, -1), 0.5, colors.HexColor("#E5E5EA")),
            ("LINEBELOW", (0, 0), (-1, 0), 0.5, colors.HexColor("#E5E5EA")),
            ("LINEBELOW", (0, 1), (-1, -1), 0.25, colors.HexColor("#F5F5F7")),
            ("LEFTPADDING", (0, 0), (-1, -1), 8),
            ("RIGHTPADDING", (0, 0), (-1, -1), 8),
            ("TOPPADDING", (0, 0), (-1, -1), 5),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ]))
        flow.append(t)

    flow.append(Spacer(1, 24))
    flow.append(Paragraph(
        f"<font color='#86868B' size='7'>Oluşturulma: {datetime.now().strftime('%d.%m.%Y %H:%M')} · EY Finans Platform · Otomatik üretilmiştir</font>",
        body
    ))

    doc.build(flow)
    return buf.getvalue()
