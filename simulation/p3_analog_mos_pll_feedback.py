#!/usr/bin/env python3
"""First PDK-MOS Ring VCO + analog behavioral PLL phase-feedback prototype.

PHYSICAL: DB HiTek 180nm SVT MOS three-stage current-starved ring VCO.
IDEAL: 1.8GHz reference, tanh-XOR phase detector, bias controller Bsource.
The controller's capacitor/RC is physical C/R but Bsource PD is ideal.
This is not the paper's dual PLL/CDR, physical PFD or switched charge pump.
A waveform is necessary to claim locked frequency; success flags are checked.
"""
from __future__ import annotations
from pathlib import Path
import csv,json,math,argparse,shutil
import p3_transistor_driver as TX
import p3_ring_vco_mos as VCO

FREF=1.8e9
PER_PS=1e12/FREF
CLOOP=35e-12
LOOP_I=45e-6
INITIAL_BIAS=.927
TIME_NS=125

def deck(corner,sign=1,initial_bias=INITIAL_BIAS):
    a=[
      "* independent P3 functional analog PLL with physical MOS VCO",
      f'.include "db180_svt018_{corner}.lib"',
      ".temp 27",
      "VDD vdd 0 1.8",
      f"VREFCLK refclk 0 PULSE(0 1.8 0 2p 2p {PER_PS/2-4:.8f}p {PER_PS:.8f}p)",
      f"VINIT initbias 0 {initial_bias:.10g}",
      f"CLOOP vbias 0 {CLOOP} ic={initial_bias}",
      "RLEAK vbias initbias 100meg",
      "BVGATE nb 0 V={min(max(v(vbias),0.65),1.65)}",
      "BPGATE pb 0 V={1.8-v(nb)}",
      "BPD xorout 0 V={0.5*(1-tanh(15*(v(refclk)-0.9))*tanh(15*(v(n1)-0.9)))}",
      f"BINT vbias 0 I={{ {sign*LOOP_I:.9g}*(v(xorout)-0.5) }}",
    ]
    for i in range(1,VCO.STAGES+1):
        node=f"n{i}"
        prev=f"n{i-1}" if i>1 else f"n{VCO.STAGES}"
        a+=[
          f"XPMAIN{i} {node} {prev} vp{i} vdd 0 pch_svt_1p8v width=4u length=.18u multi=1",
          f"XPSTARVE{i} vp{i} pb vdd vdd 0 pch_svt_1p8v width=4u length=.18u multi=1",
          f"XNMAIN{i} {node} {prev} vn{i} 0 nch_svt_1p8v width=2u length=.18u multi=1",
          f"XNSTARVE{i} vn{i} nb 0 0 nch_svt_1p8v width=2u length=.18u multi=1",
          f"CLOAD{i} {node} 0 {VCO.CL_F:.8g}"
        ]
    a += [
       ".ic "+" ".join(f"v(n{i})={'1.8' if i%2 else '0'}" for i in range(1,VCO.STAGES+1)),
       ".control","set noaskquit",
       f"tran 4p {TIME_NS}n uic",
       "wrdata pll_phase.csv time v(n1) v(refclk) v(vbias) v(xorout) i(vdd)",
       "quit",".endc",".end"
    ]
    return "\n".join(a)+"\n"

def parse(path):
    rows=[]
    for line in path.read_text().splitlines():
        try: a=[float(v) for v in line.split()]
        except ValueError:continue
        if len(a)>=12 and all(math.isfinite(x) for x in a):
            rows.append({"time_s":a[0],"ring_V":a[3],"ref_V":a[5],
                         "vco_ctrl_V":a[7],"phase_detector_V":a[9],
                         "supply_A":a[11]})
    if len(rows)<1000:raise RuntimeError("PLL transient record missing")
    return rows

def last_frequency(rows,time0=90e-9):
    rising=[]
    for a,b in zip(rows,rows[1:]):
        if a["time_s"]<time0:continue
        if a["ring_V"]<.9<=b["ring_V"]:
            t=a["time_s"]+(.9-a["ring_V"])/(b["ring_V"]-a["ring_V"])*(b["time_s"]-a["time_s"])
            rising.append(t)
    intervals=[b-a for a,b in zip(rising,rising[1:])]
    if len(intervals)<25:return None
    mean=sum(intervals)/len(intervals)
    return {"ring_frequency_GHz":1/mean/1e9,
            "period_std_ps":(sum((x-mean)**2 for x in intervals)/len(intervals))**.5*1e12,
            "ring_edges":len(rising)}

def run(out):
    out.mkdir(parents=True,exist_ok=True)
    w=TX.ENGINE_DIR/"p3_mos_pll_feedback"
    r=TX.SpiceRunner(w)
    src=TX.model_path("tt")
    dest=w/src.name
    if not dest.exists() or src.stat().st_mtime>dest.stat().st_mtime:
        shutil.copy2(src,dest)
    results={}
    for sign in (-1,1):
      for initial in (.90,.99):
        tag=f"pll_{sign:+d}_{int(initial*1000):04d}"
        r.run(deck("tt",sign,initial),tag)
        rows=parse(w/"pll_phase.csv")
        last=last_frequency(rows)
        entry={
            "sign":sign,"start_bias_V":initial,
            "final_bias_V":rows[-1]["vco_ctrl_V"],
            "final_freq":last,
            "stable_near_1p8GHz":bool(last is not None and
                              abs(last["ring_frequency_GHz"]-1.8)<.035)}
        results[tag]=entry
        if entry["stable_near_1p8GHz"]:
            with (out/f"{tag}_waveform.csv").open("w",newline="") as f:
                wr=csv.DictWriter(f,fieldnames=list(rows[0]))
                wr.writeheader();wr.writerows(rows)
        print(f"PLL sign={sign:+d} initial={initial:.2f}: "
              f"final VBN={entry['final_bias_V']:.5f}V "
              f"f={None if last is None else last['ring_frequency_GHz']:.5f}GHz "
              f"near_target={entry['stable_near_1p8GHz']}",flush=True)
    data={
      "status":"executed_ngspice_behav_pd_with_physical_mos_vco",
      "scope":"ngspice behavioral XOR phase detector + MOS tunable oscillator + ideal RC integral",
      "physical_loop":"actual MOS VCO controlled by analog B-source/capacitor current integration",
      "no_paper_exact_PLL":True,
      "target_GHz":1.8,"reference_GHz":1.8,
      "results":results,"ngspice_calls":r.calls,
      "limitations":["B-source XOR PD ideal, not original transistor PFD",
            "No MOS charge-pump UP/DN, switched-capacitor filter or 7-bit offset pump integrated",
            "No 450MHz reference divider; reference directly 1.8GHz in this prototype",
            "Frequency matching is not sufficient to demonstrate bounded loop phase or jitter transfer",
            "This PLL alone is not connected to the serial TX-to-RX link"]
    }
    (out/"mos_vco_analog_PLL_prototype.json").write_text(json.dumps(data,indent=2)+"\n")
    if not any(x["stable_near_1p8GHz"] for x in results.values()):
        print("LIMITATION: Prototype PD/VCO feedback did not achieve 1.8GHz target in selected trials",flush=True)
    else:
        print("PASS: At least one physical MOS VCO/ideal phase-controller feedback trial approached 1.8GHz",flush=True)
    return data

if __name__=="__main__":
    a=argparse.ArgumentParser()
    a.add_argument("--out",type=Path,default=Path("results/spice/p3_analog_mos_pll"))
    run(a.parse_args().out)
