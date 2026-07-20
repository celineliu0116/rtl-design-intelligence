import tempfile
import unittest
from pathlib import Path

from rtl_intel.analyzer import analyze_paths


class HierarchyTests(unittest.TestCase):
    def test_builds_nested_hierarchy_and_tracks_unknown_modules(self):
        source = """
module leaf(input logic a, output logic y);
  assign y = a;
endmodule
module middle(input logic a, output logic y);
  leaf u_leaf(.a(a), .y(y));
endmodule
module top(input logic a, output logic y);
  middle u_middle(.a(a), .y(y));
  vendor_ip u_ip(.clock(a));
endmodule
"""
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "hierarchy.sv"
            path.write_text(source, encoding="utf-8")
            report = analyze_paths([path])

        self.assertEqual(["top"], report.hierarchy["root_modules"])
        middle = report.hierarchy["roots"][0]["children"][0]
        self.assertEqual("middle", middle["module"])
        self.assertEqual("leaf", middle["children"][0]["module"])
        self.assertEqual("vendor_ip", report.hierarchy["unresolved_instances"][0]["module_type"])
        self.assertIn("UNKNOWN_MODULE", {issue.rule for issue in report.issues})


if __name__ == "__main__":
    unittest.main()

