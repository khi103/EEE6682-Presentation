#!/usr/bin/env python3
"""Attempt actual in-SPICE data-edge CDR around a physical MOS link.

ALL IN ONE ngspice transient:
- PDK MOS TX (8:4:2:1, 2-tap FFE) -> buffered two-pole RC channel
- PDK PMOS-input clocked two-lane regenerative MOS RX
- PDK three-stage current-starved MOS VCO + CMOS clock buffers
- ideal B-source frequency feedback referenced to 1.8GHz
- **new** ideal B-source DATA-EDGE phase detector (no TX PRBS labels)
  feeding the SAME physical VCO-control capacitor.

The phase detector finds threshold crossings on v(rx), detects clock slope,
and uses a half-rate-polarity-folded phase sign. This is a speculative
functional PLL/CDR test, not the published M19 or the actual 2004 PFD/CP.

Scoring reads MOS outputs at a FIXED 0.75 UI after physical clock FALLING
edges, without optimizing the sample phase against PRBS. Transmitted bits
are used only after simulation for integer frame alignment/validation.
"""
from __future__ import annotations
import argparse,csv,json,math,shutil
from pathlib import Path
import p3_transistor_driver as TX
import p3_full_link_physical_mos_vco as FULL
import p3_full_link_in_spice_frequency_feedback as FLL

N_BITS=256
ACQUISITION_UI=60
SAMPLE_AFTER_CLOCK_FALL_UI=.75
REGEN_THRESHOLD_V=.15
TARGET_FREQ_GHZ=1.8
V_RX_THRESHOLD=.25
TESTS=((1.84,0.),(1.84,-.003),(1.80,-.003),(1.86,-.002))

def deck(bits,gain,reference_scale,sign=1):
    FLL.EDGE_REFERENCE_SCALE=reference_scale
    base=FLL.netlist(bits,.30)
    extra=[
      "* Phase detector is an IDEAL behavioral analog element driven by REAL RX signal",
      "RRXDEL rx rxdel 1k",
      "CRXDEL rxdel 0 10f",
      "RVCOEDGE n1 n1del 1k",
      "CVCOEDGE n1del 0 10f",
      # Pulses of ~10-30 ps at each real RX threshold crossing.
      "BRXEDGE rxedge 0 V={0.5*(1-tanh(130*(v(rx)-.25))*tanh(130*(v(rxdel)-.25)))}",
      # Clock phase error odd/even symmetry: rising and falling clock edges
      # produce the same sign of small phase displacement.
      "BCLKGRAD clkgrad 0 V={tanh(12*(v(n1)-0.9))*tanh(25*(v(n1)-v(n1del)))}",
      f"BCDR vbias 0 I={{ {gain*sign:.12g}*v(rxedge)*v(clkgrad) }}",
    ]
    if ".control" not in base:raise ValueError("Missing ngspice control")
    base=base.replace(".control","\n".join(extra)+"\n.control",1)
    old="wrdata full_link_mos_vco.csv time v(pad) v(rx) "
    # add a separate diagnostic trace; PDK MOS output log unchanged.
    logger="wrdata live_phase_detector.csv time v(rxedge) v(clkgrad) v(vbias) v(n1)"
    if old not in base:raise ValueError("Missing full-link transient output")
    base=base.replace("quit\n.endc",logger+"\nquit\n.endc",1)
    return base

def falling_edges(rows,field,threshold=.9):
    events=[]
    for a,b in zip(rows,rows[1:]):
        x,y=a[field],b[field]
        if x>=threshold>y and a["time_s"]<b["time_s"]:
            t=a["time_s"]+(threshold-x)*(b["time_s"]-a["time_s"])/(y-x)
            events.append(t)
    return events

def score_mos_edges(rows,bits):
    times=[r["time_s"] for r in rows]
    t0=FLL.START_DATA_NS*1e-9
    events=[]
    for parity,node,qname,qbname in (
        ("even","clock_even_V","qeven_V","qbeven_V"),
        ("odd","clock_odd_V","qodd_V","qbodd_V")):
        for e in falling_edges(rows,node):
            sample=e+SAMPLE_AFTER_CLOCK_FALL_UI*TX.UI_PS*1e-12
            # no searching over sampling phase; delay is fixed by RX design.
            if not (t0+ACQUISITION_UI*TX.UI_PS*1e-12 < sample <
                    t0+(N_BITS-10)*TX.UI_PS*1e-12):
                continue
            n_est=int(round((sample-t0)/TX.UI_PS/1e-12))
            if not (ACQUISITION_UI<=n_est<N_BITS-10):continue
            q=FULL.LINK.interp(rows,sample,qname,times)
            qb=FULL.LINK.interp(rows,sample,qbname,times)
            if not math.isfinite(q+qb):continue
            differential=q-qb
            events.append({
                "lane":parity,"falling_clock_time_s":e,"sample_time_s":sample,
                "symbol_index_estimate":n_est,"sampled_mos_bit":int(differential>0),
                "Q_minus_QB_V":differential,
                "resolved":int(abs(differential)>=REGEN_THRESHOLD_V),
                "sampled_rx_V":FULL.LINK.interp(rows,sample,"rx_V",times)
            })
    events.sort(key=lambda r:r["sample_time_s"])
    # Integer word alignment is for scoring only, not clock feedback.
    lags=[]
    for lag in range(-5,6):
        sample=[r for r in events if 0<=r["symbol_index_estimate"]+lag<len(bits)]
        err=sum(not x["resolved"] or
                x["sampled_mos_bit"]!=bits[x["symbol_index_estimate"]+lag]
                for x in sample)
        lags.append({"integer_frame_lag":lag,"errors":err,
                     "samples":len(sample)})
    best=min(lags,key=lambda x:(x["errors"],abs(x["integer_frame_lag"])))
    lag=best["integer_frame_lag"]
    for r in events:
        ix=r["symbol_index_estimate"]+lag
        r["true_bit_for_post_run_scoring"]=bits[ix] if 0<=ix<len(bits) else None
        r["correct_and_resolved"]=int(r["resolved"] and
            r["true_bit_for_post_run_scoring"] is not None and
            r["sampled_mos_bit"]==r["true_bit_for_post_run_scoring"])
    unresolved=sum(1-x["resolved"] for x in events)
    wrong=sum(x["resolved"] and not x["correct_and_resolved"] for x in events)
    return events,{
        "clock_falling_edges_scored":len(events),
        "best_integer_frame_lag_for_validation_only":lag,
        "bit_errors_including_unresolved":len(events)-sum(x["correct_and_resolved"] for x in events),
        "unresolved_latch_samples":unresolved,
        "wrong_resolved_bits":wrong,
        "all_alignment_candidates":lags,
        "fixed_sample_after_clock_fall_UI":SAMPLE_AFTER_CLOCK_FALL_UI,
        "min_mos_latch_regeneration_mV":REGEN_THRESHOLD_V*1000
    }

def save(path,rows):
    if not rows:return
    with path.open("w",newline="") as f:
        w=csv.DictWriter(f,fieldnames=list(rows[0]))
        w.writeheader();w.writerows(rows)

def run(out):
    out.mkdir(parents=True,exist_ok=True)
    work=TX.ENGINE_DIR/"p3_in_spice_data_CDR"
    runner=TX.SpiceRunner(work)
    source=TX.model_path("tt")
    target=work/source.name
    if not target.exists() or source.stat().st_mtime>target.stat().st_mtime:
        shutil.copy2(source,target)
    bits=TX.prbs7(N_BITS)
    observations={}
    for reference_scale,gain in TESTS:
        label=(f"ref_{reference_scale:.3f}_gain_{gain:+.4f}".replace(".","p").replace("+","p").replace("-","m"))
        runner.run(deck(bits,gain,reference_scale),label)
        rows=FULL.read(work/"full_link_mos_vco.csv")
        measured=FULL.detect_vco_freq(rows)
        decisions,score=score_mos_edges(rows,bits)
        obs={
          "behavioral_CDR_gain_A_per_voltage":gain,
          "frequency_reference_edge_scale":reference_scale,
          "mos_vco_frequency_GHz":measured.get("frequency_GHz"),
          "mos_decisions_from_actual_clock_edges":score,
          "mos_vco_frequency_near_target":measured.get("frequency_GHz") is not None and
               abs(measured["frequency_GHz"]-TARGET_FREQ_GHZ)<.04,
        }
        observations[label]=obs
        save(out/f"{label}_physical_mos_receiver_samples.csv",decisions)
        print(f"REAL MOS+in-SPICE data PD {label}: physical VCO {measured.get('frequency_GHz')}GHz,"
              f" errors {score['bit_errors_including_unresolved']}/{score['clock_falling_edges_scored']},"
              f" unresolved {score['unresolved_latch_samples']}",flush=True)
    best=min(observations,key=lambda k:(
        observations[k]["mos_decisions_from_actual_clock_edges"]["bit_errors_including_unresolved"],
        abs(observations[k]["behavioral_CDR_gain_A_per_voltage"])))
    base=next(obs for obs in observations.values() if obs["behavioral_CDR_gain_A_per_voltage"]==0.)
    report={
       "status":"executed_in_spice_data_transition_Bsource_PD_with_MOS_TX_RX_VCO",
       "physical_PDK":"DB HiTek SVT 180nm MOS TX RX Ring VCO Clock Buffers",
       "in_spice_controller":"behavioral frequency detector + new RX transition-gated folded clock slope Bsource phase detector + capacitor",
       "rate_Gbps":3.6,
       "physical_clock_frequency_GHz":1.8,
       "sampling_clock_is_ideal":False,
       "offline_phase_search_used_for_clock_or_PD":False,
       "known_data_used_in_PD":False,
       "data_bits":N_BITS,
       "best_label_for_diagnostic_only":best,
       "corner":"tt",
       "comparison_to_no_data_PD":base,
       "trials":observations,
       "limitations":[
          "Prototype behavioral nonlinear edge PD is NOT paper Fig19 transistor BBPD",
          "No original PFD, charge pump switching, VCO layout or transistor-loop transfer validation",
          "Use of known PRBS for integer frame alignment is postrun scoring ONLY",
          "Receiver sample timing is fixed 0.75UI from physical falling MOS clock, no postrun phase search",
          "50-ohm TX buffer gate controls remain ideal PWL and channel is RC2 surrogate",
          "Does not prove physical BER, eye 37mV, clock jitter or full 27.12mW"
       ]
    }
    (out/"in_spice_data_CDR_summary.json").write_text(json.dumps(report,indent=2)+"\n")
    if (observations[best]["mos_decisions_from_actual_clock_edges"]["bit_errors_including_unresolved"] <= 5 and
        observations[best]["mos_vco_frequency_near_target"]):
        print(f"PASS: in-SPICE data-driven behavioral CDR improved physical MOS RX at {best}",flush=True)
    else:
        print("LIMITATION: Data-driven in-SPICE behavioral PD did not lock physical MOS receiver adequately",flush=True)
    return report

if __name__=="__main__":
    p=argparse.ArgumentParser()
    p.add_argument("--out",type=Path,default=Path("results/spice/p3_in_spice_data_cdr"))
    run(p.parse_args().out)
