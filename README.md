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

## NEW: executed exact lecture sim3_ffe.py and real adapted Verilator (Nov. 12)

The **original** lecturer's `sim3_ffe.py` was run **unchanged** at 56 Gb/s
in the private lecture fork, producing all 1/3/5/9-Tap outputs:
[verified run](https://github.com/khi103/serdes-lecture-site/actions/runs/43142270060).
Its original eye heights are -130.22 mV (no FFE), 70.58 mV (3-tap),
72.89 mV (5-tap) and 74.84 mV (9-tap).

The original lecturer's SystemVerilog `link.sv` was **also actually executed**
under Verilator after scratch-copy parameter adaptation to **3.6 Gb/s**,
synthetic -12 dB at 1.8 GHz, and a 2-Tap alpha=0.30 FFE:
[verified modified run](https://github.com/khi103/serdes-lecture-site/actions/runs/43139646362).
The 3.6-Gb/s RC2 eye is **35.17 mV without FFE vs 67.63 mV with FFE**.
This is separate from the earlier self-contained Python surrogate,
whose source file was not itself modified into Verilator.

The **channel-shape control experiment** using real Verilator showed that
1-, 2- and 3-pole synthetic channels having identical approximately 12-dB
Nyquist loss produce materially different eyes. See the
[channel sensitivity CI](https://github.com/khi103/serdes-lecture-site/actions/runs/43141054011).

The latest MOS-PDK validations include hypothetical per-corner
width re-trimming, gate slew variation, physical MOS DC I-V sanity,
and synthetic RX noise/jitter/offset and functional CDR phase tracking.
The details and all unavailable **original-chip** evidence are catalogued
in [docs/P3_추가검증_종합보고서_20261112.md](docs/P3_추가검증_종합보고서_20261112.md).


## Fig8/Fig14/Fig20 independent MOS tests (Nov. 12, 2026)

Three additional independent transistor-level/simulation-hybrid blocks were
actually executed with the DB HiTek SVT models:

- **Fig8-inspired pull-up/pull-down replicas:** [closed-loop MOS replica, ideal analog integrator](simulation/p3_fig8_analog_replica_loop.py) with [verified ngspice run](https://github.com/khi103/EEE6682-Presentation/actions/runs/43146576981); and [6-bit SAR MOS replica calibration](simulation/p3_fig8_dual_replica_feedback.py). Both can calibrate an isolated 50-ohm reference at TT/FF/SS/FS/SF. They do **not** implement the actual paper's Op-Amp/LDO or guarantee the full 16-code PAD Rout.
- **Fig14-inspired MOS comparator:** [physical PMOS-input differential amplifier, NMOS current-mirror load and CMOS buffers](simulation/p3_fig14_comparator_mos.py), plus [binary-weighted MOS current trim](simulation/p3_fig14_offset_current_trim.py), [verified executed characterization](https://github.com/khi103/EEE6682-Presentation/actions/runs/43147732459). MOS switching works only at a **100-MHz large-swing** test; it **does not** meet the paper's 1.8-GHz / small-signal comparator requirement. Full M1–M19 regenerative latch and precise offset controller are not implemented.
- **Fig20-inspired current pump:** [physical PMOS/NMOS 7-bit weighted current DAC](simulation/p3_fig20_charge_pump_mos.py), [executed ngspice](https://github.com/khi103/EEE6682-Presentation/actions/runs/43147620804). Only code-current monotonicity at a clamped 0.9-V node was verified. Fig21's measured phase shift and the paper's actual PLL are **not** reproduced. The separate [functional ideal-PLL loop](simulation/p3_fig18_pll_from_mos_pump.py) consumes this MOS current lookup but is not a transistor PLL.

See the [comprehensive report in Korean](docs/P3_Fig8_Fig14_Fig20_MOS_회로검증_20261112.md).
**These blocks have not yet been integrated into a validated 3.6-Gb/s
transistor-level TX–RX–PLL/CDR.** PDK HSPICE/ngspice numerical equivalence,
actual RG58/FR4 S-parameters, original 2004 silicon layout, full-link
power and jitter remain unavailable or unverified. Do not claim otherwise.


## NEW: single-deck transistor-level TX + RX + MOS ring VCO (Nov. 12, 2026)

The previously separate MOS reconstructions have now been electrically
connected in one **ngspice** netlist:

**3.6-Gb/s 8:4:2:1 MOS TX → two-pole surrogate channel →
two 1.8-GHz PMOS-input regenerative MOS RX latches**, clocked by
a **real current-starved three-stage CMOS VCO** and CMOS clock buffers.

The free-running VCO was tuned **externally** to 1.7992 GHz using a
series of MOS SPICE runs, and the RX sampling phase/parity was selected
**offline with known PRBS bits**. In the most recent strict regression
(>=150-mV physical latch Q−QB resolved differential), both no-FFE and
two-tap-FFE runs achieved **0/104 errors, 0 unresolved latch samples**
at **TT** (not a BER or independent CDR proof).

- [Strict regression in GitHub Actions](https://github.com/khi103/EEE6682-Presentation/actions/runs/43154855455)
- [Unified MOS TX/RX/VCO implementation](simulation/p3_full_link_physical_mos_vco.py)
- [Testbench/graph generator](simulation/plot_full_mos_link.py)
- [Full Korean technical report and limitations](docs/P3_180nm_전체MOS링크_통합검증_20261112.md)

**In-circuit clock recovery remains unresolved.** A prototype in-ngspice
behavioral frequency feedback driving the *physical MOS VCO* brought the
oscillation to **1.801885 GHz**, but a stricter valid-output check found
**24/104 RX errors**, including 9 unresolved latch states. The later
data-timing variant also failed (49/104 errors). This is **not** a
validated physical PLL/CDR or a reproduction of the paper's Fig. 18–20.
The model uses ideal FFE control sources, channel buffers and reference
clock, and ignores several foundry HSPICE-only parameters. The original
2004 silicon and 27.12-mW link performance have **not** been reproduced.


## Data-only transition CDR test with actual 180nm MOS latches

A new **two-pass data-only timing recovery / MOS-RX co-simulation** has
been successfully executed at 3.6Gb/s. A causal phase estimator is
updated ONLY by received RX threshold crossing times, never by TX PRBS
bits. The resulting clock-event PWL then drives two actual PDK MOS
regenerative receiver latches, with a minimum **150-mV |Q-QB|** margin
to count a valid sample. The known PRBS is used ONLY for postrun
integer-frame alignment and scoring.

All three alpha=0.30 FFE tests (nominal, +1000ppm, -1000ppm receiver
clock) gave **0 errors / 187 valid MOS samples**, with no unresolved
samples. At +1000ppm without recovery, **50/187 errors**, including
39 unresolved MOS latch samples, were observed.

- [Actual passing Actions run](https://github.com/khi103/EEE6682-Presentation/actions/runs/43157182215)
- [Causal data-only timing recovery / MOS replay code](simulation/p3_blind_cdr_mos_cosim.py)
- [Precise scope and measurements in Korean](docs/P3_수신데이터_기반_CDR_MOS검증_20261112.md)

This **does NOT** demonstrate a simultaneous in-SPICE physical
PFD/Charge-Pump/VCO/CDR loop. The new recovered clock is still an ideal
PWL source generated between separate MOS simulations. The physical
VCO / B-source phase-detector same-netlist experiments are tracked
separately, and should not be advertised as a locked data CDR unless
their quantitative clock-frequency and MOS-latch tests also pass.


## NEW: Fig.19-style four-XOR / seven-bit MOS-pump-informed CDR (Nov. 12)

[Actual passing 512-bit DB HiTek MOS validation](https://github.com/khi103/EEE6682-Presentation/actions/runs/43159596701)
uses the architecture described by Wong et al., Fig. 19: Edge/Data
samples, four-XOR Up/Down arbitration, downsampling and a seven-bit
saturating phase counter. The controller is **causal but runs in Python**.
It uses a transistor-characterized 7-bit MOS charge-pump DC-current
lookup, converted to assumed clock phase shifts using the paper's
measured 350-ps range. The resulting clock is then an **ideal PWL source**
which drives **physical 180nm MOS regenerative receiver latches**.

Under a +1000-ppm nominal clock error and unfavorable starting counter
127, **CDR OFF: 30/378 unresolved-or-incorrect MOS samples** versus
**CDR ON: 0/378**, with **all 378 output samples regenerated >=150mV**.
Seven other CDR-on settings also achieved 0/378 over the same PRBS.
Data labels were **not used for any up/down phase control**; PRBS was
used after the transistor simulation solely for word alignment/scoring.

- [Full MOS BBPD testbench](simulation/p3_fig19_bbpd_mos_cosim.py)
- [Detailed Korean methodology and explicit limits](docs/P3_Fig19_BBPD_MOS_수신검증_20261112.md)
- [Automated validation workflow](.github/workflows/p3_fig19_bbpd_mos.yml)

**An actual one-SPICE physical phase-locked data recovery loop has still
NOT locked.** The separate same-netlist B-source edge detector connected
to the physical MOS TX/RX/VCO fails frequency-plus-recovered-data
qualification across the tested gains. That experiment should be treated
as a physical/control design shortcoming, NOT as an achieved PLL/CDR.
The verified Fig19 case uses a two-pass MOS/behavioral co-simulation
and an assumed current-to-phase transfer function.
