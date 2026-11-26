// BUG (intended): y is driven by two continuous assignments
module top(input a, input b, output y);
  assign y = a;
  assign y = b;
endmodule
