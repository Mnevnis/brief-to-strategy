#!/usr/bin/env python3
"""metrics.py — воспроизводимые расчёты + проверки качества (README §5.3, шаги 4/7).

Режимы:
  check      аудит CSV/XLSX: пропуски, единицы, периоды, дубли, диапазоны дат, даты в будущем
  retention  когортное удержание D1/D7/D30 (или M1/M2/M3 при --period month)
  arpu       выручка / уникальные пользователи по периодам
  funnel     досягаемость стадий и конверсии (шаговая и сквозная)

Выход: projects/<p>/output/metrics/<name>.md + .json
       (sha256 входа, команда, версии, формулы, проверки, предупреждения)
Коды: 0 ok; 2 ошибка схемы/входа; 3 --strict и есть предупреждения (нужна проверка человеком).
"""
import argparse, hashlib, json, re, sys
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

try:
    from parse_doc import MISSING, UNITS, PERIODS
except Exception:
    try:
        from tools.parse_doc import MISSING, UNITS, PERIODS
    except Exception:
        MISSING = {"", "-", "—", "–", "н/д", "N/A", "NA", "null", "None", "нет данных", "nan"}
        UNITS = {"percent": r"%|процент|п\.?\s?п\.?", "money": r"₽|руб|рубл|\$|USD|EUR|€",
                 "scale": r"млн|млрд|тыс|million|billion|thousand",
                 "time": r"дн|мес|месяц|год|лет|сек|мин|day|month|year|hour",
                 "people": r"чел|абонент|пользовател|клиент|user|subscriber|client",
                 "data": r"Гб|Гбайт|Мбит|Mbps|GB|TB"}
        PERIODS = {"year": r"\b(19|20)\d{2}\b", "quarter": r"\b[QК][1-4]\s*['’]?\s*(19|20)?\d{2}\b",
                   "date_iso": r"\b\d{4}-\d{2}-\d{2}\b", "date_ru": r"\b\d{1,2}[./]\d{1,2}[./]\d{2,4}\b",
                   "month_ru": r"\b(янв|фев|мар|апр|май|июн|июл|авг|сен|окт|ноя|дек)[а-яa-z]*\b"}
DATE_COL = re.compile(r"date|day|cohort|period|month|дата|день|период|месяц", re.I)


def _read(path):
    p = Path(path)
    if not p.exists():
        print(f"[metrics] ERROR: файл не найден: {p}"); sys.exit(2)
    if p.suffix.lower() in (".xlsx", ".xls"):
        return pd.read_excel(p, dtype=str)
    for enc in ("utf-8-sig", "cp1251", "utf-8"):
        try:
            return pd.read_csv(p, dtype=str, encoding=enc)
        except UnicodeDecodeError:
            continue
    return pd.read_csv(p, dtype=str, encoding="utf-8", errors="replace")


def md_table(headers, rows):
    return "\n".join(["| " + " | ".join(headers) + " |", "|" + "---|" * len(headers)] +
                     ["| " + " | ".join(str(c) for c in r) + " |" for r in rows])


def audit(df):
    warns, miss, units, periods, ranges = [], {}, {}, {}, {}
    for col in df.columns:
        s = df[col].astype(str).str.strip()
        m = int(s.isin(MISSING).sum())
        if m:
            miss[str(col)] = m
        sample = str(col) + " " + s[~s.isin(MISSING)].head(200).str.cat(sep=" ")
        u = [k for k, pat in UNITS.items() if re.search(pat, sample, re.I)]
        pr = [k for k, pat in PERIODS.items() if re.search(pat, sample, re.I)]
        if u: units[str(col)] = u
        if pr: periods[str(col)] = pr
        if len(pr) > 1:
            warns.append(f"{col}: смешанные форматы периодов {pr} — сверить сопоставимость")
        if DATE_COL.search(str(col)):
            d = pd.to_datetime(s[~s.isin(MISSING)], errors="coerce")
            bad = int(d.isna().sum())
            if bad: warns.append(f"{col}: {bad} дат не распознано")
            if d.notna().any():
                ranges[str(col)] = {"min": str(d.min().date()), "max": str(d.max().date())}
                fut = int((d > pd.Timestamp.today()).sum())
                if fut: warns.append(f"{col}: {fut} дат в будущем")
    dup = int(df.duplicated().sum())
    if dup: warns.append(f"{dup} полных дублей строк")
    if df.empty: warns.append("вход пустой")
    return {"missing": miss, "units": units, "periods": periods,
            "date_ranges": ranges, "duplicates": dup}, warns


def _need(df, cols):
    for c in cols:
        if c not in df.columns:
            print(f"[metrics] ERROR: нет колонки '{c}'. Есть: {list(df.columns)}"); sys.exit(2)


def cmd_retention(df, a, checks):
    _need(df, (a.user, a.cohort, a.date))
    coh = pd.to_datetime(df[a.cohort], errors="coerce")
    act = pd.to_datetime(df[a.date], errors="coerce")
    bad = int((coh.isna() | act.isna()).sum())
    warns = [f"{bad} строк с нераспознанными датами исключены"] if bad else []
    d = df.assign(_coh=coh, _act=act).dropna(subset=["_coh", "_act"])
    n0 = len(d)
    d = d.drop_duplicates(subset=[a.user, a.cohort, a.date])
    if len(d) < n0: warns.append(f"{n0 - len(d)} дублей (user,cohort,date) исключено")
    multi = int((d.groupby(a.user)["_coh"].nunique() > 1).sum())
    if multi: warns.append(f"{multi} пользователей встречаются в нескольких когортах")
    key = d["_coh"].dt.to_period("M").dt.to_timestamp() if a.cohort_gran == "month" else d["_coh"]
    d = d.assign(_key=key)
    if a.period == "day":
        off = (d["_act"] - d["_coh"]).dt.days
        labels, pre = [int(x) for x in a.days.split(",")], "D"
        formula = "retention Dn = уникальные пользователи когорты с активностью ровно на день n / размер когорты; offset считается от индивидуальной cohort_date"
    else:
        off = (d["_act"].dt.year - d["_coh"].dt.year) * 12 + (d["_act"].dt.month - d["_coh"].dt.month)
        labels, pre = [int(x) for x in a.months.split(",")], "M"
        formula = "retention Mn = уникальные пользователи когорты с активностью в месяце n / размер когорты"
    neg = int((off < 0).sum())
    if neg: warns.append(f"{neg} активностей раньше даты когорты исключены")
    d = d.assign(_off=off)[off >= 0]
    sizes = d.groupby("_key")[a.user].nunique()
    rows, payload_cohorts, sums = [], [], {L: 0 for L in labels}
    for k, size in sizes.items():
        rec = {"cohort": str(k.date()), "size": int(size), "active": {}, "retention": {}}
        for L in labels:
            n = int(d[(d["_key"] == k) & (d["_off"] == L)][a.user].nunique())
            rec["active"][f"{pre}{L}"] = n
            rec["retention"][f"{pre}{L}"] = round(n / size, 4) if size else None
            sums[L] += n
        if size < 30: warns.append(f"когорта {k.date()}: size={size} < 30 — оценка неустойчива")
        payload_cohorts.append(rec)
        rows.append([rec["cohort"], rec["size"]] + [rec["retention"][f"{pre}{L}"] for L in labels])
    total = int(sizes.sum())
    overall = {f"{pre}{L}": round(sums[L] / total, 4) if total else None for L in labels}
    rows.append(["ИТОГО (взвеш.)", total] + [overall[f"{pre}{L}"] for L in labels])
    headers = ["cohort", "size"] + [f"{pre}{L}" for L in labels]
    payload = {"formula": formula, "cohort_granularity": a.cohort_gran,
               "cohorts": payload_cohorts, "overall": overall}
    return payload, [("Когортное удержание", md_table(headers, rows)), ("Формула", formula)], warns


def cmd_arpu(df, a, checks):
    _need(df, (a.user, a.period, a.value))
    val = pd.to_numeric(df[a.value].astype(str).str.replace(",", ".", regex=False), errors="coerce")
    bad = int(val.isna().sum())
    warns = [f"{bad} нечисловых значений выручки исключено"] if bad else []
    d = df.assign(_val=val, _per=df[a.period].astype(str).str.strip()).dropna(subset=["_val"])
    neg = int((d["_val"] < 0).sum())
    if neg: warns.append(f"{neg} отрицательных значений выручки")
    if a.value not in checks["units"]:
        warns.append(f"единицы '{a.value}' не подтверждены именем/значениями — уточнить перед выводом")
    pers = d["_per"].unique().tolist()
    tp = pd.to_datetime(pd.Series(pers), errors="coerce")
    if tp.notna().all():
        pers = [p for _, p in sorted(zip(tp, pers))]
    else:
        warns.append("периоды не парсятся как даты — сортировка лексикографическая")
    rows, payload_rows = [], []
    for p in pers:
        g = d[d["_per"] == p]
        users, rev = int(g[a.user].nunique()), float(g["_val"].sum())
        rec = {"period": p, "users": users, "revenue": round(rev, 2),
               "arpu": round(rev / users, 4) if users else None}
        if not users: warns.append(f"период {p}: 0 пользователей")
        payload_rows.append(rec)
        rows.append([p, users, rec["revenue"], rec["arpu"]])
    formula = "ARPU(period) = sum(revenue) / nunique(user_id) за период; валюта/масштаб — из checks.units"
    return {"formula": formula, "periods": payload_rows}, \
           [("ARPU по периодам", md_table(["period", "users", "revenue", "arpu"], rows)), ("Формула", formula)], warns


def cmd_funnel(df, a, checks):
    _need(df, (a.user, a.stage))
    stages = [s.strip() for s in a.stages.split(",")]
    reach, warns = [], []
    for s in stages:
        n = int(df[df[a.stage].astype(str).str.strip() == s][a.user].nunique())
        if n == 0: warns.append(f"стадия '{s}': 0 пользователей")
        reach.append(n)
    rows, payload_rows = [], []
    for i, s in enumerate(stages):
        rec = {"stage": s, "users": reach[i],
               "conv_step": round(reach[i] / reach[i - 1], 4) if i and reach[i - 1] else None,
               "conv_total": round(reach[i] / reach[0], 4) if reach[0] else None}
        payload_rows.append(rec)
        rows.append([s, rec["users"], rec["conv_step"], rec["conv_total"]])
    formula = "reach(stage) = nunique(user_id) со событием стадии; conv_step = reach_i/reach_(i-1); conv_total = reach_i/reach_0 (без требования вложенности)"
    return {"formula": formula, "stages": payload_rows}, \
           [("Воронка", md_table(["stage", "users", "conv_step", "conv_total"], rows)), ("Формула", formula)], warns


def emit(a, payload, tables, checks, warns):
    outdir = Path(a.out) if a.out else Path("projects") / a.project / "output" / "metrics"
    outdir.mkdir(parents=True, exist_ok=True)
    name = a.name or a.cmd
    sha = hashlib.sha256(Path(a.input).read_bytes()).hexdigest()
    meta = {"command": " ".join(sys.argv), "input": str(a.input), "sha256": sha,
            "ts": datetime.now(timezone.utc).isoformat(), "pandas": pd.__version__,
            "python": sys.version.split()[0], "checks": checks, "warnings": warns}
    (outdir / f"{name}.json").write_text(json.dumps({"meta": meta, **payload}, ensure_ascii=False, indent=2), encoding="utf-8")
    md = [f"# Метрика: {name}", "", f"- Вход: `{a.input}` · sha256 `{sha[:12]}…`",
          f"- Команда: `{' '.join(sys.argv)}`", f"- pandas {pd.__version__} / python {meta['python']}",
          f"- Снято: {meta['ts']}", "", "## Проверки качества", "",
          f"- пропуски: {checks['missing'] or 'нет'}", f"- единицы: {checks['units'] or 'не найдены'}",
          f"- периоды: {checks['periods'] or 'не найдены'}", f"- дубли строк: {checks['duplicates']}",
          f"- диапазоны дат: {checks['date_ranges'] or 'нет'}", "", "## Предупреждения", ""]
    md += [f"- ⚠ {w}" for w in warns] or ["- нет"]
    for title, body in tables:
        md += ["", f"## {title}", "", body]
    (outdir / f"{name}.md").write_text("\n".join(md) + "\n", encoding="utf-8")
    print(f"[metrics] OK {name}: warnings={len(warns)} out={outdir / (name + '.md')}")
    if a.strict and warns:
        print("[metrics] STRICT: есть предупреждения — требуется проверка человеком (гейт)")
        return 3
    return 0


def main():
    ap = argparse.ArgumentParser(description="Воспроизводимые метрики + аудит качества")
    sub = ap.add_subparsers(dest="cmd", required=True)
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--project", default="megafon-demo")
    common.add_argument("--out", default=None)
    common.add_argument("--name", default=None)
    common.add_argument("--strict", action="store_true")
    p = sub.add_parser("check", parents=[common]); p.add_argument("input")
    p = sub.add_parser("retention", parents=[common]); p.add_argument("input")
    p.add_argument("--user", default="user_id"); p.add_argument("--cohort", default="cohort_date")
    p.add_argument("--date", default="activity_date"); p.add_argument("--days", default="1,7,30")
    p.add_argument("--months", default="1,2,3"); p.add_argument("--period", choices=["day", "month"], default="day")
    p.add_argument("--cohort-gran", choices=["month", "day"], default="month")
    p = sub.add_parser("arpu", parents=[common]); p.add_argument("input")
    p.add_argument("--user", default="user_id"); p.add_argument("--period", default="period")
    p.add_argument("--value", default="revenue")
    p = sub.add_parser("funnel", parents=[common]); p.add_argument("input")
    p.add_argument("--user", default="user_id"); p.add_argument("--stage", default="stage")
    p.add_argument("--stages", required=True)
    a = ap.parse_args()

    df = _read(a.input)
    checks, warns = audit(df)
    if a.cmd == "check":
        payload = {"rows": int(len(df)), "cols": int(len(df.columns))}
        tables = [("Сводка", f"{len(df)} строк × {len(df.columns)} колонок")]
        extra = []
    elif a.cmd == "retention":
        payload, tables, extra = cmd_retention(df, a, checks)
    elif a.cmd == "arpu":
        payload, tables, extra = cmd_arpu(df, a, checks)
    else:
        payload, tables, extra = cmd_funnel(df, a, checks)
    return emit(a, payload, tables, checks, warns + extra)


if __name__ == "__main__":
    sys.exit(main())