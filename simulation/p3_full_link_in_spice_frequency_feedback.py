#!/usr/bin/env python3
"""MOS TX/channel/RX + physical MOS VCO + in-SPICE FLL feedback.

Actual DB HiTek 180nm MOS:
  - 8:4:2:1 TX, 2 PMOS-input regenerative RX latches,
  - 3-stage tunable current-starved ring VCO and clock buffers.
In the SAME ngspice transient, a *BEHAVIORAL* B-source rising-edge
frequency discriminator compares the MOS oscillator with an ideal
1.8GHz reference and integrates loop error on a real capacitor.

The PRBS data burst begins after feedback acquisition. Receiver
sample phase is still PRBS-assisted offline, not recovered in SPICE.
Thus this is a frequency-closed but NOT full physical PLL/CDR.
"""
from __future__ import annotations
import argparse,csv,json,math,re,shutil
from pathlib import Path
import p3_transistor_driver as TX
import p3_full_link_physical_mos_vco as FULL
import p3_mos_vco_frequency_feedback as FLL

START_DATA_NS=555.
TARGET_F_GHZ=1.8
BIAS_INITIAL=1.0
EDGE_REFERENCE_SCALE=1.664661
K_FLL=3e-3
C_FLL=20e-12
BITS=128

def netlist(bits,alpha=.30):
    deck=FULL.build(bits,alpha,control=BIAS_INITIAL)
    deck,n1=re.subn(r"(?m)^VNB nb 0 [^\n]*\n","",deck)
    deck,n2=re.subn(r"(?m)^VPB pb 0 [^\n]*\n","",deck)
    if n1!=1 or n2!=1:raise RuntimeError("Expected initial VCO bias sources missing")
    extra=[
      "* behavioral frequency loop closed over actual 180nm ring VCO",
      f"VREFCLK refclk 0 PULSE(0 1.8 0 3p 3p {FLL.REF_PERIOD_PS/2-3:.8g}p {FLL.REF_PERIOD_PS:.8g}p)",
      f"VBIAS_INIT biasstart 0 {BIAS_INITIAL}",
      f"CLOOP vbias 0 {C_FLL} ic={BIAS_INITIAL}",
      "RLEAK vbias biasstart 100meg",
      "BNGATE nb 0 V={min(max(v(vbias),0.65),1.65)}",
      "BPGATE pb 0 V={1.8-v(nb)}",
      "RREFDEL refclk refdel 1k",
      "CREFDEL refdel 0 10f",
      "RRINGDEL n1 ringdel 1k",
      "CRINGDEL ringdel 0 10f",
      f"BREFEDGE refedge 0 V={{ {0.25*EDGE_REFERENCE_SCALE:.12g}*(1+tanh(30*(v(refclk)-0.9)))*(1-tanh(30*(v(refdel)-0.9))) }}",
      "BRINGEDGE ringedge 0 V={0.25*(1+tanh(30*(v(n1)-0.9)))*(1-tanh(30*(v(ringdel)-0.9)))}",
      f"BFLL vbias 0 I={{ {K_FLL:.9g}*(v(ringedge)-v(refedge)) }}",
    ]
    deck=deck.replace(".control","\n".join(extra)+"\n.control",1)
    # Delay ALL TX MOS FFE digital PWL stimuli until oscillator tracking settles.
    # No other plus-prefixed PWL continuation lines occur in this netlist.
    def shift(match):
        return f"{match.group(1)}{float(match.group(2))+START_DATA_NS*1e3:.6f}p{match.group(3)}"
    deck,n=re.subn(r"(?m)^(\+\s+)([\d.]+)p(\s+[-\d.+Ee]+)",shift,deck)
    if n<400:raise RuntimeError(f"Insufficient delayed PWL gate vectors: {n}")
    deck,n=re.subn(r"(?m)^tran 2p [\d.]+n uic$",
                   f"tran 3p {START_DATA_NS+len(bits)*TX.UI_PS*1e-3+3:.8f}n uic",deck)
    if n!=1:raise RuntimeError("Unable to extend MOS transient time")
    # Existing generated waveform includes all analog MOS, supply, and clock nodes.
    return deck

def run(out):
    out.mkdir(parents=True,exist_ok=True)
    work=TX.ENGINE_DIR/"p3_txrx_mos_vco_feedback"
    runner=TX.SpiceRunner(work)
    p=TX.model_path("tt")
    dest=work/p.name
    if not dest.exists() or p.stat().st_mtime>dest.stat().st_mtime:
        shutil.copy2(p,dest)
    bits=TX.prbs7(BITS)
    runner.run(netlist(bits,.30),"one_deck_mos_tx_rx_ring_fll")
    rows=FULL.read(work/"full_link_mos_vco.csv")
    vco=FULL.detect_vco_freq(rows)
    data_start=START_DATA_NS*1e-9
    relativized=[dict(r,time_s=r["time_s"]-data_start)
        for r in rows if r["time_s"]>=data_start-2e-9]
    decoded=FULL.phase_search(relativized,bits)
    # Retain a focused data window instead of the whole frequency-capture record.
    focus=[r for r in rows if r["time_s"]>=(START_DATA_NS-5)*1e-9]
    with (out/"physical_mos_link_with_in_spice_FLL_waveform.csv").open("w",newline="") as f:
        writer=csv.DictWriter(f,fieldnames=list(focus[0]))
        writer.writeheader();writer.writerows(focus)
    outcome={
       "status":"completed_same_netlist_MOS_TX_RX_VCO_with_behavioral_FLL",
       "mos_blocks":"DB HiTek SVT 8:4:2:1 TX, PMOS-input two-lane RX regenerative latches, MOS ring VCO, MOS clock buffers",
       "in_spice_loop":"B-source rising-edge frequency detector + physical loop capacitor driving real MOS VCO",
       "reference_clock_GHz":1.8,
       "data_rate_Gbps":3.6,"data_start_after_acquisition_ns":START_DATA_NS,
       "actual_vco_frequency":vco,
       "fll_near_target":bool(vco.get("frequency_GHz") and abs(vco["frequency_GHz"]-TARGET_F_GHZ)<.035),
       "MOS_RX_after_offline_PRBS_phase_training":decoded,
       "limited_to":"ideal 1.8GHz reference, behavioral FLL, offline PRBS phase/parity sampling, synthetic RC channel",
       "paper_correspondence":"NOT original Wong et al. dual-loop PLL/CDR or exact Fig14 comparator topology",
       "no_claims":["No physical PFD, charge-pump switches, analogue LDO, actual CDR loop or paper silicon full power/BER",
                    "Phase alignment uses full known PRBS sequence offline; a receiver cannot do this in real time without training/recovery"],
       "ngspice_runs":runner.calls,
    }
    (out/"mos_link_with_frequency_closed_clock.json").write_text(json.dumps(outcome,indent=2)+"\n")
    print("Full-chain in-SPICE feedback: MOS-VCO freq",vco.get("frequency_GHz"),
          "GHz, FLL near 1.8GHz =",outcome["fll_near_target"],
          "physical RX offline-aligned errors=",
          decoded["errors"],"/",decoded["bits_compared"],flush=True)
    if outcome["fll_near_target"] and decoded["errors"]<=10:
        print("PASS: in-SPICE FLL-driven real MOS VCO clocks the MOS TX/RC/RX link",flush=True)
    else:
        print("LIMITATION: Combined FLL/link did not fully meet current target",flush=True)
    return outcome

if __name__=="__main__":
    p=argparse.ArgumentParser()
    p.add_argument("--out",type=Path,default=Path("results/spice/p3_fll_integrated"))
    run(p.parse_args().out)
