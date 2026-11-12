#!/usr/bin/env python3
"""Parse PDK-free XSPICE DFF diagnostic waveforms.

Run from repository root:
    ngspice -b circuits/p3_xspice_adc_dff_isolation.cir
    python3 scripts/p3_parse_xspice_dff_diag.py --wave p3_xspice_dff_diag.dat

A bridge output equal to 0.5V indicates XSPICE digital U because the
dac_bridge model explicitly declares out_undef=0.5. This is a DIGITAL
logic test only; no physical MOS transistor, BER or CDR is tested.
"""
from __future__ import annotations
import argparse,json,math
from pathlib import Path

SIGNALS=("raw_data","raw_clock","digital_adc_data","digital_adc_clock",
         "digital_adc_zero","DFF_ic2_tied_zero",
         "DFF_ic0_tied_zero","DFF_ic2_NULL_ports")

def main(path,out):
    if not path.exists():
        raise FileNotFoundError(f"Run ngspice first: {path}")
    data=[]
    for line in path.read_text().splitlines():
        try:a=[float(q) for q in line.split()]
        except ValueError:continue
        if len(a)>=18 and all(math.isfinite(v) for v in a):
            data.append((a[0],*[a[3+2*i] for i in range(len(SIGNALS))]))
    if len(data)<100:
        raise RuntimeError(f"Missing complete mixed-mode XSPICE waveform: {len(data)} records")
    # Discard the initial 2ns so each digital DFF has many clock events.
    data=[r for r in data if r[0]>=2e-9]
    results={}
    for i,name in enumerate(SIGNALS,start=1):
        vals=[r[i] for r in data]
        results[name]={
           "minimum":min(vals),"maximum":max(vals),
           "fraction_zero":sum(v<.1 for v in vals)/len(vals),
           "fraction_one":sum(v>.9 for v in vals)/len(vals),
           "fraction_unknown_U":sum(.49<v<.51 for v in vals)/len(vals),
        }
        print(f"XSPICE_STAGE {name}: "
              f"0={results[name]['fraction_zero']:.5f}, "
              f"1={results[name]['fraction_one']:.5f}, "
              f"U={results[name]['fraction_unknown_U']:.5f}",flush=True)
    state={
      "status":"PDK-free isolated ngspice code-model test",
      "source_waveform":str(path),"evaluated_samples":len(data),
      "decoder":"digital U -> analog out_undef=0.5V",
      "signals":results,
      "physical_MOS_verified":False,
      "original_4XOR_PD_or_CDR_verified":False,
    }
    out.parent.mkdir(parents=True,exist_ok=True)
    out.write_text(json.dumps(state,indent=2)+"\n")
    return state

if __name__=="__main__":
    p=argparse.ArgumentParser()
    p.add_argument("--wave",type=Path,default=Path("p3_xspice_dff_diag.dat"))
    p.add_argument("--out",type=Path,default=Path("results/audit/p3_xspice_dff_diag.json"))
    a=p.parse_args()
    main(a.wave,a.out)
