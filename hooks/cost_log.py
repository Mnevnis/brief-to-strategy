#!/usr/bin/env python3
"""Fail-closed budget preflight and idempotent usage ledger."""
import argparse, json, os, sys, tempfile, time
from datetime import datetime, timezone
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path
PRICES={"deepseek-chat":{"in":"0.30","out":"1.20"},"qwen-free":{"in":"0","out":"0"},"claude-sonnet":{"in":"3","out":"15"},"claude-haiku":{"in":"1","out":"5"}}
QUANTUM=Decimal("0.000001")
def budget_path(project):
    if not project or project in {".",".."} or "/" in project or "\\" in project: raise ValueError("invalid project name")
    return Path("projects")/project/"state"/"budget.json"
def acquire_lock(path):
    path.parent.mkdir(parents=True,exist_ok=True); lock_path=path.with_suffix(".lock"); deadline=time.monotonic()+10
    while True:
        try:
            fd=os.open(str(lock_path),os.O_CREAT|os.O_EXCL|os.O_WRONLY,0o600); os.close(fd); return lock_path
        except FileExistsError:
            if time.monotonic()>deadline: raise TimeoutError("budget lock timeout")
            time.sleep(.05)
def release_lock(lock_path):
    try: lock_path.unlink()
    except FileNotFoundError: pass
def load(project):
    path=budget_path(project)
    data=json.loads(path.read_text(encoding="utf-8")) if path.exists() else {"project":project,"limit_usd":5.0,"warn_at_pct":80,"history":[],"prices_per_1m":PRICES}
    data.setdefault("history",[]); data.setdefault("prices_per_1m",PRICES); data.setdefault("limit_usd",5.0); data.setdefault("warn_at_pct",80)
    if not isinstance(data["history"],list) or not isinstance(data["prices_per_1m"],dict): raise ValueError("invalid budget.json structure")
    return data
def amount(value): return Decimal(str(value)).quantize(QUANTUM,rounding=ROUND_HALF_UP)
def estimate(data,model,tokens_in,tokens_out):
    if model not in data["prices_per_1m"]: raise ValueError("unknown model price: "+model)
    price=data["prices_per_1m"][model]
    return amount(Decimal(tokens_in)*Decimal(str(price["in"]))/1000000+Decimal(tokens_out)*Decimal(str(price["out"]))/1000000)
def save(project,data):
    path=budget_path(project)
    data["spent_usd"]=float(sum((Decimal(str(row.get("cost_usd",0))) for row in data["history"]),Decimal(0)).quantize(QUANTUM))
    data["updated_at"]=datetime.now(timezone.utc).isoformat()
    fd,temp_name=tempfile.mkstemp(dir=path.parent,prefix="budget-",suffix=".tmp")
    try:
        with os.fdopen(fd,"w",encoding="utf-8") as stream:
            json.dump(data,stream,ensure_ascii=False,indent=2); stream.write("\n"); stream.flush(); os.fsync(stream.fileno())
        os.replace(temp_name,path)
    finally:
        if os.path.exists(temp_name): os.unlink(temp_name)
def render_report(data):
    runs={}
    for row in data["history"]:
        run=runs.setdefault(row.get("run","run-1"),{"steps":set(),"seconds":0,"cost":Decimal(0),"estimated":0})
        run["steps"].add(row.get("step",0)); run["seconds"]+=int(row.get("sec",0))
        run["cost"]+=Decimal(str(row.get("cost_usd",0))); run["estimated"]+=int(bool(row.get("estimate")))
    lines=["# COSTS — расходы и время","",
        f"Обновлено: {data.get('updated_at') or 'не обновлялось'} · лимит: ${data['limit_usd']} · потрачено: ${data.get('spent_usd',0)}","",
        "Отражены только вызовы, записанные в budget.json. Поиск, страницы, внешние инструменты и ручная доработка учитываются отдельно.","",
        "## Регистрация расходов","",
        "Перед платным вызовом выполните preflight, после него — log с уникальным ID:","",
        "    python hooks/cost_log.py preflight --project <project> --model <model> --tin <input_tokens> --tout <max_output_tokens>",
        "    python hooks/cost_log.py log --project <project> --run <run-id> --step <step> --model <model> --tin <input_tokens> --tout <output_tokens> --sec <seconds> --id <unique-call-id> --estimate",
        "    python hooks/cost_log.py report --project <project>","",
        "Для внешних расходов используйте preflight --reserve-usd <amount>, а после вызова log --actual-usd <amount> с описанием в --action. Человеческое время фиксируйте отдельно в таблице ниже.","",
        "## Итого по прогонам","","| Прогон | Шагов | Время, мин | Время, сек | Стоимость, $ | Estimate-записей |","|---|---:|---:|---:|---:|---:|"]
    for name,run in runs.items():
        lines.append(f"| {name} | {len(run['steps'])} | {run['seconds']/60:.2f} | {run['seconds']} | {run['cost']:.6f} | {run['estimated']} |")
    lines += ["","## По вызовам","","| ID | Прогон | Шаг | Модель | Input | Output | Секунды | USD | Estimate |","|---|---|---:|---|---:|---:|---:|---:|---|"]
    for row in data["history"]:
        lines.append(f"| {row.get('id','')} | {row.get('run','')} | {row.get('step',0)} | {row.get('model','')} | {row.get('tok_in',0)} | {row.get('tok_out',0)} | {row.get('sec',0)} | {row.get('cost_usd',0)} | {bool(row.get('estimate'))} |")
    lines += ["","## Внешние расходы и ручное время","","Заполняется по факту; эти значения не входят в сумму budget.json.","",
        "| Дата | Категория (search / pages / tools / human) | Количество / время | Стоимость, $ | Estimate | Комментарий |","|---|---|---:|---:|---|---|","| — | — | — | — | — | Нет измеренных записей |",
        "","## Методика","","- estimate=true означает расчёт по токенам/тарифной таблице, а не подтверждённый invoice.",
        "- Фактическую стоимость провайдера передавайте через --actual-usd.",
        "- Тарифы в hooks/cost_log.py необходимо сверять с тарифами провайдера.",
        "- Ручное время, поиск и страницы не включаются в стоимость LLM автоматически.",""]
    return "\n".join(lines)
def main():
    parser=argparse.ArgumentParser(); sub=parser.add_subparsers(dest="mode",required=True)
    for mode in ("init","check","report"):
        command=sub.add_parser(mode); command.add_argument("--project",required=True)
    command=sub.add_parser("preflight"); command.add_argument("--project",required=True); command.add_argument("--model",default="deepseek-chat"); command.add_argument("--tin",type=int,default=0); command.add_argument("--tout",type=int,default=0); command.add_argument("--reserve-usd",type=float)
    command=sub.add_parser("log"); command.add_argument("--project",required=True); command.add_argument("--id",required=True); command.add_argument("--model",default="deepseek-chat"); command.add_argument("--tin",type=int,default=0); command.add_argument("--tout",type=int,default=0); command.add_argument("--sec",type=int,default=0); command.add_argument("--step",type=int,default=0); command.add_argument("--run",default="run-1"); command.add_argument("--action",default=""); command.add_argument("--actual-usd",type=float); command.add_argument("--estimate",action="store_true")
    args=parser.parse_args(); data=load(args.project); path=budget_path(args.project)
    if args.mode=="init":
        lock_path=acquire_lock(path)
        try: save(args.project,data)
        finally: release_lock(lock_path)
        return 0
    spent,limit=amount(data.get("spent_usd",0)),amount(data["limit_usd"])
    if args.mode=="check":
        print(f"spent={spent} limit={limit}"); return 2 if spent>=limit else 0
    if args.mode=="preflight":
        if min(args.tin,args.tout)<0: raise ValueError("token counts must be non-negative")
        reserve=amount(args.reserve_usd) if args.reserve_usd is not None else estimate(data,args.model,args.tin,args.tout)
        if reserve<0: raise ValueError("reserve must be non-negative")
        allowed=spent+reserve<limit
        print(f"spent={spent} reserve={reserve} projected={spent+reserve} limit={limit} {'ALLOW' if allowed else 'BLOCK'}")
        return 0 if allowed else 2
    if args.mode=="report":
        Path("COSTS.md").write_text(render_report(data),encoding="utf-8"); print("COSTS.md updated"); return 0
    if min(args.tin,args.tout,args.sec)<0: raise ValueError("usage values must be non-negative")
    if args.actual_usd is not None and args.actual_usd<0: raise ValueError("actual cost must be non-negative")
    lock_path=acquire_lock(path)
    try:
        data=load(args.project)
        if any(row.get("id")==args.id for row in data["history"]):
            print("duplicate action; skipped"); return 0
        cost=amount(args.actual_usd) if args.actual_usd is not None else estimate(data,args.model,args.tin,args.tout)
        data["history"].append({"id":args.id,"ts":datetime.now(timezone.utc).isoformat(),"run":args.run,"step":args.step,"model":args.model,"tok_in":args.tin,"tok_out":args.tout,"sec":args.sec,"cost_usd":float(cost),"action":args.action,"estimate":bool(args.estimate or args.actual_usd is None)})
        save(args.project,data); spent,limit=amount(data["spent_usd"]),amount(data["limit_usd"])
    finally: release_lock(lock_path)
    print(f"logged {args.id}: +{cost}; total={spent}; limit={limit}")
    return 2 if spent>=limit else 0
if __name__=="__main__":
    try: sys.exit(main())
    except (ValueError,TimeoutError,json.JSONDecodeError) as error:
        print("ERROR:",error,file=sys.stderr); sys.exit(2)
