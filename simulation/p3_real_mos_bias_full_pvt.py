#!/usr/bin/env python3
"""42 electrical PVT tests of two same-design physically biased MOS PLLs.

This physically replaces the earlier IDEAL supply-tracked B-source
current-source gate with a diode-connected DB HiTek 180nm PMOS biased
by a 4k or 8k ideal resistor (not extracted on-chip resistor).
The physical MOS PMOS diode and switched MOS charge pump plus 3-stage
current-starved MOS VCO share a single ngspice transient. Clock
reference PFD/4 is behavioral XSPICE as before.

One identical sizing is used for all conditions of each design:
   diode_w16_r4k = PMOS W=16um, resistor 4kohm
   diode_w8_r8k  = PMOS W=8um, resistor 8kohm
Other MOS CP source/sink, ring VCO, 3fF per-stage load,
1.02V start, 1kohm Rzero remain fixed.

21 PVT points per design:
 - TT/FF/SS/FS/SF x -20/27/85C at VDD=1.80V
 - TT/FF/SS at VDD=1.71 and 1.89V at 27C
Quantify 450MHz reference divided MOS frequency, reference edge
phase, physical VCO control ripple, last 80ns no-slip windows and
last 3x80ns disjoint frequency stability.

Not original 2004 PLL, no phase-noise/random jitter or data CDR proof.
"""
from __future__ import annotations
import argparse,json
from pathlib import Path
import p3_pll_extended_pvt_phase as P
import p3_real_mos_pump_bias_sentinel as PHYS

DESIGNS=("diode_w16_r4k","diode_w8_r8k")
CORNERS=P.CORNERS
TEMPS=P.TEMPS
VDDS=P.VDDS

def run(out,design,corner,temp,vdd):
    if design not in DESIGNS or corner not in CORNERS or temp not in TEMPS or vdd not in VDDS:raise ValueError
    folder=out/design
    folder.mkdir(parents=True,exist_ok=True)
    before=P.deck
    try:
        P.deck=lambda c,t,v:PHYS.patch(before(c,t,v),design)
        result=P.main(folder,corner,temp,vdd)
    finally:
        P.deck=before
    w,r=PHYS.DESIGNS[design]
    met=result.get("measured",{})
    info={
      "design":design,"MOS_BIAS_diode_W_um":w,"bias_R_ohm":r,
      "bias_generator_actual_physical_PMOS":True,
      "bias_generator_resistor_extracted_PDK":False,
      "PVT_process_corner":corner,"temperature_C":temp,"supply_V":vdd,
      "physical_MOS_CP_source_sink":True,"physical_3stage_ring_VCO":True,
      "reference_PFD_XSPICE_digital":True,"reference_clock_ideal":True,
      "fixed_pump_size_pct":100*P.CP_SCALE,
      "fixed_extra_VCO_stage_cap_fF":P.EXTRA_FF,
      "fixed_initial_bias_V":P.INITIAL,
      "electrical_screen_passed":result["passes_extended_screen"],
      "VCO_frequency_GHz":met.get("vco_GHz"),
      "reference_phase_std_ps":met.get("std_phase_ps"),
      "physical_VCO_gate_ripple_mVpp":met.get("physical_vco_gate_ripple_mV"),
      "last_disjoint_window_freq_drift_MHz":result.get("interwindow_frequency_span_MHz"),
      "last_reference_cycle_slips":result.get("window_checks",[{}])[-1].get("bad_four_to_one_reference_intervals"),
      "status":result.get("sim_status"),
      "not_2004_silicon_data_CDR":True,
    }
    name=f"{corner}_T{temp:+.0f}_V{vdd:.2f}".replace("+","p").replace("-","m").replace(".","p")
    (folder/(name+"_physical_bias_PVT.json")).write_text(json.dumps(info,indent=2)+"\n")
    print(f"PHYSICALLY_BIASED_21PVT design={design} corner={corner} T={temp:g} "
          f"VDD={vdd:.2f} f_GHz={info['VCO_frequency_GHz']} "
          f"phase_ps={info['reference_phase_std_ps']} "
          f"ripple_mVpp={info['physical_VCO_gate_ripple_mVpp']} "
          f"drift_MHz={info['last_disjoint_window_freq_drift_MHz']} "
          f"slips={info['last_reference_cycle_slips']} "
          f"electricalPass={info['electrical_screen_passed']}",flush=True)
    return info

if __name__=="__main__":
    p=argparse.ArgumentParser()
    p.add_argument("--design",choices=DESIGNS,required=True)
    p.add_argument("--corner",choices=CORNERS,required=True)
    p.add_argument("--temp",type=float,choices=TEMPS,required=True)
    p.add_argument("--vdd",type=float,choices=VDDS,required=True)
    p.add_argument("--out",type=Path,default=Path("results/spice/p3_real_MOS_bias_full_PVT"))
    a=p.parse_args();run(a.out,a.design,a.corner,a.temp,a.vdd)
