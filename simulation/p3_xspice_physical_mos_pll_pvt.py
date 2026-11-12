#!/usr/bin/env python3
"""PVT sensitivity of the ACTUAL XSPICE/PDF/4/7-bit-MOS-CP/MOS-VCO PLL.

All blocks are simulated together in ngspice. Real PDK MOS VCO and
switching current source use CORNER models and temperatures; the
reference digital logic is XSPICE behavior, not physical PFD transistors.
No independent per-corner resizing/retuning of loop R or C is allowed.
A physically necessary start-bias guess is varied per corner and
disclosed; it is NOT a programmed closed-loop frequency calibration.

Lock requires: |FVCO-1.8GHz| <12MHz; reference-phase std <8ps;
VCO gate control ripple <5mVpp. No random-jitter model.
"""
from __future__ import annotations
import argparse,csv,json,shutil
from pathlib import Path
import p3_transistor_driver as TX
import p3_xspice_physical_mos_pll as PLL

SETUPS=(
 ("tt_27", "tt",27.,.96),
 ("ff_27", "ff",27.,.74),
 ("ss_27", "ss",27.,1.02),
 ("fs_27", "fs",27.,.76),
 ("sf_27", "sf",27.,1.02),
 ("tt_m20", "tt",-20.,.94),
 ("tt_p85", "tt",85.,.98),
)
CODE=63

def save(path,records):
    with path.open("w",newline="") as f:
        wr=csv.DictWriter(f,fieldnames=list(records[0]))
        wr.writeheader();wr.writerows(records)

def main(out):
    out.mkdir(parents=True,exist_ok=True)
    work=TX.ENGINE_DIR/"p3_xspice_mos_pll_pvt"
    runner=TX.SpiceRunner(work)
    for corner in TX.CORNER_NAMES:
        src=TX.model_path(corner)
        dest=work/src.name
        if not dest.exists() or src.stat().st_mtime>dest.stat().st_mtime:
            shutil.copy2(src,dest)
    rows=[]
    cases={}
    for name,corner,temp,start in SETUPS:
        spice=PLL.circuit(CODE,corner=corner,initial_bias=start)
        spice=spice.replace(".temp 27",f".temp {temp}",1)
        runner.run(spice,f"mos_pll_{name}")
        measured=PLL.read(work/"physical_pll.csv")
        met=PLL.metrics(measured)
        met.update(PLL.aligned_phase_errors_ps(measured))
        locked=bool(met.get("vco_GHz") is not None
            and abs(met["vco_GHz"]-PLL.RATE_GHZ)<.012
            and met.get("std_phase_ps") is not None
            and met["std_phase_ps"]<8.
            and met["physical_vco_gate_ripple_mV"]<5.)
        rec={
           "scenario":name,"corner":corner,"temp_C":temp,
           "VCO_initial_gate_bias_V":start,"7bit_current_code":CODE,
           "final_vco_frequency_GHz":met["vco_GHz"],
           "reference_MHz":met.get("reference_MHz"),
           "phase_std_ps":met.get("std_phase_ps"),
           "VCO_gate_bias_ripple_mVpp":met.get("physical_vco_gate_ripple_mV"),
           "loop_pump_filter_ripple_mVpp":met.get("control_delta_last_30ns_mV"),
           "locked_under_predeclared_criteria":locked,
        }
        rows.append(rec)
        cases[name]={"metrics":met,"actual_closed_loop_lock_criteria":locked}
        print(f"Physical MOS PFD/CP/VCO {name}: FVCO={met.get('vco_GHz')}, "
             f"phase_std={met.get('std_phase_ps')}ps "
             f"gate_ripple={met.get('physical_vco_gate_ripple_mV')}mVpp "
             f"locked={locked}",flush=True)
        if name=="tt_27":
            short=measured[::max(1,len(measured)//10000)]
            save(out/"tt_27_PLL_edge_and_gate_waveforms.csv",short)
    save(out/"XSPICE_physical_MOS_PLL_PVT.csv",rows)
    report={
      "status":"executed_physical_MOS_PFD4_charge_pump_VCO_PVT_corners_temperatures",
      "architecture":"450MHz XSPICE DFF/AND PFD + /4 + 7-bit physical switched MOS CP + lead-lag passive RC filter + physical 3-stage ring VCO",
      "reference_voltage":"1.8V reference ideal clock and MOS supplies",
      "conditions":cases,
      "ngspice_runs":runner.calls,
      "summary":{"locked":sum(r["locked_under_predeclared_criteria"] for r in rows),
                 "tested":len(rows)},
      "limitations":[
        "Initial bias chosen separately from known open-loop VCO curves, no in-silicon start-bias supervisor",
        "Only source transistor models change, not digital PFD/charge-pump logic or on-chip switching-capacitor notch",
        "Deterministic simulated phase deviation, not random jitter or original silicon",
        "Only limited PVT corners/temperatures, no independent Monte Carlo mismatch",
      ]
    }
    (out/"XSPICE_physical_MOS_PLL_PVT_summary.json").write_text(json.dumps(report,indent=2)+"\n")
    if not cases["tt_27"]["actual_closed_loop_lock_criteria"]:
        raise AssertionError("Nominal physical MOS PLL PVT rerun did not lock")
    print(f"PASS: PDK MOS PLL ran all {len(rows)} PVT cases, "
          f"{report['summary']['locked']}/{len(rows)} met strict lock criteria",flush=True)
    return report

if __name__=="__main__":
    p=argparse.ArgumentParser()
    p.add_argument("--out",type=Path,default=Path("results/spice/p3_pll_pvt"))
    main(p.parse_args().out)
