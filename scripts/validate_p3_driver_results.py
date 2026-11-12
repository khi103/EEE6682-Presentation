#!/usr/bin/env python3
"""Post-process checks for independent reconstructed P3 segmented NMOS driver.

Physical plausibility and reproducibility checks, NOT foundry validation.
"""
from pathlib import Path
import csv
import json
import math
import argparse

def read(path):
    with path.open(newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))

def check(out):
    d=json.loads((out/"driver_summary.json").read_text())
    levels=read(out/"tt_code_sweep.csv")
    pvt=read(out/"pvt_corner_sweep.csv")
    assert d["status"] == "reconstructed_nmos_driver_simulated"
    assert len(levels)==16
    assert [int(x["code"]) for x in levels]==list(range(16))
    v=[float(x["vout_V"]) for x in levels]
    z=[float(x["rout_ohm_at_vref"]) for x in levels]
    assert all(y>x for x,y in zip(v,v[1:])), "Output levels not strictly monotonic"
    assert 40<min(z)<55 and 45<max(z)<65, "Unphysical nominal resistance"
    assert d["calibration"]["up"]["bracketed"] and d["calibration"]["down"]["bracketed"]
    assert 0.0 < d["tt_code_sweep"]["dnl_max_abs_LSB"] < 1.0
    assert 200 < d["tt_code_sweep"]["actual_loaded_swing_mVpp"] < 400
    assert {x["corner"] for x in pvt}=={"tt","ff","ss","fs","sf"}
    assert len(pvt)>=37, "Corner, temperature and supply sweeps incomplete"
    def get(corner,code, temp=27., vs=0.5):
        for r in pvt:
            if r["corner"]==corner and int(r["code"])==code and float(r["temp_C"])==temp and float(r["v_signal_V"])==vs:
                return float(r["rout_ohm_at_vref"])
        raise AssertionError(f"Missing PVT {corner},{code},{temp},{vs}")
    assert get("ff",7)<get("tt",7)<get("ss",7), "Process sensitivity not observable"
    assert get("tt",7,vs=.45)<get("tt",7)<get("tt",7,vs=.55), "Supply sweep not applied"
    assert get("tt",7,temp=-20)<get("tt",7)<get("tt",7,temp=85), "Temperature sweep not applied"
    tr=d["transient"]
    baseline=tr["baseline"]
    ffe=tr["ffe_alpha_0p30"]
    assert baseline["waveform_rows"]>500 and ffe["waveform_rows"]>500
    assert ffe["rx_eye"]["eye_mV"]>baseline["rx_eye"]["eye_mV"], "FFE did not open the eye"
    assert ffe["rx_eye_at_common_1p20_UI_mV"]>baseline["rx_eye_at_common_1p20_UI_mV"], "No same-phase FFE improvement"
    assert 0<baseline["driver_signal_supply_mean_mW"]<10
    assert 0<ffe["driver_signal_supply_mean_mW"]<10
    assert all(math.isfinite(k) for k in z)
    operating=[float(r["rout_ohm_at_loaded_operating_point"]) for r in levels]
    assert all(0 < x < 300 for x in operating)
    assert min(operating) < min(z)-5, (
        "Expected physical nonlinear Rout variation at actual pad voltages"
    )
    authority=json.loads((out/"gate_bias_authority.json").read_text())
    assert authority["status"]=="simulated_independent_gate_bias_control_authority"
    assert authority["ngspice_calls"]>=60
    assert set(authority["per_corner"])=={"tt","ff","ss","fs","sf"}
    assert authority["per_corner"]["ff"]["crosses_50_ohm_in_tested_bias_range"]
    assert not authority["per_corner"]["ss"]["crosses_50_ohm_in_tested_bias_range"]
    noise=json.loads((out/"rx_noise_jitter_robustness.json").read_text())
    assert noise["status"]=="synthetic_receiver_noise_jitter_study"
    comparison=noise["comparison_10ps_12mV"]
    assert (comparison["baseline"]["empirical_error_fraction"] >
            comparison["ffe_alpha_0p30"]["empirical_error_fraction"])
    extra=read(out/"rx_noise_jitter_robustness.csv")
    assert len(extra)==2*len(noise["noise_rms_mV"])*len(noise["jitter_rms_ps"])
    print(f"PASS: Extended impedance at operating point, gate-bias authority, and "
          f"synthetic RX noise/jitter sensitivity")
    print(f"Operating Rout={min(operating):.2f}–{max(operating):.2f} ohm")
    print(f"Error fraction at J=10ps, N=12mV: "
          f"{comparison['baseline']['empirical_error_fraction']:.6g} -> "
          f"{comparison['ffe_alpha_0p30']['empirical_error_fraction']:.6g}")
    print(f"PASS: P3 reconstructed MOS driver, 16 output codes, {len(pvt)} PVT points, transient eye/supply")
    print(f"Rout TT={min(z):.3f}...{max(z):.3f} ohm; code7 FF/TT/SS={get('ff',7):.3f}/{get('tt',7):.3f}/{get('ss',7):.3f}")
    print(f"Eye @ common 1.20UI: {baseline['rx_eye_at_common_1p20_UI_mV']:.3f} -> {ffe['rx_eye_at_common_1p20_UI_mV']:.3f} mV")
    print(f"Driver DC supply mean: {baseline['driver_signal_supply_mean_mW']:.3f} -> {ffe['driver_signal_supply_mean_mW']:.3f} mW")
    print("LIMIT: calibrated, simplified NMOS reconstruction; not original P3 IC/PDK validation")

if __name__=="__main__":
    p=argparse.ArgumentParser()
    p.add_argument("--out",type=Path,default=Path("results/spice/p3_segmented_driver"))
    check(p.parse_args().out)
