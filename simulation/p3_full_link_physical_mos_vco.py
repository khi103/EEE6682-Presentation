#!/usr/bin/env python3
"""Single-netlist MOS TX + channel + MOS RX + PHYSICAL free-running MOS VCO.

The oscillator is an independently designed 3-stage DB HiTek SVT CMOS
current-starved ring. Its NMOS/PMOS gates share the TX/RX test PDK.
An offline calibration sweep selects the MOS VCO *bias voltage* that makes
its free-running frequency near 1.8GHz at TT. Two CMOS buffers supply
opposing phases to the two RX regenerative latches.

This is a complete functional analog TX-to-clocked-RX *testbench* with
real MOS TX, MOS RX and MOS oscillator. There is NO physical PLL/CDR
feedback: bias is tuned by external Python and PRBS sample phase is
selected offline. The channel is an ideal-buffered RC2 approximation;
TX FFE control is PWL, not a predriver transistor network.
"""
from __future__ import annotations
import argparse,csv,json,math,shutil,re
from pathlib import Path
import p3_transistor_driver as TX
import p3_integrated_mos_link as LINK
import p3_ring_vco_mos as OSC

N_BITS=128
F_TARGET=1.8
CORNER="tt"
BIAS_START=.80
BIAS_END=1.5

def build(bits,alpha,control,corner="tt"):
    deck=LINK.generate(bits,alpha,corner=corner)
    # Remove the TWO ideal half-rate clock sources, not the physical MOS latches.
    deck,n1=re.subn(r"(?m)^VCLKeven[^\n]*\n","",deck)
    deck,n2=re.subn(r"(?m)^VCLKodd[^\n]*\n","",deck)
    if n1!=1 or n2!=1:raise ValueError("Did not isolate ideal clocks")
    extra=[f"* physical MOS VCO at bias {control:.10g} V",
        f"VNB nb 0 {control:.10g}",
        f"VPB pb 0 {1.8-control:.10g}"]
    for i in range(1,OSC.STAGES+1):
        node=f"n{i}"
        prev=f"n{i-1}" if i>1 else f"n{OSC.STAGES}"
        extra += [
            f"XPVCO_MAIN{i} {node} {prev} vp{i} vdd 0 pch_svt_1p8v width=4u length=.18u multi=1",
            f"XPVCO_STARVE{i} vp{i} pb vdd vdd 0 pch_svt_1p8v width=4u length=.18u multi=1",
            f"XNVCO_MAIN{i} {node} {prev} vn{i} 0 nch_svt_1p8v width=2u length=.18u multi=1",
            f"XNVCO_STARVE{i} vn{i} nb 0 0 nch_svt_1p8v width=2u length=.18u multi=1",
            f"CVCO_LOAD{i} {node} 0 {OSC.CL_F}",
        ]
    extra += [
      # MOS inverters, not ideal complementary voltage waveforms.
      "XPCLK_E clkeven n1 vdd vdd 0 pch_svt_1p8v width=6u length=.18u multi=1",
      "XNCLK_E clkeven n1 0 0 nch_svt_1p8v width=3u length=.18u multi=1",
      "XPCLK_O clkodd clkeven vdd vdd 0 pch_svt_1p8v width=6u length=.18u multi=1",
      "XNCLK_O clkodd clkeven 0 0 nch_svt_1p8v width=3u length=.18u multi=1",
      ".ic "+" ".join(f"v(n{i})={'1.8' if i%2 else '0'}" for i in range(1,OSC.STAGES+1)),
    ]
    deck=deck.replace(".control","\n".join(extra)+"\n.control",1)
    deck=deck.replace("wrdata full_link_waveform.csv time v(pad) v(rx) "
        "v(qeven) v(qbeven) v(qodd) v(qbodd) i(vsup) i(vdd)",
        "wrdata full_link_mos_vco.csv time v(pad) v(rx) "
        "v(qeven) v(qbeven) v(qodd) v(qbodd) i(vsup) i(vdd) "
        "v(n1) v(clkeven) v(clkodd)")
    deck=re.sub(r"(?m)^tran 4p ([\d.]+n)$",r"tran 2p \1 uic",deck)
    if "tran 2p" not in deck:raise RuntimeError("Transient UIC init change missing")
    return deck

def read(path):
    out=[]
    for line in path.read_text().splitlines():
        try:v=[float(a) for a in line.split()]
        except ValueError:continue
        if len(v)<24 or not all(math.isfinite(x) for x in v):continue
        out.append({"time_s":v[0],"pad_V":v[3],"rx_V":v[5],
          "qeven_V":v[7],"qbeven_V":v[9],"qodd_V":v[11],"qbodd_V":v[13],
          "tx_A":v[15],"vdd_A":v[17],
          "vco_n1_V":v[19],"clock_even_V":v[21],"clock_odd_V":v[23]})
    if len(out)<2000:raise RuntimeError(f"Integrated physical VCO trace too short: {len(out)}")
    return out

def detect_vco_freq(rows):
    ss=[{"time_s":r["time_s"],"n1_V":r["vco_n1_V"]} for r in rows]
    return OSC.measure(ss)

def phase_search(rows,bits):
    # A near-zero Q-QB differential during RESET is NOT a valid data bit.
    # Require an independently resolved regenerative latch amplitude.
    RESOLVED_DIFFERENTIAL_V=0.15
    times=[r["time_s"] for r in rows]
    result=None
    for parity in (0,1):
        for phase_step in range(10,80): # 0.5 UI to 3.95 UI
            phase=phase_step*.05
            errors=0
            count=0
            unresolved=0
            sign_errors=0
            margin=[]
            for n in range(16,len(bits)-8):
                t=(n+phase)*TX.UI_PS*1e-12
                even=((n+parity)%2)==0
                q=LINK.interp(rows,t,"qeven_V" if even else "qodd_V",times)
                qb=LINK.interp(rows,t,"qbeven_V" if even else "qbodd_V",times)
                if not math.isfinite(q+qb):continue
                bit=int(q>qb)
                differential=abs(q-qb)
                resolved=differential>=RESOLVED_DIFFERENTIAL_V
                sign_errors+=int(bit!=bits[n])
                unresolved+=int(not resolved)
                errors+=int(bit!=bits[n] or not resolved)
                count+=1
                margin.append(differential)
            if count<80:continue
            candidate={
                "parity_mapping":parity,"offline_sample_phase_UI":phase,
                "errors":errors, "raw_sign_errors":sign_errors,
                "unresolved_samples":unresolved,
                "resolution_threshold_mV":RESOLVED_DIFFERENTIAL_V*1e3,
                "bits_compared":count,"observed_error_fraction":errors/count,
                "median_latch_differential_mV":sorted(margin)[len(margin)//2]*1e3
            }
            if result is None or (
                candidate["errors"],candidate["unresolved_samples"],
                -candidate["median_latch_differential_mV"]
                ) < (
                result["errors"],result["unresolved_samples"],
                -result["median_latch_differential_mV"]):
                result=candidate
    return result


def time_weighted_power_mW(rows, branch, supply_V):
    # Sign convention: current into voltage source is negative when supplying power.
    total_charge=0.
    for a,b in zip(rows,rows[1:]):
        dt=b["time_s"]-a["time_s"]
        if dt<0:raise ValueError("Negative simulation time increment")
        total_charge += .5*(a[branch]+b[branch])*dt
    dur=rows[-1]["time_s"]-rows[0]["time_s"]
    if dur<=0:raise ValueError("Empty transient duration")
    return -total_charge/dur*supply_V*1000.


def run(out):
    out.mkdir(parents=True,exist_ok=True)
    work=TX.ENGINE_DIR/"p3_integrated_physical_vco"
    runner=TX.SpiceRunner(work)
    src=TX.model_path(CORNER)
    dst=work/src.name
    if not dst.exists() or src.stat().st_mtime>dst.stat().st_mtime:
        shutil.copy2(src,dst)
    bits=TX.prbs7(N_BITS)
    lo,hi=BIAS_START,BIAS_END
    calibration=[]
    for iteration in range(10):
        vb=(lo+hi)/2
        runner.run(build(bits,.30,vb),f"cal_{iteration:02d}")
        rows=read(work/"full_link_mos_vco.csv")
        freq=detect_vco_freq(rows)
        if not freq["oscillating"]:
            lo=vb
        elif freq["frequency_GHz"]>F_TARGET:
            hi=vb
        else:
            lo=vb
        calibration.append({"iter":iteration,"gate_bias_V":vb,
                            "vco_freq_GHz":freq.get("frequency_GHz")})
        print(f"Physical MOS VCO calibration {iteration}: VBN={vb:.5f} V, "
              f"freq={freq.get('frequency_GHz')} GHz",flush=True)
    bias=(lo+hi)/2
    cases={}
    for label,alpha in (("baseline",0.),("ffe_0p30",.30)):
        runner.run(build(bits,alpha,bias),f"final_{label}")
        wave=read(work/"full_link_mos_vco.csv")
        f=detect_vco_freq(wave)
        decisions=phase_search(wave,bits)
        if label=="ffe_0p30":
            LINK.save_csv(out/"integrated_mos_vco_ffe_waveform.csv",wave)
        cases[label]={"vco_frequency_GHz":f.get("frequency_GHz"),
            "free_running_vco":f,"physical_RX_latch":decisions,
            "transistor_vdd_1p8V_source_power_mW":time_weighted_power_mW(wave,"vdd_A",1.8),
            "transistor_tx_signaling_0p5V_source_power_mW":time_weighted_power_mW(wave,"tx_A",.5)}
        print(f"ONE SPICE physical TX+VCO+RX {label}: frequency={f.get('frequency_GHz')} GHz; "
             f"min errors (offline phase training)={decisions['errors']}/{decisions['bits_compared']}",flush=True)
    report={
       "status":"executed_integrated_mos_tx_rx_ring_vco_free_running",
       "verified_scope":"physical MOS 3.6Gb/s TX, transistor RX 1.8GHz latches, physical MOS three-stage VCO all in single ngspice",
       "bias_training":"external Python frequency servo, not an in-circuit phase locked loop",
       "sampling_alignment":"offline PRBS-aided phase/parity search; NOT actual CDR",
       "target_half_rate_GHz":1.8,"calibration":calibration,
       "final_bias_V":bias,"cases":cases,
       "ngspice_runs":runner.calls,
       "power_scope":"Includes MOS VCO, RX latches and 0.5-V TX output-stage sources; excludes ideal TX gate drive, source termination reference and any PLL/PFD bias sources",
       "known_missing":[
          "No physical PFD/charge pump filter feedback connected to VCO",
          "No real-time CDR or BER estimation; test pattern used to train phase offline",
          "No actual paper high-speed comparator M1-M19 netlist, layout or specific PDK",
          "Ideal TX gate controls and two buffered RC channel poles; no measured RG58 S-params"
       ]}
    (out/"integrated_mos_vco_summary.json").write_text(json.dumps(report,indent=2)+"\n")
    assert cases["ffe_0p30"]["vco_frequency_GHz"] is not None
    assert abs(cases["ffe_0p30"]["vco_frequency_GHz"]-1.8)<.08,"VCO physical free-running frequency not close to 1.8GHz"
    print("PASS: Physical MOS VCO clocks the real transistor-latch receiver, in the same SPICE netlist",flush=True)
    return report

if __name__=="__main__":
    a=argparse.ArgumentParser()
    a.add_argument("--out",type=Path,default=Path("results/spice/p3_mos_vco_integrated"))
    run(a.parse_args().out)
