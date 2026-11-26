// BUG (intended): 'mask' is read but never driven
module top(input [7:0] a, output [7:0] y);
  wire [7:0] mask;
  assign y = a & mask;
endmodule
