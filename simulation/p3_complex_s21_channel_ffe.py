#!/usr/bin/env python3
"""4 complex-S21 channel / RC2 FFE portability and eye opening audit.

Inputs are lecturer's publicly hosted 100-ohm *differential* FR4-like
Touchstone 2-port, pinned to immutable Git commit. The 2004 Wong et al.
P3 used a different 50-ohm single-ended FR4+RG58 cable; THIS IS NOT
a replica of the paper's measured physical channel.

Physical method:
 - Parse the #Hz S RI R100 Touchstone and complex S21. Do not use just
   |S21| or omit phase, since group delay/ISI matter.
 - Build 3.6-Gb/s NRZ PRBS31, 32 samples/UI with 4096 bits.
 - Apply the same two-tap normalized voltage FFE
   (current - alpha * previous) / (1+alpha) for all channels.
 - Filter the source voltage via FFT with measured complex S21(f)
   assuming *matched 100ohm input/output*.
 - Compare one sample phase selected ONLY on early training symbols,
   then assess independent 3558 heldout transmitted UI symbols.
 - Compare six alphas, and an explicit synthetic RC2 -12dB@Nyquist
   transfer to establish non-portability of optimal pre-emphasis.
No original foundry MOS, no RX comparator, no PLL, no measured BER.
"""
from __future__ import annotations
import argparse,csv,io,json,math,urllib.request
from pathlib import Path
import numpy as np

COMMIT="128f225a336a2e99405cf8a5a0bfb136f9048766"
ROOT=f"https://raw.githubusercontent.com/khi103/serdes-lecture-site/{COMMIT}/linksim_H-L/"
CHANNELS={
  "lecture_FR4_basic":"fr4_diff_100ohm.s2p",
  "lecture_FR4_mid":"fr4_diff_100ohm_mid.s2p",
  "lecture_FR4_x36":"fr4_diff_100ohm_x36.s2p",
  "lecture_FR4_x42":"fr4_diff_100ohm_x42.s2p",
}
ALPHAS=(0.,.1,.2,.3,.4,.5)
SEED=0x54C4EE17
BITS=4096
SPS=32
RATE_GBPS=3.6
UI=1/(RATE_GBPS*1e9)
DT=UI/SPS
TRAIN=(128,512)
TEST=(512,4080)
RC_POLE_TAU=3.053260318e-12*50
MAX_SOURCE_ABS=1.

def generate_prbs31(n,seed=SEED):
    mask=(1<<31)-1;state=seed&mask
    if not state:raise ValueError
    out=np.empty(n,dtype=np.int8)
    for i in range(n):
        out[i]=state&1
        state=((state<<1)&mask)|(((state>>30)^(state>>27))&1)
    return out

def touchstone(name):
    url=ROOT+name
    with urllib.request.urlopen(url,timeout=40) as response:
        payload=response.read().decode("utf8")
    raw=payload.splitlines()
    options=[x.strip().lower() for x in raw if x.lstrip().startswith("#")]
    if len(options)!=1 or not options[0].replace(" ","").startswith("#hzsrir100"):
        raise RuntimeError(f"Unsupported 2port S definition {name} {options}")
    points=[]
    for line in raw:
        s=line.strip()
        if not s or s[0] in ("#","!"):continue
        v=[float(x) for x in s.split()]
        if len(v)!=9:raise RuntimeError(f"Not a nine-column S2P: {s[:60]}")
        points.append(v)
    a=np.asarray(points,dtype=float)
    if len(a)<500 or abs(a[0,0])>1e-6 or np.any(np.diff(a[:,0])<=0):
        raise RuntimeError(f"Unexpected Touchstone frequency grid: {name}")
    s21=a[:,3]+1j*a[:,4]
    s11=a[:,1]+1j*a[:,2]
    if np.max(np.abs(s21))>1.10:
        raise RuntimeError("Unreasonably large channel S21")
    return a[:,0],s21,s11,url

def interp_complex(freq,ref_freq,s):
    return np.interp(freq,ref_freq,np.real(s))+1j*np.interp(freq,ref_freq,np.imag(s))

def filtered_data(bits,alpha,transfer):
    b=2*bits.astype(float)-1
    prev=np.concatenate(([b[0]],b[:-1]))
    v=(b-alpha*prev)/(1+alpha)
    assert np.max(np.abs(v))<=1.+1e-9
    x=np.repeat(v,SPS)
    nfft=1<<((len(x)+4096-1).bit_length())
    fs=np.fft.rfftfreq(nfft,DT)
    H=transfer(fs)
    # For causal real LTI systems, enforce real Nyquist and DC bins.
    H[0]=H[0].real
    H[-1]=H[-1].real
    y=np.fft.irfft(np.fft.rfft(x,nfft)*H,nfft)
    return y, nfft, fs, H

def sample_eye(y,bits,phase,first,last):
    idx=np.arange(first,last)
    sample_idx=(idx+phase)*SPS
    values=np.interp(sample_idx,np.arange(len(y)),y)
    hi=values[bits[idx]==1]
    lo=values[bits[idx]==0]
    if not len(hi) or not len(lo):raise RuntimeError("Need both bit polarities")
    return {
      "worst_case_eye_a_u":float(hi.min()-lo.max()),
      "p01_to_p99_eye_a_u":float(np.quantile(hi,.01)-np.quantile(lo,.99)),
      "mean_level_separation_a_u":float(np.mean(hi)-np.mean(lo)),
      "center_level_a_u":float((hi.min()+lo.max())/2),
    }

def main(out):
    out.mkdir(parents=True,exist_ok=True)
    bits=generate_prbs31(BITS)
    summary={}
    table=[]
    models={}
    for label,file in CHANNELS.items():
        f,s21,s11,url=touchstone(file)
        models[label]={"source_url":url,"frequency_Hz":f,"s21":s21}
    models["RC2_minus12dB"]={"source_url":None,
                              "description":"ideal buffered 2-pole 50ohm RC channel"}
    for label,model in models.items():
        if label=="RC2_minus12dB":
            def H(freq):
                return (1+1j*2*np.pi*freq*RC_POLE_TAU)**(-2)
            s21_nyquist=H(np.asarray([1.8e9]))[0]
            ref_100_ohm=False
        else:
            f,s21=model["frequency_Hz"],model["s21"]
            def H(freq,f=f,s21=s21):
                return interp_complex(freq,f,s21)
            s21_nyquist=interp_complex(np.asarray([1.8e9]),f,s21)[0]
            ref_100_ohm=True
        waves={}
        for a in ALPHAS:
            y,nfft,freq,transfer=filtered_data(bits,a,H)
            waves[a]=y
        # The same pretrained phase is used for EVERY alpha in a channel.
        # Estimate approximate physical group delay from impulse response
        # to avoid pre-selecting a different result-dependent phase per FFE.
        h=np.fft.irfft(transfer,nfft)
        peak=int(np.argmax(np.abs(h[:min(len(h)//4,8192)])))
        peak_UI=peak/SPS
        phases=np.arange(max(0,peak_UI-3),peak_UI+5,.1)
        training=[(sample_eye(waves[0],bits,float(ph),*TRAIN)["worst_case_eye_a_u"],float(ph))
                  for ph in phases]
        trained_phase=max(training,key=lambda q:q[0])[1]
        # Width is based on TRAINING data only, not heldout phase optimization.
        phase_grid=np.arange(trained_phase-.5,trained_phase+.51,.02)
        record={
            "s21_dB_at_1p8GHz":float(20*np.log10(np.abs(s21_nyquist))),
            "touchstone_reference_ohm":100 if ref_100_ohm else None,
            "sampling_phase_from_Tx_UI":trained_phase,
            "matched_port_model":ref_100_ohm,
            "alpha":{},
        }
        for alpha in ALPHAS:
            train_eyes=[sample_eye(waves[alpha],bits,float(ph),*TRAIN)["worst_case_eye_a_u"]
                        for ph in phase_grid]
            eye=sample_eye(waves[alpha],bits,trained_phase,*TEST)
            record["alpha"][f"{alpha:.2f}"]={
                **eye,
                "training_eye_positive_width_UI_near_common_phase":float(
                    sum(x>0 for x in train_eyes)*.02),
            }
            row={"channel":label,"FFE_alpha":alpha,
                "S21_1p8GHz_dB":record["s21_dB_at_1p8GHz"],
                "common_training_sample_phase_UI":trained_phase,
                "holdout_worst_case_eye_a_u":eye["worst_case_eye_a_u"],
                "holdout_p01_to_p99_eye_a_u":eye["p01_to_p99_eye_a_u"],
                "training_positive_eye_width_UI":record["alpha"][f"{alpha:.2f}"]["training_eye_positive_width_UI_near_common_phase"]}
            table.append(row)
            print(f"COMPLEX_S21_FFE channel={label} a={alpha:.2f} "
                  f"S21dB={row['S21_1p8GHz_dB']:.3f} "
                  f"train_phase_UI={trained_phase:.2f} "
                  f"eye_au={eye['worst_case_eye_a_u']:.4f} "
                  f"p01eye_au={eye['p01_to_p99_eye_a_u']:.4f}",flush=True)
        summary[label]=record
    with (out/"complex_touchstone_FFE_holdout.csv").open("w",newline="") as f:
        w=csv.DictWriter(f,fieldnames=list(table[0]))
        w.writeheader();w.writerows(table)
    report={"experiment":"Four public lecture differential FR4 S21 models versus independent RC2",
            "source_commit":COMMIT,"rate_Gbps":RATE_GBPS,
            "PRBS":"4096-bit PRBS31 0x54C4EE17",
            "samples_per_UI":SPS,
            "train_UI_range":TRAIN,"heldout_UI_range":TEST,
            "alpha":ALPHAS,
            "method":"matched complex S21 FFT linear convolution, one training-only common phase per channel",
            "limitations":["Lecture FR4 is 100ohm differential, 2004 RG58 P3 is 50ohm single-ended",
                "Ideal matched sources and loads; no measured package or connector reflections",
                "Not transistor-level MOS TX/RX; channel isolation test",
                "No actual bit-sampling PLL jitter, BER or silicon power reproduced"],
            "channels":summary}
    (out/"complex_touchstone_FFE_holdout.json").write_text(json.dumps(report,indent=2)+"\n")
    return report

if __name__=="__main__":
    p=argparse.ArgumentParser()
    p.add_argument("--out",type=Path,default=Path("results/channels/p3_complex_s21"))
    args=p.parse_args()
    main(args.out)
