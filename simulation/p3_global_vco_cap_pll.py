#!/usr/bin/env python3
"""Test whether fixed VCO capacitance repairs 5-corner reference PLL lock.

The unmodified 180nm MOS VCO has no 1.8GHz oscillation point in FS over
its usable bias sweep. A separately executed loaded-MOS-VCO scan showed
that additional passive capacitor loading can bring 1.8GHz into the
FS oscillation range. This experiment now checks the SAME CLOSED-LOOP
XSPICE reference PFD / physical MOS switched CP + three-stage VCO
across TT/FF/SS/FS/SF, under ONE common startup bias (.96V), ONE fixed
CP strength (75% original) and ONE identical VCO node capacitor.

The extra capacitors are ideal design variables, NOT actual extracted
parasitics, and the original P3 circuit is NOT being reconstructed.
A lock screen checks reference-phase consistency and physical MOS gate
ripple, not merely an output frequency near 1.8 GHz.
"""
from __future__ import annotations
import argparse,json,shutil,math
from pathlib import Path
import p3_transistor_driver as TX
import p3_xspice_physical_mos_pll as PLL

CORNERS=("tt","ff","ss","fs","sf")
CAPS_FF=(2.,3.,4.,5.)
PUMP_WIDTH_SCALE=.75
INITIAL_BIAS=.96

def circuit(corner,cap):
    src=P.I_SOURCE_W_UM; sink=P.I_SINK_W_UM
    try:
        P.I_SOURCE_W_UM=src*PUMP_WIDTH_SCALE
        P.I_SINK_W_UM=sink*PUMP_WIDTH_SCALE
        deck=P.circuit(63,corner=corner,initial_bias=INITIAL_BIAS)
    finally:
        P.I_SOURCE_W_UM=src
        P.I_SINK_W_UM=sink
    extra=[
      f"* Add fixed {cap:g}fF load to each physical ring oscillator stage"]
    for i in range(1,4):
        extra.append(f"CEXTRA_VCO{i} n{i} 0 {cap:g}f")
    return deck.replace(".control","\n".join(extra)+"\n.control",1)

# Alias avoids changing underlying PLL helper's global variables.
P=PLL

def run(out,corner,cap):
    if corner not in CORNERS or cap not in CAPS_FF:raise ValueError
    out.mkdir(parents=True,exist_ok=True)
    work=TX.ENGINE_DIR/f"p3_global_VCO_C_{corner}_{int(cap)}"
    sim=TX.SpiceRunner(work)
    model=TX.model_path(corner);target=work/model.name
    if not target.exists() or model.stat().st_mtime>target.stat().st_mtime:
        shutil.copy2(model,target)
    status={"corner":corner,"extra_cap_fF_per_stage":cap,
       "nominal_existing_stage_cap_fF":2.,
       "pump_current_width_scale":PUMP_WIDTH_SCALE,
       "shared_initial_gate_bias_V":INITIAL_BIAS,
       "original_2004_ring_sizing_or_parasitics":False,
       "real_MOS":"DB HiTek 180nm SVT MOS switched CP and three-stage ring VCO",
       "behavioral":"XSPICE PFD and divided 450MHz ideal reference",
    }
    try:
        sim.run(circuit(corner,cap),f"physical_{corner}_{int(cap)}fF")
        rows=P.read(work/"physical_pll.csv")
        met=P.metrics(rows)
        met.update(P.aligned_phase_errors_ps(rows))
        freq=met.get("vco_GHz")
        ppm=(freq/1.8-1)*1e6 if freq is not None else None
        passed=bool(ppm is not None and abs(ppm)<1500 and
          met.get("std_phase_ps") is not None and met["std_phase_ps"]<8 and
          met["physical_vco_gate_ripple_mV"]<5 and
          met.get("n_reference_edges",0)>=25)
        status.update({"status":"simulated","frequency_ppm":ppm,
                       "electrical_lock_screen_pass":passed,
                       "measured":met})
    except Exception as e:
        status.update({"status":"simulation_failed",
                       "electrical_lock_screen_pass":False,
                       "error":f"{type(e).__name__}: {str(e)[-1500:]}"})
    (out/f"{corner}_{int(cap)}fF.json").write_text(json.dumps(status,indent=2)+"\n")
    m=status.get("measured",{})
    print(f"GLOBAL_VCO_CAP_PLL corner={corner} add_cap_fF={cap} "
          f"pump_scale={PUMP_WIDTH_SCALE} status={status['status']} "
          f"frequency_GHz={m.get('vco_GHz')} "
          f"phase_std_ps={m.get('std_phase_ps')} "
          f"gate_ripple_mV={m.get('physical_vco_gate_ripple_mV')} "
          f"pass={status['electrical_lock_screen_pass']}",flush=True)
    return status

if __name__=="__main__":
    parser=argparse.ArgumentParser()
    parser.add_argument("--corner",choices=CORNERS,required=True)
    parser.add_argument("--cap",type=float,choices=CAPS_FF,required=True)
    parser.add_argument("--out",type=Path,default=Path("results/spice/p3_global_VCO_cap_PLL"))
    a=parser.parse_args()
    run(a.out,a.corner,a.cap)
