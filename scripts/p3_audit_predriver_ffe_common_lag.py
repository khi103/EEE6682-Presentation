#!/usr/bin/env python3
"""Audit exact same training-selected integer bit alignment for MOS FFE.

Reads physically clocked MOS-Latch output CSVs from the already executed
TX-CMOS-predriver + MOS RX phase-retrim run 43179781968. For each ONE
fixed RX delay bias, alpha=0 and 0.30 are given a COMMON framing lag,
chosen on training bits 18..89 only. The 156-symbol heldout region
90..245 then counts missing, repeated, unresolved and wrong physical
MOS Latch samples. It does NOT optimize timing or framing separately
for the FFE case and makes no BER claim.
"""
from __future__ import annotations
import argparse,csv,json,math,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"simulation"))
import p3_transistor_driver as TX
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"scripts"))
import audit_physical_mos_ffe_coverage as AUDIT

BIASES=(.95,1.1,1.25)
ALPHAS=(0.,.3)
N_BITS=256
DATA_START_NS=1220.
UI_S=1/3.6e9
TRAIN=(18,90)
HOLDOUT=(90,246)

def get(folder,bias,alpha):
    prefix=f"alpha_{alpha:.2f}_vctrl_{bias:.2f}".replace(".","p")
    loc=list(folder.rglob(prefix+"_MOS_latch_decisions.csv"))
    jpath=list(folder.rglob(prefix+".json"))
    if len(loc)!=1 or len(jpath)!=1:
        raise RuntimeError(f"Expected one evidence pair for {prefix}: {len(loc)} CSV, {len(jpath)} JSON")
    with loc[0].open(newline="") as f:
        rows=list(csv.DictReader(f))
    for r in rows:
        t=float(r["physical_clock_sample_s"])
        r["physical_clock_sample_s"]=t
        r["Q_minus_QB_V"]=float(r["Q_minus_QB_V"])
        r["regenerated"]=int(r["regenerated"])
        r["mos_decoded_bit"]=int(r["mos_decoded_bit"])
        r["raw_UI_floor"]=math.floor((t-DATA_START_NS*1e-9)/UI_S)
        r["raw_UI_round"]=round((t-DATA_START_NS*1e-9)/UI_S)
    return rows,json.loads(jpath[0].read_text()),prefix

def run(folder,out):
    out.mkdir(parents=True,exist_ok=True)
    bits=TX.prbs7(N_BITS)
    summary={}
    for bias in BIASES:
        d={alpha:get(folder,bias,alpha) for alpha in ALPHAS}
        candidates=[]
        for lag in range(-5,6):
            s=sum(AUDIT.evaluate(d[alpha][0],bits,lag,*TRAIN,"floor")["invalid_or_wrong_UI"]
                  for alpha in ALPHAS)
            candidates.append((s,abs(lag),lag))
        best=min(candidates)[-1]
        cases={}
        for alpha in ALPHAS:
            rr,report,label=d[alpha]
            cases[label]={
              "alpha":alpha,"shared_postrun_training_lag":best,
              "train":AUDIT.evaluate(rr,bits,best,*TRAIN,"floor"),
              "heldout":AUDIT.evaluate(rr,bits,best,*HOLDOUT,"floor"),
              "source_power_mW":report.get("partial_source_power"),
              "source_run":"https://github.com/khi103/EEE6682-Presentation/actions/runs/43179781968",
            }
            h=cases[label]["heldout"]
            print(f"TX_FFE_COMMON_FRAME bias_V={bias} alpha={alpha} lag={best} "
                  f"score={h['invalid_or_wrong_UI']}/{h['expected_unique_bits']} "
                  f"missing={h['missing_UI']} extra={h['duplicate_extra_sample_events']} "
                  f"wrong={h['wrong_regenerated_UI']}",flush=True)
        summary[f"bias_{bias}"]={"same_rx_delay_bias_V":bias,
                                 "common_training_lag":best,"cases":cases}
    (out/"common_training_lag_heldout_MOS_FFE.json").write_text(
        json.dumps(summary,indent=2)+"\n")
    return summary

if __name__=="__main__":
    a=argparse.ArgumentParser()
    a.add_argument("--in-dir",type=Path,required=True)
    a.add_argument("--out",type=Path,default=Path("results/audit/p3_actual_predriver_ffe"))
    args=a.parse_args()
    run(args.in_dir,args.out)
