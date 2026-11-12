#!/usr/bin/env python3
"""Immutable 16-run physical 1024-bit MOS/XSPICE data-CDR independent audit.

Require a 4-seed x 2-start-phase x 2-code-to-MOS-gate step full matrix
and original 1024-bit transient execution. Interpret all 758 holdout
UI as received samples, and count missing, wrong and unresolved.
A reference PLL near 1.8GHz is NOT a data-locked CDR.
Produce direct controls with bit-level error counts and if a single
configuration is universally error-free across both phases and seeds.
"""
from __future__ import annotations
import argparse,csv,json,math
from pathlib import Path
SEEDS=("0x54c4ee17","0x13572468","0x2468ace1","0x41357268")
SHIFTS=(-.05,.95)
STEPS=(0.,3.)
N=758

def run(inp,out):
    out.mkdir(parents=True,exist_ok=True)
    data={}
    for p in inp.rglob("*_independent1024.json"):
        j=json.loads(p.read_text())
        key=(j["seed"],float(j["start_UI"]),float(j["step_mV_per_code"]))
        if key in data:raise RuntimeError(f"Duplicate case {key}")
        data[key]=j
    expected={(s,phase,gain) for s in SEEDS for phase in SHIFTS for gain in STEPS}
    if expected!=set(data):
        raise RuntimeError(f"Missing {sorted(expected-set(data))}; unexpected {sorted(set(data)-expected)}")
    rows=[]
    for key in sorted(data):
        d=data[key]
        h=d["MOS_RX"]
        if not d["actually_simulated_1024bits"]:
            raise AssertionError(f"Controller returned no valid physical MOS result: {key}")
        if h.get("expected")!=N:
            raise AssertionError(f"Not all 758 holdout UI scored for {key}: {h}")
        if h["total_invalid"]!=h["missing"]+h["unresolved"]+h["wrong_regenerated"]:
            raise AssertionError(f"False bit error accounting for {key}: {h}")
        rows.append({
          "seed_hex":key[0],"initial_phase_UI":key[1],
          "physical_gain_mV_per_counter_code":key[2],
          "sent_bits":1024,"holdout_bits":N,
          "invalid_including_erasures":h["total_invalid"],
          "missing_UI":h["missing"],"unresolved_MOS_latch":h["unresolved"],
          "wrong_regenerated_MOS_bit":h["wrong_regenerated"],
          "full_data_CDR_lock_electrically_proven":h["total_invalid"]==0,
        })
    with (out/"1024bit_MOS_CDR_case_summary.csv").open("w",newline="") as f:
        w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)
    pairwise=[]
    for s in SEEDS:
        for p in SHIFTS:
            zero=data[(s,p,0.)]["MOS_RX"]["total_invalid"]
            on=data[(s,p,3.)]["MOS_RX"]["total_invalid"]
            pairwise.append({"seed_hex":s,"phase_UI":p,"baseline_invalid":zero,
              "gain3_invalid":on,"absolute_error_reduction":zero-on})
            print(f"MOS1024_PAIR seed={s} phase_UI={p:+.2f} "
                  f"OFF={zero}/{N} ON_gain3={on}/{N} "
                  f"reduction={zero-on}",flush=True)
    summary={
      "source":"same one-SPICE 180nm MOS TX RX PLL and XSPICE four-XOR 7bit data counter",
      "cases":len(rows),"all_full_packet":True,
      "gain_zero_controls":len([r for r in rows if r["physical_gain_mV_per_counter_code"]==0.]),
      "zero_error_long_cases":sum(r["invalid_including_erasures"]==0 for r in rows),
      "smallest_observed_invalid":min(r["invalid_including_erasures"] for r in rows),
      "largest_observed_invalid":max(r["invalid_including_erasures"] for r in rows),
      "matched_controls":pairwise,
      "universally_locked_full_CDR":all(r["invalid_including_erasures"]==0 for r in rows if r["physical_gain_mV_per_counter_code"]==3.),
      "statistical_1e_minus12_BER_claim":False,
      "original_2004_Fig19_circuit_equivalence":False
    }
    (out/"1024bit_MOS_CDR_independent_summary.json").write_text(json.dumps(summary,indent=2)+"\n")
    print(f"MOS1024_AUDIT cases={len(rows)} "
          f"error_free_cases={summary['zero_error_long_cases']}/16 "
          f"best_invalid={summary['smallest_observed_invalid']}/{N} "
          f"universally_locked={summary['universally_locked_full_CDR']}",flush=True)
    return summary

if __name__=="__main__":
    p=argparse.ArgumentParser()
    p.add_argument("--in-dir",type=Path,required=True)
    p.add_argument("--out",type=Path,default=Path("results/audit/p3_MOS_1024_CDR"))
    args=p.parse_args()
    run(args.in_dir,args.out)
