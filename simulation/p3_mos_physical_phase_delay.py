#!/usr/bin/env python3
"""Actual CMOS two-stage current-starved clock-delay characterization.

An independently sized pair of DB HiTek 180-nm starved CMOS inverters
is inserted between the physical, reference-locked MOS VCO and the MOS
receiver clock buffers. This is a REAL MOS phase-actuation experiment,
not a data-locked CDR. Both PMOS/NMOS starve gates are driven by an
externally specified ideal DC bias, and the original VCO reference PLL
remains closed. The Fig.19 digital loop is absent.

The controlled experiment holds the MOS TX, alpha=.3, RC channel, PLL,
PRBS7, 450-MHz reference, RX latches, and acquisition duration fixed.
The initial data timing is ±0.35 UI. We record VCO frequency, clock
propagation delay, MOS latch resolution and data decisions.
"""
from __future__ import annotations
import argparse,bisect,csv,json,math,shutil
from pathlib import Path
import p3_transistor_driver as TX
import p3_reference_pll_integrated_mos_link as LINK

BITS=256
ALPHA=.3
STARVE_BIASES=(0.,.65,.8,.95,1.1,1.25)
SHIFTS=(-.35,+.35)
REGEN=.15

def build(bits,bias,shift):
    start=LINK.START_DATA_NS+shift*TX.UI_PS*1e-3
    deck=LINK.netlist(bits,ALPHA,start_ns=start)
    if bias==0:
        return deck,start
    before="XPCLK_E clkeven n1 vdd vdd 0 pch_svt_1p8v"
    before2="XNCLK_E clkeven n1 0 0 nch_svt_1p8v"
    assert deck.count(before)==1 and deck.count(before2)==1
    deck=deck.replace(before,
        "XPCLK_E clkeven ph2 vdd vdd 0 pch_svt_1p8v")
    deck=deck.replace(before2,
        "XNCLK_E clkeven ph2 0 0 nch_svt_1p8v")
    lines=[
      "* Two physical current-starved MOS inverter clock delay stages",
      f"VPDNB pd_nb 0 DC {bias:.6f}",
      f"VPDPB pd_pb 0 DC {1.8-bias:.6f}",
    ]
    for i in (1,2):
        node=f"ph{i}"
        prev="n1" if i==1 else "ph1"
        lines+= [
          f"XP_PHMAIN{i} {node} {prev} ph_p{i} vdd 0 pch_svt_1p8v width=6u length=.18u multi=1",
          f"XP_PHSTARVE{i} ph_p{i} pd_pb vdd vdd 0 pch_svt_1p8v width=6u length=.18u multi=1",
          f"XN_PHMAIN{i} {node} {prev} ph_n{i} 0 nch_svt_1p8v width=3u length=.18u multi=1",
          f"XN_PHSTARVE{i} ph_n{i} pd_nb 0 0 nch_svt_1p8v width=3u length=.18u multi=1",
          f"CPH{i} {node} 0 20f",
        ]
    return deck.replace(".control","\n".join(lines)+"\n.control",1),start

def delay_measure(rows,first_s,last_s):
    # clkeven is inverted n1 after two noninverting delay stages.
    vco=LINK.rising(rows,"vco_V",first_s)
    even=LINK.falling(rows,"clkeven_V",first_s)
    vco=[x for x in vco if x<last_s]
    even=[x for x in even if x<last_s]
    delays=[]
    for t in vco:
        k=bisect.bisect_left(even,t)
        if k<len(even):
            delay=(even[k]-t)*1e12
            if 0<=delay<555.:
                delays.append(delay)
    if len(delays)<40:
        raise RuntimeError("Insufficient clock-delay edge pairs")
    delays.sort()
    return {"matched_physical_clocks":len(delays),
            "clock_delay_p05_ps":delays[int(.05*len(delays))],
            "clock_delay_median_ps":delays[len(delays)//2],
            "clock_delay_p95_ps":delays[int(.95*len(delays))],
            "clock_delay_max_minus_min_ps":delays[-1]-delays[0]}

def check(rows,bits,start):
    samples,original=LINK.evaluate(rows,bits,start)
    from collections import Counter
    idx=Counter(x["estimated_symbol_index"] for x in samples)
    v=[abs(s["Q_minus_QB_V"])*1000 for s in samples]
    return {"original_sample_scoring":original,
            "physical_RX_Qdiff_median_mV":sorted(v)[len(v)//2] if v else None,
            "physical_rx_unresolved_lt_150mV":sum(a<150 for a in v),
            "distinct_UI_index_count":len(idx),
            "duplicate_extra_events":sum(n-1 for n in idx.values() if n>1),
            "original_total_clock_samples":len(samples)}

def main(out,bias,shift):
    if bias not in STARVE_BIASES or shift not in SHIFTS:raise ValueError
    out.mkdir(parents=True,exist_ok=True)
    label=f"bias_{bias:.2f}_shift_{shift:+.2f}".replace(".","p").replace("+","plus").replace("-","minus")
    work=TX.ENGINE_DIR/("p3_physical_phase_delay_"+label)
    runner=TX.SpiceRunner(work)
    orig=TX.model_path("tt")
    copy=work/orig.name
    if not copy.exists() or orig.stat().st_mtime>copy.stat().st_mtime:
        shutil.copy2(orig,copy)
    bits=TX.prbs7(BITS)
    deck,start=build(bits,bias,shift)
    runner.run(deck,label)
    wave=LINK.read(work/"pll_driven_rx_wave.csv")
    pll=LINK.frequency(wave)
    rx=check(wave,bits,start)
    clock=delay_measure(wave,(start+2)*1e-9,
                          (start+(BITS-5)*TX.UI_PS*1e-3)*1e-9)
    summary={"case":label,"physical_phase_delay_bias_V":bias,
             "data_start_offset_UI":shift,"delay":clock,
             "reference_PLL":pll,"physical_RX":rx,
             "physical_clock_actuator":bias!=0,
             "receiver_data_feedback":False,
             "phase_bias_is_ideal_external":True,
             "original_paper_phase_control":False,
             "original_2004_silicon_equivalent":False,
             "limit":"Clock-delay actuator uses actual MOSFETs, but its DC bias is not generated by a BBPD controller"}
    (out/(label+".json")).write_text(json.dumps(summary,indent=2)+"\n")
    data=[w for w in wave if w["time_s"]>(start-1)*1e-9]
    with (out/(label+"_clocks.csv")).open("w",newline="") as f:
        writer=csv.DictWriter(f,fieldnames=["time_s","vco_V","clkeven_V","clkodd_V","rx_V"])
        writer.writeheader()
        writer.writerows([{k:r[k] for k in writer.fieldnames} for r in data[::max(1,len(data)//5000)]])
    print(f"PHYSICAL_PHASE_DELAY bias={bias} shift={shift:+.2f} "
          f"VCO={pll['vco_GHz']:.9f}GHz "
          f"delay_median_ps={clock['clock_delay_median_ps']:.3f} "
          f"error={rx['original_sample_scoring']['bit_errors_including_unresolved']}/"
          f"{rx['original_total_clock_samples']} "
          f"unresolved={rx['physical_rx_unresolved_lt_150mV']} "
          f"duplicate_events={rx['duplicate_extra_events']}",flush=True)
    return summary

if __name__=="__main__":
    p=argparse.ArgumentParser()
    p.add_argument("--bias",type=float,choices=STARVE_BIASES,required=True)
    p.add_argument("--shift",type=float,choices=SHIFTS,required=True)
    p.add_argument("--out",type=Path,default=Path("results/spice/p3_mos_physical_phase_delay"))
    a=p.parse_args()
    main(a.out,a.bias,a.shift)
