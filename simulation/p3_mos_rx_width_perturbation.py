#!/usr/bin/env python3
"""True MOS-W input-pair mismatch perturbation within physical 3.6Gb/s link.

Perturb widths of BOTH CMOS PMOS differential input devices in each
real regenerative MOS RX latch, with complementary signs to increase
sensitivity to a systematic differential-pair sizing offset:
   VIN device width = 5um*(1+delta)
   VREF device width = 5um*(1-delta)
for delta=-0.10,-0.05,0,+0.05,+0.10. This is a deterministic
device-width corner STRESS, not a foundry mismatch model or actual
statistical Monte Carlo of native Vth/β variation.

The rest of the CMOS TX predriver, 8:4:2:1 driver, RC2 -12dB channel,
MOS receiver clock delay at one common 1.10V bias, and reference PLL
remain SAME in each 512-bit PRBS31 SPICE run. Alpha=0/.30 are compared.
Data labels NEVER enter the PLL or actual MOS clock actuator.
A 358-UI holdout counts missed/duplicate/unresolved/regenerated decisions.

The original 2004 Fig14 transistor sizing and silicon statistics are
not available, so report only systematic sensitivity, not foundry yield.
"""
from __future__ import annotations
import argparse,csv,json,re,shutil
from pathlib import Path
import p3_long_predriver_prbs31 as FULL
import p3_mos_predriver_clock_retune as RETIME
import p3_reference_pll_integrated_mos_link as LINK
import p3_mos_tx_predriver as PRE
import p3_transistor_driver as TX
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"scripts"))
import audit_physical_mos_ffe_coverage as AUDIT

DELTAS=(-.10,-.05,0.,.05,.10)
ALPHAS=(0.,.30)
BIAS_V=1.10
BITS=512
SEED=0x54C4EE17

def deck(bits,delta,alpha):
    s=RETIME.build(bits,alpha,BIAS_V)
    for prefix in ("E","O"):
        for kind,weight in (("VIN",1+delta),("REF",1-delta)):
            width=5*weight
            # Specific reconstructed PMOS input-pair device instance.
            pat=rf"(?m)^(XP{prefix}{kind}\s+.+?\s+width=)5u(\s+length=\.18u\s+multi=1\s*)$"
            replacement=rf"\g<1>{width:.8g}u\2"
            s,n=re.subn(pat,replacement,s)
            if n!=1:
                raise RuntimeError(f"Exactly one real MOS RX input transistor required: {prefix} {kind}, found {n}")
    return s

def score(samples,bits):
    import math
    start=LINK.START_DATA_NS*1e-9
    ui=TX.UI_PS*1e-12
    data=[]
    for row in samples:
        z=dict(row)
        z["raw_UI_floor"]=math.floor((z["physical_clock_sample_s"]-start)/ui)
        z["raw_UI_round"]=round((z["physical_clock_sample_s"]-start)/ui)
        data.append(z)
    candidate=min(range(-5,6),key=lambda k:(
         AUDIT.evaluate(data,bits,k,18,144,"floor")["invalid_or_wrong_UI"],
         AUDIT.evaluate(data,bits,k,18,144,"floor")["missing_UI"],abs(k)))
    return {"training_integer_lag":candidate,
        "heldout":AUDIT.evaluate(data,bits,candidate,144,502,"floor")}

def run(out,delta,alpha):
    if delta not in DELTAS or alpha not in ALPHAS:raise ValueError
    out.mkdir(parents=True,exist_ok=True)
    label=f"delta_{delta:+.2f}_alpha_{alpha:.2f}".replace("+","p").replace("-","m").replace(".","p")
    work=TX.ENGINE_DIR/("p3_MOS_latch_W_mismatch_"+label)
    engine=PRE.TXGateLargeRunner(work)
    model=TX.model_path("tt")
    dest=work/model.name
    if not dest.exists() or model.stat().st_mtime>dest.stat().st_mtime:shutil.copy2(model,dest)
    previous=LINK.BITS
    result={"input_pair_delta":delta,"FFE_alpha":alpha,
        "MOS_input_width_VIN_um":5*(1+delta),
        "MOS_reference_width_VREF_um":5*(1-delta),
        "PRBS31_seed_hex":hex(SEED),
        "systematic_device_width_perturbation":True,
        "actual_foundry_mismatch_model":False,
        "actual_mismatch_yield_claim":False,
        "actual_2004_comparator_Fig14":False,
        "all_other_supply_clock_channel_model_identical":True}
    try:
        LINK.BITS=BITS
        bits=FULL.prbs31(BITS,seed=SEED)
        engine.run(deck(bits,delta,alpha),label)
        wave=LINK.read(work/"pll_driven_rx_wave.csv")
        physical,raw=LINK.evaluate(wave,bits,LINK.START_DATA_NS)
        m=score(physical,bits)
        pll=LINK.frequency(wave)
        result.update({"status":"simulated","PLL":pll,
            "MOS_RX":m,"initial_scoring":raw})
        with (out/(label+"_real_MOS_latches.csv")).open("w",newline="") as f:
            w=csv.DictWriter(f,fieldnames=list(physical[0]))
            w.writeheader()
            w.writerows(physical)
    except Exception as e:
        result.update({"status":"simulator_or_readout_failed",
              "error":f"{type(e).__name__}: {str(e)[-1200:]}"})
    finally:
        LINK.BITS=previous
    (out/(label+".json")).write_text(json.dumps(result,indent=2)+"\n")
    hold=result.get("MOS_RX",{}).get("heldout",{})
    print(f"MOS_WIDTH_MISMATCH delta={delta:+.2f} alpha={alpha:.2f} "
       f"status={result['status']} VCO_GHz={result.get('PLL',{}).get('vco_GHz')} "
       f"errors={hold.get('invalid_or_wrong_UI')}/{hold.get('expected_unique_bits')} "
       f"missing={hold.get('missing_UI')} wrong={hold.get('wrong_regenerated_UI')} "
       f"unresolved={hold.get('unresolved_UI')}",flush=True)
    return result

if __name__=="__main__":
    p=argparse.ArgumentParser()
    p.add_argument("--delta",type=float,choices=DELTAS,required=True)
    p.add_argument("--alpha",type=float,choices=ALPHAS,required=True)
    p.add_argument("--out",type=Path,default=Path("results/spice/p3_MOS_latch_width_perturb"))
    a=p.parse_args()
    run(a.out,a.delta,a.alpha)
