// BUG (intended): q_next is not assigned when en == 0 -> latch inferred
module top(input en, input [7:0] d, output reg [7:0] q_next);
  always @(*) begin
    if (en) q_next = d;
  end
endmodule
