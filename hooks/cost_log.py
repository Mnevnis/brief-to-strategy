#!/usr/bin/env python3
"""Fail-closed budget preflight and idempotent usage ledger."""
import argparse,json,os,sys,tempfile,time
from datetime import datetime,timezone
from decimal import Decimal,ROUND_HALF_UP
from pathlib import Path
PRICES={"deepseek-chat":{"in":"0.30","out":"1.20"},"qwen-free":{"in":"0","out":"0"},"claude-sonnet":{"in":"3","out":"15"},"claude-haiku":{"in":"1","out":"5"}}
Q=Decimal("0.000001")
def path(p):
    if not p or p in {".",".."} or "/" in p or "\\" in p: raise ValueError("invalid project name")
    return Path("projects")/p/"state"/"budget.json"
def lock(p):
    p.parent.mkdir(parents=True,exist_ok=True); l=p.with_suffix(".lock"); end=time.monotonic()+10
    while True:
        try: fd=os.open(str(l),os.O_CREAT|os.O_EXCL|os.O_WRONLY,0o600); os.close(fd); return l
        except FileExistsError:
            if time.monotonic()>end: raise TimeoutError("budget lock timeout")
            time.sleep(.05)
def unlock(l):
    try:l.unlink()
    except FileNotFoundError:pass
def load(project):
    p=path(project); d=json.loads(p.read_text(encoding="utf-8")) if p.exists() else {"project":project,"limit_usd":5.0,"warn_at_pct":80,"history":[],"prices_per_1m":PRICES}
    d.setdefault("history",[]); d.setdefault("prices_per_1m",PRICES); d.setdefault("limit_usd",5.0); d.setdefault("warn_at_pct",80)
    if not isinstance(d["history"],list): raise ValueError("history must be a list")
    return d
def amount(v):return Decimal(str(v)).quantize(Q,rounding=ROUND_HALF_UP)
def estimate(d,model,ti,to):
    if model not in d["prices_per_1m"]: raise ValueError("unknown model price: "+model)
    p=d["prices_per_1m"][model]
    return amount(Decimal(ti)*Decimal(str(p["in"]))/1000000+Decimal(to)*Decimal(str(p["out"]))/1000000)
def save(project,d):
    p=path(project); d["spent_usd"]=float(sum((Decimal(str(x.get("cost_usd",0))) for x in d["history"]),Decimal(0)).quantize(Q)); d["updated_at"]=datetime.now(timezone.utc).isoformat()
    fd,tmp=tempfile.mkstemp(dir=p.parent,prefix="budget-",suffix=".tmp")
    try:
        with os.fdopen(fd,"w",encoding="utf-8") as f: json.dump(d,f,ensure_ascii=False,indent=2); f.write("\n"); f.flush(); os.fsync(f.fileno())
        os.replace(tmp,p)
    finally:
        if os.path.exists(tmp): os.unlink(tmp)
def main():
    ap=argparse.ArgumentParser(); sp=ap.add_subparsers(dest="mode",required=True)
    for m in ("init","check","report"):
        q=sp.add_parser(m); q.add_argument("--project",required=True)
    q=sp.add_parser("preflight"); q.add_argument("--project",required=True); q.add_argument("--model",default="deepseek-chat"); q.add_argument("--tin",type=int,default=0); q.add_argument("--tout",type=int,default=0); q.add_argument("--reserve-usd",type=float)
    q=sp.add_parser("log"); q.add_argument("--project",required=True); q.add_argument("--id",required=True); q.add_argument("--model",default="deepseek-chat"); q.add_argument("--tin",type=int,default=0); q.add_argument("--tout",type=int,default=0); q.add_argument("--sec",type=int,default=0); q.add_argument("--step",type=int,default=0); q.add_argument("--run",default="run-1"); q.add_argument("--action",default=""); q.add_argument("--actual-usd",type=float); q.add_argument("--estimate",action="store_true")
    a=ap.parse_args(); d=load(a.project); p=path(a.project)
    if a.mode=="init":
        l=lock(p)
        try: save(a.project,d)
        finally: unlock(l)
        return 0
    spent=amount(d.get("spent_usd",0)); limit=amount(d["limit_usd"])
    if a.mode=="check":
        print(f"spent={spent} limit={limit}"); return 2 if spent>=limit else 0
    if a.mode=="preflight":
        reserve=amount(a.reserve_usd) if a.reserve_usd is not None else estimate(d,a.model,a.tin,a.tout)
        ok=spent+reserve<limit; print(f"spent={spent} reserve={reserve} projected={spent+reserve} limit={limit} {'ALLOW' if ok else 'BLOCK'}"); return 0 if ok else 2
    if a.mode=="report":
        rows=["# COSTS — recorded usage","",f"Updated: {d.get('updated_at') or 'not updated'} | limit: ${d['limit_usd']} | spent: ${d.get('spent_usd',0)}","","Only calls explicitly recorded by cost_log.py are included. Search, tools, invoices and human time must be tracked separately.","","| ID | Run | Step | Model | Input | Output | Seconds | USD | Estimated |","|---|---|---:|---|---:|---:|---:|---:|---|"]
        for h in d["history"]:
            rows.append(f"| {h.get('id','')} | {h.get('run','')} | {h.get('step',0)} | {h.get('model','')} | {h.get('tok_in',0)} | {h.get('tok_out',0)} | {h.get('sec',0)} | {h.get('cost_usd',0)} | {bool(h.get('estimate'))} |")
        Path("COSTS.md").write_text("\\n".join(rows)+"\\n",encoding="utf-8")
        print("COSTS.md updated"); return 0
    if min(a.tin,a.tout,a.sec)<0: raise ValueError("usage values must be non-negative")
    l=lock(p)
    try:
        d=load(a.project)
        if any(x.get("id")==a.id for x in d["history"]): print("duplicate action; skipped"); return 0
        cost=amount(a.actual_usd) if a.actual_usd is not None else estimate(d,a.model,a.tin,a.tout)
        d["history"].append({"id":a.id,"ts":datetime.now(timezone.utc).isoformat(),"run":a.run,"step":a.step,"model":a.model,"tok_in":a.tin,"tok_out":a.tout,"sec":a.sec,"cost_usd":float(cost),"action":a.action,"estimate":bool(a.estimate or a.actual_usd is None)})
        save(a.project,d); spent=amount(d["spent_usd"]); limit=amount(d["limit_usd"])
    finally: unlock(l)
    print(f"logged {a.id}: +{cost}; total={spent}; limit={limit}")
    return 2 if spent>=limit else 0
if __name__=="__main__":
    try: sys.exit(main())
    except (ValueError,TimeoutError,json.JSONDecodeError) as e: print("ERROR:",e,file=sys.stderr); sys.exit(2)
