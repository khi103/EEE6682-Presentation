#!/usr/bin/env python3
"""Experimental *same-ngspice-deck* serial-data phase feedback to MOS PLL.

Runs real DB HiTek 180-nm 3.6Gb/s MOS TX, 2-pole RC surrogate,
physical PMOS MOS RX latches, reference XSPICE PFD /4, switched MOS
charge pump, RC filter and physical ring VCO. A BEHAVIORAL analogue
RX transition detector (ngspice B-source) injects a data-dependent
correction current directly into the REAL PLL filter. It is NOT the
paper's Fig. 19 four-XOR bang-bang circuit or a physical second CP.

TX bit labels are NEVER used by any phase detector or control source.
They are used after the completed SPICE transient only to score the
receiver. A data-start timing offset challenges the fixed reference-
PLL clock. Positive, negative and zero detector gains are controls.
"""
from __future__ import annotations

import argparse
import csv
import json
import math
import shutil
from pathlib import Path

import p3_transistor_driver as TX
import p3_reference_pll_integrated_mos_link as LINK

DATA_START_SHIFT_UI=0.35
ALPHA=.30
BITS=256
FREQUENCY_GHZ=1.8
VALID_GAIN=(-80e-6,-20e-6,0.,20e-6,80e-6)

def netlist(bits, gain_A, shift_ui):
    start_ns=LINK.START_DATA_NS + shift_ui*TX.UI_PS*1e-3
    base=LINK.netlist(bits,ALPHA,start_ns=start_ns)
    assert base.count(".control")==1
    extra=[
      "* Experimental received-data phase feedback for in-circuit MOS PLL",
      "* No transmitted bit labels or PYTHON-precomputed clock sources",
      "RRXCDR rx rxdel 2k",
      "CRXCDR rxdel 0 6f",
      "RVCOCDR n1 n1del 4k",
      "CVCOCDR n1del 0 8f",
      # A cross-threshold window suppresses activity except at analogue
      # RX crossings. The delayed RX indicates a transition without
      # knowing any transmitted bits.
      "BRXEDGE rxedge 0 V={exp(-((v(rx)-.25)/.020)*((v(rx)-.25)/.020))*"
        "tanh(100*(v(rx)-v(rxdel)))*tanh(100*(v(rx)-v(rxdel)))}",
      # Polarity folding across both VCO slopes: near either physical
      # clock transition this signal changes sign with early/late phase.
      "BCLKPHASE clockphase 0 V={tanh(8*(v(n1)-.9))*"
        "tanh(12*(v(n1)-v(n1del)))}",
      f"BCDRINJECT loopctrl 0 I={{ {gain_A:.10g}*v(rxedge)*v(clockphase) }}",
    ]
    base=base.replace(".control","\n".join(extra)+"\n.control",1)
    original="quit\n.endc"
    if base.count(original)!=1:
        raise RuntimeError("Expected one SPICE control quit section")
    base=base.replace(original,
        "wrdata experimental_data_pd.csv time v(rxedge) v(clockphase) "
        "v(loopctrl) v(vcobias) v(rx) v(n1)\nquit\n.endc",1)
    return base,start_ns

def vco_freq_over_window(rows, first_s, last_s):
    events=[t for t in LINK.rising(rows,"vco_V",first_s) if t<=last_s]
    if len(events)<4:
        return None
    period=(events[-1]-events[0])/(len(events)-1)
    return 1/(period*1e9)

def average_last_vctrl(rows,begin_s):
    r=[x["vco_control_V"] for x in rows if x["time_s"]>=begin_s]
    return sum(r)/len(r) if r else None

def save(path,rows):
    if not rows:
        return
    with path.open("w",newline="") as f:
        w=csv.DictWriter(f,fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)

def main(out,gain,shift_ui):
    if gain not in VALID_GAIN:
        raise ValueError(f"gain {gain} not in predetermined test matrix {VALID_GAIN}")
    out.mkdir(parents=True,exist_ok=True)
    label=("gain_"+f"{gain*1e6:+.0f}"+"_shift_"+
            f"{shift_ui:+.2f}").replace("+","p").replace("-","m").replace(".","p")
    work=TX.ENGINE_DIR/("p3_real_mos_data_feedback_"+label)
    runner=TX.SpiceRunner(work)
    model=TX.model_path("tt")
    destination=work/model.name
    if not destination.exists() or model.stat().st_mtime>destination.stat().st_mtime:
        shutil.copy2(model,destination)
    bits=TX.prbs7(BITS)
    deck,start_ns=netlist(bits,gain,shift_ui)
    runner.run(deck,label)
    rows=LINK.read(work/"pll_driven_rx_wave.csv")
    pll=LINK.frequency(rows)
    samples,decision=LINK.evaluate(rows,bits,start_ns)
    t0=start_ns*1e-9
    tend=(start_ns+BITS*TX.UI_PS*1e-3)*1e-9
    metrics={
      "receiver_samples":len(samples),
      "receiver_errors_including_unresolved":decision["bit_errors_including_unresolved"],
      "unresolved":decision["unresolved_MOS_latch_samples"],
      "unique_symbol_indices":len({x["estimated_symbol_index"] for x in samples}),
      "real_MOS_vco_during_data_GHz":vco_freq_over_window(
           rows,t0+20*TX.UI_PS*1e-12,tend-4*TX.UI_PS*1e-12),
      "mean_vco_gate_V_before_data":average_last_vctrl(
          [x for x in rows if x["time_s"]<t0],t0-10e-9),
      "mean_vco_gate_V_during_late_data":average_last_vctrl(rows,tend-15e-9),
    }
    valid_time=bool(metrics["real_MOS_vco_during_data_GHz"] and
                    abs(metrics["real_MOS_vco_during_data_GHz"]-FREQUENCY_GHZ)<.025)
    result={
      "gain_A":gain,"data_start_offset_UI":shift_ui,
      "pll_before_data":pll,"physical_rx":decision,
      "during_data":metrics,
      "physical_reference_PLL_still_near_1p8GHz":valid_time,
      "data_driven_feedback_is_physical_MOS_loop_connection":True,
      "data_phase_detector_is_behavioral_Bsource":True,
      "original_fig19_XOR_data_detector_reproduced":False,
      "real_2004_chip_reproduced":False,
      "no_transmitted_bits_used_by_PD":True,
      "actual_3p6Gbps_serial_data_CDR_lock_proven":False,
      "simulator":"ngspice PDK MOS + XSPICE digital reference PFD",
      "known_limitation":"Reference PLL suppresses phase-perturbation; this is a controlled characterization, not a demonstrated BBPD data loop",
    }
    save(out/f"{label}_clocked_MOS_RX.csv",samples)
    focus=[x for x in rows if x["time_s"]>=t0-3e-9]
    save(out/f"{label}_MOS_PLL_RX_waveform.csv",focus[::max(1,len(focus)//5000)])
    (out/f"{label}_data_feedback_result.json").write_text(
         json.dumps(result,indent=2)+"\n")
    print(
        f"PHYSICAL_DATA_PHASE_TEST gain_uA={gain*1e6:+.0f} shift_UI={shift_ui:+.2f} "
        f"PLL_ref_GHz={pll['vco_GHz']:.6f} "
        f"VCO_during_data_GHz={metrics['real_MOS_vco_during_data_GHz']} "
        f"RX_err={metrics['receiver_errors_including_unresolved']}/{metrics['receiver_samples']} "
        f"unresolved={metrics['unresolved']} "
        f"unique_symbol_indices={metrics['unique_symbol_indices']} "
        f"vco_clock_near_target={valid_time}",
        flush=True)
    return result

if __name__=="__main__":
    p=argparse.ArgumentParser()
    p.add_argument("--gain",type=float,choices=VALID_GAIN,required=True)
    p.add_argument("--shift-ui",type=float,default=DATA_START_SHIFT_UI)
    p.add_argument("--out",type=Path,
       default=Path("results/spice/p3_mos_in_spice_data_phase_test"))
    a=p.parse_args()
    main(a.out,a.gain,a.shift_ui)
