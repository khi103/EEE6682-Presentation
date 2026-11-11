# P3 simulation provenance, mathematical circuit, and validation (Nov. 11, 2026)

**Scope:** This repository contains an **independent Python behavioral simulation**, not a transistor-level recreation of Wong et al., *IEEE JSSC*, vol. 39, no. 4, pp. 602-612 (2004).

## Instructor's original script

- Actual source: [serdes-lecture-site/linksim_H-L/sim3_ffe.py](https://github.com/khi103/serdes-lecture-site/blob/main/linksim_H-L/sim3_ffe.py) (private lecture fork).
- Source task: Deck H.3, 56 Gb/s TX FFE, 3/5/9-tap zero-forcing, sample-by-sample response (SBR), eye diagrams, and **sum(abs(c))=1**.
- Original implementation uses `linksim.py`, `link.sv`, Verilator and an FR4-like channel represented by Touchstone-derived impulse taps.
- We reused **the ZF / tap-sweep / L1 mathematical approach**, but **did not execute a modified original Verilator/SystemVerilog stack**.

## Adaptation to P3 conditions

- Executable driver: `simulation/sim3_ffe_P3_adapted.py`; actual solver: `simulation/p3_reproduce.py`.
- 3.6 Gb/s NRZ, UI 277.7778 ps, Nyquist 1.8 GHz, PRBS7 (2,048 bits), 32 samples/UI (8.6806 ps/sample).
- Output budget 250 mVpp, common mode 250 mV, Gaussian TX 10-90% rise time 110 ps (model assumption), no RX noise or jitter.
- Two-tap original FIR is **y[n]=x[n]-alpha*x[n-1]**. At alpha=0.30 the constrained lecture-style taps are `c0=1/(1+alpha)=0.76923077` and `c1=-alpha/(1+alpha)=-0.23076923`. They satisfy **sum(abs(c))=1**.
- TX long-run same-bit swing under this ideal constraint is 250*(c0+c1)=**134.615 mVpp**. This is *not* the RX eye height.
- 3/5/9-tap alternatives are additional *lecture extensions* computed via sample-cursor zero-forcing and L1 normalization; the fabricated P3 transceiver used a two-tap pre-emphasis scheme.

## What circuit elements were modeled?

The channel is **not an extracted cable or a MOS schematic**. In Python, `scipy.signal.lfilter` applies **two identical first-order RC low-pass transfer functions**, with ideal decoupling:

`H_ch(f)=[1+j(f/fc)]^(-2)`

The cutoff `fc=1.042524557 GHz` was solved so that **|H_ch(1.8 GHz)| = 10^(-12/20)=0.2511886 (-12 dB)**. The time constant is `tau=152.663 ps`. With `dt=8.6806 ps`, the discrete IIR update is `p=exp(-dt/tau)`; `y[k]=(1-p)*x[k]+p*y[k-1]` twice.

An **optional, unexecuted** ngspice illustration in [circuits/two_pole_rc_surrogate.cir](../circuits/two_pole_rc_surrogate.cir) shows the same two RC poles using R1=R2=50 ohms, C1=C2=3.053260 pF, and a unity-gain **ideal VCVS buffer** to isolate the stages. Those resistor/capacitor values are an arbitrary equivalent scaling of the model's time constant, **not the original P3 chip dimensions or measured channel**.

There is NO PDK model, BSIM transistor, segmented output driver, real 50-ohm MOS termination, RX comparator, PLL/CDR, power simulation, or BER counting in this execution.

## Verification process and numbers

From the repository root:

```bash
python -m pip install -r requirements.txt
pytest -q tests/test_p3.py
python simulation/sim3_ffe_P3_adapted.py --out results
python simulation/export_veusz.py
```

Local rerun: **four pytest tests passed**. Checks include coefficient L1 normalization, Nyquist attenuation, parameter conditions and eye improvement. The lecture-style tap comparison gives:

| TX taps | Model eye height (mV) | Long-run DC swing (mVpp) |
| ---: | ---: | ---: |
| 1 (none) | 33.90 | 250.00 |
| 2, alpha=0.30 | 70.13 | 134.62 |
| 3, ZF | 65.24 | 65.11 |
| 5, ZF | 70.14 | 70.09 |
| 9, ZF | 70.20 | 70.75 |

The published **silicon measurement** for the 2-tap design in Fig. 25 is **37 mV x 189 ps**. The **Python RC model** yields **70.13 mV x 173.61 ps**. A match at **one** channel loss point (-12 dB at 1.8 GHz) cannot constrain full S21(f) magnitude/phase, package parasitics, noise/jitter, or the receiver. Thus exact numerical agreement is **not** claimed.

The published approximately 50-ohm output driver impedance (Fig. 10) and 27.12-mW total active link power (Table IV) are **paper measurements**, not Python outputs.

## Raw figures and editing

- `results/p3_results.json`: raw parameters and calculated metrics
- `results/P3_modified_sim3_ffe_summary.json`: per-tap summary
- `veusz/*.csv` and `veusz/P3_Editable_Plots.vsz`: plotted data in independently editable form
- `simulation/export_veusz.py`: regenerate the Veusz CSV and project (after running simulation)

Reproduction tests and generated data **do not prove** chip transistor-level functionality. Running the original silicon comparison would require a licensed CMOS PDK, transistor schematic and foundry device models, controlled 50-ohm impedance feedback, actual FR4/RG58 S-parameters, RX/clock loops, and measured/calculated jitter/noise/power.
