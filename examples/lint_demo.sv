// This file intentionally contains one example of each primary lint finding.
module lint_demo (
    input  logic clk,
    input  logic enable,
    input  logic unused_input,
    output logic latched_value,
    output logic sequential_value,
    output logic never_driven
);
    wire unused_wire;
    logic source_without_driver;

    // Missing else/default assignment can infer a latch.
    always_comb begin
        if (enable)
            latched_value = source_without_driver;
    end

    // Clocked logic should normally use <=.
    always_ff @(posedge clk) begin
        sequential_value = latched_value;
    end
endmodule

