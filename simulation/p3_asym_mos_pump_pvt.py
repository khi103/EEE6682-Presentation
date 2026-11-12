#!/usr/bin/env python3
"""Two-dimensional physical MOS charge-pump source/sink PVT screening.

With a common 3fF additional per-stage ring-VCO load, the 450MHz
mixed-mode MOS reference PLL locks in FF only for smaller CP drive,
while SS needs larger drive. Scaling both devices together cannot
meet FF and SS simultaneously. The seven-bit code is fixed at 63.

Here the PMOS sourcing device WIDTH and NMOS sinking device WIDTH are
independently varied, with all other silicon MOS sizes, PLL RC filter,
1.8V supply, startup=0.96V, and reference clock held identical.

Use 1.2us ngspice and numerical lock screen: |freq error|<1500ppm,
reference-edge phase std<8ps, filtered MOS VCO bias ripple<5mVpp.
This is a deterministic reconstructed MOS reference PLL, NOT the 2004
full transceiver or original physical data CDR.
"""
from __future__ import annotations
import argparse,json,shutil
from pathlib import Path
import p3_transistor_driver as TX
import p3_xspice_physical_mos_pll as PLL

CORNERS=("ff","ss","tt","fs","sf")
SOURCE_SCALES=(.85,.95,1.05)
SINK_SCALES=(.7,.8,.9)
CAP_FF=3.
BIAS=.96

def netlist(corner,sourcing,sinking):
    source=PLL.I_SOURCE_W_UM;sink=PLL.I_SINK_W_UM
    try:
        PLL.I_SOURCE_W_UM=source*sourcing
        PLL.I_SINK_W_UM=sink*sinking
        deck=PLL.circuit(63,corner=corner,initial_bias=BIAS)
    finally:
        PLL.I_SOURCE_W_UM=source
        PLL.I_SINK_W_UM=sink
    extra=[
      f"CASSYMVCO{i} n{i} 0 {CAP_FF:g}f" for i in range(1,4)]
    return deck.replace(".control","\n".join(extra)+"\n.control",1)

def run(out,corner,sourcing,sinking):
    if corner not in CORNERS or sourcing not in SOURCE_SCALES or sinking not in SINK_SCALES:
        raise ValueError
    out.mkdir(parents=True,exist_ok=True)
    label=f"{corner}_src_{sourcing:.2f}_snk_{sinking:.2f}".replace(".","p")
    work=TX.ENGINE_DIR/("p3_asymmetric_MOS_CP_"+label)
    sim=TX.SpiceRunner(work)
    model=TX.model_path(corner);copy=work/model.name
    if not copy.exists() or model.stat().st_mtime>copy.stat().st_mtime:
        shutil.copy2(model,copy)
    results={"corner":corner,"common_initial_V":BIAS,
        "CP_source_width_scale":sourcing,"CP_sink_width_scale":sinking,
        "physical_added_VCO_cap_per_stage_fF":CAP_FF,
        "not_source_silicon_or_original_P3_PFD":True}
    try:
        sim.run(netlist(corner,sourcing,sinking),label)
        wave=PLL.read(work/"physical_pll.csv")
        m=PLL.metrics(wave)
        m.update(PLL.aligned_phase_errors_ps(wave))
        f=m.get("vco_GHz")
        ppm=1e6*(f/1.8-1) if f is not None else None
        passed=bool(ppm is not None and abs(ppm)<1500 and
                     m.get("std_phase_ps") is not None and m["std_phase_ps"]<8 and
                     m["physical_vco_gate_ripple_mV"]<5 and
                     m.get("n_reference_edges",0)>=25)
        results.update({"status":"simulated","measured":m,
             "freq_error_ppm":ppm,"locked_predeclared_criterion":passed})
    except Exception as e:
        results.update({"status":"spice_failed",
             "error":f"{type(e).__name__}: {str(e)[-1300:]}",
             "locked_predeclared_criterion":False})
    (out/(label+".json")).write_text(json.dumps(results,indent=2)+"\n")
    m=results.get("measured",{})
    print(f"ASYMMETRIC_MOS_CP corner={corner} source_scale={sourcing:.2f} "
          f"sink_scale={sinking:.2f} fVCO_GHz={m.get('vco_GHz')} "
          f"phase_std_ps={m.get('std_phase_ps')} "
          f"gate_ripple_mV={m.get('physical_vco_gate_ripple_mV')} "
          f"pass={results['locked_predeclared_criterion']}",flush=True)
    return results

if __name__=="__main__":
    parser=argparse.ArgumentParser()
    parser.add_argument("--corner",choices=CORNERS,required=True)
    parser.add_argument("--source-scale",type=float,choices=SOURCE_SCALES,required=True)
    parser.add_argument("--sink-scale",type=float,choices=SINK_SCALES,required=True)
    parser.add_argument("--out",type=Path,default=Path("results/spice/p3_asym_mos_CP_PVT"))
    a=parser.parse_args()
    run(a.out,a.corner,a.source_scale,a.sink_scale)
