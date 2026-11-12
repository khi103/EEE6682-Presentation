#!/usr/bin/env python3
"""Diagnose sampled-data DFF U state caused by physical-clock ADC selection.

Previously measured:
  - physical clkeven voltage traverses 0.006–1.82V in a complete MOS trace
  - digital RX ADC mostly yields valid logic, E0 DFF clocked by ring n1
    yields known 0/1 ~93% of active time
  - D0 DFF clocked by ADC(dclke) yields digital-U 100% of time,
    causing XOR up/down outputs to be permanently U
  - attaching a DAC probe directly to dclke causes ngspice to stop early

Control experiment: change ONLY D0 sample DFF clock:
  'original': digital ADC(clkeven) (unmodified)
  'ring': digital ADC(n1) (diagnostic, not a valid BBPD phase allocation)
  'ring_inv': digital inverter of ADC(n1) (approximate inverted physical
              n1, may also differ in analogue propagation delay).

These are diagnosis-only; a valid Wong et al. Fig19 dual-loop CDR has
NOT been created. Clock switch does not change physical MOS PLL or TX.
"""
from __future__ import annotations
import argparse,json,shutil
from pathlib import Path
import p3_xspice_one_stage_probe as PROBE
import p3_xspice_4xor_mos_cdr as FOUR
import p3_transistor_driver as TX

MODES=("original","ring","ring_inv")
PHASES=(-.05,.95)
DFF_ORIGINAL="ADAT0 drx dclke dzero dzero dD0 dD0b sampled"

def new_deck(bits,mode,shift):
    d,start=PROBE.raw_deck(bits,"dD0",shift)
    if d.count(DFF_ORIGINAL)!=1:raise RuntimeError("Data DFF clock wiring not uniquely located")
    if mode=="ring":
        d=d.replace(DFF_ORIGINAL,"ADAT0 drx dn1 dzero dzero dD0 dD0b sampled",1)
    if mode=="ring_inv":
        d=d.replace(DFF_ORIGINAL,"ADAT0 drx dn1bar dzero dzero dD0 dD0b sampled",1)
        extra=[
          "ACLKCOMPL dn1 dn1bar data_clock_complement",
          ".model data_clock_complement d_inverter(rise_delay=8e-12 fall_delay=8e-12)",
        ]
        d=d.replace(".control","\n".join(extra)+"\n.control",1)
    return d,start

def run(out,mode,shift):
    if mode not in MODES or shift not in PHASES:raise ValueError
    out.mkdir(parents=True,exist_ok=True)
    label=f"{mode}_phase_{shift:+.2f}".replace("+","plus").replace("-","minus").replace(".","p")
    work=TX.ENGINE_DIR/("p3_DFFclock_diagnostic_"+label)
    engine=TX.SpiceRunner(work)
    src=TX.model_path("tt");dst=work/src.name
    if not dst.exists() or src.stat().st_mtime>dst.stat().st_mtime:shutil.copy2(src,dst)
    result={"D0_sample_digital_clock_source":mode,
      "phase_UI":shift,"test_only_not_correct_2004_BBPD":True}
    try:
        deck,start=new_deck(FOUR.prbs31(256),mode,shift)
        log=engine.run(deck,label)
        result["SPICE_errors"]=[s for s in log.splitlines()
               if any(k in s.lower() for k in ("timestep too small","tran simulation(s) aborted","error:"))][-15:]
        result.update(PROBE.read_probe(work/"single_stage.csv",start))
        result["status"]="ran"
    except Exception as e:
        result.update({"status":"failed",
              "error":f"{type(e).__name__}: {str(e)[-1400:]}"})
    (out/f"{label}.json").write_text(json.dumps(result,indent=2)+"\n")
    print(f"DFF_CLOCK_ROOT mode={mode} shift_UI={shift:+.2f} "
          f"status={result['status']} "
          f"last_ns={result.get('last_time_ns')} "
          f"valid_data_window={result.get('full_serial_data_interval_executed')} "
          f"U={result.get('digital_undefined_fraction')} "
          f"zero={result.get('digital_zero_fraction')} "
          f"one={result.get('digital_one_fraction')}",flush=True)
    return result

if __name__=="__main__":
    p=argparse.ArgumentParser()
    p.add_argument("--mode",choices=MODES,required=True)
    p.add_argument("--shift",type=float,choices=PHASES,required=True)
    p.add_argument("--out",type=Path,default=Path("results/spice/p3_DFF_clock_root"))
    a=p.parse_args()
    run(a.out,a.mode,a.shift)
