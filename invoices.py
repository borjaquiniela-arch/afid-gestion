"""Génération de factures PDF en français."""
from __future__ import annotations

from io import BytesIO
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.platypus import (
    Image,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

from database import get_invoice, get_settings

APP_DIR = Path(__file__).resolve().parent
LOGO_PATH = APP_DIR / "static" / "logo.png"

NAVY = colors.HexColor("#1A5F9E")
ACCENT = colors.HexColor("#3AA35A")
LINE = colors.HexColor("#D7D2C8")
SOFT = colors.HexColor("#F4F0EA")
TEXT = colors.HexColor("#1F1B16")
MUTED = colors.HexColor("#6B645C")


def _money(value: float) -> str:
    return f"{value:,.2f}".replace(",", "'") + " CHF"


def _hours(value: float) -> str:
    return f"{value:,.2f}".replace(",", "'") + " h"


def _fmt_tva(rate: float) -> str:
    if abs(rate - round(rate)) < 0.05:
        return f"{rate:.0f} %"
    return f"{rate:.1f} %".replace(".", ",")


def _p(text: str, style: ParagraphStyle) -> Paragraph:
    return Paragraph((text or "").replace("\n", "<br/>"), style)


def build_invoice_pdf(invoice_id: int) -> bytes:
    invoice = get_invoice(invoice_id)
    if not invoice:
        raise ValueError("Facture introuvable")
    settings = get_settings()
    client = invoice["client"]
    franchise = str(settings.get("tva_franchise") or "0") in ("1", "true", "True")
    if str(settings.get("billing_tva") or "").lower() == "sans":
        franchise = True
    if invoice.get("apply_tva") in (0, "0", False):
        franchise = True
    if invoice.get("apply_tva") in (1, "1", True):
        franchise = False

    buf = BytesIO()
    doc = SimpleDocTemplate(
        buf,
        pagesize=A4,
        leftMargin=16 * mm,
        rightMargin=16 * mm,
        topMargin=14 * mm,
        bottomMargin=16 * mm,
        title=f"Facture {invoice['number']}",
        author=settings.get("company_name") or "A-fid comptabilité",
    )

    title_style = ParagraphStyle(
        "title", fontName="Helvetica-Bold", fontSize=22, textColor=NAVY, spaceAfter=0, leading=26
    )
    number_style = ParagraphStyle(
        "number", fontName="Helvetica-Bold", fontSize=12, textColor=ACCENT, spaceBefore=2, spaceAfter=8, leading=16
    )
    label_style = ParagraphStyle(
        "label", fontName="Helvetica", fontSize=8, textColor=MUTED, leading=11
    )
    body_style = ParagraphStyle(
        "body", fontName="Helvetica", fontSize=9.5, textColor=TEXT, leading=13
    )
    bold_style = ParagraphStyle(
        "bold", fontName="Helvetica-Bold", fontSize=9.5, textColor=TEXT, leading=13
    )
    small_style = ParagraphStyle(
        "small", fontName="Helvetica", fontSize=8, textColor=MUTED, leading=11
    )
    th_style = ParagraphStyle(
        "th", fontName="Helvetica-Bold", fontSize=8, textColor=colors.white, leading=11
    )
    td_style = ParagraphStyle(
        "td", fontName="Helvetica", fontSize=8.5, textColor=TEXT, leading=12
    )
    right_style = ParagraphStyle(
        "right", fontName="Helvetica", fontSize=8.5, textColor=TEXT, leading=12, alignment=2
    )
    th_right = ParagraphStyle(
        "th_right", fontName="Helvetica-Bold", fontSize=8, textColor=colors.white, leading=11, alignment=2
    )

    company_lines = [
        settings.get("company_name") or "Votre société",
        settings.get("company_legal_form") or "",
        settings.get("company_address") or "",
        " ".join(
            x
            for x in [
                settings.get("company_postal_code") or "",
                settings.get("company_city") or "",
            ]
            if x
        ),
        settings.get("company_country") or "",
        f"Tél. {settings['company_phone']}" if settings.get("company_phone") else "",
        settings.get("company_email") or "",
        f"SIRET {settings['company_siret']}" if settings.get("company_siret") else "",
        f"N° TVA {settings['company_tva']}" if settings.get("company_tva") else "",
    ]
    company_txt = "<br/>".join([l for l in company_lines if l])

    client_lines = [
        client.get("name") or "",
        client.get("address") or "",
        " ".join(x for x in [client.get("postal_code") or "", client.get("city") or ""] if x),
        client.get("country") or "",
        client.get("email") or "",
        f"SIRET {client['siret']}" if client.get("siret") else "",
        f"N° TVA {client['tva_intra']}" if client.get("tva_intra") else "",
    ]
    client_txt = "<br/>".join([l for l in client_lines if l])

    story = []
    if LOGO_PATH.exists():
        from reportlab.lib.utils import ImageReader
        raw = ImageReader(str(LOGO_PATH))
        iw, ih = raw.getSize()
        logo_width = 70 * mm
        logo_height = logo_width * (ih / float(iw))
        logo_cell = Image(str(LOGO_PATH), width=logo_width, height=logo_height)
        logo_cell.hAlign = "LEFT"
    else:
        logo_cell = _p("A-fid comptabilité", title_style)

    right_block = Table(
        [
            [_p("FACTURE", title_style)],
            [_p(invoice["number"], number_style)],
            [_p("ÉMETTEUR", label_style)],
            [_p(company_txt, body_style)],
        ],
        colWidths=[88 * mm],
    )
    right_block.setStyle(
        TableStyle(
            [
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 4),
                ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                ("TOPPADDING", (0, 0), (-1, 0), 0),
                ("BOTTOMPADDING", (0, 0), (-1, 0), 0),
                ("TOPPADDING", (0, 1), (-1, 1), 2),
                ("BOTTOMPADDING", (0, 1), (-1, 1), 8),
            ]
        )
    )
    header = Table(
        [[logo_cell, right_block]],
        colWidths=[86 * mm, 92 * mm],
    )
    header.setStyle(
        TableStyle(
            [
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 0),
                ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
            ]
        )
    )
    story.append(header)
    story.append(Spacer(1, 8 * mm))

    meta = Table(
        [
            [
                _p("Date d'émission", label_style),
                _p("Date d'échéance", label_style),
                _p("Statut", label_style),
                _p("Client", label_style),
            ],
            [
                _p(_fmt_date(invoice["issue_date"]), body_style),
                _p(_fmt_date(invoice["due_date"]), body_style),
                _p(_status_label(invoice["status"]), bold_style),
                _p(client_txt, body_style),
            ],
        ],
        colWidths=[38 * mm, 38 * mm, 32 * mm, 70 * mm],
    )
    meta.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), SOFT),
                ("BOX", (0, 0), (-1, -1), 0.4, LINE),
                ("INNERGRID", (0, 0), (-1, -1), 0.3, LINE),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 6),
                ("RIGHTPADDING", (0, 0), (-1, -1), 6),
                ("TOPPADDING", (0, 0), (-1, -1), 5),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
            ]
        )
    )
    story.append(meta)
    story.append(Spacer(1, 8 * mm))

    if franchise:
        table_data = [
            [
                _p("Désignation", th_style),
                _p("Date", th_style),
                _p("Quantité", th_right),
                _p("Prix unitaire", th_right),
                _p("Total", th_right),
            ]
        ]
        for line in invoice["lines"]:
            desc = line.get("description") or "Prestation de services"
            table_data.append(
                [
                    _p(desc, td_style),
                    _p(_fmt_date(line["work_date"]), td_style),
                    _p(_hours(line["hours"]), right_style),
                    _p(_money(line["hourly_rate_ht"]), right_style),
                    _p(_money(line["amount_ht"]), right_style),
                ]
            )
        col_w = [78 * mm, 26 * mm, 24 * mm, 26 * mm, 24 * mm]
    else:
        table_data = [
            [
                _p("Désignation", th_style),
                _p("Date", th_style),
                _p("Quantité", th_right),
                _p("Prix unit. HT", th_right),
                _p("TVA", th_right),
                _p("Total HT", th_right),
            ]
        ]
        for line in invoice["lines"]:
            desc = line.get("description") or "Prestation de services"
            table_data.append(
                [
                    _p(desc, td_style),
                    _p(_fmt_date(line["work_date"]), td_style),
                    _p(_hours(line["hours"]), right_style),
                    _p(_money(line["hourly_rate_ht"]), right_style),
                    _p(_fmt_tva(line["tva_rate"]), right_style),
                    _p(_money(line["amount_ht"]), right_style),
                ]
            )
        col_w = [68 * mm, 24 * mm, 22 * mm, 24 * mm, 16 * mm, 24 * mm]
    items = Table(table_data, colWidths=col_w, repeatRows=1)
    items.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), NAVY),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("BACKGROUND", (0, 1), (-1, -1), colors.white),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, SOFT]),
                ("BOX", (0, 0), (-1, -1), 0.4, NAVY),
                ("INNERGRID", (0, 0), (-1, -1), 0.25, LINE),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("LEFTPADDING", (0, 0), (-1, -1), 5),
                ("RIGHTPADDING", (0, 0), (-1, -1), 5),
                ("TOPPADDING", (0, 0), (-1, -1), 5),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
            ]
        )
    )
    story.append(items)
    story.append(Spacer(1, 6 * mm))

    if franchise:
        tva_rows = [["Total", _money(invoice["total_ht"])]]
    else:
        tva_rows = [["Total HT", _money(invoice["total_ht"])]]
        for bucket in invoice["tva_by_rate"]:
            tva_rows.append([f"TVA {_fmt_tva(bucket['rate'])}", _money(bucket["amount"])])
        tva_rows.append(["Total TTC", _money(invoice["total_ttc"])])

    totals = Table(
        [[_p(a, bold_style if "TTC" in a else body_style), _p(b, bold_style if "TTC" in a else body_style)] for a, b in tva_rows],
        colWidths=[40 * mm, 32 * mm],
        hAlign="RIGHT",
    )
    totals.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -2), SOFT),
                ("BACKGROUND", (0, -1), (-1, -1), NAVY),
                ("TEXTCOLOR", (0, -1), (-1, -1), colors.white),
                ("BOX", (0, 0), (-1, -1), 0.4, NAVY),
                ("INNERGRID", (0, 0), (-1, -1), 0.25, LINE),
                ("ALIGN", (1, 0), (1, -1), "RIGHT"),
                ("LEFTPADDING", (0, 0), (-1, -1), 8),
                ("RIGHTPADDING", (0, 0), (-1, -1), 8),
                ("TOPPADDING", (0, 0), (-1, -1), 5),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
            ]
        )
    )
    # Recolor last row paragraphs to white - reportlab paragraphs keep their style.
    # Simpler: rebuild last row with white style
    white_style = ParagraphStyle(
        "white", fontName="Helvetica-Bold", fontSize=10, textColor=colors.white, leading=13, alignment=0
    )
    white_right = ParagraphStyle(
        "white_r", fontName="Helvetica-Bold", fontSize=10, textColor=colors.white, leading=13, alignment=2
    )
    last_label, last_val = tva_rows[-1]
    rebuilt = []
    for i, (a, b) in enumerate(tva_rows):
        if i == len(tva_rows) - 1:
            rebuilt.append([_p(a, white_style), _p(b, white_right)])
        else:
            rebuilt.append([_p(a, body_style), Paragraph(b, right_style)])
    totals = Table(rebuilt, colWidths=[40 * mm, 32 * mm], hAlign="RIGHT")
    totals.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -2), SOFT),
                ("BACKGROUND", (0, -1), (-1, -1), ACCENT),
                ("BOX", (0, 0), (-1, -1), 0.4, LINE),
                ("INNERGRID", (0, 0), (-1, -1), 0.25, LINE),
                ("LEFTPADDING", (0, 0), (-1, -1), 8),
                ("RIGHTPADDING", (0, 0), (-1, -1), 8),
                ("TOPPADDING", (0, 0), (-1, -1), 5),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
            ]
        )
    )
    story.append(totals)
    story.append(Spacer(1, 8 * mm))

    pay_bits = []
    if settings.get("company_iban"):
        pay_bits.append(f"IBAN : {settings['company_iban']}")
    if settings.get("company_bic"):
        pay_bits.append(f"BIC : {settings['company_bic']}")
    pay_bits.append(f"Paiement à {settings.get('payment_days') or '30'} jours.")
    if invoice.get("notes"):
        pay_bits.append(invoice["notes"])

    story.append(_p("CONDITIONS DE RÈGLEMENT", bold_style))
    story.append(_p("<br/>".join(pay_bits), body_style))
    story.append(Spacer(1, 5 * mm))

    mentions = []
    if franchise:
        mentions.append("TVA non applicable.")
    mentions.append(settings.get("invoice_footer") or "")
    story.append(_p("MENTIONS LÉGALES", label_style))
    story.append(_p(" ".join(m for m in mentions if m), small_style))

    def _footer(canvas, doc_):
        canvas.saveState()
        canvas.setStrokeColor(LINE)
        canvas.setLineWidth(0.4)
        canvas.line(16 * mm, 12 * mm, A4[0] - 16 * mm, 12 * mm)
        canvas.setFont("Helvetica", 8)
        canvas.setFillColor(MUTED)
        canvas.drawString(16 * mm, 8 * mm, (settings.get("company_name") or "A-fid comptabilité")[:60])
        canvas.drawRightString(A4[0] - 16 * mm, 8 * mm, f"Page {doc_.page}")
        canvas.restoreState()

    doc.build(story, onFirstPage=_footer, onLaterPages=_footer)
    return buf.getvalue()


def save_invoice_pdf(invoice_id: int, dest: Path | None = None) -> Path:
    invoice = get_invoice(invoice_id)
    data = build_invoice_pdf(invoice_id)
    if dest is None:
        dest = Path(__file__).resolve().parent / "data" / "factures"
        dest.mkdir(parents=True, exist_ok=True)
        dest = dest / f"{invoice['number']}.pdf"
    dest.write_bytes(data)
    return dest


def _fmt_date(iso: str) -> str:
    try:
        y, m, d = iso.split("-")
        return f"{d}/{m}/{y}"
    except Exception:
        return iso


def _status_label(status: str) -> str:
    return {"brouillon": "Brouillon", "emise": "Émise", "payee": "Payée"}.get(status, status)
