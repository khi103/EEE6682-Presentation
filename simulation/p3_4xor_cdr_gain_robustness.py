#!/usr/bin/env python3
"""Cross-seed 4-XOR XSPICE MOS-data-phase feedback stability study.

The corrected 4-XOR phase detector has separate DFF and XOR node
names (case-insensitive ngspice node collision was fixed), uses actual
sampled MOS RX data, and feeds a MOS clock delay capacitor. The
reference MOS PLL is XSPICE-digital PFD / MOS CP and ring VCO. It is
NOT the full original 2004 7-bit saturating-counter data CDR.

For 256-bit non-repeating PRBS31 at two independent seeds:
 - same input data channel and 450MHz reference
 - no true bits used by BBPD, control source or phase selection
 - two start phases and two physical capacitor sizes
 - signed small gains and exact gain-zero controls
 - report heldout missing, duplicate, wrong and unresolved MOS latch
   results, not statistical BER and not silicon 2004 replication.
"""
from __future__ import annotations
import argparse,json
from pathlib import Path
import p3_xspice_4xor_mos_cdr as X

SEEDS=(0x54C4EE17,0x13572468)
GAINS=(-20.,-10.,-5.,0.,5.,10.,20.)
CAP_PF=(2.,8.)
SHIFTS=(-.05,.95)

def run(out,seed,gain,cap,shift):
    if seed not in SEEDS or gain not in GAINS or cap not in CAP_PF or shift not in SHIFTS:
        raise ValueError
    out.mkdir(parents=True,exist_ok=True)
    label=f"seed{seed:X}_gain{gain:+g}_C{cap:g}_shift{shift:+.2f}".replace("+","p").replace("-","m").replace(".","p")
    old=(X.PRBS_SEED,X.CCTRL,X.GAINS_UA)
    try:
        X.PRBS_SEED=seed
        X.CCTRL=cap*1e-12
        X.GAINS_UA=GAINS
        res=X.main(out/label,gain,shift)
    finally:
        X.PRBS_SEED,X.CCTRL,X.GAINS_UA=old
    h=res.get("heldout_coverage",{}).get("holdout",{})
    pll=res.get("reference_PLL",{})
    ld=res.get("four_XOR_logic_diagnostics",{})
    row={
      "experiment":"physical MOS 3.6Gbps receiver sampled four-XOR phase actuator",
      "seed_hex":hex(seed),"gain_uA":gain,"control_cap_pF":cap,
      "start_phase_UI":shift,
      "underlying_sim_status":res.get("status"),
      "reference_PLL_GHz":pll.get("vco_GHz"),
      "postrun_holdout":h,
      "digital_pd":ld,
      "original_2004_4XOR_counter_complete":False,
      "data_CDR_lock_proven":False,
    }
    (out/label/"cdr_data_stress_result.json").write_text(json.dumps(row,indent=2)+"\n")
    print(f"FOUR_XOR_STRESS seed={seed:#x} gain_uA={gain} cap_pF={cap} shift_UI={shift} "
          f"status={res.get('status')} f_GHz={pll.get('vco_GHz')} "
          f"holdout_errors={h.get('total_invalid')}/{h.get('expected')} "
          f"missing={h.get('missing')} wrong={h.get('wrong_regenerated')} "
          f"unresolved={h.get('unresolved')} "
          f"PD_vote_active_fraction={ld.get('nonzero_difference_fraction')}",flush=True)
    return row

if __name__=="__main__":
    p=argparse.ArgumentParser()
    p.add_argument("--seed",type=lambda s:int(s,0),choices=SEEDS,required=True)
    p.add_argument("--gain",type=float,choices=GAINS,required=True)
    p.add_argument("--cap",type=float,choices=CAP_PF,required=True)
    p.add_argument("--shift",type=float,choices=SHIFTS,required=True)
    p.add_argument("--out",type=Path,default=Path("results/spice/p3_4XOR_CDR_gain"))
    a=p.parse_args()
    run(a.out,a.seed,a.gain,a.cap,a.shift)
