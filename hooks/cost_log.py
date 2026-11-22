#!/usr/bin/env python3
"""cost_log.py — токены/время/вызовы -> budget.json -> COSTS.md.
Режимы: init | log | report | check.  Usage: python hooks/cost_log.py log --project megafon-demo --step 2 ...
"""
import argparse, json, sys
from datetime import datetime, timezone
from pathlib import Path

PRICES = {  # $ за 1M токенов; держать в sync с README §6
    "deepseek-chat": {"in": 0.30, "out": 1.20},
    "qwen-free":     {"in": 0.00, "out": 0.00},
    "claude-sonnet": {"in": 3.00, "out": 15.00},
    "claude-haiku":  {"in": 1.00, "out": 5.00},
}

def bpath(p): return Path("projects") / p / "state" / "budget.json"

def load(p):
    f = bpath(p)
    if not f.exists():
        return {"project": p, "limit_usd": 5.0, "warn_at_pct": 80, "spent_usd": 0.0,
                "updated_at": None, "prices_per_1m": PRICES, "history": []}
    return json.loads(f.read_text(encoding="utf-8"))

def save(p, d):
    d["updated_at"] = datetime.now(timezone.utc).isoformat()
    d["spent_usd"] = round(sum(h["cost_usd"] for h in d["history"]), 4)
    bpath(p).parent.mkdir(parents=True, exist_ok=True)
    bpath(p).write_text(json.dumps(d, ensure_ascii=False, indent=2), encoding="utf-8")

def cmd_init(a):
    save(a.project, load(a.project)); print(f"[cost_log] init OK: {bpath(a.project)}"); return 0

def cmd_log(a):
    d = load(a.project)
    if a.id and any(h.get("id") == a.id for h in d["history"]):
        print(f"[cost_log] SKIP: действие {a.id} уже залогировано (идемпотентность)"); return 0
    pr = d.get("prices_per_1m", PRICES).get(a.model, {"in": 0.0, "out": 0.0})
    cost = round(a.tin / 1e6 * pr["in"] + a.tout / 1e6 * pr["out"], 4)
    d["history"].append({"id": a.id, "ts": datetime.now(timezone.utc).isoformat(),
                         "run": a.run, "step": a.step, "model": a.model,
                         "tok_in": a.tin, "tok_out": a.tout, "sec": a.sec,
                         "cost_usd": cost, "action": a.action, "estimate": a.estimate})
    save(a.project, d)
    warn = d["spent_usd"] >= d["limit_usd"] * d["warn_at_pct"] / 100
    print(f"[cost_log] step={a.step} +${cost} | total=${d['spent_usd']}" +
          (" | WARN: достигнут порог — эскалация к человеку (AGENTS §0.5)" if warn else ""))
    return 0

def cmd_check(a):
    d = load(a.project)
    over = d["spent_usd"] > d["limit_usd"]
    print(f"[cost_log] check: spent=${d['spent_usd']} limit=${d['limit_usd']} -> {'OVER' if over else 'ok'}")
    return 1 if over else 0

def cmd_report(a):
    d = load(a.project)
    runs = {}
    for h in d["history"]:
        r = runs.setdefault(h["run"], {"steps": set(), "tin": 0, "tout": 0, "sec": 0, "cost": 0.0, "est": 0})
        r["steps"].add(h["step"]); r["tin"] += h["tok_in"]; r["tout"] += h["tok_out"]
        r["sec"] += h["sec"]; r["cost"] += h["cost_usd"]; r["est"] += 1 if h.get("estimate") else 0
    lines = ["# COSTS.md — измеренная стоимость и время", "",
             f"Обновлено: {d['updated_at']} · лимит: ${d['limit_usd']} · потрачено: ${d['spent_usd']}", "",
             "## Итого по прогонам", "",
             "| run | шагов | токены in/out | время, мин | стоимость $ | estimate-записей |",
             "|---|---|---|---|---|---|"]
    for name, r in runs.items():
        lines.append(f"| {name} | {len(r['steps'])} | {r['tin']}/{r['tout']} | {round(r['sec']/60,1)} | {round(r['cost'],4)} | {r['est']} |")
    lines += ["", "## По шагам", "", "| run | шаг | действие | модель | tok in/out | сек | $ |", "|---|---|---|---|---|---|---|"]
    for h in d["history"]:
        lines.append(f"| {h['run']} | {h['step']} | {h['action']} | {h['model']} | {h['tok_in']}/{h['tok_out']} | {h['sec']} | {h['cost_usd']} |")
    lines += ["", "## Заметки", "- estimate=true — оценка токенов (среда не отдала usage), не точный учёт.",
              "- Правки человека: <заполнить вручную>.", "- Цены моделей: hooks/cost_log.py PRICES, сверено с README §6."]
    Path("COSTS.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"[cost_log] report OK: COSTS.md ({len(d['history'])} записей, ${d['spent_usd']})"); return 0

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("mode", choices=["init", "log", "report", "check"])
    ap.add_argument("--project", required=True)
    ap.add_argument("--step", type=int, default=0)
    ap.add_argument("--model", default="deepseek-chat")
    ap.add_argument("--tin", type=int, default=0); ap.add_argument("--tout", type=int, default=0)
    ap.add_argument("--sec", type=int, default=0)
    ap.add_argument("--action", default=""); ap.add_argument("--run", default="demo-1")
    ap.add_argument("--id", default=None); ap.add_argument("--estimate", action="store_true")
    a = ap.parse_args()
    return {"init": cmd_init, "log": cmd_log, "report": cmd_report, "check": cmd_check}[a.mode](a)

if __name__ == "__main__":
    sys.exit(main())