#!/bin/bash

# Script to apply test updates
# Run from project root: bash apply_test_updates.sh

set -e

echo "🔧 Applying test updates..."

# Backup original files
echo "📦 Creating backups..."
cp tests/conftest.py tests/conftest.py.bak
cp tests/services/conftest.py tests/services/conftest.py.bak

# Apply new files
echo "📝 Applying new test files..."
mv tests/conftest_new.py tests/conftest.py
mv tests/services/conftest_new.py tests/services/conftest.py
mv tests/services/test_subfinder_service_new.py tests/services/test_subfinder_service.py
mv tests/README_new.md tests/README.md

echo "✅ Test updates applied!"
echo ""
echo "🧪 Run tests with:"
echo "  pytest tests/ -v"
echo ""
echo "📊 Run with coverage:"
echo "  pytest --cov=src --cov-report=html tests/"
echo ""
echo "🔄 To rollback:"
echo "  mv tests/conftest.py.bak tests/conftest.py"
echo "  mv tests/services/conftest.py.bak tests/services/conftest.py"
