#!/usr/bin/env python3
"""Transistor-realized PMOS diode+resistor supply-tracking PLL bias DOE.

Existing reconstructed XSPICE/MOS reference PLL originally uses an
IDEAL constant voltage source to bias the PMOS charge-pump current
source. An ideal supply-tracked B-source bias was found to qualify
9/9 PVT sentinels. This independent OP-only experiment checks whether
a physically realized diode-connected 180nm PMOS plus poly-equivalent
resistor could produce a similar VSG supply-tracking characteristic.

VDD -> diode-connected MOS PMOS (S/B at VDD, G/D at PBias)
    -> resistor to GND. MOS and resistor are physical SPICE devices;
    only the supply source is ideal. Original foundry model remains
inside GitHub Actions and is NEVER packaged in output data.
This is a circuit TOPLOGY candidate, not a calibrated bandgap or
2004 charge pump replica; satisfactory DC gate bias does not imply
dynamic PLL lock.
"""
from __future__ import annotations
import argparse,csv,json,math,shutil
from pathlib import Path
import p3_transistor_driver as TX

WIDTHS_UM=(2.,4.,8.,16.)
RES_OHM=(1000,2000,4000,8000)
CONDITIONS=(
 ("tt",27.,1.8),("ff",27.,1.8),("ss",27.,1.8),
 ("fs",27.,1.8),("sf",27.,1.8),
 ("ff",27.,1.89),("ss",27.,1.71),
 ("ff",-20.,1.8),("ss",-20.,1.8),
 ("tt",-20.,1.8),("tt",85.,1.8),("ff",85.,1.8),("ss",85.,1.8),
)
TARGET_VSG=.91

def net(corner,temp,vdd,width,res):
    return "\n".join([
      "* Independent PDK MOS diode resistor supply-tracking source bias",
      f'.include "db180_svt018_{corner}.lib"',
      f".temp {temp:g}",
      f"VDD vdd 0 DC {vdd:.9g}",
      f"XPMOS_DIODE pbias pbias vdd vdd 0 pch_svt_1p8v width={width:g}u length=.36u multi=1",
      f"RBIAS pbias 0 {res:g}",
      ".control","set noaskquit","op",
      "print v(pbias) i(vdd)","quit",".endc",".end","",
    ])

def run(out):
    out.mkdir(parents=True,exist_ok=True)
    working=TX.ENGINE_DIR/"p3_transistor_CP_PBIAS_DC"
    runner=TX.SpiceRunner(working)
    for corner in set(x[0] for x in CONDITIONS):
        model=TX.model_path(corner);dest=working/model.name
        if not dest.exists() or model.stat().st_mtime>dest.stat().st_mtime:
            shutil.copy2(model,dest)
    rec=[]
    for width in WIDTHS_UM:
      for res in RES_OHM:
       for corner,temp,vdd in CONDITIONS:
        tag=f"W{int(width)}_R{res}_{corner}_T{int(temp)}_V{vdd:.2f}".replace(".","p")
        row={"corner":corner,"temp_C":temp,"supply_V":vdd,
             "MOS_diode_width_um":width,"resistor_ohm":res}
        try:
            log=runner.run(net(corner,temp,vdd,width,res),tag)
            pbias=TX.spice_vector(log,"v(pbias)")
            i=abs(TX.spice_vector(log,"i(vdd)"))
            row.update({
                "status":"simulated","PMOS_gate_pbias_V":pbias,
                "PMOS_effective_vsg_V":vdd-pbias,
                "error_from_target_0p91V_mV":(vdd-pbias-TARGET_VSG)*1e3,
                "additional_generator_current_uA":i*1e6,
            })
        except Exception as exc:
            row.update({"status":"failed",
                "error":f"{type(exc).__name__}: {str(exc)[-900:]}"})
        rec.append(row)
    summary=[]
    for width in WIDTHS_UM:
      for res in RES_OHM:
        d=[r for r in rec if r["MOS_diode_width_um"]==width and r["resistor_ohm"]==res]
        good=[r for r in d if r["status"]=="simulated"]
        score=max(abs(r["error_from_target_0p91V_mV"]) for r in good) if len(good)==len(d) else None
        summary.append({"width_um":width,"R_ohm":res,
          "all_conditions_electrical_success":len(good)==len(d),
          "max_abs_gate_source_bias_error_mV":score,
          "max_bias_generator_current_uA":
              max(r["additional_generator_current_uA"] for r in good) if good else None})
        print(f"MOS_DIODE_PBIAS width_um={width} R_ohm={res} "
              f"max_dev_mV={score} "
              f"max_current_uA={summary[-1]['max_bias_generator_current_uA']}",flush=True)
    selected=min((r for r in summary if r["max_abs_gate_source_bias_error_mV"] is not None),
                 key=lambda z:(z["max_abs_gate_source_bias_error_mV"],
                               z["max_bias_generator_current_uA"]))
    with (out/"physical_diode_PMOS_bias_DC.csv").open("w",newline="") as f:
        fields=list(rec[0])
        w=csv.DictWriter(f,fieldnames=fields,extrasaction="ignore")
        w.writeheader();w.writerows(rec)
    report={
      "type":"independent diode-connected physical MOS PMOS + resistor current-source bias",
      "target_vsg_V":TARGET_VSG,
      "conditions":len(CONDITIONS),"designs":len(summary),
      "simulations_attempted":len(rec),
      "all_candidates":summary,"best_minimax_MOS_bias":selected,
      "note":"This is physical DC only, no actual PLL transient or original foundry bandgap",
      "circuit_details":"Diode-connected pch_svt_1p8v source/bulk=vdd, gate/drain=pbias, resistor pbias to ground",
      "foundry_model_source_parameters_included":False,
    }
    (out/"physical_diode_PMOS_bias_summary.json").write_text(json.dumps(report,indent=2)+"\n")
    print(f"PHYSICAL_MOS_BIAS_SELECTED {json.dumps(selected)}",flush=True)
    return report

if __name__=="__main__":
    p=argparse.ArgumentParser()
    p.add_argument("--out",type=Path,default=Path("results/spice/p3_physical_MOS_CP_bias_DC"))
    a=p.parse_args();run(a.out)
