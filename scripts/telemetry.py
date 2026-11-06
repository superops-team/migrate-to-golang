#!/usr/bin/env python3
"""Telemetry & Executive Infographic Generator for the migrate-to-golang Skill.

Tracks real wall-clock time across migration task buckets, performs automated
Before/After codebase censuses (LOC, modularity, comment/doc density, cognitive
complexity, legacy memory hazards vs. Go unsafe imports), logs test/parity
self-healing iterations and PGO benchmark staircases, computes the 8-dimension
Executive Scorecard from measured values, and renders a self-contained HTML
infographic from references/infographic_template.html.
"""

import argparse
import datetime
import json
import os
from pathlib import Path
import re
import sys
import time

BUCKET_META = {
    "discovery": ("Discovery & Baseline Capture", "bg-sky-400"),
    "blueprint": ("Deep Audit & 6-Section Blueprint", "bg-indigo-400"),
    "rewrite": ("Safe Go Rewrite & Modularization", "bg-emerald-400"),
    "test_heal": ("Test Generation & Self-Healing Loop", "bg-amber-400"),
    "parity": ("A/B Differential Parity Verification", "bg-cyan-400"),
    "pgo_bench": ("PGO Profiling & Go Benchmarks", "bg-violet-400"),
}

STAGE_LABELS = {
    "legacy_baseline": "1. Legacy Baseline Binary",
    "safe_go": "2. Initial Safe Go Port (Idiomatic)",
    "tuned_soa": "3. Struct-of-Arrays (SoA) & Zero-Alloc Tuning",
    "pgo": "4. Profile-Guided Optimization (Go PGO)",
}

# Scorecard formula weights. Each value is the single source of truth for the
# dimension it feeds; changing one here changes every derived score.
SPEED_BONUS_BASE = 60.0
SPEED_BONUS_CAP = 40.0
SPEED_BONUS_GAIN = 15.0
MEMORY_AFTER_BASE = 70.0
MEMORY_AFTER_GAIN_PER_PCT = 0.3
COST_AFTER_BASE = 50.0
COST_AFTER_GAIN_PER_PCT = 0.5
SAFETY_BEFORE_BASE = 80.0
SAFETY_HAZARD_WEIGHT = 2.5
SAFETY_AFTER_BASE = 90.0
SAFETY_UNSAFE_WEIGHT = 10.0
QUALITY_LINT_WEIGHT = 3.0
HYGIENE_BEFORE_DOC_WEIGHT = 2.0
HYGIENE_BEFORE_LOC_WEIGHT = 0.4
HYGIENE_AFTER_DOC_WEIGHT = 1.8
HYGIENE_AFTER_LOC_WEIGHT = 0.6
HYGIENE_DOC_CAP = 40.0
SIMPLICITY_BEFORE_NEST_WEIGHT = 5.0
SIMPLICITY_BEFORE_FN_WEIGHT = 0.3
SIMPLICITY_AFTER_NEST_FREE = 2
SIMPLICITY_AFTER_NEST_WEIGHT = 4.0
SIMPLICITY_AFTER_FN_FREE = 20
SIMPLICITY_AFTER_FN_WEIGHT = 0.4

LEGACY_EXTS = {
    ".c",
    ".cc",
    ".cpp",
    ".cxx",
    ".h",
    ".hh",
    ".hpp",
    ".f",
    ".f90",
    ".f95",
    ".for",
    ".py",
    ".java",
    ".sh",
    ".bash",
    ".r",
}
GO_EXTS = {".go"}


class TelemetryError(Exception):
  """Actionable error raised when telemetry input or files are invalid."""


def grade_from_score(score: int | None) -> str:
  if score is None:
    return "N/A"
  if score >= 95:
    return "A+"
  if score >= 90:
    return "A"
  if score >= 85:
    return "A-"
  if score >= 80:
    return "B+"
  if score >= 75:
    return "B"
  if score >= 65:
    return "C"
  if score >= 50:
    return "D"
  return "F"


def clamp_score(val: float, low: int = 0, high: int = 100) -> int:
  return max(low, min(high, int(round(val))))


def load_telemetry(path: Path) -> dict:
  if not path.exists():
    raise TelemetryError(
        f"Telemetry file not found: '{path}'. Run 'telemetry.py init"
        f" --telemetry {path} --project-name <name> --legacy-lang <lang>'"
        " first."
    )
  try:
    with path.open("r", encoding="utf-8") as f:
      data = json.load(f)
  except json.JSONDecodeError as exc:
    raise TelemetryError(
        f"Malformed JSON in telemetry file '{path}': {exc}. Re-initialize with"
        " 'telemetry.py init' or fix the JSON syntax."
    ) from exc
  except OSError as exc:
    raise TelemetryError(
        f"Unable to read telemetry file '{path}': {exc}"
    ) from exc
  if not isinstance(data, dict):
    raise TelemetryError(
        f"Telemetry file '{path}' must contain a top-level JSON object."
    )
  return data


def save_telemetry(path: Path, data: dict) -> None:
  try:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
      json.dump(data, f, indent=2)
  except OSError as exc:
    raise TelemetryError(
        f"Unable to write telemetry file '{path}': {exc}"
    ) from exc


def resolve_effective_model(
    cli_model: str | None, existing_model: str | None
) -> str | None:
  """Resolve the active model name from CLI flags, existing telemetry, or environment."""
  for candidate in (
      cli_model,
      existing_model,
      os.environ.get("MIGRATE_TO_GOLANG_MODEL"),
  ):
    if candidate and candidate.strip():
      cleaned = candidate.strip()
      if cleaned.lower() not in {"none", "unspecified", "unknown"}:
        return cleaned
  return None


def close_active_bucket(data: dict, now: float) -> None:
  active = data.get("_active_bucket")
  if isinstance(active, dict) and active.get("name"):
    bname = active["name"]
    elapsed_sec = max(0.0, now - float(active.get("started_at", now)))
    buckets = data.setdefault("_bucket_seconds", {})
    buckets[bname] = buckets.get(bname, 0.0) + elapsed_sec
    data["_active_bucket"] = None


def cmd_init(args: argparse.Namespace) -> None:
  out_path = Path(args.telemetry)
  now = time.time()
  user = getattr(args, "user", None) or os.environ.get("USER", "developer")
  model = resolve_effective_model(getattr(args, "model", None), None)
  data = {
      "project_name": args.project_name,
      "legacy_language": args.legacy_lang,
      "user": user,
      "model": model,
      "source_url": getattr(args, "source_url", None) or "",
      "scope_summary": getattr(args, "scope_summary", None) or "",
      "started_at_epoch": now,
      "completed_at": None,
      "_active_bucket": None,
      "_bucket_seconds": {k: 0.0 for k in BUCKET_META},
      "story": {
          "headline": "",
          "intro": "",
          "ch1_narrative": "",
          "ch2_narrative": "",
          "ch3_narrative": "",
          "ch4_narrative": "",
          "ch5_narrative": "",
      },
      "census": {
          "before": {
              "scanned": False,
              "files": 0,
              "code_loc": 0,
              "comment_loc": 0,
              "comment_pct": None,
              "max_file_loc": 0,
              "avg_file_loc": 0,
              "files_under_400_pct": None,
              "examples": 0,
              "max_nesting_depth": None,
              "avg_fn_loc": None,
              "hazards_count": None,
              "latent_bugs_found": None,
          },
          "after": {
              "scanned": False,
              "files": 0,
              "code_loc": 0,
              "comment_loc": 0,
              "comment_pct": None,
              "max_file_loc": 0,
              "avg_file_loc": 0,
              "files_under_400_pct": None,
              "examples": 0,
              "max_nesting_depth": None,
              "avg_fn_loc": None,
              "unsafe_imports": None,
              "no_unsafe": False,
              "statement_coverage_pct": None,
              "branch_coverage_pct": None,
              "lint_warnings": None,
          },
      },
      "opportunities": [],
      "test_iterations": [],
      "parity_iterations": [],
      "benchmarks": [],
      "time_buckets": [],
      "scorecard": [],
      "roi": {},
      "spotlight": {
          "explanation": "",
          "legacy_file": "",
          "legacy_code": "",
          "go_file": "",
          "go_code": "",
      },
  }
  save_telemetry(out_path, data)
  print(
      f"[telemetry] Initialized {out_path} for '{args.project_name}'"
      f" ({args.legacy_lang})."
  )


def cmd_start_bucket(args: argparse.Namespace) -> None:
  path = Path(args.telemetry)
  data = load_telemetry(path)
  now = time.time()
  close_active_bucket(data, now)
  data["_active_bucket"] = {"name": args.bucket, "started_at": now}
  save_telemetry(path, data)
  print(f"[telemetry] Started timer for bucket '{args.bucket}'.")


def cmd_end_bucket(args: argparse.Namespace) -> None:
  path = Path(args.telemetry)
  data = load_telemetry(path)
  now = time.time()
  close_active_bucket(data, now)
  if args.minutes is not None:
    data.setdefault("_bucket_seconds", {})[args.bucket] = (
        float(args.minutes) * 60.0
    )
  save_telemetry(path, data)
  print(f"[telemetry] Ended timer for bucket '{args.bucket}'.")


SKIP_DIRS = {
    ".git",
    "target",
    "build",
    "vendor",
    "node_modules",
    ".venv",
    "__pycache__",
}

FN_PATTERN_GO = re.compile(
    r"^\s*func\s+(?:\([^)]*\)\s+)?(?:[A-Za-z_]\w*)\s*\("
)
FN_PATTERN_LEGACY = re.compile(
    r"^\s*(?:[\w:<>~*&\s]+)\s+\w+\s*\([^;]*\)\s*(?:const)?\s*\{|"
    r"^\s*def\s+\w+\s*\(|"
    r"^\s*(?:subroutine|function)\s+\w+",
    re.IGNORECASE,
)
HAZARD_PATTERN = re.compile(
    r"\b(?:malloc|calloc|realloc|free|new|delete|memcpy|memset|goto|COMMON|EQUIVALENCE)\b|"
    r"\*\s*\w+\s*=|->\w+|\bstatic\s+(?!const\b)\w+",
)
# "import \"unsafe\"" as a single line, or "\"unsafe\"" inside an import block.
UNSAFE_IMPORT_PATTERN = re.compile(r'^\s*(?:import\s+)?"unsafe"\s*$')
EXAMPLE_PATTERN = re.compile(r"^\s*func\s+Example[\w]*\s*\(")


def _iter_source_files(root_dir: Path, exts: set[str]):
  """Yield (path, lines) for every source file of an extension inside root."""
  for dirpath, dirnames, filenames in os.walk(root_dir):
    dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS]
    for fname in filenames:
      fpath = Path(dirpath) / fname
      if fpath.suffix.lower() not in exts:
        continue
      try:
        lines = fpath.read_text(encoding="utf-8", errors="ignore").splitlines()
      except OSError:
        continue
      yield fpath, lines


def _track_nesting(
    line: str, suffix: str, brace_depth: int, max_nesting: int
) -> tuple[int, int]:
  """Update the running nesting estimate for one non-empty source line."""
  if suffix == ".py":
    depth = (len(line) - len(line.lstrip(" "))) // 4
    return brace_depth, max(max_nesting, depth)
  stripped = line.strip()
  brace_depth += stripped.count("{") - stripped.count("}")
  brace_depth = max(0, brace_depth)
  return brace_depth, max(max_nesting, brace_depth)


def _scan_source_file(fpath: Path, lines: list[str], is_go: bool) -> dict:
  """Classify every line of one file into code/comment/hazard counters."""
  suffix = fpath.suffix.lower()
  file_code = 0
  file_comment = 0
  in_block_comment = False
  brace_depth = 0
  max_nesting = 0
  fn_count = 0
  hazards = 0
  unsafe_imports = 0
  examples = 0

  for line in lines:
    stripped = line.strip()
    if not stripped:
      continue

    if is_go and UNSAFE_IMPORT_PATTERN.match(stripped):
      unsafe_imports += 1

    # Block comment handling
    if in_block_comment:
      file_comment += 1
      if "*/" in stripped:
        in_block_comment = False
      continue

    if stripped.startswith("/*"):
      file_comment += 1
      if "*/" not in stripped[2:]:
        in_block_comment = True
      continue

    if is_go:
      if stripped.startswith("//"):
        file_comment += 1
        continue
    else:
      if (
          stripped.startswith("//")
          or stripped.startswith("#")
          or (
              suffix in {".f", ".f90", ".f95", ".for"}
              and stripped.startswith("!")
          )
      ):
        file_comment += 1
        continue

    # Count code line
    file_code += 1
    if "//" in stripped:
      file_comment += 1

    brace_depth, max_nesting = _track_nesting(
        line, suffix, brace_depth, max_nesting
    )

    if is_go:
      if FN_PATTERN_GO.match(line):
        fn_count += 1
      if EXAMPLE_PATTERN.match(line):
        examples += 1
    else:
      if FN_PATTERN_LEGACY.match(line):
        fn_count += 1
      hazards += len(HAZARD_PATTERN.findall(stripped))

  return {
      "code": file_code,
      "comment": file_comment,
      "examples": examples,
      "hazards": hazards,
      "unsafe_imports": unsafe_imports,
      "max_nesting": max_nesting,
      "fn_count": fn_count,
  }


def _summarize_census(
    files_loc: list[int],
    total_code: int,
    total_comments: int,
    examples: int,
    max_nesting: int,
    fn_count: int,
    hazards: int,
    unsafe_imports: int,
    is_go: bool,
) -> dict:
  """Aggregate per-file counters into the census payload for one phase."""
  num_files = len(files_loc)
  max_loc = max(files_loc) if files_loc else 0
  avg_loc = int(round(sum(files_loc) / num_files)) if num_files else 0
  under_400 = (
      round((sum(1 for x in files_loc if x <= 400) / num_files) * 100.0, 1)
      if num_files
      else None
  )
  comment_pct = (
      round((total_comments / max(1, total_code)) * 100.0, 1)
      if total_code > 0
      else None
  )
  # A file with code but no recognizable function must not fake an average.
  avg_fn_loc = int(round(total_code / fn_count)) if fn_count > 0 else None
  measured_nesting = (
      max(1, min(max_nesting, 12 if is_go else 15)) if num_files > 0 else None
  )

  if is_go:
    return {
        "scanned": num_files > 0,
        "files": num_files,
        "code_loc": total_code,
        "comment_loc": total_comments,
        "comment_pct": comment_pct,
        "max_file_loc": max_loc,
        "avg_file_loc": avg_loc,
        "files_under_400_pct": under_400,
        "examples": examples,
        "max_nesting_depth": measured_nesting,
        "avg_fn_loc": avg_fn_loc,
        # Safety is unknown, not proven safe, when nothing was scanned.
        "unsafe_imports": unsafe_imports if num_files > 0 else None,
        "no_unsafe": (unsafe_imports == 0) if num_files > 0 else None,
    }
  return {
      "scanned": num_files > 0,
      "files": num_files,
      "code_loc": total_code,
      "comment_loc": total_comments,
      "comment_pct": comment_pct,
      "max_file_loc": max_loc,
      "avg_file_loc": avg_loc,
      "files_under_400_pct": under_400,
      "examples": 0,
      "max_nesting_depth": measured_nesting,
      "avg_fn_loc": avg_fn_loc,
      "hazards_count": hazards if num_files > 0 else None,
  }


def analyze_directory(root_dir: Path, is_go: bool) -> dict:
  if not root_dir.exists():
    raise TelemetryError(
        f"Directory to scan does not exist: '{root_dir}'. Pass a valid"
        " source directory to 'scan-codebase --dir'."
    )
  exts = GO_EXTS if is_go else LEGACY_EXTS

  files_loc: list[int] = []
  total_code = 0
  total_comments = 0
  examples = 0
  max_nesting = 0
  fn_count = 0
  hazards = 0
  unsafe_imports = 0

  for fpath, lines in _iter_source_files(root_dir, exts):
    stats = _scan_source_file(fpath, lines, is_go)
    file_total_loc = stats["code"] + stats["comment"]
    if file_total_loc > 0:
      files_loc.append(file_total_loc)
      total_code += stats["code"]
      total_comments += stats["comment"]
    examples += stats["examples"]
    max_nesting = max(max_nesting, stats["max_nesting"])
    fn_count += stats["fn_count"]
    hazards += stats["hazards"]
    unsafe_imports += stats["unsafe_imports"]

  return _summarize_census(
      files_loc,
      total_code,
      total_comments,
      examples,
      max_nesting,
      fn_count,
      hazards,
      unsafe_imports,
      is_go,
  )


def cmd_scan_codebase(args: argparse.Namespace) -> None:
  path = Path(args.telemetry)
  data = load_telemetry(path)
  target_dir = Path(args.dir)
  is_go = args.phase == "after"
  stats = analyze_directory(target_dir, is_go=is_go)

  census = data.setdefault("census", {})
  before_c = census.setdefault("before", {})
  after_c = census.setdefault("after", {})

  if is_go:
    legacy_cov = after_c.get("statement_coverage_pct")
    if legacy_cov is None:
      # Backward compatibility: ledgers written before the rename only carry
      # the historical "branch" key.
      legacy_cov = after_c.get("branch_coverage_pct")
    cov = (
        round(float(args.coverage_pct), 1)
        if args.coverage_pct is not None
        else legacy_cov
    )
    stats["statement_coverage_pct"] = cov
    stats["branch_coverage_pct"] = cov
    if args.lint_warnings is not None:
      stats["lint_warnings"] = int(args.lint_warnings)
    else:
      stats["lint_warnings"] = after_c.get("lint_warnings")
    after_c.update(stats)
  else:
    # latent_bugs_found is owned by 'log-opportunity'; scanning only refreshes
    # measured code metrics so there is exactly one writer for that counter.
    stats.pop("latent_bugs_found", None)
    before_c.update(stats)

  save_telemetry(path, data)
  print(
      f"[telemetry] Scanned '{args.phase}' codebase at {target_dir}:"
      f" {json.dumps(stats)}"
  )


def cmd_log_opportunity(args: argparse.Namespace) -> None:
  path = Path(args.telemetry)
  data = load_telemetry(path)
  entry = {
      "category": args.category,
      "title": args.title,
      "file": args.file or "",
      "description": args.description,
  }
  data.setdefault("opportunities", []).append(entry)
  if args.category == "latent_bug":
    latent = sum(
        1 for o in data["opportunities"] if o.get("category") == "latent_bug"
    )
    data.setdefault("census", {}).setdefault("before", {})[
        "latent_bugs_found"
    ] = latent
  save_telemetry(path, data)
  print(f"[telemetry] Logged {args.category}: {args.title}")


def cmd_log_test_run(args: argparse.Namespace) -> None:
  path = Path(args.telemetry)
  data = load_telemetry(path)
  cov_val = (
      round(float(args.coverage_pct), 1)
      if args.coverage_pct is not None
      else None
  )
  lint_val = (
      int(args.lint_warnings) if args.lint_warnings is not None else None
  )
  entry = {
      "iteration": args.iteration,
      "total": args.total,
      "passed": args.passed,
      "failed": args.failed,
      "coverage_pct": cov_val,
      "lint_warnings": lint_val,
      "failures_summary": args.failures_summary,
      "fix_applied": args.fix_applied,
  }
  runs = data.setdefault("test_iterations", [])
  runs = [r for r in runs if r.get("iteration") != args.iteration]
  runs.append(entry)
  runs.sort(key=lambda r: r["iteration"])
  data["test_iterations"] = runs
  after_c = data.setdefault("census", {}).setdefault("after", {})
  if cov_val is not None:
    after_c["statement_coverage_pct"] = cov_val
    after_c["branch_coverage_pct"] = cov_val
  if lint_val is not None:
    after_c["lint_warnings"] = lint_val
  save_telemetry(path, data)
  print(
      f"[telemetry] Logged test iteration #{args.iteration}:"
      f" {args.passed}/{args.total} passed."
  )


def cmd_log_parity_run(args: argparse.Namespace) -> None:
  path = Path(args.telemetry)
  data = load_telemetry(path)
  entry = {
      "iteration": args.iteration,
      "seeds_tested": args.seeds_tested,
      "seeds_passed": args.seeds_passed,
      "max_abs_error": args.max_abs_error,
      "divergence_cause": args.divergence_cause,
      "fix_applied": args.fix_applied,
  }
  runs = data.setdefault("parity_iterations", [])
  runs = [r for r in runs if r.get("iteration") != args.iteration]
  runs.append(entry)
  runs.sort(key=lambda r: r["iteration"])
  data["parity_iterations"] = runs
  save_telemetry(path, data)
  print(
      f"[telemetry] Logged parity iteration #{args.iteration}:"
      f" {args.seeds_passed}/{args.seeds_tested} seeds matched."
  )


def cmd_log_benchmark(args: argparse.Namespace) -> None:
  path = Path(args.telemetry)
  data = load_telemetry(path)
  benches = data.setdefault("benchmarks", [])
  benches = [b for b in benches if b.get("stage") != args.stage]

  base_ms = float(args.wall_time_ms)
  for b in benches:
    if b.get("stage") == "legacy_baseline":
      base_ms = float(b["wall_time_ms"])
      break

  entry = {
      "stage": args.stage,
      "label": args.label or STAGE_LABELS.get(args.stage, args.stage),
      "wall_time_ms": round(float(args.wall_time_ms), 2),
      "peak_rss_mb": round(float(args.peak_rss_mb), 2),
      "speedup": round(base_ms / max(0.001, float(args.wall_time_ms)), 2),
      "notes": args.notes or "",
  }
  benches.append(entry)
  stage_order = ["legacy_baseline", "safe_go", "tuned_soa", "pgo"]
  benches.sort(
      key=lambda b: stage_order.index(b["stage"])
      if b["stage"] in stage_order
      else 99
  )

  # Recompute speedups relative to first benchmark
  if benches:
    first_ms = max(0.001, float(benches[0]["wall_time_ms"]))
    for b in benches:
      b["speedup"] = round(first_ms / max(0.001, float(b["wall_time_ms"])), 2)

  data["benchmarks"] = benches
  save_telemetry(path, data)
  print(
      f"[telemetry] Logged benchmark '{args.stage}': {entry['wall_time_ms']} ms"
      f" ({entry['speedup']}x)."
  )


def cmd_log_spotlight(args: argparse.Namespace) -> None:
  path = Path(args.telemetry)
  data = load_telemetry(path)
  legacy_code = args.legacy_code or ""
  if args.legacy_code_file:
    lpath = Path(args.legacy_code_file)
    if not lpath.exists():
      raise TelemetryError(f"Legacy spotlight code file not found: '{lpath}'")
    legacy_code = lpath.read_text(encoding="utf-8", errors="ignore")
  go_code = args.go_code or ""
  if args.go_code_file:
    gpath = Path(args.go_code_file)
    if not gpath.exists():
      raise TelemetryError(f"Go spotlight code file not found: '{gpath}'")
    go_code = gpath.read_text(encoding="utf-8", errors="ignore")

  data["spotlight"] = {
      "explanation": args.explanation,
      "legacy_file": args.legacy_file,
      "legacy_code": legacy_code,
      "go_file": args.go_file,
      "go_code": go_code,
  }
  save_telemetry(path, data)
  print("[telemetry] Updated Before/After code spotlight.")


def cmd_set_story(args: argparse.Namespace) -> None:
  path = Path(args.telemetry)
  data = load_telemetry(path)
  story = data.setdefault("story", {})
  for field in [
      "headline",
      "intro",
      "ch1_narrative",
      "ch2_narrative",
      "ch3_narrative",
      "ch4_narrative",
      "ch5_narrative",
  ]:
    val = getattr(args, field, None)
    if val:
      story[field] = val
  save_telemetry(path, data)
  print("[telemetry] Updated first-person AI narrative chapters.")


DIMENSION_META = (
    (
        "speed",
        "Speed & PGO Throughput",
        "⚡",
        (
            "Wall-clock runtime comparison across baseline, Struct-of-Arrays"
            " (SoA) layout, and Go Profile-Guided Optimization (PGO)."
        ),
    ),
    (
        "memory",
        "Memory Efficiency (RSS)",
        "💾",
        (
            "Peak resident memory footprint with pre-allocated workspace"
            " buffers and zero hot-loop heap allocations."
        ),
    ),
    (
        "safety",
        "Memory Safety (Unsafe Import Audit)",
        "🛡️",
        (
            "Go memory safety is enforced by the language; 0 imports of the"
            " unsafe package guarantee no unchecked pointer arithmetic."
        ),
    ),
    ("parity", "Output Parity & Determinism", "🎯", None),
    (
        "quality",
        "Code Quality & Test Coverage",
        "✅",
        (
            "Unit, integration, Example-function, and property-based rapid"
            " suites with go vet / staticcheck zero-warning verification."
        ),
    ),
    (
        "hygiene",
        "Code Hygiene & Documentation",
        "📚",
        (
            "Exported symbols documented with Go doc comments and runnable"
            " Example functions, targeting <=400 LOC per file."
        ),
    ),
    (
        "simplicity",
        "Cognitive Simplicity",
        "🧩",
        (
            "Decomposed deeply nested monolithic functions and mutable"
            " globals into small, composable functions."
        ),
    ),
    (
        "cost",
        "Compute Throughput Efficiency",
        "☁️",
        (
            "Measured execution speedup and memory reduction per node"
            " across benchmark stages."
        ),
    ),
)


def _finalize_completion(data: dict) -> None:
  after_scanned = bool(
      ((data.get("census") or {}).get("after") or {}).get("scanned")
  )
  if after_scanned:
    data["completed_at"] = datetime.datetime.now(
        datetime.timezone.utc
    ).strftime("%Y-%m-%d %H:%M UTC")
  else:
    data.setdefault("completed_at", None)


def _compute_time_buckets(data: dict) -> tuple[list[dict], dict]:
  """Aggregate measured wall-clock time into bucket rows and the ROI block."""
  sec_map = data.get("_bucket_seconds", {})
  time_buckets = []
  total_minutes = 0
  active_buckets_count = 0
  for bkey, (blabel, bcolor) in BUCKET_META.items():
    secs = float(sec_map.get(bkey, 0.0))
    if secs > 0.0:
      mins = max(1, int(round(secs / 60.0)))
      active_buckets_count += 1
    else:
      mins = 0
    total_minutes += mins
    time_buckets.append({
        "bucket": bkey,
        "label": blabel,
        "minutes": mins,
        "color": bcolor,
    })
  roi = {
      "total_ai_minutes": total_minutes,
      "total_ai_hours": round(total_minutes / 60.0, 2),
      "active_buckets_count": active_buckets_count,
  }
  return time_buckets, roi


def _score_speed(benches: list[dict]) -> dict:
  if len(benches) >= 2:
    base_b = benches[0]
    final_b = benches[-1]
    base_ms = max(0.001, float(base_b.get("wall_time_ms", 0.0)))
    final_ms = max(0.001, float(final_b.get("wall_time_ms", 0.0)))
    speedup = round(base_ms / final_ms, 2)
    return {
        "before_score": clamp_score(100.0 / max(1.0, speedup), 0, 100),
        "before_label": f"{base_b['wall_time_ms']} ms (1.0x)",
        "after_score": clamp_score(
            SPEED_BONUS_BASE * speedup
            if speedup < 1.0
            else SPEED_BONUS_BASE
            + min(SPEED_BONUS_CAP, (speedup - 1.0) * SPEED_BONUS_GAIN),
            0,
            100,
        ),
        "after_label": f"{final_b['wall_time_ms']} ms ({speedup:.2f}x)",
        "delta_badge": (
            f"{speedup:.2f}x Faster" if speedup >= 1.0 else f"{speedup:.2f}x Slower"
        ),
        "explanation": None,
    }
  return {
      "before_score": None,
      "before_label": (
          f"{benches[0]['wall_time_ms']} ms" if benches else "Not measured"
      ),
      "after_score": None,
      "after_label": "Not measured",
      "delta_badge": "Not measured",
      "explanation": None,
  }


def _score_memory(benches: list[dict]) -> dict:
  if len(benches) >= 2:
    base_b = benches[0]
    final_b = benches[-1]
    rss_before = max(0.001, float(base_b.get("peak_rss_mb", 0.0)))
    rss_after = max(0.001, float(final_b.get("peak_rss_mb", 0.0)))
    rss_drop_pct = round((1.0 - rss_after / rss_before) * 100.0, 1)
    return {
        "before_score": clamp_score(100.0 - max(0.0, rss_drop_pct), 0, 100),
        "before_label": f"{base_b['peak_rss_mb']} MB Peak RSS",
        "after_score": clamp_score(
            MEMORY_AFTER_BASE + rss_drop_pct * MEMORY_AFTER_GAIN_PER_PCT, 0, 100
        ),
        "after_label": f"{final_b['peak_rss_mb']} MB Peak RSS",
        "delta_badge": (
            f"-{rss_drop_pct:.1f}% RAM"
            if rss_drop_pct >= 0
            else f"+{abs(rss_drop_pct):.1f}% RAM"
        ),
        "explanation": None,
    }
  return {
      "before_score": None,
      "before_label": (
          f"{benches[0]['peak_rss_mb']} MB" if benches else "Not measured"
      ),
      "after_score": None,
      "after_label": "Not measured",
      "delta_badge": "Not measured",
      "explanation": None,
  }


def _score_safety(before_c: dict, after_c: dict) -> dict:
  hazards = before_c.get("hazards_count")
  unsafe_cnt = after_c.get("unsafe_imports")
  result = {
      "before_score": None,
      "before_label": "Not measured",
      "after_score": None,
      "after_label": "Not measured",
      "delta_badge": "Not measured",
      "explanation": None,
  }
  if hazards is not None:
    result["before_score"] = clamp_score(
        SAFETY_BEFORE_BASE - float(hazards) * SAFETY_HAZARD_WEIGHT, 0, 100
    )
    result["before_label"] = f"{int(hazards)} Pointer/State Hazards"
  if unsafe_cnt is not None:
    unsafe_int = int(unsafe_cnt)
    result["after_score"] = (
        100
        if unsafe_int == 0
        else clamp_score(
            SAFETY_AFTER_BASE - unsafe_int * SAFETY_UNSAFE_WEIGHT, 0, 100
        )
    )
    result["after_label"] = f"{unsafe_int} Unsafe Imports"
    result["delta_badge"] = (
        "100% Safe Go" if unsafe_int == 0 else f"{unsafe_int} Unsafe Imports"
    )
  return result


def _score_parity(parity_runs: list[dict]) -> dict:
  if parity_runs:
    last_p = parity_runs[-1]
    seeds_t = max(1, int(last_p.get("seeds_tested", 0)))
    seeds_p = int(last_p.get("seeds_passed", 0))
    parity_pct = round((seeds_p / seeds_t) * 100.0, 1)
    return {
        "before_score": None,
        "before_label": "Not measured",
        "after_score": clamp_score(parity_pct, 0, 100),
        "after_label": f"{parity_pct}% across {seeds_t} Seeds",
        "delta_badge": f"{parity_pct}% Verified",
        "explanation": (
            "Automated A/B differential harness verified output equivalence"
            f" across {seeds_t} deterministic seeds."
        ),
    }
  return {
      "before_score": None,
      "before_label": "Not measured",
      "after_score": None,
      "after_label": "Not measured",
      "delta_badge": "Not measured",
      "explanation": (
          "No A/B parity runs were logged. Run 'telemetry.py log-parity-run' to"
          " record seed comparisons."
      ),
  }


def _normalize_coverage_keys(after_c: dict) -> None:
  """Backfill the statement key from a legacy ledger so consumers see one name."""
  if (
      after_c.get("statement_coverage_pct") is None
      and after_c.get("branch_coverage_pct") is not None
  ):
    after_c["statement_coverage_pct"] = after_c["branch_coverage_pct"]


def _score_quality(after_c: dict) -> dict:
  cov_raw = after_c.get("statement_coverage_pct")
  if cov_raw is None:
    # Backward compatibility with ledgers that only carry the legacy key.
    cov_raw = after_c.get("branch_coverage_pct")
  lint_raw = after_c.get("lint_warnings")
  if cov_raw is not None and lint_raw is not None:
    cov_pct = round(float(cov_raw), 1)
    lint_w = int(lint_raw)
    return {
        "before_score": None,
        "before_label": "Not measured",
        "after_score": clamp_score(
            cov_pct - lint_w * QUALITY_LINT_WEIGHT, 0, 100
        ),
        "after_label": f"{cov_pct}% Coverage",
        "delta_badge": f"{lint_w} Lint Warnings • {cov_pct}% Cov",
        "explanation": None,
    }
  return {
      "before_score": None,
      "before_label": "Not measured",
      "after_score": None,
      "after_label": "Not measured",
      "delta_badge": "Not measured",
      "explanation": None,
  }


def _score_hygiene(before_c: dict, after_c: dict) -> dict:
  doc_before = before_c.get("comment_pct")
  doc_after = after_c.get("comment_pct")
  u400_before = before_c.get("files_under_400_pct")
  u400_after = after_c.get("files_under_400_pct")
  result = {
      "before_score": None,
      "before_label": "Not measured",
      "after_score": None,
      "after_label": "Not measured",
      "delta_badge": "Not measured",
      "explanation": None,
  }
  if doc_before is not None and u400_before is not None:
    result["before_score"] = clamp_score(
        float(doc_before) * HYGIENE_BEFORE_DOC_WEIGHT
        + float(u400_before) * HYGIENE_BEFORE_LOC_WEIGHT,
        0,
        100,
    )
    result["before_label"] = (
        f"{doc_before}% Comments • {before_c.get('max_file_loc', 0)} Max LOC"
    )
  if doc_after is not None and u400_after is not None:
    result["after_score"] = clamp_score(
        float(u400_after) * HYGIENE_AFTER_LOC_WEIGHT
        + min(
            HYGIENE_DOC_CAP, float(doc_after) * HYGIENE_AFTER_DOC_WEIGHT
        ),
        0,
        100,
    )
    result["after_label"] = (
        f"{doc_after}% Docs • {after_c.get('max_file_loc', 0)} Max LOC"
    )
    if doc_before is not None and float(doc_before) > 0:
      doc_inc = int(
          round(
              ((float(doc_after) - float(doc_before)) / float(doc_before))
              * 100.0
          )
      )
      result["delta_badge"] = (
          f"+{doc_inc}% Docs" if doc_inc >= 0 else f"{doc_inc}% Docs"
      )
    else:
      result["delta_badge"] = f"{doc_after}% Docs"
  return result


def _score_simplicity(before_c: dict, after_c: dict) -> dict:
  nest_b = before_c.get("max_nesting_depth")
  fn_b = before_c.get("avg_fn_loc")
  nest_a = after_c.get("max_nesting_depth")
  fn_a = after_c.get("avg_fn_loc")
  result = {
      "before_score": None,
      "before_label": "Not measured",
      "after_score": None,
      "after_label": "Not measured",
      "delta_badge": "Not measured",
      "explanation": None,
  }
  if nest_b is not None and fn_b is not None:
    result["before_score"] = clamp_score(
        100.0
        - int(nest_b) * SIMPLICITY_BEFORE_NEST_WEIGHT
        - int(fn_b) * SIMPLICITY_BEFORE_FN_WEIGHT,
        0,
        100,
    )
    result["before_label"] = f"Depth {int(nest_b)} • {int(fn_b)} LOC/Fn"
  if nest_a is not None and fn_a is not None:
    result["after_score"] = clamp_score(
        100.0
        - max(0, int(nest_a) - SIMPLICITY_AFTER_NEST_FREE)
        * SIMPLICITY_AFTER_NEST_WEIGHT
        - max(0, int(fn_a) - SIMPLICITY_AFTER_FN_FREE)
        * SIMPLICITY_AFTER_FN_WEIGHT,
        0,
        100,
    )
    result["after_label"] = f"Depth {int(nest_a)} • {int(fn_a)} LOC/Fn"
    if fn_b is not None and int(fn_b) > 0:
      fn_drop = int(round(((int(fn_b) - int(fn_a)) / int(fn_b)) * 100.0))
      result["delta_badge"] = (
          f"-{fn_drop}% Fn Size"
          if fn_drop >= 0
          else f"+{abs(fn_drop)}% Fn Size"
      )
    else:
      result["delta_badge"] = f"{int(fn_a)} LOC/Fn"
  return result


def _score_cost(benches: list[dict]) -> dict:
  if len(benches) >= 2:
    base_b = benches[0]
    final_b = benches[-1]
    base_ms = max(0.001, float(base_b.get("wall_time_ms", 0.0)))
    final_ms = max(0.001, float(final_b.get("wall_time_ms", 0.0)))
    compute_saved_pct = int(round((1.0 - final_ms / base_ms) * 100.0))
    return {
        "before_score": None,
        "before_label": "Not measured",
        "after_score": clamp_score(
            COST_AFTER_BASE
            + compute_saved_pct * COST_AFTER_GAIN_PER_PCT,
            0,
            100,
        ),
        "after_label": f"{round(base_ms / final_ms, 2):.2f}x Throughput / Node",
        "delta_badge": (
            f"-{compute_saved_pct}% Compute Hrs"
            if compute_saved_pct >= 0
            else f"+{abs(compute_saved_pct)}% Compute Hrs"
        ),
        "explanation": None,
    }
  return {
      "before_score": None,
      "before_label": "Not measured",
      "after_score": None,
      "after_label": "Not measured",
      "delta_badge": "Not measured",
      "explanation": None,
  }


def _build_scorecard(measured: dict[str, dict]) -> list[dict]:
  cards = []
  for dim_id, title, icon, explanation in DIMENSION_META:
    scores = measured[dim_id]
    cards.append({
        "id": dim_id,
        "title": title,
        "icon": icon,
        "before_score": scores["before_score"],
        "before_grade": grade_from_score(scores["before_score"]),
        "before_label": scores["before_label"],
        "after_score": scores["after_score"],
        "after_grade": grade_from_score(scores["after_score"]),
        "after_label": scores["after_label"],
        "delta_badge": scores["delta_badge"],
        "explanation": (
            scores["explanation"]
            if scores["explanation"] is not None
            else explanation
        ),
    })
  return cards


def _compute_overall_summary(cards: list[dict]) -> dict:
  before = [
      card["before_score"]
      for card in cards
      if card.get("before_score") is not None
  ]
  after = [
      card["after_score"]
      for card in cards
      if card.get("after_score") is not None
  ]
  before_avg = int(round(sum(before) / len(before))) if before else None
  after_avg = int(round(sum(after) / len(after))) if after else None
  return {
      "before_avg": before_avg,
      "before_grade": grade_from_score(before_avg),
      "after_avg": after_avg,
      "after_grade": grade_from_score(after_avg),
  }


def compute_derived_metrics(data: dict) -> None:
  """Compute every derived block from measured telemetry (single entry point)."""
  now = time.time()
  close_active_bucket(data, now)
  _finalize_completion(data)

  time_buckets, roi = _compute_time_buckets(data)
  data["time_buckets"] = time_buckets
  data["roi"] = roi

  census = data.get("census") or {}
  before_c = census.get("before") or {}
  after_c = census.get("after") or {}
  _normalize_coverage_keys(after_c)
  benches = data.get("benchmarks") or []
  parity_runs = data.get("parity_iterations") or []

  measured = {
      "speed": _score_speed(benches),
      "memory": _score_memory(benches),
      "safety": _score_safety(before_c, after_c),
      "parity": _score_parity(parity_runs),
      "quality": _score_quality(after_c),
      "hygiene": _score_hygiene(before_c, after_c),
      "simplicity": _score_simplicity(before_c, after_c),
      "cost": _score_cost(benches),
  }
  cards = _build_scorecard(measured)
  data["scorecard"] = cards
  summary = _compute_overall_summary(cards)
  data["overall"] = summary
  data["summary_grade"] = summary["after_grade"]


def render_infographic_from_template(tpl_path: Path, data: dict) -> str:
  """Render an interactive HTML infographic from infographic_template.html and telemetry dict."""
  try:
    html = tpl_path.read_text(encoding="utf-8")
  except OSError as exc:
    raise TelemetryError(
        f"Unable to read infographic template '{tpl_path}': {exc}"
    ) from exc
  json_payload = json.dumps(data, indent=2).replace("</", "<\\/")
  return html.replace('"__TELEMETRY_JSON_PLACEHOLDER__"', json_payload)


def cmd_render_infographic(args: argparse.Namespace) -> None:
  tpath = Path(args.telemetry)
  data = load_telemetry(tpath)
  if getattr(args, "user", None):
    data["user"] = args.user
  data["model"] = resolve_effective_model(
      getattr(args, "model", None), data.get("model")
  )
  if getattr(args, "source_url", None):
    data["source_url"] = args.source_url
  if getattr(args, "scope_summary", None):
    data["scope_summary"] = args.scope_summary
  if getattr(args, "run_id", None):
    data["run_id"] = args.run_id

  compute_derived_metrics(data)
  save_telemetry(tpath, data)

  script_dir = Path(__file__).parent.resolve()
  default_tpl = script_dir.parent / "references" / "infographic_template.html"
  tpl_path = Path(args.template) if args.template else default_tpl

  if not tpl_path.exists():
    raise TelemetryError(
        f"Infographic template not found at '{tpl_path}'. Pass a valid path"
        " via '--template'."
    )

  html_out = render_infographic_from_template(tpl_path, data)

  out_path = Path(args.out)
  try:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(html_out, encoding="utf-8")
  except OSError as exc:
    raise TelemetryError(
        f"Unable to write HTML infographic to '{out_path}': {exc}"
    ) from exc
  print(f"[telemetry] Rendered interactive HTML infographic to {out_path}")


def build_parser() -> argparse.ArgumentParser:
  p = argparse.ArgumentParser(
      description="migrate-to-golang Migration Telemetry & Infographic CLI"
  )
  sub = p.add_subparsers(dest="cmd", required=True)

  p_init = sub.add_parser("init", help="Initialize migration_telemetry.json")
  p_init.add_argument(
      "--telemetry", required=True, help="Path to migration_telemetry.json"
  )
  p_init.add_argument(
      "--project-name", required=True, help="Human-readable project name"
  )
  p_init.add_argument(
      "--legacy-lang",
      required=True,
      help="Detected legacy language (e.g. C++14, Fortran90, Python)",
  )
  p_init.add_argument(
      "--model",
      default=None,
      help="Optional AI model identifier",
  )
  p_init.add_argument("--user", default=None, help="Developer username")
  p_init.add_argument(
      "--source-url", default=None, help="Source GitHub URL or repository path"
  )
  p_init.add_argument(
      "--scope-summary", default=None, help="Brief summary of migrated scope"
  )
  p_init.set_defaults(func=cmd_init)

  p_sb = sub.add_parser(
      "start-bucket", help="Start wall-clock timer for a task bucket"
  )
  p_sb.add_argument("--telemetry", required=True)
  p_sb.add_argument("--bucket", required=True, choices=list(BUCKET_META.keys()))
  p_sb.set_defaults(func=cmd_start_bucket)

  p_eb = sub.add_parser(
      "end-bucket", help="End wall-clock timer for a task bucket"
  )
  p_eb.add_argument("--telemetry", required=True)
  p_eb.add_argument("--bucket", required=True, choices=list(BUCKET_META.keys()))
  p_eb.add_argument(
      "--minutes",
      type=float,
      default=None,
      help="Optional explicit minutes override",
  )
  p_eb.set_defaults(func=cmd_end_bucket)

  p_scan = sub.add_parser(
      "scan-codebase",
      help="Scan Before (legacy) or After (Go) codebase metrics",
  )
  p_scan.add_argument("--telemetry", required=True)
  p_scan.add_argument("--phase", required=True, choices=["before", "after"])
  p_scan.add_argument("--dir", required=True, help="Directory to scan")
  p_scan.add_argument("--coverage-pct", type=float, default=None)
  p_scan.add_argument("--lint-warnings", type=int, default=None)
  p_scan.set_defaults(func=cmd_scan_codebase)

  p_opp = sub.add_parser(
      "log-opportunity",
      help="Log an architectural opportunity or latent legacy bug",
  )
  p_opp.add_argument("--telemetry", required=True)
  p_opp.add_argument(
      "--category",
      required=True,
      choices=[
          "latent_bug",
          "performance",
          "safety",
          "hygiene",
          "architecture",
      ],
  )
  p_opp.add_argument("--title", required=True)
  p_opp.add_argument("--file", default="")
  p_opp.add_argument("--description", required=True)
  p_opp.set_defaults(func=cmd_log_opportunity)

  p_tr = sub.add_parser(
      "log-test-run", help="Log a test execution & self-healing iteration"
  )
  p_tr.add_argument("--telemetry", required=True)
  p_tr.add_argument("--iteration", type=int, required=True)
  p_tr.add_argument("--total", type=int, required=True)
  p_tr.add_argument("--passed", type=int, required=True)
  p_tr.add_argument("--failed", type=int, required=True)
  p_tr.add_argument("--coverage-pct", type=float, default=None)
  p_tr.add_argument("--lint-warnings", type=int, default=None)
  p_tr.add_argument("--failures-summary", required=True)
  p_tr.add_argument("--fix-applied", required=True)
  p_tr.set_defaults(func=cmd_log_test_run)

  p_pr = sub.add_parser(
      "log-parity-run", help="Log an A/B differential parity iteration"
  )
  p_pr.add_argument("--telemetry", required=True)
  p_pr.add_argument("--iteration", type=int, required=True)
  p_pr.add_argument("--seeds-tested", type=int, required=True)
  p_pr.add_argument("--seeds-passed", type=int, required=True)
  p_pr.add_argument("--max-abs-error", required=True)
  p_pr.add_argument("--divergence-cause", required=True)
  p_pr.add_argument("--fix-applied", required=True)
  p_pr.set_defaults(func=cmd_log_parity_run)

  p_bm = sub.add_parser(
      "log-benchmark", help="Log a benchmark stage on the 4-stage PGO staircase"
  )
  p_bm.add_argument("--telemetry", required=True)
  p_bm.add_argument(
      "--stage",
      required=True,
      choices=["legacy_baseline", "safe_go", "tuned_soa", "pgo"],
  )
  p_bm.add_argument("--label", default="")
  p_bm.add_argument("--wall-time-ms", type=float, required=True)
  p_bm.add_argument("--peak-rss-mb", type=float, required=True)
  p_bm.add_argument("--notes", default="")
  p_bm.set_defaults(func=cmd_log_benchmark)

  p_sp = sub.add_parser(
      "log-spotlight", help="Record Before/After code snippet spotlight"
  )
  p_sp.add_argument("--telemetry", required=True)
  p_sp.add_argument("--explanation", required=True)
  p_sp.add_argument("--legacy-file", required=True)
  p_sp.add_argument("--legacy-code", default="")
  p_sp.add_argument("--legacy-code-file", default="")
  p_sp.add_argument("--go-file", required=True)
  p_sp.add_argument("--go-code", default="")
  p_sp.add_argument("--go-code-file", default="")
  p_sp.set_defaults(func=cmd_log_spotlight)

  p_st = sub.add_parser(
      "set-story", help="Set first-person AI story narrative fields"
  )
  p_st.add_argument("--telemetry", required=True)
  p_st.add_argument("--headline", default=None)
  p_st.add_argument("--intro", default=None)
  p_st.add_argument("--ch1-narrative", dest="ch1_narrative", default=None)
  p_st.add_argument("--ch2-narrative", dest="ch2_narrative", default=None)
  p_st.add_argument("--ch3-narrative", dest="ch3_narrative", default=None)
  p_st.add_argument("--ch4-narrative", dest="ch4_narrative", default=None)
  p_st.add_argument("--ch5-narrative", dest="ch5_narrative", default=None)
  p_st.set_defaults(func=cmd_set_story)

  p_ri = sub.add_parser(
      "render-infographic",
      help="Compute final scorecard and render HTML infographic",
  )
  p_ri.add_argument("--telemetry", required=True)
  p_ri.add_argument(
      "--out",
      required=True,
      help="Output HTML file path",
  )
  p_ri.add_argument(
      "--template", default=None, help="Optional custom template path"
  )
  p_ri.add_argument(
      "--model",
      default=None,
      help="Optional AI model identifier",
  )
  p_ri.add_argument("--user", default=None, help="Developer username")
  p_ri.add_argument(
      "--source-url", default=None, help="Source GitHub URL or repository path"
  )
  p_ri.add_argument(
      "--scope-summary", default=None, help="Brief summary of migrated scope"
  )
  p_ri.add_argument(
      "--run-id", default=None, help="Optional explicit run ID slug"
  )
  p_ri.set_defaults(func=cmd_render_infographic)

  return p


def main(argv: list[str] | None = None) -> int:
  parser = build_parser()
  args = parser.parse_args(argv)
  try:
    args.func(args)
  except TelemetryError as exc:
    print(f"[telemetry] ERROR: {exc}", file=sys.stderr)
    return 1
  except KeyError as exc:
    print(
        f"[telemetry] ERROR: Missing required telemetry key {exc}. Ensure"
        " 'telemetry.py init' was run on this file.",
        file=sys.stderr,
    )
    return 1
  return 0


if __name__ == "__main__":
  sys.exit(main())
