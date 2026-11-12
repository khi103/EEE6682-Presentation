#!/usr/bin/env python3
"""Trace the earliest undefined XSPICE digital node with ONE DAC probe.

The first four-XOR mixed-signal MOS CDR trace had every UP/DN analog DAC
at out_undef=.5V, despite the MOS RX channel varying. Adding NINE
extra DAC probes caused some ngspice full-deck transients to terminate
early. This instrumented experiment adds exactly ONE digital probe
at a time, preserving the original ADC/DFF/XOR feedback loop and its
physical transistor MOS TX/RX/charge pump/clock path.

No source bits are provided to the detector or to the physical phase
control. The source PRBS31 bits are used only to generate the PWL TX.
A probe with unknown state after serial data starts is reported, not
corrected or converted into a predetermined 0/1 value.
"""
from __future__ import annotations
import argparse,json,math,re,shutil
from pathlib import Path
import p3_transistor_driver as TX
import p3_xspice_4xor_mos_cdr as FOUR
import p3_reference_pll_integrated_mos_link as LINK

NODES=("drx","dclke","dD0","dE0","du0","dd0")
SHIFTS=(.95,-.05)
START=1220.
ALPHA=.30

def raw_deck(bits,node,shift):
    d,start=FOUR.make_deck(bits,0.,shift)
    # Pull out the 9-output aggregate probe that had convergence problems.
    rows=[line for line in d.splitlines()
          if not line.startswith("APROBE_DIGITAL ")
          and not line.startswith("wrdata xor_digital_inputs.csv ")]
    deck="\n".join(rows)+"\n"
    extra=f"AONEPROBE [{node}] [vprobe] xdac"
    if deck.count(".control")!=1:
        raise RuntimeError("SPICE control section not uniquely identified")
    deck=deck.replace(".control",extra+"\n.control",1)
    orig="quit\n.endc"
    if deck.count(orig)!=1:raise RuntimeError("Cannot find single end of control")
    deck=deck.replace(orig,
        "wrdata single_stage.csv time v(vprobe) v(rx) v(clkeven) v(n1)\nquit\n.endc",1)
    return deck,start

def read_probe(path,start_ns):
    items=[]
    for line in path.read_text().splitlines():
        try:a=[float(z) for z in line.split()]
        except ValueError:continue
        if len(a)>=10 and all(math.isfinite(z) for z in a):
            items.append({"t":a[0],"digital":a[3],"rx":a[5],
                          "clock":a[7],"vco":a[9]})
    if len(items)<200:raise RuntimeError("No adequate mixed-mode probe waveform")
    active=[x for x in items if x["t"]>=start_ns*1e-9]
    summary={
      "record_count":len(items),
      "first_time_ns":items[0]["t"]*1e9,
      "last_time_ns":items[-1]["t"]*1e9,
      "data_start_ns":start_ns,
      "full_serial_data_interval_executed":len(active)>200,
    }
    if active:
        vals=[x["digital"] for x in active]
        summary.update({
          "digital_zero_fraction":sum(v<.1 for v in vals)/len(vals),
          "digital_one_fraction":sum(v>.9 for v in vals)/len(vals),
          "digital_undefined_fraction":sum(.4<v<.6 for v in vals)/len(vals),
          "digital_min_V":min(vals),"digital_max_V":max(vals),
          "received_RX_min_V":min(x["rx"] for x in active),
          "received_RX_max_V":max(x["rx"] for x in active),
          "clock_min_V":min(x["clock"] for x in active),
          "clock_max_V":max(x["clock"] for x in active),
        })
    return summary

def run(out,node,shift):
    if node not in NODES or shift not in SHIFTS:raise ValueError
    out.mkdir(parents=True,exist_ok=True)
    name=f"node_{node}_phase_{shift:+.2f}".replace("+","plus").replace("-","minus").replace(".","p")
    work=TX.ENGINE_DIR/("p3_one_xspice_probe_"+name)
    engine=TX.SpiceRunner(work)
    model=TX.model_path("tt");dst=work/model.name
    if not dst.exists() or model.stat().st_mtime>dst.stat().st_mtime:shutil.copy2(model,dst)
    bits=FOUR.prbs31(256)
    entry={"tested_digital_node":node,"start_UI":shift,
           "probe_count":1,"added_probe_load_is_zero":False,
           "is_not_original_2004_PLL":True}
    try:
        d,start=raw_deck(bits,node,shift)
        log=engine.run(d,name)
        entry["SPICE_log_tail_errors"]=[
            ln for ln in log.splitlines()
            if any(q in ln.lower() for q in ("timestep too small","singular matrix","simulation aborted","error:","fatal:"))
        ][-15:]
        entry.update(read_probe(work/"single_stage.csv",start))
        entry["status"]="simulated"
    except Exception as exc:
        entry.update({"status":"simulation_or_parse_failed",
                      "error":f"{type(exc).__name__}: {str(exc)[-1800:]}"})
    (out/f"{name}.json").write_text(json.dumps(entry,indent=2)+"\n")
    print(f"XSPICE_ONE_PROBE node={node} shift={shift:+.2f} "
          f"status={entry['status']} "
          f"last_time_ns={entry.get('last_time_ns')} "
          f"after_data={entry.get('full_serial_data_interval_executed')} "
          f"U_frac={entry.get('digital_undefined_fraction')} "
          f"zero_frac={entry.get('digital_zero_fraction')} "
          f"one_frac={entry.get('digital_one_fraction')}",flush=True)
    return entry

if __name__=="__main__":
    p=argparse.ArgumentParser()
    p.add_argument("--node",choices=NODES,required=True)
    p.add_argument("--shift",type=float,choices=SHIFTS,required=True)
    p.add_argument("--out",type=Path,default=Path("results/spice/p3_xspice_one_probe"))
    a=p.parse_args()
    run(a.out,a.node,a.shift)
