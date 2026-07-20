# RTL Intel

RTL Intel is a dependency-free RTL lint and design-intelligence tool for a practical subset of Verilog and SystemVerilog. It finds common design-quality problems, extracts module hierarchy, produces machine-readable JSON, and generates a concise natural-language design overview.

It is intentionally small enough to understand end to end: the project demonstrates parsing, source-aware static analysis, RTL-specific lint rules, hierarchy construction, reporting, CLI design, automated tests, and CI without hiding the core logic behind a parser dependency.

## Features

- Parses modules, ANSI and classic port declarations, signals, continuous assignments, `always`/`always_comb`/`always_ff` blocks, and named or positional module instances.
- Detects unused internal wires/signals and unused input ports.
- Detects undriven outputs and signals that are read without a detected driver.
- Flags possible combinational latches when no default or complete assignment is detected.
- Flags blocking assignments in sequential logic and non-blocking assignments in combinational logic.
- Builds a nested module hierarchy and identifies unresolved child modules and hierarchy cycles.
- Emits a human-readable terminal report or versioned JSON report.
- Produces a deterministic natural-language design summary.
- Includes clean ALU, synchronous FIFO, FSM, and integrated top-level examples, plus an intentionally broken lint demo.
- Runs with Python's standard library only and is covered by unit tests and GitHub Actions.

## Quick start

Python 3.9 or newer is required.

```bash
python -m pip install -e .
rtl-intel examples/alu.sv --summary
```

Analyze a directory and write JSON:

```bash
rtl-intel examples --format json --output rtl-report.json
```

Fail CI when warnings or errors are present:

```bash
rtl-intel rtl/ --fail-on warning
```

Try every primary lint rule with the deliberately faulty example:

```bash
rtl-intel examples/lint_demo.sv --summary
```

The CLI also works without installation while developing:

```bash
PYTHONPATH=src python -m rtl_intel.cli examples/alu.sv
```

## CLI

```text
usage: rtl-intel [-h] [--format {text,json}] [-o OUTPUT] [--summary]
                 [--compact] [--fail-on {never,error,warning}] [--version]
                 [paths ...]
```

Directories are scanned recursively for `.v`, `.sv`, `.vh`, and `.svh` files. Text output includes findings and a hierarchy tree. JSON output always includes the design summary and is suitable for CI artifacts, editor integrations, or a future MCP server.

## Lint rules

| Rule | Severity | Meaning |
| --- | --- | --- |
| `UNUSED_SIGNAL` | warning | Internal signal is never consumed, or is never referenced at all. |
| `UNUSED_INPUT` | info | Input port is not read by module logic. |
| `UNDRIVEN_SIGNAL` | warning | Internal signal is read but has no detected driver. |
| `UNDRIVEN_OUTPUT` | error | Output port has no detected assignment or child output driver. |
| `POSSIBLE_LATCH` | warning | A combinational target lacks a detected default or complete branch assignment. |
| `BLOCKING_IN_SEQUENTIAL` | warning | Clocked logic uses `=` instead of `<=`. |
| `NONBLOCKING_IN_COMBINATIONAL` | warning | Combinational logic uses `<=` instead of `=`. |
| `UNKNOWN_MODULE` | warning | An instance's module definition was not included in the analysis. |
| `DUPLICATE_MODULE` | error | Multiple analyzed files declare the same module name. |

Every issue contains a path, line number, rule, severity, message, module context when available, and a suggested remediation. The JSON schema is versioned with `schema_version: "1.0"`.

## Architecture

```text
RTL files
   -> structural parser (modules, declarations, blocks, instances)
   -> module-aware data-flow and lint passes
   -> hierarchy builder + design summarizer
   -> text or JSON reporter
   -> CLI / future MCP adapter
```

The code is separated into focused modules:

- `parser.py`: comment-safe structural parsing with source locations.
- `analyzer.py`: design orchestration, signal usage, driver analysis, and RTL lint rules.
- `hierarchy.py`: root discovery, recursive instance trees, unresolved references, and cycle guards.
- `reporting.py`: stable JSON and readable terminal rendering.
- `cli.py`: argument handling, file output, and CI exit policies.

## Testing

```bash
python -m unittest discover -s tests -v
```

The suite covers parsing, procedural block classification, all core lint categories, complete combinational assignments, hierarchy extraction, unresolved modules, JSON compatibility, and CLI exit codes. GitHub Actions runs the suite on Python 3.9 and 3.12, then lints the clean integrated example as an end-to-end smoke test.

## Scope and limitations

RTL Intel is an educational static analyzer, not a replacement for a full IEEE 1800 compiler or commercial lint tool. It works best on conventional synthesizable RTL. Preprocessor expansion, packages/interfaces, macros that generate syntax, complex type declarations, escaped identifiers, function-level data flow, and deeply nested branch-completeness proofs are outside the current parser's scope. The latch rule is intentionally conservative and heuristic.

The clean extension path is to keep the reporting models and lint passes while replacing the structural parser with a full AST frontend such as slang or Surelog when production-grade language coverage is needed.

## Roadmap

- Add an MCP server exposing `analyze_rtl`, `get_module`, and `explain_issue` tools.
- Add an optional full-SystemVerilog AST backend.
- Track clock/reset domains and cross-domain signals.
- Generate control/data-flow visualizations.
- Add configurable rule severities and suppression comments.

## Resume bullet

> Developed an RTL analysis tool for Verilog/SystemVerilog that detects common design-quality issues, extracts module hierarchy, and generates structured design summaries for hardware debugging workflows.
