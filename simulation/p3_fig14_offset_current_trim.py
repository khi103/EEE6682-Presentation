#!/usr/bin/env python3
"""Fig14-inspired MOS offset-current trim at low input Vcm=0.25 V.

Builds on the already SPICE-executed PMOS-input differential preamplifier.
Four binary-weighted PMOS *injectors* or NMOS *sinks* add programmable
DC current directly at preamp output. That intentionally differs from the
paper's M8-M10 differential-pair steering DAC, so we call this a separate
proof-of-principle transistor-level offset experiment.
"""
from pathlib import Path
import argparse,csv,json,math,shutil
import p3_transistor_driver as TX
import p3_fig14_comparator_mos as CMP

CODES=tuple(range(-15,16))
VREF=.25
WEIGHTS=(1,2,4,8)

def deck(corner,code,vin=.25):
    base=CMP.circuit(corner,vin,input_skew=0.0)
    assert ".control" in base
    inject=[]
    for w in WEIGHTS:
        ps=(code>0 and bool(code&w))
        ns=(code<0 and bool(-code&w))
        inject += [
           f"VTP{w} gp{w} 0 {1.15 if ps else 1.8}",
           f"VTN{w} gn{w} 0 {0.65 if ns else 0}",
           f"XPM{w} pre gp{w} vdd vdd 0 pch_svt_1p8v width=0.48u length=0.36u multi={w}",
           f"XNM{w} pre gn{w} 0 0 nch_svt_1p8v width=0.48u length=0.36u multi={w}"
        ]
    return base.replace(".control","\n".join(inject)+"\n.control",1)

def execute(out):
    out.mkdir(parents=True,exist_ok=True)
    work=TX.ENGINE_DIR/"p3_fig14_mos_offset"
    runner=TX.SpiceRunner(work)
    for corner in TX.CORNER_NAMES:
        src=TX.model_path(corner)
        dst=work/src.name
        if not dst.exists() or src.stat().st_mtime>dst.stat().st_mtime:
            shutil.copy2(src,dst)
    rows=[]
    summary={}
    for corner in TX.CORNER_NAMES:
        arr=[]
        for code in CODES:
            log=runner.run(deck(corner,code),f"offset_{corner}_{code:+03d}")
            result={
              "corner":corner,"signed_trim_code":code,
              "input_mV":250.,
              "ref_mV":250.,
              "preamp_V":TX.spice_vector(log,"v(pre)"),
              "comparator_output_V":TX.spice_vector(log,"v(out)"),
              "supply_current_uA":-TX.spice_vector(log,"i(vdd)")*1e6}
            arr.append(result);rows.append(result)
        best=min(arr,key=lambda r:abs(r["comparator_output_V"]-.9))
        summary[corner]={
            "best_midpoint_trim_code":best["signed_trim_code"],
            "midpoint_output_V":best["comparator_output_V"],
            "best_approx_midpoint_error_V":abs(best["comparator_output_V"]-.9),
            "reachable_low_out":min(x["comparator_output_V"] for x in arr)<.2,
            "reachable_high_out":max(x["comparator_output_V"] for x in arr)>1.5
        }
        print(f"{corner.upper()} MOS current-steer trim: closest code"
              f" {best['signed_trim_code']:+d}, output={best['comparator_output_V']:.4f}V",flush=True)
    with (out/"fig14_mos_offset_current_trim.csv").open("w",newline="") as f:
        w=csv.DictWriter(f,fieldnames=list(rows[0]))
        w.writeheader();w.writerows(rows)
    result={
       "status":"characterized_fig14_inspired_mos_current_trim",
       "not_original_steering_M8_M10":True,
       "model":"physical DB HiTek MOS PMOS/NMOS 4-bit current injectors at preamplifier output",
       "corner_trim":summary,
       "ngspice_calls":runner.calls,
       "limitations":[
           "Current injection at preamp output is not paper's M8-M9 differential-pair digital steering",
           "Preamp high-speed 1.8-GHz comparator limitation is NOT fixed or hidden",
           "No clocked M11-M19 positive-feedback regenerative latch",
           "Bias levels and MOS widths are assumptions and not original silicon sizing",
           "A mid-point DC voltage is not BER, bandwidth, offset sigma, or transient proof"
       ]}
    (out/"fig14_mos_offset_current_trim.json").write_text(json.dumps(result,indent=2)+"\n")
    assert len(rows)==5*len(CODES)
    print("PASS: actual PDK MOS offset-current code sweep executed; no full-comparator claim")
    return result

if __name__=="__main__":
    p=argparse.ArgumentParser()
    p.add_argument("--out",type=Path,default=Path("results/spice/p3_fig14_comparator"))
    execute(p.parse_args().out)
