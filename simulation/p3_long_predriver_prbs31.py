#!/usr/bin/env python3
"""512-bit nonrepeating PRBS31, physically buffered TX and MOS clocked RX.

The previously reconstructed CMOS TX gate predriver (two MOS inverter
stages per segmented gate), MOS reference PFD/CP/VCO, MOS RX latches
and optional physical current-starved MOS RX clock delay share a
single ngspice transient. Unlike the short PRBS7 run, this test uses
a 512-bit PRBS31 with identical seed, channel and TX bit rate.
TX predriver node dimensions and RX bias are identical across alpha
0.0 and alpha 0.30. Post-run scoring is audited SEPARATELY with ONE
integer frame lag per receiver bias, selected from training symbols.
No PRBS labels enter the physical PLL or clock actuation. No BER
or original 2004 silicon circuit equivalence is claimed.
"""
from __future__ import annotations
import argparse,csv,json,shutil
from pathlib import Path
import p3_transistor_driver as TX
import p3_mos_predriver_clock_retune as RETIME
import p3_mos_tx_predriver as PRE
import p3_reference_pll_integrated_mos_link as LINK

BITS=512
SEED=0x54C4EE17
ALPHAS=(0.,.30)
BIASES=(.95,1.10)

def prbs31(n,seed=SEED):
    mask=(1<<31)-1;x=seed&mask;bits=[]
    if x==0:raise ValueError("Invalid seed")
    for _ in range(n):
        bits.append(x&1)
        x=((x<<1)&mask)|(((x>>30)^(x>>27))&1)
    return bits

def run(out,alpha,bias):
    if alpha not in ALPHAS or bias not in BIASES:raise ValueError
    out.mkdir(parents=True,exist_ok=True)
    label=f"alpha_{alpha:.2f}_bias_{bias:.2f}".replace(".","p")
    work=TX.ENGINE_DIR/("p3_long_fullMOS_ffe_"+label)
    sim=PRE.TXGateLargeRunner(work)
    src=TX.model_path("tt");dest=work/src.name
    if not dest.exists() or src.stat().st_mtime>dest.stat().st_mtime:
        shutil.copy2(src,dest)
    bits=prbs31(BITS)
    old=LINK.BITS
    try:
        LINK.BITS=BITS
        net=RETIME.build(bits,alpha,bias)
        sim.run(net,label)
        rows=LINK.read(work/"pll_driven_rx_wave.csv")
        pll=LINK.frequency(rows)
        physical,original=LINK.evaluate(rows,bits,LINK.START_DATA_NS)
        focus=[r for r in rows if r["time_s"]>=LINK.START_DATA_NS*1e-9]
        power={
          "physical_MOS_PLL_RX_clock_buffer_TX_CMOS_driver_1p8V_mW":
             LINK.time_weighted_power_mW(focus,"power_vdd_source_A",1.8),
          "MOS_TX_output_stage_0p5V_source_mW":
             LINK.time_weighted_power_mW(focus,"power_tx_source_A",.5)}
        power["summed_partial_power_mW"]=sum(power.values())
        report={
            "physical":"MOS segmented TX, two-stage MOS TX predriver, two-stage MOS RX clock delay, RX latch, MOS CP and VCO",
            "mixed_signal":"XSPICE 450MHz PFD, divider and ideal reference",
            "RX_delay_gate_fixed_V":bias,
            "FFE_alpha":alpha,
            "bits":BITS,"pattern":"PRBS31","seed_hex":hex(SEED),
            "channel":"ideal buffered two-pole RC -12dB at Nyquist, not RG58",
            "PLL":pll,"original_score":original,
            "partial_power_during_data":power,
            "postrun_sample_to_UI_alignment":"to be fitted once for alpha 0 and .3 in an independent holdout audit",
            "data_driven_CDR":False,
            "2004_chip_accuracy":False,
            "statistical_BER":False,
        }
        (out/(label+".json")).write_text(json.dumps(report,indent=2)+"\n")
        with (out/(label+"_physical_latch.csv")).open("w",newline="") as f:
            w=csv.DictWriter(f,fieldnames=list(physical[0]))
            w.writeheader();w.writerows(physical)
        print(
          f"PREDRIVER_PRBS31 alpha={alpha} RX_bias={bias} "
          f"VCO_GHz={pll['vco_GHz']:.9f} "
          f"initial_MOS_decisions={original['bit_errors_including_unresolved']}/"
          f"{original['samples_scored']} "
          f"P1p8_mW={power['physical_MOS_PLL_RX_clock_buffer_TX_CMOS_driver_1p8V_mW']:.4f} "
          f"PTX_mW={power['MOS_TX_output_stage_0p5V_source_mW']:.4f}",flush=True)
        return report
    finally:
        LINK.BITS=old

if __name__=="__main__":
    p=argparse.ArgumentParser()
    p.add_argument("--alpha",type=float,choices=ALPHAS,required=True)
    p.add_argument("--bias",type=float,choices=BIASES,required=True)
    p.add_argument("--out",type=Path,default=Path("results/spice/p3_long_predriver_PRBS31"))
    a=p.parse_args()
    run(a.out,a.alpha,a.bias)
