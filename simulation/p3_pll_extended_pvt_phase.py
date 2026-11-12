#!/usr/bin/env python3
"""Electrical PVT, acquisition, and phase-cycle-slip audit for the fixed PLL.

Fixed single design candidate from 2026-11-12 PVT run 43180163187:
  initial Vctrl=1.02 V, shared MOS switched pump source/sink widths=82.5%
  of reconstructed sizes, 3 fF extra shunt C on each MOS VCO stage.

Evaluate 5 process corners at -20/27/85 C, and supply 1.71/1.80/1.89 V
at TT/FF/SS (27 C). Source PFD remains external 1.8V clock; the MOS core
and DAC gates are scaled with the core supply. 450MHz reference remains
ideal; XSPICE PFD/divider are behavioral; original 2004 foundry is unknown.

Strict evidence beyond wrapped phase variance:
  - |mean frequency error| < 1500 ppm over the last 40ns
  - nearest-edge reference phase std < 8ps
  - physical VCO control gate ripple < 5mV peak-to-peak
  - no missed/extra VCO cycles versus every reference interval in
    the last 80ns (expected exactly 4 VCO cycles per 450MHz interval)
  - late 3 nonoverlapping 80ns windows have similar VCO frequency
  - acquisition screening over earlier 80ns intervals (diagnostic only)
This is deterministic 1.2us ngspice, NOT silicon random jitter/BER.
"""
from __future__ import annotations
import argparse,bisect,json,math,shutil
from pathlib import Path
import p3_transistor_driver as TX
import p3_xspice_physical_mos_pll as PLL

CORNERS=("tt","ff","ss","fs","sf")
TEMPS=(-20.,27.,85.)
VDDS=(1.71,1.80,1.89)
INITIAL=1.02
CP_SCALE=.825
EXTRA_FF=3.
SIM_NS=1200.
REF_MHZ=450.

def deck(corner,temp,vdd):
    p,n=PLL.I_SOURCE_W_UM,PLL.I_SINK_W_UM
    try:
        PLL.I_SOURCE_W_UM=p*CP_SCALE;PLL.I_SINK_W_UM=n*CP_SCALE
        out=PLL.circuit(63,corner=corner,initial_bias=INITIAL)
    finally:
        PLL.I_SOURCE_W_UM=p;PLL.I_SINK_W_UM=n
    out=out.replace(".temp 27",f".temp {temp:.9g}",1)
    out=out.replace("VDD vdd 0 DC 1.8",f"VDD vdd 0 DC {vdd:.9g}",1)
    out=out.replace("out_high=1.8 ",f"out_high={vdd:.9g} ",1)
    # Keep external PFD reference clock at 1.8V, MOS VCO output rails track core.
    out=out.replace("BPB pb 0 V={1.8-v(nb)}","BPB pb 0 V={v(vdd)-v(nb)}",1)
    extras=[f"CPVTADDED{i} n{i} 0 {EXTRA_FF:g}f" for i in range(1,4)]
    return out.replace(".control","\n".join(extras)+"\n.control",1)

def edges(rows,key,begin_ns,end_ns):
    # PLL.rising filters against fixed 0.9-V threshold.
    return [t for t in PLL.rising(rows,key,start_ns=begin_ns)
            if t <= end_ns*1e-9]

def window(rows,a,b):
    e=edges(rows,"vco_V",a,b)
    r=edges(rows,"ref_V",a,b)
    hz=(len(e)-1)/(e[-1]-e[0])*1e-9 if len(e)>=6 else None
    counts=[]
    for x,y in zip(r,r[1:]):
        counts.append(bisect.bisect_left(e,y)-bisect.bisect_left(e,x))
    counts=counts[1:-1] if len(counts)>2 else counts
    slips=sum(c!=4 for c in counts)
    # Diagnostic edge stability relative to both reference and physical oscillator.
    return {"start_ns":a,"end_ns":b,
      "VCO_GHz":hz,"ref_interval_count":len(counts),
      "bad_four_to_one_reference_intervals":slips,
      "min_VCO_edges_per_reference_interval":min(counts) if counts else None,
      "max_VCO_edges_per_reference_interval":max(counts) if counts else None}

def main(out,corner,temp,vdd):
    if corner not in CORNERS or temp not in TEMPS or vdd not in VDDS:
        raise ValueError("Bad PVT case")
    out.mkdir(parents=True,exist_ok=True)
    name=f"{corner}_t{temp:+.0f}_v{vdd:.2f}".replace(".","p").replace("+","plus").replace("-","minus")
    working=TX.ENGINE_DIR/("p3_PLL_extended_PVT_"+name)
    engine=TX.SpiceRunner(working)
    model=TX.model_path(corner)
    dest=working/model.name
    if not dest.exists() or model.stat().st_mtime>dest.stat().st_mtime:
        shutil.copy2(model,dest)
    item={
      "case":name,"corner":corner,"temperature_C":temp,"MOS_core_supply_V":vdd,
      "external_reference_supply_V":1.8,"startup_voltage_V":INITIAL,
      "pump_width_scale":CP_SCALE,"added_VCO_cap_fF_per_stage":EXTRA_FF,
      "target_GHz":1.8,"mixed_signal":"XSPICE PFD+divider, physical MOS pump/VCO",
      "original_P3_physical_PLL":False,"jitter_is_not_random":True}
    try:
        engine.run(deck(corner,temp,vdd),name)
        rows=PLL.read(working/"physical_pll.csv")
        m=PLL.metrics(rows);m.update(PLL.aligned_phase_errors_ps(rows))
        windows=[window(rows,a,a+80) for a in (680,760,840,920,1000,1080,1120)]
        recent=windows[-1]
        span=[x["VCO_GHz"] for x in windows[-3:] if x["VCO_GHz"] is not None]
        drift=(max(span)-min(span))*1000 if len(span)==3 else None
        ppm=(m["vco_GHz"]/1.8-1)*1e6 if m.get("vco_GHz") else None
        criteria={
          "abs_frequency_error_under_1500ppm":ppm is not None and abs(ppm)<1500,
          "nearest_reference_edge_phase_std_under_8ps":
             m.get("std_phase_ps") is not None and m["std_phase_ps"]<8,
          "actual_MOS_VCO_gate_ripple_under_5mVpp":
             m.get("physical_vco_gate_ripple_mV") is not None and
             m["physical_vco_gate_ripple_mV"]<5,
          "no_ref_interval_cycle_slip_last_80ns":
             recent["ref_interval_count"]>=20 and
             recent["bad_four_to_one_reference_intervals"]==0,
          "last_3x80ns_frequency_span_under_2MHz":
             drift is not None and drift<2.0,
        }
        item.update({"sim_status":"ran","frequency_error_ppm":ppm,
                     "interwindow_frequency_span_MHz":drift,
                     "measured":m,"window_checks":windows,
                     "screen":criteria,
                     "passes_extended_screen":all(criteria.values())})
    except Exception as e:
        item.update({"sim_status":"failed",
                     "passes_extended_screen":False,
                     "error":f"{type(e).__name__}: {str(e)[-2200:]}"})
    (out/(name+".json")).write_text(json.dumps(item,indent=2)+"\n")
    m=item.get("measured",{})
    print(f"PLL_EXTENDED_PVT {name} f_GHz={m.get('vco_GHz')} "
          f"phase_std_ps={m.get('std_phase_ps')} "
          f"ripple_mVpp={m.get('physical_vco_gate_ripple_mV')} "
          f"drift_MHz={item.get('interwindow_frequency_span_MHz')} "
          f"ref_slips={item.get('window_checks',[{}])[-1].get('bad_four_to_one_reference_intervals')} "
          f"qualified={item['passes_extended_screen']} status={item['sim_status']}",flush=True)
    return item

if __name__=="__main__":
    p=argparse.ArgumentParser()
    p.add_argument("--corner",choices=CORNERS,required=True)
    p.add_argument("--temp",type=float,choices=TEMPS,required=True)
    p.add_argument("--vdd",type=float,choices=VDDS,required=True)
    p.add_argument("--out",type=Path,
      default=Path("results/spice/p3_extensive_MOS_PLL_PVT"))
    a=p.parse_args()
    main(a.out,a.corner,a.temp,a.vdd)
