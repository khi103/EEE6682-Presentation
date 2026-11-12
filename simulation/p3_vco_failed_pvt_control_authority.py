#!/usr/bin/env python3
"""Open-loop physical MOS VCO tuning authority at failed PLL PVT conditions.

This is a standalone ring-oscillator control-characterization using the
SAME transistor-level ring + 3fF/stage extra load as the 21-case physical
reference PLL and its actual two 180nm foundry corners. It deliberately
replaces the ring's PLL control gate with two externally commanded ideal
DC voltage sources. This isolates VCO tuning range from loop acquisition.

Problem PVT scenarios:
  FF, -20C at 1.80V: reference PLL phase fluctuation despite near 1.8GHz
  FF, +27C at 1.89V: reference PLL unstable
  SS, -20C at 1.80V: reference PLL slow
  SS, +27C at 1.71V: reference PLL slow

The original 2004 transistor VCO and real on-chip supply references are
not available. Passing open-loop tuning is not proof of PLL lock.
"""
from __future__ import annotations
import argparse,csv,json,math,shutil
from pathlib import Path
import p3_transistor_driver as TX
import p3_loaded_vco_pvt_authority as OPEN
import p3_xspice_physical_mos_pll as PLL

SCENARIOS={
  "ff_cold":("ff",-20.,1.8),
  "ff_vdd_high":("ff",27.,1.89),
  "ss_cold":("ss",-20.,1.8),
  "ss_vdd_low":("ss",27.,1.71),
  "tt_nominal":("tt",27.,1.8),
}
GATES=(.65,.70,.75,.80,.85,.90,.95,1.00,1.05,1.10,1.15,1.20,1.30)
ADDED_FF=3.0
T_NS=80.

def make_deck(corner,temp,supply,bias):
    d=OPEN.deck(corner,bias)
    d=d.replace(".temp 27",f".temp {temp:.8g}",1)
    d=d.replace("VDD vdd 0 DC 1.8",f"VDD vdd 0 DC {supply:.9g}",1)
    old=f"VBIAS_P pb 0 DC {1.8-bias:.9f}"
    assert d.count(old)==1,old
    d=d.replace(old,f"VBIAS_P pb 0 DC {supply-bias:.9f}")
    # Keep physical VCO stage MOS identical, add fixed independent load.
    extra=[f"CPVT_LOAD_{i} n{i} 0 {ADDED_FF:g}f" for i in range(1,4)]
    return d.replace(".control","\n".join(extra)+"\n.control",1)

def run(out,scenario):
    if scenario not in SCENARIOS:raise ValueError
    corner,temp,supply=SCENARIOS[scenario]
    out.mkdir(parents=True,exist_ok=True)
    path=TX.ENGINE_DIR/("p3_extreme_PVT_openloop_VCO_"+scenario)
    spice=TX.SpiceRunner(path)
    model=TX.model_path(corner);dest=path/model.name
    if not dest.exists() or model.stat().st_mtime>dest.stat().st_mtime:shutil.copy2(model,dest)
    rows=[]
    for bias in GATES:
        tag=f"pvt_{scenario}_{bias:.2f}".replace(".","p")
        item={"corner":corner,"temp_C":temp,"vdd_V":supply,
            "external_N_gate_V":bias,"additional_load_per_stage_fF":ADDED_FF}
        try:
            spice.run(make_deck(corner,temp,supply,bias),tag)
            wave=PLL.read(path/"physical_pll.csv")
            rise=PLL.rising(wave,"vco_V",start_ns=T_NS-40)
            rise=[t for t in rise if t<=T_NS*1e-9]
            f=(len(rise)-1)/(rise[-1]-rise[0])*1e-9 if len(rise)>=8 else None
            item.update({"status":"simulated","frequency_GHz":f,
                "last_40ns_rising_edges":len(rise)})
        except Exception as exc:
            item.update({"status":"simulator_failed",
                         "frequency_GHz":None,"error":str(exc)[-1300:]})
        rows.append(item)
        print(f"PVT_VCO_OPENLOOP scenario={scenario} bias={bias:.2f} "
              f"f_GHz={item['frequency_GHz']} status={item['status']}",flush=True)
    oscillators=[r for r in rows if r.get("frequency_GHz") is not None]
    frequencies=[r["frequency_GHz"] for r in oscillators]
    bracket=bool(frequencies and min(frequencies)<=1.8<=max(frequencies))
    near=min(oscillators,key=lambda x:abs(x["frequency_GHz"]-1.8)) if oscillators else None
    summary={"scenario":scenario,"target_GHz":1.8,"sweep_brackets_target":bracket,
             "measured_min_GHz":min(frequencies) if frequencies else None,
             "measured_max_GHz":max(frequencies) if frequencies else None,
             "nearest_point":near,"number_of_runs":spice.calls,
             "original_2004_VCO":False,"actual_PLL_lock_proven":False,"cases":rows}
    (out/f"{scenario}.json").write_text(json.dumps(summary,indent=2)+"\n")
    if rows:
        with (out/f"{scenario}.csv").open("w",newline="") as f:
            writer=csv.DictWriter(f,fieldnames=["corner","temp_C","vdd_V",
                         "external_N_gate_V","additional_load_per_stage_fF",
                         "status","frequency_GHz","last_40ns_rising_edges"],extrasaction="ignore")
            writer.writeheader();writer.writerows(rows)
    print(f"PVT_VCO_RANGE scenario={scenario} bracket_target={bracket} "
          f"fmin_GHz={summary['measured_min_GHz']} "
          f"fmax_GHz={summary['measured_max_GHz']} "
          f"nearest_bias_V={near['external_N_gate_V'] if near else None} "
          f"nearest_f_GHz={near['frequency_GHz'] if near else None}",flush=True)
    return summary

if __name__=="__main__":
    p=argparse.ArgumentParser()
    p.add_argument("--scenario",choices=SCENARIOS,required=True)
    p.add_argument("--out",type=Path,
          default=Path("results/spice/p3_pvt_openloop_vco"))
    a=p.parse_args()
    run(a.out,a.scenario)
