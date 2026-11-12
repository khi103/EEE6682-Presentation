#!/usr/bin/env python3
"""Does a REAL 7-bit MOS charge-pump trim code restore SS-corner lock?

All MOS widths and physical MOS ring-VCO loads are held fixed:
source/sink CP widths 75% of original independently sized reconstruction,
3fF added capacitance per three-stage VCO node, 0.96V startup, 1.8V
supply, 450MHz ideal reference, 27C and same RC loop filter.

Only the already physically implemented 7-bit binary-weighted MOS
charge-pump sinking-current DAC code is changed. In the untrimmed
code-63 case, SS-corner frequency and phase lock fails, whereas TT,
FF, FS, SF pass. The aim is to find static code authority, NOT claim
an implemented automatic digital calibration controller or 2004 ASIC
phase tracking. Preserve every successful and failed test separately.
"""
from __future__ import annotations
import argparse,json,shutil
from pathlib import Path
import p3_transistor_driver as TX
import p3_xspice_physical_mos_pll as PLL

CODES=(0,8,16,24,32,40,48,56,63,72,96,127)
CORNER="ss"
CAP_FF=3.
PUMP_SCALE=.75
INIT=.96

def netlist(code):
    src=PLL.I_SOURCE_W_UM;snk=PLL.I_SINK_W_UM
    try:
        PLL.I_SOURCE_W_UM=src*PUMP_SCALE
        PLL.I_SINK_W_UM=snk*PUMP_SCALE
        deck=PLL.circuit(code,corner=CORNER,initial_bias=INIT)
    finally:
        PLL.I_SOURCE_W_UM=src;PLL.I_SINK_W_UM=snk
    extra=[f"CTRIMVCO{i} n{i} 0 {CAP_FF:g}f" for i in range(1,4)]
    return deck.replace(".control","\n".join(extra)+"\n.control",1)

def run(out,code):
    if code not in CODES:raise ValueError(code)
    out.mkdir(parents=True,exist_ok=True)
    work=TX.ENGINE_DIR/f"p3_SS_7bit_CP_code_{code:03d}"
    sim=TX.SpiceRunner(work)
    model=TX.model_path(CORNER);dst=work/model.name
    if not dst.exists() or model.stat().st_mtime>dst.stat().st_mtime:
        shutil.copy2(model,dst)
    record={"corner":CORNER,"7bit_real_MOS_CP_code":code,
      "physical_MOS_CP_source_sink_width_scale":PUMP_SCALE,
      "fixed_extra_VCO_node_cap_fF":CAP_FF,
      "initial_bias_V":INIT,"temperature_C":27,
      "physical":"DB HiTek 180nm MOS 7bit switched pump and 3stage ring VCO",
      "behavioral":"XSPICE digital PFD and divider",
      "original_P3_2004_equivalent":False}
    try:
        sim.run(netlist(code),f"ss_code_{code:03d}")
        rows=PLL.read(work/"physical_pll.csv")
        m=PLL.metrics(rows)
        m.update(PLL.aligned_phase_errors_ps(rows))
        f=m.get("vco_GHz")
        ppm=(f/1.8-1)*1e6 if f else None
        passed=bool(ppm is not None and abs(ppm)<1500 and
             m.get("std_phase_ps") is not None and m["std_phase_ps"]<8 and
             m.get("physical_vco_gate_ripple_mV") is not None and
             m["physical_vco_gate_ripple_mV"]<5 and
             m.get("n_reference_edges",0)>=25)
        record.update({"status":"simulated",
            "frequency_error_ppm":ppm,
            "static_code_meets_reference_lock_screen":passed,
            "measurements":m})
    except Exception as e:
        record.update({"status":"simulator_failed",
          "static_code_meets_reference_lock_screen":False,
          "error":f"{type(e).__name__}: {str(e)[-1600:]}"})
    (out/f"SS_code_{code:03d}.json").write_text(json.dumps(record,indent=2)+"\n")
    m=record.get("measurements",{})
    print(f"PHYSICAL_SS_CP_CODE code={code:3d} "
          f"fVCO_GHz={m.get('vco_GHz')} "
          f"phase_STD_ps={m.get('std_phase_ps')} "
          f"VCO_ripple_mV={m.get('physical_vco_gate_ripple_mV')} "
          f"pass={record['static_code_meets_reference_lock_screen']}",flush=True)
    return record

if __name__=="__main__":
    p=argparse.ArgumentParser()
    p.add_argument("--code",type=int,choices=CODES,required=True)
    p.add_argument("--out",type=Path,default=Path("results/spice/p3_SS_physical_MOS_CP_trim"))
    a=p.parse_args()
    run(a.out,a.code)
