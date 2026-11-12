#!/usr/bin/env python3
"""Controlled 512-bit physical MOS/XSPICE data-counter vote gating experiment.

Baseline uses OR of two four-XOR UP paths and two four-XOR DOWN paths
to clock an actual XSPICE d_state saturating 7-bit counter driving
real DB HiTek 180nm MOS current-starved receiver clock-delay stages.

1024-bit independent PRBS31 evidence shows a persistent downward
counter bias: after ~768 received UI the count saturates at zero even
with zero physical gate gain. Before modifying the MOS PLL, test whether
this bias can be reduced with strictly local digital BBPD vote gating:

  collision: suppress simultaneous UP and DOWN
  transition: only update counter when two independent physical
              sampled MOS receiver data lanes disagree
  both: apply the two conditions together
  original: completely unchanged counter input logic (control)

Same 512-bit PRBS31, same physical TX/RX, reference PLL, channel,
counter clock, MOS phase actuator, initial 0.05/-0.95 UI timing,
and fixed physical gain 2mV/code are used for every mode.

This does NOT duplicate the original Wong et al. 2004 Fig.19
sampler/edge phase allocation. Even if an experimental gate makes
errors decrease, do not infer silicon BER or a data CDR lock.
"""
from __future__ import annotations
import argparse,json
from pathlib import Path
import p3_512bit_mos_7bit_counter_cdr as DRIVER
import p3_real_mos_7bit_data_counter as CORE

MODES=("original","collision","transition","both")
SEEDS=DRIVER.SEEDS
SHIFTS=DRIVER.SHIFTS
GAIN_MV=2.

def modify(deck,mode):
    if mode=="original":return deck
    orig=[
       "AANDUP [dcounter_up_raw denable] dcounter_up_enabled counter_gate_and",
       "AANDDN [dcounter_dn_raw denable] dcounter_dn_enabled counter_gate_and",
    ]
    for o in orig:
        if deck.count(o)!=1:raise RuntimeError(f"Unexpected digital counter vote connections: {o}")
    clauses=[]
    extras=["* Experimental transition and collision-qualified data CDR vote gate"]
    if mode in ("collision","both"):
        extras+= [
           "AINV_COUNTER_UP dcounter_up_raw dinv_up not_counter_up",
           "AINV_COUNTER_DN dcounter_dn_raw dinv_dn not_counter_dn",
           ".model not_counter_up d_inverter(rise_delay=8e-12 fall_delay=8e-12)",
           ".model not_counter_dn d_inverter(rise_delay=8e-12 fall_delay=8e-12)",
        ]
    if mode in ("transition","both"):
        extras+= [
           "AXOR_COUNTER_DATA [dD0 dD1] dcounter_data_transition data_change_xor",
           ".model data_change_xor d_xor(rise_delay=8e-12 fall_delay=8e-12)",
        ]
    up=["dcounter_up_raw","denable"]
    dn=["dcounter_dn_raw","denable"]
    if mode in ("collision","both"):
        up.append("dinv_dn")
        dn.append("dinv_up")
    if mode in ("transition","both"):
        up.append("dcounter_data_transition")
        dn.append("dcounter_data_transition")
    deck=deck.replace(orig[0],"AANDUP ["+" ".join(up)+"] dcounter_up_enabled counter_gate_and",1)
    deck=deck.replace(orig[1],"AANDDN ["+" ".join(dn)+"] dcounter_dn_enabled counter_gate_and",1)
    if deck.count(".control")!=1:raise RuntimeError("Missing single SPICE control")
    return deck.replace(".control","\n".join(extras)+"\n.control",1)

def run(out,seed,phase,mode):
    if seed not in SEEDS or phase not in SHIFTS or mode not in MODES:raise ValueError
    out.mkdir(parents=True,exist_ok=True)
    saved=CORE.make_deck
    try:
        CORE.make_deck=lambda bits,s,g: (
            (lambda deck,start:(modify(deck,mode),start))(*saved(bits,s,g)))
        result=DRIVER.run(out/str(mode),seed,phase,GAIN_MV)
    finally:
        CORE.make_deck=saved
    h=result["heldout"]
    counter=result["counter"] or {}
    row={
      "gate_mode":mode,"seed":hex(seed),"phase_UI":phase,
      "mV_per_code":GAIN_MV,
      "actual_7bit_XSPICE_saturating_counter":True,
      "real_MOS_phase_actuator":True,
      "transmitted_512_prbs31_bits_not_used_by_logic":True,
      "full_transient_status":result["source_status"],
      "heldout":h,"physical_counter":counter,
      "original_P3_4XOR_phase_detector_equivalent":False,
      "full_data_CDR_lock_proven":False,
    }
    tag=f"seed{seed:X}_phase{phase:+.2f}_mode{mode}".replace("+","p").replace("-","m").replace(".","p")
    (out/(tag+".json")).write_text(json.dumps(row,indent=2)+"\n")
    print(f"COUNTER_VOTE_GATE mode={mode} seed={seed:#x} "
          f"phase={phase:+.2f} errors={h.get('total_invalid')}/{h.get('expected')} "
          f"missing={h.get('missing')} unresolved={h.get('unresolved')} "
          f"wrong={h.get('wrong_regenerated')} "
          f"counter_min={counter.get('range_counter_min')} "
          f"counter_max={counter.get('range_counter_max')}",flush=True)
    return row

if __name__=="__main__":
    p=argparse.ArgumentParser()
    p.add_argument("--seed",type=lambda x:int(x,0),choices=SEEDS,required=True)
    p.add_argument("--phase",type=float,choices=SHIFTS,required=True)
    p.add_argument("--mode",choices=MODES,required=True)
    p.add_argument("--out",type=Path,default=Path("results/spice/p3_mos_counter_vote_gating"))
    a=p.parse_args();run(a.out,a.seed,a.phase,a.mode)
