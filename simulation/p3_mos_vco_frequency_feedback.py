#!/usr/bin/env python3
"""In-circuit frequency-locked loop controlling a REAL 180nm MOS VCO.

Actual MOS: 3-stage DB HiTek current-starved oscillator. Behavioral:
the phase/frequency detector is an ideal analog rising-edge-rate
discriminator made from B-sources and RC delay networks. Its output
charges a physical 20-pF loop capacitor and tunes the MOS oscillator.
This is one step beyond Python offline VCO calibration, but is NOT a
PFD / PLL or the published Fig18 original 2004 transistor schematic.
"""
from __future__ import annotations
import argparse,csv,json,math,shutil
from pathlib import Path
import p3_transistor_driver as TX
import p3_ring_vco_mos as VCO

TGT_GHZ=1.8
REF_PERIOD_PS=1e3/TGT_GHZ
PERIOD_NS=.5555555556
RUN_NS=220.
CLOOP=20e-12
GAIN=3e-3
TRIM_BIAS=(.78, .94)

def deck(initial_v, gain=GAIN, reference_detector_scale=1., stop_ns=RUN_NS):
    lines=[
      "* P3 INDEPENDENT MOS ring VCO with ngspice B-source FLL",
      '.include "db180_svt018_tt.lib"',
      ".temp 27",
      "VDD vdd 0 DC 1.8",
      f"VREF refclk 0 PULSE(0 1.8 0 3p 3p {REF_PERIOD_PS/2-3:.8g}p {REF_PERIOD_PS:.8g}p)",
      f"VSTART vstart 0 DC {initial_v}",
      f"CLOOP loopctrl 0 {CLOOP} ic={initial_v}",
      "RLEAK loopctrl vstart 100meg",
      "BNGATE nb 0 V={min(max(v(loopctrl),0.65),1.65)}",
      "BPGATE pb 0 V={1.8-v(nb)}",
      "* Rising edge extraction using a 1k/10f RC-delayed copy",
      "RREFDEL refclk refd 1k",
      "CREFDEL refd 0 10f",
      "RRINGDEL n1 n1d 1k",
      "CRINGDEL n1d 0 10f",
      f"BREFEDGE refedge 0 V={{ {0.25*reference_detector_scale:.12g}*(1+tanh(30*(v(refclk)-0.9)))*(1-tanh(30*(v(refd)-0.9))) }}",
      "BRINGEDGE ringedge 0 V={0.25*(1+tanh(30*(v(n1)-0.9)))*(1-tanh(30*(v(n1d)-0.9)))}",
      f"BLOOP loopctrl 0 I={{ {gain:.9g}*(v(ringedge)-v(refedge)) }}",
    ]
    for i in range(1,VCO.STAGES+1):
        n=f"n{i}"
        prev=f"n{i-1}" if i>1 else f"n{VCO.STAGES}"
        lines += [
           f"XPMAIN{i} {n} {prev} vp{i} vdd 0 pch_svt_1p8v width=4u length=.18u multi=1",
           f"XPSTARVE{i} vp{i} pb vdd vdd 0 pch_svt_1p8v width=4u length=.18u multi=1",
           f"XNMAIN{i} {n} {prev} vn{i} 0 nch_svt_1p8v width=2u length=.18u multi=1",
           f"XNSTARVE{i} vn{i} nb 0 0 nch_svt_1p8v width=2u length=.18u multi=1",
           f"CLOAD{i} {n} 0 {VCO.CL_F:.9g}",
        ]
    lines += [
      ".ic "+" ".join(f"v(n{i})={'1.8' if i%2 else '0'}" for i in range(1,VCO.STAGES+1)),
      ".control","set noaskquit",
      f"tran 3p {stop_ns}n uic",
      "wrdata fll.csv time v(n1) v(refclk) v(loopctrl) v(refedge) v(ringedge)",
      "quit",".endc",".end"
    ]
    return "\n".join(lines)+"\n"

def parse(path):
    rr=[]
    for line in path.read_text().splitlines():
        try:a=[float(x) for x in line.split()]
        except ValueError:continue
        if len(a)>=12 and all(math.isfinite(x) for x in a):
            rr.append({"time_s":a[0],"ring_V":a[3],"reference_V":a[5],
                       "tuning_bias_V":a[7],
                       "reference_rising_detector":a[9],
                       "ring_rising_detector":a[11]})
    if len(rr)<1000:raise RuntimeError("No FLL waveform")
    return rr

def measure(rr,begin_ns=RUN_NS-45):
    edges=[]
    for a,b in zip(rr,rr[1:]):
        if a["time_s"]<begin_ns*1e-9: continue
        if a["ring_V"]<.9<=b["ring_V"]:
            t=a["time_s"]+(.9-a["ring_V"])*(b["time_s"]-a["time_s"])/(b["ring_V"]-a["ring_V"])
            edges.append(t)
    periods=[b-a for a,b in zip(edges,edges[1:])]
    if len(periods)<45:
        return {"frequency_GHz":None,"edges":len(edges)}
    mean=sum(periods)/len(periods)
    return {"frequency_GHz":1/mean/1e9,"edges":len(edges),
            "median_tuning_bias_V":sorted(x["tuning_bias_V"] for x in rr[-3000:])[1500],
            "period_std_ps":math.sqrt(sum((p-mean)**2 for p in periods)/len(periods))*1e12}

def time_average(rows,field,begin_ns):
    a=[r for r in rows if r["time_s"]>=begin_ns*1e-9]
    if len(a)<100:raise RuntimeError("Not enough samples for edge detector calibration")
    area=sum((a[i][field]+a[i+1][field])*.5*(a[i+1]["time_s"]-a[i]["time_s"])
             for i in range(len(a)-1))
    return area/(a[-1]["time_s"]-a[0]["time_s"])


def run(out):
    out.mkdir(parents=True,exist_ok=True)
    work=TX.ENGINE_DIR/"p3_in_spice_fll"
    runner=TX.SpiceRunner(work)
    model=TX.model_path("tt")
    path=work/model.name
    if not path.exists() or model.stat().st_mtime>path.stat().st_mtime:
        shutil.copy2(model,path)
    # Calibrate different output edge slopes of ideal ref and physical MOS VCO.
    # In-circuit feedback still controls physical MOS bias; per-edge detector
    # gain is independently calibrated here once at nearly the target frequency.
    reference_bias=.86
    runner.run(deck(reference_bias,gain=0,stop_ns=65.),
               "fll_detector_calibration")
    cal=parse(work/"fll.csv")
    freq=measure(cal,begin_ns=25)["frequency_GHz"]
    if not freq:raise RuntimeError("Unforced calibration VCO did not oscillate")
    refmean=time_average(cal,"reference_rising_detector",20)
    ringmean=time_average(cal,"ring_rising_detector",20)
    reference_detector_scale=(ringmean/refmean)*(TGT_GHZ/freq)
    print(f"FLL per-edge calibration: physical ring at {freq:.4f}GHz, "
          f"edge detector gain correction={reference_detector_scale:.6f}",flush=True)
    results=[]
    for bias in TRIM_BIAS:
        runner.run(deck(bias,reference_detector_scale=reference_detector_scale),
                   f"fll_start_{int(bias*1000)}")
        rr=parse(work/"fll.csv")
        m=measure(rr)
        record={"initial_V":bias,"final_V":rr[-1]["tuning_bias_V"],
                "measured":m,"close_to_1p8GHz":m["frequency_GHz"] is not None and abs(m["frequency_GHz"]-1.8)<.025}
        results.append(record)
        record["final_edge_duty_ring"]=time_average(rr,"ring_rising_detector",RUN_NS-35)
        record["final_edge_duty_reference"]=time_average(rr,"reference_rising_detector",RUN_NS-35)
        if True:  # Preserve failure waveforms as engineering evidence.
            with (out/f"mos_fll_0p{int(bias*1000):03d}_waveform.csv").open("w",newline="") as f:
                wr=csv.DictWriter(f,fieldnames=list(rr[0]))
                wr.writeheader();wr.writerows(rr)
        print(f"FLL initial={bias:.3f} V, final={record['final_V']:.5f} V "
              f"frequency={m['frequency_GHz']} GHz lock_metric={record['close_to_1p8GHz']}",flush=True)
    report={
      "status":"real_MOS_VCO_ideal_B_edge_frequency_feedback_executed",
      "actual_physical_components":"DB HiTek SVT NMOS/PMOS ring VCO + 20pF loop capacitance and delay RC",
      "behavioral_components":"ideal B-source rising-edge detectors and loop current controller",
      "test_duration_ns":RUN_NS,"feedback_Gain_A_per_detector_difference":GAIN,
      "target_GHz":TGT_GHZ,"trials":results,
      "reference_edge_scale":reference_detector_scale,
      "calibration_initial_ring_frequency_GHz":freq,
      "not_actual_original_P3_PLL":True,
      "limits":[
        "This is an ideal behavioral frequency-locked loop; no phase lock detector or original PFD",
        "No original P3 7-bit MOS charge pump attached to this FLL control node",
        "No original 450MHz reference divider or PLL loop stability margins",
        "Not attached to MOS TX/channel/RX in a single feedback netlist",
      ]
    }
    (out/"real_mos_vco_fll_summary.json").write_text(json.dumps(report,indent=2)+"\n")
    if any(r["close_to_1p8GHz"] for r in results):
        print("PASS: B-source frequency feedback actually tuned MOS oscillator to ~1.8GHz",flush=True)
    else:
        print("LIMITATION: Frequency feedback did not capture 1.8GHz in this initial design",flush=True)
    return report

if __name__=="__main__":
    p=argparse.ArgumentParser()
    p.add_argument("--out",type=Path,default=Path("results/spice/p3_in_spice_fll"))
    run(p.parse_args().out)
