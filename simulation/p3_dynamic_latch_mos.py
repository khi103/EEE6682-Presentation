#!/usr/bin/env python3
"""Clocked low-common-mode regenerative MOS comparator reconstruction.

A *new*, independent complementary dynamic-latch comparator for 0.25-V
common-mode inputs. Uses real DB HiTek 180nm SVT PMOS-input differential
devices and NMOS cross-coupled regeneration + clocked reset transistors.
It does not copy the published Fig14 M1-M19 netlist or offset calibration.

Scope: 1.8GHz (= 2 samples/UI) clocked comparator STANDALONE functional
simulation at low 0.25V common mode. Output is read during evaluate.
If it fails, preserve failure details; do not relabel it as success.
"""
from __future__ import annotations
import argparse, json, math, csv, shutil
from pathlib import Path
import p3_transistor_driver as TX

CLOCK_PERIOD_NS=0.555556
SAMPLE_PHASE_NS=0.225
N_CYCLES=18
LOW_VIN=0.210
HIGH_VIN=0.290
VREF=0.250

def latch_devices(prefix="L", input_node="vin", ref_node="vref",
                  clk_node="clk", out_node="q", inv_node="qb"):
    # Positive decision Q=1 when VIN>VREF: input PMOS at VIN charges 'qb'
    # more slowly, PMOS at VREF charges 'q' faster, positive feedback sets Q.
    # PMOS has D G S B SUB; NMOS has D G S B.
    lines=[
      f"XP{prefix}TAIL t{prefix} {clk_node} vdd vdd 0 pch_svt_1p8v width=8u length=.18u multi=1",
      f"XP{prefix}VIN {inv_node} {input_node} t{prefix} vdd 0 pch_svt_1p8v width=5u length=.18u multi=1",
      f"XP{prefix}REF {out_node} {ref_node} t{prefix} vdd 0 pch_svt_1p8v width=5u length=.18u multi=1",
      f"XN{prefix}RESETQ {out_node} {clk_node} 0 0 nch_svt_1p8v width=4u length=.18u multi=1",
      f"XN{prefix}RESETB {inv_node} {clk_node} 0 0 nch_svt_1p8v width=4u length=.18u multi=1",
      f"XN{prefix}REGENQ {out_node} {inv_node} 0 0 nch_svt_1p8v width=6u length=.18u multi=1",
      f"XN{prefix}REGENB {inv_node} {out_node} 0 0 nch_svt_1p8v width=6u length=.18u multi=1",
      f"C{prefix}Q {out_node} 0 10f",
      f"C{prefix}QB {inv_node} 0 10f",
    ]
    return lines

def deck(corner:str="tt",delta_v:float=.04):
    vl=VREF-delta_v
    vh=VREF+delta_v
    # Input first 2 cycles LOW, next 2 HIGH, alternating.
    period=CLOCK_PERIOD_NS
    lines=[
       "* P3-INFORMED clocked PMOS input regenerative latch (not paper Fig14)",
       f'.include "db180_svt018_{corner}.lib"',
       ".temp 27",
       "VDD vdd 0 1.8",
       f"VREF vref 0 {VREF}",
       # 1.8GHz samples: CLK=LOW evaluation between ~0.075 and 0.335 ns.
       f"VCLK clk 0 PULSE(1.8 0 0.075n 5p 5p 0.255n {period:.9f}n)",
       f"VIN vin 0 PULSE({vl:.8g} {vh:.8g} {2*period:.9f}n 8p 8p {2*period-.016:.9f}n {4*period:.9f}n)",
    ]+latch_devices()
    stop=N_CYCLES*period
    lines += [
       ".control","set noaskquit",
       f"tran 2p {stop:.9f}n",
       "wrdata dyn_latch.csv time v(vin) v(q) v(qb) i(vdd)",
       "quit",".endc",".end",
    ]
    return "\n".join(lines)+"\n"

def parse_csv(path:Path):
    rows=[]
    for line in path.read_text().splitlines():
        try: a=[float(x) for x in line.split()]
        except ValueError: continue
        if len(a)>=10 and all(math.isfinite(x) for x in a):
            rows.append({"time_s":a[0],"vin_V":a[3],"q_V":a[5],"qb_V":a[7],"supply_A":a[9]})
    if len(rows)<200:
        raise RuntimeError(f"ngspice returned too few transient samples: {len(rows)}")
    return rows

def interpolate(rows:list[dict],time_s:float,field:str):
    from bisect import bisect_left
    times=[r["time_s"] for r in rows]
    ix=bisect_left(times,time_s)
    if ix<=0:return rows[0][field]
    if ix>=len(rows):return rows[-1][field]
    a,b=rows[ix-1],rows[ix]
    frac=(time_s-a["time_s"])/(b["time_s"]-a["time_s"])
    return a[field]*(1-frac)+b[field]*frac

def test(out:Path):
    out.mkdir(parents=True,exist_ok=True)
    work=TX.ENGINE_DIR/"p3_dynamic_latch"
    runner=TX.SpiceRunner(work)
    for corner in ("tt","ff","ss"):
        p=TX.model_path(corner)
        dest=work/p.name
        if not dest.exists() or p.stat().st_mtime>dest.stat().st_mtime:
            shutil.copy2(p,dest)
    result=[]
    for corner in ("tt","ff","ss"):
        for delta in (.04,.08):
            runner.run(deck(corner,delta),f"latch_{corner}_{int(delta*1000)}mV")
            raw=parse_csv(work/"dyn_latch.csv")
            if corner=="tt" and delta==.04:
                with (out/"latch_tt_40mV_waveform.csv").open("w",newline="") as f:
                    wr=csv.DictWriter(f,fieldnames=list(raw[0]))
                    wr.writeheader();wr.writerows(raw)
            successes=0; checks=[]
            for cycle in range(2,N_CYCLES-1):
                tm=(cycle*CLOCK_PERIOD_NS+SAMPLE_PHASE_NS)*1e-9
                inp=interpolate(raw,tm,"vin_V")
                q=interpolate(raw,tm,"q_V")
                qb=interpolate(raw,tm,"qb_V")
                decision=int(q>qb)
                actual=int(inp>VREF)
                checks.append({"cycle":cycle,"vin_V":inp,"q_V":q,"qb_V":qb,
                               "expected":actual,"observed":decision})
                successes+=int(decision==actual)
            r={
              "corner":corner,"differential_input_mV":2*delta*1e3,
              "samples_evaluated":len(checks),"correct":successes,
              "accuracy":successes/len(checks),
              "output_positive_max_V":max(z["q_V"] for z in checks),
              "output_positive_min_V":min(z["q_V"] for z in checks),
              "cases":checks
            }
            result.append(r)
            print(f"{corner} +/-{delta*1000:.0f}mV: {successes}/{len(checks)} correctly resolved, "
                  f"Q range {r['output_positive_min_V']:.3f}..{r['output_positive_max_V']:.3f}V",flush=True)
    d={
       "status":"executed_transistor_clocked_regenerative_comparator",
       "rate_GHz":1/CLOCK_PERIOD_NS,
       "silicon":"independent DB HiTek 180nm SVT PMOS-input regenerative latch",
       "not_paper_exact_m1_to_m19":True,
       "per_corner":result,
       "ngspice_calls":runner.calls,
       "limits":[
           "Clock waveform is ideal, generated by PULSE not PLL",
           "No mismatches beyond FF/SS, no offset trim, metastability or input capacitance back-annotation",
           "Standalone sampling on ideal square inputs, not yet linked to real P3 channel RX",
           "Not paper's exact Fig14 comparator transistor connections"
       ]
    }
    (out/"dynamic_latch_validation.json").write_text(json.dumps(d,indent=2)+"\n")
    passed=[r for r in result if r["corner"]=="tt" and r["differential_input_mV"]==80]
    assert passed and passed[0]["accuracy"]>=.95, "TT 80mV standalone clocked latch failed expected decisions"
    print("PASS: TT clocked PMOS regenerative latch independently resolves clocked symbols",flush=True)
    return d

if __name__=="__main__":
    p=argparse.ArgumentParser()
    p.add_argument("--out",type=Path,default=Path("results/spice/p3_dynamic_latch"))
    test(p.parse_args().out)
