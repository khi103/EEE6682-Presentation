#!/usr/bin/env python3
"""Causal, DATA-ONLY timing recovery followed by a physical MOS RX test.

Pass A: run the actual DB HiTek 180nm 8:4:2:1 MOS transmitter + RC2
channel in ngspice and record V(rx).
Pass B: a digital transition-time CDR reads ONLY V(rx), nominal UI,
and VREF=0.25 V. Its event-by-event phase updates NEVER access
transmitted PRBS labels, even for initialization. A new clock PWL is
constructed from those recovered edges. The SAME PDK MOS TX/RC channel
and actual 2-lane regenerative MOS receiver then run in ngspice.
Pass C: PRBS bits are used only AFTER the MOS transient for scoring.

This is two-pass CAUSAL-WAVEFORM REPLAY / co-simulation, NOT a live
in-SPICE feedback loop, and its recovered clock voltage sources are
ideal. We explicitly do not claim a physical P3 PLL/CDR or BER.
"""
from __future__ import annotations
import argparse,csv,json,math,shutil,re
from bisect import bisect_left
from pathlib import Path
import p3_transistor_driver as TX
import p3_integrated_mos_link as LINK

N_BITS=256
UI_S=1/(3.6e9)
VREF=.25
GAIN=.15
FIRST_VALID=55
EVAL_GAP_UI=.42
EVAL_WIDTH_UI=.78
MIN_RESOLVED_V=.15
# Only one parameter per scenario is changed. No PRBS bits are passed to the CDR.
SCENARIOS=(
 ("ffe_initial_0p05_nominal",.30,.05,0.,True),
 ("ffe_initial_0p75_plus_1000ppm",.30,.75,1000.,True),
 ("ffe_initial_0p65_minus_1000ppm",.30,.65,-1000.,True),
 ("ffe_fixed_initial_0p75_plus_1000ppm",.30,.75,1000.,False),
 ("baseline_initial_0p75_plus_1000ppm",0.,.75,1000.,True),
)

def read_rc(path):
    return TX.parse_wrdata(path)

def crossings(rows,threshold=VREF):
    ans=[]
    for a,b in zip(rows,rows[1:]):
        va=a["rx_V"]-threshold
        vb=b["rx_V"]-threshold
        if va*vb < 0 and b["time_s"]>a["time_s"]:
            t=a["time_s"]-va*(b["time_s"]-a["time_s"])/(vb-va)
            if not ans or t-ans[-1] > .4*UI_S:ans.append(t)
    return ans

def wrap_phase(delta_ui):
    return (delta_ui+.5)%1-.5

def recover_clock(rows,initial_phase,rate_offset_ppm,feedback=True):
    """Process each RX crossing before issuing the next local clock edge.

    Known signals: analog RX(t), VREF=0.25V, approximate nominal UI,
    previous phase. Never data labels. Absolute sample index n is a
    VCO cycle counter, not the transmitted PRBS word.
    """
    ui_rx=UI_S*(1+rate_offset_ppm/1e6)
    events=[v for v in crossings(rows) if v>4*UI_S]
    phase=initial_phase%1
    next_event=0
    updates=[]
    schedule=[]
    for n in range(N_BITS):
        deadline=(n+.92)*ui_rx
        while next_event<len(events) and events[next_event]<deadline:
            e=events[next_event]
            p=((e/ui_rx)+.5)%1
            correction=GAIN*wrap_phase(p-phase) if feedback else 0.
            phase=(phase+correction)%1
            updates.append({"crossing_time_s":e,"target_sample_phase_mod_UI":p,
                "post_update_phase_mod_UI":phase,"phase_step_UI":correction,
                "change_detected":int(abs(correction)>1e-12)})
            next_event+=1
        # +1 UI for approximate receive filter latency (constant, not TX bits).
        t_sample=(n+1+phase)*ui_rx
        schedule.append({
            "bit_clock_cycle_index":n,
            "recovered_sample_time_s":t_sample,
            "phase_mod_UI":phase,
            "receiver_ui_s":ui_rx,
            "transition_events_seen":next_event,
            "feedback_enabled":bool(feedback),
        })
    if len(events)<25:
        raise RuntimeError(f"Insufficient signal threshold crossings: {len(events)}")
    if not all(x["recovered_sample_time_s"]<y["recovered_sample_time_s"] for x,y in zip(schedule,schedule[1:])):
        raise RuntimeError("Recovered timing is non-monotonic")
    return schedule,updates

def clock_source(name,schedule,parity):
    """Create 1.8V->0V evaluation windows for the appropriate MOS latch lane."""
    tpoints=[(0.,1.8)]
    for entry in schedule:
        n=entry["bit_clock_cycle_index"]
        if n%2!=parity:continue
        center=entry["recovered_sample_time_s"]*1e12
        down=center-EVAL_GAP_UI*UI_S*1e12
        up=down+EVAL_WIDTH_UI*UI_S*1e12
        edge_ps=2.
        tpoints += [(down-edge_ps/2,1.8),(down+edge_ps/2,0.),
                    (up-edge_ps/2,0.),(up+edge_ps/2,1.8)]
    if any(t2<=t1 for (t1,_),(t2,_) in zip(tpoints,tpoints[1:])):
        raise RuntimeError("Invalid/overlapping recovered CDR PWL events")
    lines=[f"VCLK{name} clk{name} 0 PWL("]
    lines += [f"+ {time_ps:.9f}p {value:.3f}" for time_ps,value in tpoints]
    lines[-1] += ")"
    return "\n".join(lines)

def generate_latch_deck(bits,alpha,schedule,corner="tt"):
    src=LINK.generate(bits,alpha,corner=corner)
    for node in ("even","odd"):
        src,count=re.subn(rf"(?m)^VCLK{node}[^\n]*\n","",src)
        if count!=1:raise ValueError(f"Could not replace {node} ideal clock")
    extra=clock_source("even",schedule,0)+"\n"+clock_source("odd",schedule,1)
    if ".control" not in src:raise ValueError("Missing ngspice control")
    src=src.replace(".control",extra+"\n.control",1)
    return src

def analyze_latches(wave,schedule,bits):
    times=[r["time_s"] for r in wave]
    decisions=[]
    for entry in schedule[FIRST_VALID:N_BITS-8]:
        n=entry["bit_clock_cycle_index"]
        t=entry["recovered_sample_time_s"]
        even=(n%2==0)
        node="qeven_V" if even else "qodd_V"
        nodeb="qbeven_V" if even else "qbodd_V"
        q=LINK.interp(wave,t,node,times)
        qb=LINK.interp(wave,t,nodeb,times)
        inp=LINK.interp(wave,t,"rx_V",times)
        diff=q-qb
        resolved=math.isfinite(diff) and abs(diff)>=MIN_RESOLVED_V
        bit=int(diff>0) if math.isfinite(diff) else None
        correct=resolved and bit==bits[n]
        decisions.append({
            "cycle_index":n,"sample_time_s":t,"true_bit_FOR_SCORING_ONLY":bits[n],
            "recovered_mos_bit":bit,"rx_V":inp,"latch_q_V":q,
            "latch_qb_V":qb,"latch_differential_V":diff,
            "resolved_at_150mV":int(resolved),"correct_and_resolved":int(correct),
            "phase_mod_UI":entry["phase_mod_UI"],
        })
    errors=sum(1-x["correct_and_resolved"] for x in decisions)
    unresolved=sum(1-x["resolved_at_150mV"] for x in decisions)
    errors_polarity=sum(x["resolved_at_150mV"] and
         x["recovered_mos_bit"]!=x["true_bit_FOR_SCORING_ONLY"] for x in decisions)
    return decisions,{
        "evaluated_bits":len(decisions),
        "total_errors_including_unresolved":errors,
        "unresolved_latch_samples":unresolved,
        "resolved_wrong_bits":errors_polarity,
        "error_fraction":errors/len(decisions),
        "mean_abs_latch_differential_mV":
          sum(abs(x["latch_differential_V"]) for x in decisions)/len(decisions)*1000.,
    }

def save_csv(path,entries):
    if not entries:return
    with path.open("w",newline="",encoding="utf-8") as f:
        w=csv.DictWriter(f,fieldnames=list(entries[0]))
        w.writeheader();w.writerows(entries)

def run(out):
    out.mkdir(parents=True,exist_ok=True)
    work=TX.ENGINE_DIR/"p3_blind_cdr"
    runner=TX.SpiceRunner(work)
    model=TX.model_path("tt")
    dest=work/model.name
    if not dest.exists() or model.stat().st_mtime>dest.stat().st_mtime:
        shutil.copy2(model,dest)
    bits=TX.prbs7(N_BITS)
    analog_waves={}
    for alpha in (0.,.30):
        codes=TX.ffe_codes(bits,alpha)
        runner.run(TX.make_transient(codes,LINK.TRIM_WU,LINK.TRIM_WD,
                                   gate_transition_ps=10),
                   f"transistor_tx_rc_{int(alpha*100)}")
        analog_waves[alpha]=read_rc(work/"tx_waveform.csv")
        print(f"PDK MOS TX/RC waveform alpha={alpha}: {len(analog_waves[alpha])} points",flush=True)
    results={}
    for name,alpha,init,ppm,feedback in SCENARIOS:
        schedule,updates=recover_clock(analog_waves[alpha],init,ppm,feedback)
        deck=generate_latch_deck(bits,alpha,schedule)
        runner.run(deck,"mos_rx_"+name)
        wave=LINK.read_trace(work/"full_link_waveform.csv")
        decisions,metrics=analyze_latches(wave,schedule,bits)
        results[name]={
          "mode_alpha":alpha,"initial_phase_mod_UI":init,
          "receiver_nominal_rate_offset_ppm":ppm,
          "cdr_enabled":feedback,
          "transition_events_processed":len(updates),
          "final_recovered_phase_mod_UI":schedule[-1]["phase_mod_UI"],
          "mos_latch":metrics,
          "recovery_used_transmitted_labels":False
        }
        save_csv(out/f"{name}_recovery_timing.csv",schedule)
        save_csv(out/f"{name}_physical_mos_decisions.csv",decisions)
        print(f"DATA-ONLY CDR {name}: MOS latch errors {metrics['total_errors_including_unresolved']}"
              f"/{metrics['evaluated_bits']}, unresolved={metrics['unresolved_latch_samples']},"
              f" phase={schedule[-1]['phase_mod_UI']:.4f}UI, transitions={len(updates)}",
              flush=True)
    report={
      "status":"two_pass_blind_transition_CDR_physically_clocked_MOS_latches",
      "scope":"actual ngspice MOS TX wave -> causal data-only edge timing controller -> ngspice two-lane MOS RX latches",
      "rate_Gbps":3.6,
      "test_bits":N_BITS,
      "evaluation_start_bit":FIRST_VALID,
      "threshold_V":VREF,
      "output_resolved_threshold_V":MIN_RESOLVED_V,
      "control_algorithm":"per-received-transition circular phase accumulator, no transmitted data labels",
      "actual_real_time_hardware_CDR":False,
      "simulation_passes":2,
      "notes":[
        "Two SPICE passes with Python time-stamped data transition replay; not simultaneous PFD/VCO feedback",
        "The regenerated recovered clocks are ideal PWL voltage sources, not the MOS VCO",
        "The 1-UI channel latency is an independent testbench assumption",
        "Scoring uses transmitted PRBS only after both simulation passes",
        "Never claim a physical 2004 Fig19 BBPD, original PLL, actual FR4/RG58, or BER <1e-12"
      ],
      "scenarios":results,
      "ngspice_calls":runner.calls
    }
    (out/"blind_CDR_mos_latch_summary.json").write_text(json.dumps(report,indent=2)+"\n")
    baseline=results["ffe_initial_0p75_plus_1000ppm"]["mos_latch"]
    control=results["ffe_fixed_initial_0p75_plus_1000ppm"]["mos_latch"]
    nominal=results["ffe_initial_0p05_nominal"]["mos_latch"]
    if nominal["total_errors_including_unresolved"]>5:
        raise AssertionError("Nominal CDR MOS receiver failed strict regenerated-output check")
    if baseline["total_errors_including_unresolved"]>15:
        raise AssertionError("+1000 ppm CDR receiver has too many resolved/unknown errors")
    if baseline["total_errors_including_unresolved"]>=control["total_errors_including_unresolved"]-15:
        raise AssertionError("Data-only timing tracking did not substantially beat fixed off-phase clock")
    print("PASS: Data-only transition CDR clocks real MOS RX with strict 150mV resolved-output checks",flush=True)
    return report

if __name__=="__main__":
    p=argparse.ArgumentParser()
    p.add_argument("--out",type=Path,default=Path("results/spice/p3_blind_cdr"))
    run(p.parse_args().out)
