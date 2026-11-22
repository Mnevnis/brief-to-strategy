"""Bounded HTTP fetch with ordered URL fallback."""
import hashlib,json,time
from datetime import datetime,timezone
from pathlib import Path
from urllib.error import URLError,HTTPError
from urllib.parse import urlparse
from urllib.request import Request,urlopen
MAX_BYTES=25*1024*1024
def fetch_with_fallback(urls,cache_dir,timeout=20,retries=2):
    cache=Path(cache_dir); cache.mkdir(parents=True,exist_ok=True); last=None
    for i,url in enumerate(urls):
        u=urlparse(url)
        if u.scheme not in {"http","https"} or not u.hostname: last=ValueError("only http(s) URLs are supported"); continue
        for attempt in range(max(0,retries)+1):
            try:
                with urlopen(Request(url,headers={"User-Agent":"brief-to-strategy/1.1"}),timeout=timeout) as r:
                    ctype=r.headers.get("Content-Type",""); data=r.read(MAX_BYTES+1)
                if not data or len(data)>MAX_BYTES: raise ValueError("empty or oversized response")
                key=hashlib.sha1(url.encode()).hexdigest()[:12]; ext=".pdf" if url.lower().endswith(".pdf") or "pdf" in ctype.lower() else ".html"; p=cache/(key+ext); p.write_bytes(data)
                meta={"url":url,"fetched_at":datetime.now(timezone.utc).isoformat(),"sha256":hashlib.sha256(data).hexdigest(),"fallback_used":i>0,"retries":attempt,"bytes":len(data),"content_type":ctype}
                (cache/(key+".meta.json")).write_text(json.dumps(meta,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
                return p,url,i>0
            except (HTTPError,URLError,TimeoutError,OSError,ValueError) as e:
                last=e
                if attempt<retries: time.sleep(min(2**attempt,8))
    if last: print(f"[net_retry] failed: {type(last).__name__}: {last}")
    return None,None,True
