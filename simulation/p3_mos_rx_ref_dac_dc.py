#!/usr/bin/env python3
"""Independent MOS 4-bit receiver-reference offset-trim authority experiment.

A series resistor and real DB HiTek 180-nm NMOS binary-weighted sinks
synthesize a selectable 0.28-V to lower reference voltage. This is an
independently sized R+MOS current DAC, NOT the original 2004 M8-M10
current-steering DAC and NOT a proof of in-circuit calibration.

The physical DC voltage for each code is computed by actual ngspice
MOS IV models. The digital control gate sources are ideal. The best
code is chosen using only a **known reference voltage target**, never
the transmitted PRBS bits or downstream error labels.
"""
from __future__ import annotations
import argparse,csv,json,math,shutil
from pathlib import Path
import p3_transistor_driver as TX

RESISTORS_OHM=(1000.,3000.,10000.)
GATES_V=(.5,.6)
CODES=tuple(range(16))
BASE_V=.28
DESIRED_V=.25
WEIGHTS=(1,2,4,8)

def deck(res,gate,code,corner):
    arr=[
      "* Fig14-inspired independent 4bit MOS offset-reference authority",
      f'.include "db180_svt018_{corner}.lib"',
      ".temp 27",
      "VDD vdd 0 1.8",
      f"VREFSRC vrefbase 0 {BASE_V}",
      f"RREF vrefbase vref_rx {res:.10g}",
    ]
    for w in WEIGHTS:
        arr.extend([
           f"VB{w} trim{w} 0 {gate if code&w else 0:.9g}",
           f"XNTRIM{w} vref_rx trim{w} 0 0 nch_svt_1p8v "
             f"width=.48u length=.36u multi={w}",
        ])
    arr+=[".control","set noaskquit","op",
          "print v(vref_rx) i(vrefsrc)","quit",".endc",".end"]
    return "\n".join(arr)+"\n"

def run(out):
    out.mkdir(parents=True,exist_ok=True)
    work=TX.ENGINE_DIR/"p3_rx_ref_mos_trim"
    sp=TX.SpiceRunner(work)
    src=TX.model_path("tt");dst=work/src.name
    if not dst.exists() or src.stat().st_mtime>dst.stat().st_mtime:
        shutil.copy2(src,dst)
    rec=[]
    best={}
    for res in RESISTORS_OHM:
        for gate in GATES_V:
            per=[]
            for code in CODES:
                log=sp.run(deck(res,gate,code,"tt"),
                           f"reftrim_{int(res)}_{int(gate*100)}_{code:02d}")
                ref=TX.spice_vector(log,"v(vref_rx)")
                row={"resistor_ohm":res,"gate_on_V":gate,
                     "code":code,"vref_actual_V":ref,
                     "error_from_nominal_mV":(ref-DESIRED_V)*1e3,
                     "offset_before_trim_mV":(BASE_V-DESIRED_V)*1e3}
                per.append(row);rec.append(row)
            mono=all(per[i]["vref_actual_V"]>=per[i+1]["vref_actual_V"]
                     for i in range(15))
            hit=min(per,key=lambda r:abs(r["error_from_nominal_mV"]))
            best[f"R{int(res)}_VG{int(gate*100)}"]={
               "code":hit["code"],
               "reference_after_trim_V":hit["vref_actual_V"],
               "residual_offset_mV":hit["error_from_nominal_mV"],
               "full_16_code_monotonic":mono,
               "range_V":[per[-1]["vref_actual_V"],per[0]["vref_actual_V"]],
            }
            print(f"PHYSICAL_RX_MOS_DAC R={res:g} VG={gate:g} "
                  f"best_code={hit['code']} best_ref_V={hit['vref_actual_V']:.8f} "
                  f"residual_mV={hit['error_from_nominal_mV']:.3f} "
                  f"monotonic={mono} range=[{per[-1]['vref_actual_V']:.6f}, "
                  f"{per[0]['vref_actual_V']:.6f}]",flush=True)
    with (out/"mos_receiver_reference_dac_dc.csv").open("w",newline="") as f:
        w=csv.DictWriter(f,fieldnames=list(rec[0]))
        w.writeheader();w.writerows(rec)
    report={"status":"independent_four_bit_MOS_R_reference_DAC_DC_characterized",
       "code_selection":"nearest VREF=0.25V based on physical DC only, no transmitted bit labels",
       "original_P3_Fig14_DAC":False,
       "physical":"DB HiTek 180nm MOS binary NMOS current sinks",
       "ideal":"DC control gate bias and 0.28V offset source",
       "not_closed_loop_offset_calibrator":True,
       "best":best,"runs":sp.calls}
    (out/"mos_receiver_reference_dac_dc_summary.json").write_text(
        json.dumps(report,indent=2)+"\n")
    return report

if __name__=="__main__":
    p=argparse.ArgumentParser()
    p.add_argument("--out",type=Path,
       default=Path("results/spice/p3_RX_MOS_ref_trim_DC"))
    a=p.parse_args()
    run(a.out)
