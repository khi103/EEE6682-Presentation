#!/usr/bin/env python3
"""Independent second-seed 512bit MOS FFE eye/power cross-validation.

The established physical two-stage CMOS TX predriver, 180nm MOS
segmented driver, RC2 channel, MOS regenerative RX latches, MOS
phase-delayed reference PLL and physical charge pump/VCO all share
the original ngspice transient. All devices, source amplitudes and
clock bias are kept unchanged from the first-seed six-alpha FFE run.

Only PRBS31 seed changes to 0x13572468. The original FFE alpha sweep
enforces complete transient through entire packet and retains actual
MOS RX voltage, latch bits and partial supply currents. Independent
holdout scoring selects a common frame and analog phase using TRAINING
bits only for ALL six alphas within each clock-bias group.

This is independent MOS FFE pattern sensitivity, not original 2004
silicon eye/BER or foundry mismatch Monte Carlo.
"""
from __future__ import annotations
import argparse,json
from pathlib import Path
import p3_fullmos_ffe_alpha_sweep as BASE
import p3_long_predriver_prbs31 as FULL
SEED=0x13572468
ALPHAS=BASE.ALPHAS
BIASES=BASE.BIASES

def run(out,alpha,bias):
    if alpha not in ALPHAS or bias not in BIASES:raise ValueError
    original=FULL.prbs31
    try:
        FULL.prbs31=lambda n:original(n,seed=SEED)
        result=BASE.run(out,alpha,bias)
    finally:
        FULL.prbs31=original
    path=out/(f"seed_{SEED:X}_alpha{alpha:.2f}_clock{bias:.2f}".replace(".","p")+".json")
    payload={"seed_hex":hex(SEED),"FFE_alpha":alpha,"MOS_clock_bias_V":bias,
             "source_report":result,"pattern_repeated_PRBS7":False,
             "original_2004_silicon":False}
    path.write_text(json.dumps(payload,indent=2)+"\n")
    print(f"SECOND_PRBS31_FULLMOS_FFE seed={SEED:#x} alpha={alpha} "
          f"clock_bias={bias} VCO_GHz={result['PLL']['vco_GHz']} "
          f"1p8_VDD_partial_mW={result['partial_power_during_data']['physical_MOS_PLL_RX_clock_buffer_TX_CMOS_driver_1p8V_mW']}",flush=True)
    return payload

if __name__=="__main__":
    p=argparse.ArgumentParser()
    p.add_argument("--alpha",type=float,choices=ALPHAS,required=True)
    p.add_argument("--bias",type=float,choices=BIASES,required=True)
    p.add_argument("--out",type=Path,default=Path("results/spice/p3_second_seed_MOS_FFE"))
    args=p.parse_args()
    run(args.out,args.alpha,args.bias)
