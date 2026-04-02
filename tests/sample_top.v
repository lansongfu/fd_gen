// Top-level netlist for FD Generator testing
// This file contains SOC_IGT comment list for FD detection

module top (
    input  wire        clk,
    input  wire [31:0] awaddr_in,
    output wire [31:0] awaddr_out,
    output wire        awvalid_out,
    input  wire        awready_in
);

    // ------------ begin SOC_IGT comment list ------------//
    //INSTANCE(../crg/core_crg.v, CORE_CRG, U_CORE_CRG);
    //CONNECT(i, clk, U_CORE_CRG`clki, 1, i);
    //CONNECT(o, clko, U_CORE_CRG`clko, 1, o);
    //CONNECT(w, awaddr, U_CORE_CRG`awaddr, 32, o);
    //CONNECT(w, awvalid, U_CORE_CRG`awvalid, 1, o);
    //CONNECT(w, awready, U_CORE_CRG`awready, 1, i);
    
    //INSTANCE(../module1/module1.v, MODULE1, U_MODULE1);
    //CONNECT(w, awaddr, U_MODULE1`awaddr, 32, i);
    //CONNECT(w, awvalid, U_MODULE1`awvalid, 1, i);
    //CONNECT(w, awready, U_MODULE1`awready, 1, o);
    
    //INSTANCE(../module2/module2.v, MODULE2, U_MODULE2);
    //CONNECT(w, awaddr, U_MODULE2`awaddr, 32, i);
    //CONNECT(w, awvalid, U_MODULE2`awvalid, 1, i);
    //CONNECT(w, awready, U_MODULE2`awready, 1, o);
    
    //INSTANCE(../module3/module3.v, MODULE3, U_MODULE3);
    //CONNECT(w, awaddr, U_MODULE3`awaddr, 32, i);
    //CONNECT(w, awvalid, U_MODULE3`awvalid, 1, i);
    //CONNECT(w, awready, U_MODULE3`awready, 1, o);
    // ------------ end SOC_IGT comment list ------------//
    
    // Regular Verilog code (should be ignored by parser)
    CORE_CRG U_CORE_CRG (
        .clki(clk),
        .clko(clko),
        .awaddr(awaddr),
        .awvalid(awvalid),
        .awready(awready)
    );
    
    MODULE1 U_MODULE1 (
        .awaddr(awaddr),
        .awvalid(awvalid),
        .awready(awready)
    );
    
    MODULE2 U_MODULE2 (
        .awaddr(awaddr),
        .awvalid(awvalid),
        .awready(awready)
    );
    
    MODULE3 U_MODULE3 (
        .awaddr(awaddr),
        .awvalid(awvalid),
        .awready(awready)
    );
    
    assign awaddr_out = awaddr;
    assign awvalid_out = awvalid;
    assign awready_in = awready;

endmodule
