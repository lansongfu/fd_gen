// Large-scale test - 10 modules, 4-level FD chain
// Signal 'sig_long' connects M1 to M6, but they are not adjacent
// Must pass through M2->M3->M4->M5 (4 intermediate modules)

module top (
    input  wire        clk,
    input  wire [31:0] data_in,
    output wire [31:0] data_out
);

    // ------------ begin SOC_IGT comment list ------------//
    //INSTANCE(../m1.v, M1, U_M1);
    //CONNECT(i, clk, U_M1`clk, 1, i);
    //CONNECT(i, data_in, U_M1`data_in, 32, i);
    //CONNECT(w, sig_long, U_M1`data_out, 32, o);
    
    //INSTANCE(../m2.v, M2, U_M2);
    //CONNECT(w, sig_long, U_M2`pass, 32, i);
    //CONNECT(w, sig_long, U_M2`pass, 32, o);
    
    //INSTANCE(../m3.v, M3, U_M3);
    //CONNECT(w, sig_long, U_M3`pass, 32, i);
    //CONNECT(w, sig_long, U_M3`pass, 32, o);
    
    //INSTANCE(../m4.v, M4, U_M4);
    //CONNECT(w, sig_long, U_M4`pass, 32, i);
    //CONNECT(w, sig_long, U_M4`pass, 32, o);
    
    //INSTANCE(../m5.v, M5, U_M5);
    //CONNECT(w, sig_long, U_M5`pass, 32, i);
    //CONNECT(w, sig_long, U_M5`pass, 32, o);
    
    //INSTANCE(../m6.v, M6, U_M6);
    //CONNECT(w, sig_long, U_M6`data_in, 32, i);
    //CONNECT(o, data_out, U_M6`data_out, 32, o);
    // ------------ end SOC_IGT comment list ------------//

endmodule
