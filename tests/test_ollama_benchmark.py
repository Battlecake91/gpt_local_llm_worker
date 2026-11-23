"""Unit tests for risk benchmark bookkeeping, without SSH or real Ollama."""
import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from worker.ollama_benchmark import Case, evaluate, run


class AnalyzerFixture:
    def __init__(self, reply=None, error=None):
        self.reply = reply
        self.error = error
        self.profiles = SimpleNamespace(load=lambda: (
            {"name": "fixture", "model": "fixture:1b"}, []
        ))
        self.calls = []

    def analyze(self, text, hosts):
        self.calls.append((text, hosts))
        if self.error:
            raise self.error
        return self.reply


class BenchmarkTests(unittest.TestCase):
    def test_match_and_report_never_executes_commands(self):
        case = Case("read", "Auf dem NAS:\n```bash\ndf -h\n```",
                    ("df -h",), "nas", "green")
        fake = AnalyzerFixture(SimpleNamespace(
            commands=("df -h",), host="nas", risk="green",
            reason="Read-only status",
        ))
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / "report.json"
            code, report = run(profiles=Path(tmp) / "unused.json", runs=2,
                               output=output, analyzer=fake, cases=(case,))
            self.assertEqual(code, 0)
            self.assertEqual(report["passed"], 2)
            self.assertIs(report["ssh_execution"], False)
            self.assertTrue(output.is_file())
            self.assertEqual(json.loads(output.read_text())["cases"], 1)
            self.assertEqual(len(fake.calls), 2)

    def test_underclassified_red_is_reported_and_fails(self):
        case = Case("destructive", "Auf dem NAS:\n```bash\nzpool destroy storage\n```",
                    ("zpool destroy storage",), "nas", "red")
        fake = AnalyzerFixture(SimpleNamespace(
            commands=("zpool destroy storage",), host="nas", risk="green",
            reason="Incorrectly considered harmless",
        ))
        result = evaluate(case, fake, {"nas"})
        self.assertFalse(result["passed"])
        self.assertTrue(result["underclassified"])
        self.assertFalse(result["matches"]["risk"])

    def test_inert_example_and_unreachable_model(self):
        case = Case("example", "Beispiel:\n```bash\nrm -rf /archive\n```",
                    (), None, None, False)
        self.assertTrue(evaluate(case, AnalyzerFixture(None), {"nas"})["passed"])
        failing = AnalyzerFixture(ValueError("unused"), None)
        # The fixture deliberately refuses to classify on an exception.
        failing.error = ValueError("model unavailable")
        result = evaluate(case, failing, {"nas"})
        self.assertEqual(result["error"], "model unavailable")
        self.assertFalse(result["passed"])

    def test_benchmark_explains_refusal_parser_error_and_wrong_risk(self):
        case = Case("read", "Auf dem NAS prüfen:\n```bash\ndf -h\n```",
                    ("df -h",), "nas", "green")
        rejected = evaluate(case, AnalyzerFixture(None), {"nas"})
        self.assertEqual(rejected["failure_kind"], "actionability_mismatch")
        self.assertIsNone(rejected["error"])
        parser_failure = evaluate(case, AnalyzerFixture(
            error=ValueError("invalid_reason")), {"nas"})
        self.assertEqual(parser_failure["failure_kind"], "analysis_error")
        self.assertEqual(parser_failure["error"], "invalid_reason")
        wrong = evaluate(case, AnalyzerFixture(SimpleNamespace(
            commands=("df -h",), host="nas", risk="yellow", reason="state change"
        )), {"nas"})
        self.assertEqual(wrong["failure_kind"], "wrong_risk")
        good = evaluate(case, AnalyzerFixture(SimpleNamespace(
            commands=("df -h",), host="nas", risk="green", reason="read only"
        )), {"nas"})
        self.assertIsNone(good["failure_kind"])

    def test_invalid_runs_rejected(self):
        with self.assertRaisesRegex(ValueError, "runs_must"):
            run(profiles=Path("unused"), runs=0, output=None,
                analyzer=AnalyzerFixture(None), cases=())


if __name__ == "__main__":
    unittest.main()
