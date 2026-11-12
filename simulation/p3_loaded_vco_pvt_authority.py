#!/usr/bin/env python3
"""Check physical MOS VCO tuning authority across all five foundry corners.

The existing P3 mixed-signal PLL is used as a LOADED VCO testbench, but
its VCO gate bias is swept with explicit ideal DC sources in place of
the normal PLL filter-derived B-sources. This intentionally breaks
feedback only during this standalone VCO control-authority test.

It distinguishes 'not enough VCO tuning range in FS' from 'PLL cannot
acquire a reachable frequency'. A possible frequency is NOT a locked
closed-loop PLL, and the device topology is not the 2004 original.
"""
from __future__ import annotations
import argparse,csv,json,math,re,shutil
from pathlib import Path
import p3_transistor_driver as TX
import p3_xspice_physical_mos_pll as PLL

CORNERS=("tt","ff","ss","fs","sf")
BIAS=(.65,.75,.85,.95,1.05,1.15,1.3,1.45,1.65)
SIM_NS=80.

def deck(corner,bias):
    d=PLL.circuit(63,corner=corner,initial_bias=.96)
    a="BNB nb 0 V={min(max(v(vcobias),.65),1.65)}"
    b="BPB pb 0 V={1.8-v(nb)}"
    if d.count(a)!=1 or d.count(b)!=1:
        raise AssertionError("Unrecognized PLL VCO bias source")
    d=d.replace(a,f"VBIAS_N nb 0 DC {bias:.9f}")
    d=d.replace(b,f"VBIAS_P pb 0 DC {1.8-bias:.9f}")
    pattern=r"(?m)^tran 3p ([\d.]+)n uic$"
    d,n=re.subn(pattern,f"tran 3p {SIM_NS:.6f}n uic",d)
    if n!=1:raise AssertionError("Transient extraction mismatch")
    return d

def test(out):
    out.mkdir(parents=True,exist_ok=True)
    work=TX.ENGINE_DIR/"p3_loaded_VCO_PVT_frequency_map"
    sim=TX.SpiceRunner(work)
    for corner in CORNERS:
        orig=TX.model_path(corner)
        dst=work/orig.name
        if not dst.exists() or orig.stat().st_mtime>dst.stat().st_mtime:
            shutil.copy2(orig,dst)
    records=[]
    for corner in CORNERS:
        for voltage in BIAS:
            sim.run(deck(corner,voltage),f"open_VCO_{corner}_{int(voltage*100):03d}")
            wave=PLL.read(work/"physical_pll.csv")
            events=[t for t in PLL.rising(wave,"vco_V",start_ns=SIM_NS-40.)]
            if len(events)<6:
                freq=None
            else:
                period=(events[-1]-events[0])/(len(events)-1)
                freq=1/(period*1e9)
            record={"corner":corner,"external_MOS_VCO_N_gate_V":voltage,
                    "PMOS_gate_V":1.8-voltage,"frequency_GHz":freq,
                    "steady_state_rising_crossings":len(events),
                    "near_target_1p8GHz":bool(freq is not None and abs(freq-1.8)<.012)}
            records.append(record)
            print(f"LOADED_VCO_RANGE corner={corner} bias={voltage:.2f}V "
                  f"freq_GHz={freq} crossings={len(events)}",flush=True)
    summary={}
    for corner in CORNERS:
        data=[r for r in records if r["corner"]==corner and
              r["frequency_GHz"] is not None]
        fs=[r["frequency_GHz"] for r in data]
        is_bracketed=bool(fs and min(fs)<=1.8<=max(fs))
        nearest=min(data,key=lambda r:abs(r["frequency_GHz"]-1.8)) if data else None
        summary[corner]={"sweep_brackets_1p8GHz":is_bracketed,
                         "min_GHz":min(fs) if fs else None,
                         "max_GHz":max(fs) if fs else None,
                         "closest_bias_V":nearest["external_MOS_VCO_N_gate_V"] if nearest else None,
                         "closest_freq_GHz":nearest["frequency_GHz"] if nearest else None}
        print(f"LOADED_VCO_RANGE_SUMMARY {corner}: bracketed={is_bracketed} "
              f"min={summary[corner]['min_GHz']} max={summary[corner]['max_GHz']}",flush=True)
    with (out/"P3_loaded_MOS_VCO_PVT_authority.csv").open("w",newline="") as f:
        w=csv.DictWriter(f,fieldnames=list(records[0]))
        w.writeheader();w.writerows(records)
    result={"experiment":"loaded but OPEN LOOP MOS VCO gain and range PVT",
            "sweep":summary,
            "records":records,
            "ngspice_runs":sim.calls,
            "all_closed_PLL_lock_established":False,
            "physical_source":"DB HiTek 180nm MOS 3stage ring and mixed-signal PFD loads",
            "bias_ideal_external":True,
            "model_equivalence_to_2004_chip":False}
    (out/"P3_loaded_MOS_VCO_PVT_authority.json").write_text(json.dumps(result,indent=2)+"\n")
    return result

if __name__=="__main__":
    p=argparse.ArgumentParser()
    p.add_argument("--out",type=Path,default=Path("results/spice/p3_loaded_vco_PVT_range"))
    args=p.parse_args()
    test(args.out)
