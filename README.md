# migrate-to-golang

Agentic skill: migrate legacy codebases (C++, Fortran, Java, Python, C, Shell) from a GitHub URL or local directory to a **100% Safe, PGO-tuned Go** architecture, tracking live telemetry across every task bucket, test failure/fix cycle, and Profile-Guided Optimization (PGO) stage — and producing a first-person AI storytelling report plus an interactive HTML infographic.

This is a **Go port of Google's [`migrate-to-rust`](https://github.com/google/skills/tree/main/skills/developers/migrate-to-rust)** skill, re-targeted to the Go toolchain and Go language semantics.

## Directory Layout

```
migrate-to-golang/
├── SKILL.md                                # Main agent instructions & 3-stage workflow
├── scripts/
│   └── telemetry.py                        # Telemetry & infographic CLI (Go semantics)
└── references/
    ├── pgo_and_telemetry_guide.md          # Engineering standards, blueprint spec, Go PGO pipeline
    └── infographic_template.html           # Interactive HTML infographic template
```

## Toolchain Mapping (Rust → Go)

| migrate-to-rust | migrate-to-golang |
|---|---|
| `#![forbid(unsafe_code)]` | Go language memory safety + **0 `unsafe` package imports** (auto-detected) |
| `cargo test` / `cargo clippy` | `go test ./...` / `go vet` (+ optional `staticcheck`) |
| `rustdoc` + doc-tests | Go doc comments + runnable `Example` functions |
| `proptest` | `rapid` (pgregory.net/rapid) property-based tests |
| LLVM PGO (`llvm-profdata`) | Go PGO: `runtime/pprof` CPU profile → `default.pgo` → `go build -pgo=auto` |
| Stages `safe_rust → soa_simd → pgo_lto` | Stages `safe_go → tuned_soa → pgo` |

## Workflow (3 Stages)

- **Stage 0** — Acquire repo, initialize `migration_telemetry.json`, scan legacy codebase, confirm resolved build/run commands with the user, benchmark legacy baseline.
- **Stage 1** — Deep audit; log opportunities & latent legacy bugs; generate a 6-section Architectural Blueprint (safe Go package graph, mapping table, test/parity strategy, 4-stage benchmark & PGO plan).
- **Stage 2** — Phased Safe Go implementation: `go mod init` with 0 `unsafe` imports → Verification Crucible (`go test`, `go vet`, `rapid`, ≥95% statement coverage, max 5 self-healing iterations) → A/B differential output parity across N deterministic seeds → Go PGO (`default.pgo` + `-pgo=auto`) → final census, first-person AI story & interactive HTML infographic.

## Usage

Run the telemetry CLI at each stage transition so every metric is grounded in real measurements:

```bash
python3 scripts/telemetry.py init \
  --telemetry "{workspace_dir}/migration_telemetry.json" \
  --project-name "{project_name}" \
  --legacy-lang "{legacy_language}"

# ... scan-codebase / log-benchmark / log-test-run / log-parity-run / log-spotlight / set-story ...

python3 scripts/telemetry.py render-infographic \
  --telemetry "{workspace_dir}/migration_telemetry.json" \
  --out "{output_dir}/migration_infographic.html" \
  --scope-summary "{short_summary_of_ported_packages}"
```

Full command recipes: [`references/pgo_and_telemetry_guide.md`](references/pgo_and_telemetry_guide.md).
