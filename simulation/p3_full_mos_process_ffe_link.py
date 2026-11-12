#!/usr/bin/env python3
"""Actual 512-bit PRBS31 full MOS link across five PDK process corners.

Use the same physically diode-biased MOS reference PLL design that was
independently confirmed 21/21 for PVT:
  16um diode-PMOS/4kohm bias, 1kohm loop zero, fixed switched pump
  widths, +3fF/stage 3-stage MOS ring.
Connect an actual two-stage CMOS TX predriver, 8:4:2:1 MOS TX, two-pole
surrogate channel, two transistor-level RX latches and two actual
current-starved MOS RX clock-delay stages in ONE ngspice transient.
Process corners TT/FF/SS/FS/SF affect ALL MOS TX, RX, CP, VCO, PMOS
diode bias devices. One 1.10V receiver phase delay is kept fixed,
with alpha=0/.30, 512 PRBS31 and post-run 358 UI coverage-aware scoring.

The 450MHz reference clock, XSPICE PFD, physical phase-delay bias
voltage source and surrogate RC channel are still ideal/behavioral.
The 2004 original 50ohm FR4/RG58 or ASIC layout is NOT reconstructed.
Different corner behavior is NOT a true random foundry mismatch MC.
"""
from __future__ import annotations
import argparse,csv,json,shutil
from pathlib import Path
import p3_transistor_driver as TX
import p3_reference_pll_integrated_mos_link as LINK
import p3_mos_predriver_clock_retune as RETIME
import p3_mos_tx_predriver as PRE
import p3_long_predriver_prbs31 as LONG
import p3_mos_rx_offset_stress as SCORE
import p3_real_mos_pump_bias_sentinel as PHYS

CORNERS=("tt","ff","ss","fs","sf")
ALPHAS=(0.,.30)
BITS=512
BIAS=1.10
SEED=0x54C4EE17

def netlist(bits,corner,alpha):
    old_corner=LINK.CORNER
    try:
        LINK.CORNER=corner
        deck=RETIME.build(bits,alpha,BIAS)
    finally:
        LINK.CORNER=old_corner
    # The one PVT qualified physical PMOS diode reference generator
    # and passive zero resistor replace original PLL ideal fixed-bias.
    deck=PHYS.patch(deck,"diode_w16_r4k")
    assert deck.count(".control")==1
    extras=[f"CEXTRA_FULL_LINK_VCO{i} n{i} 0 3f" for i in range(1,4)]
    deck=deck.replace(".control","\n".join(extras)+"\n.control",1)
    # The initial voltage is the same 1.02 V used in the full PVT PLL
    # rather than the older standalone link's .96 V.
    old="VSTART vstart 0 0.96"
    if deck.count(old)!=1:raise RuntimeError("Missing original 0.96V startup")
    deck=deck.replace(old,"VSTART vstart 0 1.02",1)
    assert deck.count("ic=0.96")==3
    deck=deck.replace("ic=0.96","ic=1.02")
    for v in ("lpcap","loopctrl","vcobias"):
        anchor=f"v({v})=0.96"
        if deck.count(anchor)!=1:raise RuntimeError(f"Missing original {v} IC")
        deck=deck.replace(anchor,f"v({v})=1.02",1)
    return deck

def run(out,corner,alpha):
    if corner not in CORNERS or alpha not in ALPHAS:raise ValueError
    out.mkdir(parents=True,exist_ok=True)
    name=f"{corner}_alpha_{alpha:.2f}".replace(".","p")
    work=TX.ENGINE_DIR/("p3_fixed_FullMOS_PVT_"+name)
    runner=PRE.TXGateLargeRunner(work)
    model=TX.model_path(corner)
    dest=work/model.name
    if not dest.exists() or model.stat().st_mtime>dest.stat().st_mtime:shutil.copy2(model,dest)
    old=LINK.BITS
    report={
      "corner":corner,"alpha":alpha,"pattern":"512-bit PRBS31","seed":hex(SEED),
      "actual_MOS":"DB HiTek 180nm TX predriver, segmented driver, regenerative RX, diode-bias, pump and VCO",
      "reference":"ideal 450MHz XSPICE PFD/4",
      "channel":"buffered two-pole surrogate -12dB at 1.8GHz, not measured RG58",
      "physical_RX_clock_delay_bias_V":BIAS,
      "phase_clock_actuator_data_CDR":False,
      "no_bit_labels_drive_reference_PLL":True,
      "not_original_2004_silicon":True,
    }
    try:
        LINK.BITS=BITS
        bits=LONG.prbs31(BITS,SEED)
        runner.run(netlist(bits,corner,alpha),name)
        rows=LINK.read(work/"pll_driven_rx_wave.csv")
        pll=LINK.frequency(rows)
        samples,raw=LINK.evaluate(rows,bits,LINK.START_DATA_NS)
        coverage=SCORE.score(samples,bits)
        focus=[x for x in rows if x["time_s"]>=LINK.START_DATA_NS*1e-9]
        partial={
           "shared_1p8V_MOS_link_mW":LINK.time_weighted_power_mW(focus,"power_vdd_source_A",1.8),
           "0p5V_TX_signaling_source_mW":LINK.time_weighted_power_mW(focus,"power_tx_source_A",.5)}
        report.update({"status":"simulated","PLL":pll,
            "sample_coverage_audit":coverage,
            "initial_score":raw,"partial_supply_power":partial})
        with (out/(name+"_physical_decisions.csv")).open("w",newline="") as f:
            w=csv.DictWriter(f,fieldnames=list(samples[0]))
            w.writeheader();w.writerows(samples)
        # Preserve actual analog RX voltage for independent fixed-phase Eye.
        chunk=[x for x in rows if x["time_s"]>=LINK.START_DATA_NS*1e-9-1e-9]
        with (out/(name+"_RX_analog.csv")).open("w",newline="") as f:
            cols=("time_s","rx_V","clkeven_V","clkodd_V","vco_V")
            w=csv.DictWriter(f,fieldnames=cols);w.writeheader()
            w.writerows([{k:q[k] for k in cols} for q in chunk[::max(1,len(chunk)//8000)]])
    except Exception as e:
        report.update({"status":"simulation_or_scoring_failed",
                       "error":f"{type(e).__name__}: {str(e)[-2200:]}"})
    finally:
        LINK.BITS=old
    (out/(name+".json")).write_text(json.dumps(report,indent=2)+"\n")
    h=report.get("sample_coverage_audit",{}).get("holdout",{})
    print(
      f"FULL_MOS_PROCESS_LINK corner={corner} alpha={alpha} "
      f"status={report['status']} fVCO_GHz={report.get('PLL',{}).get('vco_GHz')} "
      f"heldout={h.get('invalid_or_wrong_UI')}/{h.get('expected_unique_bits')} "
      f"missing={h.get('missing_UI')} wrong={h.get('wrong_regenerated_UI')} "
      f"unresolved={h.get('unresolved_UI')} "
      f"partial_mW={report.get('partial_supply_power')}",flush=True)
    return report

if __name__=="__main__":
    p=argparse.ArgumentParser()
    p.add_argument("--corner",choices=CORNERS,required=True)
    p.add_argument("--alpha",type=float,choices=ALPHAS,required=True)
    p.add_argument("--out",type=Path,default=Path("results/spice/p3_full_MOS_process_link"))
    a=p.parse_args()
    run(a.out,a.corner,a.alpha)
