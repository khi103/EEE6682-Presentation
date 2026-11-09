# P3 presentation: requirements mapping (Dec. 2, 2026)

## Authoritative instructions
The attached EEE6682 presentation plan (p. 2) originally assigns 30 minutes to five sections; the professor's later announcement reduces the talk to 20 min, with 10 min for Q&A. Slides: at most 15, English on screen, Korean/English oral explanation, upload through LearnUs before 23:59 on Dec. 1. Slide 15 must state *actual* presenter roles.

## Mandatory sections / timing (20:00)
| Required component | New timing | Slides |
| --- | ---: | ---: |
| Problem definition: data rate, loss at Nyquist, NRZ, process, power, Deck E speed limits | 3 min | 1–2 |
| Full architecture: TX FFE/slew, channel, RX sampler/comparator, PLL/CDR | 6 min | 3–6 |
| Deep core idea: 2-tap FFE, 50-ohm matching, swing/power trade-offs | 5 min | 7–9 |
| Actual runnable reproduction: tap count and swing loss, plus eye, with method caveats | 4 min | 10–13 |
| One critical question, limits and conclusion | 2 min | 14–15 |

## Assessment (30+25+25+10+10)
- **Lecture connection (30)**: Deck E (channel/eye), Deck H (FFE), Deck M (clock/jitter); slides 2–3.
- **Core idea (25)**: Eq. (1), binary-weighted segmented driver and constant conductance/50 ohms; slides 5, 7–9.
- **Reproduction (25)**: independently executed Python model and figures, four tests passed; slides 10–13.
- **Presentation/Q&A (10)**: 20-minute notes, anticipated technical questions, 10-minute discussion.
- **Peer evaluation (10)**: audience evaluation form and assigned next-group question duties must be performed live; slides cannot complete these obligations.

## P3-specific starting script (presentation plan p. 3)
The reason for choosing P3 is that it is a textbook low-power SerDes link with a clear TX equalization/power trade-off. The instructor's [linksim_H-L/sim3_ffe.py](https://github.com/khi103/serdes-lecture-site/blob/main/linksim_H-L/sim3_ffe.py) is a **56-Gb/s 3/5/9-tap ZF FFE example**, with sum|c_i|=1. It is not the 3.6-Gb/s two-tap implementation in the 2004 paper.

The actual executable P3-specific [simulation/p3_reproduce.py](../simulation/p3_reproduce.py) runs 3.6-Gb/s NRZ with 250 mVpp, alpha=0.30, an **idealized 2-pole RC channel adjusted to 12 dB at 1.8 GHz**, and 1/2/3/5/9 taps under sum|c_i|=1. It incorporates the lecture's ZF/L1 concept but is an independent implementation, **not an execution of the original link.sv or a transistor-level reproduction**.

Results (eye height): 1-tap 33.90 mV, paper-style 2-tap 70.13 mV, lecture extensions 3/5/9-tap 65.24/70.14/70.20 mV. The **paper's physical measurement** at alpha=0.30 is 37 mV × 189 ps (Fig. 25). Do not claim numerical equality. The paper's 27.12 mW is a total active TX+RX+PLL link metric (Table IV), not the isolated TX power.

Run:
```sh
python -m pip install -r requirements.txt
python -m pytest -q tests/test_p3.py
python simulation/p3_reproduce.py --out results
```

## Submission and unfinished items
- PPTX and PDF for classroom presentation are delivered separately; the licensed IEEE paper and figure crops are **not committed to this public GitHub repository**.
- Actual names, student IDs and factual contribution split must replace placeholders.
- Team members must submit the PPTX to LearnUs, rehearse the Q&A, prepare next-group questions as assigned, and complete audience peer evaluations.
