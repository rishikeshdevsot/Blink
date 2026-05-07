# Scripts to run and evaluate Blink

This directory contains the scripts used in the evaluation of the OSDI '26 paper *"When Sampling Lies: Trustworthy Performance Profiling for Flat Workloads with Blink"*. The evaluation covers four areas: correctness, overhead/perturbation, coverage, and real-world utility (auto-tuning, jank investigation, LSEO validation, and test-suite integration).

## Directory Overview

```
scripts/
├── blink/                       # Runtime setup code to be run on the target phone (ARM64 / OpenHarmony)
│   ├── configure-blink.cpp      
│   ├── blink-pmu-detect.cpp     
│   ├── Makefile                 
│   └── README.md                # Detailed Blink user guide (compile-time, runtime, post-processing)
├── post_process/                # Scripts to post-process Blink's raw traces into user-readable format
│   ├── post-process.py          # Main script: raw traces → per-function summary CSVs
│   ├── pmu_filter.py            # Helper functions to filter known issues
│   └── run_many_multiprocess2.sh# Batch orchestrator for many apps/workloads/runs
├── framedrop/                   # Frame jank analysis (overhead evaluation)
│   ├── compute_jank_simple.py   # Jank histogram from raw .htrace text files
│   └── compute_jank.py          # Jank analysis from SmartPerf SQLite .db files
└── mir_scripts/                 # Multi-run aggregation, perf parsing, and visualization
    └── cpu-test/
        ├── blink/               # Blink aggregation scripts
        │   ├── summarize_workload.py  # Merge per-run summaries into one per-workload CSV
        │   ├── process_workload.py    # Scan report tree, aggregate all workloads
        │   └── callee_result.py       # Base vs custom profile comparison (auto-tuning case study)
        └── perf/                # Perf/Hiperf equivalents + comparative plots
            ├── parse_perf.py                # Parse hiperf/perf .data files → function-level CSVs
            ├── parse_many_perf2.sh          # Batch wrapper around parse_perf.py
            ├── summarize_workload.py        # Merge per-run perf summaries
            ├── process_workload.py          # Scan report tree, aggregate perf workloads
            ├── librenderservice_boxplot.py  # Blink vs Perf comparative plots (Fig. 6, Table 3)
            ├── librenderservice_boxplot_coverage.py  # Coverage comparison (Fig. 2)
            └── small_function.py            # Small-function accuracy scatter (Fig. 4)
```

## Prerequisites

### On the host machine (post-processing & plotting)
- BiSheng compiler with Blink instrumentation support (see `blink/README.md`)
- Python 3.8+ with packages: `pandas`, `numpy`, `scipy`, `tqdm`, `matplotlib`, `seaborn`, `statsmodels`
- `c++filt` (binutils) — used for C++ name demangling
- `tar`, `uuidgen` — used by the batch orchestrator

### On the target phone (data collection)
- OpenHarmony/HarmonyOS device (tested on Huawei Mate 60 Pro, Kirin 9000S)
- `hdc` (HarmonyOS Device Connector) — for pushing files and running commands on the phone
- `hiperf_host` binary — for offline parsing of hiperf `.data` files (used by `parse_perf.py`)

## Workflow

The evaluation follows a pipeline: **compile binary with blink → deploy binary → collect raw blink traces → post-process traces → aggregate → visualize**. Steps 2–3 happen on/with the phone; steps 1,4–6 happen on the host.

### Step 1: Compile the runtime binaries

```bash
cd scripts/blink
make
```

This produces two ARM64 binaries:
- **`configure-blink`** — sends tracing configuration to an instrumented process via `SIGUSR2`
- **`blink-pmu-detect`** — detects which PMU counter index is usable on the phone

> The Makefile uses a BiSheng Clang toolchain at a hardcoded path. Update `CXX` and `LD` in the Makefile to match your environment.

### Step 2: Detect available PMU counter (on the phone)

```bash
./blink-pmu-detect
```

**Output:** Prints the recommended PMU counter index to stdout, e.g.:
```
[RESULT] Counter PMEVCNTR5_EL0 appears monotonically increasing. Recommend using index 5.
```

**Paper context:** Used to determine `--pmu-index` for `configure-blink`. Default is index 5 (Section 3.4).

### Step 3: Collect Blink traces (on the phone)

```bash
# Phone setup
setenforce 0
chmod 777 /data/local/tmp/pmu

# Enable tracing
./configure-blink \
    --pid $(pidof render_service) \
    --event CPU_CYCLES \
    --lib librender_service_base.z.so \
    --mode=dynamic \
    --nsamples 30 \
    --sampling-interval 400000 \
    --output-dir /data/local/tmp/pmu

# Run the workload (e.g. gallery swipe)
# ... then kill/stop the app so buffers flush
```

Key parameters (see `blink/README.md` for full details):
| Parameter | Description | Default | Paper Section |
|-----------|-------------|---------|---------------|
| `--pid` | PID of the process to trace | (required) | §3 |
| `--event` | PMU event name (`CPU_CYCLES`, `INST_RETIRED`, etc.) | (required) | §3 |
| `--mode` | `dynamic` (sampling) or `regular` (signal-based) | (required) | §3 |
| `--lib` | Name of instrumented library (dynamic mode) | (required in dynamic) | §3 |
| `--bundle` | App bundle name (required for apps) | — | §3 |
| `--nsamples` | Samples per function before self-disabling | 20 | §3, §4 |
| `--sampling-interval` | Re-enable interval in microseconds | 400,000 | §3, §4 |
| `--pervasive` | Disable sampling; trace every invocation | off | §4.3.4 |
| `--pmu-index` | PMU counter register index | 5 | §3.4 |
| `--buffer-size` | Thread-local buffer size (in samples) | 10,000 | §3.4 |
| `--output-dir` | Trace output directory on phone | `/data/storage/el1/base` | §3 |

**Output:** Per-thread binary trace files: `thread-<tid>.bin` (or `.csv`) in the output directory.

### Step 4: Post-process Blink traces (on the host)

#### Single workload

```bash
cd scripts/post_process
python3 post-process.py \
    --mip_dir /path/to/MIPCodeInfo \
    --pmu_dir /path/to/pmu \
    --compute_self
```

**Parameters:**
| Flag | Description |
|------|-------------|
| `--mip_dir` | Path to `MIPCodeInfo/` directory from the compiler build output |
| `--pmu_dir` | Path to directory containing raw `thread-*.csv` / `.bin` trace files |
| `--compute_self` | Compute self-time (excluding callees) — needed for tree vs. self analysis (§3.3) |
| `--debug` | Enable verbose logging and write `debug/` diagnostic files |

**Output** (written to `data/` relative to the working directory):

| File | Description | Paper Figure |
|------|-------------|-------------|
| `summary.csv` | Per-function statistics: mangled name, demangled name, median/avg event counts, invocation count, total event counts, nchildren, callsite totals | Table 2, Fig. 5, Fig. 6 |
| `summary_corrected.csv` | Same as `summary.csv` with an ad-hoc correction subtracting `nchildren * 10` | — |
| `output.csv` | Raw per-invocation self-time durations | — |
| `nchildren.csv` | Per-function child count statistics | — |
| `failure.csv` | Stack-mismatch failures (entry/exit pairing errors) | — |
| `leftover.csv` | Unpaired events remaining at trace end | — |
| `info.json` | Overall totals (start/end PMU values, total samples) | — |

#### Batch processing (many apps/workloads/runs)

```bash
cd scripts/post_process
bash run_many_multiprocess2.sh \
    /path/to/report_dir \
    /path/to/MIPCodeInfo \
    false        # set to "--parallel" for parallel processing, "true" for old flat .bin layout
```

The report directory should follow this layout:
```
report_dir/
└── <app>/
    └── <workload>/
        └── pmu_blink/
            └── <run#>/
                └── blink_logs.tar.gz   # archive of thread-*.bin files
```

For each run, the script extracts the archive, runs `post-process.py`, and copies the resulting `data/` CSVs back into the run directory.

**Output:** Each `pmu_blink/<run#>/data/storage/el1/base/` is populated with `summary.csv`, `summary_corrected.csv`, `info.json`, `leftover.csv`, `output.csv`, `failure.csv`.

### Step 5: Aggregate across runs and workloads

#### Blink aggregation

```bash
cd scripts/mir_scripts/cpu-test/blink
python3 process_workload.py \
    /path/to/report_dir \
    --json workload.json
```

The `workload.json` file specifies active apps and workloads:
```json
{
  "active": {
    "Camera": { "workload": ["large_picture_view", "small_capture"] },
    "Browser": { "workload": ["search", "open_first_news"] }
  }
}
```

**Output:**
- Per-workload CSVs: `<RESULT>/<app>_<workload>.csv`
- Combined CSV: `<RESULT>/combined.csv` — all workloads concatenated, with columns: `fun`, `lib`, per-run values (`1`..`N`), `Avg`, `StdDev%`, `Avg%_of_total`, `Num_Run_out_10`

#### Perf/Hiperf aggregation

```bash
cd scripts/mir_scripts/cpu-test/perf
python3 process_workload.py \
    /path/to/report_dir \
    --json workload.json \
    -n 10
```

Same structure and output as the Blink version, but for perf `.data.csv` files.

**Paper context:** The combined CSVs from both Blink and Perf are used as input to the comparative visualization scripts (Step 6).

### Step 6: Visualization and analysis

#### Blink vs. Perf comparison (Figure 6, Table 3)

```bash
cd scripts/mir_scripts/cpu-test/perf
python3 librenderservice_boxplot.py \
    --perf /path/to/perf_combined.csv \
    --blink /path/to/blink_combined.csv \
    --output full_perf.png
```

All flags are optional with defaults matching the standard directory layout. Run with `--help` to see all options.

**Output:**
- `wow.png` — Violin/box plot of per-function cycle distributions
- `xy_function_merge.png` — Log-log scatter with OLS regression (reproduces Figure 6)
- `unique_functions.png` / `.pdf` — Unique function coverage bar charts
- `numcycle_function_merge_*.png` — Cycle difference plots
- `diff_*_cycle.png` — Percentage difference histograms

#### Coverage comparison across sampling frequencies (Figure 2)

```bash
cd scripts/mir_scripts/cpu-test/perf
# Edit INPUT1–INPUT4 paths for perf@4kHz, perf@8kHz, perf@30kHz, and Blink
python3 librenderservice_boxplot_coverage.py
```

**Output:**
- `unique_functions.png` / `.pdf` — Grouped bar chart of function coverage per workload (reproduces Figure 2)

#### Small-function accuracy (Figure 4)

```bash
cd scripts/mir_scripts/cpu-test/perf
python3 small_function.py \
    --blink /path/to/blink_no_isb.csv \
    --blink-isb /path/to/blink_with_isb.csv \
    --perf /path/to/perf_default.csv \
    --perf-20k /path/to/perf_20k.csv \
    --ground-truth /path/to/final_demangled.csv
```

All flags are optional with defaults matching the standard directory layout. Run with `--help` to see all options.

**Input:** Blink summary CSVs (with and without ISB, with different configurations) and a ground-truth instruction count file (`final_demangled.csv`).

**Output:**
- `small_function.png` / `.pdf` — Scatter plot of measured vs. ground-truth instruction counts (reproduces Figure 4)
- Prints mean error, median error, and 95% CI to stdout

### Frame jank analysis (Table 1)

Two scripts are provided for measuring jank (consecutive delayed frames). `compute_jank_simple.py` works with raw `.htrace` text files and requires no special tools; `compute_jank.py` works with SmartPerf's structured SQLite databases and can additionally invoke critical-path analysis.

#### From raw hitrace text files

```bash
cd scripts/framedrop
python3 compute_jank_simple.py trace_run_1.htrace trace_run_2.htrace ...
```

**Input:** One or more `.htrace` text files from hitrace/ftrace on the phone.

**Output:**
- `jank.csv` — DataFrame with jank distribution per run (Jank0 = on-time, JankN = N consecutive delayed frames)
- Prints mean and standard deviation of jank distribution to stdout

**Paper context:** This reproduces Table 1 — comparing jank distribution between Baseline and Blink-instrumented runs.

#### From SmartPerf SQLite databases

SmartPerf is HarmonyOS's built-in performance profiling tool ([OpenHarmony docs](https://gitee.com/openharmony/docs/blob/master/en/application-dev/application-test/smartperf-guidelines.md), [Huawei developer guide](https://developer.huawei.com/consumer/cn/doc/harmonyos-guides/smartperf-guidelines)). It captures both trace events and sampling data, storing results in SQLite `.db` files. Its `frame_slice` table contains per-frame timing with `expected` vs. `actual` render durations, which `compute_jank.py` queries to classify frames as jank or on-time.

```bash
cd scripts/framedrop
python3 compute_jank.py /path/to/smartperf_trace.db
```

**Input:** A SQLite `.db` file from SmartPerf containing `frame_slice` tables.

**Output:** Comma-separated consecutive-jank histogram to stdout.

## Paper Evaluation Mapping

| Paper Section | Figure/Table | Scripts Used |
|---------------|-------------|-------------|
| §2.3 Coverage (Fig. 2) | Unique functions covered | `librenderservice_boxplot_coverage.py` |
| §3 PMU detection | — | `blink/blink-pmu-detect.cpp` |
| §3 Runtime configuration | — | `blink/configure-blink.cpp` |
| §3 Post-processing | — | `post_process/post-process.py`, `pmu_filter.py` |
| §4.1 Correctness (Fig. 4) | Blink accuracy without ISB | `small_function.py` |
| §4.2 Overhead (Table 1) | Jank distribution | `framedrop/compute_jank_simple.py` |
| §4.3.1 Auto-tuning (Fig. 5) | Base vs. custom flag comparison | `blink/callee_result.py` |
| §4.3.2 Jank investigation | Frame-level cycle attribution | `blink/configure-blink.cpp` (pervasive mode), `post-process.py` |
| §4.3.3 LSEO (Table 2) | Instruction count for `update` function | `post-process.py` (`--compute_self`, ISB enabled) |
| §4.3.4 Test suite (Fig. 6, Table 3) | Blink vs. Perf per-workload comparison | `process_workload.py` (both), `librenderservice_boxplot.py` |

## Notes

- **Hardcoded paths:** Some scripts still contain hardcoded absolute paths (e.g., `hiperf_host` location in `parse_perf.py`, report directories in `librenderservice_boxplot_coverage.py`). These need to be updated to match your environment. The main visualization scripts (`librenderservice_boxplot.py` and `small_function.py`) accept all input paths via command-line arguments — run with `--help` to see options.
- **MIPCodeInfo:** This directory is generated by the BiSheng compiler during compilation with Blink instrumentation flags. It must be saved from the build output directory before any clean build overwrites it.
- **PMU glitching:** The post-processing scripts include glitch detection and filtering logic in `pmu_filter.py`. If corruption is detected, the script will notify the user and the run should be repeated (see Known Issues in `blink/README.md`).
- **Do not run perf alongside Blink:** Running both simultaneously will corrupt PMU counter values.
- The `blink/README.md` file contains additional detail on compile-time setup, runtime phone configuration, and known issues.
