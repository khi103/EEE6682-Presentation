#!/usr/bin/env python3
"""Actual MOS reference-PLL clock-frequency tracking across five corners.

Using the independently reconstructed PDK MOS reference PLL with a
physically diode-connected PMOS source-bias generator and resistor
(W=16um, R=4kohm), fixed MOS charge-pump source/sink and VCO, vary ONLY
the ideal reference clock's frequency by [-1000,0,+1000] ppm relative
to 450MHz. The actual MOS oscillator should track FOUR TIMES the
physical reference frequency under XSPICE PFD/4 closed-loop feedback.
The comparator and full serial-data CDR are not included in this test.

Compute 40ns settled oscillator period, phase relative to reference,
MOS VCO-gate ripple, and reference-cycle slip/frequency drift in
three nonoverlapping 80ns windows. The frequency criterion is relative
to the *requested perturbed reference*, not hardcoded 1.800GHz, so
a correctly tracking +1000ppm PLL is not mislabeled as failed.
This is deterministic clock-frequency robustness, not phase-noise,
random clock jitter or the original 2004 ASIC.
"""
from __future__ import annotations
import argparse,json,shutil
from pathlib import Path
import p3_transistor_driver as TX
import p3_xspice_physical_mos_pll as PLL
import p3_pll_extended_pvt_phase as PVT
import p3_real_mos_pump_bias_sentinel as PHYS

CORNERS=("tt","ff","ss","fs","sf")
PPMS=(-1000.,0.,1000.)
INIT=1.02
SUPPLY_V=1.8

def run(out,corner,ppm):
    if corner not in CORNERS or ppm not in PPMS:raise ValueError
    out.mkdir(parents=True,exist_ok=True)
    name=f"corner_{corner}_offset_{ppm:+.0f}ppm".replace("+","p").replace("-","m")
    work=TX.ENGINE_DIR/("p3_reference_freq_tracking_"+name)
    engine=TX.SpiceRunner(work)
    src=TX.model_path(corner);dest=work/src.name
    if not dest.exists() or src.stat().st_mtime>dest.stat().st_mtime:shutil.copy2(src,dest)
    original=PLL.REF_PERIOD_PS
    reference_mhz=450*(1+ppm*1e-6)
    target_ghz=4*reference_mhz/1000
    pvt_orig=PVT.deck
    try:
        PLL.REF_PERIOD_PS=1e12/(reference_mhz*1e6)
        PVT.deck=lambda c,t,v:PHYS.patch(pvt_orig(c,t,v),"diode_w16_r4k")
        deck=PVT.deck(corner,27.,SUPPLY_V)
        engine.run(deck,name)
        rows=PLL.read(work/"physical_pll.csv")
        metrics=PLL.metrics(rows)
        metrics.update(PLL.aligned_phase_errors_ps(rows))
        windows=[PVT.window(rows,t,t+80) for t in (960,1040,1120)]
        freqs=[w["VCO_GHz"] for w in windows]
        drift=(max(freqs)-min(freqs))*1000 if all(f is not None for f in freqs) else None
        frequency=metrics.get("vco_GHz")
        frequency_error_ppm=(frequency/target_ghz-1)*1e6 if frequency is not None else None
        last=windows[-1]
        conditions={
          "target_relative_frequency_error_abs_lt_1500ppm":
             frequency_error_ppm is not None and abs(frequency_error_ppm)<1500,
          "phase_std_lt_8ps":
             metrics.get("std_phase_ps") is not None and metrics["std_phase_ps"]<8,
          "VCO_control_ripple_lt_5mVpp":
             metrics.get("physical_vco_gate_ripple_mV") is not None and
             metrics["physical_vco_gate_ripple_mV"]<5,
          "no_final_reference_cycle_slip":
             last["ref_interval_count"]>=20 and
             last["bad_four_to_one_reference_intervals"]==0,
          "three_windows_drift_lt_2MHz":drift is not None and drift<2,
        }
        record={
          "process":corner,"temperature_C":27.,"VDD_V":SUPPLY_V,
          "reference_frequency_MHz":reference_mhz,
          "reference_offset_ppm":ppm,"target_4x_output_GHz":target_ghz,
          "actual_MOS_VCO_GHz":frequency,
          "frequency_error_relative_to_reference_ppm":frequency_error_ppm,
          "actual_ref_edge_phase_std_ps":metrics.get("std_phase_ps"),
          "control_ripple_mVpp":metrics.get("physical_vco_gate_ripple_mV"),
          "disjoint_window_span_MHz":drift,
          "last_reference_cycle_slips":last["bad_four_to_one_reference_intervals"],
          "screen":conditions,
          "all_conditions_pass":all(conditions.values()),
          "actual_physical_PMOS_diode_bias":True,
          "physical_MOS_CP_VCO":True,
          "XSPICE_digital_reference_PFD":True,
          "original_2004_chip":False,
          "real_random_jitter_or_phase_noise_measured":False,
        }
    except Exception as e:
        record={
          "process":corner,"reference_offset_ppm":ppm,
          "all_conditions_pass":False,
          "status":"spice_failed","error":f"{type(e).__name__}: {str(e)[-1400:]}"}
    finally:
        PLL.REF_PERIOD_PS=original
        PVT.deck=pvt_orig
    (out/(name+".json")).write_text(json.dumps(record,indent=2)+"\n")
    print(f"MOS_PLL_FREQ_TRACK corner={corner} offset_ppm={ppm:+.0f} "
          f"target_GHz={target_ghz:.9f} "
          f"actual_GHz={record.get('actual_MOS_VCO_GHz')} "
          f"tracking_error_ppm={record.get('frequency_error_relative_to_reference_ppm')} "
          f"phase_ps={record.get('actual_ref_edge_phase_std_ps')} "
          f"cycle_slips={record.get('last_reference_cycle_slips')} "
          f"pass={record['all_conditions_pass']}",flush=True)
    return record

if __name__=="__main__":
    p=argparse.ArgumentParser()
    p.add_argument("--corner",choices=CORNERS,required=True)
    p.add_argument("--ppm",type=float,choices=PPMS,required=True)
    p.add_argument("--out",type=Path,default=Path("results/spice/p3_MOS_reference_frequency_tracking"))
    a=p.parse_args()
    run(a.out,a.corner,a.ppm)
