#!/usr/bin/env python3
"""No-proprietary-source quantitative channel/FFE sensitivity at 3.6 Gb/s.

This substitute runs independently of the PRIVATE lecturer Touchstone
repository (raw.githubusercontent.com returned HTTP 404 in public CI).
All channels are SYNTHETIC analytic, not measurements of Wong et al.'s
FR4/RG58 cable and not the lecturer's complex S21. No file contents
from the lecturer's private repo are copied or republished.

Evaluate four intentionally parameterized, causal channels:
  2-pole LPF with |H(1.8GHz)| = -6/-9/-12/-15 dB,
  with a common 0.9ns propagation delay and optional -0.1 echo
  at +0.55ns to test reflection sensitivity.
Apply the same normalized two-tap FFE (1-alpha*z^-1)/(1+alpha)
for alpha 0..0.5 and 4096 PRBS31 bits with 32 samples/UI.
For each CHANNEL choose the common sampling phase using ONLY
alpha=0 training symbols 128..511. Then evaluate heldout 512..4079:
  worst-case analog eye height in normalized transmitter units,
  1-99% trimmed eye gap, phase-grid eye openness (training only),
  deterministic Gaussian added receiver noise and sampling jitter
  to estimate *conditional synthetic* decision sensitivity.

The input symbols never alter an actual PLL or a MOS receiver.
No real transistor-level noise, real measured BER, or original 2004
silicon channel equivalence is claimed.
"""
from __future__ import annotations
import argparse,csv,json
from pathlib import Path
import numpy as np

RATE=3.6e9
UI=1/RATE
SPS=32
DT=UI/SPS
BITS=4096
SEED=0x54C4EE17
TRAIN=(128,512)
TEST=(512,4080)
ALPHAS=(0.,.1,.2,.3,.4,.5)
LOSS_DB=(6.,9.,12.,15.)
ECHO_COEFFS=(0.,-.10)
NORM_DELAY_NS=.9
JITTER_RMS_PS=10.
NOISE_RMS_NORMALIZED=.04
NOISE_TRIALS=20
RNG=424253

def prbs31(n):
    mask=(1<<31)-1;x=SEED&mask
    bits=np.empty(n,dtype=np.int8)
    for k in range(n):
        bits[k]=x&1
        x=((x<<1)&mask)|(((x>>30)^(x>>27))&1)
    return bits

def tau_from_nyquist_loss(db):
    if db<=0:raise ValueError
    magnitude=10**(-db/20)
    # H=(1+jw*tau)^-2 so |H|=1/(1+(w*tau)^2)
    return (1/magnitude-1)**.5/(2*np.pi*RATE/2)

def transfer(freq,db,echo):
    tau=tau_from_nyquist_loss(db)
    p=1j*2*np.pi*freq
    base=np.exp(-p*NORM_DELAY_NS*1e-9)/(1+p*tau)**2
    # Echo is a second delayed path; ensure no DC gain change,
    # matching the same normalized NRZ swing at zero frequency.
    return base*(1+echo*np.exp(-p*.55e-9))/(1+echo)

def simulate(bits,alpha,db,echo):
    x=2*bits.astype(float)-1
    prev=np.r_[x[0],x[:-1]]
    tx=(x-alpha*prev)/(1+alpha)
    samples=np.repeat(tx,SPS)
    nfft=1<<int(np.ceil(np.log2(len(samples)+8192)))
    f=np.fft.rfftfreq(nfft,DT)
    h=transfer(f,db,echo)
    h[0]=h[0].real
    h[-1]=h[-1].real
    received=np.fft.irfft(np.fft.rfft(samples,nfft)*h,nfft)
    return received

def sample(wave,bits,phase,interval):
    idx=np.arange(*interval)
    positions=(idx+phase)*SPS
    v=np.interp(positions,np.arange(len(wave)),wave)
    ones=v[bits[idx]==1]
    zeros=v[bits[idx]==0]
    if not len(ones) or not len(zeros):raise RuntimeError("Unbalanced data")
    return {"eye_worst":float(np.min(ones)-np.max(zeros)),
            "eye_p01p99":float(np.quantile(ones,.01)-np.quantile(zeros,.99)),
            "mean_HiMinusLow":float(np.mean(ones)-np.mean(zeros)),
            "threshold":float((np.quantile(ones,.01)+np.quantile(zeros,.99))/2)}

def run(out):
    out.mkdir(parents=True,exist_ok=True)
    bits=prbs31(BITS)
    rows=[]
    for db in LOSS_DB:
      for echo in ECHO_COEFFS:
        label=f"LP2_{db:g}dB_echo_{echo:+.2f}".replace(".","p")
        waves={a:simulate(bits,a,db,echo) for a in ALPHAS}
        # Sample delay ≈3.24 UI; choose positive phase around it
        # using training and FFE-OFF only; common for ALL alpha.
        phase_candidates=np.arange(2.3,6.,.025)
        phase=max(phase_candidates,
            key=lambda ph:sample(waves[0.],bits,ph,TRAIN)["eye_worst"])
        common_threshold=sample(waves[0.],bits,phase,TRAIN)["threshold"]
        idx=np.arange(*TEST)
        ideal_times=(idx+phase)*UI
        normal=np.random.default_rng(RNG)
        jitters=normal.normal(0.,JITTER_RMS_PS*1e-12,(NOISE_TRIALS,len(idx)))
        noise=normal.normal(0.,NOISE_RMS_NORMALIZED,(NOISE_TRIALS,len(idx)))
        for alpha in ALPHAS:
            wave=waves[alpha]
            eye=sample(wave,bits,phase,TEST)
            times=ideal_times[None,:]+jitters
            v=np.interp(times.ravel()/DT,np.arange(len(wave)),wave).reshape(times.shape)
            decision=(v+noise>common_threshold)
            errors=int(np.count_nonzero(decision!=(bits[idx]==1)[None,:]))
            # Differing FFE levels and common slicer will cause explicit
            # threshold penalties; identical common threshold is intentional.
            wgrid=np.arange(phase-.5,phase+.5,.025)
            positives=sum(sample(wave,bits,p,TRAIN)["eye_worst"]>0 for p in wgrid)
            row={
                "channel":label,"nyquist_loss_dB":db,"reflection_echo_coeff":echo,
                "ffe_alpha":alpha,
                "trained_common_phase_UI":float(phase),
                "source_level_normalized":True,
                "holdout_eye_worst_normalized":eye["eye_worst"],
                "holdout_eye_p01p99_normalized":eye["eye_p01p99"],
                "train_open_width_UI":positives*.025,
                "noise_rms_normalized":NOISE_RMS_NORMALIZED,
                "jitter_rms_ps":JITTER_RMS_PS,
                "reused_holdout_symbols":len(idx),
                "noise_trials":NOISE_TRIALS,
                "synthetic_decision_errors":errors,
                "synthetic_trial_fraction":errors/(len(idx)*NOISE_TRIALS),
            }
            rows.append(row)
            print(f"INDEPENDENT_CHANNEL_FFE {label} alpha={alpha:.2f} "
              f"eye={eye['eye_worst']:.5f} "
              f"openWidth_UI={positives*.025:.3f} "
              f"synthetic_errors={errors}/{len(idx)*NOISE_TRIALS}",flush=True)
    with (out/"synthetic_channel_ffe.csv").open("w",newline="") as f:
        w=csv.DictWriter(f,fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)
    result={
        "study":"Independent synthetic RC2 loss and delayed echo sensitivity",
        "data_pattern":"4096-bit PRBS31",
        "data_seed":hex(SEED),
        "line_rate_Gbps":RATE/1e9,
        "training_range_symbols":TRAIN,
        "holdout_range_symbols":TEST,
        "samples_per_UI":SPS,
        "synthetic_channel_characterization_only":True,
        "lecturer_private_Touchstone_copied":False,
        "2004_cable_reproduced":False,
        "real_180nm_MOS_receiver":False,
        "full_rate_BER_measured":False,
        "different_channel_impedances_not_equated":True,
        "single_common_sampling_phase_per_channel_selected_with_FFE_OFF_training":True,
        "same_noise_and_jitter_draws_for_each_alpha":True,
        "rows":rows,
    }
    (out/"synthetic_channel_ffe.json").write_text(json.dumps(result,indent=2)+"\n")
    return result

if __name__=="__main__":
    p=argparse.ArgumentParser()
    p.add_argument("--out",type=Path,default=Path("results/channels/p3_synthetic_ffe"))
    run(p.parse_args().out)
