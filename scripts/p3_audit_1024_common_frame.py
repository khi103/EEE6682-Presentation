#!/usr/bin/env python3
"""Re-score ALL 16 original 1024bit MOS CDR runs with shared trained framing.

The first 1024-bit score selected a post-run integer frame lag for each
zero/positive-gain run independently. That makes the data recovery
control comparison less strict. This forensic audit downloads the
IMMUTABLE same physical MOS latch sample CSV from all 16 actual runs.
For each PRBS31 seed + TX starting phase it selects exactly ONE common
integer lag pooling BOTH gain=0 and gain=3 training data [18,256).
Then the same fixed lag scores the untouched 758-bit holdout
[256,1014). Missed UI and unresolved analog MOS latch results count
as errors. No transmitted labels control the actual SPICE oscillator.

This checks fairness and can contradict earlier per-case results; it
does not claim original chip BER or lock from reference PLL alone.
"""
from __future__ import annotations
import argparse,csv,json,math
from collections import defaultdict
from pathlib import Path

SEEDS=(0x54C4EE17,0x13572468,0x2468ACE1,0x41357268)
PHASES=(-.05,.95)
GAINS=(0.,3.)
START_NS=1220.
UI_S=1/3.6e9
TRAIN=(18,256)
HOLD=(256,1014)

def bits31(n,seed):
    x=seed&((1<<31)-1);mask=(1<<31)-1
    b=[]
    for _ in range(n):
        b.append(x&1)
        x=((x<<1)&mask)|(((x>>30)^(x>>27))&1)
    return b

def filename(seed,phase,gain):
    v=f"seed_{seed:X}_phase_{phase:+.2f}_step_{gain:+g}mV"
    return v.replace("+","p").replace("-","m").replace(".","p")+"_MOS_bit_decisions.csv"

def load(inp,seed,phase,gain):
    name=filename(seed,phase,gain)
    files=list(inp.rglob(name))
    if len(files)!=1:raise RuntimeError(f"Physical MOS sample missing/duplicate: {name} => {len(files)}")
    data=[]
    with files[0].open(newline="") as f:
        for s in csv.DictReader(f):
            t=float(s["physical_clock_sample_s"])
            i=math.floor((t-(START_NS*1e-9+phase*UI_S))/UI_S)
            data.append({
              "UI":i,"time":t,
              "regenerated":int(s["regenerated"]),
              "qdiff":float(s["Q_minus_QB_V"]),
              "decoded":int(s["mos_decoded_bit"]),
            })
    if len(data)<500:raise RuntimeError(f"Too few physical clock samples for 1024bit {name}")
    return data

def score(data,bits,lag,lo,hi):
    by=defaultdict(list)
    for s in data:
        i=s["UI"]+lag
        if lo<=i<hi:by[i].append(s)
    missing=unres=wrong=dup=0
    for i in range(lo,hi):
        rows=by.get(i,[])
        if not rows:
            missing+=1
            continue
        dup+=len(rows)-1
        picked=min(rows,key=lambda a:a["time"])
        if not picked["regenerated"] or abs(picked["qdiff"])<.15:
            unres+=1
        elif picked["decoded"]!=bits[i]:
            wrong+=1
    return {"holdout_UI":hi-lo,"missing":missing,
        "unresolved":unres,"wrong_regenerated":wrong,
        "duplicate_clocks_extra":dup,
        "total_invalid":missing+unres+wrong}

def run(inp,out):
    out.mkdir(parents=True,exist_ok=True)
    result=[]
    for seed in SEEDS:
        bits=bits31(1024,seed)
        for phase in PHASES:
            samples={gain:load(inp,seed,phase,gain) for gain in GAINS}
            train=[(sum(score(samples[g],bits,lag,*TRAIN)["total_invalid"] for g in GAINS),
                    abs(lag),lag) for lag in range(-6,7)]
            shared=min(train)[-1]
            scores={}
            for gain in GAINS:
                h=score(samples[gain],bits,shared,*HOLD)
                row={
                  "seed":hex(seed),"initial_phase_UI":phase,
                  "gain_mV_per_counter_code":gain,
                  "common_training_lag":shared,
                  **h,
                }
                result.append(row);scores[gain]=h
                print(f"FAIR_MOS1024 seed={seed:#x} phase={phase:+.2f} "
                      f"gain={gain} common_lag={shared} "
                      f"invalid={h['total_invalid']}/758 "
                      f"missing={h['missing']} wrong={h['wrong_regenerated']} "
                      f"unresolved={h['unresolved']} dupes={h['duplicate_clocks_extra']}",
                      flush=True)
            print(f"FAIR_MOS1024_PAIR seed={seed:#x} phase={phase:+.2f} "
                  f"OFF={scores[0.]['total_invalid']} ON={scores[3.]['total_invalid']} "
                  f"reduction={scores[0.]['total_invalid']-scores[3.]['total_invalid']}",flush=True)
    with (out/"1024_shared_training_framing.csv").open("w",newline="") as f:
        w=csv.DictWriter(f,fieldnames=list(result[0]));w.writeheader();w.writerows(result)
    summary={
      "real_ngspice_1024bit_runs":16,
      "independent_actual_MOS_latch_CSVs_verified":len(result),
      "shared_training_frame_per_seed_and_phase":True,
      "training_range":TRAIN,"heldout_range":HOLD,
      "maximum_expected_bit_count":758,
      "all_data_CDR_gain3_cases_error_free":all(x["total_invalid"]==0 for x in result
                                                 if x["gain_mV_per_counter_code"]==3.),
      "per_case":result,
      "measured_BER_under_1e_minus12":False,
      "paper_original_Fig19_replica":False}
    (out/"1024_shared_training_framing.json").write_text(json.dumps(summary,indent=2)+"\n")
    return summary

if __name__=="__main__":
    p=argparse.ArgumentParser()
    p.add_argument("--in-dir",type=Path,required=True)
    p.add_argument("--out",type=Path,default=Path("results/audit/p3_MOS1024_shared_lag"))
    a=p.parse_args()
    run(a.in_dir,a.out)
