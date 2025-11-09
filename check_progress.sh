#!/bin/bash
# Quick script to check multi-year comparison progress

echo "==================== PROCESS STATUS ===================="
ps aux | grep "run_multi_year_comparison.py" | grep -v grep
echo ""

echo "==================== LATEST LOGS ===================="
tail -20 multi_year_run.log
echo ""

echo "==================== COMPLETED BACKTESTS ===================="
if [ -d "reports/multi_year_comparison" ]; then
    ls -la reports/multi_year_comparison/*/summary_tp40.csv 2>/dev/null | wc -l | xargs echo "Completed:"
    echo ""
    echo "Directories:"
    ls -d reports/multi_year_comparison/*/ 2>/dev/null | tail -5
else
    echo "No results yet"
fi
