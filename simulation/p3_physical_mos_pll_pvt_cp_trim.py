#!/usr/bin/env python3
"""Seven-bit CP-code correction for PVT-limited P3 reference PLL.

Reuses the actually executed XSPICE DFF PFD/4, physical 450MHz MOS
switched charge pump, passive third-order RC filter and transistor
3-stage VCO. Earlier TT/FF/SS/FS/SF run with fixed code63 was locked
only in TT and SS. This experiment keeps MOS dimensions, 450MHz ref,
R-C loop and initial physical VCO startup guesses fixed, and varies
ONLY the physical seven-bit NMOS current-bank code 0/31/63/95/127.

It is NOT the original 7-bit data CDR, which dynamically changes phase
mismatch under Fig19 BBPD control. Here static code trim assesses
whether process failures can be recovered by available pump authority.
"""
from __future__ import annotations
import argparse,csv,json,shutil
from pathlib import Path
import p3_transistor_driver as TX
import p3_xspice_physical_mos_pll as PLL

CASES={
 "ff":.74,
 "fs":.76,
 "sf":1.02,
}
CODES=(0,31,63,95,127)

def save(path,records):
    with path.open("w",newline="") as f:
        w=csv.DictWriter(f,fieldnames=list(records[0]))
        w.writeheader();w.writerows(records)

def run(out):
    out.mkdir(parents=True,exist_ok=True)
    work=TX.ENGINE_DIR/"p3_cp_corners_trim"
    runner=TX.SpiceRunner(work)
    for corner in CASES:
        src=TX.model_path(corner)
        dst=work/src.name
        if not dst.exists() or src.stat().st_mtime>dst.stat().st_mtime:
            shutil.copy2(src,dst)
    measures=[]
    for corner,vstart in CASES.items():
        for code in CODES:
            runner.run(PLL.circuit(code,corner=corner,initial_bias=vstart),
                       f"cp_code_{corner}_{code:03d}")
            wave=PLL.read(work/"physical_pll.csv")
            m=PLL.metrics(wave)
            m.update(PLL.aligned_phase_errors_ps(wave))
            lock=bool(m.get("vco_GHz") is not None and
                     abs(m["vco_GHz"]-1.8)<.012 and
                     m.get("std_phase_ps") is not None and
                     m["std_phase_ps"]<8 and
                     m["physical_vco_gate_ripple_mV"]<5)
            row={
                "corner":corner,"trim_code":code,
                "start_VCO_bias_V":vstart,
                "VCO_frequency_GHz":m.get("vco_GHz"),
                "phase_std_ps":m.get("std_phase_ps"),
                "VCO_gate_ripple_mVpp":m.get("physical_vco_gate_ripple_mV"),
                "reference_PFD_source_MHz":450.,
                "strictly_locked":lock
            }
            measures.append(row)
            print(f"{corner.upper()} MOS CP code{code:3d}: FVCO={row['VCO_frequency_GHz']}GHz "
                  f"phaseSTD={row['phase_std_ps']}ps "
                  f"ripple={row['VCO_gate_ripple_mVpp']}mVpp, lock={lock}",
                  flush=True)
    save(out/"PVT_MOS_charge_pump_code_trim.csv",measures)
    best={}
    for corner in CASES:
        c=[x for x in measures if x["corner"]==corner]
        good=[x for x in c if x["strictly_locked"]]
        best[corner]={
           "passed_codes":[x["trim_code"] for x in good],
           "code63_reference":next(x for x in c if x["trim_code"]==63),
           "any_code_locked":bool(good),
           "closest_frequency_code":min(c,key=lambda x:abs(x["VCO_frequency_GHz"]-1.8)
                               if x["VCO_frequency_GHz"] is not None else float("inf"))["trim_code"],
        }
    report={
      "status":"executed_MOS_CP_code_trim_at_PLL_unlocked_PVT_corners",
      "corners":list(CASES),"pump_codes":CODES,
      "physical_simulator":"XSPICE digital PFD/4 + real DB HiTek MOS switched current bank and ring oscillator",
      "tested_runs":runner.calls,
      "results":best,"all_measurements":measures,
      "limitations":[
        "Static charge-pump current code is pre-programmed, not recovered by actual data-driven CDR",
        "Only sampled 5 of 128 codes, not globally optimized",
        "Assumed initial VCO bias differs per corner as declared",
        "No complete PDK HSPICE correlation or original 2004 chip physical design",
      ]
    }
    (out/"PVT_MOS_charge_pump_code_trim.json").write_text(json.dumps(report,indent=2)+"\n")
    print("PASS: Measured physical MOS PLL seven-bit code control authority at FF FS SF; "
          "individual PVT lock failures remain explicit",flush=True)
    return report

if __name__=="__main__":
    p=argparse.ArgumentParser()
    p.add_argument("--out",type=Path,
       default=Path("results/spice/p3_pll_cp_pvt_trim"))
    run(p.parse_args().out)
