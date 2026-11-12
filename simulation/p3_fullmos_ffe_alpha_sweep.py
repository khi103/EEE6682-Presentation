#!/usr/bin/env python3
"""12-case physical CMOS TX-FFE gain sweep with fixed MOS clock bias.

Simulates the FULL transistor-level reconstructed TX predriver,
segmental MOS voltage-mode driver, two-pole -12dB RC surrogate,
MOS RX latch, XSPICE PFD, switched-MOS charge pump and MOS VCO,
plus physical current-starved MOS clock delay.

Both PRBS31 pattern and 450MHz reference are kept fixed across 6 FFE
coefficients and 2 MOS clock delays. 512 symbols transmitted. Actual
SPICE analog RX voltages are retained for independent fixed-phase Eye
analysis; the existing PDK model bytes are never exported.

The original 2004 low-power slew-controller/ASIC is NOT duplicated.
"""
from __future__ import annotations
import argparse,csv,json
from pathlib import Path
import p3_long_predriver_prbs31 as ORIGINAL
import p3_reference_pll_integrated_mos_link as LINK

ALPHAS=(0.,.1,.2,.3,.4,.5)
BIASES=(.95,1.10)
def run(out,alpha,bias):
    if alpha not in ALPHAS or bias not in BIASES:raise ValueError
    out.mkdir(parents=True,exist_ok=True)
    prior=(ORIGINAL.ALPHAS,ORIGINAL.BIASES)
    old_read=LINK.read
    tag=f"alpha_{alpha:.2f}_bias_{bias:.2f}".replace(".","p")
    def instrumented_read(file):
        rows=old_read(file)
        focus=[row for row in rows if row["time_s"] >= (LINK.START_DATA_NS-1)*1e-9]
        with (out/f"{tag}_actual_analog_RX.csv").open("w",newline="") as f:
            field=["time_s","rx_V","vco_V","clkeven_V","clkodd_V"]
            wr=csv.DictWriter(f,fieldnames=field);wr.writeheader()
            wr.writerows([{k:r[k] for k in field} for r in focus[::max(1,len(focus)//10000)]])
        return rows
    try:
        ORIGINAL.ALPHAS=ALPHAS
        ORIGINAL.BIASES=BIASES
        LINK.read=instrumented_read
        result=ORIGINAL.run(out,alpha,bias)
    finally:
        ORIGINAL.ALPHAS,ORIGINAL.BIASES=prior
        LINK.read=old_read
    print(f"FULLMOS_FFE_ALPHA alpha={alpha:.2f} clock_bias={bias:.2f} "
          f"pattern=PRBS31_512 "
          f"f_GHz={result['PLL']['vco_GHz']:.9f} "
          f"PLL_RX_TXbuffer_mW={result['partial_power_during_data']['physical_MOS_PLL_RX_clock_buffer_TX_CMOS_driver_1p8V_mW']:.4f} "
          f"TXsignal_mW={result['partial_power_during_data']['MOS_TX_output_stage_0p5V_source_mW']:.4f}",flush=True)
    return result

if __name__=="__main__":
    p=argparse.ArgumentParser()
    p.add_argument("--alpha",type=float,choices=ALPHAS,required=True)
    p.add_argument("--bias",type=float,choices=BIASES,required=True)
    p.add_argument("--out",type=Path,default=Path("results/spice/p3_fullmos_ffe_alpha"))
    a=p.parse_args();run(a.out,a.alpha,a.bias)
