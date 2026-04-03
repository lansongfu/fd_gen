#!/bin/bash
# FD Generator 调试运行脚本
# 用法：./run_fd_debug.sh <top.v> <floorplan.txt> <output_dir>

TOP_FILE=$1
FLOORPLAN=$2
OUTPUT_DIR=$3

echo "Running FD Generator..."
echo "Top: $TOP_FILE"
echo "Floorplan: $FLOORPLAN"
echo "Output: $OUTPUT_DIR"
echo ""

python3 fd_generator.py -top "$TOP_FILE" -floorplan "$FLOORPLAN" -output "$OUTPUT_DIR" -link

echo ""
echo "Done! Check log file: $OUTPUT_DIR/fd_generator.log"
