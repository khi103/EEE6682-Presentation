#!/usr/bin/env python3
"""Strict one-common-phase PRBS31 MOS-FFE eye and heldout bit audit.

Electrical input: actual physical ngspice CMOS TX predriver/MOS TX/RX
latch/XSPICE reference PLL/ MOS clock phase RX waveform. For each fixed
physical MOS receiver delay bias, all six FFE alphas use:
 - identical 512-symbol PRBS31,
 - one common integer frame lag chosen ONLY on training bits [18,144),
 - one common analog RX eye sampling phase selected ONLY from training
   symbols, maximizing worst-case training eye across six alphas,
 - heldout [144,502) bit-error + erasure scoring and worst-case RX
   electrical eye-height at that COMMON phase.
The analog eye uses TX labels only after simulation, never for the
actual XSPICE PLL or MOS receiver clock phase actuator. The channel
is a surrogate RC2, not the authors' FR4+RG58 cable. No BER claim.
"""
from __future__ import annotations
import argparse,bisect,csv,json,math
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"simulation"))
import p3_long_predriver_prbs31 as LONG

ALPHAS=(0.,.1,.2,.3,.4,.5)
BIASES=(.95,1.10)
TRAIN=(18,144)
HOLD=(144,502)
UI_S=1/3.6e9
T0_S=1220e-9
PHASES=[x/20 for x in range(0,61)]
BITS=LONG.prbs31(512)

def tag(alpha,bias):
    return f"alpha_{alpha:.2f}_bias_{bias:.2f}".replace(".","p")
def waveform(folder,alpha,bias):
    stem=tag(alpha,bias)
    path=list(folder.rglob(stem+"_actual_analog_RX.csv"))
    if len(path)!=1:raise RuntimeError(f"Expected one analog waveform for {stem}: {path}")
    with path[0].open(newline="") as f:r=list(csv.DictReader(f))
    time=[float(x["time_s"]) for x in r]
    values=[float(x["rx_V"]) for x in r]
    if not 1500<=len(time)<=15000 or time!=sorted(time):
        raise RuntimeError(f"Corrupt or nonmonotonic physical MOS waveform for {stem}")
    return time,values

def interp(times,values,t):
    k=bisect.bisect_left(times,t)
    if k==0:return values[0]
    if k==len(times):return values[-1]
    t0,t1=times[k-1],times[k]
    if t1<=t0:return values[k]
    return values[k-1]+(values[k]-values[k-1])*(t-t0)/(t1-t0)

def analog_eye(t,v,phase,start,stop):
    hi=[];lo=[]
    for i in range(start,stop):
        s=interp(t,v,T0_S+(i+phase)*UI_S)
        (hi if BITS[i] else lo).append(s)
    if not hi or not lo:raise ValueError("PRBS holdout lacks 0/1")
    h=(min(hi)-max(lo))*1e3
    midpoint=(min(hi)+max(lo))/2
    mean_sep=(sum(hi)/len(hi)-sum(lo)/len(lo))*1000
    return {
      "worst_case_vertical_eye_mV":h,
      "mean_level_separation_mV":mean_sep,
      "eye_center_threshold_V":midpoint,
      "worst_high_V":min(hi),"worst_low_V":max(lo),
    }

def get_samples(folder,alpha,bias):
    stem=tag(alpha,bias)
    p=list(folder.rglob(stem+"_physical_latch.csv"))
    j=list(folder.rglob(stem+".json"))
    if len(p)!=1 or len(j)!=1:raise RuntimeError(f"Missing original physical sample or metadata {stem}")
    with p[0].open(newline="") as f:rr=list(csv.DictReader(f))
    data=[]
    for r in rr:
        t=float(r["physical_clock_sample_s"])
        data.append({
          "index":math.floor((t-T0_S)/UI_S),
          "time_s":t,
          "regenerated":int(r["regenerated"]),
          "q_diff_V":float(r["Q_minus_QB_V"]),
          "decoded":int(r["mos_decoded_bit"])})
    return data,json.loads(j[0].read_text())

def bit_score(samples,lag,begin,end):
    groups={}
    for r in samples:
        n=r["index"]+lag
        if begin<=n<end:groups.setdefault(n,[]).append(r)
    count={"expected_bits":end-begin,"missing_UI":0,"duplicate_clocks_extra":0,
           "unresolved_MOS_latches":0,"wrong_regenerated_MOS_bits":0}
    margins=[]
    for i in range(begin,end):
        s=groups.get(i,[])
        if not s:
            count["missing_UI"]+=1
            continue
        count["duplicate_clocks_extra"]+=max(0,len(s)-1)
        x=min(s,key=lambda z:z["time_s"])
        margins.append((2*BITS[i]-1)*x["q_diff_V"]*1000)
        if not x["regenerated"] or abs(x["q_diff_V"])<.15:
            count["unresolved_MOS_latches"]+=1
        elif x["decoded"]!=BITS[i]:
            count["wrong_regenerated_MOS_bits"]+=1
    count["invalid_or_wrong_UI"]=sum(count[k] for k in
        ("missing_UI","unresolved_MOS_latches","wrong_regenerated_MOS_bits"))
    count["p05_signed_latch_margin_mV"]=sorted(margins)[int(len(margins)*.05)] if margins else None
    return count

def run(folder,out):
    out.mkdir(parents=True,exist_ok=True)
    rows=[]
    full={}
    for bias in BIASES:
        evidence={a:{"wave":waveform(folder,a,bias),
                    "samples":get_samples(folder,a,bias)} for a in ALPHAS}
        lag=min(range(-5,6),key=lambda n:(
           sum(bit_score(evidence[a]["samples"][0],n,*TRAIN)["invalid_or_wrong_UI"] for a in ALPHAS),
           abs(n)))
        candidates=[]
        for ph in PHASES:
            heights=[analog_eye(*evidence[a]["wave"],ph,*TRAIN)["worst_case_vertical_eye_mV"]
                      for a in ALPHAS]
            candidates.append((min(heights),-abs(ph-1.2),ph))
        phase=max(candidates)[-1]
        per={}
        for alpha in ALPHAS:
            t,v=evidence[alpha]["wave"]
            samples,meta=evidence[alpha]["samples"]
            h=bit_score(samples,lag,*HOLD)
            eye=analog_eye(t,v,phase,*HOLD)
            train_heights=[analog_eye(t,v,p,*TRAIN)["worst_case_vertical_eye_mV"] for p in PHASES]
            width_pos=sum(x>0 for x in train_heights)*(PHASES[1]-PHASES[0])
            power=meta["partial_power_during_data"]
            data={
              "alpha":alpha,"fixed_MOS_clock_control_V":bias,
              "shared_integer_lag_fitted_on_training":lag,
              "shared_analog_eye_phase_fitted_on_training_UI":phase,
              "heldout_latch":h,
              "heldout_analog_RX_eye_at_shared_phase":eye,
              "training_positive_eye_phase_width_UI_approx":width_pos,
              "data_window_partial_power_mW":power,
              "reference_PLL_GHz":meta["PLL"]["vco_GHz"],
              "physical_predriver":True,
              "channel":"surrogate -12dB at Nyquist RC2, not original RG58",
              "measured_true_BER":False,
              "original_2004_P3_circuit":False,
            }
            per[f"{alpha:.2f}"]=data
            row={
                "RX_gate_bias_V":bias,"alpha":alpha,
                "training_integer_lag":lag,"common_eye_phase_UI":phase,
                "heldout_errors":h["invalid_or_wrong_UI"],
                "missing":h["missing_UI"],
                "wrong_regenerated":h["wrong_regenerated_MOS_bits"],
                "unresolved":h["unresolved_MOS_latches"],
                "duplicate_extra":h["duplicate_clocks_extra"],
                "p05_signed_latch_margin_mV":h["p05_signed_latch_margin_mV"],
                "heldout_analog_eye_mV":eye["worst_case_vertical_eye_mV"],
                "training_eye_open_width_UI_approx":width_pos,
                "partial_1p8V_mW":power["physical_MOS_PLL_RX_clock_buffer_TX_CMOS_driver_1p8V_mW"],
                "partial_0p5V_mW":power["MOS_TX_output_stage_0p5V_source_mW"],
                "partial_sum_mW":power["summed_partial_power_mW"],
            }
            rows.append(row)
            print(f"FULLMOS_FFE_HELDOUT RX_bias={bias:.2f} alpha={alpha:.2f} "
                  f"errors={row['heldout_errors']}/358 "
                  f"missing={row['missing']} wrong={row['wrong_regenerated']} "
                  f"eye_mV={row['heldout_analog_eye_mV']:.3f} "
                  f"power_partial_mW={row['partial_sum_mW']:.4f}",flush=True)
        full[str(bias)]={"shared_lag":lag,"shared_training_analog_phase":phase,"modes":per}
    dest=out/"fullmos_ffe_holdout_comparison.csv"
    with dest.open("w",newline="") as f:
        writer=csv.DictWriter(f,fieldnames=list(rows[0]));writer.writeheader();writer.writerows(rows)
    report={
      "experiment":"full-transistor reconstructed MOS TX with predriver FFE coefficient sweep",
      "original_link_measured":False,"statistical_BER":False,
      "training":[*TRAIN],"heldout":[*HOLD],
      "reused_pattern":"PRBS31 seed 0x54C4EE17",
      "sweep":full,
      "caveats":["Mean level separation and worst-case eye on actual analog RX are postrun labels-based metrics",
      "Training-only phase is global across alphas, rather than tuned per FFE setting",
      "Positive-eye width uses training-only waveform, not measured silicon BER or a true oscilloscope Eye",
      "Two-pole ideal buffered RC channel differs from paper and lecture FR4 touchstone",
      "Partial supply power does not include original full-chip digital power."] }
    (out/"fullmos_ffe_heldout_report.json").write_text(json.dumps(report,indent=2)+"\n")
    return report

if __name__=="__main__":
    p=argparse.ArgumentParser()
    p.add_argument("--in-dir",type=Path,required=True)
    p.add_argument("--out",type=Path,default=Path("results/audit/p3_fullmos_ffe_alpha"))
    a=p.parse_args()
    run(a.in_dir,a.out)
