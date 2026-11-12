#!/usr/bin/env python3
"""P3 Fig20-inspired physical 7-bit charge-pump current-DAC test.

NMOS base sink, 7 binary-weighted NMOS sink fingers and a PMOS pull-up
current source use the actual DB HiTek 0.18-um 1.8-V SVT MOS models.
The output VCO control node is held at 0.9 V by an IDEAL test source,
so only STATIC current-code linearity and corner sensitivity are tested.

NOT the original Wong Fig20 exact transistor circuit, switched PLL,
VCO, phase transfer, filter or phase-lock measurement. The paper's
measured 7-bit phase shift / DNL cannot be inferred from this current
DAC without VCO gain and feedback-loop dynamics.
"""
from pathlib import Path
import argparse,csv,json,math,shutil
import p3_transistor_driver as TX

WIDTH_PU_UM=10.0
WIDTH_DN_BASE_UM=12.0
WIDTH_DN_UNIT_UM=.36
L_UM=.36
BIAS_P=.95
BIAS_DN_BASE=.64
BIAS_DN_TRIM=.50
BINARY=(1,2,4,8,16,32,64)
CORNERS=TX.CORNER_NAMES

def circuit(corner,code):
    gate_on=BIAS_DN_TRIM
    a=[
       "* Fig20-inspired 7-bit MOS charge-pump DAC, DC only",
       f'.include "db180_svt018_{corner}.lib"',
       ".temp 27",
       "VDD vdd 0 1.8",
       "VCTRL control 0 .9",
       f"VBIASP gbp 0 {BIAS_P}",
       f"VBIASN gbn 0 {BIAS_DN_BASE}",
       f"XPU control gbp vdd vdd 0 pch_svt_1p8v width={WIDTH_PU_UM}u length={L_UM}u multi=1",
       f"XDNBASE control gbn 0 0 nch_svt_1p8v width={WIDTH_DN_BASE_UM}u length={L_UM}u multi=1",
    ]
    for weight in BINARY:
        val=gate_on if code & weight else 0.0
        a += [
           f"VG{weight} g{weight} 0 {val}",
           f"XDAC{weight} control g{weight} 0 0 nch_svt_1p8v width={WIDTH_DN_UNIT_UM}u length={L_UM}u multi={weight}"
        ]
    return "\n".join(a+[".control","set noaskquit","op","print i(vctrl) i(vdd)","quit",".endc",".end",""])

def run(out):
    out.mkdir(parents=True,exist_ok=True)
    work=TX.ENGINE_DIR/"p3_fig20_pump"
    runner=TX.SpiceRunner(work)
    for corner in CORNERS:
        src=TX.model_path(corner)
        dest=work/src.name
        if not dest.exists() or src.stat().st_mtime>dest.stat().st_mtime:
            shutil.copy2(src,dest)
    data=[]
    for corner in CORNERS:
        codes=range(128) if corner=="tt" else (0,1,3,15,31,63,127)
        for code in codes:
            txt=runner.run(circuit(corner,code),f"cp_{corner}_{code:03d}")
            data.append({
              "corner":corner,"seven_bit_code":code,
              "control_voltage_V":.9,
              "pump_clamp_current_A":TX.spice_vector(txt,"i(vctrl)"),
              "vdd_supply_current_A":-TX.spice_vector(txt,"i(vdd)")
            })
        print(f"{corner}: charge-pump MOS code sweep {len(codes)} points",flush=True)
    with (out/"fig20_mos_charge_pump_current.csv").open("w",newline="") as f:
        w=csv.DictWriter(f,fieldnames=list(data[0]))
        w.writeheader();w.writerows(data)
    tt=sorted([x for x in data if x["corner"]=="tt"],key=lambda x:x["seven_bit_code"])
    current=[x["pump_clamp_current_A"] for x in tt]
    steps=[b-a for a,b in zip(current,current[1:])]
    delta=(current[-1]-current[0])/127
    max_dnl=max(abs(x/delta-1) for x in steps) if delta else float("inf")
    metrics={
       "status":"simulated_fig20_inspired_7bit_mos_pump_current_dac",
       "simulator":"ngspice 42 + DB HiTek 180nm SVT MOS, static 0.9V VCO control voltage",
       "ngspice_runs":runner.calls,
       "tt_current_endpoints_A":[current[0],current[-1]],
       "current_code_slope_A_per_LSB":delta,
       "max_abs_current_code_DNL_LSB":max_dnl,
       "is_code_current_monotonic":all(x*delta>0 for x in steps),
       "simulated_corners":CORNERS,
       "limitations":[
         "No physical PFD, UP/DN pulse width, loop filter, charge-pump switches or PLL/VCO",
         "Measured Fig21 phase-shift linearity cannot be inferred from this static current-DAC",
         "MOS widths and gate bias are assumed, not extracted from the paper",
         "No HSPICE/Spectre numerical correlation yet; nanosecond transient switching not tested",
       ]
    }
    (out/"fig20_mos_charge_pump_current.json").write_text(json.dumps(metrics,indent=2)+"\n")
    print("Charge pump summary:",json.dumps(metrics,indent=2),flush=True)
    assert len(tt)==128 and runner.calls>=156
    print("PASS: Actual MOS transistor charge-pump DC code sweep completed (not PLL)",flush=True)
    return metrics

if __name__=="__main__":
    a=argparse.ArgumentParser()
    a.add_argument("--out",type=Path,default=Path("results/spice/p3_fig20_charge_pump"))
    run(a.parse_args().out)
