import unittest

from rtl_intel.parser import VerilogParser


class ParserTests(unittest.TestCase):
    def test_parses_ansi_ports_assignments_and_instances(self):
        source = """
module child(input logic a, output logic y);
  assign y = a;
endmodule

module top(input logic source, output logic sink);
  logic link;
  child u_child(.a(source), .y(link));
  assign sink = link;
endmodule
"""
        modules, issues = VerilogParser().parse_text(source, "design.sv")

        self.assertEqual([], issues)
        self.assertEqual(["child", "top"], [module.name for module in modules])
        self.assertEqual(["a", "y"], [port.name for port in modules[0].ports])
        self.assertEqual("u_child", modules[1].instances[0].name)
        self.assertEqual("source", modules[1].instances[0].connections["a"])
        self.assertEqual("sink", modules[1].continuous_assignments[0].target)

    def test_classifies_always_blocks_and_assignments(self):
        source = """
module blocks(input logic clk, input logic d, output logic q, output logic c);
  always_ff @(posedge clk) begin
    q <= d;
    c <= q;
  end
  always_comb begin
    c = d;
  end
endmodule
"""
        modules, issues = VerilogParser().parse_text(source)

        self.assertFalse(issues)
        blocks = modules[0].procedural_blocks
        self.assertEqual(["sequential", "combinational"], [block.kind for block in blocks])
        self.assertEqual(["<=", "="], [block.assignments[0].operator for block in blocks])
        self.assertEqual(2, len(blocks[0].assignments))

    def test_reports_missing_endmodule(self):
        modules, issues = VerilogParser().parse_text("module broken(input a);", "broken.v")

        self.assertFalse(modules)
        self.assertEqual("PARSE_MISSING_ENDMODULE", issues[0].rule)

    def test_parses_classic_verilog_ports_and_always_star(self):
        source = """
module mux(a, b, select, y);
  input a, b, select;
  output reg y;
  always @* begin
    y = select ? b : a;
  end
endmodule
"""
        modules, issues = VerilogParser().parse_text(source, "mux.v")

        self.assertFalse(issues)
        self.assertEqual(["a", "b", "select", "y"], [port.name for port in modules[0].ports])
        self.assertEqual("combinational", modules[0].procedural_blocks[0].kind)
        self.assertEqual("y", modules[0].procedural_blocks[0].assignments[0].target)


if __name__ == "__main__":
    unittest.main()
