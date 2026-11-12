#!/usr/bin/env python3
"""P3 Fig8-inspired ANALOG integral replica feedback (not exact paper).

Two DB HiTek 1.8-V NMOS replica resistor-divider branches compare 0.25 V
against 0.5-V source and 50-ohm external references. Each feedback integrator
is an ngspice behavioral B-current source + ideal C, with a limited-voltage
driver (B-source). MOS reference paths are physical PDK devices.

It mimics Fig8's SEPARATE pull-up and pull-down feedback intent but NOT its
actual opamp/regulator topology, PVDD/VG generations, sizing, or closed-loop
impedance tracking at all PAD voltages.
"""
from pathlib import Path
import argparse,csv,json,math,shutil
import p3_transistor_driver as TX

WUNIT=1.4896875*1.30
V_SIGNAL=.5
VREF=.25
V_GATE_MAX=1.8
V_GATE_MIN=.75
N_UNIT=15
GAIN=2e-4
CAP=1e-12

def deck(corner):
    return "\n".join([
     "* Reconstructed Fig8-inspired dual analog servo + physical MOS replicas",
     f'.include "db180_svt018_{corner}.lib"',
     ".temp 27",
     "VSUP vs 0 0.5",
     "VREF ref 0 0.25",
     "VBIAS vbias 0 1.15",
     "* Pull-up: NMOS VS to n_up -> off-chip 50-ohm reference to GND",
     "RUPREF n_up 0 50",
     f"XREP_UP vs gup n_up 0 nch_svt_1p8v width={WUNIT:.8g}u length=0.18u multi={N_UNIT}",
     "* Pull-down: 50 ohm between VS and n_down, NMOS n_down to GND",
     "RDOWNREF vs n_down 50",
     f"XREP_DN n_down gdn 0 0 nch_svt_1p8v width={WUNIT:.8g}u length=0.18u multi={N_UNIT}",
     "* Opposite servo polarities: Vup rises with gate V, Vdown falls with gate V",
     f"BERRUP  ctrlup 0 I = {{ {GAIN:.8g}*(v(n_up)-{VREF}) }}",
     f"BERRDN  ctrldn 0 I = {{ -{GAIN:.8g}*(v(n_down)-{VREF}) }}",
     f"CUP     ctrlup 0 {CAP:.8g} ic=1.15",
     f"CDN     ctrldn 0 {CAP:.8g} ic=1.15",
     "RLEAKUP ctrlup vbias 1000meg",
     "RLEAKDN ctrldn vbias 1000meg",
     f"BGUP gup 0 V = {{ min(max(v(ctrlup),{V_GATE_MIN}),{V_GATE_MAX}) }}",
     f"BGDN gdn 0 V = {{ min(max(v(ctrldn),{V_GATE_MIN}),{V_GATE_MAX}) }}",
     ".ic v(ctrlup)=1.15 v(ctrldn)=1.15",
     ".control","set noaskquit",
     "tran 100p 160n uic",
     "wrdata analog_servo.csv time v(n_up) v(n_down) v(gup) v(gdn)",
     "quit",".endc",".end",""
    ])

def parse(path):
    rr=[]
    for line in path.read_text().splitlines():
        try: a=[float(x) for x in line.split()]
        except ValueError: continue
        if len(a)<10 or not all(math.isfinite(x) for x in a):continue
        rr.append({"time_ns":a[0]*1e9,
                   "up_replica_V":a[3],
                   "down_replica_V":a[5],
                   "up_gate_V":a[7],
                   "down_gate_V":a[9]})
    if len(rr)<100:raise RuntimeError("No usable ngspice closed-loop waveform")
    return rr

def run(out):
    out.mkdir(parents=True,exist_ok=True)
    work=TX.ENGINE_DIR/"p3_fig8_analog"
    runner=TX.SpiceRunner(work)
    for corner in TX.CORNER_NAMES:
        src=TX.model_path(corner)
        cp=work/src.name
        if not cp.exists() or src.stat().st_mtime>cp.stat().st_mtime:
            shutil.copy2(src,cp)
    data=[];results={}
    for corner in TX.CORNER_NAMES:
        runner.run(deck(corner),f"analog_loop_{corner}")
        trace=parse(work/"analog_servo.csv")
        data.extend({"corner":corner,**r} for r in trace)
        final=trace[-1]
        up=final["up_replica_V"]
        down=final["down_replica_V"]
        rup=50*(V_SIGNAL/up-1) if up>0 else float("inf")
        rdn=50*down/(V_SIGNAL-down) if down<V_SIGNAL else float("inf")
        results[corner]={
          "final_up_reference_V":up,
          "final_down_reference_V":down,
          "final_up_gate_V":final["up_gate_V"],
          "final_down_gate_V":final["down_gate_V"],
          "inferred_pullup_R_ohm":rup,
          "inferred_pulldown_R_ohm":rdn,
          "deviation_up_reference_mV":(up-VREF)*1e3,
          "deviation_down_reference_mV":(down-VREF)*1e3,
          "gate_up_rail_limited":final["up_gate_V"]>=V_GATE_MAX-1e-3,
          "gate_down_rail_limited":final["down_gate_V"]>=V_GATE_MAX-1e-3,
        }
        print(f"{corner.upper()}: dual PDK MOS replica up/dn -> {up:.4f}/{down:.4f} V,"
              f" implied R={rup:.2f}/{rdn:.2f} ohm",flush=True)
    with (out/"fig8_analog_servo_waveforms.csv").open("w",newline="") as f:
        writer=csv.DictWriter(f,fieldnames=list(data[0]))
        writer.writeheader();writer.writerows(data)
    output={
      "status":"executed_behavioral_integrator_closing_real_MOS_replica_loop",
      "ngspice_calls":runner.calls,
      "mos_device":"DB HiTek 1.8V SVT NMOS, TT/FF/SS/FS/SF",
      "servo":"ideal B-source continuous-time feedback integrator and limited gate voltage",
      "external_reference_ohm":50.,
      "reference_target_V":.25,
      "not_original_fig8":True,
      "results":results,
      "limitations":[
       "Not paper's physical opamps/LDO, PVDD and VG controls",
       "Chosen finger width 1.30x TT calibration is not published sizing",
       "Two replica paths are not integrated with active 16-code output driver",
       "No loop stability/noise or convergence spec comparable to original paper"
      ]
    }
    (out/"fig8_analog_servo_summary.json").write_text(json.dumps(output,indent=2)+"\n")
    print("PASS: ngspice simulated analog B-source servo connected to MOS replicas",flush=True)
    return output

if __name__=="__main__":
    ap=argparse.ArgumentParser()
    ap.add_argument("--out",type=Path,default=TX.DEFAULT_OUT)
    run(ap.parse_args().out)
