#!/usr/bin/env bash
# Local-only DB HiTek 180-nm 1.8-V SVT smoke test.
# Use in a Codespace/workstation ONLY if the foundry license permits
# storing and using model files there. This does not commit PDK bytes.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PDK_DIR="$ROOT/pdk_private"
ZIP="${1:-$ROOT/P3_DBHitek180_1p8V_SVT_Local_Model_Subset.zip}"
MODEL="$PDK_DIR/db180_svt018_tt.lib"
CIR="$PDK_DIR/smoke_ngspice_inverter.cir"
LOG="$PDK_DIR/smoke_ngspice.log"

command -v ngspice >/dev/null || { echo "ERROR: ngspice not installed"; exit 2; }

if [[ ! -f "$MODEL" || ! -f "$CIR" ]]; then
    if [[ ! -f "$ZIP" ]]; then
        echo "MISSING: $MODEL / $CIR"
        echo "Upload the local-only P3_DBHitek180_1p8V_SVT_Local_Model_Subset.zip to the repository folder in Codespaces."
        echo "Then run: bash scripts/run_dbhitek_smoke.sh"
        echo "Do NOT git add/commit the foundry model archive or extracted .lib files."
        exit 2
    fi
    command -v unzip >/dev/null || { echo "ERROR: unzip not installed"; exit 2; }
    mkdir -p "$PDK_DIR"
    unzip -oq "$ZIP" -d "$PDK_DIR"
fi

if [[ ! -f "$PDK_DIR/.spiceinit" ]]; then
    printf '%s\n' "set ngbehavior=hs" > "$PDK_DIR/.spiceinit"
fi

echo "ngspice: $(ngspice --version | grep -m1 -i ngspice || true)"
echo "Run directory: $PDK_DIR"
echo "Model and circuit: found"
set +e
(cd "$PDK_DIR" && ngspice -b smoke_ngspice_inverter.cir > smoke_ngspice.log 2>&1)
STATUS=$?
set -e
echo
echo "---- Last 50 log lines ----"
tail -n 50 "$LOG"
echo "---------------------------"
echo "ngspice process exit: $STATUS"

if [[ -s "$PDK_DIR/inverter_transient.csv" ]]; then
    echo "Transient output exists: $PDK_DIR/inverter_transient.csv"
    echo "IMPORTANT: inspect log for model parse errors, unknown params, or convergence issues."
else
    echo "No valid transient CSV was produced. Check the log above."
    exit 3
fi
if [[ $STATUS -ne 0 ]] || grep -Eiq '(^|[[:space:]])(error:|fatal:)|cannot open|no such file|unknown subcircuit|unknown model' "$LOG"; then
    echo "Potential model or simulation error detected. Review full log."
    exit 4
fi
echo "Smoke test produced data; electrical plausibility and HSPICE equivalence still require checking."
