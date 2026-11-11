# DB HiTek 180 nm — P3 1.8 V device inventory (metadata only)

This file records **identifiers, terminal order, intended tests, and local references**, not foundry model parameter values or protected source. The available PDK library explicitly states restrictions on reproduction/adaptation/distribution, The user subsequently committed the extracted subset ZIP to this private repository. This file only lists metadata and does not reproduce foundry coefficients. Private hosting does not, by itself, establish redistribution permission; confirm your authorization.

## Source models examined locally

| Local file | Purpose | Needed now? |
| --- | --- | --- |
| `1830BD18BA_Rev3p6p0.l` | HSPICE process library, includes 1.8-V SVT sections/corners | **Yes**: use original authorized copy locally |
| `1830BD18BA_Rev3p6p0_mis.l` | Mismatch / Monte Carlo statistics | Later, after nominal simulation |
| `1830BD18BA_Rev3p6p0_eSOA.l` | Electrical safe-operating-area checking | Optional, later |
| `dbody_nldmhs_12va.va.hspice`, `dbody_nldmiso_12va.va.hspice`, `dbody_pldm_12va.va.hspice` | Verilog-A **body diode** modules in 12-V/20-V LDMOS sublibraries (`.hdl` references) | **No** for 1.8-V SVT |
| Three corresponding `.vp` files | Protected/encrypted alternative Verilog-A bodies (`pragma protect`) | **No** for 1.8-V SVT |
| `cornerSim.il` | Cadence SKILL tool controlling corner selection | **No** for HSPICE/ngspice netlist |

## Selected devices in base library

| Role | Declared HSPICE subcircuit name | External terminal order |
| --- | --- | --- |
| NMOS switch / pull-down | `nch_svt_1p8v` | `d g s b` |
| PMOS switch / pull-up | `pch_svt_1p8v` | `d g s b sub` |

Do **not** use a four-terminal PMOS call for `pch_svt_1p8v`; it has five external terminals. Use appropriate bulk/substrate hookups according to the authorized PDK documentation.

Nominal library section: `tt_svt018`; process corners identified: `ff_svt018`, `ss_svt018`, `fs_svt018`, `sf_svt018`. Model/library names above were verified by direct static inspection.

The HSPICE library internally references other sections and model parameters using `.lib`, and therefore **cannot safely be reduced to two individual `.model` lines without dependency tracing and numerical comparison**.

## How to keep local PDK separate from reproducible project files

Recommended working layout (outside version-controlled files):

```text
EEE6682-Presentation/
  circuits/                  # student-authored SPICE netlists — tracked
  simulation/                # student-authored Python scripts — tracked
  docs/pdk/                  # this metadata manifest — tracked
  pdk_private/               # licensed foundry models — ignored by Git
    1830BD18BA_Rev3p6p0.l
    1830BD18BA_Rev3p6p0_mis.l
    1830BD18BA_Rev3p6p0_eSOA.l
```

Do **not** upload copied blocks of foundry `.model` parameters as a substitute for the original files. Check the license/contract before placing any foundry model bytes on GitHub Actions runners or other third-party servers.

## Updated execution status (Nov. 11, 2026)

- **Completed:** ngspice-42 inverter DC/Transient smoke test under `ngbehavior=hs`, 1650 waveform rows and basic switching validation.
- **Completed:** independent 8:4:2:1 NMOS driver reconstruction with 16-code DC sweep, incremental output resistance measurement, nominal width calibration, FF/SS/FS/SF corners, -20/85°C and 0.45/0.55-V signaling-supply variation.
- **Completed:** 128-bit PRBS7 MOS-driver transient test, FFE on/off at 3.6 Gb/s with the same surrogate two-pole channel.
- **Verified CI run:** https://github.com/khi103/EEE6682-Presentation/actions/runs/43000597888
- **Model/measurement report:** [P3 reconstructed MOS driver results](../p3_driver_spice_results_2026-11-11.md)
- **Not completed:** HSPICE-versus-ngspice numerical correlation, original paper's real impedance feedback and slew control, accurate transmitter/RX PLL/CDR, physical PCB/cable S-parameter channel, full-link power, BER.

The tested circuit is a **separate NMOS reconstruction** informed by the published Fig. 7, not an exact implementation of the authors' PDK and topology. HSPICE-specific model parameters are ignored by ngspice and require correlation testing.
