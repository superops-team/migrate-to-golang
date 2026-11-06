#!/usr/bin/env python3
"""Regression tests for the migrate-to-golang telemetry CLI.

These tests encode the acceptance criteria of
prd-spec/bugfixes/telemetry-scorecard-hardening/2026-11-06-telemetry-scorecard-hardening.md
and are intentionally standard-library only.
"""

import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
TEMPLATE = ROOT / "references" / "infographic_template.html"

sys.path.insert(0, str(SCRIPTS))
import telemetry  # noqa: E402


def run_cli(*argv: str) -> int:
  return telemetry.main(list(argv))


class TelemetryFixture:
  """Creates a temporary telemetry ledger plus source fixtures."""

  def __init__(self) -> None:
    self._tmp = tempfile.TemporaryDirectory()
    self.base = Path(self._tmp.name)
    self.telemetry_path = self.base / "migration_telemetry.json"

  def close(self) -> None:
    self._tmp.cleanup()

  def init(self) -> None:
    rc = run_cli(
        "init",
        "--telemetry",
        str(self.telemetry_path),
        "--project-name",
        "fixture",
        "--legacy-lang",
        "C++",
    )
    if rc != 0:
      raise AssertionError(f"init failed with rc={rc}")

  def load(self) -> dict:
    return json.loads(self.telemetry_path.read_text(encoding="utf-8"))

  def write(self, data: dict) -> None:
    self.telemetry_path.write_text(json.dumps(data, indent=2), encoding="utf-8")

  def make_dir(self, name: str) -> Path:
    path = self.base / name
    path.mkdir(parents=True, exist_ok=True)
    return path


class GradeMappingTests(unittest.TestCase):
  """AC-1: one grade source of truth."""

  def test_grade_thresholds_are_nine_bands(self) -> None:
    expected = {
        100: "A+",
        95: "A+",
        90: "A",
        85: "A-",
        80: "B+",
        75: "B",
        65: "C",
        50: "D",
        0: "F",
    }
    for score, grade in expected.items():
      self.assertEqual(telemetry.grade_from_score(score), grade, score)

  def test_template_has_no_second_grade_implementation(self) -> None:
    template = TEMPLATE.read_text(encoding="utf-8")
    self.assertNotIn(
        "function gradeFromScore",
        template,
        "the HTML template must consume backend grades instead of owning a "
        "second implementation",
    )

  def test_summary_grade_uses_the_single_grading_function(self) -> None:
    fixture = TelemetryFixture()
    try:
      fixture.init()
      data = fixture.load()
      data["census"]["after"].update(
          {
              "scanned": True,
              "files": 3,
              "code_loc": 120,
              "comment_loc": 30,
              "comment_pct": 20.0,
              "max_file_loc": 50,
              "files_under_400_pct": 100.0,
              "max_nesting_depth": 2,
              "avg_fn_loc": 12,
              "unsafe_imports": 0,
              "statement_coverage_pct": 88.0,
              "lint_warnings": 0,
          }
      )
      telemetry.compute_derived_metrics(data)
      measured = [
          card["after_score"]
          for card in data["scorecard"]
          if card.get("after_score") is not None
      ]
      self.assertTrue(measured, "expected at least one measured dimension")
      mean = int(round(sum(measured) / len(measured)))
      self.assertEqual(data.get("summary_grade"), telemetry.grade_from_score(mean))
      for card in data["scorecard"]:
        self.assertEqual(
            card["after_grade"],
            telemetry.grade_from_score(card["after_score"]),
            card["id"],
        )
    finally:
      fixture.close()


class EmptyDataBoundaryTests(unittest.TestCase):
  """AC-2 / AC-3: unknown data must stay unknown."""

  def test_empty_go_directory_has_no_safety_claim(self) -> None:
    fixture = TelemetryFixture()
    try:
      fixture.init()
      empty = fixture.make_dir("empty_go")
      rc = run_cli(
          "scan-codebase",
          "--telemetry",
          str(fixture.telemetry_path),
          "--phase",
          "after",
          "--dir",
          str(empty),
      )
      self.assertEqual(rc, 0)
      after = fixture.load()["census"]["after"]
      self.assertIsNone(after["no_unsafe"])
      self.assertIsNone(after["unsafe_imports"])
    finally:
      fixture.close()

  def test_go_file_without_functions_has_null_avg_fn_loc(self) -> None:
    fixture = TelemetryFixture()
    try:
      fixture.init()
      src = fixture.make_dir("nofunc")
      (src / "main.go").write_text(
          "package main\n\nvar x = 1\n\nconst y = 2\n", encoding="utf-8"
      )
      rc = run_cli(
          "scan-codebase",
          "--telemetry",
          str(fixture.telemetry_path),
          "--phase",
          "after",
          "--dir",
          str(src),
      )
      self.assertEqual(rc, 0)
      after = fixture.load()["census"]["after"]
      self.assertGreater(after["code_loc"], 0)
      self.assertIsNone(after["avg_fn_loc"])
    finally:
      fixture.close()


class CoverageNamingTests(unittest.TestCase):
  """AC-4: statement coverage naming with a legacy alias."""

  def test_scan_writes_statement_key_and_keeps_alias(self) -> None:
    fixture = TelemetryFixture()
    try:
      fixture.init()
      src = fixture.make_dir("cov")
      (src / "main.go").write_text(
          "package main\n\nfunc main() {\n\tprintln(1)\n}\n", encoding="utf-8"
      )
      rc = run_cli(
          "scan-codebase",
          "--telemetry",
          str(fixture.telemetry_path),
          "--phase",
          "after",
          "--dir",
          str(src),
          "--coverage-pct",
          "88.5",
      )
      self.assertEqual(rc, 0)
      after = fixture.load()["census"]["after"]
      self.assertEqual(after["statement_coverage_pct"], 88.5)
      self.assertEqual(after["branch_coverage_pct"], 88.5)
    finally:
      fixture.close()

  def test_legacy_ledger_with_only_branch_key_still_renders(self) -> None:
    fixture = TelemetryFixture()
    try:
      fixture.init()
      data = fixture.load()
      data["census"]["after"].update(
          {
              "scanned": True,
              "files": 1,
              "code_loc": 10,
              "comment_pct": 10.0,
              "files_under_400_pct": 100.0,
              "max_nesting_depth": 1,
              "avg_fn_loc": 5,
              "unsafe_imports": 0,
              "branch_coverage_pct": 91.0,
              "lint_warnings": 0,
          }
      )
      fixture.write(data)
      out = fixture.base / "report.html"
      rc = run_cli(
          "render-infographic",
          "--telemetry",
          str(fixture.telemetry_path),
          "--out",
          str(out),
      )
      self.assertEqual(rc, 0)
      rendered = out.read_text(encoding="utf-8")
      self.assertIn('"statement_coverage_pct": 91.0', rendered)
      self.assertIn('"summary_grade"', rendered)
    finally:
      fixture.close()


class ScanBehaviorTests(unittest.TestCase):
  """AC-5 / NFR-3: scan metrics stay behavior-preserving."""

  def test_basic_go_scan_metrics(self) -> None:
    fixture = TelemetryFixture()
    try:
      fixture.init()
      src = fixture.make_dir("basic")
      (src / "lib.go").write_text(
          "package lib\n\n"
          "import \"unsafe\"\n\n"
          "// Add sums two ints.\n"
          "func Add(a, b int) int {\n"
          "\treturn a + b\n"
          "}\n\n"
          "func ExampleAdd() {\n"
          "\t// Output: 3\n"
          "}\n",
          encoding="utf-8",
      )
      rc = run_cli(
          "scan-codebase",
          "--telemetry",
          str(fixture.telemetry_path),
          "--phase",
          "after",
          "--dir",
          str(src),
      )
      self.assertEqual(rc, 0)
      after = fixture.load()["census"]["after"]
      self.assertEqual(after["files"], 1)
      self.assertEqual(after["unsafe_imports"], 1)
      self.assertFalse(after["no_unsafe"])
      self.assertEqual(after["examples"], 1)
      self.assertGreater(after["code_loc"], 0)
      self.assertEqual(after["files_under_400_pct"], 100.0)
    finally:
      fixture.close()

  def test_scan_does_not_duplicate_latent_bug_writes(self) -> None:
    fixture = TelemetryFixture()
    try:
      fixture.init()
      run_cli(
          "log-opportunity",
          "--telemetry",
          str(fixture.telemetry_path),
          "--category",
          "latent_bug",
          "--title",
          "edge case",
          "--description",
          "uninitialized boundary state",
      )
      legacy = fixture.make_dir("legacy")
      (legacy / "solver.cpp").write_text(
          "// legacy solver\nint run() {\n  return 0;\n}\n", encoding="utf-8"
      )
      run_cli(
          "scan-codebase",
          "--telemetry",
          str(fixture.telemetry_path),
          "--phase",
          "before",
          "--dir",
          str(legacy),
      )
      before = fixture.load()["census"]["before"]
      self.assertEqual(before["latent_bugs_found"], 1)
    finally:
      fixture.close()


class RenderContractTests(unittest.TestCase):
  """AC-6 / AC-7: render contract and end-to-end smoke."""

  def test_template_placeholder_is_replaced(self) -> None:
    data = {"project_name": "fixture", "census": {"before": {}, "after": {}}}
    rendered = telemetry.render_infographic_from_template(TEMPLATE, data)
    self.assertNotIn("__TELEMETRY_JSON_PLACEHOLDER__", rendered)

  def test_end_to_end_render_pipeline(self) -> None:
    fixture = TelemetryFixture()
    try:
      fixture.init()
      before = fixture.make_dir("legacy_src")
      (before / "solver.cpp").write_text(
          "// legacy\nint run() {\n  int *p = malloc(8);\n  return 0;\n}\n",
          encoding="utf-8",
      )
      after = fixture.make_dir("go_src")
      (after / "run.go").write_text(
          "package main\n\nfunc Run() int {\n\treturn 0\n}\n", encoding="utf-8"
      )
      base_argv = ("--telemetry", str(fixture.telemetry_path))
      run_cli("scan-codebase", *base_argv, "--phase", "before", "--dir", str(before))
      run_cli(
          "scan-codebase",
          *base_argv,
          "--phase",
          "after",
          "--dir",
          str(after),
          "--coverage-pct",
          "96.0",
          "--lint-warnings",
          "0",
      )
      run_cli(
          "log-benchmark",
          *base_argv,
          "--stage",
          "legacy_baseline",
          "--wall-time-ms",
          "1000",
          "--peak-rss-mb",
          "500",
      )
      run_cli(
          "log-benchmark",
          *base_argv,
          "--stage",
          "pgo",
          "--wall-time-ms",
          "400",
          "--peak-rss-mb",
          "300",
      )
      run_cli(
          "log-parity-run",
          *base_argv,
          "--iteration",
          "1",
          "--seeds-tested",
          "10",
          "--seeds-passed",
          "10",
          "--max-abs-error",
          "1e-12",
          "--divergence-cause",
          "none",
          "--fix-applied",
          "none",
      )
      out = fixture.base / "report.html"
      rc = run_cli("render-infographic", *base_argv, "--out", str(out))
      self.assertEqual(rc, 0)
      html = out.read_text(encoding="utf-8")
      self.assertIn('"summary_grade"', html)
      self.assertIn('"statement_coverage_pct": 96.0', html)
      self.assertIn('"scorecard"', html)
    finally:
      fixture.close()


if __name__ == "__main__":
  unittest.main()
