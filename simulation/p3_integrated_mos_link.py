#!/usr/bin/env python3
"""One SPICE DECK: PDK-MOS FFE TX -> channel -> 2-lane PDK-MOS RX latch.

Physical transistors: DB HiTek 180nm SVT 8:4:2:1 output driver and
two independent clocked regenerative PMOS-input comparator latches.

Abstractions (NOT physical full original ASIC):
  - TX gate drivers and 1.8 GHz half-rate RX clocks are ideal sources;
  - TX impedance feedback calibration is fixed at TT, not interconnected;
  - 2-pole buffered RC surrogate is not paper's measured FR4/RG58;
  - no physical CDR/PLL, digital demux, offset or full TX+RX overhead.
Scope: prove electrical serial TX-to-RX signal propagation and clocked
transistor decisions in one ngspice transient with actual PDK.
"""
from __future__ import annotations
import argparse, csv, json, math, shutil
from bisect import bisect_left
from pathlib import Path
import p3_transistor_driver as TX
from p3_dynamic_latch_mos import latch_devices

N_BITS=128
UI_PS=TX.UI_PS
SAMPLE_LATENCY_UI=1.20
CLOCK_FALL_PHASE_UI=.95
EVALUATION_WIDTH_UI=.58
TRIM_WU=1.4896875
TRIM_WD=1.4896875
CORNER="tt"

def generate(bits,alpha:float,clock_phase_ui:float=CLOCK_FALL_PHASE_UI,
             corner:str=CORNER):
    codes=TX.ffe_codes(bits,alpha)
    d=TX.make_transient(codes,TRIM_WU,TRIM_WD,corner=corner,gate_transition_ps=10)
    period_ps=UI_PS*2
    def clk_source(name,first_bit):
        initial_delay=(first_bit+clock_phase_ui)*UI_PS
        evaluate_width=EVALUATION_WIDTH_UI*UI_PS
        return (f"VCLK{name} clk{name} 0 PULSE(1.8 0 "
                f"{initial_delay:.7f}p 5p 5p "
                f"{evaluate_width:.7f}p {period_ps:.7f}p)")
    extra=[
      "* P3 INDEPENDENT INTEGRATED DBHiTek MOS-TX / MOS-RX two-lane link",
      "* Ideal clock and 2-pole RC channel, original PLL/RX is not replicated",
      "VDD vdd 0 DC 1.8",
      clk_source("even",0),
      clk_source("odd",1),
    ]
    extra+=latch_devices("E","rx","vref","clkeven","qeven","qbeven")
    extra+=latch_devices("O","rx","vref","clkodd","qodd","qbodd")
    if ".control" not in d:raise ValueError("Cannot locate ngspice control")
    d=d.replace(".control","\n".join(extra)+"\n.control",1)
    original="wrdata tx_waveform.csv time v(pad) v(rx) i(vsup)"
    next_line=("wrdata full_link_waveform.csv time v(pad) v(rx) "
               "v(qeven) v(qbeven) v(qodd) v(qbodd) i(vsup) i(vdd)")
    if original not in d:raise ValueError("Cannot locate old signal log")
    d=d.replace(original,next_line)
    return d

def read_trace(path):
    rows=[]
    for line in path.read_text().splitlines():
        try:v=[float(x) for x in line.split()]
        except ValueError:continue
        if len(v)<18 or not all(math.isfinite(x) for x in v):continue
        rows.append({"time_s":v[0],"pad_V":v[3],"rx_V":v[5],
            "qeven_V":v[7],"qbeven_V":v[9],
            "qodd_V":v[11],"qbodd_V":v[13],
            "signaling_supply_A":v[15],"rx_supply_A":v[17]})
    if len(rows)<500:raise RuntimeError(f"Missing integrated waveform, {len(rows)} rows")
    return rows

def interp(rows, time_s, name, times=None):
    if times is None:times=[x["time_s"] for x in rows]
    ix=bisect_left(times,time_s)
    if ix<1 or ix>=len(rows):return float("nan")
    left,right=rows[ix-1],rows[ix]
    u=(time_s-left["time_s"])/(right["time_s"]-left["time_s"])
    return left[name]+(right[name]-left[name])*u

def average_power(rows,branch):
    import numpy as np
    t=[x["time_s"] for x in rows]
    i=[x[branch] for x in rows]
    vdd=1.8 if branch=="rx_supply_A" else .5
    return max(0., -float(np.trapezoid(i,t))/(t[-1]-t[0])*vdd*1e3)

def analyze(rows,bits):
    times=[r["time_s"] for r in rows]
    details=[]
    for n in range(16,len(bits)-8):
        t=(n+SAMPLE_LATENCY_UI)*UI_PS*1e-12
        even=(n%2==0)
        q=interp(rows,t,"qeven_V" if even else "qodd_V",times)
        qb=interp(rows,t,"qbeven_V" if even else "qbodd_V",times)
        rx=interp(rows,t,"rx_V",times)
        decoded=int(q>qb)
        details.append({"bit_index":n,"even_lane":int(even),
             "tx_bit":bits[n],"mos_comparator_bit":decoded,
             "correct":int(decoded==bits[n]),"rx_V":rx,
             "q_V":q,"qb_V":qb,"differential_latch_V":q-qb})
    if len(details)<80:raise ValueError("Insufficient clocked samples")
    errors=sum(1-r["correct"] for r in details)
    return details, {"data_bits_sampled":len(details),
            "bit_errors":errors,"observed_error_fraction":errors/len(details),
            "latch_min_abs_differential_at_sample_mV":
               min(abs(r["differential_latch_V"]) for r in details)*1e3,
            "latch_median_abs_differential_at_sample_mV":
               sorted(abs(r["differential_latch_V"]) for r in details)[len(details)//2]*1e3,
            "signal_source_average_mW":average_power(rows,"signaling_supply_A"),
            "receiver_latch_1p8V_source_average_mW":average_power(rows,"rx_supply_A")}

def save_csv(path,rows):
    if not rows:return
    with path.open("w",newline="") as f:
        w=csv.DictWriter(f,fieldnames=list(rows[0]))
        w.writeheader();w.writerows(rows)

def run(out:Path):
    out.mkdir(parents=True,exist_ok=True)
    working=TX.ENGINE_DIR/"p3_integrated_link"
    runner=TX.SpiceRunner(working)
    for corner in ("tt","ff","ss"):
        model=TX.model_path(corner)
        target=working/model.name
        if not target.exists() or model.stat().st_mtime>target.stat().st_mtime:
            shutil.copy2(model,target)
    bits=TX.prbs7(N_BITS)
    report={}
    for corner in ("tt","ff","ss"):
        for case,alpha in (("baseline",0),("ffe_0p30",.30)):
            runner.run(generate(bits,alpha,corner=corner),
                       f"integrated_{corner}_{case}")
            waveform=read_trace(working/"full_link_waveform.csv")
            decisions,metrics=analyze(waveform,bits)
            save_csv(out/f"{corner}_{case}_mos_rx_decisions.csv",decisions)
            if corner=="tt" and case=="ffe_0p30":
                save_csv(out/"tt_ffe_0p30_mos_tx_rx_latch_waveform.csv",waveform)
            report[f"{corner}_{case}"]=metrics
            print(f"Integrated {corner} {case}: {metrics['bit_errors']} errors "
                  f"over {metrics['data_bits_sampled']} real MOS latch samples, "
                  f"median Q-QB={metrics['latch_median_abs_differential_at_sample_mV']:.1f}mV, "
                  f"RX VDD={metrics['receiver_latch_1p8V_source_average_mW']:.3f}mW",flush=True)
    data={"status":"executed_integrated_pdk_tx_channel_clocked_pdk_rx",
          "simulation_backend":"single ngspice 42 transient per TX condition",
          "data_rate_Gbps":3.6,
          "two_clocked_receiver_lanes_GHz":1.8,
          "clock_source":"ideal PULSE; external CDR/PLL not yet connected",
          "mos_physical_blocks":"real 8:4:2:1 NMOS TX bank and two PMOS-input regenerative latches",
          "nonphysical_blocks":["TX gate source drivers","ideal 50-ohm VREF source",
               "two buffered RC channel poles","clock waveform source",
               "PLL, CDR, load demux and reference bias"],
          "calibration":"TT TX widths fixed from independent source impedance test; FF/SS use same sizing",
          "sample_latency_UI":SAMPLE_LATENCY_UI,
          "clock_eval_start_phase_UI":CLOCK_FALL_PHASE_UI,
          "observations":report,
          "limitations":[
             "Not exact source Fig7/8/14 physical topology",
             "No transistor-level PLL/VCO/PFD, CDR or adaptive clock lock",
             "Finite deterministic PRBS7 128-bit tests, not BER statistical proof",
             "No real 8cm-FR4+6.5m-RG58 measured Touchstone or package",
             "Separate 1.8V comparator source vs 0.5V TX signaling source and ideal clocks; incomplete power"
          ]}
    (out/"integrated_mos_link_summary.json").write_text(json.dumps(data,indent=2)+"\n")
    assert report["tt_ffe_0p30"]["bit_errors"]<=5, "Integrated transistor latch receiver does not meet 5/104 bit sanity target"
    print("PASS: true transistor MOS TX and clocked transistor RX in the SAME ngspice netlist",flush=True)
    return data

if __name__=="__main__":
    p=argparse.ArgumentParser()
    p.add_argument("--out",type=Path,default=Path("results/spice/p3_integrated_link"))
    run(p.parse_args().out)
