#!/usr/bin/env python3
"""Fixed-design pump-strength PVT study of the XSPICE/MOS reference PLL.

A common start voltage (0.96 V), fixed RC loop filter and fixed charge-pump
strength are used for all five PDK corners. This deliberately avoids
per-corner external pretraining. A pass requires simultaneous 1.8-GHz
frequency, reference phase and MOS VCO gate-ripple screening.
This is NOT transistor-level replication of the original 2004 PLL.
"""
from __future__ import annotations
import argparse,csv,json,shutil
from pathlib import Path
import p3_transistor_driver as TX
import p3_xspice_physical_mos_pll as P

CORNERS=("tt","ff","ss","fs","sf")
SCALES=(.5,.65,.75,.85,1.)
REF_MHZ=450.
ORIGINAL_WIDTH_SOURCE=P.I_SOURCE_W_UM
ORIGINAL_WIDTH_SINK=P.I_SINK_W_UM

def measure(corner,scale,out):
    if corner not in CORNERS or scale not in SCALES:raise ValueError("Invalid case")
    out.mkdir(parents=True,exist_ok=True)
    root=TX.ENGINE_DIR/f"p3_global_strength_{corner}_{int(scale*100):03d}"
    engine=TX.SpiceRunner(root)
    orig=TX.model_path(corner);target=root/orig.name
    if not target.exists() or orig.stat().st_mtime>target.stat().st_mtime:
        shutil.copy2(orig,target)
    try:
        P.I_SOURCE_W_UM=ORIGINAL_WIDTH_SOURCE*scale
        P.I_SINK_W_UM=ORIGINAL_WIDTH_SINK*scale
        engine.run(P.circuit(63,corner=corner,initial_bias=.96),f"{corner}_{int(scale*100)}")
    finally:
        P.I_SOURCE_W_UM=ORIGINAL_WIDTH_SOURCE
        P.I_SINK_W_UM=ORIGINAL_WIDTH_SINK
    wave=P.read(root/"physical_pll.csv")
    metric=P.metrics(wave)
    metric.update(P.aligned_phase_errors_ps(wave))
    err_ppm=(metric["vco_GHz"]/1.8-1)*1e6 if metric.get("vco_GHz") else None
    lock=bool(err_ppm is not None and abs(err_ppm)<1500
              and metric.get("std_phase_ps") is not None and metric["std_phase_ps"]<8
              and metric.get("physical_vco_gate_ripple_mV") is not None
              and metric["physical_vco_gate_ripple_mV"]<5)
    # Frequency stability in three non-overlapping windows must also be recorded.
    end=P.TIME_NS
    windows={}
    for a,b in ((end-240,end-160),(end-160,end-80),(end-80,end)):
        events=[t for t in P.rising(wave,"vco_V",start_ns=a) if t<=b*1e-9]
        windows[f"{a:g}_{b:g}ns_GHz"] = (len(events)-1)/(events[-1]-events[0])*1e-9 if len(events)>10 else None
    drift=max((v for v in windows.values() if v is not None),default=0)-min((v for v in windows.values() if v is not None),default=0)
    result={"corner":corner,"shared_initial_V":.96,
            "pump_source_sink_width_scale":scale,
            "temperature_C":27,
            "target_GHz":1.8,
            "frequency_error_ppm":err_ppm,
            "all_three_lock_criteria":lock,
            "three_frequency_windows_GHz":windows,
            "interwindow_frequency_span_MHz":drift*1000,
            "metrics":metric,
            "physical":"MOS switched CP, loop RC, MOS VCO; XSPICE PFD+divider",
            "original_ASIC_equivalence":False,
            "caveat":"single transient deterministic screening; no Monte Carlo/jitter"}
    (out/f"pvt_{corner}_{int(scale*100):03d}.json").write_text(json.dumps(result,indent=2)+"\n")
    print(f"GLOBAL_PUMP_PVT corner={corner} scale={scale} "
          f"f_GHz={metric.get('vco_GHz')} freq_ppm={err_ppm} "
          f"phase_std_ps={metric.get('std_phase_ps')} "
          f"VCO_gate_ripple_mV={metric.get('physical_vco_gate_ripple_mV')} "
          f"pass={lock} window_span_MHz={drift*1000}",flush=True)
    return result

if __name__=="__main__":
    p=argparse.ArgumentParser()
    p.add_argument("--corner",required=True,choices=CORNERS)
    p.add_argument("--scale",required=True,type=float,choices=SCALES)
    p.add_argument("--out",type=Path,default=Path("results/spice/p3_global_pump_pvt"))
    a=p.parse_args()
    measure(a.corner,a.scale,a.out)
