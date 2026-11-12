#!/usr/bin/env python3
"""Independent Gear 3ps full 5x3x3 process-temp-voltage MOS PLL validation.

The reconstructed physical PMOS diode-bias MOS charge-pump PLL already
passed 45/45 PVT with ngspice default trapezoidal 3ps step, but its
numerical stability is in question: at the marginal SS+85C+1.71V
design A failed Gear 3ps while design B survived. This study tests
design B (diode_w8_r8k) at ALL 45 independent Cartesian PVT points.

Identical MOS CP, diode-PMOS gate bias, RC loop filter, 3fF/stage
ring-VCO capacitors, initial 1.02V and ideal external 450MHz reference
in every case. Only ngspice integrator changes to Gear/3ps.

Count electrical PASS only after checking:
  1. actual physical transient completes through 1200ns,
  2. absolute PLL frequency error <1500ppm,
  3. reference/VCO phase edge difference std <8ps,
  4. VCO gate ripple <5mV peak-to-peak,
  5. final reference cycle-slip count zero,
  6. three disjoint final 80ns frequency span <2MHz.

This is *numerical convergence evidence* for one independent reference
PLL, not measured random noise, transistor mismatch or silicon BER.
"""
from __future__ import annotations
import argparse,json,re
from pathlib import Path
import p3_real_mos_bias_full_pvt as BASE
import p3_pll_extended_pvt_phase as P
import p3_transistor_driver as TX
import p3_xspice_physical_mos_pll as PLL

DESIGN="diode_w8_r8k"
CORNERS=BASE.CORNERS
TEMPS=BASE.TEMPS
VDDS=BASE.VDDS

def modify(deck):
    old="tran 3p "
    if deck.count(old)!=1:raise AssertionError("Unexpected transient source")
    if deck.count(".control")!=1:raise AssertionError("Missing control block")
    return deck.replace(".control",
        ".options method=gear reltol=.001\n.control",1)

def main(out,corner,temp,vdd):
    if corner not in CORNERS or temp not in TEMPS or vdd not in VDDS:
        raise ValueError("Unknown fixed PVT corner")
    out.mkdir(parents=True,exist_ok=True)
    old=P.deck
    try:
        P.deck=lambda c,t,v:modify(old(c,t,v))
        result=BASE.run(out,DESIGN,corner,temp,vdd)
    finally:
        P.deck=old
    name=f"{corner}_T{temp:+.0f}_V{vdd:.2f}".replace("+","p").replace("-","m").replace(".","p")
    waveform=TX.ENGINE_DIR/("p3_PLL_extended_PVT_"+name)/"physical_pll.csv"
    try:
        last_ns=PLL.read(waveform)[-1]["time_s"]*1e9
    except Exception:
        last_ns=None
    complete=bool(last_ns is not None and last_ns>=1199.8)
    m={
      "design":DESIGN,
      "independent_solver":"ngspice_42_gear_3ps",
      "corner":corner,"temperature_C":temp,"supply_V":vdd,
      "original_MOS_topology_unchanged":True,
      "waveform_last_ns":last_ns,"complete_1p2us_transient":complete,
      "electrical_pass_from_original_screen":result["electrical_screen_passed"],
      "qualified_after_completeness":bool(complete and result["electrical_screen_passed"]),
      "VCO_frequency_GHz":result["VCO_frequency_GHz"],
      "phase_std_ps":result["reference_phase_std_ps"],
      "physical_VCO_gate_ripple_mVpp":result["physical_VCO_gate_ripple_mVpp"],
      "last_three_disjoint_80ns_frequency_drift_MHz":result["last_disjoint_window_freq_drift_MHz"],
      "last_reference_cycle_slips":result["last_reference_cycle_slips"],
      "original_2004_foundry_PDK":False,
      "physical_2004_data_CDR_proven":False,
    }
    (out/f"gear_PVT_{name}.json").write_text(json.dumps(m,indent=2)+"\n")
    print(f"GEAR_45MOS_PVT {DESIGN} corner={corner} T={temp:g} VDD={vdd:.2f} "
          f"complete={complete} VCO={m['VCO_frequency_GHz']} "
          f"phase_std_ps={m['phase_std_ps']} "
          f"drift_MHz={m['last_three_disjoint_80ns_frequency_drift_MHz']} "
          f"slips={m['last_reference_cycle_slips']} "
          f"electrical_pass={m['qualified_after_completeness']}",flush=True)
    return m

if __name__=="__main__":
    p=argparse.ArgumentParser()
    p.add_argument("--corner",choices=CORNERS,required=True)
    p.add_argument("--temp",type=float,choices=TEMPS,required=True)
    p.add_argument("--vdd",type=float,choices=VDDS,required=True)
    p.add_argument("--out",type=Path,default=Path("results/spice/p3_gear45_physicalMOS_PLL"))
    a=p.parse_args()
    main(a.out,a.corner,a.temp,a.vdd)
