"""
core.payslip_pdf
====================
Generates an actual professional-looking payslip PDF with reportlab —
replacing the old QTextEdit.print_(QPrinter) approach, which routed
through the OS print/PDF driver stack (a source of the Windows spooler
crashes mentioned elsewhere in this codebase) and never looked like a
real payslip to begin with.

Layout is deliberately plain-business: single muted accent color,
clear earnings/deductions tables, one prominent net-pay line — the
kind of payslip an HR office actually hands out, not a themed app
screenshot.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Optional

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (
    SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, HRFlowable,
)
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_RIGHT, TA_LEFT, TA_CENTER

# reportlab's standard 14 PDF fonts (Helvetica, Times, Courier) use
# WinAnsi/MacRoman encoding, which does NOT include the Philippine peso
# sign (\u20b1) — it silently renders as a missing-glyph box. DejaVu Sans
# does include it and ships bundled inside matplotlib (already a project
# dependency), so we register that instead of shipping a separate font
# file. Falls back to plain Helvetica + a "PHP" prefix if it's ever
# unavailable, so a missing font never breaks payslip generation.
_UNICODE_FONT = "Helvetica"
_UNICODE_FONT_BOLD = "Helvetica-Bold"
_PESO_GLYPH_OK = False
try:
    import matplotlib
    import os as _os
    _dejavu = _os.path.join(matplotlib.get_data_path(), "fonts", "ttf", "DejaVuSans.ttf")
    _dejavu_bold = _os.path.join(matplotlib.get_data_path(), "fonts", "ttf", "DejaVuSans-Bold.ttf")
    if _os.path.exists(_dejavu) and _os.path.exists(_dejavu_bold):
        pdfmetrics.registerFont(TTFont("DejaVuSans", _dejavu))
        pdfmetrics.registerFont(TTFont("DejaVuSans-Bold", _dejavu_bold))
        _UNICODE_FONT = "DejaVuSans"
        _UNICODE_FONT_BOLD = "DejaVuSans-Bold"
        _PESO_GLYPH_OK = True
except Exception:
    pass

INK = colors.HexColor("#1f2430")
MUTED = colors.HexColor("#6b7280")
ACCENT = colors.HexColor("#1e3a5f")       # deep slate-navy — not the app's neon theme
ACCENT_LIGHT = colors.HexColor("#eaf0f7")
LINE = colors.HexColor("#d7dce3")
NET_BG = colors.HexColor("#eef7ee")
NET_INK = colors.HexColor("#1f6b3a")


def _peso(value) -> str:
    v = value if isinstance(value, Decimal) else Decimal(str(value or 0))
    symbol = "\u20b1" if _PESO_GLYPH_OK else "PHP"
    return f"{symbol} {v:,.2f}"


@dataclass
class PayslipLine:
    label: str
    amount: Decimal


@dataclass
class PayslipData:
    company_name: str
    employee_name: str
    employee_code: str
    department_name: str
    position_title: str
    period_name: str
    pay_date: str
    payroll_status: str
    days_worked: Decimal
    days_absent: Decimal
    days_late: Decimal
    overtime_hours: Decimal
    daily_rate: Decimal
    basic_pay: Decimal
    overtime_pay: Decimal
    gross_pay: Decimal
    earnings: list  # list[PayslipLine] — allowances only (basic/OT shown separately)
    deductions: list  # list[PayslipLine]
    tax_withheld: Decimal
    total_allowances: Decimal
    total_deductions: Decimal
    net_pay: Decimal
    payment_method_label: str
    payment_detail: str
    generated_at: Optional[str] = None


def _styles():
    ss = getSampleStyleSheet()
    return {
        "company": ParagraphStyle("company", parent=ss["Normal"], fontName=_UNICODE_FONT_BOLD,
                                   fontSize=16, textColor=ACCENT, leading=19),
        "doc_title": ParagraphStyle("doc_title", parent=ss["Normal"], fontName=_UNICODE_FONT_BOLD,
                                     fontSize=11, textColor=MUTED, leading=14, alignment=TA_RIGHT),
        "meta": ParagraphStyle("meta", parent=ss["Normal"], fontName=_UNICODE_FONT,
                                fontSize=9, textColor=MUTED, alignment=TA_RIGHT, leading=12),
        "section": ParagraphStyle("section", parent=ss["Normal"], fontName=_UNICODE_FONT_BOLD,
                                   fontSize=10, textColor=ACCENT, spaceBefore=10, spaceAfter=4),
        "label": ParagraphStyle("label", parent=ss["Normal"], fontName=_UNICODE_FONT, fontSize=9, textColor=MUTED),
        "value": ParagraphStyle("value", parent=ss["Normal"], fontName=_UNICODE_FONT_BOLD, fontSize=9.5, textColor=INK),
        "cell": ParagraphStyle("cell", parent=ss["Normal"], fontName=_UNICODE_FONT, fontSize=9.5, textColor=INK),
        "cell_muted": ParagraphStyle("cell_muted", parent=ss["Normal"], fontName=_UNICODE_FONT,
                                      fontSize=9, textColor=MUTED),
        "footer": ParagraphStyle("footer", parent=ss["Normal"], fontName=_UNICODE_FONT, fontSize=7.5,
                                  textColor=MUTED, alignment=TA_CENTER, leading=10),
    }


def generate_payslip_pdf(data: PayslipData, output_path: str) -> str:
    st = _styles()
    doc = SimpleDocTemplate(
        output_path, pagesize=A4,
        leftMargin=20 * mm, rightMargin=20 * mm, topMargin=16 * mm, bottomMargin=16 * mm,
        title=f"Payslip - {data.employee_name} - {data.period_name}",
    )
    story = []

    # ---- Header --------------------------------------------------
    header = Table(
        [[Paragraph(data.company_name, st["company"]),
          Paragraph("PAYSLIP", st["doc_title"])],
         [Paragraph("Official Statement of Earnings & Deductions", st["cell_muted"]),
          Paragraph(f"{data.period_name}<br/>Pay Date: {data.pay_date}", st["meta"])]],
        colWidths=[100 * mm, 70 * mm],
    )
    header.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("BOTTOMPADDING", (0, 0), (-1, 0), 2),
        ("TOPPADDING", (0, 0), (-1, -1), 0),
    ]))
    story.append(header)
    story.append(Spacer(1, 6))
    story.append(HRFlowable(width="100%", thickness=1.4, color=ACCENT))
    story.append(Spacer(1, 10))

    # ---- Employee info block --------------------------------------
    def kv(label, value):
        return [Paragraph(label, st["label"]), Paragraph(str(value), st["value"])]

    info = Table([
        [*kv("Employee", f"{data.employee_name} ({data.employee_code})"),
         *kv("Pay Period", data.period_name)],
        [*kv("Department", data.department_name or "\u2014"),
         *kv("Payment Method", f"{data.payment_method_label} \u2013 {data.payment_detail}")],
        [*kv("Position", data.position_title or "\u2014"),
         *kv("Status", data.payroll_status.title())],
    ], colWidths=[28 * mm, 57 * mm, 32 * mm, 53 * mm])
    info.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ("TOPPADDING", (0, 0), (-1, -1), 0),
    ]))
    story.append(info)
    story.append(Spacer(1, 4))
    story.append(HRFlowable(width="100%", thickness=0.6, color=LINE))
    story.append(Spacer(1, 8))

    # ---- Attendance summary strip ----------------------------------
    att = Table([[
        Paragraph(f"<b>{data.days_worked:g}</b><br/><font size=7.5 color='#6b7280'>Days Worked</font>", st["cell"]),
        Paragraph(f"<b>{data.overtime_hours:g}</b><br/><font size=7.5 color='#6b7280'>OT Hours</font>", st["cell"]),
        Paragraph(f"<b>{data.days_absent:g}</b><br/><font size=7.5 color='#6b7280'>Days Absent</font>", st["cell"]),
        Paragraph(f"<b>{data.days_late:g}</b><br/><font size=7.5 color='#6b7280'>Days Late</font>", st["cell"]),
        Paragraph(f"<b>{_peso(data.daily_rate)}</b><br/><font size=7.5 color='#6b7280'>Daily Rate</font>", st["cell"]),
    ]], colWidths=[34 * mm] * 5)
    att.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), ACCENT_LIGHT),
        ("ALIGN", (0, 0), (-1, -1), "CENTER"),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
        ("ROUNDEDCORNERS", [4, 4, 4, 4]),
    ]))
    story.append(att)
    story.append(Spacer(1, 12))

    # ---- Earnings table ---------------------------------------------
    story.append(Paragraph("EARNINGS", st["section"]))
    earn_rows = [[Paragraph("Description", st["label"]), Paragraph("Amount", st["label"])]]
    earn_rows.append([Paragraph("Basic Pay", st["cell"]), Paragraph(_peso(data.basic_pay), st["cell"])])
    if data.overtime_pay and data.overtime_pay > 0:
        earn_rows.append([Paragraph(f"Overtime Pay ({data.overtime_hours:g} hrs)", st["cell"]),
                           Paragraph(_peso(data.overtime_pay), st["cell"])])
    for line in data.earnings:
        earn_rows.append([Paragraph(line.label, st["cell"]), Paragraph(_peso(line.amount), st["cell"])])
    if not data.earnings:
        pass
    earn_rows.append([Paragraph("<b>Gross Pay</b>", st["value"]),
                       Paragraph(f"<b>{_peso(data.gross_pay + data.total_allowances)}</b>", st["value"])])

    earn_table = Table(earn_rows, colWidths=[110 * mm, 60 * mm])
    style = [
        ("ALIGN", (1, 0), (1, -1), "RIGHT"),
        ("LINEBELOW", (0, 0), (-1, 0), 0.8, ACCENT),
        ("LINEABOVE", (0, -1), (-1, -1), 0.8, LINE),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("BACKGROUND", (0, -1), (-1, -1), ACCENT_LIGHT),
    ]
    earn_table.setStyle(TableStyle(style))
    story.append(earn_table)
    story.append(Spacer(1, 12))

    # ---- Deductions table ---------------------------------------------
    story.append(Paragraph("DEDUCTIONS", st["section"]))
    ded_rows = [[Paragraph("Description", st["label"]), Paragraph("Amount", st["label"])]]
    for line in data.deductions:
        ded_rows.append([Paragraph(line.label, st["cell"]), Paragraph(_peso(line.amount), st["cell"])])
    if data.tax_withheld and data.tax_withheld > 0:
        ded_rows.append([Paragraph("Withholding Tax", st["cell"]), Paragraph(_peso(data.tax_withheld), st["cell"])])
    if len(ded_rows) == 1:
        ded_rows.append([Paragraph("No deductions this period", st["cell_muted"]), Paragraph("\u2014", st["cell_muted"])])
    ded_rows.append([Paragraph("<b>Total Deductions</b>", st["value"]),
                      Paragraph(f"<b>{_peso(data.total_deductions + data.tax_withheld)}</b>", st["value"])])

    ded_table = Table(ded_rows, colWidths=[110 * mm, 60 * mm])
    ded_table.setStyle(TableStyle(style))
    story.append(ded_table)
    story.append(Spacer(1, 14))

    # ---- Net pay banner ---------------------------------------------
    net = Table([[
        Paragraph("NET PAY", ParagraphStyle("netlbl", fontName=_UNICODE_FONT_BOLD, fontSize=11, textColor=NET_INK)),
        Paragraph(_peso(data.net_pay), ParagraphStyle("netval", fontName=_UNICODE_FONT_BOLD, fontSize=16,
                                                        textColor=NET_INK, alignment=TA_RIGHT)),
    ]], colWidths=[110 * mm, 60 * mm])
    net.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), NET_BG),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 10),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 10),
        ("LEFTPADDING", (0, 0), (-1, -1), 10),
        ("RIGHTPADDING", (0, 0), (-1, -1), 10),
        ("BOX", (0, 0), (-1, -1), 0.8, colors.HexColor("#bfe0c8")),
    ]))
    story.append(net)
    story.append(Spacer(1, 18))

    # ---- Footer ---------------------------------------------------
    gen = data.generated_at or datetime.now().strftime("%B %d, %Y %I:%M %p")
    story.append(HRFlowable(width="100%", thickness=0.5, color=LINE))
    story.append(Spacer(1, 6))
    story.append(Paragraph(
        f"This is a system-generated payslip and is valid without a signature. "
        f"Generated on {gen}. For questions about this payslip, please contact your HR/Payroll office. "
        f"This document contains confidential compensation information intended solely for the named employee.",
        st["footer"],
    ))

    doc.build(story)
    return output_path
