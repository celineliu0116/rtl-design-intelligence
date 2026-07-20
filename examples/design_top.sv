module design_top (
    input  logic       clk,
    input  logic       rst_n,
    input  logic [7:0] a,
    input  logic [7:0] b,
    input  logic [2:0] alu_op,
    input  logic       fifo_write,
    input  logic       fifo_read,
    input  logic       timer_expired,
    output logic [7:0] alu_result,
    output logic       alu_zero,
    output logic [7:0] fifo_data,
    output logic       fifo_full,
    output logic       fifo_empty,
    output logic       red,
    output logic       yellow,
    output logic       green
);
    alu #(.WIDTH(8)) u_alu (
        .a(a),
        .b(b),
        .op(alu_op),
        .result(alu_result),
        .zero(alu_zero)
    );

    sync_fifo #(.WIDTH(8), .DEPTH(4)) u_fifo (
        .clk(clk),
        .rst_n(rst_n),
        .write_en(fifo_write),
        .read_en(fifo_read),
        .write_data(alu_result),
        .read_data(fifo_data),
        .full(fifo_full),
        .empty(fifo_empty)
    );

    traffic_fsm u_fsm (
        .clk(clk),
        .rst_n(rst_n),
        .timer_expired(timer_expired),
        .red(red),
        .yellow(yellow),
        .green(green)
    );
endmodule

