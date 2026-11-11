# DB HiTek 180 nm — P3 1.8 V device inventory (metadata only)

This file records **identifiers, terminal order, intended tests, and local references**, not foundry model parameter values or protected source. The available PDK library explicitly states restrictions on reproduction/adaptation/distribution, so neither the full PDK nor an extracted model subset has been committed to this repository. Confirm your own authorization before any remote distribution, even in a private repository.

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

## Planned P3 circuit-level tests (not yet executed)

1. 1.8-V inverter / individual transistor DC and transient smoke test with the `tt_svt018` model.
2. 8:4:2:1 weighted segment output-driver reconstruction, including bias controls and a 50-ohm load.
3. DC output level and incremental output resistance `Rout = ΔVout/ΔItest` for each FFE coefficient/code, not solely a single operating point.
4. Transient eye waveform and average supply-current integration with the **same** data pattern and channel assumptions as the behavioral model.
5. Corner, supply, temperature variation, optionally mismatch after compatibility is validated.
6. Compare with paper Fig. 7 (topology), Fig. 10 (impedance), Fig. 25 (eye), Table III–IV (power); label all reconstructed-model outputs separately from silicon measurements.

**Status:** Only static file/device/corner mapping has been checked. No HSPICE or ngspice run using this PDK has yet been demonstrated here; ngspice compatibility remains an open test.
