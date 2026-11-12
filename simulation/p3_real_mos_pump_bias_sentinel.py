#!/usr/bin/env python3
"""Actual 180nm diode-connected PMOS CP-bias generator in closed PLL.

Unlike prior supply-tracked IDEAL B-source, this model has only
a diode-connected foundry PMOS and physical resistor:
 vdd -> diode-PMOS (S/B=vdd, gate/drain=pbias) -> R to GND.
pbias biases the real PMOS switched charge-pump source gate.
All actual MOS CP/VCO sizes, VCO additional 3fF/stage, 1.02V start,
RC loop filter C and 450MHz XSPICE PFD remain fixed.
Both diode sizing and resistor are shared across all corners.
Loop RZERO=1k determined from previously completed FF high-VDD test.

Report true 1.2us MOS transient, phase/ripple, cycle integrity,
and late 3 disjoint 80ns window frequency stability. No original
2004 silicon or full recovered-data CDR claim.
"""
from __future__ import annotations
import argparse,json
from pathlib import Path
import p3_pll_extended_pvt_phase as TEST

DESIGNS={
 "diode_w8_r4k":(8.,4000),
 "diode_w16_r4k":(16.,4000),
 "diode_w8_r8k":(8.,8000),
}
SCENARIOS={
 "ss_low":("ss",27.,1.71),"ss_cold":("ss",-20.,1.8),
 "ss_nominal":("ss",27.,1.8),"ff_high":("ff",27.,1.89),
 "ff_cold":("ff",-20.,1.8),"ff_nominal":("ff",27.,1.8),
 "tt_nominal":("tt",27.,1.8),"fs_nominal":("fs",27.,1.8),
 "sf_nominal":("sf",27.,1.8),
}
LOOP_RZERO_OHM=1000

def patch(deck,design):
    w,r=DESIGNS[design]
    orig="VBPMOS pbias 0 .95"
    if deck.count(orig)!=1:raise RuntimeError("Original CP bias source missing")
    phys=f"XCP_DIODE pbias pbias vdd vdd 0 pch_svt_1p8v width={w:g}u length=.36u multi=1\nRCP_BIAS pbias 0 {r:g}"
    deck=deck.replace(orig,phys)
    orig="RZERO loopctrl lpcap 2k"
    if deck.count(orig)!=1:raise RuntimeError("PLL RZERO missing")
    return deck.replace(orig,f"RZERO loopctrl lpcap {LOOP_RZERO_OHM:g}",1)

def run(out,design,scenario):
    if design not in DESIGNS or scenario not in SCENARIOS:raise ValueError
    corner,temp,vdd=SCENARIOS[scenario]
    out.mkdir(parents=True,exist_ok=True)
    old=TEST.deck
    try:
        TEST.deck=lambda c,t,v:patch(old(c,t,v),design)
        result=TEST.main(out/design/scenario,corner,temp,vdd)
    finally:
        TEST.deck=old
    m=result.get("measured",{})
    width,res=DESIGNS[design]
    item={
      "bias_generator_type":"physical MOS diode and resistor, not B-source",
      "process_model":"DB HiTek 180nm SVT (independent reconstruction)",
      "bias_diode_width_um":width,"bias_resistor_ohm":res,
      "same_design_every_corner":True,
      "RZERO_ohm":LOOP_RZERO_OHM,
      "corner":corner,"temperature_C":temp,"supply_V":vdd,
      "full_2004_P3_chip_identical":False,
      "electrical_screen_passed":result["passes_extended_screen"],
      "frequency_GHz":m.get("vco_GHz"),
      "phase_std_ps":m.get("std_phase_ps"),
      "physical_VCO_control_ripple_mVpp":m.get("physical_vco_gate_ripple_mV"),
      "cycle_slips":result.get("window_checks",[{}])[-1].get("bad_four_to_one_reference_intervals"),
      "window_frequency_span_MHz":result.get("interwindow_frequency_span_MHz"),
      "status":result.get("sim_status"),
      "error":result.get("error"),
    }
    (out/design/scenario/"real_transistor_bias_PLL.json").write_text(json.dumps(item,indent=2)+"\n")
    print(f"PHYSICAL_BIAS_REAL_PLL design={design} case={scenario} "
          f"f_GHz={item['frequency_GHz']} phaseSTD_ps={item['phase_std_ps']} "
          f"gateRipple_mVpp={item['physical_VCO_control_ripple_mVpp']} "
          f"slips={item['cycle_slips']} span_MHz={item['window_frequency_span_MHz']} "
          f"electricalPass={item['electrical_screen_passed']}",flush=True)
    return item

if __name__=="__main__":
    p=argparse.ArgumentParser()
    p.add_argument("--design",choices=DESIGNS,required=True)
    p.add_argument("--scenario",choices=SCENARIOS,required=True)
    p.add_argument("--out",type=Path,
       default=Path("results/spice/p3_physical_pump_bias_sentinel"))
    a=p.parse_args();run(a.out,a.design,a.scenario)
