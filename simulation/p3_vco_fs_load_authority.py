#!/usr/bin/env python3
"""Investigate physical FS-corner MOS VCO tuning gap with extra node loading.

Independent MOS-loaded VCO characterization showed that FS oscillator
does not oscillate at 0.65/0.75V and, when it first oscillates at
0.85V, it runs at 2.185GHz rather than reaching 1.8GHz. This study
adds ONE common per-stage shunt capacitor (ideal extracted-load
surrogate) to the SAME transistor VCO nodes. Determine whether a
reasonable fixed load could make 1.8GHz reachable at FS, and quantify
the TT speed penalty. It is not foundry capacitance extraction.
"""
from __future__ import annotations
import argparse,csv,json,math,shutil
from pathlib import Path
import p3_transistor_driver as TX
import p3_loaded_vco_pvt_authority as AUTH
import p3_xspice_physical_mos_pll as PLL

CAPS_FF=(0.,1.,2.,3.,5.,8.,12.,20.,30.,50.)
TRIALS=(("fs",.85),("fs",.95),("tt",.95))
TARGET=1.8

def netlist(corner,bias,extra_fF):
    deck=AUTH.deck(corner,bias)
    extras=[
      "* Additional per-stage physical VCO output load (ideal fF capacitor)"
    ]
    for i in range(1,4):
        if extra_fF>0:
            extras.append(f"CEXTRA{i} n{i} 0 {extra_fF:.6g}f")
    return deck.replace(".control","\n".join(extras)+"\n.control",1)

def run(out):
    out.mkdir(parents=True,exist_ok=True)
    work=TX.ENGINE_DIR/"p3_VCO_FS_load_authority"
    runner=TX.SpiceRunner(work)
    for corner in ("fs","tt"):
        src=TX.model_path(corner);dst=work/src.name
        if not dst.exists() or src.stat().st_mtime>dst.stat().st_mtime:
            shutil.copy2(src,dst)
    records=[]
    for corner,bias in TRIALS:
        for load in CAPS_FF:
            runner.run(netlist(corner,bias,load),
               f"extra_{corner}_{int(bias*100)}_{int(load)}")
            wave=PLL.read(work/"physical_pll.csv")
            ev=PLL.rising(wave,"vco_V",start_ns=AUTH.SIM_NS-40)
            f=(len(ev)-1)/(ev[-1]-ev[0])*1e-9 if len(ev)>=6 else None
            result={"corner":corner,"nmos_control_V":bias,
                    "extra_load_fF_per_stage":load,
                    "oscillating":f is not None,
                    "frequency_GHz":f,
                    "relative_target_freq_error_pct":100*(f/TARGET-1) if f else None}
            records.append(result)
            print(f"FS_VCO_LOAD corner={corner} ctrl={bias} load_fF={load} "
                  f"freq_GHz={f}",flush=True)
    closest=min((r for r in records if r["corner"]=="fs" and
                r["frequency_GHz"] is not None),
                key=lambda r:abs(r["frequency_GHz"]-TARGET))
    with (out/"loaded_VCO_extra_cap_sweep.csv").open("w",newline="") as f:
        w=csv.DictWriter(f,fieldnames=list(records[0]))
        w.writeheader();w.writerows(records)
    info={"source":"independent 180nm MOS ring VCO with ideal extra node capacitors",
          "only_open_loop":True,"original_Fig18_equivalent":False,
          "FS_previous_issue":"unloaded ring fails to oscillate below 0.85V and starts above 2.18GHz",
          "extra_capacitor_is_PDK_extracted":False,
          "closest_FS":closest,
          "results":records,"ngspice_runs":runner.calls}
    (out/"loaded_VCO_extra_cap_summary.json").write_text(json.dumps(info,indent=2)+"\n")
    print(f"FS_VCO_LOAD_CLOSEST {json.dumps(closest)}",flush=True)
    return info

if __name__=="__main__":
    p=argparse.ArgumentParser()
    p.add_argument("--out",type=Path,default=Path("results/spice/p3_vco_FS_load"))
    x=p.parse_args()
    run(x.out)
