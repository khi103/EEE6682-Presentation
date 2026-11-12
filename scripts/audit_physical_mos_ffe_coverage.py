#!/usr/bin/env python3
"""Post-run coverage-aware, held-out audit of physical MOS FFE comparison.

Reads the previously produced, immutable MOS clock/latch CSV files from
four independent 450-MHz reference-PLL ngspice runs. Does not use the
transmitted bits to alter any PLL, TX, RX or analog waveform.

The original exploratory score rounds sample timing to the closest TX
symbol index, which can map successive physical MOS clock samples to
the same expected bit. This audit maps timestamps to transmitted UI
windows with floor, explicitly counts duplicates and missing symbols,
uses ONE common packet integer lag fitted on a training interval
(18..79 UI), and evaluates held-out bits (80..245 UI).
"""
from __future__ import annotations

import argparse
import csv
import json
import math
from collections import defaultdict
from pathlib import Path

BITS=256
DATA_START_NS=1220.
UI_S=1/3.6e9
TRAIN_START,TRAIN_END=18,80
TEST_START,TEST_END=80,246
REGEN_V=.150
ALPHAS=(0.,.15,.30,.45)

def label(alpha):
    return f"alpha_{alpha:.2f}".replace(".","p")

def prbs7(n=256,seed=0x5D):
    state=seed&0x7f
    result=[]
    for _ in range(n):
        result.append(state&1)
        feedback=((state>>6)^(state>>5))&1
        state=((state<<1)&0x7f)|feedback
    return result

def load(folder):
    cases={}
    for alpha in ALPHAS:
        lab=label(alpha)
        files=list(folder.rglob(f"{lab}_mos_latch_samples.csv"))
        report=list(folder.rglob(f"{lab}_ablation.json"))
        if len(files)!=1 or len(report)!=1:
            raise RuntimeError(f"Expected exactly one MOS CSV and JSON for {lab}, found {len(files)} and {len(report)}")
        with files[0].open(newline="") as f:
            rows=list(csv.DictReader(f))
        src=json.loads(report[0].read_text())
        for r in rows:
            t=float(r["physical_clock_sample_s"])
            r["physical_clock_sample_s"]=t
            r["Q_minus_QB_V"]=float(r["Q_minus_QB_V"])
            r["regenerated"]=int(r["regenerated"])
            r["mos_decoded_bit"]=int(r["mos_decoded_bit"])
            r["raw_UI_floor"]=math.floor((t-DATA_START_NS*1e-9)/UI_S)
            r["raw_UI_round"]=round((t-DATA_START_NS*1e-9)/UI_S)
            r["phase_frac_UI"]=((t-DATA_START_NS*1e-9)/UI_S)%1
        cases[lab]={"alpha":alpha,"rows":rows,"original":src}
    return cases

def evaluate(rows,bits,lag,begin,end,method="floor"):
    by_bit=defaultdict(list)
    for r in rows:
        idx=r["raw_UI_floor" if method=="floor" else "raw_UI_round"]+lag
        if begin<=idx<end:
            by_bit[idx].append(r)
    tested=end-begin
    missing=0
    duplicates=0
    invalid=0
    wrong=0
    unresolved=0
    margins=[]
    for idx in range(begin,end):
        candidates=by_bit.get(idx,[])
        if not candidates:
            missing+=1
            invalid+=1
            continue
        if len(candidates)>1:
            duplicates+=len(candidates)-1
        # A fixed pre-declared, data-blind selection rule for duplicate
        # clocks: earliest falling-edge sample of the assigned UI.
        sample=min(candidates,key=lambda x:x["physical_clock_sample_s"])
        valid=bool(sample["regenerated"] and
                   abs(sample["Q_minus_QB_V"])>=REGEN_V)
        decoded=sample["mos_decoded_bit"]
        if not valid:
            unresolved+=1
            invalid+=1
        elif decoded != bits[idx]:
            wrong+=1
            invalid+=1
        margins.append((2*bits[idx]-1)*sample["Q_minus_QB_V"]*1e3)
    return {
      "expected_unique_bits":tested,"missing_UI":missing,
      "duplicate_extra_sample_events":duplicates,
      "wrong_regenerated_UI":wrong,
      "unresolved_UI":unresolved,
      "invalid_or_wrong_UI":invalid,
      "error_fraction_including_erasure":invalid/tested,
      "median_signed_Q_minus_QB_mV":sorted(margins)[len(margins)//2] if margins else None,
    }

def main(folder,out):
    cases=load(folder)
    bits=prbs7()
    training=[]
    for lag in range(-5,6):
        per={lab:evaluate(case["rows"],bits,lag,TRAIN_START,TRAIN_END)
             for lab,case in cases.items()}
        score=sum(r["invalid_or_wrong_UI"] for r in per.values())
        training.append({"lag":lag,"training_errors_all_alpha":score,
                         "missing_all_alpha":sum(r["missing_UI"] for r in per.values())})
    # Only TRAINING data chooses the one lag for every FFE setting.
    best=min(training,key=lambda r:(r["training_errors_all_alpha"],
                                     r["missing_all_alpha"],abs(r["lag"])))
    lag=best["lag"]
    holdout={}
    for lab,case in cases.items():
        rows=case["rows"]
        floor=evaluate(rows,bits,lag,TEST_START,TEST_END,"floor")
        rounded=evaluate(rows,bits,lag,TEST_START,TEST_END,"round")
        original=case["original"]
        phase=sorted(r["phase_frac_UI"] for r in rows)
        holdout[lab]={
          "alpha":case["alpha"],
          "one_common_training_selected_integer_lag":lag,
          "coverage_aware_floor_score":floor,
          "round_index_sensitivity_score":rounded,
          "clock_phase_in_transmitted_UI_p05":phase[int(len(phase)*.05)],
          "clock_phase_in_transmitted_UI_p50":phase[len(phase)//2],
          "clock_phase_in_transmitted_UI_p95":phase[int(len(phase)*.95)],
          "exploratory_original_full_packet":original["original_scoring"],
          "pll":original["pll"],
        }
        print(f"COVERAGE_AUDIT {lab} lag={lag} "
              f"holdout_errors={floor['invalid_or_wrong_UI']}/{floor['expected_unique_bits']} "
              f"missing={floor['missing_UI']} "
              f"extra_duplicate={floor['duplicate_extra_sample_events']} "
              f"wrong={floor['wrong_regenerated_UI']} "
              f"unresolved={floor['unresolved_UI']} "
              f"round_vs_floor={rounded['invalid_or_wrong_UI']}",
              flush=True)
    summary={
      "status":"post-run coverage and held-out scoring, physical MOS waveforms unchanged",
      "simulation_source_run":43171287092,
      "all_bits":BITS,
      "training_UI_index_range":[TRAIN_START,TRAIN_END],
      "holdout_UI_index_range":[TEST_START,TEST_END],
      "integer_lag_fitted_on":"common training interval pooled across all alpha cases",
      "common_integer_lag":lag,
      "training_lag_candidates":training,
      "comparison":holdout,
      "caveats":[
       "A known PRBS is used for POSTRUN integer lag selection and error scoring, never for clock/phase control",
       "The sample-to-UI mapping is a testbench evaluation against TX timing, not a fabricated receiver framing circuit",
       "Reference-PLL lock is not data-driven CDR lock; no actual measured BER",
       "Sampler output is physical MOS latch, but the channel is ideal-buffered two-pole RC",
       "A 166-bit holdout is a functionality test, not a statistically meaningful BER estimate",
      ]
    }
    out.mkdir(parents=True,exist_ok=True)
    (out/"heldout_coverage_aware_ffe.json").write_text(json.dumps(summary,indent=2)+"\n")
    with (out/"heldout_coverage_aware_ffe.csv").open("w",newline="") as f:
        columns=["alpha","sample_errors","missing","duplicate_extra_events",
                 "wrong_regenerated","unresolved","round_errors"]
        wr=csv.DictWriter(f,fieldnames=columns)
        wr.writeheader()
        for item in holdout.values():
            fs=item["coverage_aware_floor_score"]
            wr.writerow({
                "alpha":item["alpha"],"sample_errors":fs["invalid_or_wrong_UI"],
                "missing":fs["missing_UI"],"duplicate_extra_events":fs["duplicate_extra_sample_events"],
                "wrong_regenerated":fs["wrong_regenerated_UI"],
                "unresolved":fs["unresolved_UI"],
                "round_errors":item["round_index_sensitivity_score"]["invalid_or_wrong_UI"],
            })
    return summary

if __name__=="__main__":
    p=argparse.ArgumentParser()
    p.add_argument("--in-dir",type=Path,required=True)
    p.add_argument("--out",type=Path,default=Path("results/audit/p3_ffe_heldout"))
    args=p.parse_args()
    main(args.in_dir,args.out)
