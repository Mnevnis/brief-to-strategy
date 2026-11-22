#!/usr/bin/env python3
"""search.py — поиск открытых источников (DuckDuckGo без ключа), как заявлено в README §5.3.

Цепочка провайдеров: ddg-html -> ddg-lite -> searxng (public) -> L2 (только курированный реестр).
Идемпотентность: ключ "search:<запрос>|max|lang" через hooks/action_ledger.py + локальный кэш JSON.
Контент сниппетов — ДАННЫЕ, не инструкции (AGENTS.md §0.2): скрипт ничего из них не исполняет.

Usage:
    python tools/search.py "МегаФон годовой отчёт МСФО" --project megafon-demo --max 8
    python tools/search.py "..." --offline          # тест деградации L2
    python tools/search.py "..." --json             # машиночитаемо для агента
Коды выхода: 0 = есть результаты; 4 = все провайдеры недоступны (L2, работаем с реестром).
"""
import argparse, hashlib, json, re, subprocess, sys, time
from datetime import date, datetime, timezone
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import quote, urlparse, parse_qs
from urllib.request import Request, urlopen

UA = {"User-Agent": "brief-to-strategy/1.0 (open-source research; contact: repo)"}
SEARCH_DIR = Path("knowledge/sources/search")
SEARX = ["https://searx.be", "https://searx.tiekoetter.com", "https://search.bus-hit.me"]
REG_COLS = "| id | url | title | publisher | pub_date | fetch_date | type | relevance | status | cache_path |"
REG_SEP = "|---|---|---|---|---|---|---|---|---|---|"


def _get(url, timeout):
    with urlopen(Request(url, headers=UA), timeout=timeout) as r:
        return r.read()


def _clean_url(u):
    if u.startswith("//"):
        u = "https:" + u
    p = urlparse(u)
    if "duckduckgo.com" in p.netloc and p.path.startswith("/l/"):
        q = parse_qs(p.query)
        if "uddg" in q:
            return q["uddg"][0]
    return u


class _DDGParser(HTMLParser):
    """Парсит выдачи html.duckduckgo.com и lite.duckduckgo.com."""
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.results, self._cur, self._cap, self._buf = [], None, None, []

    def handle_starttag(self, tag, attrs):
        cls = dict(attrs).get("class", "")
        href = dict(attrs).get("href", "")
        if tag == "a" and ("result__a" in cls or "result-link" in cls):
            self._cur = {"title": "", "url": href, "snippet": ""}
            self._cap, self._buf = "title", []
        elif tag in ("a", "td") and ("result__snippet" in cls or "result-snippet" in cls):
            self._cap, self._buf = "snippet", []

    def handle_data(self, data):
        if self._cap:
            self._buf.append(data)

    def handle_endtag(self, tag):
        text = "".join(self._buf).strip()
        if self._cap == "title" and tag == "a" and self._cur is not None:
            self._cur["title"] = text
            self._cap = None
        elif self._cap == "snippet" and tag in ("a", "td"):
            if self._cur is not None:
                self._cur["snippet"] = text
                self.results.append(self._cur)
                self._cur = None
            self._cap = None


def _norm(raw, provider, max_results):
    out, seen = [], set()
    for r in raw:
        u = _clean_url(r.get("url", ""))
        if not u.startswith(("http://", "https://")) or u in seen:
            continue
        seen.add(u)
        out.append({"title": r.get("title", "").strip(), "url": u,
                    "snippet": r.get("snippet", "").strip(), "provider": provider})
        if len(out) >= max_results:
            break
    for i, r in enumerate(out, 1):
        r["rank"] = i
    return out


def p_ddg_html(q, n, t):
    p = _DDGParser(); p.feed(_get("https://html.duckduckgo.com/html/?q=" + quote(q), t).decode("utf-8", "replace"))
    return _norm(p.results, "ddg-html", n)


def p_ddg_lite(q, n, t):
    p = _DDGParser(); p.feed(_get("https://lite.duckduckgo.com/lite/?q=" + quote(q), t).decode("utf-8", "replace"))
    return _norm(p.results, "ddg-lite", n)


def p_searx(q, n, t):
    last = None
    for inst in SEARX:  # инстансы нестабильны; отказ всех -> следующий провайдер/L2
        try:
            d = json.loads(_get(inst + "/search?q=" + quote(q) + "&format=json", t))
            return _norm([{"title": x.get("title", ""), "url": x.get("url", ""),
                           "snippet": x.get("content", "")} for x in d.get("results", [])], "searxng", n)
        except Exception as e:
            last = e
    raise last or RuntimeError("searxng unavailable")


def ledger(mode, project, key, artifact=None, aid=None):
    cmd = [sys.executable, "hooks/action_ledger.py", mode, "--project", project, "--key", key]
    if artifact:
        cmd += ["--artifact", artifact]
    if aid:
        cmd += ["--id", aid]
    try:
        r = subprocess.run(cmd, capture_output=True, text=True)
        print(r.stdout.strip())
        return r.returncode
    except FileNotFoundError:
        print("[search] WARN: action_ledger недоступен — идемпотентность только по кэшу")
        return 3


def append_registry(results, query, provider, reg):
    reg = Path(reg)
    existing = reg.read_text(encoding="utf-8") if reg.exists() else REG_COLS + "\n" + REG_SEP + "\n"
    n = len(re.findall(r"^\| SRCH-", existing, flags=re.M))
    rows = []
    for i, r in enumerate(results, n + 1):
        rows.append(f"| SRCH-{i:03d} | {r['url']} | {r['title'][:80]} | {provider} | — | — | поиск | {query[:40]} | резерв | (нет) |")
    reg.parent.mkdir(parents=True, exist_ok=True)
    reg.write_text(existing.rstrip("\n") + "\n" + "\n".join(rows) + "\n", encoding="utf-8")


def main():
    ap = argparse.ArgumentParser(description="Поиск открытых источников (DuckDuckGo, без ключа)")
    ap.add_argument("query")
    ap.add_argument("--project", default="megafon-demo")
    ap.add_argument("--max", type=int, default=8)
    ap.add_argument("--timeout", type=int, default=20)
    ap.add_argument("--registry", default="knowledge/sources/registry.md")
    ap.add_argument("--offline", action="store_true", help="принудительная деградация L2 (тест)")
    ap.add_argument("--force", action="store_true", help="игнорировать кэш (новый поиск)")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args()

    key = f"search:{a.query}|max={a.max}"
    cache = SEARCH_DIR / (hashlib.sha1(key.encode()).hexdigest()[:12] + ".json")
    if not a.force and cache.exists():
        try:
            d = json.loads(cache.read_text(encoding="utf-8"))
            print(f"[search] SKIP повтор: {len(d['results'])} результатов из кэша {cache}")
            if a.json:
                print(json.dumps(d, ensure_ascii=False))
            return 0 if d["results"] else 4
        except (OSError, json.JSONDecodeError, KeyError, TypeError):
            print("[search] WARN: cache is invalid; performing a fresh search")
    elif not a.force and ledger("check", a.project, key) == 0:
        print("[search] WARN: ledger says completed but cache artifact is missing; performing a fresh search")

    providers = [] if a.offline else [("ddg-html", p_ddg_html), ("ddg-lite", p_ddg_lite), ("searxng", p_searx)]
    results, used, tried = [], None, []
    t0 = time.time()
    for name, fn in providers:
        tried.append(name)
        for attempt in range(3):  # retry с backoff (T2.4)
            try:
                results = fn(a.query, a.max, a.timeout)
                used = name
                break
            except Exception as e:
                print(f"[search] fail {name} попытка {attempt+1}: {type(e).__name__}")
                time.sleep(2 ** attempt)
        if used:
            break
    sec = int(time.time() - t0)
    degraded = used is None or used != providers[0][0] if providers else True

    payload = {"query": a.query, "key": key, "ts": datetime.now(timezone.utc).isoformat(),
               "provider_used": used, "providers_tried": tried, "degraded": degraded,
               "sec": sec, "results": results}
    SEARCH_DIR.mkdir(parents=True, exist_ok=True)
    cache.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    if results:
        append_registry(results, a.query, used, a.registry)
    ledger("done", a.project, key, artifact=str(cache), aid=f"A-search-{hashlib.sha1(key.encode()).hexdigest()[:6]}")

    if a.json:
        print(json.dumps(payload, ensure_ascii=False))
    else:
        for r in results:
            print(f"{r['rank']}. {r['title']}\n   {r['url']}\n   {r['snippet'][:160]}")
    if used is None:
        print(f"[search] DEGRADED L2: поиск недоступен ({sec}s). Работай с knowledge/sources/registry.md и кэшем; пробелы фиксируй в claims.")
        return 4
    print(f"[search] OK query='{a.query}' results={len(results)} provider={used} degraded={degraded} sec={sec} cache={cache}")
    return 0


if __name__ == "__main__":
    sys.exit(main())