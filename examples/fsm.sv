module traffic_fsm (
    input  logic clk,
    input  logic rst_n,
    input  logic timer_expired,
    output logic red,
    output logic yellow,
    output logic green
);
    typedef enum logic [1:0] {
        RED_STATE,
        GREEN_STATE,
        YELLOW_STATE
    } state_t;

    state_t state_q;
    state_t state_d;

    always_comb begin
        state_d = state_q;
        red = 1'b0;
        yellow = 1'b0;
        green = 1'b0;

        unique case (state_q)
            RED_STATE: begin
                red = 1'b1;
                if (timer_expired) state_d = GREEN_STATE;
            end
            GREEN_STATE: begin
                green = 1'b1;
                if (timer_expired) state_d = YELLOW_STATE;
            end
            YELLOW_STATE: begin
                yellow = 1'b1;
                if (timer_expired) state_d = RED_STATE;
            end
            default: state_d = RED_STATE;
        endcase
    end

    always_ff @(posedge clk or negedge rst_n) begin
        if (!rst_n)
            state_q <= RED_STATE;
        else
            state_q <= state_d;
    end
endmodule

