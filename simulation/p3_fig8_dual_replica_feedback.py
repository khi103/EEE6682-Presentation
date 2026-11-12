#!/usr/bin/env python3
"""Fig.8-INFORMED dual-replica PVT calibration (hybrid ngspice/Python).

Two *physical DB HiTek NMOS* replica networks are sensed with ngspice:
all pull-up code 15 and all pull-down code 0. A six-bit successive
approximation controller implemented in Python trims their effective
parallel transistor finger width INDEPENDENTLY toward a 50-ohm reference.
Both loops are closed over actual ngspice MOS solves, but the controller
and width-control actuator are idealized abstractions.

IMPORTANT: Not the exact Fig.8 of Wong et al., JSSC 2004. That figure
uses analogue feedback to predriver supply and VG, an off-chip resistor,
and a transistor regulator. We have a hybrid digital calibration of
width, NOT that analogue circuitry.
"""
from pathlib import Path
import json, csv, argparse, shutil, math
import p3_transistor_driver as TX

BASE_SCALE=.65
MAX_SCALE=1.50
MAX_CODE=63
TARGET_OHM=50.0
TEST_CODES=tuple(range(16))

def scale(code):
    return BASE_SCALE+(MAX_SCALE-BASE_SCALE)*code/MAX_CODE

def servo(run, corner, wu,wd,side, rounds=7):
    """SAR on width code; actual ngspice replica's incremental R."""
    assert side in ("up","down")
    ref_code=15 if side=="up" else 0
    lo,hi=0,MAX_CODE
    history=[]
    cache={}
    def measure(c):
        if c not in cache:
            wu2=wu*scale(c) if side=="up" else wu
            wd2=wd*scale(c) if side=="down" else wd
            cache[c]=run.rout(ref_code,wu2,wd2,corner)
        r=cache[c]
        history.append({"step":len(history)+1,"trim_code":c,
                        "width_scale":scale(c),"replica_r_ohm":r,
                        "error_ohm":r-TARGET_OHM})
        return r
    for k in range(rounds):
        m=(lo+hi)//2
        r=measure(m)
        if r>TARGET_OHM: lo=min(MAX_CODE,m+1)
        else: hi=max(0,m-1)
        if lo>hi:break
    for c in (0,MAX_CODE,lo,hi,lo-1,lo+1,hi-1,hi+1):
        if 0<=c<=MAX_CODE and c not in cache:measure(c)
    best=min(cache, key=lambda c:abs(cache[c]-TARGET_OHM))
    return {"side":side,"best_code":best,"scale":scale(best),
            "replica_r_ohm":cache[best],"history":history,
            "within_3percent":abs(cache[best]-TARGET_OHM)<1.5}

def main(out):
    out.mkdir(parents=True,exist_ok=True)
    base=json.loads((out/"driver_summary.json").read_text())
    wup=float(base["calibration"]["up"]["unit_w_um"])
    wdn=float(base["calibration"]["down"]["unit_w_um"])
    work=TX.ENGINE_DIR/"p3_fig8_replicas"
    work.mkdir(parents=True,exist_ok=True)
    runner=TX.SpiceRunner(work)
    for corner in TX.CORNER_NAMES:
        p=TX.model_path(corner)
        q=work/p.name
        if not q.exists() or p.stat().st_mtime>q.stat().st_mtime:
            shutil.copy2(p,q)
    all_rows=[]
    history=[]
    summary={}
    for corner in TX.CORNER_NAMES:
        up=servo(runner,corner,wup,wdn,"up")
        down=servo(runner,corner,wup,wdn,"down")
        wu_cal=wup*up["scale"]
        wd_cal=wdn*down["scale"]
        summary[corner]={"up":up,"down":down}
        for side,data in (("up",up),("down",down)):
            history.extend({"corner":corner,"side":side,**x} for x in data["history"])
        for code in TEST_CODES:
            orig=runner.dc(code,wup,wdn,corner)
            fixed_r=TX.rout_at_operating_voltage(runner,code,wup,wdn,corner,orig["pad_V"])
            changed=runner.dc(code,wu_cal,wd_cal,corner)
            fixed_mid=runner.rout(code,wup,wdn,corner)
            cal_mid=runner.rout(code,wu_cal,wd_cal,corner)
            actual_r=TX.rout_at_operating_voltage(runner,code,wu_cal,wd_cal,corner,changed["pad_V"])
            all_rows.append({
              "corner":corner,"code":code,
              "up_trim_code":up["best_code"],"down_trim_code":down["best_code"],
              "up_scale":up["scale"],"down_scale":down["scale"],
              "untrimmed_rout_at_loaded_pad_ohm":fixed_r,
              "trimmed_rout_at_loaded_pad_ohm":actual_r,
              "untrimmed_rout_at_vref_ohm":fixed_mid,
              "trimmed_rout_at_vref_ohm":cal_mid,
              "untrimmed_output_V":orig["pad_V"],"trimmed_output_V":changed["pad_V"],
              "trimmed_signal_supply_power_mW":max(0,-changed["driver_supply_A"]*.5*1e3)
            })
        print(f"{corner.upper()} Fig8-inspired: pullup trim={up['best_code']:2d} Rout={up['replica_r_ohm']:.3f}; "
              f"pulldown trim={down['best_code']:2d} Rout={down['replica_r_ohm']:.3f}",flush=True)
    with (out/"fig8_dual_replica_feedback.csv").open("w",newline="") as f:
        w=csv.DictWriter(f,fieldnames=list(all_rows[0]))
        w.writeheader();w.writerows(all_rows)
    with (out/"fig8_feedback_servo_history.csv").open("w",newline="") as f:
        w=csv.DictWriter(f,fieldnames=list(history[0]))
        w.writeheader();w.writerows(history)
    measures={}
    for corner in TX.CORNER_NAMES:
        r=[x for x in all_rows if x["corner"]==corner]
        measures[corner]={
          "pullup_replica_r_ohm":summary[corner]["up"]["replica_r_ohm"],
          "pulldown_replica_r_ohm":summary[corner]["down"]["replica_r_ohm"],
          "loaded_r_ohm_min":min(x["trimmed_rout_at_loaded_pad_ohm"] for x in r),
          "loaded_r_ohm_max":max(x["trimmed_rout_at_loaded_pad_ohm"] for x in r),
          "mean_abs_loaded_r_error_before_percent":sum(abs(x["untrimmed_rout_at_loaded_pad_ohm"]-50) for x in r)/len(r)*2,
          "mean_abs_loaded_r_error_after_percent":sum(abs(x["trimmed_rout_at_loaded_pad_ohm"]-50) for x in r)/len(r)*2
        }
    result={
      "status":"simulated_fig8_inspired_dual_mos_replica_digital_calibration",
      "architecture":"two ngspice MOS replica networks (full 15-finger pull-up / pull-down), two Python SAR width trim controllers, shared trim codes",
      "not_actual_fig8_feedback":True,
      "trim_resolution_bits":6,"trim_range_scales":[BASE_SCALE,MAX_SCALE],
      "corners":list(TX.CORNER_NAMES),"ngspice_runs":runner.calls,
      "target_r_ohm":TARGET_OHM,
      "per_corner":measures,
      "limitations":[
        "Fig.8 actual opamp/current source/pre-driver PVDD and NMOS VG control are not instantiated as MOS circuits",
        "The digital width tuning is an abstract actuator; no physical bank decoder/transistor gate delay",
        "Replica uses only full-up/full-down codes; residual voltage-dependent Rout remains",
        "Not original 2004 process, layout or extracted parasitics",
        "ngspice ignores some HSPICE proprietary BSIM options"
      ]
    }
    (out/"fig8_dual_replica_feedback.json").write_text(json.dumps(result,indent=2)+"\n")
    assert len(all_rows)==80
    assert len(history)>=40
    assert all(math.isfinite(x["trimmed_rout_at_loaded_pad_ohm"]) for x in all_rows)
    print("PASS: 5-corner dual-replica closed-loop digital calibration, 16-code sweep",flush=True)
    return result

if __name__=="__main__":
    ap=argparse.ArgumentParser()
    ap.add_argument("--out",type=Path,default=TX.DEFAULT_OUT)
    main(ap.parse_args().out)
