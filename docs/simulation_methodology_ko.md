# P3 시뮬레이션 방법 - 한국어 요약

**실제 실행한 것은 Python 행동 모델입니다.** 원 논문 0.18-µm MOSFET 회로를 PDK/SPICE로 검증한 것이 아닙니다.

1. 강의 원본: khi103/serdes-lecture-site/linksim_H-L/sim3_ffe.py. 원본은 56 Gb/s, 3/5/9-Tap ZF와 Σ|c|=1 예제이며 Verilator + Touchstone 모델입니다.
2. P3 변환: 3.6 Gb/s NRZ, 250 mVpp, 12 dB @ 1.8 GHz, 2-Tap α=0.30, 3/5/9-Tap 추가 비교. 원본 전체 시뮬레이터를 수정 실행한 것이 아니라 수학적 FFE 방법을 독립 Python 코드로 이식했습니다.
3. 실제 모델 소자: 동일한 두 개의 RC 저역통과 극점을 scipy.signal.lfilter로 모델링했습니다. fc=1.042524557 GHz, τ=152.663 ps입니다. 50 Ω + 3.053260 pF의 버퍼 분리 RC 넷리스트는 설명용 등가 회로이며 논문 MOS driver의 소자값이 아닙니다.
4. 신호 조건: PRBS7 2048bit, UI=277.78 ps, OSR=32, Gaussian 110-ps TX edge, RX 잡음과 지터는 0으로 가정합니다. Σ|c|=1에서 c0=0.76923, c1=-0.23077이고 TX DC swing은 134.615 mVpp입니다.
5. 실행 검증: Python 단위 테스트 4개 통과. 1/2/3/5/9-Tap eye height는 각각 33.90/70.13/65.24/70.14/70.20 mV입니다. 논문 실측 Fig.25의 37 mV x 189 ps와 Python 계산의 70.13 mV x 173.61 ps는 다른 모델이므로 같다고 주장하지 않습니다.
6. GitHub 경로: simulation/p3_reproduce.py, simulation/sim3_ffe_P3_adapted.py, simulation/export_veusz.py, results/p3_results.json, veusz/*.csv, veusz/P3_Editable_Plots.vsz, circuits/two_pole_rc_surrogate.cir.
7. **미구현**: 8:4:2:1 MOS segmented driver, 50-Ω Zout PVT, Comparator, PLL/CDR, BER 및 실제 power. ngspice/Verilator/Veusz의 이 환경 내 실행 확인도 없습니다.

아래에는 영어로 상세한 계산 절차, 구분표, 실행 명령과 검증 수치가 정리되어 있습니다.

---
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
