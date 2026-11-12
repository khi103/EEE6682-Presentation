#!/usr/bin/env python3
"""Isolate ngspice startup failure when attaching 4-bit MOS RX offset DAC.

A full MOS PLL/RX reference-offset loop succeeds when VREFRX is an ideal
0.28V voltage source. Replacing that source with a resistor-fed physical
MOS current DAC initially caused 'initial timepoint: trouble with
nw_psub-instance d.xpsource.dd1'. The aim is to identify which topology
change causes ngspice to abort, not to disguise or ignore the failure.
All trials use the same license-authorized DB HiTek MOS model in private CI.
"""
from __future__ import annotations
import argparse,re,shutil
from pathlib import Path
import p3_transistor_driver as TX
import p3_reference_pll_integrated_mos_link as LINK
import p3_mos_rx_offset_stress as OFFSET
import p3_mos_rx_ref_dac_link as DAC

def decks():
    bits=OFFSET.prbs31(32)
    base=OFFSET.netlist(bits,.3,30.)
    dev=DAC.netlist(bits,9)
    idealref="VREF_RX vref_rx 0 DC 0.280000000"
    resref=("VREFBASE vref_base 0 DC 0.28\n"
            "RREFDAC vref_base vref_rx 3000\n"
            "CREFTRIM vref_rx 0 100f ic=.28")
    extra=[
       f"VRXTRIM{w} rxtrim{w} 0 DC {0.5 if 9&w else 0}"
       for w in (1,2,4,8)]
    extra.extend([
      f"XNREFTRIM{w} vref_rx rxtrim{w} 0 0 nch_svt_1p8v width=.48u length=.36u multi={w}"
      for w in (1,2,4,8)])
    cases={
        "ideal_reference_baseline":base,
        "resistor_reference_only":base.replace(idealref,resref),
        "MOS_sinks_on_ideal_reference":base.replace(".control","\n".join(extra)+"\n.control",1),
        "full_MOS_DAC_UIC":dev,
        "full_MOS_DAC_without_UIC":dev,
        "full_MOS_DAC_reduced_step_gear":dev,
    }
    for label,deck in list(cases.items()):
        deck,n=re.subn(r"(?m)^tran 3p [\d.]+n uic$",
                       "tran 3p 25n uic",deck)
        if n!=1:raise RuntimeError(f"Unexpected transient statement for {label}")
        if label=="full_MOS_DAC_without_UIC":
            deck=deck.replace("tran 3p 25n uic","tran 3p 25n")
        if label=="full_MOS_DAC_reduced_step_gear":
            deck=deck.replace(".control",
             ".options reltol=0.005 method=gear gmin=1e-11\n.control",1)
        cases[label]=deck
    return cases

def main(out):
    out.mkdir(parents=True,exist_ok=True)
    work=TX.ENGINE_DIR/"p3_RX_DAC_debug"
    sim=TX.SpiceRunner(work)
    src=TX.model_path("tt");dst=work/src.name
    if not dst.exists() or src.stat().st_mtime>dst.stat().st_mtime:
        shutil.copy2(src,dst)
    result={}
    for label,deck in decks().items():
        try:
            sim.run(deck,label)
            status="RUN_OK"
            details=""
        except Exception as e:
            status="SIM_FAIL"
            details=str(e)[-800:]
        result[label]={"status":status,"error_excerpt":details}
        print(f"RX_DAC_DIAGNOSTIC case={label} result={status} {details[-200:]}",flush=True)
    import json
    (out/"RX_DAC_startup_failure_map.json").write_text(json.dumps(result,indent=2)+"\n")
    return result

if __name__=="__main__":
    p=argparse.ArgumentParser()
    p.add_argument("--out",type=Path,default=Path("results/spice/p3_RX_DAC_startup_debug"))
    main(p.parse_args().out)
