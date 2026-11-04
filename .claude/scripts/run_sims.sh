#!/bin/bash
# Run all keyboardtest simulations in a pseudo terminal and check the expected results.
# Usage: run_sims.sh [output-dir]      (default: a new temp dir)
# Exit code 0 = all as expected.
set -u
HERE="$(cd "$(dirname "$0")" && pwd)"
OUT="${1:-$(mktemp -d -t kbdsim-XXXXXX)}"
mkdir -p "$OUT"
cd "$OUT" || exit 1
export TERM=xterm-256color
fail=0

run_pty() {   # run a python script inside a 100x32 pty, output to log file
    local log="$1"; shift
    timeout 120 script -qc "stty cols 100 rows 32; python3 -I $*" /dev/null > "$log" 2>&1
}

python3 -m py_compile "$HERE/../../keyboardtest.py" && rm -rf "$HERE/../../__pycache__" \
    || { echo "FAIL: keyboardtest.py does not compile"; exit 1; }

# 1) unit checks: orphan scancode decoding + early press
run_pty unit.log "$HERE/test_scan_and_early.py"
dec=$(tr -d '\033' < unit.log | grep -a '^decoded:')
early=$(tr -d '\033' < unit.log | grep -a -E '^T PASS True')
echo "$dec"
if [[ "$dec" == *"('KEY_ENTER', 0, '0x1c', True)"* && "$dec" == *"SCAN_6d"* && -n "$early" ]]; then
    echo "OK   unit checks (orphan scan -> real key, unmapped -> SCAN_xx, early press)"
else
    echo "FAIL unit checks - see $OUT/unit.log"; fail=1
fi

# 2) full simulated run with deliberate faults (expected 83/86, failed Screen, Q, W)
rm -rf reports
run_pty full.log "$HERE/sim_full_run.py" "$OUT/reports"
rep=$(ls -t reports/*.txt 2>/dev/null | head -1)
if [[ -z "$rep" ]]; then
    echo "FAIL full run produced no report - see $OUT/full.log"; tr -d '\033' < full.log | grep -a -E 'Error|Traceback' | head -5
    fail=1
else
    grep -E '^(Keys passed|Failed keys)' "$rep"
    if grep -q '^Keys passed   : 83 / 86' "$rep" && grep -q '^Failed keys   : Screen, Q, W' "$rep"; then
        echo "OK   full run (deliberate faults detected, everything else passed)"
    else
        echo "FAIL full run - unexpected result, see $rep"; fail=1
    fi
fi

echo "output: $OUT"
exit $fail
