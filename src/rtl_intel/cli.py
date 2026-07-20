"""Command-line interface for rtl-intel."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import List, Optional

from . import __version__
from .analyzer import analyze_paths
from .reporting import render_json, render_text


def build_argument_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="rtl-intel",
        description="Lint Verilog/SystemVerilog and extract module-level design intelligence.",
    )
    parser.add_argument(
        "paths",
        nargs="*",
        default=["."],
        help="RTL files or directories to analyze (default: current directory)",
    )
    parser.add_argument(
        "--format",
        choices=("text", "json"),
        default="text",
        dest="output_format",
        help="Report format (default: text)",
    )
    parser.add_argument("-o", "--output", help="Write the report to a file instead of stdout")
    parser.add_argument(
        "--summary",
        action="store_true",
        help="Include a natural-language design summary in text output (JSON always includes it)",
    )
    parser.add_argument(
        "--compact",
        action="store_true",
        help="Emit compact JSON instead of indented JSON",
    )
    parser.add_argument(
        "--fail-on",
        choices=("never", "error", "warning"),
        default="never",
        help="Return exit status 1 at or above this severity (default: never)",
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    return parser


def main(argv: Optional[List[str]] = None) -> int:
    args = build_argument_parser().parse_args(argv)
    report = analyze_paths(args.paths)
    if args.output_format == "json":
        rendered = render_json(report, pretty=not args.compact)
    else:
        rendered = render_text(report, include_summary=args.summary)

    if args.output:
        output_path = Path(args.output)
        try:
            output_path.parent.mkdir(parents=True, exist_ok=True)
            output_path.write_text(rendered, encoding="utf-8")
        except OSError as error:
            print(f"rtl-intel: could not write {output_path}: {error}", file=sys.stderr)
            return 2
    else:
        sys.stdout.write(rendered)

    severities = {issue.severity for issue in report.issues}
    if args.fail_on == "error" and "error" in severities:
        return 1
    if args.fail_on == "warning" and ({"error", "warning"} & severities):
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
