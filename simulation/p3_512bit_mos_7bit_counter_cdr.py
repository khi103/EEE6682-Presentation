#!/usr/bin/env python3
"""Extend actual XSPICE 7-bit four-XOR MOS data CDR to 512-bit PRBS31.

The physically connected system already includes 7-bit XSPICE
saturating UP/DOWN digital counter, four-XOR sampled data phase detector,
7-bit DAC mapped into actual two-stage MOS current-starved receiver clock
delay, physical MOS TX + MOS regenerative RX, actual switched-MOS
charge pump + VCO, and reference 450MHz XSPICE PFD/4.

Previously 256-bit PRBS31 scenarios sometimes reduced 40 to 10 errors,
but full 512-bit serial DATA lock was never proven. This challenge:
  - executes two different PRBS31 seeds and two unfavourable initial phases
  - compares zero actuator step against selected positive code-to-bias gains
  - requires actual transient to run past entire 512-bit burst BEFORE scoring
  - uses COMMON post-run training [18,144) and held-out [144,502)
  - never forwards known transmitted labels into XSPICE BBPD/counter
  - preserves counter saturation, unregenerated, missing and wrong MOS bits.

This is still an INDEPENDENT approximation, not Wong et al.'s exact
Fig19 timing and phase DAC, original 2004 MOS process or true BER.
"""
from __future__ import annotations
import argparse,json,math
from pathlib import Path
import p3_real_mos_7bit_data_counter as CORE
import p3_mos_tx_predriver as DRIVER
import p3_reference_pll_integrated_mos_link as LINK
import p3_live_mos_phase_servo as SCORE
import p3_transistor_driver as TX

SEEDS=CORE.SEEDS
SHIFTS=(-.05,.95)
STEP_MV=(0.,2.,4.,8.)
N_BITS=512
TRAIN=(18,144)
TEST=(144,502)

def run(out,seed,shift,step):
    if seed not in SEEDS or shift not in SHIFTS or step not in STEP_MV:
        raise ValueError
    out.mkdir(parents=True,exist_ok=True)
    before=(CORE.BITS,CORE.STEPS_MV,LINK.BITS,SCORE.TRAIN,SCORE.TEST,
            TX.SpiceRunner,LINK.read)
    def checked_read(path):
        rows=before[-1](path)
        expected_ns=LINK.START_DATA_NS + N_BITS*TX.UI_PS*1e-3 + LINK.DATA_END_DELAY_NS
        measured_ns=rows[-1]["time_s"]*1e9
        if measured_ns<expected_ns-.2:
            raise RuntimeError(f"INCOMPLETE_512BIT_MOS_CDR_SPICE: "
               f"actual end {measured_ns:.4f}ns, expected {expected_ns:.4f}ns")
        return rows
    try:
        CORE.BITS=N_BITS
        CORE.STEPS_MV=STEP_MV
        LINK.BITS=N_BITS
        SCORE.TRAIN=TRAIN
        SCORE.TEST=TEST
        TX.SpiceRunner=DRIVER.TXGateLargeRunner
        LINK.read=checked_read
        result=CORE.run(out,seed,shift,step)
    finally:
        (CORE.BITS,CORE.STEPS_MV,LINK.BITS,SCORE.TRAIN,SCORE.TEST,
         TX.SpiceRunner,LINK.read)=before
    data=result.get("physical_RX_score",{}).get("holdout",{})
    ctl=result.get("counter_and_MOS_actuation",{})
    audit={
       "seed_hex":hex(seed),"shift_UI":shift,"mV_per_counter_code":step,
       "received_PRBS31_bits":N_BITS,
       "training_UI_range":TRAIN,"heldout_UI_range":TEST,
       "strict_transient_completeness_required":True,
       "source_status":result.get("status"),
       "heldout":data,"counter":ctl,
       "original_P3_Fig19_identical":False,
       "statistically_verified_BER":False,
       "data_CDR_lock_proven":False,
    }
    tag=(f"seed_{seed:X}_phase{shift:+.2f}_step{step:+.0f}".replace("+","p").replace("-","m").replace(".","p"))
    (out/(tag+"_512bit_challenge.json")).write_text(json.dumps(audit,indent=2)+"\n")
    print(f"FULL_512BIT_MOS_CDR seed={seed:#x} shift_UI={shift} "
          f"step_mV={step} status={result.get('status')} "
          f"counter_min={ctl.get('range_counter_min')} max={ctl.get('range_counter_max')} "
          f"gate_pp_mV={ctl.get('actual_MOS_phase_control_peak_to_peak_mV')} "
          f"holdout_invalid={data.get('total_invalid')}/{data.get('expected')} "
          f"missing={data.get('missing')} wrong={data.get('wrong_regenerated')} "
          f"unresolved={data.get('unresolved')}",flush=True)
    return audit

if __name__=="__main__":
    p=argparse.ArgumentParser()
    p.add_argument("--seed",type=lambda s:int(s,0),choices=SEEDS,required=True)
    p.add_argument("--shift",type=float,choices=SHIFTS,required=True)
    p.add_argument("--step-mv",type=float,choices=STEP_MV,required=True)
    p.add_argument("--out",type=Path,default=Path("results/spice/p3_512bit_MOS_7bit_CDR"))
    a=p.parse_args()
    run(a.out,a.seed,a.shift,a.step_mv)
