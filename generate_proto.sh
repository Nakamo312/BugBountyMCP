#!/bin/bash
set -e

cd playwright
python -m grpc_tools.protoc -I. --python_out=../src/api/infrastructure/runners --grpc_python_out=../src/api/infrastructure/runners scanner.proto
echo "Proto files generated successfully"
