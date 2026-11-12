#!/usr/bin/env python3
"""Independent NMOS-only, binary-weighted TX driver reconstruction for P3.

This is NOT the exact Wong et al. JSSC 2004 transistor circuit. The published
feedback loops, measured channel, layout, and PLL/RX are not available.
Two *alternately enabled* DB HiTek 1.8-V SVT NMOS devices per 8:4:2:1 bank
connect PAD to 0.5 V or to ground, with separate nominal width calibration.

Runs ngspice on local PDK COPIES created by prepare_ngspice_model.py.
No proprietary PDK coefficients enter this script or its outputs.
All outputs are independently generated reconstruction results, NOT silicon.
"""
from __future__ import annotations

import argparse
import csv
import json
import math
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PDK_DIR = ROOT / "pdk_private"
ENGINE_DIR = PDK_DIR / "ngspice_compat"
DEFAULT_OUT = ROOT / "results" / "spice" / "p3_segmented_driver"
CORNER_NAMES = ("tt", "ff", "ss", "fs", "sf")
WEIGHTS = (8, 4, 2, 1)
V_GATE = 1.8
V_SIGNAL = 0.5
V_COMMON = 0.25
R_TERM = 50.0
L_UM = 0.18
UI_PS = 1e12 / 3.6e9
ALPHA = 0.30
PROCESS_TEMP_C = 27.0
# These are behavioral testbench assumptions, NOT extracted from P3 layout.
PAD_CAP_F = 100e-15
CHANNEL_R_OHM = 50.0
CHANNEL_C_F = 3.053260318e-12    # 2-pole surrogate: -12 dB @ 1.8 GHz
RC_POLES = 2

def model_path(corner: str) -> Path:
    if corner not in CORNER_NAMES:
        raise ValueError(f"Unknown corner {corner}")
    dest = ENGINE_DIR / f"db180_svt018_{corner}.lib"
    orig = PDK_DIR / f"db180_svt018_{corner}.lib"
    converter = ROOT / "scripts" / "prepare_ngspice_model.py"
    if not orig.exists():
        raise FileNotFoundError(
            f"Missing local model {orig}. Run bash scripts/run_dbhitek_smoke.sh "
            "on a licensed PDK-capable environment first."
        )
    if not dest.exists() or orig.stat().st_mtime > dest.stat().st_mtime or converter.stat().st_mtime > dest.stat().st_mtime:
        subprocess.run([sys.executable, str(converter), str(orig), str(dest)], check=True)
    return dest

def inv_sources(code: int, wu: float, wd: float, mode: str = "dc") -> list[str]:
    if not 0 <= code <= 15:
        raise ValueError(code)
    lines = []
    for weight in WEIGHTS:
        is_up = bool(code & weight)
        up_val = V_GATE if is_up else 0.0
        dn_val = 0.0 if is_up else V_GATE
        lines += [
            f"VGU{weight} gu{weight} 0 DC {up_val:.8g}",
            f"VGD{weight} gd{weight} 0 DC {dn_val:.8g}",
            # NMOS-only low-common-mode pull-up and pull-down
            f"XPU{weight} vs gu{weight} pad 0 nch_svt_1p8v width={wu:.10g}u length={L_UM}u multi={weight}",
            f"XPD{weight} pad gd{weight} 0 0 nch_svt_1p8v width={wd:.10g}u length={L_UM}u multi={weight}",
        ]
    return lines

def make_dc(code: int, wu: float, wd: float, corner: str,
            clamp_v: float | None, temp_c: float = PROCESS_TEMP_C,
            v_signal: float = V_SIGNAL) -> str:
    lines = [
        "* INDEPENDENT reconstructed P3 binary-weighted NMOS voltage-mode TX",
        "* Not the exact 2004 transistor-level source implementation.",
        f'.include "db180_svt018_{corner}.lib"',
        f".temp {temp_c}",
        f"VSUP vs 0 DC {v_signal}",
        f"VREF vref 0 DC {v_signal/2:.8g}",
    ]
    lines += inv_sources(code, wu, wd)
    if clamp_v is None:
        lines += [f"RTERM pad vref {R_TERM}", "CPAD pad 0 100f"]
    else:
        lines += [f"VCLAMP pad 0 DC {clamp_v:.8g}"]
    lines += [".control", "set noaskquit", "op"]
    if clamp_v is None:
        lines.append("print v(pad) i(vsup)")
    else:
        lines.append("print i(vclamp)")
    lines += ["quit", ".endc", ".end"]
    return "\n".join(lines) + "\n"

FLOAT_RE = r"([-+]?(?:[0-9]+(?:\.[0-9]*)?|\.[0-9]+)(?:[Ee][-+]?[0-9]+)?)"

def spice_vector(log: str, vector: str) -> float:
    # ngspice print i(vxxx) appears as vxxx#branch
    rx = re.compile(r"^\s*" + re.escape(vector) + r"\s*=\s*" + FLOAT_RE + r"\s*$", re.I | re.M)
    m = rx.search(log)
    if not m:
        raise RuntimeError(f"Missing vector '{vector}' in ngspice log:\n{log[-2500:]}")
    v = float(m.group(1))
    if not math.isfinite(v):
        raise RuntimeError(f"Non-finite {vector}: {v}")
    return v

class SpiceRunner:
    def __init__(self, working: Path):
        self.working = working
        self.working.mkdir(parents=True, exist_ok=True)
        (self.working / ".spiceinit").write_text("set ngbehavior=hs\n")
        self.calls = 0
        self.warning_types = set()

    def run(self, deck: str, tag: str) -> str:
        cir = self.working / f"{tag}.cir"
        cir.write_text(deck)
        run = subprocess.run(
            ["ngspice", "-b", cir.name], cwd=self.working,
            capture_output=True, text=True, timeout=90,
        )
        self.calls += 1
        txt = run.stdout + "\n" + run.stderr
        if run.returncode != 0 or re.search(r"(^|\n)\s*(Error|Fatal)\s*[:o]", txt, re.I):
            raise RuntimeError(f"ngspice failed for {tag} (returncode={run.returncode}):\n{txt[-4500:]}")
        for match in re.findall(r"unrecognized parameter\s*\(([^)]+)\)", txt, flags=re.I):
            self.warning_types.add(match.lower())
        return txt

    def dc(self, code: int, wu: float, wd: float, corner: str,
           clamp_v: float | None = None,
           temp_c: float = PROCESS_TEMP_C, v_signal: float = V_SIGNAL) -> dict:
        deck = make_dc(code, wu, wd, corner, clamp_v, temp_c, v_signal)
        tag = f"dc_{self.calls:05d}"
        txt = self.run(deck, tag)
        if clamp_v is None:
            return {
                "pad_V": spice_vector(txt, "v(pad)"),
                "driver_supply_A": spice_vector(txt, "i(vsup)"),
            }
        return {"clamp_A": spice_vector(txt, "i(vclamp)")}

    def rout(self, code: int, wu: float, wd: float, corner: str,
             temp_c: float = PROCESS_TEMP_C, v_signal: float = V_SIGNAL) -> float:
        dv = 0.002
        a = self.dc(code, wu, wd, corner, v_signal/2-dv/2, temp_c, v_signal)["clamp_A"]
        b = self.dc(code, wu, wd, corner, v_signal/2+dv/2, temp_c, v_signal)["clamp_A"]
        conductance = abs(b-a)/dv
        if conductance <= 0:
            raise RuntimeError("Non-positive incremental conductance")
        return 1.0/conductance

def rout_at_operating_voltage(runner: SpiceRunner, code: int,
                              wu: float, wd: float, corner: str,
                              center_v: float, temp_c: float=PROCESS_TEMP_C,
                              v_signal: float=V_SIGNAL) -> float:
    """Incremental source resistance at actual LOADED pad operating point.
    
    Measure dV/dI by removing the termination and substituting a voltage clamp,
    centered on the pad voltage found with the matched 50-ohm receiver.
    """
    dv=.002
    a=runner.dc(code,wu,wd,corner,center_v-dv/2,temp_c,v_signal)["clamp_A"]
    b=runner.dc(code,wu,wd,corner,center_v+dv/2,temp_c,v_signal)["clamp_A"]
    return dv/abs(b-a)


def calibrate(runner: SpiceRunner, corner: str, code: int, side: str,
              desired_r: float = 50.0) -> dict:
    # width_unit in micrometers; each binary unit is an NMOS finger, and
    # multi=weight sets how many parallel unit fingers are in each bank.
    lo, hi = 0.36, 10.0
    def measure(w):
        wu, wd = (w, 1.0) if side=="up" else (1.0, w)
        return runner.rout(code, wu, wd, corner)
    rlo, rhi = measure(lo), measure(hi)
    attempts = [{"w_um":lo,"r_ohm":rlo},{"w_um":hi,"r_ohm":rhi}]
    if not (rlo >= desired_r >= rhi):
        best = min(attempts, key=lambda item: abs(item["r_ohm"]-desired_r))
        return {"unit_w_um":best["w_um"],"measured_r_ohm":best["r_ohm"],
                "bracketed":False,"attempts":attempts}
    for _ in range(7):
        mid = (lo+hi)/2
        rm = measure(mid)
        attempts.append({"w_um":mid,"r_ohm":rm})
        if rm > desired_r:
            lo = mid
        else:
            hi = mid
    best = min(attempts, key=lambda item: abs(item["r_ohm"]-desired_r))
    return {"unit_w_um":best["w_um"],"measured_r_ohm":best["r_ohm"],
            "bracketed":True,"attempts":attempts}

def prbs7(n: int, seed: int = 0x5D) -> list[int]:
    # Deterministic 7-bit LFSR; exact polynomial is not a paper claim.
    state = seed & 0x7f
    ret = []
    for _ in range(n):
        ret.append(state & 1)
        feedback = ((state >> 6) ^ (state >> 5)) & 1
        state = ((state << 1) & 0x7f) | feedback
    return ret

def ffe_codes(bits: list[int], alpha: float) -> list[int]:
    if alpha < 0 or alpha > 1:
        raise ValueError("alpha must lie between 0 and 1")
    prev = bits[0]
    codes = []
    for b in bits:
        now = 2*b-1
        old = 2*prev-1
        normalized = (now - alpha*old)/(1.0+alpha)
        codes.append(max(0, min(15, int(math.floor((normalized+1)*7.5+0.5)))))
        prev = b
    return codes

def pwl_gate(name: str, node: str, levels: list[float],
             transition_ps: float = 2.0) -> list[str]:
    # Gate 10%-90% slew is NOT the original paper's control circuit.
    # This is a parametric, ideal, symmetric linear PWL gate ramp.
    if not 0 < transition_ps < UI_PS:
        raise ValueError("Gate transition time must be positive and less than one UI")
    dt = UI_PS
    points = [(0.0, levels[0])]
    for n in range(1, len(levels)):
        t = n*dt
        points.append((t-transition_ps/2, levels[n-1]))
        points.append((t+transition_ps/2, levels[n]))
    points.append((len(levels)*dt, levels[-1]))
    lines = [f"{name} {node} 0 PWL("]
    for t, v in points:
        lines.append(f"+ {t:.8f}p {v:.8g}")
    lines[-1] += ")"
    return lines

def make_transient(codes: list[int], wu: float, wd: float, corner="tt",
                   gate_transition_ps: float = 2.0) -> str:
    lines = [
        "* NONEXACT P3 NMOS-only TX reconstruction and surrogate channel",
        f"* Ideal gate PWL rise/fall={gate_transition_ps}ps; no actual control loop/PLL.",
        f'.include "db180_svt018_{corner}.lib"',
        ".temp 27",
        f"VSUP vs 0 {V_SIGNAL}",
        f"VREF vref 0 {V_COMMON}",
        "RTERM pad vref 50",
        f"CPAD pad 0 {PAD_CAP_F:.12g}",
        "E_BUF1 ch1 0 pad 0 1",
        f"RCH1 ch1 rx1 {CHANNEL_R_OHM}",
        f"CCH1 rx1 0 {CHANNEL_C_F:.12g}",
        "E_BUF2 ch2 0 rx1 0 1",
        f"RCH2 ch2 rx {CHANNEL_R_OHM}",
        f"CCH2 rx 0 {CHANNEL_C_F:.12g}",
    ]
    for w in WEIGHTS:
        up = [V_GATE if (c&w) else 0.0 for c in codes]
        dn = [0.0 if (c&w) else V_GATE for c in codes]
        lines += pwl_gate(f"VGU{w}",f"gu{w}",up,gate_transition_ps)
        lines += pwl_gate(f"VGD{w}",f"gd{w}",dn,gate_transition_ps)
        lines += [
            f"XPU{w} vs gu{w} pad 0 nch_svt_1p8v width={wu:.10g}u length={L_UM}u multi={w}",
            f"XPD{w} pad gd{w} 0 0 nch_svt_1p8v width={wd:.10g}u length={L_UM}u multi={w}",
        ]
    end_ns = len(codes)*UI_PS*1e-3
    lines += [
        ".control", "set noaskquit",
        f"tran 4p {end_ns:.9g}n",
        "wrdata tx_waveform.csv time v(pad) v(rx) i(vsup)",
        "quit",".endc",".end",
    ]
    return "\n".join(lines) + "\n"

def parse_wrdata(path: Path) -> list[dict]:
    # ngspice wrdata repeats the time axis between each saved vector.
    records = []
    for line in path.read_text().splitlines():
        try:
            a = [float(z) for z in line.split()]
        except ValueError:
            continue
        if len(a) < 8:
            continue
        if not all(math.isfinite(x) for x in a):
            continue
        # time v(pad), time v(rx), time i(vsup)
        records.append({"time_s":a[0], "pad_V":a[3],
                        "rx_V":a[5], "supply_A":a[7]})
    if len(records) < 500:
        raise RuntimeError(f"Waveform parse produced only {len(records)} rows; inspect {path}")
    return records

def eye_from_transient(rows: list[dict], bits: list[int], field: str) -> dict:
    """PRBS worst-case eye height after optimizing common sampling phase.

    The same method is applied to baseline and FFE. This is *not* BER.
    """
    from bisect import bisect_left
    times = [r["time_s"] for r in rows]
    values = [r[field] for r in rows]
    best = None
    for shift in range(0, 5):
        for frac_step in range(2, 20):  # 0.10 to 0.95 UI
            frac = frac_step / 20.
            hi, lo = [], []
            for n in range(16, len(bits)-6):
                t = (n + shift + frac) * UI_PS * 1e-12
                k = bisect_left(times, t)
                if k < 1 or k >= len(rows):
                    continue
                u = (t-times[k-1])/(times[k]-times[k-1])
                v = values[k-1] + u*(values[k]-values[k-1])
                (hi if bits[n] else lo).append(v)
            if len(hi) < 10 or len(lo) < 10:
                continue
            h = (min(hi)-max(lo))*1000.
            if best is None or h > best["eye_mV"]:
                best = {"eye_mV":h, "sample_delay_UI":shift+frac,
                        "n_hi":len(hi),"n_lo":len(lo)}
    if best is None:
        raise RuntimeError("Eye metric could not be extracted")
    return best

def eye_at_fixed_phase(rows: list[dict], bits: list[int], field: str,
                       delay_UI: float = 1.20) -> float:
    """One physically identical sample phase and latency for both FFE cases."""
    from bisect import bisect_left
    times=[r["time_s"] for r in rows]
    vv=[r[field] for r in rows]
    hi,lo=[],[]
    for n in range(16,len(bits)-6):
        t=(n+delay_UI)*UI_PS*1e-12
        k=bisect_left(times,t)
        if not 0<k<len(rows):continue
        u=(t-times[k-1])/(times[k]-times[k-1])
        sample=vv[k-1]+u*(vv[k]-vv[k-1])
        (hi if bits[n] else lo).append(sample)
    if len(hi)<10 or len(lo)<10:
        raise RuntimeError("Not enough eye samples at common phase")
    return (min(hi)-max(lo))*1e3


def save_csv(path: Path, rows: list[dict]):
    if not rows: return
    with path.open("w", newline="", encoding="utf-8") as f:
        writer=csv.DictWriter(f, fieldnames=list(rows[0]))
        writer.writeheader(); writer.writerows(rows)

def main(out: Path, symbols: int, do_transient: bool):
    out.mkdir(parents=True,exist_ok=True)
    ENGINEDIR=ENGINE_DIR
    ENGINEDIR.mkdir(parents=True, exist_ok=True)
    runner=SpiceRunner(ENGINEDIR / "p3_tx_tests")
    print("Preparing local ngspice model copies for TT/FF/SS/FS/SF ...",flush=True)
    for corner in CORNER_NAMES: model_path(corner)
    # ngspice needs models in the working directory of all generated .cir files
    for corner in CORNER_NAMES:
        src=model_path(corner)
        dest=runner.working/src.name
        if not dest.exists() or src.stat().st_mtime > dest.stat().st_mtime:
            dest.write_bytes(src.read_bytes())
    print("Calibrating 1.8-V SVT NMOS 8:4:2:1 banks to nominal 50 ohms ...",flush=True)
    up=calibrate(runner,"tt",15,"up")
    dn=calibrate(runner,"tt",0,"down")
    wu,wd=up["unit_w_um"],dn["unit_w_um"]
    print(f"Nominal Wunit pullup={wu:.4g}um (R={up['measured_r_ohm']:.3f}), pulldown={wd:.4g}um (R={dn['measured_r_ohm']:.3f})",flush=True)
    rows=[]
    for code in range(16):
        d=runner.dc(code,wu,wd,"tt")
        z=runner.rout(code,wu,wd,"tt")
        z_operating=rout_at_operating_voltage(runner,code,wu,wd,"tt",d["pad_V"])
        rows.append({
          "corner":"tt","temp_C":27,"code":code,"up_fraction":code/15.0,
          "vout_V":d["pad_V"],"ideal_loaded_V":0.125+0.25*code/15.0,
          "rout_ohm_at_vref":z,
          "rout_ohm_at_loaded_operating_point":z_operating,
          "p_signal_supply_mW":max(0,-d["driver_supply_A"]*V_SIGNAL*1e3),
        })
    save_csv(out/"tt_code_sweep.csv",rows)
    variation=[]
    for corner in CORNER_NAMES:
        for temp in (27.0,): # corner variation (temperature held constant)
            for code in (0,3,7,12,15):
                d=runner.dc(code,wu,wd,corner,temp_c=temp)
                z=runner.rout(code,wu,wd,corner,temp_c=temp)
                variation.append({
                 "corner":corner,"temp_C":temp,"v_signal_V":V_SIGNAL,"code":code,
                 "vout_V":d["pad_V"],"rout_ohm_at_vref":z,
                 "p_signal_supply_mW":max(0,-d["driver_supply_A"]*V_SIGNAL*1e3),
                })
    save_csv(out/"pvt_corner_sweep.csv",variation)
    for temp in (-20.0,85.0):
        for code in (0,7,15):
            d=runner.dc(code,wu,wd,"tt",temp_c=temp)
            z=runner.rout(code,wu,wd,"tt",temp_c=temp)
            variation.append({"corner":"tt","temp_C":temp,"v_signal_V":V_SIGNAL,"code":code,
                "vout_V":d["pad_V"],"rout_ohm_at_vref":z,
                "p_signal_supply_mW":max(0,-d["driver_supply_A"]*V_SIGNAL*1e3)})
    # +/-10% on the separate 0.5-V SIGNAL supply. Core gate VDD remains 1.8 V.
    # VREF and the incremental-resistance clamp track VS/2.
    for supply in (0.45, 0.55):
        for code in (0, 7, 15):
            d=runner.dc(code,wu,wd,"tt",temp_c=27.0,v_signal=supply)
            z=runner.rout(code,wu,wd,"tt",temp_c=27.0,v_signal=supply)
            variation.append({"corner":"tt","temp_C":27.0,"v_signal_V":supply,
                "code":code,"vout_V":d["pad_V"],
                "rout_ohm_at_vref":z,
                "p_signal_supply_mW":max(0,-d["driver_supply_A"]*supply*1e3)})
    save_csv(out/"pvt_corner_sweep.csv",variation)
    rvals=[x["rout_ohm_at_vref"] for x in rows]
    rop=[x["rout_ohm_at_loaded_operating_point"] for x in rows]
    vout=[x["vout_V"] for x in rows]
    actual_lsb=(vout[-1]-vout[0])/15.
    dnl = [(vout[i+1]-vout[i])/actual_lsb-1 for i in range(15)]
    inl = [((v-vout[0])/actual_lsb-i) for i,v in enumerate(vout)]
    res={
       "status":"reconstructed_nmos_driver_simulated",
       "source":"P3 Wong et al. Fig.7 architecture (NOT exact transistor schematic)",
       "method":"DB HiTek 0.18 um 1.8-V SVT NMOS ngspice-42; local HSPICE-compatible copy",
       "model_assumptions":{
          "v_core_gate_V":V_GATE,"v_signal_V":V_SIGNAL,"v_common_V":V_COMMON,
          "r_load_ohm":R_TERM,"channel":"two buffered RC poles with -12 dB at 1.8GHz",
          "driver":"8:4:2:1 binary banks with complementary NMOS pullup/pulldown",
          "width_calibration":"TT @ 27 C, no published impedance feedback loop",
          "driver_supply_power_only":True,
          "voltage_sweep":"0.45/0.50/0.55 V 0.5-V signaling supply at TT 27C, with core gate 1.8 V fixed",
          "excluded":["P3 exact predriver/slew loop","actual impedance feedback","true PCB/RG58 S-parameters","PLL/CDR","RX comparator","full transceiver power","extracted parasitics"],
       },
       "calibration":{"up":up,"down":dn},
       "tt_code_sweep":{
        "code_count":16,"rout_min_ohm":min(rvals),"rout_max_ohm":max(rvals),
        "rout_mean_ohm":sum(rvals)/len(rvals),
        "rout_loaded_operating_min_ohm":min(rop),
        "rout_loaded_operating_max_ohm":max(rop),
        "rout_loaded_operating_mean_ohm":sum(rop)/len(rop),
        "output_min_V":min(vout),"output_max_V":max(vout),
        "actual_loaded_swing_mVpp":(vout[-1]-vout[0])*1e3,
        "actual_endpoint_lsb_mV":actual_lsb*1e3,
        "dnl_max_abs_LSB":max(abs(x) for x in dnl),
        "inl_max_abs_LSB":max(abs(x) for x in inl),
        "dnl_LSB":dnl
       },
       "ngspice_invocations":runner.calls,
       "unrecognized_hspice_model_params":sorted(runner.warning_types),
       "comparison":{"paper_fig10_impedance_ohm":"roughly 47.5 to 50.7 across alpha with feedback",
                     "paper_fig25_eye":"37 mV x 189 ps, alpha=0.30; measured",
                     "paper_total_power_mW":27.12,
                     "important":"The reconstruction has different PDK, bias, sizing and no real feedback; do NOT claim equivalence."}
    }
    if do_transient:
        bits=prbs7(symbols)
        modes={}
        for name,alpha in (("baseline",0.0),("ffe_alpha_0p30",ALPHA)):
            codes=ffe_codes(bits,alpha)
            deck=make_transient(codes,wu,wd)
            wdpath=runner.working
            txt=runner.run(deck,f"tran_{name}")
            wave=wdpath/"tx_waveform.csv"
            samples=parse_wrdata(wave)
            save_csv(out/f"{name}_mos_tx_rx.csv",samples)
            pad=eye_from_transient(samples,bits,"pad_V")
            rx=eye_from_transient(samples,bits,"rx_V")
            supply=[max(0,-v["supply_A"]*V_SIGNAL*1e3) for v in samples]
            modes[name]={"pad_eye":pad,"rx_eye":rx,
                         "driver_signal_supply_mean_mW":sum(supply)/len(supply),
                         "rx_eye_at_common_1p20_UI_mV":eye_at_fixed_phase(samples,bits,"rx_V",1.20),
                         "waveform_rows":len(samples),"discrete_codes":sorted(set(codes))}
            print(f"Transient {name}: RX Eye {rx['eye_mV']:.3f}mV, {len(samples)} points",flush=True)
        res["transient"]=modes
    res["ngspice_invocations"]=runner.calls
    (out/"driver_summary.json").write_text(json.dumps(res,indent=2)+"\n")
    print("P3 reconstructed segmented driver results:",json.dumps({
      "nominal_r_ohm":res["tt_code_sweep"]["rout_mean_ohm"],
      "min_r_ohm":res["tt_code_sweep"]["rout_min_ohm"],
      "max_r_ohm":res["tt_code_sweep"]["rout_max_ohm"],
      "dnl_max_abs_LSB":res["tt_code_sweep"]["dnl_max_abs_LSB"],
      "calls":runner.calls,"has_transient":bool(res.get("transient"))},indent=2),flush=True)

if __name__ == "__main__":
    ap=argparse.ArgumentParser()
    ap.add_argument("--out",type=Path,default=DEFAULT_OUT)
    ap.add_argument("--symbols",type=int,default=128)
    ap.add_argument("--skip-transient",action="store_true")
    args=ap.parse_args()
    main(args.out,args.symbols,not args.skip_transient)
