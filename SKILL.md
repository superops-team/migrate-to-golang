---
name: migrate-to-golang
metadata:
  version: "1.0.0"
  category: ApplicationDevelopment
description: >-
  Clones, analyzes, plans, and migrates legacy codebases (C++, Fortran, Java,
  Python, C, Shell) from a GitHub URL or local directory to a modern,
  high-performance, deterministic, 100% Safe Go architecture, tracking live
  telemetry across every task bucket, test failure/fix cycle, and
  Profile-Guided Optimization (PGO) stage, and producing a first-person AI
  storytelling report and interactive HTML infographic. Use when migrating a
  GitHub repository or local codebase to Go, porting legacy C++, Fortran,
  Python, or Java workloads to memory-safe Go, designing Struct-of-Arrays
  (SoA) Go architectures, or optimizing Go ports with runtime/pprof-guided
  PGO. Don't use for unrelated non-Go refactoring or single-line syntax
  questions.
---

# Migrate Legacy Codebases to Safe Go

Act as a Systems Architect, Performance Engineer, and Go Specialist. Your goal
is to migrate legacy codebases into 100% Safe, PGO-tuned Go while recording
measured telemetry and a first-person engineering narrative via
[`scripts/telemetry.py`](scripts/telemetry.py).

## Execution Contract & Portability

When migrating a repository or local directory (`{github_url}` or
`{codebase_path}`), follow these execution rules across agentic harnesses:

1.  **Stage 0 External Code Confirmation Gate**: After cloning an external
    repository and inspecting its build files, **present the resolved legacy
    build command, run command, and target directory to the user and obtain
    confirmation before compiling or executing cloned code**. (For local code
    that the user explicitly instructed you to run, or once Stage 0 confirmation
    is granted, proceed directly.)
2.  **Continuous Stage 1 -> Stage 2 Progression**: Once Stage 0 baseline
    capture is complete, proceed directly from writing the Architectural
    Blueprint (Stage 1) into implementing and verifying the Go module
    (Stage 2) without pausing between milestones, where the host environment
    permits autonomous tool execution.
3.  **Bounded Automated Self-Healing (Max 5 Iterations)**: When tests, `go vet`
    / `staticcheck` lints, or A/B parity checks fail, log the failure via
    [`scripts/telemetry.py`](scripts/telemetry.py), diagnose and fix the root
    cause, and re-test automatically up to a budget of **5 self-healing
    iterations** (or 15 minutes per phase). If any test or seed still diverges
    after the budget is exhausted, record the partial state in
    `migration_telemetry.json` and document the remaining gap in the final
    report rather than looping indefinitely.
4.  **Verification Targets & Definition of Done**:
    -   The Go module compiles with a target of `0` `go vet` warnings and `0`
        `staticcheck` warnings (any unavoidable exception must be documented),
        and with **`0` imports of the `unsafe` package** (Go's memory safety is
        enforced by the language; importing `unsafe` would opt out of it).
    -   Unit, integration, `Example`-function, and property-based (`rapid`)
        tests pass with a target of `>= 95%` statement coverage as measured by
        the Go toolchain (`go test -coverprofile`, any unavoidable exception
        must be documented), with every run logged in `migration_telemetry.json`.
    -   A/B differential output parity is verified across `N` deterministic
        seeds within a documented numerical epsilon (`--max-abs-error`), with
        any floating-point/PRNG divergence root-caused and logged.
    -   All 4 benchmark stages (`legacy_baseline`, `safe_go`, `tuned_soa`,
        `pgo`) are measured and logged (or omitted cleanly if a tool such as
        `go tool pprof` is unavailable).
    -   The interactive HTML infographic (`migration_infographic.html`) is
        rendered via `scripts/telemetry.py render-infographic`.

## End-to-End Workflow Checklist

Copy this checklist to track progress across the three stages (detailed command
recipes and architectural specifications are in
[references/pgo_and_telemetry_guide.md](references/pgo_and_telemetry_guide.md)):

```markdown
- [ ] Stage 0: Acquire repo, initialize `migration_telemetry.json` (`discovery` bucket), scan legacy codebase, confirm resolved build/run commands, and benchmark baseline
- [ ] Stage 1: Audit legacy code (`blueprint` bucket), log opportunities & latent legacy bugs, and generate 6-section Architectural Blueprint
- [ ] Stage 2.1: Scaffold Safe Go module (0 `unsafe` imports) & deterministic PRNG parity layer (`rewrite` bucket)
- [ ] Stage 2.2: Implement core domain types & SoA/tuned kernels (<= 400 LOC/file target, full Go doc comments + runnable Example functions) & benchmark `safe_go` + `tuned_soa`
- [ ] Stage 2.3: Run Verification Crucible (`test_heal` bucket, max 5 iterations) — log initial test failure % and each self-healing fix
- [ ] Stage 2.4: Run A/B differential parity harness (`parity` bucket, max 5 iterations) across N seeds within documented epsilon tolerance
- [ ] Stage 2.5: Run Go Profile-Guided Optimization (`pgo_bench` bucket), scan final Go codebase, and render `migration_infographic.html`
```

--------------------------------------------------------------------------------

## Stage 0: Repository Acquisition, Telemetry Init & Legacy Baseline

Resolve context parameters from the repository or directory:

Parameter                         | Placeholder                                | Resolution Strategy
:-------------------------------- | :----------------------------------------- | :------------------
**Source Input**                  | `{codebase_path}` or `{github_url}`        | Accept a GitHub URL (`https://github.com/...`) or a local filesystem path
**Original Language / Framework** | `{legacy_language}`                        | Auto-detect from file extensions and build files (`CMakeLists.txt`, `Makefile`, `meson.build`, `pyproject.toml`, `pom.xml`, `*.f90`, `*.cpp`)
**Baseline Run Command**          | `{baseline_run_command}`                   | Identify from `README.md`, CI workflows (`.github/workflows/*.yml`), `Makefile`, or test scripts
**Telemetry Ledger**              | `{workspace_dir}/migration_telemetry.json` | Initialized via `scripts/telemetry.py init` at the start of Stage 0

### Stage 0 Execution Steps

1.  **Clone Repository (if GitHub URL)**: Choose a clean local directory
    (default to `~/go_migrations/{repo_name}`, or inside the current workspace
    if requested) and run `git clone {github_url}
    ~/go_migrations/{repo_name}`.
2.  **Initialize Telemetry & Scan Legacy Codebase**: Run `scripts/telemetry.py
    init --telemetry "{workspace_dir}/migration_telemetry.json" --project-name
    "{project_name}" --legacy-lang "{legacy_language}"`. Start the `discovery`
    bucket and run `scripts/telemetry.py scan-codebase --phase before` on the
    legacy source directory to record baseline file count, code LOC, comment
    density %, max file LOC, nesting depth, average function length, and raw
    pointer/memory hazards.
3.  **Confirm & Benchmark Legacy Baseline**: Before executing build or run
    commands from a cloned external repository, surface the resolved build
    command, `{baseline_run_command}`, and working directory for user
    confirmation. Once confirmed, compile the legacy project in release mode
    (`-O3` / `Release`), capture golden reference outputs across deterministic
    seeds, measure baseline wall-clock runtime (ms) and peak RSS (MB), and log
    Stage 1 via `scripts/telemetry.py log-benchmark --stage legacy_baseline`.

--------------------------------------------------------------------------------

## Stage 1: Deep Audit, Opportunity Discovery & Architectural Blueprint

Start the `blueprint` timer bucket (`scripts/telemetry.py start-bucket --bucket
blueprint`), inspect the repository, log every discovered opportunity and
**latent legacy bug** (`scripts/telemetry.py log-opportunity`), and generate the
6-section Markdown blueprint defined in Section 2 of
[references/pgo_and_telemetry_guide.md](references/pgo_and_telemetry_guide.md).

**Stage 1 -> Stage 2 Transition**: Save the blueprint and proceed directly to
Stage 2 (unless the user explicitly requested a blueprint-only plan).

--------------------------------------------------------------------------------

## Stage 2: Phased Safe Go Implementation, Self-Healing, PGO & Infographic

Follow the command recipes and core engineering standards in
[references/pgo_and_telemetry_guide.md](references/pgo_and_telemetry_guide.md)
for each step:

### Step 1: Scaffold Safe Go Module & Port Packages (`rewrite` Bucket)

1.  Start the `rewrite` timer bucket (`scripts/telemetry.py start-bucket
    --bucket rewrite`).
2.  Initialize the Go module (`go mod init {module_path}`) and enforce a **0
    `unsafe` imports** policy: never `import "unsafe"`; use safe slices, typed
    values, and `errors.Is`-style typed error handling instead of raw pointers,
    manual `malloc`/`free`, or unchecked indexing.
3.  Implement the deterministic PRNG wrapper, domain types, and packages in
    dependency order (`<= 400` LOC per file target, complete Go doc comments
    `// Package ...` / `// FuncName ...` and runnable `Example*` functions).
4.  Benchmark and log Stage 2 (`safe_go`) and Stage 3 (`tuned_soa`) via
    `scripts/telemetry.py log-benchmark`.

### Step 2: The Verification Crucible — Test, Fail, Diagnose & Fix (`test_heal` Bucket)

1.  Start the `test_heal` timer bucket (`scripts/telemetry.py start-bucket
    --bucket test_heal`).
2.  Write unit tests, runnable `Example` functions, and `rapid` property-based
    boundary tests.
3.  Run `go test ./...`, `go test -coverprofile=coverage.out ./...`, `go vet
    ./...`, and (if available) `staticcheck ./...`.
4.  **Log Every Iteration (Up to 5 Iterations)**: After Run 1 and each
    subsequent run, invoke `scripts/telemetry.py log-test-run` with total tests,
    passed, failed, coverage %, lint warnings, diagnostic summary, and fix
    applied. Iterate until `0` failures and `0` lint warnings (or until the
    5-iteration budget is reached, documenting any unavoidable exception).

### Step 3: A/B Differential Output Parity (`parity` Bucket)

1.  Start the `parity` timer bucket (`scripts/telemetry.py start-bucket --bucket
    parity`).
2.  Run the automated A/B differential harness across `N` deterministic seeds
    comparing `{baseline_run_command}` and the Go binary within the documented
    epsilon tolerance.
3.  Log each parity iteration via `scripts/telemetry.py log-parity-run`. If any
    seed diverges beyond epsilon, bisect the first diverging step, repair the
    discrepancy, and re-run (up to 5 iterations).

### Step 4: Profile-Guided Optimization (PGO) & Final Benchmarks (`pgo_bench` Bucket)

1.  Start the `pgo_bench` timer bucket (`scripts/telemetry.py start-bucket
    --bucket pgo_bench`).
2.  Execute the Go PGO workflow in
    [references/pgo_and_telemetry_guide.md](references/pgo_and_telemetry_guide.md):
    collect a `runtime/pprof` CPU profile from representative workloads
    (`go test -cpuprofile=default.pgo ...` or an in-process
    `pprof.StartCPUProfile`), place it at the module root as `default.pgo`, and
    rebuild with `go build -pgo=auto` (Go 1.21+), optionally with
    `-gcflags`/`GOAMD64` tuning flags (documented fallback if profile sampling
    is unavailable in the environment).
3.  Verify that tests and A/B parity still pass on the PGO binary, then measure
    wall-clock runtime and peak RSS and log Stage 4 (`pgo`) via
    `scripts/telemetry.py log-benchmark --stage pgo`.

### Step 5: Final Census, First-Person AI Story & Visual Infographic

1.  Run `scripts/telemetry.py scan-codebase --phase after` on the Go module's
    source tree (`.go` files) to capture final LOC, `<= 400` LOC compliance,
    comment/Go doc density, runnable `Example` functions, nesting depth, and
    `unsafe` import count.
2.  Log a **Before vs. After Code Spotlight** (`scripts/telemetry.py
    log-spotlight`) and populate the **First-Person AI Story Chapters**
    (`scripts/telemetry.py set-story`).
3.  End the `pgo_bench` timer bucket and render the interactive HTML infographic
    (where `{skill_dir}` is the directory containing this `SKILL.md`):

    ```bash
    python3 "{skill_dir}/scripts/telemetry.py" render-infographic \
      --telemetry "{workspace_dir}/migration_telemetry.json" \
      --out "{output_dir}/migration_infographic.html" \
      --scope-summary "{short_summary_of_ported_packages}"
    ```
4.  Output a concise executive summary referencing the generated
    `migration_infographic.html` report and key measured before/after metrics.

--------------------------------------------------------------------------------

## Bundled Resources

-   **Telemetry & Infographic CLI**:
    [`scripts/telemetry.py`](scripts/telemetry.py)
-   **Engineering Standards, Blueprint Spec, PGO & Telemetry Recipes**:
    [references/pgo_and_telemetry_guide.md](references/pgo_and_telemetry_guide.md)
-   **Interactive HTML Infographic Template**:
    [references/infographic_template.html](references/infographic_template.html)
