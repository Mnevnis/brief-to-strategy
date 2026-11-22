#!/usr/bin/env python3
"""Run a reproducible, non-LLM smoke pipeline for the fictional-operator case.

This records local tool execution and network degradation honestly. It does not
claim a full agent run, paid model usage, customer research, or pilot evidence.
"""
import argparse
import json
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path


def run(label, command, timeout=120):
    started = time.perf_counter()
    try:
        result = subprocess.run(command, capture_output=True, text=True, timeout=timeout)
        status = "success" if result.returncode == 0 else "degraded" if result.returncode == 4 else "failed"
        stdout, stderr, code = result.stdout, result.stderr, result.returncode
    except subprocess.TimeoutExpired as exc:
        status, stdout, stderr, code = "timeout", exc.stdout or "", exc.stderr or "", 124
    elapsed = round(time.perf_counter() - started, 3)
    return {
        "label": label, "command": command, "exit_code": code,
        "status": status, "elapsed_seconds": elapsed,
        "stdout": stdout[-12000:], "stderr": stderr[-6000:],
    }


def last_json_with_results(stdout):
    for line in reversed(stdout.splitlines()):
        line = line.strip()
        if not line.startswith("{"):
            continue
        try:
            value = json.loads(line)
            if isinstance(value, dict) and "results" in value:
                return value
        except json.JSONDecodeError:
            pass
    return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--project", default="fictional-operator")
    ap.add_argument("--input", default="projects/fictional-operator/materials/brief_metrics.csv")
    ap.add_argument("--outdir", default="projects/fictional-operator/output/tool_runs")
    args = ap.parse_args()

    outdir = Path(args.outdir)
    outdir.mkdir(parents=True, exist_ok=True)
    started_at = datetime.now(timezone.utc).isoformat()
    started = time.perf_counter()
    steps = []
    cases = [
        (args.project, args.input, "Таблица показателей основного учебного брифа"),
        ("second-brief", "projects/second-brief/materials/brief_metrics.csv",
         "Таблица показателей мини-брифа по собственным номерам"),
    ]
    for project, input_path, title in cases:
        parsed_dir = Path("projects") / project / "materials" / "parsed"
        steps.append(run(f"parse_doc:{project}", [
            sys.executable, "tools/parse_doc.py", input_path,
            "--outdir", str(parsed_dir), "--title", title,
        ]))
        steps.append(run(f"metrics_check:{project}", [
            sys.executable, "tools/metrics.py", "check", input_path,
            "--project", project, "--name", "brief_metrics_audit", "--strict",
        ]))

    steps.append(run("cost_log_init", [
        sys.executable, "hooks/cost_log.py", "init", "--project", args.project,
    ]))
    steps.append(run("cost_log_check", [
        sys.executable, "hooks/cost_log.py", "check", "--project", args.project,
    ]))
    steps.append(run("cost_log_report", [
        sys.executable, "hooks/cost_log.py", "report", "--project", args.project,
    ]))

    query = "European Data Protection Board Guidelines 05/2020 consent official"
    search = run("search", [
        sys.executable, "tools/search.py", query, "--project", args.project,
        "--max", "3", "--json", "--force",
    ], timeout=110)
    steps.append(search)
    payload = last_json_with_results(search["stdout"])
    urls = [x.get("url") for x in (payload or {}).get("results", []) if x.get("url")]
    search["result_count"] = len(urls)
    search["provider_used"] = (payload or {}).get("provider_used")
    if not urls:
        search["status"] = "empty_results"
        search["status_note"] = "Search returned zero usable results; the direct official-source fetch below is a separate fallback."
    # The fallback is an official EDPB landing page, not a substitute for search evidence.
    fetch_url = urls[0] if urls else (
        "https://www.edpb.europa.eu/our-work-tools/our-documents/guidelines/"
        "guidelines-052020-consent-under-regulation-2016679_en"
    )
    fetch = run("fetch_cache", [
        sys.executable, "tools/fetch_cache.py", fetch_url,
        "--project", args.project, "--force",
    ], timeout=60)
    fetch["selected_url"] = fetch_url
    fetch["url_source"] = "search_result" if urls else "documented_official_fallback"
    steps.append(fetch)

    elapsed = round(time.perf_counter() - started, 3)
    required_ok = all(s["status"] == "success" for s in steps[:7])
    report = {
        "run_id": "fictional-operator-tool-smoke",
        "started_at_utc": started_at,
        "finished_at_utc": datetime.now(timezone.utc).isoformat(),
        "project": args.project,
        "input": args.input,
        "steps": steps,
        "automated_wall_time_seconds": elapsed,
        "manual_time_seconds": None,
        "llm_api_calls": 0,
        "llm_api_cost_usd": None,
        "cost_note": "No LLM/API call was made by this smoke run; this is not a measurement of the full agent or human work.",
        "external_cost_usd": None,
        "external_cost_note": "Search/fetch used public endpoints; any infrastructure or indirect cost was not measured.",
        "overall": "PASS_WITH_NETWORK_STATUS_RECORDED" if required_ok else "FAIL",
        "scope_note": "This is a local-tool smoke run, not an end-to-end agent workflow or customer/pilot validation.",
    }
    (outdir / "smoke_run.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    lines = [
        "# Tool smoke run — fictional-operator", "",
        f"- Started (UTC): {started_at}",
        f"- Automated wall time: {elapsed:.3f} s",
        "- Manual time: not measured",
        "- LLM/API calls: 0 in this smoke run; full agent usage not measured",
        "- LLM/API cost: not applicable to this run; not a full-run cost estimate",
        "- External search/fetch cost: not measured", "",
        "## Human time (separate from automated wall time)", "",
        "| Activity | Time | Evidence |",
        "|---|---:|---|",
        "| Brief preparation / manual review | Not measured | No time-tracking record available |",
        "| Human gates / approval | Not performed | Gate decisions remain pending |",
        "",
        "| Tool | Status | Exit | Wall time, s |",
        "|---|---|---:|---:|",
    ]
    for step in steps:
        lines.append(f"| {step['label']} | {step['status']} | {step['exit_code']} | {step['elapsed_seconds']:.3f} |")
    lines += ["", "## Commands and outcomes", ""]
    for step in steps:
        lines += [f"### {step['label']}", "", f"- Command: `{' '.join(step['command'])}`",
                  f"- Status: **{step['status']}** (exit {step['exit_code']})",
                  f"- Wall time: {step['elapsed_seconds']:.3f} s"]
        if step.get("selected_url"):
            lines.append(f"- URL: {step['selected_url']} ({step['url_source']})")
        if step["stdout"]:
            lines += ["", "Output:", "", "```text", step["stdout"][-4000:], "```"]
        if step["stderr"]:
            lines += ["", "Stderr:", "", "```text", step["stderr"][-2000:], "```"]
        lines.append("")
    lines += [
        "## Interpretation", "",
        "Parser and metrics run against the checked-in, source-derived CSV fixtures for both cases. Search/fetch status is recorded independently; zero-result search is not presented as successful source discovery. The second brief is a derived sub-scenario from the same source brief, not an independent external brief.",
        "No paid model was called. This report does not include the manual time needed to prepare or review the case, nor any full-agent runtime.",
        "",
    ]
    (outdir / "smoke_run.md").write_text("\n".join(lines), encoding="utf-8")
    print(f"[demo_pipeline_smoke] {report['overall']} elapsed={elapsed:.3f}s report={outdir / 'smoke_run.md'}")
    return 0 if required_ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
