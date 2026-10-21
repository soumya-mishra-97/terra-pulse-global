"""Server-side PDF rendering with ReportLab (platypus).

Cover page, clickable table of contents with PDF bookmarks, numbered section headings, metric
tables that split across pages with repeated headers, line/bar charts, citation labels next to
claims, page numbers and footer metadata. A Unicode TrueType font is used when available.
"""

from __future__ import annotations

import io
import logging
import os
import re
from xml.sax.saxutils import escape

from reportlab.graphics.charts.barcharts import VerticalBarChart
from reportlab.graphics.charts.legends import Legend
from reportlab.graphics.charts.lineplots import LinePlot
from reportlab.graphics.shapes import Drawing, String
from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (
    BaseDocTemplate,
    Frame,
    KeepTogether,
    PageBreak,
    PageTemplate,
    Paragraph,
    Spacer,
    Table,
    TableStyle,
)
from reportlab.platypus.tableofcontents import TableOfContents

INK = colors.HexColor("#111418")
MUTED = colors.HexColor("#5a616d")
ACCENT_HEX = "#1f6feb"
ACCENT = colors.HexColor(ACCENT_HEX)
ACCENT_2 = colors.HexColor("#c8611f")
LINE = colors.HexColor("#dde1e7")
SERIES_COLORS = [ACCENT, ACCENT_2, colors.HexColor("#0f8a7c"), colors.HexColor("#6b7380")]

FONT_CANDIDATES = [
    os.environ.get("PDF_FONT_PATH", ""),
    "/usr/share/fonts/truetype/liberation/LiberationSerif-Regular.ttf",  # metric-compatible with Times New Roman
    "/usr/share/fonts/truetype/dejavu/DejaVuSerif.ttf",
    "/System/Library/Fonts/Supplemental/Times New Roman.ttf",
]
BOLD_CANDIDATES = [
    os.environ.get("PDF_FONT_BOLD_PATH", ""),
    "/usr/share/fonts/truetype/liberation/LiberationSerif-Bold.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSerif-Bold.ttf",
    "/System/Library/Fonts/Supplemental/Times New Roman Bold.ttf",
]
BUILTIN_FONT = "Times-Roman"
_FONTS: tuple[str, str] | None = None


def _fonts() -> tuple[str, str]:
    """Register a Unicode serif font once; fall back to built-in Times (Latin-1) if none is installed."""
    global _FONTS
    if _FONTS:
        return _FONTS
    regular = next((p for p in FONT_CANDIDATES if p and os.path.isfile(p)), None)
    bold = next((p for p in BOLD_CANDIDATES if p and os.path.isfile(p)), None)
    if regular:
        try:
            pdfmetrics.registerFont(TTFont("TPSerif", regular))
            pdfmetrics.registerFont(TTFont("TPSerif-Bold", bold or regular))
            _FONTS = ("TPSerif", "TPSerif-Bold")
            return _FONTS
        except Exception:  # corrupt/unsupported font file: fall back to built-in Times
            logging.getLogger(__name__).warning("could not register PDF font", extra={"font": regular})
    _FONTS = (BUILTIN_FONT, "Times-Bold")
    return _FONTS


def _safe(text: object) -> str:
    """Escape for ReportLab mini-markup; drop characters built-in Times cannot draw when no TTF is present."""
    s = escape(str(text if text is not None else ""))
    if _fonts()[0] == BUILTIN_FONT:
        s = s.encode("latin-1", "replace").decode("latin-1")
    return s


def _cite_markup(text: str) -> str:
    """Escape text and render citation labels like [F3] in the accent colour."""
    return re.sub(r"\[((?:[FDS]\d+(?:, )?)+)\]", rf'<font color="{ACCENT_HEX}" size="7">[\1]</font>', _safe(text))


class _Doc(BaseDocTemplate):
    def __init__(self, buf, meta: dict, **kw):
        super().__init__(buf, pagesize=A4, leftMargin=18 * mm, rightMargin=18 * mm, topMargin=18 * mm,
                         bottomMargin=20 * mm, title=meta["title"], author="TerraPulse Global AI",
                         subject=meta["subject"], creator="TerraPulse Global AI (ReportLab)", **kw)
        self.meta = meta
        frame = Frame(self.leftMargin, self.bottomMargin, self.width, self.height, id="body")
        self.addPageTemplates([PageTemplate(id="cover", frames=[frame], onPage=self._cover_page),
                               PageTemplate(id="body", frames=[frame], onPage=self._body_page)])

    def _cover_page(self, canvas, doc):
        canvas.saveState()
        canvas.setFillColor(INK)
        canvas.rect(0, A4[1] - 70 * mm, A4[0], 70 * mm, fill=1, stroke=0)
        canvas.setFillColor(ACCENT)
        canvas.rect(0, A4[1] - 72 * mm, A4[0], 2 * mm, fill=1, stroke=0)
        canvas.restoreState()

    def _body_page(self, canvas, doc):
        regular, _ = _fonts()
        canvas.saveState()
        canvas.setStrokeColor(LINE)
        canvas.line(self.leftMargin, 14 * mm, A4[0] - self.rightMargin, 14 * mm)
        canvas.setFont(regular, 7.5)
        canvas.setFillColor(MUTED)
        canvas.drawString(self.leftMargin, 9 * mm, _plain(self.meta["footer"]))
        canvas.drawRightString(A4[0] - self.rightMargin, 9 * mm, f"Page {doc.page}")
        canvas.restoreState()

    def afterFlowable(self, flowable):
        if isinstance(flowable, Paragraph) and getattr(flowable, "_bookmark", None):
            key, level, text = flowable._bookmark
            self.canv.bookmarkPage(key)
            self.canv.addOutlineEntry(text, key, level=level, closed=False)
            self.notify("TOCEntry", (level, text, self.page, key))


def _plain(text: str) -> str:
    return text if _fonts()[0] != BUILTIN_FONT else text.encode("latin-1", "replace").decode("latin-1")


def _styles():
    regular, bold = _fonts()
    base = getSampleStyleSheet()
    return {
        "cover_title": ParagraphStyle("ct", parent=base["Title"], fontName=bold, fontSize=24, leading=30,
                                      textColor=colors.white, alignment=TA_LEFT),
        "cover_sub": ParagraphStyle("cs", fontName=regular, fontSize=11, leading=15, textColor=colors.HexColor("#c9ced6")),
        "h1": ParagraphStyle("h1", fontName=bold, fontSize=15, leading=19, textColor=INK, spaceBefore=10, spaceAfter=6),
        "h2": ParagraphStyle("h2", fontName=bold, fontSize=11, leading=14, textColor=INK, spaceBefore=8, spaceAfter=4),
        "body": ParagraphStyle("body", fontName=regular, fontSize=9.5, leading=13.5, textColor=INK, spaceAfter=4),
        "bullet": ParagraphStyle("bullet", fontName=regular, fontSize=9.5, leading=13.5, textColor=INK, leftIndent=10,
                                 bulletIndent=0, spaceAfter=3),
        "small": ParagraphStyle("small", fontName=regular, fontSize=8, leading=11, textColor=MUTED, spaceAfter=3),
        "cell": ParagraphStyle("cell", fontName=regular, fontSize=8, leading=10, textColor=INK),
        "cell_b": ParagraphStyle("cellb", fontName=bold, fontSize=8, leading=10, textColor=colors.white),
        "badge": ParagraphStyle("badge", fontName=bold, fontSize=8, leading=10, textColor=ACCENT),
        "toc1": ParagraphStyle("toc1", fontName=regular, fontSize=10, leading=15, textColor=INK, leftIndent=6),
    }


def _heading(text: str, style, key: str, level: int = 0) -> Paragraph:
    p = Paragraph(_safe(text), style)
    p._bookmark = (key, level, _plain(text))
    return p


def _table(columns: list[str], rows: list[list[str]], st, col_widths=None) -> Table:
    data = [[Paragraph(_safe(c), st["cell_b"]) for c in columns]]
    data += [[Paragraph(_cite_markup(str(x)), st["cell"]) for x in row] for row in rows]
    t = Table(data, colWidths=col_widths, repeatRows=1, hAlign="LEFT")
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), INK),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f2f4f7")]),
        ("LINEBELOW", (0, 0), (-1, -1), 0.25, LINE),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 4), ("RIGHTPADDING", (0, 0), (-1, -1), 4),
        ("TOPPADDING", (0, 0), (-1, -1), 3), ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
    ]))
    return t


def _line_chart(chart: dict, width: float) -> Drawing | None:
    series = [s for s in chart.get("series", []) if len(s.get("points", [])) >= 2]
    if not series:
        return None
    regular, bold = _fonts()
    h = 62 * mm
    d = Drawing(width, h)
    lp = LinePlot()
    lp.x, lp.y, lp.width, lp.height = 38, 28, width - 60, h - 52
    lp.data = [[(p["year"], p["value"]) for p in s["points"]] for s in series]
    for i in range(len(series)):
        lp.lines[i].strokeColor = SERIES_COLORS[i % len(SERIES_COLORS)]
        lp.lines[i].strokeWidth = 1.6
    lp.xValueAxis.labelTextFormat = "%d"
    lp.xValueAxis.labels.fontName = regular
    lp.xValueAxis.labels.fontSize = 7
    lp.yValueAxis.labels.fontName = regular
    lp.yValueAxis.labels.fontSize = 7
    vals = [p["value"] for s in series for p in s["points"]]
    big = max(abs(v) for v in vals) >= 1e6
    lp.yValueAxis.labelTextFormat = (lambda v: f"{v / 1e6:,.0f}M") if big else (lambda v: f"{v:,.1f}")
    lp.xValueAxis.strokeColor = lp.yValueAxis.strokeColor = LINE
    d.add(lp)
    d.add(String(0, h - 10, _plain(chart.get("title", "")), fontName=bold, fontSize=8.5, fillColor=INK))
    if len(series) > 1:
        lg = Legend()
        lg.x, lg.y = width - 150, h - 6
        lg.fontName, lg.fontSize = regular, 7
        lg.alignment = "right"
        lg.columnMaximum = 1
        lg.colorNamePairs = [(SERIES_COLORS[i % len(SERIES_COLORS)], _plain(s["name"])) for i, s in enumerate(series)]
        d.add(lg)
    return d


def _bar_chart(chart: dict, width: float) -> Drawing | None:
    series = chart.get("series", [])
    if not series:
        return None
    regular, bold = _fonts()
    h = 58 * mm
    d = Drawing(width, h)
    bc = VerticalBarChart()
    bc.x, bc.y, bc.width, bc.height = 44, 26, width - 60, h - 46
    bc.data = [[s["value"] for s in series]]
    bc.categoryAxis.categoryNames = [_plain(str(s["name"]))[:10] for s in series]
    bc.categoryAxis.labels.fontName = regular
    bc.categoryAxis.labels.fontSize = 6.5
    bc.categoryAxis.labels.angle = 30 if len(series) > 6 else 0
    bc.categoryAxis.labels.dy = -6 if len(series) > 6 else 0
    bc.valueAxis.labels.fontName = regular
    bc.valueAxis.labels.fontSize = 7
    big = max(abs(s["value"]) for s in series) >= 1e6
    bc.valueAxis.labelTextFormat = (lambda v: f"{v / 1e6:,.1f}M") if big else (lambda v: f"{v:,.0f}")
    bc.bars[0].fillColor = ACCENT
    bc.bars[0].strokeColor = None
    d.add(bc)
    d.add(String(0, h - 10, _plain(chart.get("title", "")), fontName=bold, fontSize=8.5, fillColor=INK))
    return d


def render_pdf(content: dict) -> bytes:
    st = _styles()
    c = content["country"]
    prov = content.get("provenance") or {}
    buf = io.BytesIO()
    footer = (f"TerraPulse Global AI · {c['name']} ({c['iso3']}) · data ref. {content.get('data_reference_date')} · "
              f"generated {content['generated_at'][:19].replace('T', ' ')} UTC · source [S1] "
              f"{prov.get('publisher', '')} {prov.get('release_version', '')}")
    doc = _Doc(buf, {"title": content["title"], "subject": f"Demographic intelligence report for {c['name']}",
                     "footer": footer})
    width = doc.width
    story: list = []

    # Cover
    story += [Spacer(1, 12 * mm), Paragraph(_safe(f"{c['iso3']} · COUNTRY INTELLIGENCE REPORT"), st["cover_sub"]),
              Spacer(1, 3 * mm), Paragraph(_safe(c["name"]), st["cover_title"]),
              Paragraph(_safe(f"{content['period']['label']} · {content['period']['start_year']}–"
                              f"{content['period']['end_year']}"), st["cover_sub"]), Spacer(1, 40 * mm)]
    meta_rows = [
        ["Country", f"{c['name']} ({c['iso3']})"],
        ["Region / income group", f"{c.get('region') or 'Data unavailable'} / {c.get('income_level') or 'Data unavailable'}"],
        ["Reporting period", f"{content['period']['label']} ({content['period']['start_year']}–{content['period']['end_year']})"],
        ["Data reference date", str(content.get("data_reference_date") or "Data unavailable")],
        ["Generated", content["generated_at"].replace("T", " ") + " UTC"],
        ["Primary source [S1]", f"{prov.get('dataset_name')} — {prov.get('publisher')}, release {prov.get('release_version')}"],
        ["Licence", str(prov.get("license"))],
        ["Narrative mode", f"{content.get('mode')}" + (f" ({content.get('model')})" if content.get("model") else
                                                        " (deterministic text; no LLM)")],
        ["Validation", str((content.get("validation") or {}).get("status"))],
    ]
    story.append(_table(["Report metadata", ""], meta_rows, st, [55 * mm, width - 55 * mm]))
    story += [Spacer(1, 6 * mm), Paragraph("<b>Disclaimer.</b> " + _safe(content["disclaimer"]), st["small"])]
    if prov.get("is_synthetic"):
        story.append(Paragraph("<b>DEMO DATA:</b> this report uses synthetic values that are not real statistics.",
                               st["badge"]))
    story.append(PageBreak())

    # Table of contents
    from reportlab.platypus.doctemplate import NextPageTemplate

    story.insert(0, NextPageTemplate("body"))
    toc = TableOfContents()
    toc.levelStyles = [st["toc1"]]
    toc.dotsMinLevel = 0
    story += [Paragraph("Contents", st["h1"]), toc, PageBreak()]

    for s in content["sections"]:
        key = f"sec-{s['number']}"
        block = [_heading(f"{s['number']}. {s['title']}", st["h1"], key)]
        if s["status"] != "ok":
            block.append(Paragraph(_safe(f"Status: {s['status']}"), st["badge"]))
        story += block
        if s.get("narrative"):
            story.append(Paragraph(_cite_markup(s["narrative"]), st["body"]))
            story.append(Paragraph("AI-generated explanation, validated against the figures in this section.", st["small"]))
        for p in s.get("summary_points", []):
            story.append(Paragraph(_cite_markup(p), st["bullet"], bulletText="•"))
        for p in s.get("implications", []):
            story.append(Paragraph(_cite_markup(p), st["bullet"], bulletText="→"))
        if s.get("metrics"):
            rows = [[m["label"], m["value"], m["kind"] + (f" [{m['fact_id']}]" if m.get("fact_id") else "")]
                    for m in s["metrics"]]
            story += [Spacer(1, 2 * mm), _table(["Metric", "Value", "Basis"], rows, st,
                                                [width * 0.48, width * 0.32, width * 0.20])]
        ch = s.get("chart")
        if ch:
            drawing = _line_chart(ch, width) if ch["type"] == "line" else _bar_chart(ch, width)
            if drawing:
                story += [Spacer(1, 3 * mm), KeepTogether([drawing])]
        t = s.get("table")
        if t and t.get("rows"):
            n = len(t["columns"])
            first = width * (0.16 if n > 2 else 0.3)
            story += [Spacer(1, 3 * mm), _table(t["columns"], t["rows"], st,
                                                [first] + [(width - first) / (n - 1)] * (n - 1))]
        for u in s.get("unavailable", []):
            story.append(Paragraph(f"<b>Data unavailable:</b> {_safe(u)}", st["small"]))
        for n in s.get("notes", []):
            story.append(Paragraph(f"Note: {_safe(n)}", st["small"]))
        if s.get("citations"):
            story.append(Paragraph("Sources: " + ", ".join(f"[{_safe(x)}]" for x in s["citations"]), st["small"]))
        story.append(Spacer(1, 4 * mm))

    story += [PageBreak(), _heading("References", st["h1"], "references")]
    for src in content.get("sources", []):
        story.append(Paragraph(f"<b>[{_safe(src['label'])}]</b> {_safe(src['title'])}. {_safe(src.get('publisher'))}. "
                               f"{_safe(src.get('published'))}. {_safe(src.get('reference') or '')} "
                               f"<font color='{ACCENT_HEX}'>{_safe(src.get('url'))}</font>", st["body"]))
    story.append(_heading("Limitations", st["h2"], "limitations", level=0))
    for x in content.get("limitations", []):
        story.append(Paragraph(_safe(x), st["bullet"], bulletText="•"))
    v = content.get("validation") or {}
    story.append(_heading("Validation checks", st["h2"], "validation", level=0))
    rows = [[ch["name"], "pass" if ch["passed"] else ch["severity"], ch["detail"]] for ch in v.get("checks", [])]
    if rows:
        story.append(_table(["Check", "Result", "Detail"], rows, st, [width * 0.28, width * 0.14, width * 0.58]))

    doc.multiBuild(story)
    return buf.getvalue()
