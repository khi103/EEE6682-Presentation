#!/usr/bin/env python3
"""All 45 process/temperature/supply combinations for physical 180nm MOS PLL.

The prior 42-run study independently passed two fixed real-diode-PMOS
bias designs in 21 PVT conditions each, but it did NOT jointly cross
every voltage with every temperature. This completes exactly 5 process
corners x 3 temperatures x 3 core supply voltages = 45 conditions for
each of the SAME two fixed circuit designs, without case-specific
optimization or warm-start substitution.

Actual MOS PFD charge-pump switches, diode-connected MOS PMOS bias,
MOS VCO and reference clock XSPICE PFD/4 simulate in ngspice. The
reference 450MHz clock is ideal and the reconstructed 2004 ASIC does
not use the same foundry PDK. A PASS is confined to the five declared
frequency/phase/ripple/continuity/drift criteria, not random jitter,
mismatch, phase-noise, BER or end-to-end transceiver PVT.
"""
from __future__ import annotations
import argparse,json
from pathlib import Path
import p3_real_mos_bias_full_pvt as BASE

DESIGNS=BASE.DESIGNS
CORNERS=BASE.CORNERS
TEMPS=BASE.TEMPS
VDDS=BASE.VDDS

def main(out,design,corner,temp,vdd):
    r=BASE.run(out,design,corner,temp,vdd)
    summary={
        "design":design,"corner":corner,"temp_C":temp,
        "VDD_V":vdd,
        "full_cartesian_5x3x3":True,
        "one_invariant_circuit_across_all_PVT":True,
        "electrical_screen_pass":r["electrical_screen_passed"],
        "deterministic_MOS_PLL_only":True,
        "actual_original_P3_silicon":False,
        "measured":r,
    }
    file=out/design/(f"grid_{corner}_T{temp:+.0f}_V{vdd:.2f}".replace(".","p")+".json")
    file.write_text(json.dumps(summary,indent=2)+"\n")
    print(
       f"FULL_GRID_PVT design={design} corner={corner} temp_C={temp:g} "
       f"VDD_V={vdd:.2f} f_GHz={r['VCO_frequency_GHz']} "
       f"phase_ps={r['reference_phase_std_ps']} "
       f"gate_ripple_mVpp={r['physical_VCO_gate_ripple_mVpp']} "
       f"late_drift_MHz={r['last_disjoint_window_freq_drift_MHz']} "
       f"slips={r['last_reference_cycle_slips']} "
       f"electrical_PASS={r['electrical_screen_passed']}",flush=True)
    return summary

if __name__=="__main__":
    p=argparse.ArgumentParser()
    p.add_argument("--design",choices=DESIGNS,required=True)
    p.add_argument("--corner",choices=CORNERS,required=True)
    p.add_argument("--temp",type=float,choices=TEMPS,required=True)
    p.add_argument("--vdd",type=float,choices=VDDS,required=True)
    p.add_argument("--out",type=Path,
        default=Path("results/spice/p3_complete_45grid_MOS_PVT"))
    a=p.parse_args()
    main(a.out,a.design,a.corner,a.temp,a.vdd)
