#!/usr/bin/env python3
"""PVT failure root-cause study of MOS charge pump bias and loop-zero R.

The same 3fF/stage physical 180nm VCO and 82.5% source/sink CP width
are held constant. The previous 21-case PVT audit found that VCO
tuning range still brackets 1.8GHz in the failing FF high-VDD and SS
low-VDD conditions. We now isolate two physical circuit hypotheses:

1. Static PMOS charge-pump source-gate bias (.95V) makes VSG depend on
   VDD; supply-referenced MOS source-gate bias may reduce pump mismatch.
2. 2-kOhm loop-filter zero resistor could be poorly damped at extreme
   supply and process. Screen RZERO = 1/2/4 kOhm.

All tests are real ngspice 42 MOS/XSPICE PLL simulations, not foundry
original 2004 PFD/PLL. The 450MHz reference clock is ideal. The
specified lock criteria include actual reference cycle slips and
disjoint final three 80ns window VCO stability.
"""
from __future__ import annotations
import argparse,json
from pathlib import Path
import p3_pll_extended_pvt_phase as P

SCENARIOS={
  "ff_high_vdd":("ff",27.,1.89),
  "ss_low_vdd":("ss",27.,1.71),
}
RZERO_OHM=(1000,2000,4000)
BIAS_MODES=("fixed","vsg_0p85","vsg_0p80")

def apply(deck,bias_mode,rzero):
    a="VBPMOS pbias 0 .95"
    if bias_mode!="fixed":
        assert deck.count(a)==1, "PMOS charge pump bias source missing"
        vsg=.85 if bias_mode=="vsg_0p85" else .80
        deck=deck.replace(a,f"BPMOS_BIAS pbias 0 V={{v(vdd)-{vsg:.9g}}}",1)
    k="RZERO loopctrl lpcap 2k"
    assert deck.count(k)==1,"Loop filter resistor missing"
    deck=deck.replace(k,f"RZERO loopctrl lpcap {rzero:g}",1)
    return deck

def run(out,scenario,bias_mode,rzero):
    if scenario not in SCENARIOS or bias_mode not in BIAS_MODES or rzero not in RZERO_OHM:
        raise ValueError
    corner,temp,vdd=SCENARIOS[scenario]
    folder=out/scenario/bias_mode/f"R{rzero}"
    old=P.deck
    try:
        P.deck=lambda c,t,v:apply(old(c,t,v),bias_mode,rzero)
        result=P.main(folder,corner,temp,vdd)
    finally:
        P.deck=old
    item={
       "scenario":scenario,"pump_PBIAS_mode":bias_mode,
       "loop_zero_resistance_ohm":rzero,
       "reference_PLL_only_not_data_CDR":True,
       "physical_180nm_MOS_PDK":True,
       "relative_supply_range":"+/-5% around 1.8V",
       "experiment":"adaptive PMOS gate-source bias / loop-zero compensation",
       "results":result,
    }
    (folder/"supply_bias_filter_summary.json").write_text(json.dumps(item,indent=2)+"\n")
    m=result.get("measured",{})
    print(f"PHYSICAL_PLL_BIAS_FILTER scenario={scenario} "
          f"pump_bias_mode={bias_mode} Rzero_ohm={rzero} "
          f"VCO_GHz={m.get('vco_GHz')} "
          f"phaseSTD_ps={m.get('std_phase_ps')} "
          f"gateRipple_mV={m.get('physical_vco_gate_ripple_mV')} "
          f"frequencyWindowSpan_MHz={result.get('interwindow_frequency_span_MHz')} "
          f"cycleSlip={result.get('window_checks',[{}])[-1].get('bad_four_to_one_reference_intervals')} "
          f"electricalQualified={result['passes_extended_screen']}",flush=True)
    return item

if __name__=="__main__":
    p=argparse.ArgumentParser()
    p.add_argument("--scenario",choices=SCENARIOS,required=True)
    p.add_argument("--bias-mode",choices=BIAS_MODES,required=True)
    p.add_argument("--rzero",type=int,choices=RZERO_OHM,required=True)
    p.add_argument("--out",type=Path,default=Path("results/spice/p3_MOS_supply_bias_filter"))
    a=p.parse_args()
    run(a.out,a.scenario,a.bias_mode,a.rzero)
