#!/usr/bin/env python3
"""P3 Fig18/20-inspired FUNCTIONAL PLL using actual MOS charge-pump I-code LUT.

The transistor-level current DAC of p3_fig20_charge_pump_mos.py supplies
I(code) at VCTRL=.9V. A separately assumed 450MHz PFD, first-order
ideal PFD current (100uA*sin(error)), R-C loop filter and linear VCO
(Kvco=0.5GHz/V) then evolve phase/frequency numerically.

This is not a PDK transistor VCO/PFD, the original dual-loop PLL,
450-MHz switched-capacitor ripple filter, real VCO jitter or recovered
3.6-Gb/s data. Lock proves this assumed behavioral loop can regulate
itself when driven by the reconstructed MOS current LUT.
"""
from pathlib import Path
import argparse,csv,json,math
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

FREF=450e6
FDES=1.8e9
N=4
KVCO=0.5e9
C_FILT=200e-12
R_FILT=2000.0
I_PFD=100e-6
DAC_PULSE_DUTY=.10
STEPS=6500
TEST_CODES=(0,32,63,96,127)

def load(out):
    with (out/"fig20_mos_charge_pump_current.csv").open(newline="") as f:
        rr=list(csv.DictReader(f))
    mapping={int(r["seven_bit_code"]):float(r["pump_clamp_current_A"])
             for r in rr if r["corner"]=="tt"}
    if len(mapping)!=128:raise RuntimeError("Missing physical MOS current code(s)")
    return mapping

def simulate(code, table):
    dt=1/FREF
    phase=.2
    v_int=.88
    v_out=.88
    rows=[]
    for n in range(STEPS):
        f=FDES+KVCO*(v_out-.9)
        phase=(phase+2*math.pi*(1-f/(N*FREF))+math.pi)%(2*math.pi)-math.pi
        delta_i=(table[code]-table[63])*DAC_PULSE_DUTY
        i=I_PFD*math.sin(phase)+delta_i
        v_int=float(np.clip(v_int+dt*i/C_FILT,.7,1.1))
        v_out=float(np.clip(v_int+R_FILT*i,.7,1.1))
        rows.append({"mos_charge_pump_code":code,"step":n,
                     "time_us":n*dt*1e6,"phase_error_rad":phase,
                     "phase_error_ps_at_450MHz":phase/(2*math.pi*FREF)*1e12,
                     "frequency_GHz":f/1e9,"vctrl_V":v_out,
                     "filtered_pump_current_uA":i*1e6})
    tail=rows[-750:]
    residual=float(np.std([x["phase_error_rad"] for x in tail]))
    return rows,{
       "control_code":code,"final_phase_error_rad":float(np.mean([x["phase_error_rad"] for x in tail])),
       "final_phase_error_ps_at_450MHz":float(np.mean([x["phase_error_ps_at_450MHz"] for x in tail])),
       "phase_std_rad_last_750_steps":residual,
       "nominal_frequency_GHz":float(np.mean([x["frequency_GHz"] for x in tail])),
       "behavioral_lock":residual<0.01}

def main(out):
    out.mkdir(parents=True,exist_ok=True)
    table=load(out)
    rows=[]
    lock={}
    for code in TEST_CODES:
        r,s=simulate(code,table)
        rows.extend(r)
        lock[str(code)]=s
        print(f"code={code} Phase mean={s['final_phase_error_ps_at_450MHz']:.3f}ps "
              f"std={s['phase_std_rad_last_750_steps']:.6f} rad, locked={s['behavioral_lock']}",flush=True)
    with (out/"fig18_20_functional_pll_mos_lut.csv").open("w",newline="") as f:
        w=csv.DictWriter(f,fieldnames=list(rows[0]))
        w.writeheader();w.writerows(rows)
    metrics={
      "status":"behavioral_PLL_lock_from_transistor_MOS_charge_pump_current_LUT",
      "simulator":"Python loop using ngspice-extracted MOS current-code LUT, NOT PLL transistor-level",
      "reference_MHz":450, "vco_nominal_GHz":1.8,"divide_N":4,
      "assumed_Kvco_GHz_per_V":KVCO/1e9,
      "assumed_pfd_peak_current_uA":I_PFD*1e6,
      "assumed_filter_R_ohm":R_FILT, "assumed_filter_C_pF":C_FILT*1e12,
      "assumed_code_current_pulse_duty":DAC_PULSE_DUTY,
      "controller":"sinusoidal phase-error current, PI-like R-C charge-pump filter",
      "conditions":lock,
      "limitations":[
          "Physical MOS 7-bit charge-pump currents only measured at fixed VCTRL=0.9V",
          "No MOS PFD, VCO, PLL reference buffer or switched capacitor filter",
          "Not the original dual-loop charge-pump mismatch phase shifter",
          "No transistor-level jitter, 1.8GHz clock waveform, 4-phase data sampling, CDR or BER",
          "Final phase from assumed ideal 450MHz divided loop must not be compared directly with measured Fig21 350ps phase range"
      ]}
    (out/"fig18_20_functional_pll_mos_lut.json").write_text(json.dumps(metrics,indent=2)+"\n")
    fig,ax=plt.subplots(figsize=(9.2,5.2),layout="constrained")
    for code in TEST_CODES:
        rr=[r for r in rows if r["mos_charge_pump_code"]==code]
        stepsize=8
        ax.plot([x["time_us"] for x in rr[::stepsize]],
                [x["phase_error_ps_at_450MHz"] for x in rr[::stepsize]],
                label=f"Code {code}")
    ax.set(xlabel="Time (µs)",ylabel="Reference-phase error equivalent (ps)",
           title="Assumed PLL with measured MOS charge-pump current LUT")
    ax.grid(alpha=.25);ax.legend(ncol=2)
    fig.savefig(out/"fig18_20_behavioral_pll_lock.png",dpi=175)
    plt.close(fig)
    assert all(x["behavioral_lock"] for x in lock.values())
    print("PASS: Assumed functional PLL locks in five MOS-pump-code conditions",flush=True)
    return metrics

if __name__=="__main__":
    p=argparse.ArgumentParser()
    p.add_argument("--out",type=Path,default=Path("results/spice/p3_fig20_charge_pump"))
    main(p.parse_args().out)
