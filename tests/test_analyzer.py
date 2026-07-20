import tempfile
import unittest
from pathlib import Path

from rtl_intel.analyzer import analyze_paths


class AnalyzerTests(unittest.TestCase):
    def analyze(self, source: str):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        path = Path(directory.name) / "design.sv"
        path.write_text(source, encoding="utf-8")
        return analyze_paths([path])

    def test_detects_core_lint_rules(self):
        report = self.analyze(
            """
module bad(input logic clk, input logic en, output logic q, output logic comb);
  logic unused;
  always_ff @(posedge clk) begin
    q = comb;
  end
  always_comb begin
    if (en) comb <= 1'b1;
  end
endmodule
"""
        )
        rules = {issue.rule for issue in report.issues}

        self.assertIn("UNUSED_SIGNAL", rules)
        self.assertIn("BLOCKING_IN_SEQUENTIAL", rules)
        self.assertIn("NONBLOCKING_IN_COMBINATIONAL", rules)
        self.assertIn("POSSIBLE_LATCH", rules)

    def test_detects_undriven_output_and_read_signal(self):
        report = self.analyze(
            """
module missing(output logic y, output logic other);
  wire source;
  assign y = source;
endmodule
"""
        )
        rules_by_signal = {(issue.rule, issue.signal) for issue in report.issues}

        self.assertIn(("UNDRIVEN_SIGNAL", "source"), rules_by_signal)
        self.assertIn(("UNDRIVEN_OUTPUT", "other"), rules_by_signal)

    def test_complete_combinational_assignments_do_not_report_latch(self):
        report = self.analyze(
            """
module complete(input logic select, input logic a, input logic b, output logic y);
  always_comb begin
    if (select) y = a;
    else y = b;
  end
endmodule
"""
        )

        self.assertNotIn("POSSIBLE_LATCH", {issue.rule for issue in report.issues})

    def test_unconditional_assignment_after_case_does_not_report_latch(self):
        report = self.analyze(
            """
module post_default(input logic [1:0] select, input logic a, output logic y, output logic z);
  always_comb begin
    case (select)
      2'b00: y = a;
      default: y = 1'b0;
    endcase
    z = y;
  end
endmodule
"""
        )

        latch_signals = {issue.signal for issue in report.issues if issue.rule == "POSSIBLE_LATCH"}
        self.assertNotIn("z", latch_signals)


if __name__ == "__main__":
    unittest.main()
