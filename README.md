# EEE6682 P3 — A 27-mW 3.6-Gb/s I/O Transceiver

**Group 11 — 김형인 · 정여진 | December 2, 2026 | 20-minute talk + 10-minute Q&A**

This repository contains original, runnable **behavioral Python reproduction code** for Wong *et al.*, IEEE JSSC 39(4), pp. 602–612 (2004), DOI [10.1109/JSSC.2004.825259](https://doi.org/10.1109/JSSC.2004.825259), together with the updated course rubric mapping.

## Updated professor's rubric (Nov. 9 handout)

**Background and prior limitations 30, core-idea understanding 25, reproduction 25, talk/Q&A 10, peer evaluation 10**. The scoring evidence and the 15-slide/20-minute mapping are in [notes/presentation_rubric_2026-12-02.md](notes/presentation_rubric_2026-12-02.md).

The public GitHub repository intentionally does **not** contain the licensed IEEE PDF, figure crops, or the finished PPTX. Those files are distributed separately in the course presentation deliverables.

## Reproduce the lecture-inspired FFE experiment

The lecture starting script is available in the private fork at [linksim_H-L/sim3_ffe.py](https://github.com/khi103/serdes-lecture-site/blob/main/linksim_H-L/sim3_ffe.py). It runs 56 Gb/s 3/5/9-tap FFE with Verilator and a Touchstone-derived channel.

Our **adapted methodology** is implemented in [simulation/sim3_ffe_P3_adapted.py](simulation/sim3_ffe_P3_adapted.py): 3.6 Gb/s NRZ, 12 dB Nyquist loss at 1.8 GHz, 250 mVpp peak budget, alpha=0.30 paper-like 2-tap plus 3/5/9-tap ZF extensions, and Σ|c_i|=1.

Run from the repository root:

```bash
python -m pip install -r requirements.txt
python -m pytest -q tests/test_p3.py
python simulation/sim3_ffe_P3_adapted.py --out results
```

The original Verilator/SystemVerilog backend is **replaced with a self-contained Python two-pole RC surrogate**. This is an honest *methodology adaptation*, not a transistor-level design reconstruction or a literal run of the instructor's 56-Gb/s simulator. It does not simulate actual RG58/PCB S-parameters, impedance, clock jitter, BER or power.

Our locally reproduced eye heights (1/2/3/5/9-tap): **33.90/70.13/65.24/70.14/70.20 mV**, under the stipulated fixed TX swing constraint. Four Python tests passed. In contrast, Fig. 25 of the **actual paper measures 37 mV x 189 ps** at alpha=0.30. Do not claim equality with the 70.13 mV x 173.61 ps surrogate result.

## Questions and remaining submission tasks

The Dec. 2 order is Group 10 P17, followed by Group 11 P3. **Group 11 is the assigned question group for P17**, and Group 1 will question Group 11. Each Group 11 member should prepare and ask a paper-grounded question. See [notes/p17_question_duty.md](notes/p17_question_duty.md).

**Human actions remain necessary:** Verify actual student IDs and contribution split, rehearse 20 minutes, upload final slides to LearnUs by **Dec. 1, 23:59**, answer Q&A, ask P17 questions, and submit audience peer evaluation forms. These subjective/operational assessment items cannot be completed by code alone.


## NEW: actual DB HiTek NMOS driver ngspice reconstruction (Nov. 11, 2026)

This is separate from the Python-only FFE behavioral reproduction.

- **Executable MOS reconstruction:** [simulation/p3_transistor_driver.py](simulation/p3_transistor_driver.py)
- **Inspectable SPICE netlist:** [circuits/p3_8_4_2_1_nmos_example.cir](circuits/p3_8_4_2_1_nmos_example.cir)
- **Results, circuit assumptions, and limitations:** [docs/p3_driver_spice_results_2026-11-11.md](docs/p3_driver_spice_results_2026-11-11.md)
- **Automated 180-nm PDK-based CI:** [P3 ngspice workflow](.github/workflows/p3_driver_spice.yml)
- **Permanent numerical results:** [results/spice/p3_segmented_driver/driver_summary.json](results/spice/p3_segmented_driver/driver_summary.json) plus `tt_code_sweep.csv` and `pvt_corner_sweep.csv`
- **Editable Veusz chart specification:** [veusz/P3_MOS_Driver_Editable.vsz](veusz/P3_MOS_Driver_Editable.vsz)
- **Verified successful Actions run:** [P3 MOS driver run 43000597888](https://github.com/khi103/EEE6682-Presentation/actions/runs/43000597888)

Independent 8:4:2:1 NMOS pull-up/pull-down reconstruction, calibrated **at TT / 27°C only**:
nominal incremental R_OUT **49.20–50.72 Ω** (16 codes); loaded swing **285.99 mVpp**,
which is **not** the ideal 250-mVpp target; PRBS RX eye at a **fixed, identical**
sample phase increased **50.96 → 90.01 mV** for a quantized α=0.30 two-tap FFE
with the same two-pole surrogate channel. The 0.5-V signaling-source average
power increased **0.780 → 1.014 mW**. Without bias/impedance feedback, the
reconstructed stage varies from **42.81 Ω (FF)** to **58.67 Ω (SS)** at code 7.

The **published** Fig. 25 silicon eye is **37 mV × 189 ps**, not our computed
90.01-mV result. **This is not the original author's transistor-level circuit.**
The exact predriver, impedance/slew feedback, actual cable S-parameters,
jitter/RX/PLL, and full power budget are missing. ngspice also ignores several
HSPICE-only BSIM3 model parameters; no HSPICE numeric correlation has yet been
established. The 0.5-V signal supply power excludes gate-driver power and
receiver termination bias. Use the full documentation rather than treating the
good nominal 50-ohm result as a silicon validation.

## Expanded electrical validation (Nov. 12, 2026)

The enhanced MOS ngspice workflow also checks each code at its **actual loaded PAD voltage** (source impedance **35.92–50.35 Ω**, despite **49.20–50.72 Ω** at the fixed 0.25-V reference). An ideal gate-bias sweep shows that FF/FS can approach 50 Ω at the tested operating point, whereas SS/SF cannot do so within a 0.9–1.8-V gate-high range. Synthetic Gaussian RX noise and sampling jitter applied to *ngspice-generated waveforms* further indicate a conditional FFE decision-margin benefit, but are **not physical comparator/CDR or measured BER simulations**.

Full verified results, uncertainties, open questions, links to the new CSVs and the exact run: [docs/p3_expanded_verification_2026-11-12.md](docs/p3_expanded_verification_2026-11-12.md).
