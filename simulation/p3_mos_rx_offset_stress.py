#!/usr/bin/env python3
"""Physical receiver input-reference offset stress in an integrated MOS link.

The injected DC offset appears ONLY on the reference-gate of the two
real DB HiTek 180nm PMOS regenerative receiver latches. The driver
termination VREF stays 0.25V. This is an explicit input-referred
threshold-offset surrogate, NOT foundry mismatch Monte Carlo, random
thermal noise, or reconstruction of the 2004 Fig14 offset calibration.

All cases share 512 PRBS31 TX symbols, identical 450MHz XSPICE PFD ->
switched MOS CP / MOS VCO, RC2 surrogate channel, and fixed MOS clock
buffers. Analyze 358 held-out transmitted UI windows with one training-
selected integer lag and count missing or duplicate MOS latch samples.
"""
from __future__ import annotations
import argparse,csv,json,math,shutil
from pathlib import Path
import p3_transistor_driver as TX
import p3_reference_pll_integrated_mos_link as LINK
# Existing per-symbol coverage assessment must NEVER drive PLL/DUT.
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"scripts"))
import audit_physical_mos_ffe_coverage as AUDIT

OFFSETS_MV=(-30.,-15.,0.,15.,30.)
ALPHAS=(0.,.30)
N_BITS=512
SEED=0x54C4EE17

def prbs31(n,seed=SEED):
    mask=(1<<31)-1;x=seed&mask;out=[]
    for _ in range(n):
        out.append(x&1)
        fb=((x>>30)^(x>>27))&1
        x=((x<<1)&mask)|fb
    return out

def netlist(bits,alpha,offset_mV):
    deck=LINK.netlist(bits,alpha)
    targets={
        "XPEREF qeven vref tE":"XPEREF qeven vref_rx tE",
        "XPOREF qodd vref tO":"XPOREF qodd vref_rx tO",
    }
    for src,dst in targets.items():
        if deck.count(src)!=1:
            raise AssertionError(f"Receiver latch reference mismatch: {src}")
        deck=deck.replace(src,dst)
    v=.25+offset_mV*1e-3
    deck=deck.replace(".control",f"VREF_RX vref_rx 0 DC {v:.9f}\n.control",1)
    return deck

def score(samples,bits):
    t0=LINK.START_DATA_NS
    ui=TX.UI_PS*1e-12
    # Convert physical LINK.evaluate clocks into the established post-run audit format.
    data=[]
    for row in samples:
        t=row["physical_clock_sample_s"]
        x=dict(row)
        x["raw_UI_floor"]=math.floor((t-t0*1e-9)/ui)
        x["raw_UI_round"]=round((t-t0*1e-9)/ui)
        data.append(x)
    best=None
    for lag in range(-5,6):
        training=AUDIT.evaluate(data,bits,lag,18,144,method="floor")
        v=(training["invalid_or_wrong_UI"],training["missing_UI"],abs(lag))
        if best is None or v<best[0]:
            best=(v,lag)
    lag=best[1]
    return {"lag_fitted_on_training_only":lag,
            "training":AUDIT.evaluate(data,bits,lag,18,144,method="floor"),
            "holdout":AUDIT.evaluate(data,bits,lag,144,502,method="floor")}

def run(out,alpha,offset):
    if alpha not in ALPHAS or offset not in OFFSETS_MV:raise ValueError
    out.mkdir(parents=True,exist_ok=True)
    label=(f"alpha_{alpha:.2f}_offset_{offset:+.0f}mV"
           .replace(".","p").replace("+","plus").replace("-","minus"))
    work=TX.ENGINE_DIR/("p3_real_MOS_RX_offset_"+label)
    engine=TX.SpiceRunner(work)
    src=TX.model_path("tt")
    dst=work/src.name
    if not dst.exists() or src.stat().st_mtime>dst.stat().st_mtime:
        shutil.copy2(src,dst)
    bits=prbs31(N_BITS)
    original_bits=LINK.BITS
    try:
        LINK.BITS=N_BITS
        engine.run(netlist(bits,alpha,offset),label)
        wave=LINK.read(work/"pll_driven_rx_wave.csv")
        pll=LINK.frequency(wave)
        samples,orig=LINK.evaluate(wave,bits,LINK.START_DATA_NS)
    finally:
        LINK.BITS=original_bits
    audit=score(samples,bits)
    report={
       "FFE_alpha":alpha,
       "RX_input_referred_DC_offset_mV":offset,
       "tested_bits":N_BITS,"PRBS31_seed":hex(SEED),
       "physical":"PDK MOS TX, 2 clocked PMOS input latches, 7bit physical MOS CP and 1.8GHz ring VCO",
       "hybrid":"XSPICE 450MHz ideal-reference PFD/4, ideal TX predriver and RC channel surrogate",
       "offset_source":"DC input-threshold offset on reference transistor gates; not random mismatch MC",
       "reference_PLL":pll,"original_score":orig,
       "heldout_coverage_audit":audit,
       "measured_BER":False,
       "actual_2004_original_silicon":False,
    }
    (out/(label+".json")).write_text(json.dumps(report,indent=2)+"\n")
    with (out/(label+"_latches.csv")).open("w",newline="") as f:
        writer=csv.DictWriter(f,fieldnames=list(samples[0]))
        writer.writeheader();writer.writerows(samples)
    h=audit["holdout"]
    print(f"PHYSICAL_RX_OFFSET alpha={alpha} offset_mV={offset:+.0f} "
          f"VCO={pll['vco_GHz']:.9f}GHz errors={h['invalid_or_wrong_UI']}/{h['expected_unique_bits']} "
          f"wrong={h['wrong_regenerated_UI']} missing={h['missing_UI']} "
          f"unresolved={h['unresolved_UI']} duplicates={h['duplicate_extra_sample_events']}",flush=True)
    return report

if __name__=="__main__":
    p=argparse.ArgumentParser()
    p.add_argument("--alpha",type=float,choices=ALPHAS,required=True)
    p.add_argument("--offset",type=float,choices=OFFSETS_MV,required=True)
    p.add_argument("--out",type=Path,default=Path("results/spice/p3_mos_rx_dc_offset"))
    a=p.parse_args()
    run(a.out,a.alpha,a.offset)
