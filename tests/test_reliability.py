import json,os,subprocess,sys,tempfile,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
class Reliability(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.old=os.getcwd();os.chdir(self.tmp.name);Path("projects/demo/state").mkdir(parents=True)
 def tearDown(self):os.chdir(self.old);self.tmp.cleanup()
 def runpy(self,path,*args):return subprocess.run([sys.executable,str(ROOT/path),*args],capture_output=True,text=True)
 def test_unknown_price_blocks(self):
  r=self.runpy(Path("hooks/cost_log.py"),"preflight","--project","demo","--model","missing");self.assertEqual(r.returncode,2)
 def test_preflight_blocks_limit(self):
  Path("projects/demo/state/budget.json").write_text(json.dumps({"limit_usd":1,"spent_usd":.9,"history":[],"prices_per_1m":{"m":{"in":"1","out":"1"}}}))
  r=self.runpy(Path("hooks/cost_log.py"),"preflight","--project","demo","--model","m","--tin","200000");self.assertEqual(r.returncode,2)
 def test_cost_log_idempotent(self):
  args=("log","--project","demo","--id","call-1","--model","deepseek-chat","--tin","1000","--tout","1000")
  self.assertEqual(self.runpy(Path("hooks/cost_log.py"),*args).returncode,0);self.runpy(Path("hooks/cost_log.py"),*args)
  d=json.loads(Path("projects/demo/state/budget.json").read_text());self.assertEqual(len(d["history"]),1);self.assertGreater(d["spent_usd"],0)
 def test_cost_report_uses_real_newlines_and_markdown_table(self):
  budget={"project":"demo","limit_usd":5,"spent_usd":0.0123,"updated_at":"2026-01-01T00:00:00+00:00","history":[{"id":"call-report","run":"test-run","step":3,"model":"deepseek-chat","tok_in":1000,"tok_out":500,"sec":12,"cost_usd":0.0123,"estimate":True}]}
  Path("projects/demo/state/budget.json").write_text(json.dumps(budget))
  r=self.runpy(Path("hooks/cost_log.py"),"report","--project","demo")
  self.assertEqual(r.returncode,0,r.stderr)
  report=Path("COSTS.md").read_text(encoding="utf-8")
  self.assertIn("| ID | Прогон | Шаг |",report)
  self.assertIn("\n## По вызовам",report)
  self.assertNotIn("\\n",report)
  self.assertGreater(report.count("\n"),10)
 def test_ledger_idempotent(self):
  args=("--project","demo","--key","fetch:test");self.assertEqual(self.runpy(Path("hooks/action_ledger.py"),"check",*args).returncode,1)
  self.runpy(Path("hooks/action_ledger.py"),"done",*args);self.assertEqual(self.runpy(Path("hooks/action_ledger.py"),"check",*args).returncode,0)
  self.runpy(Path("hooks/action_ledger.py"),"done",*args);self.assertEqual(len(Path("projects/demo/state/action_ledger.jsonl").read_text().splitlines()),1)
if __name__=="__main__":unittest.main()
