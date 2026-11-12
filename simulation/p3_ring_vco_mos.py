#!/usr/bin/env python3
"""Standalone tunable 3-stage 180-nm CMOS ring VCO.

Real DB HiTek 1.8V SVT MOS devices are used for 5 current-starved CMOS
inverters. MOS VCO netlists and ngspice transient waveforms genuinely run
in the CI workspace. No original paper Fig18 VCO transistor sizing/data
is available, so these are independently selected widths/capacitances.

This is an OPEN-LOOP VCO frequency-vs-bias experiment, not a PLL or CDR.
"""
from pathlib import Path
import argparse,csv,json,math,shutil
from bisect import bisect_left
import p3_transistor_driver as TX

STAGES=3
BIAS_N_VALUES=(.65,.85,1.05,1.25,1.45,1.65)
PVT=("tt","ff","ss")
RUN_NS=20
CL_F=2e-15

def deck(corner,control):
    pgate=1.8-control
    lines=[
      "* Independent current-starved PDK MOS three-stage ring VCO",
      f'.include "db180_svt018_{corner}.lib"',
      ".temp 27",
      "VDD vdd 0 DC 1.8",
      f"VNB nb 0 DC {control:.8g}",
      f"VPB pb 0 DC {pgate:.8g}",
    ]
    for i in range(1,STAGES+1):
        node=f"n{i}"
        prev=f"n{i-1}" if i>1 else f"n{STAGES}"
        lines+=[
            f"XPMAIN{i} {node} {prev} vp{i} vdd 0 pch_svt_1p8v width=4u length=.18u multi=1",
            f"XPSTARVE{i} vp{i} pb vdd vdd 0 pch_svt_1p8v width=4u length=.18u multi=1",
            f"XNMAIN{i} {node} {prev} vn{i} 0 nch_svt_1p8v width=2u length=.18u multi=1",
            f"XNSTARVE{i} vn{i} nb 0 0 nch_svt_1p8v width=2u length=.18u multi=1",
            f"CLOAD{i} {node} 0 {CL_F:.8g}",
        ]
    lines+=[".ic " + " ".join(f"v(n{i})={'1.8' if i%2 else '0'}" for i in range(1,STAGES+1)),
           ".control","set noaskquit",
           f"tran 2p {RUN_NS}n uic",
           "wrdata vco.csv time v(n1) v(n3) i(vdd)",
           "quit",".endc",".end"]
    return "\n".join(lines)+"\n"

def parse(path):
    rows=[]
    for line in path.read_text().splitlines():
        try:v=[float(a) for a in line.split()]
        except ValueError:continue
        if len(v)>=8 and all(math.isfinite(x) for x in v):
            rows.append({"time_s":v[0],"n1_V":v[3],"n3_V":v[5],"vdd_A":v[7]})
    if len(rows)<100:raise RuntimeError(f"VCO trace missing {len(rows)}")
    return rows

def measure(rows):
    crossings=[]
    x0=1.8*.5
    for a,b in zip(rows,rows[1:]):
        if a["time_s"]<3e-9:continue
        va,vb=a["n1_V"],b["n1_V"]
        if va<=x0<vb and vb>va:
            t=a["time_s"]+(x0-va)/(vb-va)*(b["time_s"]-a["time_s"])
            crossings.append(t)
    periods=[b-a for a,b in zip(crossings,crossings[1:])]
    if len(periods)<4:
        return {"oscillating":False,"frequency_GHz":None,
                "rising_crossings":len(crossings),"last_node_range_V":[
                min(x["n1_V"] for x in rows[-500:]),
                max(x["n1_V"] for x in rows[-500:])]}
    good=periods[-min(12,len(periods)):]
    med=sorted(good)[len(good)//2]
    if med<=0:raise RuntimeError("Bad VCO period")
    frequency=1/med/1e9
    return {"oscillating":True,"frequency_GHz":frequency,
            "rising_crossings":len(crossings),
            "final_period_std_ps":(sum((p-med)**2 for p in good)/len(good))**.5*1e12,
            "output_min_V":min(r["n1_V"] for r in rows[-1000:]),
            "output_max_V":max(r["n1_V"] for r in rows[-1000:])}

def run(out):
    out.mkdir(parents=True,exist_ok=True)
    w=TX.ENGINE_DIR/"p3_ring_vco"
    runner=TX.SpiceRunner(w)
    for c in PVT:
        src=TX.model_path(c)
        dst=w/src.name
        if not dst.exists() or src.stat().st_mtime>dst.stat().st_mtime:
            shutil.copy2(src,dst)
    data=[]
    for corner in PVT:
        for v in BIAS_N_VALUES:
            runner.run(deck(corner,v),f"vco_{corner}_{round(v*100):03d}")
            wave=parse(w/"vco.csv")
            m=measure(wave)
            line={"corner":corner,"v_nMOS_gate_V":v,
                  "v_pMOS_gate_V":1.8-v,
                  "frequency_GHz":m["frequency_GHz"],
                  "oscillating":m["oscillating"],"rising_crossings":m["rising_crossings"],
                  "output_min_V":m.get("output_min_V"),
                  "output_max_V":m.get("output_max_V")}
            data.append(line)
            if corner=="tt" and abs(v-1.25)<1e-6:
                with (out/"ring_vco_tt_1p25V_waveform.csv").open("w",newline="") as f:
                    wr=csv.DictWriter(f,fieldnames=list(wave[0]))
                    wr.writeheader();wr.writerows(wave)
            print(f"VCO {corner} VBN={v:.2f}: "
                  f"{m.get('frequency_GHz')} GHz, oscillating={m['oscillating']}",flush=True)
    with (out/"ring_vco_frequency_sweep.csv").open("w",newline="") as f:
        wr=csv.DictWriter(f,fieldnames=list(data[0]))
        wr.writeheader();wr.writerows(data)
    status={
      "status":"executed_real_mos_tunable_ring_oscillator_sweep",
      "topology":"independent three-stage current-starved MOS ring, open-loop",
      "simulator":"ngspice42 / DB HiTek SVT 180nm 1.8V",
      "load_capacitance_F":CL_F,
      "simulations":runner.calls,
      "data":data,
      "limits":["Not original Fig18 physical VCO design",
                "No PFD, charge pump, loop filter or PLL lock in MOS",
                "Ideal DC VCO bias sources, no supply noise, clock buffer or fractional divider",
                "Frequency at only three-stage selected PDK widths/temperatures"]
    }
    (out/"ring_vco_results.json").write_text(json.dumps(status,indent=2)+"\n")
    assert any(r["oscillating"] for r in data if r["corner"]=="tt"),"No TT VCO oscillation"
    print("PASS: Actual MOS ring oscillator produced periodic output",flush=True)
    return status

if __name__=="__main__":
    a=argparse.ArgumentParser()
    a.add_argument("--out",type=Path,default=Path("results/spice/p3_ring_vco"))
    run(a.parse_args().out)
