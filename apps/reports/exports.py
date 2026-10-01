"""Generate complete filtered downloads from the same projections as the API."""

from decimal import Decimal
from io import BytesIO
from math import ceil
from xml.sax.saxutils import escape

from openpyxl import Workbook
from openpyxl.cell import WriteOnlyCell
from openpyxl.styles import Alignment, Font
from openpyxl.utils import get_column_letter
from reportlab.lib import colors
from reportlab.lib.enums import TA_RIGHT
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.platypus import LongTable, Paragraph, SimpleDocTemplate, Spacer, TableStyle

from apps.core.exceptions import ServiceError

from .definitions import EXPORT_ROW_LIMIT
from .selectors import report_columns, report_rows


def _xlsx(sections):
    workbook = Workbook(write_only=True)
    for key, section in sections.items():
        summary = section["summary"]
        sheet = workbook.create_sheet(summary["title"][:31])
        columns = report_columns(key)
        sheet.freeze_panes = "A2"
        widths = [
            40
            if column["key"] == "customer"
            else (24 if column["kind"] == "text" else 18)
            for column in columns
        ]
        for index, width in enumerate(widths, 1):
            sheet.column_dimensions[get_column_letter(index)].width = width
        headers = []
        for column in columns:
            cell = WriteOnlyCell(sheet, value=column["label"])
            cell.font = Font(bold=True)
            headers.append(cell)
        sheet.append(headers)
        for row_number, row in enumerate(
            report_rows(key, section["queryset"].iterator(chunk_size=500)),
            2,
        ):
            sheet.row_dimensions[row_number].height = 15 * max(
                ceil(len(str(row[column["key"]])) / width)
                for column, width in zip(columns, widths, strict=True)
            )
            cells = []
            for column in columns:
                value = row[column["key"]]
                cell = WriteOnlyCell(sheet, value=value)
                cell.alignment = Alignment(wrap_text=True, vertical="top")
                if column["kind"] == "money":
                    cell.value = float(value)
                    cell.number_format = "#,##0.00"
                elif isinstance(value, str):
                    cell.data_type = "s"
                cells.append(cell)
            sheet.append(cells)
    output = BytesIO()
    workbook.save(output)
    return output.getvalue()


def _pdf(sections):
    output = BytesIO()
    document = SimpleDocTemplate(
        output,
        pagesize=landscape(A4),
        leftMargin=28,
        rightMargin=28,
        topMargin=28,
        bottomMargin=28,
    )
    styles = getSampleStyleSheet()
    styles["BodyText"].fontSize = 8
    styles["BodyText"].leading = 10
    story = []
    money_style = ParagraphStyle(
        "ReportMoney", parent=styles["BodyText"], alignment=TA_RIGHT
    )
    section_title_style = ParagraphStyle(
        "ReportSectionTitle", parent=styles["BodyText"], fontName="Helvetica-Bold"
    )
    for key, section in sections.items():
        summary = section["summary"]
        columns = report_columns(key)
        data = [
            [Paragraph(escape(summary["title"]), section_title_style)]
            + [""] * (len(columns) - 1),
            [Paragraph(escape(column["label"]), styles["BodyText"]) for column in columns]
        ]
        for row in report_rows(key, section["queryset"].iterator(chunk_size=500)):
            data.append(
                [
                    Paragraph(escape(f"{Decimal(row[column['key']]):,.2f}"), money_style)
                    if column["kind"] == "money"
                    else Paragraph(escape(str(row[column["key"]])), styles["BodyText"])
                    for column in columns
                ]
            )
        table = LongTable(
            data,
            colWidths=[document.width / len(columns)] * len(columns),
            repeatRows=2,
        )
        table.setStyle(
            TableStyle(
                [
                    ("SPAN", (0, 0), (-1, 0)),
                    ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#f1f5f9")),
                    ("BACKGROUND", (0, 1), (-1, 1), colors.HexColor("#e7eef0")),
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                    ("GRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#ccd5d8")),
                    ("TOPPADDING", (0, 0), (-1, -1), 5),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
                ]
            )
        )
        story.append(table)
        story.append(Spacer(1, 12))
    document.build(story)
    return output.getvalue()


def export_report(report: dict, sections: dict, *, file_type: str) -> bytes:
    """Reject oversized results before fetching rows; downloads never truncate."""
    if (
        sum(section["summary"]["count"] for section in sections.values())
        > EXPORT_ROW_LIMIT
    ):
        raise ServiceError(
            f"Exports allow at most {EXPORT_ROW_LIMIT:,} rows. Narrow the report filters."
        )
    return _xlsx(sections) if file_type == "xlsx" else _pdf(sections)
