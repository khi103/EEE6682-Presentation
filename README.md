# EEE6682 P3 — A 27-mW 3.6-Gb/s I/O Transceiver

Presentation and **independent behavioral simulation** for Wong *et al.*, *IEEE JSSC*, vol. 39, no. 4, 2004 (DOI: [10.1109/JSSC.2004.825259](https://doi.org/10.1109/JSSC.2004.825259)).

## Research question

How does a voltage-mode, two-tap transmitter pre-emphasis scheme mitigate intersymbol interference while preserving approximately 50-Ω source termination and a low-power serial link architecture?

## Reproducibility and scientific scope

This project **does not** claim a transistor-level recreation or an exact reproduction of the paper's 8-cm FR4 + 6.5-m RG58 measured channel. It simulates an **original, deterministic equivalent low-pass channel** with −12-dB attenuation at 1.8 GHz. Silicon driver impedance, RX comparator, PLL/CDR, jitter, package parasitics, and measured S-parameters are not modeled. Reference values from the paper are labeled separately from simulation outputs.

The lecture source, [`khi103/serdes-lecture-site/linksim_H-L/sim3_ffe.py`](https://github.com/khi103/serdes-lecture-site/blob/main/linksim_H-L/sim3_ffe.py), is a 56-Gb/s 3-/5-/9-tap zero-forcing FFE example. It should **not** be mislabeled as the paper's 3.6-Gb/s two-tap chip simulation. Our original implementation borrows only public engineering principles and the mathematical constraint `sum(abs(c)) == 1`.

## Reproduce figures

```bash
python -m pip install -r requirements.txt
pytest -q tests/test_p3.py
python simulation/p3_reproduce.py --out results
```

The above generates six PNG figures and `p3_results.json`. A GitHub Actions workflow performs the same tests and uploads a `p3-figures-and-results` artifact. The complete numerical output for a default 2048-bit PRBS7 sequence is deterministic.

## Main findings from the illustrative model

| Configuration | Worst-case RX eye height | Eye width |
| --- | ---: | ---: |
| 1-tap (no FFE) | 33.90 mV | 147.57 ps |
| 2-tap, alpha = 0.30 | 70.13 mV | 173.61 ps |
| 3-tap ZF (lecture extension) | 65.24 mV | 147.57 ps |
| 5-tap ZF (lecture extension) | 70.14 mV | 164.93 ps |
| 9-tap ZF (lecture extension) | 70.20 mV | 164.93 ps |

**Paper reference, not ours:** Fig. 25 reports a 37-mV × 189-ps eye after equalization at alpha = 0.3 on a physical 12-dB channel. The reported active link consumes 27.12 mW (Table IV). Matching the Nyquist loss alone does not uniquely determine the channel pulse response, so the illustrative numbers are not expected to match Fig. 25.

## Organization

```text
simulation/p3_reproduce.py   # Independently implemented channel and FFE model
tests/test_p3.py             # Mathematical and numerical sanity checks
results/                     # Simulation plots and machine-readable metrics
notes/paper_analysis_ko.md   # Section-by-section paper analysis and caveats
notes/speaker_notes_ko.md    # Slide-by-slide Korean 20-minute talk track
notes/questions_ko.md        # Question / answer preparation
presentation/                # PPTX (distributed separately for class submission)
```

The original licensed IEEE PDF and the instructor's proprietary private lecture source are intentionally **not** copied into this public repository. Figures clipped from the original paper, if any, are intended only for the course presentation with attribution, not for redistribution as public repository assets.

## Presentation constraints

20-min presentation + 10-min Q&A, no more than 15 English slides (based on instructor's original slide cap; latest notice changes the time). Slides due via LearnUs 23:59 on the day **before the assigned group's presentation**. Verify your final assigned date and include actual contributor roles on the final slide.
