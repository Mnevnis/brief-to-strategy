#!/usr/bin/env python3
"""parse_doc.py — PDF/DOCX/XLSX/CSV -> Markdown + метаданные + проверки качества.

Использование:
    python tools/parse_doc.py input.pdf --url https://... --title "Годовой отчёт"
    python tools/parse_doc.py data.xlsx -o projects/demo/materials/parsed

Выход:
    <имя>.md        — markdown: метаданные, контент, секция "Качество данных"
    <имя>.meta.json — provenance и проверки (машиночитаемо, для claims.jsonl)
"""
import argparse, hashlib, json, re, sys
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

VERSION = "1.0"
MISSING = {"", "-", "—", "–", "н/д", "N/A", "NA", "null", "None", "нет данных", "nan"}
UNITS = {
    "percent": r"%|процент|п\.?\s?п\.?",
    "money":   r"₽|руб|рубл|\$|USD|EUR|€",
    "scale":   r"млн|млрд|тыс|million|billion|thousand",
    "time":    r"дн|мес|месяц|год|лет|сек|мин|day|month|year|hour",
    "people":  r"чел|абонент|пользовател|клиент|user|subscriber|client",
    "data":    r"Гб|Гбайт|Мбит|Mbps|GB|TB",
}
PERIODS = {
    "year":     r"\b(19|20)\d{2}\b",
    "quarter":  r"\b[QК][1-4]\s*['’]?\s*(19|20)?\d{2}\b",
    "date_iso": r"\b\d{4}-\d{2}-\d{2}\b",
    "date_ru":  r"\b\d{1,2}[./]\d{1,2}[./]\d{2,4}\b",
    "month_ru": r"\b(янв|фев|мар|апр|май|июн|июл|авг|сен|окт|ноя|дек)[а-яa-z]*\b",
}
UNIT_RE = re.compile("|".join(UNITS.values()), re.I)


def md_esc(v):
    return str(v).replace("|", "\\|").replace("\n", " ")


def list_to_df(rows):
    rows = [[("" if c is None else str(c).strip()) for c in r]
            for r in rows if r and any(c not in (None, "") for c in r)]
    if not rows:
        return pd.DataFrame()
    header = [h if h else f"col{i+1}" for i, h in enumerate(rows[0])]
    return pd.DataFrame(rows[1:], columns=header)


def df_to_md(df, max_rows):
    df = df.fillna("")
    cols = [md_esc(c) if str(c).strip() else f"col{i+1}" for i, c in enumerate(df.columns)]
    lines = ["| " + " | ".join(cols) + " |", "|" + "---|" * len(cols)]
    for _, row in df.head(max_rows).iterrows():
        lines.append("| " + " | ".join(md_esc(v) for v in row.tolist()) + " |")
    if len(df) > max_rows:
        lines.append(f"| … обрезано: ещё {len(df) - max_rows} строк (см. meta.json) … |")
    return "\n".join(lines)


def check_table(name, df):
    res = {"table": name, "rows": int(len(df)), "cols": int(len(df.columns)),
           "missing": {}, "units": {}, "periods": {}, "warnings": []}
    if df.empty:
        return res
    for col in df.columns:
        s = df[col].astype(str).str.strip()
        miss = int(s.isin(MISSING).sum())
        if miss:
            res["missing"][str(col)] = miss
        vals = str(col) + " " + s[~s.isin(MISSING)].head(100).str.cat(sep=" ")
        res_u = [k for k, p in UNITS.items() if re.search(p, vals, re.I)]
        res_p = [k for k, p in PERIODS.items() if re.search(p, vals, re.I)]
        if res_u:
            res["units"][str(col)] = res_u
        if res_p:
            res["periods"][str(col)] = res_p
        num = pd.to_numeric(s.replace(list(MISSING), pd.NA), errors="coerce")
        if len(s) and num.notna().mean() > 0.5 and not UNIT_RE.search(str(col)):
            res["warnings"].append(f"колонка '{col}': числа без единиц измерения — проверить вручную")
    return res


def parse_pdf(path):
    import pdfplumber
    sections, tables = [], []
    with pdfplumber.open(path) as pdf:
        for i, page in enumerate(pdf.pages, 1):
            body = [(page.extract_text() or "").strip()]
            for j, t in enumerate(page.extract_tables(), 1):
                df = list_to_df(t)
                if not df.empty:
                    body.append(df_to_md(df, MAX_ROWS))
                    tables.append((f"p{i}.table{j}", df))
            sections.append((f"Страница {i}", "\n\n".join(x for x in body if x)))
    return sections, tables


def parse_docx(path):
    from docx import Document
    from docx.table import Table as DTable
    from docx.text.paragraph import Paragraph
    doc = Document(path)
    sections, tables, buf, n = [], [], [], 0
    def flush():
        nonlocal buf
        if buf:
            n_ = len(sections) + 1
            sections.append((f"Блок {n_}", "\n\n".join(buf)))
            buf = []
    for child in doc.element.body.iterchildren():
        if child.tag.endswith("}p"):
            p = Paragraph(child, doc)
            text = p.text.strip()
            if not text:
                continue
            style = (p.style.name or "") if p.style else ""
            m = re.search(r"Heading\s*(\d)", style)
            if style == "Title":
                flush(); sections.append((text, ""))
            elif m:
                flush(); buf.append("#" * min(int(m.group(1)) + 1, 6) + " " + text)
            else:
                buf.append(text)
        elif child.tag.endswith("}tbl"):
            t = DTable(child, doc)
            df = list_to_df([[c.text for c in r.cells] for r in t.rows])
            if not df.empty:
                flush()
                n += 1
                sections.append((f"Таблица {n}", df_to_md(df, MAX_ROWS)))
                tables.append((f"doc.table{n}", df))
    flush()
    return sections, tables


def parse_xlsx(path):
    sheets = pd.read_excel(path, sheet_name=None, dtype=str)
    sections, tables = [], []
    for name, df in sheets.items():
        df.columns = [str(c) for c in df.columns]
        sections.append((f"Лист: {name}", df_to_md(df, MAX_ROWS)))
        tables.append((str(name), df))
    return sections, tables


def parse_csv(path):
    df = None
    for enc in ("utf-8-sig", "cp1251", "utf-8"):
        try:
            df = pd.read_csv(path, dtype=str, encoding=enc)
            break
        except UnicodeDecodeError:
            continue
    if df is None:
        df = pd.read_csv(path, dtype=str, encoding="utf-8", errors="replace")
    df.columns = [str(c) for c in df.columns]
    return [(path.stem, df_to_md(df, MAX_ROWS))], [(path.stem, df)]


def main():
    global MAX_ROWS
    ap = argparse.ArgumentParser(description="PDF/DOCX/XLSX/CSV -> markdown + метаданные")
    ap.add_argument("input")
    ap.add_argument("-o", "--outdir", default=None)
    ap.add_argument("--url", default=None, help="URL источника (provenance)")
    ap.add_argument("--title", default=None)
    ap.add_argument("--max-rows", type=int, default=200)
    a = ap.parse_args()
    MAX_ROWS = a.max_rows

    src = Path(a.input)
    if not src.exists():
        print(f"[parse_doc] ERROR: файл не найден: {src}"); return 1
    outdir = Path(a.outdir) if a.outdir else src.parent
    outdir.mkdir(parents=True, exist_ok=True)

    parsers = {".pdf": parse_pdf, ".docx": parse_docx,
               ".xlsx": parse_xlsx, ".xls": parse_xlsx, ".csv": parse_csv}
    fn = parsers.get(src.suffix.lower())
    if not fn:
        print(f"[parse_doc] ERROR: неподдерживаемый формат: {src.suffix}"); return 2

    try:
        sections, tables = fn(src)
    except Exception as e:
        print(f"[parse_doc] ERROR: {src.name}: {e}"); return 1

    checks = [check_table(n, df) for n, df in tables]
    all_periods = sorted({p for c in checks for p in c["periods"].values() for p in p})
    summary_warnings = [w for c in checks for w in c["warnings"]]
    if len(all_periods) > 1:
        summary_warnings.append(f"смешанные форматы периодов: {', '.join(all_periods)} — сверить сопоставимость")

    meta = {
        "parser": "parse_doc.py", "version": VERSION,
        "parsed_at": datetime.now(timezone.utc).isoformat(),
        "source_file": str(src), "source_url": a.url,
        "title": a.title or src.stem,
        "sha256": hashlib.sha256(src.read_bytes()).hexdigest(),
        "sections": [t for t, _ in sections],
        "tables": checks, "warnings": summary_warnings,
    }

    md = [f"# {meta['title']}", "",
          f"- Источник: `{meta['source_file']}`" + (f" (<{a.url}>)" if a.url else ""),
          f"- Разобрано: {meta['parsed_at']} · sha256: `{meta['sha256'][:12]}…` · парсер v{VERSION}", "", "---", ""]
    for title, body in sections:
        md += [f"## {title}", "", body, ""]
    md += ["---", "", "## Качество данных (автопроверки)", ""]
    if not checks:
        md += ["Таблицы не найдены — проверки не применялись."]
    for c in checks:
        md += [f"- **{c['table']}**: {c['rows']} строк × {c['cols']} колонок"]
        if c["missing"]:
            md += [f"  - пропуски: " + ", ".join(f"{k}: {v}" for k, v in c["missing"].items())]
        if c["units"]:
            md += [f"  - единицы: " + ", ".join(f"{k}: {v}" for k, v in c["units"].items())]
        if c["periods"]:
            md += [f"  - периоды: " + ", ".join(f"{k}: {v}" for k, v in c["periods"].items())]
        for w in c["warnings"]:
            md += [f"  - ⚠ {w}"]
    for w in summary_warnings:
        if w not in [x for c in checks for x in c["warnings"]]:
            md += [f"- ⚠ {w}"]

    out_md = outdir / (src.stem + ".md")
    out_json = outdir / (src.stem + ".meta.json")
    out_md.write_text("\n".join(md), encoding="utf-8")
    out_json.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
    n_warn = len(summary_warnings) + sum(len(c["warnings"]) for c in checks)
    print(f"[parse_doc] OK {out_md}: секций={len(sections)}, таблиц={len(checks)}, предупреждений={n_warn}")
    return 0


if __name__ == "__main__":
    sys.exit(main())