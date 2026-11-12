#!/usr/bin/env python3
"""Disambiguate apparent reference-interval cycle slip from edge-boundary artifacts.

Some MOS reference PLL runs have 3/5 VCO rising-edge counts in single
450-MHz reference periods even though measured reference-edge phase
std is <1ps. Counting exact edges in arbitrarily bounded time
intervals may mislabel jitter at an edge boundary as genuine PLL slip.

Use the 180nm physically PMOS-diode-biased MOS PLL with 450MHz
reference +/-1000ppm, full 1.2us SPICE. Pair EVERY kth reference edge
with a CONSISTENT 4k-indexed physical VCO edge, using the initial
nearest crossing only for the fixed phase offset. Track the resulting
unwrapped time-offset sequence and check for large cycle-sized jumps.

This is a finite transient numerical phase-continuity screen, not
silicon measured random PLL jitter, noise or original Wong CDR lock.
"""
from __future__ import annotations
import argparse,bisect,json,math,shutil
from pathlib import Path
import p3_xspice_physical_mos_pll as PLL
import p3_pll_extended_pvt_phase as PVT
import p3_real_mos_pump_bias_sentinel as PHYS
import p3_transistor_driver as TX

PPM=(-1000.,0.,1000.)
CORNERS=("ff",)
BEGIN_NS=1040
END_NS=1200

def run(out,corner,ppm):
    if corner not in CORNERS or ppm not in PPM:raise ValueError
    out.mkdir(parents=True,exist_ok=True)
    label=f"{corner}_{ppm:+g}ppm".replace("+","p").replace("-","m")
    work=TX.ENGINE_DIR/("p3_PLL_ref_edge_index_"+label)
    runner=TX.SpiceRunner(work)
    src=TX.model_path(corner);dst=work/src.name
    if not dst.exists() or src.stat().st_mtime>dst.stat().st_mtime:shutil.copy2(src,dst)
    period0=PLL.REF_PERIOD_PS;d0=PVT.deck
    freq_ref=450*(1+ppm*1e-6)
    try:
        PLL.REF_PERIOD_PS=1e12/(freq_ref*1e6)
        PVT.deck=lambda c,t,v:PHYS.patch(d0(c,t,v),"diode_w16_r4k")
        runner.run(PVT.deck(corner,27.,1.8),label)
    finally:
        PLL.REF_PERIOD_PS=period0;PVT.deck=d0
    rows=PLL.read(work/"physical_pll.csv")
    # include prestart oscillator edges so initial nearest index is grounded.
    ref=[t for t in PLL.rising(rows,"ref_V",start_ns=BEGIN_NS) if t<=END_NS*1e-9]
    osc=[t for t in PLL.rising(rows,"vco_V",start_ns=BEGIN_NS-2) if t<=END_NS*1e-9]
    if len(ref)<40 or len(osc)<200:raise RuntimeError("Incomplete postlock reference/oscillator edges")
    k=bisect.bisect_left(osc,ref[0])
    initial=min((k-1,k),key=lambda z:abs(osc[z]-ref[0]))
    continuous=[]
    interval_counts=[]
    for n,(a,b) in enumerate(zip(ref,ref[1:])):
        ka=bisect.bisect_left(osc,a);kb=bisect.bisect_left(osc,b)
        interval_counts.append(kb-ka)
    for n,t in enumerate(ref):
        j=initial+4*n
        if j>=len(osc):break
        continuous.append((osc[j]-t)*1e12)
    steps=[b-a for a,b in zip(continuous,continuous[1:])]
    vco_UI_ps=1/(4*freq_ref*1e6)*1e12
    result={
      "corner":corner,"reference_offset_ppm":ppm,
      "actual_physical_MOS_PLL":True,
      "real_original_chip_or_random_jitter":False,
      "reference_intervals":len(interval_counts),
      "naive_nonfour_intervals":sum(k!=4 for k in interval_counts),
      "naive_min_edges":min(interval_counts),"naive_max_edges":max(interval_counts),
      "continuous_four_to_one_edge_pairs":len(continuous),
      "phase_index_shift_ps":continuous[0],
      "maximum_relative_phase_change_ps":
          max(abs(x-continuous[0]) for x in continuous),
      "maximum_adjacent_phase_step_ps":max(abs(x) for x in steps),
      "oscillator_period_ps":vco_UI_ps,
      "phase_jumps_larger_than_half_VCO_UI":
          sum(abs(x)>vco_UI_ps/2 for x in steps),
      "phase_tracking_without_continuity_jumps":
          len(continuous)>=40 and all(abs(x)<vco_UI_ps/2 for x in steps),
      "physical_initial_phase_assigned_by_nearest_edge_only":True,
      "not_a_proof_of_phase_noise_or_data_CDR":True,
    }
    (out/f"{label}.json").write_text(json.dumps(result,indent=2)+"\n")
    print(f"PLL_CONTINUITY corner={corner} ref_ppm={ppm:+g} "
          f"naive_non_four_intervals={result['naive_nonfour_intervals']} "
          f"max_adjacent_phase_step_ps={result['maximum_adjacent_phase_step_ps']:.3f} "
          f"max_phase_range_ps={result['maximum_relative_phase_change_ps']:.3f} "
          f"half_UI_jump_count={result['phase_jumps_larger_than_half_VCO_UI']} "
          f"continuous={result['phase_tracking_without_continuity_jumps']}",flush=True)
    return result

if __name__=="__main__":
    p=argparse.ArgumentParser()
    p.add_argument("--corner",choices=CORNERS,default="ff")
    p.add_argument("--ppm",type=float,choices=PPM,required=True)
    p.add_argument("--out",type=Path,default=Path("results/spice/p3_PLL_ref_edge_continuity"))
    a=p.parse_args()
    run(a.out,a.corner,a.ppm)
