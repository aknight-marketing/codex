from __future__ import annotations

import csv
import json
import logging
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable
from xml.sax.saxutils import escape
from zipfile import ZipFile, ZIP_DEFLATED

logger = logging.getLogger(__name__)

PRICE_RE = re.compile(r"(?:£|GBP\s?)([\d,]+(?:\.\d{2})?)", re.I)
RAM_RE = re.compile(r"(\d{2,3})\s?GB(?:\s+(?:unified\s+)?memory|\s+RAM)?", re.I)
SSD_RE = re.compile(r"((?:\d+(?:\.\d+)?)\s?(?:TB|GB))(?:\s+(?:SSD|Storage|Flash))?", re.I)
SCREEN_RE = re.compile(r"(14(?:\.\d)?|16(?:\.\d)?)\s?(?:-?inch|\")", re.I)
CHIP_RE = re.compile(r"\b(M[234]\s+(?:Pro|Max)|M[234])\b", re.I)
KEYBOARD_RE = re.compile(r"\b(UK|US|QWERTY(?:\s*-?\s*(?:English|UK|US))?)\b", re.I)


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def ensure_dir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)


def parse_price(text: str | None) -> float | None:
    if not text:
        return None
    match = PRICE_RE.search(text.replace("\xa0", " "))
    return float(match.group(1).replace(",", "")) if match else None


def parse_ram_gb(text: str | None) -> int | None:
    if not text:
        return None
    values = [int(m.group(1)) for m in RAM_RE.finditer(text)]
    preferred = [v for v in values if v in {18, 24, 32, 36, 48, 64, 96, 128}]
    return max(preferred or values) if values else None


def parse_ssd_gb(text: str | None) -> int | None:
    if not text:
        return None
    match = re.search(r"((?:\d+(?:\.\d+)?)\s?(?:TB|GB))\s+(?:SSD|Storage|Flash)", text, re.I)
    token = None
    if match:
        token = match.group(1)
    else:
        candidates = re.findall(r"((?:\d+(?:\.\d+)?)\s?(?:TB|GB))", text, re.I)
        storage_like = []
        for candidate in candidates:
            upper = candidate.upper().replace(" ", "")
            if upper.endswith("TB") or int(float(upper[:-2])) >= 256:
                storage_like.append(candidate)
        token = storage_like[-1] if storage_like else None
    if not token:
        return None
    token = token.upper().replace(" ", "")
    return int(float(token[:-2]) * 1024) if token.endswith("TB") else int(float(token[:-2])) if token.endswith("GB") else None


def parse_screen_size(text: str | None) -> float | None:
    match = SCREEN_RE.search(text or "")
    return float(match.group(1)) if match else None


def parse_chip(text: str | None) -> str | None:
    if not text:
        return None
    matches = re.findall(r"\b(M[234](?:\s+(?:Pro|Max))?)\b", text, re.I)
    if not matches:
        return None
    matches = [m.upper().replace("  ", " ") for m in matches]
    matches.sort(key=lambda value: ("MAX" in value, "PRO" in value, len(value)), reverse=True)
    return matches[0]


def parse_keyboard(text: str | None) -> str | None:
    match = KEYBOARD_RE.search(text or "")
    return match.group(1).upper() if match else None


def clean_whitespace(text: str | None) -> str:
    return re.sub(r"\s+", " ", text or "").strip()


def dump_json(path: Path, data: object) -> None:
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")


def dump_csv(path: Path, rows: Iterable[dict]) -> None:
    rows = list(rows)
    if not rows:
        path.write_text("", encoding="utf-8")
        return
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)


def dump_xlsx(path: Path, rows: Iterable[dict]) -> None:
    rows = list(rows)
    headers = list(rows[0].keys()) if rows else []

    def cell_ref(col: int, row: int) -> str:
        label = ""
        n = col
        while n:
            n, rem = divmod(n - 1, 26)
            label = chr(65 + rem) + label
        return f"{label}{row}"

    sheet_rows = []
    if headers:
        sheet_rows.append(headers)
        for row in rows:
            sheet_rows.append([json.dumps(v, ensure_ascii=False) if isinstance(v, (dict, list)) else ("" if v is None else str(v)) for v in row.values()])
    sheet_xml_rows = []
    for r_idx, row in enumerate(sheet_rows, start=1):
        cells = []
        for c_idx, value in enumerate(row, start=1):
            cells.append(f'<c r="{cell_ref(c_idx, r_idx)}" t="inlineStr"><is><t>{escape(str(value))}</t></is></c>')
        sheet_xml_rows.append(f'<row r="{r_idx}">{"".join(cells)}</row>')
    workbook_xml = '<?xml version="1.0" encoding="UTF-8" standalone="yes"?><workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><sheets><sheet name="listings" sheetId="1" r:id="rId1"/></sheets></workbook>'
    rels_xml = '<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet1.xml"/></Relationships>'
    root_rels_xml = '<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/></Relationships>'
    content_types_xml = '<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/><Default Extension="xml" ContentType="application/xml"/><Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/><Override PartName="/xl/worksheets/sheet1.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/></Types>'
    sheet_xml = f'<?xml version="1.0" encoding="UTF-8" standalone="yes"?><worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><sheetData>{"".join(sheet_xml_rows)}</sheetData></worksheet>'
    with ZipFile(path, 'w', ZIP_DEFLATED) as zf:
        zf.writestr('[Content_Types].xml', content_types_xml)
        zf.writestr('_rels/.rels', root_rels_xml)
        zf.writestr('xl/workbook.xml', workbook_xml)
        zf.writestr('xl/_rels/workbook.xml.rels', rels_xml)
        zf.writestr('xl/worksheets/sheet1.xml', sheet_xml)


def configure_logging(verbose: bool = False) -> None:
    logging.basicConfig(level=logging.DEBUG if verbose else logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
