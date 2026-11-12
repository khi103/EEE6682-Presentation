#!/usr/bin/env python3
"""Actual 180nm MOS analog reference-offset calibration authority stress.

Reuses the physically executed 3.6Gbps MOS TX -> RC2 -> MOS regenerative
RX latches -> MOS switched-CP/VCO reference PLL, and real MOS current
sink controlled by a behavioral analogue voltage-error integrator.

Sweep receiver reference-source offset symmetrically:
  0.22, 0.25, 0.28, 0.30 V, with target 0.25 V.
The circuit is a UNIDIRECTIONAL MOS SINK: a below-target reference may
not be correctable by this topology, and is kept as a deliberately
failing negative control. No transmitted bit is used in calibration.
Nonzero controller and zero-gain are identical except feedback gain.
512-bit PRBS31, 358 heldout UI include missing and unresolved samples.
"""
from __future__ import annotations
import argparse,json
from pathlib import Path
import p3_auto_mos_rx_offset_servo as S

OFFSETS_V=(.22,.25,.28,.30)
GMS=(0.,.0001)
ALPHAS=(0.,.30)
CAL_TARGET=.25

def run(out,base,gm,alpha):
    if base not in OFFSETS_V or gm not in GMS or alpha not in ALPHAS:
        raise ValueError
    old=(S.REFERENCE_SOURCE,S.GMS,S.ALPHAS)
    try:
        S.REFERENCE_SOURCE=base
        S.GMS=GMS
        S.ALPHAS=ALPHAS
        name=f"base_{base:.2f}_gm_{gm*1e6:.0f}_ffe_{alpha:.2f}"
        result=S.main(out/name,alpha,gm)
    finally:
        S.REFERENCE_SOURCE,S.GMS,S.ALPHAS=old
    h=result.get("postrun_holdout",{}).get("holdout",{})
    vref=result.get("physical_ref",{}).get("during_last_data_reference_mV")
    metadata={
      "base_reference_V":base,"target_reference_V":CAL_TARGET,
      "initial_offset_mV":(base-CAL_TARGET)*1000,
      "physical":"MOS current-sink with Rfeed and Ccomp",
      "controller":"behavioral analog voltage error feedback, never PRBS labels",
      "sinks_current_only":True,
      "negative_offset_not_repairable_if_current_sink_only":base<CAL_TARGET,
      "gain_A_per_V":gm,"FFE_alpha":alpha,"loop_status":result.get("status"),
      "measured_Vref_mV":vref,
      "final_reference_error_mV":vref-250 if vref is not None else None,
      "heldout_wrong_unresolved_missing":h,
      "reference_PLL_GHz":result.get("PLL",{}).get("vco_GHz"),
      "original_Fig14_identical":False,
      "physical_fabrication_mismatch_MC":False}
    (out/name/"calibration_authority.json").write_text(json.dumps(metadata,indent=2)+"\n")
    print(f"RX_OFFSET_AUTHORITY base={base:.3f} gm={gm:.5g} alpha={alpha} "
          f"Vref_mV={vref} final_err_mV={metadata['final_reference_error_mV']} "
          f"heldout_invalid={h.get('invalid_or_wrong_UI')}/{h.get('expected_unique_bits')} "
          f"missing={h.get('missing_UI')} wrong={h.get('wrong_regenerated_UI')} "
          f"status={result.get('status')}",flush=True)
    return metadata

if __name__=="__main__":
    p=argparse.ArgumentParser()
    p.add_argument("--base",type=float,choices=OFFSETS_V,required=True)
    p.add_argument("--gm",type=float,choices=GMS,required=True)
    p.add_argument("--alpha",type=float,choices=ALPHAS,required=True)
    p.add_argument("--out",type=Path,default=Path("results/spice/p3_rx_auto_offset_robustness"))
    a=p.parse_args()
    run(a.out,a.base,a.gm,a.alpha)
