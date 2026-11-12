#!/usr/bin/env python3
"""P3 Fig.20-inspired PHYSICAL SWITCHED 7-bit MOS charge pump.

Unlike the previous DC code-current sweep, UP/DOWN MOS switches operate
under 450-MHz pulsed commands, with DB HiTek 0.18-um SVT NMOS/PMOS.

Switching transistors and binary-weighted NMOS current elements are
real MOS devices. UP and DOWN pulse sources are ideal and independently
scheduled. VCTRL is clamped at 0.9 V to isolate switching-current
characterization (no closed PLL). MOS dimensions and bias are assumed.
Neither exact paper layout nor actual Fig.20 SPICE netlist is claimed.
"""
from __future__ import annotations
import argparse, csv, json, math, shutil
from pathlib import Path
import p3_transistor_driver as TX

W=(1,2,4,8,16,32,64)
CORNERS=("tt","ff","ss")
CODES=(0,64,127)
PERIOD_PS=1e12/450e6
TOTAL_NS=40.0
UP_PULSE_PS=300.
UP_FIRST_PS=500.
DOWN_OFFSET_PS=50.
BIASES={"pmos_V":.95,"nmos_base_V":.68,"nmos_trim_V":.55}
OUTPUT=Path("results/spice/p3_switched_charge_pump")

def deck(corner,code,down_delay_ps=DOWN_OFFSET_PS):
    nmos_code_gates=[f"VCBIT{w} bc{w} 0 {BIASES['nmos_trim_V'] if code&w else 0.}" for w in W]
    nmos_code_devices=[
        f"XNTRIM{w} nsink bc{w} 0 0 nch_svt_1p8v width=0.48u length=0.36u multi={w}"
        for w in W
    ]
    return "\n".join([
       "* P3 Fig20-inspired PHYSICAL MOS switched 7-bit charge pump",
       "* PLL PFD/Filter/VCO NOT implemented in this current test",
       f'.include "db180_svt018_{corner}.lib"',
       ".temp 27",
       "VDD vdd 0 DC 1.8",
       "VCLAMP cpout 0 DC 0.9",
       f"VBPMOS pbias 0 {BIASES['pmos_V']}",
       f"VBNMOS nbias 0 {BIASES['nmos_base_V']}",
       f"VUP gup 0 PULSE(1.8 0 {UP_FIRST_PS:.8f}p 5p 5p "
           f"{UP_PULSE_PS:.8f}p {PERIOD_PS:.8f}p)",
       f"VDOWN gdown 0 PULSE(0 1.8 {UP_FIRST_PS+down_delay_ps:.8f}p "
           f"5p 5p {UP_PULSE_PS:.8f}p {PERIOD_PS:.8f}p)",
       "XPMOS_CURRENT psource pbias vdd vdd 0 pch_svt_1p8v "
           "width=8u length=0.36u multi=1",
       "XPMOS_SWITCH cpout gup psource vdd 0 pch_svt_1p8v "
           "width=12u length=0.18u multi=1",
       "XNMOS_SWITCH cpout gdown nsink 0 nch_svt_1p8v "
           "width=12u length=0.18u multi=1",
       "XNMOS_BASE nsink nbias 0 0 nch_svt_1p8v "
           "width=8u length=0.36u multi=1",
       *nmos_code_gates,*nmos_code_devices,
       ".control","set noaskquit",
       f"tran 3p {TOTAL_NS}n",
       "wrdata physical_switched_pump.csv time i(vclamp) "
          "v(gup) v(gdown) i(vdd)",
       "quit",".endc",".end",""
    ])

def parse(path):
    output=[]
    for row in path.read_text().splitlines():
        try: a=[float(x) for x in row.split()]
        except ValueError: continue
        if len(a)>=10 and all(math.isfinite(x) for x in a):
            output.append({"time_s":a[0],"clamped_pump_A":a[3],
                           "up_gate_V":a[5],"down_gate_V":a[7],
                           "vdd_branch_A":a[9]})
    if len(output)<200:raise RuntimeError("No physical switched charge-pump waveform")
    return output

def average(rows,field,t_start=10e-9):
    kept=[x for x in rows if x["time_s"]>=t_start]
    if len(kept)<100:raise RuntimeError("Insufficient steady-state pulses")
    area=sum((a[field]+b[field])*.5*(b["time_s"]-a["time_s"])
              for a,b in zip(kept,kept[1:]))
    return area/(kept[-1]["time_s"]-kept[0]["time_s"])

def run(out=OUTPUT):
    out.mkdir(parents=True,exist_ok=True)
    work=TX.ENGINE_DIR/"p3_physical_switched_pump"
    runner=TX.SpiceRunner(work)
    for corner in CORNERS:
        source=TX.model_path(corner)
        target=work/source.name
        if not target.exists() or source.stat().st_mtime>target.stat().st_mtime:
            shutil.copy2(source,target)
    results=[]
    for corner in CORNERS:
        for code in CODES:
            # 0/64/127 code sensitivity; +200ps UP-DOWN skew control.
            skews=(DOWN_OFFSET_PS,200.) if corner=="tt" and code==64 else (DOWN_OFFSET_PS,)
            for skew in skews:
                runner.run(deck(corner,code,skew),
                           f"mos_pump_{corner}_{code:03d}_{int(skew)}")
                rr=parse(work/"physical_switched_pump.csv")
                m=average(rr,"clamped_pump_A")
                peak=max(abs(x["clamped_pump_A"]) for x in rr)
                results.append({
                   "corner":corner,"7bit_code":code,
                   "down_pulse_delay_ps":skew,
                   "steady_average_cp_clamp_A":m,
                   "peak_cp_clamp_magnitude_A":peak,
                   "duration_ns":TOTAL_NS,
                   "reference_MHz":450.,
                   "supply_1p8V_mean_mW":-average(rr,"vdd_branch_A")*1.8e3,
                   "recorded_points":len(rr),
                })
                if corner=="tt" and code==64 and skew==DOWN_OFFSET_PS:
                    with (out/"tt_code64_physical_pump_waveform.csv").open("w",newline="") as f:
                        writer=csv.DictWriter(f,fieldnames=list(rr[0]))
                        writer.writeheader();writer.writerows(rr)
                print(f"Switched CP {corner} code {code} skew={skew:g} ps: "
                      f"Iclamp_avg={m*1e6:+.3f}uA, peak={peak*1e6:.3f}uA",
                      flush=True)
    with (out/"physical_switched_charge_pump_metrics.csv").open("w",newline="") as f:
        writer=csv.DictWriter(f,fieldnames=list(results[0]))
        writer.writeheader();writer.writerows(results)
    percorner={}
    for corner in CORNERS:
        r=sorted((x for x in results if x["corner"]==corner and
               x["down_pulse_delay_ps"]==DOWN_OFFSET_PS),key=lambda x:x["7bit_code"])
        currents=[x["steady_average_cp_clamp_A"] for x in r]
        percorner[corner]={
           "codes":[0,64,127],
           "mean_clamp_current_A":currents,
           "monotonic_code_response":bool(
               (currents[0]<currents[1]<currents[2]) or
               (currents[0]>currents[1]>currents[2])),
           "total_7bit_swing_uA":(currents[2]-currents[0])*1e6,
        }
    report={
      "status":"executed_physical_mos_450MHz_switched_charge_pump",
      "source":"Independent Fig20-inspired MOS pullup/pulldown and 7-bit weighted sinks",
      "simulator":"ngspice 42, DB HiTek 180nm SVT models",
      "code_sweep":CODES,"PVT_corners":CORNERS,"ngspice_runs":runner.calls,
      "per_corner":percorner,
      "all_results":results,
      "limitations":[
       "This test clamps VCTRL to 0.9V; no PLL and no phase locking measured",
       "UP and DOWN are ideal 450MHz source pulses, not an actual phase-frequency detector",
       "No exact paper transistor dimensions or switched-capacitor notch filter",
       "HSPICE-model-only BSIM flags ignored by ngspice: numerical correlation pending"
      ]
    }
    (out/"physical_switched_charge_pump_summary.json").write_text(
        json.dumps(report,indent=2)+"\n")
    if not all(x["monotonic_code_response"] for x in percorner.values()):
        raise AssertionError("Actual switched MOS current code failed monotonic response")
    print("PASS: 450MHz MOS switched charge pump produces monotonic code-dependent current",
          flush=True)
    return report

if __name__=="__main__":
    arg=argparse.ArgumentParser()
    arg.add_argument("--out",type=Path,default=OUTPUT)
    run(arg.parse_args().out)
