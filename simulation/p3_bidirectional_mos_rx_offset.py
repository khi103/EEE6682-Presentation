#!/usr/bin/env python3
"""Provisional true-MOS bidirectional receiver-reference calibration servo.

Previously, a real 180nm NMOS sinking current servo corrected positive
RX VREF offset but could NOT correct negative offset because it could
only draw current. This independently reconstructed extension adds a
real 180nm PMOS sourcing device from VDD and real 180nm NMOS sinking
device to ground; a single analogue integration node with two
complementary gate offsets adjusts their relative strengths.

This is a physical MOS correction actuator with an ideal B-source
feedback controller, not the paper's exact Fig14 digital comparator
offset calibration, not foundry mismatch Monte Carlo. It senses only
actual RX reference voltage and fixed 0.25V target, NEVER transmitted
PRBS labels or receiver errors.

Full MOS TX/RX/reference-PLL transient is required to complete the
512-bit PRBS31 burst before 358 heldout receiver samples are scored.
Report failed convergence or numeric issues without forcing a PASS.
"""
from __future__ import annotations
import argparse,json
from pathlib import Path
import p3_auto_mos_rx_offset_servo as ORIGINAL
import p3_reference_pll_integrated_mos_link as LINK
import p3_transistor_driver as TX

BASES=(.22,.25,.28,.30)
GAINS=(0.,.0001)
ALPHAS=(0.,.30)
START_CTRL=.80
PMOS_OFFSET=.55
NMOS_OFFSET=.25
PMOS_MULT=12
NMOS_MULT=9

def deck(bits,alpha,gm):
    d=old_deck(bits,alpha,gm)
    # START_CTRL is the integrator state, not MOS receiving reference.
    for original,replacement in [
      ("VSTARTCAL calstart 0 DC 0.350000",f"VSTARTCAL calstart 0 DC {START_CTRL:.6f}"),
      ("CCAL_V trimstate 0 5e-12 ic=0.350000",f"CCAL_V trimstate 0 5e-12 ic={START_CTRL:.6f}"),
      ("v(trimstate)=0.350000",f"v(trimstate)={START_CTRL:.6f}"),
      ("BVG_CAL gatecal 0 V={min(max(v(trimstate),0.0),1.2)}",
       f"BVG_CAL gatecal 0 V={{min(max(v(trimstate)-{NMOS_OFFSET},0.0),1.8)}}")
    ]:
        if d.count(original)!=1:
            raise RuntimeError(f"Analog MOS servo node not found: {original}")
        d=d.replace(original,replacement,1)
    extra=[
      "* True PMOS sourcing offset correction separate from NMOS sink",
      "BPMOSRXG gatecalp 0 V={min(max(v(trimstate)+.55,0.0),1.8)}",
      f"XPRXAUTO vref_rx gatecalp vdd vdd 0 pch_svt_1p8v width=.48u length=.36u multi={PMOS_MULT}",
    ]
    d=d.replace(".control","\n".join(extra)+"\n.control",1)
    return d

old_deck=ORIGINAL.deck
old_read=LINK.read

def strict_read(path):
    rows=old_read(path)
    expected_ns=LINK.START_DATA_NS+512*TX.UI_PS*1e-3+LINK.DATA_END_DELAY_NS
    if rows[-1]["time_s"]*1e9<expected_ns-.20:
        raise RuntimeError(f"TRUNCATED_MOS_REFERENCE_SERVO: "
            f"end={rows[-1]['time_s']*1e9:.4f} expected={expected_ns:.4f}ns")
    return rows

def run(out,base,gm,alpha):
    if base not in BASES or gm not in GAINS or alpha not in ALPHAS:raise ValueError
    out.mkdir(parents=True,exist_ok=True)
    old=(ORIGINAL.REFERENCE_SOURCE,ORIGINAL.GMS,ORIGINAL.ALPHAS,
         ORIGINAL.deck,LINK.read)
    label=f"base_{base:.2f}_gain_{gm:.4f}_alpha_{alpha:.2f}".replace(".","p")
    try:
        ORIGINAL.REFERENCE_SOURCE=base
        ORIGINAL.GMS=GAINS
        ORIGINAL.ALPHAS=ALPHAS
        ORIGINAL.deck=deck
        LINK.read=strict_read
        result=ORIGINAL.main(out/label,alpha,gm)
    finally:
        (ORIGINAL.REFERENCE_SOURCE,ORIGINAL.GMS,ORIGINAL.ALPHAS,
         ORIGINAL.deck,LINK.read)=old
    v=result.get("physical_ref",{})
    h=result.get("postrun_holdout",{}).get("holdout",{})
    info={
       "reference_source_V":base,"target_V":.25,
       "gain_A_per_V":gm,"FFE_alpha":alpha,
       "physical_PMOS_source_and_NMOS_sink":True,
       "behavioural_voltage_error_integrator":True,
       "original_fig14_exact":False,
       "real_foundry_MonteCarlo":False,
       "source_status":result.get("status"),
       "reference_mV":v.get("during_last_data_reference_mV"),
       "reference_final_error_mV":
          (v["during_last_data_reference_mV"]-250)
             if v.get("during_last_data_reference_mV") is not None else None,
       "heldout":h,
       "physical_PLL":result.get("PLL"),
    }
    (out/label/"bidirectional_mos_calibration.json").write_text(
       json.dumps(info,indent=2)+"\n")
    print(
      f"BIDIRECTIONAL_MOS_RX_OFFSET base_V={base:.2f} gm={gm:.5g} "
      f"alpha={alpha:.2f} status={result.get('status')} "
      f"vref_mV={info['reference_mV']} "
      f"reference_error_mV={info['reference_final_error_mV']} "
      f"heldout_invalid={h.get('invalid_or_wrong_UI')}/{h.get('expected_unique_bits')} "
      f"missing={h.get('missing_UI')} wrong={h.get('wrong_regenerated_UI')}",flush=True)
    return info

if __name__=="__main__":
    p=argparse.ArgumentParser()
    p.add_argument("--base",type=float,choices=BASES,required=True)
    p.add_argument("--gain",type=float,choices=GAINS,required=True)
    p.add_argument("--alpha",type=float,choices=ALPHAS,required=True)
    p.add_argument("--out",type=Path,
         default=Path("results/spice/p3_bidirectional_RX_reference"))
    a=p.parse_args()
    run(a.out,a.base,a.gain,a.alpha)
