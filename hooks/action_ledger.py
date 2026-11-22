#!/usr/bin/env python3
"""Append-only, lock-protected idempotency ledger for network actions."""
import argparse,json,os,sys,tempfile,time
from datetime import datetime,timezone
from pathlib import Path
def target(p):
    if not p or p in {".",".."} or "/" in p or "\\" in p: raise ValueError("invalid project")
    return Path("projects")/p/"state"/"action_ledger.jsonl"
def events(p):
    if not p.exists(): return []
    out=[]
    for i,line in enumerate(p.read_text(encoding="utf-8").splitlines(),1):
        if line.strip():
            try: out.append(json.loads(line))
            except json.JSONDecodeError as e: raise ValueError(f"invalid ledger line {i}") from e
    return out
def main():
    ap=argparse.ArgumentParser(); ap.add_argument("mode",choices=["check","start","done","fail"]); ap.add_argument("--project",required=True); ap.add_argument("--key",required=True); ap.add_argument("--id"); ap.add_argument("--artifact"); ap.add_argument("--error"); a=ap.parse_args()
    p=target(a.project); rows=events(p); done=any(x.get("key")==a.key and x.get("event")=="done" for x in rows)
    if a.mode=="check": print("completed" if done else "not completed"); return 0 if done else 1
    p.parent.mkdir(parents=True,exist_ok=True); l=p.with_suffix(".lock"); deadline=time.monotonic()+10
    while True:
        try: fd=os.open(str(l),os.O_CREAT|os.O_EXCL|os.O_WRONLY,0o600); os.close(fd); break
        except FileExistsError:
            if time.monotonic()>deadline: raise TimeoutError("ledger lock timeout")
            time.sleep(.05)
    try:
        rows=events(p)
        if a.mode=="done" and any(x.get("key")==a.key and x.get("event")=="done" for x in rows): return 0
        rows.append({"event":a.mode,"key":a.key,"id":a.id,"artifact":a.artifact,"error":a.error,"ts":datetime.now(timezone.utc).isoformat()})
        fd,tmp=tempfile.mkstemp(dir=p.parent,prefix="ledger-",suffix=".tmp")
        try:
            with os.fdopen(fd,"w",encoding="utf-8") as f:
                for x in rows: f.write(json.dumps(x,ensure_ascii=False)+"\n")
                f.flush(); os.fsync(f.fileno())
            os.replace(tmp,p)
        finally:
            if os.path.exists(tmp): os.unlink(tmp)
    finally:
        try: l.unlink()
        except FileNotFoundError: pass
    return 0
if __name__=="__main__":
    try: sys.exit(main())
    except (ValueError,TimeoutError) as e: print("ERROR:",e,file=sys.stderr); sys.exit(2)
