#!/usr/bin/env python3
"""Fixed candidate MOS PLL full-PVT cross-condition screening (stage 1).

Select *one common design* and test nine PVT sentinels before any
21-case electrical qualification. DB HiTek 180nm MOS CP/VCO, 450-MHz
XSPICE reference PFD/4, 1.02V start and 3fF per ring node remain
unchanged. Modify ONLY PMOS current-source control and RZERO.
Separate source-bias implementations:
  fixed_080: ideal fixed 0.80V gate, RZERO=1k.
  fixed_070: ideal fixed 0.70V gate, RZERO=1k.
  tracked_091: ideal VDD-referenced Vsg=0.91V, RZERO=1k.
  tracked_graded: ideal affine supply gate=.833333*VDD-.625,
                  giving 0.80V at VDD1.71 and 0.95V at VDD1.89,
                  RZERO=1k.
This is an exploration of topology / headroom; a supply-tracking
B-source is NOT a physical MOS bandgap or bias circuit.
No per-corner model PDK data is exposed in artifacts.
"""
from __future__ import annotations
import argparse,json
from pathlib import Path
import p3_pll_extended_pvt_phase as TEST

SCENARIOS={
 "ss_low":("ss",27.,1.71),
 "ss_cold":("ss",-20.,1.80),
 "ss_nominal":("ss",27.,1.80),
 "ff_high":("ff",27.,1.89),
 "ff_cold":("ff",-20.,1.80),
 "ff_nominal":("ff",27.,1.80),
 "tt_nominal":("tt",27.,1.80),
 "fs_nominal":("fs",27.,1.80),
 "sf_nominal":("sf",27.,1.80),
}
DESIGNS=("fixed_080","fixed_070","tracked_091","tracked_graded")
RZERO=1000

def patch(d,design):
    b="VBPMOS pbias 0 .95"
    assert d.count(b)==1,"Source bias unique"
    new={
      "fixed_080":"VBPMOS pbias 0 DC 0.80",
      "fixed_070":"VBPMOS pbias 0 DC 0.70",
      "tracked_091":"BPMOSCTRL pbias 0 V={v(vdd)-.91}",
      "tracked_graded":"BPMOSCTRL pbias 0 V={.83333333333*v(vdd)-.625}",
    }[design]
    d=d.replace(b,new)
    old="RZERO loopctrl lpcap 2k"
    assert d.count(old)==1
    return d.replace(old,f"RZERO loopctrl lpcap {RZERO}",1)

def run(out,design,scenario):
    if design not in DESIGNS or scenario not in SCENARIOS:raise ValueError
    out.mkdir(parents=True,exist_ok=True)
    corner,temp,vdd=SCENARIOS[scenario]
    original=TEST.deck
    try:
        TEST.deck=lambda c,t,v:patch(original(c,t,v),design)
        result=TEST.main(out/design/scenario,corner,temp,vdd)
    finally:
        TEST.deck=original
    m=result.get("measured",{})
    summ={
      "common_design":design,"PVT_case":scenario,
      "process_corner":corner,"temperature_C":temp,"supply_V":vdd,
      "MOS_CP_source_gate_bias_model":"fixed DC or supply-tracking ideal behavior; not physical bias generator",
      "MOS_Cp_current_width_scale":TEST.CP_SCALE,
      "MOS_ring_added_load_fF":TEST.EXTRA_FF,
      "initial_control_V":TEST.INITIAL,
      "physical_PLL_reference_MHz":450.,
      "test_loop_Rzero_ohm":RZERO,
      "simulator_status":result["sim_status"],
      "electrical_qualified":result["passes_extended_screen"],
      "frequency_GHz":m.get("vco_GHz"),
      "phase_std_ps":m.get("std_phase_ps"),
      "ripple_mVpp":m.get("physical_vco_gate_ripple_mV"),
      "ref_cycle_slips":result.get("window_checks",[{}])[-1].get("bad_four_to_one_reference_intervals"),
      "span_MHz":result.get("interwindow_frequency_span_MHz"),
      "original_2004_P3_PLL":False,
    }
    (out/design/scenario/"cross_pvt_summary.json").write_text(json.dumps(summ,indent=2)+"\n")
    print(f"P3_GLOBAL_PVT_CANDIDATE design={design} case={scenario} "
          f"f_GHz={summ['frequency_GHz']} phaseSTD_ps={summ['phase_std_ps']} "
          f"ripple_mVpp={summ['ripple_mVpp']} slips={summ['ref_cycle_slips']} "
          f"span_MHz={summ['span_MHz']} pass={summ['electrical_qualified']}",flush=True)
    return summ

if __name__=="__main__":
    p=argparse.ArgumentParser()
    p.add_argument("--design",choices=DESIGNS,required=True)
    p.add_argument("--scenario",choices=SCENARIOS,required=True)
    p.add_argument("--out",type=Path,default=Path("results/spice/p3_global_PVT_candidate"))
    a=p.parse_args()
    run(a.out,a.design,a.scenario)
