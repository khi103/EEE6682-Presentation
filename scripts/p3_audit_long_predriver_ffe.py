#!/usr/bin/env python3
"""Fair heldout 512-bit PRBS31 FFE-on/off comparison with actual MOS predrivers.

For each ONE fixed MOS RX delay bias (0.95V or 1.10V), alpha=0 and
alpha=0.30 use SAME training-derived integer frame alignment. A
single 358-symbol holdout [144,502) is scored, with missing and duplicate
actual MOS samples counted. All source CSVs are from *completed* SPICE
runs; neither PLL nor TX output is influenced by post-run known bits.
"""
from __future__ import annotations
import argparse,csv,json,math
from pathlib import Path

BIAS=(.95,1.1)
ALPHA=(0.,.3)
T0_S=1220e-9
UI_S=1/3.6e9
PRBS31_SEED=0x54C4EE17
TRAIN=(18,144)
TEST=(144,502)

def prbs31(n):
    state=PRBS31_SEED&((1<<31)-1)
    out=[]
    for _ in range(n):
        out.append(state&1)
        state=((state<<1)&((1<<31)-1))|(((state>>30)^(state>>27))&1)
    return out

def load(folder,bias,alpha):
    prefix=f"alpha_{alpha:.2f}_bias_{bias:.2f}".replace(".","p")
    matches=list(folder.rglob(prefix+"_physical_latch.csv"))
    meta=list(folder.rglob(prefix+".json"))
    if len(matches)!=1 or len(meta)!=1:
        raise RuntimeError(f"Need one physical MOS pair for {prefix}; got {matches},{meta}")
    with matches[0].open(newline="") as f:rows=list(csv.DictReader(f))
    for r in rows:
        t=float(r["physical_clock_sample_s"])
        r.update({
          "time":t,
          "estimated_UI":math.floor((t-T0_S)/UI_S),
          "QminusQB":float(r["Q_minus_QB_V"]),
          "regenerated":int(r["regenerated"]),
          "bit":int(r["mos_decoded_bit"])})
    return rows,json.loads(meta[0].read_text())

def score(rows,bits,lag,start,end):
    bins={}
    for r in rows:
        n=r["estimated_UI"]+lag
        if start<=n<end:bins.setdefault(n,[]).append(r)
    missing=duplicates=unresolved=wrong=0
    for n in range(start,end):
        r=bins.get(n,[])
        if not r:
            missing+=1;continue
        duplicates+=max(0,len(r)-1)
        # Consistent data-independent selection when two samples map to one UI.
        x=min(r,key=lambda a:a["time"])
        if not x["regenerated"] or abs(x["QminusQB"])<.150:
            unresolved+=1
        elif x["bit"]!=bits[n]:
            wrong+=1
    return {
      "expected_unique_UI":end-start,
      "missing_UI":missing,
      "duplicate_extra_clocks":duplicates,
      "unresolved_MOS_latches":unresolved,
      "wrong_regenerated_MOS_latches":wrong,
      "total_errors_including_missing":missing+unresolved+wrong
    }

def run(folder,out):
    out.mkdir(parents=True,exist_ok=True)
    bits=prbs31(512)
    results={}
    for bias in BIAS:
        a={alpha:load(folder,bias,alpha) for alpha in ALPHA}
        lags=[]
        for lag in range(-5,6):
            err=sum(score(a[alpha][0],bits,lag,*TRAIN)["total_errors_including_missing"]
                    for alpha in ALPHA)
            lags.append({"lag":lag,"training_errors_sum":err})
        common=min(lags,key=lambda z:(z["training_errors_sum"],abs(z["lag"])))["lag"]
        pairs={}
        for alpha in ALPHA:
            sample,meta=a[alpha]
            h=score(sample,bits,common,*TEST)
            pairs[f"alpha_{alpha:.2f}"]={
               "alpha":alpha,
               "training":score(sample,bits,common,*TRAIN),
               "heldout":h,
               "partial_mW":meta["partial_power_during_data"],
               "VCO_GHz":meta["PLL"]["vco_GHz"]}
            print(f"FAIR_PREDRIVER_FFE_PRBS31 physical_clock_bias={bias} "
                  f"alpha={alpha} common_lag={common} "
                  f"errors={h['total_errors_including_missing']}/{h['expected_unique_UI']} "
                  f"missing={h['missing_UI']} wrong={h['wrong_regenerated_MOS_latches']} "
                  f"dupes={h['duplicate_extra_clocks']}",flush=True)
        results[f"bias_{bias:.2f}"]={
            "same_Physical_RX_clock_bias_V":bias,
            "same_integer_lag_trained_only":common,
            "training_candidates":lags,
            "physical_MOS_comparisons":pairs,
        }
    final={
      "method":"common training-lag, same physical clock bias, untrained PRBS31 holdout",
      "data_labels_used_in_real_PLL_feedback":False,
      "TX_swing_or_error_count_alone_not_full_silicon_BER":True,
      "source_run":"same run 2026-11-12 physical CMOS MOS TX/RX PLL",
      "results":results}
    (out/"fair_full_MOS_FFE_PRBS31_heldout.json").write_text(
        json.dumps(final,indent=2)+"\n")
    return final

if __name__=="__main__":
    p=argparse.ArgumentParser()
    p.add_argument("--in-dir",type=Path,required=True)
    p.add_argument("--out",type=Path,default=Path("results/audit/p3_full_MOS_PRBS31_FFE"))
    a=p.parse_args()
    run(a.in_dir,a.out)
