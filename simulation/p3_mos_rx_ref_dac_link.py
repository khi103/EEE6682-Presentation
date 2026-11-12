#!/usr/bin/env python3
"""Physical MOS 4-bit RX reference-DAC trim in actual 3.6-Gb/s link.

A 0.28-V deliberately offset receiver reference is sourced through a
3-kOhm resistor into the PMOS-input differential gates of two physical
regenerative MOS RX latches. Four binary-weighted DB HiTek 180nm NMOS
sinks draw current from the receiver reference under an ideal 4-bit
code. The TX driver termination remains at 0.25V. The actual MOS RX,
segmented TX, 450MHz reference PLL, MOS switched CP, and MOS VCO run in
one ngspice transient for 512 independent PRBS31 bits.

This is NOT the 2004 paper's M8-M10 current-steering structure and no
digital calibration state-machine exists. Code 9 was preselected using
ONLY independent MOS DC voltage characterization (run 43176424096)
as closest to the target 0.25V, NEVER based on known bit outcomes.
Other codes are stress cases. Receiver sample errors are scored
postrun on a 358-bit holdout with missing/duplicate UI recorded.
"""
from __future__ import annotations
import argparse,csv,json,math,shutil
from pathlib import Path
import p3_transistor_driver as TX
import p3_reference_pll_integrated_mos_link as LINK
import p3_mos_rx_offset_stress as OFFSET

TRIM_CODES=(0,3,6,8,9,10,12,15)
RESISTOR_OHM=3000.
VG_ON=.5
SEED=0x54C4EE17
TX_FFE_ALPHA=.30
RX_BASE_REF_V=.280
PRESELECTED_DC_CODE=9
BITS=512

def netlist(bits,code):
    deck=OFFSET.netlist(bits,TX_FFE_ALPHA,30.)
    original="VREF_RX vref_rx 0 DC 0.280000000"
    if deck.count(original)!=1:raise RuntimeError("RX reference source unexpected")
    rest=[
        "* Actual 4-bit MOS NMOS current-source reference trim",
        f"VREFBASE vref_base 0 DC {RX_BASE_REF_V:.9g}",
        f"RREFDAC vref_base vref_rx {RESISTOR_OHM:.9g}",
        "CREFTRIM vref_rx 0 100f ic=.28",
    ]
    for w in (1,2,4,8):
        rest.extend([
          f"VTRIM{w} trim{w} 0 DC {VG_ON if code&w else 0:.9g}",
          f"XNREFTRIM{w} vref_rx trim{w} 0 0 nch_svt_1p8v "
          f"width=.48u length=.36u multi={w}",
        ])
    deck=deck.replace(original,"\n".join(rest),1)
    deck=deck.replace(".control",".ic v(vref_rx)=.28\n.control",1)
    original_control="quit\n.endc"
    if deck.count(original_control)!=1:
        raise RuntimeError("Expected one ngspice quit")
    deck=deck.replace(original_control,
        "wrdata mos_reference_wave.csv time v(vref_rx)\nquit\n.endc",1)
    return deck

def voltage_stats(path,start_ns=LINK.START_DATA_NS):
    a=[]
    for line in path.read_text().splitlines():
        try:x=[float(z) for z in line.split()]
        except ValueError:continue
        if len(x)>=4 and math.isfinite(x[3]) and x[0]>=start_ns*1e-9:
            a.append(x[3])
    if not a:raise RuntimeError("No physical MOS DAC reference waveform")
    return {"reference_during_serial_data_mean_mV":sum(a)/len(a)*1000,
            "reference_min_mV":min(a)*1000,
            "reference_max_mV":max(a)*1000}

def run(out,code):
    if code not in TRIM_CODES:raise ValueError(code)
    out.mkdir(parents=True,exist_ok=True)
    label=f"code_{code:02d}"
    work=TX.ENGINE_DIR/("p3_physical_rx_DAC_"+label)
    engine=TX.SpiceRunner(work)
    src=TX.model_path("tt");dest=work/src.name
    if not dest.exists() or src.stat().st_mtime>dest.stat().st_mtime:
        shutil.copy2(src,dest)
    bits=OFFSET.prbs31(BITS,SEED)
    LINK.BITS=BITS
    engine.run(netlist(bits,code),label)
    wave=LINK.read(work/"pll_driven_rx_wave.csv")
    source=voltage_stats(work/"mos_reference_wave.csv")
    pll=LINK.frequency(wave)
    samples,original=LINK.evaluate(wave,bits,LINK.START_DATA_NS)
    audit=OFFSET.score(samples,bits)
    result={
      "source":"physically sized 4bit NMOS current DAC, DB HiTek 180nm model",
      "reference_original_mV":280.0,
      "reference_target_mV":250.0,
      "preselected_code_based_only_on_DC_voltage":PRESELECTED_DC_CODE,
      "this_trial_code":code,
      "trim_code_active_bits":sum(bool(code&w) for w in (1,2,4,8)),
      "selected_for_calibration_using_transmitted_data":False,
      "actual_MOS_reference_voltage":source,
      "physical_RX_heldout":audit,"original_scoring":original,
      "physical_PLL":pll,
      "physical_MOS_DAC_transient":True,
      "actual_circuit_offset_training_controller":False,
      "actual_2004_Fig14_M8_M10_structure":False,
      "random_statistical_mismatch":False,
      "no_original_2004_silicon_power_or_BER_claim":True
    }
    (out/(label+".json")).write_text(json.dumps(result,indent=2)+"\n")
    with (out/(label+"_real_latch_decisions.csv")).open("w",newline="") as f:
        w=csv.DictWriter(f,fieldnames=list(samples[0]))
        w.writeheader();w.writerows(samples)
    h=audit["holdout"]
    print(f"PHYSICAL_RX_DAC_LINK code={code} calibrated_DC_choice={code==PRESELECTED_DC_CODE} "
          f"VREF_mV={source['reference_during_serial_data_mean_mV']:.3f} "
          f"VCO_GHz={pll['vco_GHz']:.9f} "
          f"heldout_errors={h['invalid_or_wrong_UI']}/{h['expected_unique_bits']} "
          f"wrong={h['wrong_regenerated_UI']} missing={h['missing_UI']} "
          f"unresolved={h['unresolved_UI']}",flush=True)
    return result

if __name__=="__main__":
    p=argparse.ArgumentParser()
    p.add_argument("--code",type=int,choices=TRIM_CODES,required=True)
    p.add_argument("--out",type=Path,default=Path("results/spice/p3_physical_MOS_RX_DAC"))
    a=p.parse_args()
    run(a.out,a.code)
