#!/usr/bin/env python3
"""Gain/capacitance sensitivity of in-SPICE Alexander phase detector.

The previous four-XOR run was invalid because the digital 'dup' and
'ddn' nodes collided case-insensitively with the reference PLL's dUP
and dDN nodes. Those were renamed ddata_up and ddata_dn and MOS PLL
frequency lock was restored. Independent mixed-mode Alexander detector
was then active (not all-U) but 40pF control capacitor attenuated its
phase-correction action to <0.5mV in 0.08us serial-data burst.

This experiment uses the SAME physical MOS TX/RX/PFD/CP/VCO and
physical CMOS delay stage, but tests a physical capacitive range of
0.8 and 2.0pF and signed feedback gains. Gain zero is a mandatory
negative control. Data labels are not read by the phase detector.
Successful reference PLL lock is NOT proof of recovered-data CDR lock.
"""
from __future__ import annotations
import argparse,json
from pathlib import Path
import p3_transition_qualified_mos_bbpd as B

CAPS_PF=(.8,2.)
GAINS_UA=(-80.,0.,80.)
SHIFTS=(-.05,.95)

def run(out,cap,gain,shift):
    if cap not in CAPS_PF or gain not in GAINS_UA or shift not in SHIFTS:raise ValueError
    old=(B.CONTROL_C,B.GAINS_UA)
    try:
        B.CONTROL_C=cap*1e-12
        B.GAINS_UA=GAINS_UA
        result=B.main(out/f"C{cap:.1f}pF",gain,shift)
    finally:
        B.CONTROL_C,B.GAINS_UA=old
    summary={
      "capacitance_pF":cap,"gain_uA":gain,"start_phase_UI":shift,
      "MOS_recovered_clock_status":result.get("reference_PLL"),
      "PD_activity":result.get("PD_activity"),
      "real_MOS_sample_holdout":result.get("coverage_aware_holdout",{}).get("holdout",{}),
      "phase_controller_digital_7bit_original":False,
      "proof_original_2004_CDR":False,
    }
    path=out/f"C{cap:.1f}pF"/"loop_gain_summary.json"
    path.write_text(json.dumps(summary,indent=2)+"\n")
    h=summary["real_MOS_sample_holdout"]
    pd=summary.get("PD_activity") or {}
    print(f"ALEXANDER_MOS_GAIN cap_pF={cap} gain_uA={gain} shift_UI={shift} "
          f"status={result['status']} "
          f"vco_GHz={result.get('reference_PLL',{}).get('vco_GHz')} "
          f"control_delta_mV={1e3*(pd.get('control_end_V',1.1)-1.1):.5f} "
          f"error={h.get('total_invalid')}/{h.get('expected')} "
          f"missing={h.get('missing')} wrong={h.get('wrong_regenerated')}",flush=True)
    return summary

if __name__=="__main__":
    a=argparse.ArgumentParser()
    a.add_argument("--cap",type=float,choices=CAPS_PF,required=True)
    a.add_argument("--gain",type=float,choices=GAINS_UA,required=True)
    a.add_argument("--shift",type=float,choices=SHIFTS,required=True)
    a.add_argument("--out",type=Path,default=Path("results/spice/p3_alexander_MOS_gain"))
    x=a.parse_args()
    run(x.out,x.cap,x.gain,x.shift)
