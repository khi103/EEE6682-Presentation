#!/usr/bin/env bash
# Local-only P3 ngspice smoke test (DO NOT COMMIT PDK model sources).
# This uses a zero-DTEMP ngspice-compat model COPY and keeps the HSPICE
# model and original archive untouched.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PDK_DIR="$ROOT/pdk_private"
ZIP="${1:-$ROOT/P3_DBHitek180_1p8V_SVT_Local_Model_Subset.zip}"
SOURCE="$PDK_DIR/db180_svt018_tt.lib"
SOURCE_CIR="$PDK_DIR/smoke_ngspice_inverter.cir"
RUN_DIR="$PDK_DIR/ngspice_compat"
MODEL="$RUN_DIR/db180_svt018_tt.lib"
CIR="$RUN_DIR/smoke_ngspice_inverter.cir"
LOG="$RUN_DIR/smoke_ngspice.log"
CSV="$RUN_DIR/inverter_transient.csv"

command -v ngspice >/dev/null || { echo "ERROR: ngspice missing"; exit 2; }
command -v python3 >/dev/null || { echo "ERROR: python3 missing"; exit 2; }

if [[ ! -f "$SOURCE" || ! -f "$SOURCE_CIR" ]]; then
    if [[ ! -f "$ZIP" ]]; then
        echo "MISSING local model or netlist: $SOURCE or $SOURCE_CIR"
        echo "Place the authorized subset ZIP in the repository root."
        exit 2
    fi
    command -v unzip >/dev/null || { echo "ERROR: unzip missing"; exit 2; }
    mkdir -p "$PDK_DIR"
    unzip -oq "$ZIP" -d "$PDK_DIR"
fi

mkdir -p "$RUN_DIR"
# Reuse converted files in a persistent Codespace if unchanged.
# Fresh GitHub-hosted Actions runners still reconstruct them per job.
if [[ ! -f "$MODEL" || "$SOURCE" -nt "$MODEL" || "$ROOT/scripts/prepare_ngspice_model.py" -nt "$MODEL" ]]; then
    python3 "$ROOT/scripts/prepare_ngspice_model.py" "$SOURCE" "$MODEL"
else
    echo "Reusing cached local ngspice-compatible model."
fi
if [[ ! -f "$CIR" || "$SOURCE_CIR" -nt "$CIR" ]]; then
    cp "$SOURCE_CIR" "$CIR"
fi
printf '%s\n' "set ngbehavior=hs" > "$RUN_DIR/.spiceinit"
rm -f "$CSV" "$LOG"

echo "ngspice: $(ngspice --version | grep -m1 -i ngspice || true)"
echo "Test copy directory: $RUN_DIR"
echo "HSPICE model source remains unchanged in $PDK_DIR"
set +e
(cd "$RUN_DIR" && ngspice -b smoke_ngspice_inverter.cir > smoke_ngspice.log 2>&1)
STATUS=$?
set -e

echo
echo "---- Last 70 ngspice log lines ----"
tail -n 70 "$LOG"
echo "---------------------------------"
echo "ngspice process exit: $STATUS"

if [[ $STATUS -ne 0 ]] || grep -Eiq '(^|[[:space:]])(error:|fatal:)|cannot open|no such file|unknown subcircuit|unknown model|simulation interrupted' "$LOG"; then
    echo "ERROR: ngspice model loading or simulation failed."
    exit 4
fi
if [[ ! -s "$CSV" ]]; then
    echo "ERROR: transient waveform CSV not generated."
    exit 3
fi
echo "Transient waveform CSV: $CSV"
echo "Smoke test completed without fatal errors. Next: check inverter"
echo "waveform plausibility, skipped parameter warnings, and HSPICE equivalence."
