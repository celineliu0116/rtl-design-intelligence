module sync_fifo #(
    parameter int WIDTH = 8,
    parameter int DEPTH = 4,
    parameter int PTR_WIDTH = $clog2(DEPTH)
) (
    input  logic             clk,
    input  logic             rst_n,
    input  logic             write_en,
    input  logic             read_en,
    input  logic [WIDTH-1:0] write_data,
    output logic [WIDTH-1:0] read_data,
    output logic             full,
    output logic             empty
);
    logic [WIDTH-1:0] mem [0:DEPTH-1];
    logic [PTR_WIDTH-1:0] write_ptr;
    logic [PTR_WIDTH-1:0] read_ptr;
    logic [PTR_WIDTH:0] count;

    assign empty = (count == 0);
    assign full = (count == DEPTH);
    assign read_data = mem[read_ptr];

    always_ff @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            write_ptr <= '0;
            read_ptr <= '0;
            count <= '0;
        end else begin
            if (write_en && !full) begin
                mem[write_ptr] <= write_data;
                write_ptr <= write_ptr + 1'b1;
            end
            if (read_en && !empty) begin
                read_ptr <= read_ptr + 1'b1;
            end
            case ({write_en && !full, read_en && !empty})
                2'b10: count <= count + 1'b1;
                2'b01: count <= count - 1'b1;
                default: count <= count;
            endcase
        end
    end
endmodule

