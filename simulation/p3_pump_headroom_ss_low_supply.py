#!/usr/bin/env python3
"""SS low-supply MOS charge-pump headroom / bias DOE.

This is an actual DB HiTek 180nm MOS closed reference PLL transient
with XSPICE 450MHz PFD and real 7-bit switched MOS charge pump and VCO.
Same fixed original reconstruction: CP width 82.5%, +3fF/stage VCO,
1.02V startup and 40pF loop capacitor. Only physical CP NMOS/PMOS
bias source and loop resistor are swept. 27C, SS and VDD=1.71V.
Output explicitly preserves failures as negative evidence.
There is no original-paper complete CDR nor measured phase noise.
"""
from __future__ import annotations
import argparse,json
from pathlib import Path
import p3_pll_extended_pvt_phase as TEST

PBIAS=(.70,.80,.90,1.00)
NBIAS=(.48,.58,.68,.78)
RZERO_OHM=(1000,2000)
INIT_V=1.02
CASE=("ss",27.,1.71)

def main(out,pbias,nbias,rzero):
    if pbias not in PBIAS or nbias not in NBIAS or rzero not in RZERO_OHM:
        raise ValueError("Input must belong to fixed DOE")
    out.mkdir(parents=True,exist_ok=True)
    original=TEST.deck
    def patched(c,t,v):
        d=original(c,t,v)
        target={"VBPMOS pbias 0 .95":f"VBPMOS pbias 0 {pbias:g}",
                "VBNMOS nbias 0 .68":f"VBNMOS nbias 0 {nbias:g}",
                "RZERO loopctrl lpcap 2k":f"RZERO loopctrl lpcap {rzero:g}"}
        for a,b in target.items():
            if d.count(a)!=1:raise RuntimeError(f"Expected one {a}")
            d=d.replace(a,b,1)
        return d
    try:
        TEST.deck=patched
        name=f"P{pbias:.2f}_N{nbias:.2f}_R{rzero}"
        result=TEST.main(out/name,*CASE)
    finally:
        TEST.deck=original
    m=result.get("measured",{})
    evidence={
      "experiment":"physical MOS CP bias input headroom at SS -5% supply",
      "physical":"180nm switched MOS CP, 3-stage VCO; 450MHz XSPICE reference PFD",
      "corner":"ss","temp_C":27,"supply_V":1.71,
      "constant_pump_width_scale":TEST.CP_SCALE,
      "extra_stage_cap_fF":TEST.EXTRA_FF,
      "shared_initial_control_V":INIT_V,
      "pump_PMOS_bias_V":pbias,"pump_NMOS_bias_V":nbias,
      "loop_Rzero_ohm":rzero,
      "locked_under_predefined_extended_screen":result["passes_extended_screen"],
      "frequency_GHz":m.get("vco_GHz"),
      "phase_std_ps":m.get("std_phase_ps"),
      "gate_ripple_mVpp":m.get("physical_vco_gate_ripple_mV"),
      "cycle_slips":result.get("window_checks",[{}])[-1].get("bad_four_to_one_reference_intervals"),
      "window_frequency_span_MHz":result.get("interwindow_frequency_span_MHz"),
      "error":result.get("error"),
      "not_original_2004_transceiver_or_data_CDR":True
    }
    (out/name/"cp_headroom_summary.json").write_text(json.dumps(evidence,indent=2)+"\n")
    print(f"CP_HEADROOM_SS_VDD171 PMOSbias={pbias:.2f} NMOSbias={nbias:.2f} "
          f"Rzero={rzero} f_GHz={evidence['frequency_GHz']} "
          f"phase_ps={evidence['phase_std_ps']} "
          f"slips={evidence['cycle_slips']} "
          f"ripple_mVpp={evidence['gate_ripple_mVpp']} "
          f"pass={evidence['locked_under_predefined_extended_screen']}",flush=True)
    return evidence

if __name__=="__main__":
    p=argparse.ArgumentParser()
    p.add_argument("--pbias",type=float,choices=PBIAS,required=True)
    p.add_argument("--nbias",type=float,choices=NBIAS,required=True)
    p.add_argument("--rzero",type=int,choices=RZERO_OHM,required=True)
    p.add_argument("--out",type=Path,default=Path("results/spice/p3_pump_SS_headroom"))
    a=p.parse_args()
    main(a.out,a.pbias,a.nbias,a.rzero)
