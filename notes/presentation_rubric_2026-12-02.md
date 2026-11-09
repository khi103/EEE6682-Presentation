# EEE6682 P3 — UPDATED rubric effective Nov. 9, 2026

**Assignment:** Group 11 (김형인 · 정여진), Paper P3, Dec. 2, 2026.
**Submit slides:** Dec. 1, 2026 by 23:59 on LearnUs. 15 slides maximum; 20-minute talk + 10-minute Q&A.
**Important:** The latest rubric differs from the previous announcement.

## 100-point rubric and evidence

| Criterion | Points | Presentation evidence |
| --- | ---: | --- |
| Background and existing limitations | 30 | Slides 2–4: prior 18–40 mW/Gb/s, 3.6-Gb/s NRZ, UI 277.8 ps, 12 dB @ 1.8 GHz, 0.18-µm CMOS, power constraints, Deck E/I speed limits |
| Understanding the key idea | 25 | Slides 7–9: FIR equation, 5.38-dB Nyquist/DC relative pre-emphasis, Σ|c|=1, 50-Ω segmented-driver conductance argument, Fig. 10 Zout |
| Reproduction | 25 | Slides 10–14: executed adapted FFE methodology, 1/2/3/5/9-tap voltage swing and eye charts, paper comparison 37mV ×189ps versus surrogate 70.13mV ×173.61ps, sensitivity/measurement critique |
| Presentation and Q&A | 10 | Fifteen slide notes total exactly 20:00; technical Q&A preparation and rehearsal required |
| Peer evaluation | 10 | Clear problem, core-idea, and reproduction explanations designed for the three peer-evaluation questions; actual scoring belongs to attendees |

## Mandatory five-section time allocation

- **Problem definition**: Slides 1–2 = 3:00. Data rate, insertion loss at Nyquist, NRZ, technology, power.
- **Full architecture**: Slides 3–6 = 6:00. TX→channel→4-phase comparator RX→CDR. Deck D S3, E S2–S7, F S4/S9, H S17–S19, I S9, M S3–S6. P3 lacks separate CTLE/VGA/multibit ADC/DSP RX FFE, DFE, and MLSD.
- **Core novelty**: Slides 7–9 = 5:00. Voltage-mode 2-tap FFE plus approximately constant 50-Ω source impedance through 8:4:2:1 segmented driver.
- **Reproduction**: Slides 10–13 = 4:00. Adapted link simulation script and measured-vs-modeled comparison.
- **Critique/question**: Slides 14–15 = 2:00. Equal Nyquist loss does not guarantee equal impulse response; unmeasured BER; Deck F validation.

## P3-specific start-script compliance and limitation

Course source (private fork): [linksim_H-L/sim3_ffe.py](https://github.com/khi103/serdes-lecture-site/blob/main/linksim_H-L/sim3_ffe.py).
Course baseline: 56 Gb/s, 3/5/9-tap zero-forcing TX FFE, Σ|c|=1, Verilator + S-parameter.
Adapted file: [simulation/sim3_ffe_P3_adapted.py](../simulation/sim3_ffe_P3_adapted.py).
Adapted conditions: 3.6 Gb/s NRZ, 250 mVpp peak output budget, 12 dB at 1.8 GHz, 2-tap α=0.3 and 3/5/9-tap extensions, Σ|c|=1.
**Backend caveat:** The adapted experiment uses an independently written 2-pole RC Python channel via p3_reproduce.py; it does **not** run the lecturer's native Verilator or reproduce the physical 6.5-m RG58 and 8-cm PCB S-parameter channel, 50-Ω MOS output conductance, BER, noise, PLL, or measured total power.

Run:
```bash
python -m pip install -r requirements.txt
python -m pytest -q tests/test_p3.py
python simulation/sim3_ffe_P3_adapted.py --out results
```
Local verification: four tests passed, plus script asserts 3.6 Gb/s, 12 dB at 1.8 GHz, and L1 normalization.
Eye heights for 1/2/3/5/9 taps: 33.90/70.13/65.24/70.14/70.20 mV.
DC long-run swing (mVpp): 250.00/134.62/65.11/70.09/70.75.

The paper's **measured** 2-tap α=0.3 eye = 37 mV × 189 ps (Fig.25), compared to model **70.13 mV × 173.61 ps**. Do not claim exact agreement. Reported 27.12 mW total active link (Table IV) is 7.53 pJ/bit at 3.6 Gb/s.

## Group-specific operational obligations

- Group 11 must prepare **two questions for Group 10's P17 presentation** on Dec. 2; assign at least one to each group member. Incomplete question duty deducts **2 points per occasion**. Group 1 will question Group 11.
- Every attendee submits peer evaluation (three 1–5 scoring items).
- Actual contribution split and student IDs must be verified and filled into slide 15; placeholders are not factual assignments.
- Rehearse 20 minutes and Q&A; upload final PPTX on time. Only actual in-class execution can fulfill these tasks.
- The Dec. 2 discussion includes a course-deck ↔ paper mapping; slide 3 is prepared for that purpose.

**Source:** latest five-page EEE6682 handout, pages 1–3 and 5, and Wong et al., IEEE JSSC, 39(4), 602–612, 2004.
