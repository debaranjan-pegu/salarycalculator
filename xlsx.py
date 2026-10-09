"""Minimal XLSX writer – standard library only.

Enough of the format to produce a well-formatted single-sheet workbook
(number formats, fonts, fills, borders, alignment, merged cells, column
widths, frozen header). No third-party dependency, so the app stays offline.
"""
from __future__ import annotations

import io
import zipfile
from typing import Any

CONTENT_TYPES = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
<Default Extension="xml" ContentType="application/xml"/>
<Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>
<Override PartName="/xl/worksheets/sheet1.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>
<Override PartName="/xl/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.styles+xml"/>
</Types>"""

ROOT_RELS = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/>
</Relationships>"""

WB_RELS = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet1.xml"/>
<Relationship Id="rId2" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/>
</Relationships>"""

NUM_FMT_ID = 164  # custom: #,##0


def col_letter(n: int) -> str:
    """1-based column index -> 'A', 'B', ... 'AA'."""
    s = ""
    while n > 0:
        n, r = divmod(n - 1, 26)
        s = chr(65 + r) + s
    return s


def _esc(value: Any) -> str:
    return (str(value).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
            .replace('"', "&quot;"))


class _Styles:
    def __init__(self) -> None:
        self.fonts: list[dict] = []
        self.fills: list[str | None] = [None, "gray125"]
        self.borders: list[bool] = [False]
        self.xfs: list[dict] = []
        self._font_ix: dict[tuple, int] = {}
        self._fill_ix: dict[Any, int] = {}

    def font(self, bold=False, size=11, color=None, italic=False) -> int:
        key = (bold, size, color, italic)
        if key not in self._font_ix:
            self._font_ix[key] = len(self.fonts)
            self.fonts.append({"bold": bold, "size": size, "color": color, "italic": italic})
        return self._font_ix[key]

    def fill(self, color) -> int:
        if not color:
            return 0
        if color not in self._fill_ix:
            self._fill_ix[color] = len(self.fills)
            self.fills.append(color)
        return self._fill_ix[color]

    def border(self, on: bool) -> int:
        if on and len(self.borders) < 2:
            self.borders.append(True)
        return 1 if on else 0

    def xf(self, bold=False, size=11, color=None, italic=False, fill=None,
           border=False, num=False, align=None, valign="center", wrap=False) -> int:
        spec = {
            "font": self.font(bold, size, color, italic),
            "fill": self.fill(fill),
            "border": self.border(border),
            "num": num, "align": align, "valign": valign, "wrap": wrap,
        }
        for i, existing in enumerate(self.xfs):
            if existing == spec:
                return i
        self.xfs.append(spec)
        return len(self.xfs) - 1

    # ---- xml -----------------------------------------------------------
    def xml(self) -> str:
        fonts = []
        for f in self.fonts or [{"bold": False, "size": 11, "color": None, "italic": False}]:
            bits = []
            if f["bold"]:
                bits.append("<b/>")
            if f["italic"]:
                bits.append("<i/>")
            bits.append(f'<sz val="{f["size"]}"/>')
            bits.append(f'<color rgb="{_rgb(f["color"] or "000000")}"/>')
            bits.append('<name val="Calibri"/>')
            fonts.append("<font>" + "".join(bits) + "</font>")

        fills = []
        for c in self.fills:
            if c is None:
                fills.append('<fill><patternFill patternType="none"/></fill>')
            elif c == "gray125":
                fills.append('<fill><patternFill patternType="gray125"/></fill>')
            else:
                fills.append('<fill><patternFill patternType="solid">'
                             f'<fgColor rgb="{_rgb(c)}"/><bgColor indexed="64"/>'
                             '</patternFill></fill>')

        borders = []
        for on in self.borders:
            if not on:
                borders.append('<border><left/><right/><top/><bottom/><diagonal/></border>')
            else:
                side = '<color rgb="FFC7CFE0"/>'
                borders.append('<border>'
                               f'<left style="thin">{side}</left>'
                               f'<right style="thin">{side}</right>'
                               f'<top style="thin">{side}</top>'
                               f'<bottom style="thin">{side}</bottom>'
                               '<diagonal/></border>')

        xfs = []
        for x in self.xfs or [{"font": 0, "fill": 0, "border": 0, "num": False,
                               "align": None, "valign": "center", "wrap": False}]:
            attrs = [f'numFmtId="{NUM_FMT_ID if x["num"] else 0}"',
                     f'fontId="{x["font"]}"', f'fillId="{x["fill"]}"', f'borderId="{x["border"]}"',
                     'xfId="0"', 'applyFont="1"', 'applyFill="1"', 'applyBorder="1"']
            if x["num"]:
                attrs.append('applyNumberFormat="1"')
            children = ""
            if x["align"] or x["valign"] or x["wrap"]:
                attrs.append('applyAlignment="1"')
                al = ""
                if x["align"]:
                    al += f' horizontal="{x["align"]}"'
                if x["valign"]:
                    al += f' vertical="{x["valign"]}"'
                if x["wrap"]:
                    al += ' wrapText="1"'
                children = f"<alignment{al}/>"
            if children:
                xfs.append("<xf " + " ".join(attrs) + ">" + children + "</xf>")
            else:
                xfs.append("<xf " + " ".join(attrs) + "/>")

        return ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
                '<styleSheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
                f'<numFmts count="1"><numFmt numFmtId="{NUM_FMT_ID}" formatCode="#,##0"/></numFmts>'
                f'<fonts count="{len(fonts)}">' + "".join(fonts) + '</fonts>'
                f'<fills count="{len(fills)}">' + "".join(fills) + '</fills>'
                f'<borders count="{len(borders)}">' + "".join(borders) + '</borders>'
                '<cellStyleXfs count="1"><xf numFmtId="0" fontId="0" fillId="0" borderId="0"/></cellStyleXfs>'
                f'<cellXfs count="{len(xfs)}">' + "".join(xfs) + '</cellXfs>'
                '<cellStyles count="1"><cellStyle name="Normal" xfId="0" builtinId="0"/></cellStyles>'
                '</styleSheet>')


def _rgb(color: str) -> str:
    color = color.lstrip("#").upper()
    return color if len(color) == 8 else "FF" + color


class Workbook:
    def __init__(self, sheet_name: str = "Sheet1") -> None:
        self.sheet_name = sheet_name
        self.styles = _Styles()
        self.cells: dict[tuple[int, int], tuple[Any, int]] = {}
        self.merges: list[tuple[int, int, int, int]] = []
        self.widths: dict[int, float] = {}
        self.heights: dict[int, float] = {}
        self.freeze_rows: int = 0

    def style(self, **kwargs) -> int:
        return self.styles.xf(**kwargs)

    def cell(self, row: int, col: int, value: Any, style: int = 0) -> None:
        self.cells[(row, col)] = (value, style)

    def merge(self, r1: int, c1: int, r2: int, c2: int) -> None:
        self.merges.append((r1, c1, r2, c2))

    def height(self, row: int, h: float) -> None:
        self.heights[row] = h

    def width(self, col: int, w: float) -> None:
        self.widths[col] = w

    def freeze(self, rows: int) -> None:
        self.freeze_rows = rows

    # ---- parts ---------------------------------------------------------
    def _sheet_xml(self) -> str:
        rows: dict[int, list[tuple[int, Any, int]]] = {}
        for (r, c), (v, s) in self.cells.items():
            rows.setdefault(r, []).append((c, v, s))

        cols_xml = ""
        if self.widths:
            parts = []
            for c in sorted(self.widths):
                parts.append(f'<col min="{c}" max="{c}" width="{self.widths[c]}" customWidth="1"/>')
            cols_xml = "<cols>" + "".join(parts) + "</cols>"

        pane = ""
        if self.freeze_rows:
            pane = (f'<sheetView workbookViewId="0"><pane ySplit="{self.freeze_rows}" '
                    f'topLeftCell="A{self.freeze_rows + 1}" activePane="bottomLeft" state="frozen"/>'
                    '</sheetView>')
        else:
            pane = '<sheetView workbookViewId="0"/>'

        sheet_rows = []
        for r in sorted(rows):
            attrs = f' r="{r}"'
            if r in self.heights:
                attrs += f' ht="{self.heights[r]}" customHeight="1"'
            cells = []
            for c, v, s in sorted(rows[r]):
                ref = f"{col_letter(c)}{r}"
                if v is None or v == "":
                    cells.append(f'<c r="{ref}" s="{s}"/>')
                elif isinstance(v, (int, float)) and not isinstance(v, bool):
                    cells.append(f'<c r="{ref}" s="{s}"><v>{v}</v></c>')
                else:
                    cells.append(f'<c r="{ref}" s="{s}" t="inlineStr">'
                                 f'<is><t xml:space="preserve">{_esc(v)}</t></is></c>')
            sheet_rows.append(f"<row{attrs}>" + "".join(cells) + "</row>")

        merge_xml = ""
        if self.merges:
            refs = "".join(
                f'<mergeCell ref="{col_letter(c1)}{r1}:{col_letter(c2)}{r2}"/>'
                for r1, c1, r2, c2 in self.merges)
            merge_xml = f'<mergeCells count="{len(self.merges)}">{refs}</mergeCells>'

        last_row = max(rows) if rows else 1
        last_col = max((c for (_r, c) in self.cells), default=1)
        return ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
                '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
                f'<dimension ref="A1:{col_letter(last_col)}{last_row}"/>'
                f'<sheetViews>{pane}</sheetViews>'
                '<sheetFormatPr defaultRowHeight="16"/>'
                f'{cols_xml}<sheetData>' + "".join(sheet_rows) + '</sheetData>'
                f'{merge_xml}'
                '<pageMargins left="0.5" right="0.5" top="0.6" bottom="0.6" header="0.3" footer="0.3"/>'
                '</worksheet>')

    def _workbook_xml(self) -> str:
        return ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
                '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" '
                'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
                f'<sheets><sheet name="{_esc(self.sheet_name)}" sheetId="1" r:id="rId1"/></sheets>'
                '</workbook>')

    def to_bytes(self) -> bytes:
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
            z.writestr("[Content_Types].xml", CONTENT_TYPES)
            z.writestr("_rels/.rels", ROOT_RELS)
            z.writestr("xl/workbook.xml", self._workbook_xml())
            z.writestr("xl/_rels/workbook.xml.rels", WB_RELS)
            z.writestr("xl/styles.xml", self.styles.xml())
            z.writestr("xl/worksheets/sheet1.xml", self._sheet_xml())
        return buf.getvalue()
