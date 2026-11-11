#!/usr/bin/env python3
"""Regenerate Veusz-compatible CSV from the P3 independent Python RC model.

This is NOT a PDK/transistor/SPICE reproduction of the JSSC silicon.
Run from the repository root: python simulation/export_veusz.py
"""
from pathlib import Path
import csv
import json
import numpy as np
import p3_reproduce as P

ROOT = Path(__file__).resolve().parents[1]
RES = ROOT / "results"
OUT = ROOT / "veusz"

def save(name, header, rows):
    OUT.mkdir(parents=True, exist_ok=True)
    with (OUT / name).open("w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(header)
        w.writerows(rows)
    print("Wrote", name, "rows", len(rows))

def main():
    if not (RES / "p3_results.json").exists():
        P.run(RES)
    d = json.loads((RES / "p3_results.json").read_text())
    cases = d["simulated_cases"]
    names = ["1-tap, no FFE", "2-tap, alpha=0.30",
             "3-tap ZF (lecture extension)", "5-tap ZF (lecture extension)",
             "9-tap ZF (lecture extension)"]
    save("tap_tradeoff.csv",
         ["tap_count","sum_abs_coefficients","dc_swing_mVpp","eye_height_mV",
          "eye_width_ps","main_cursor_mV","sum_abs_isi_mV"],
         [[len(v["taps"]),v["L1"],v["DC_run_amplitude_mVpp"],
           v["worst_case_eye_height_mV"],v["eye_width_ps"],
           v["main_cursor_mV"],v["sum_abs_other_cursors_mV"]]
          for v in (cases[k] for k in names)])
    save("alpha_sweep.csv",
         ["alpha","eye_height_alpha_mV","eye_width_alpha_ps",
          "dc_swing_alpha_mVpp","main_coeff_alpha"],
         [[v["alpha"],v["eye_height_mV"],v["eye_width_ps"],
           v["dc_swing_mVpp"],v["main_coeff"]] for v in d["alpha_sweep"]])
    f = np.linspace(0.0, 3.0, 401)
    save("channel_loss.csv", ["freq_GHz","onepole_loss_dB","twopole_loss_dB"],
         [[x,P.channel_db(x*1e9,1),P.channel_db(x*1e9,2)] for x in f])
    save("channel_sensitivity.csv",
         ["rc_order","ffe_enabled","eye_height_mV","eye_width_ps"],
         [[v["order"],int(v["label"]=="alpha=0.3"),v["eye_mV"],v["width_ps"]]
          for v in d["sensitivity"]])
    # Eye overlay has NaN breaks so that separate UI traces are not joined.
    bits = P.m_sequence(2048)
    wave = []
    for coeff in [[1.0],[1/(1+.3),-.3/(1+.3)]]:
        _, rx = P.simulate(bits, np.array(coeff))
        wave.append((rx,P.eye_metrics(bits,rx)))
    eyes = []
    for k in range(150,205):
        sampled = []
        for rx,met in wave:
            center = (k+met["lag"])*P.OSR+met["phase"]
            sampled.append(rx[center-P.OSR:center+P.OSR+1])
        for i,t in enumerate(np.linspace(-1,1,2*P.OSR+1)):
            eyes.append([t,1e3*(sampled[0][i]+P.VCM),
                         1e3*(sampled[1][i]+P.VCM)])
        eyes.append([float("nan")]*3)
    save("eye_overlay.csv",["eye_time_UI","without_ffe_mV","with_2tap_mV"],eyes)
    print("Open veusz/P3_Editable_Plots.vsz in Veusz; CSV values are linked.")

if __name__ == "__main__":
    main()
