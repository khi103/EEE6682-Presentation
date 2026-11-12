#!/usr/bin/env python3
"""Physical CMOS TX gate predrivers added to reference-locked MOS link.

Before this experiment the 8:4:2:1 NMOS TX bank was driven directly by
ideal 1.8-V PWL gate sources, omitting gate-switching power. This study
replaces each of the eight NMOS bank gate sources with two physical
180nm CMOS inverter stages; ideal PWL now drives ONLY each first-stage
inverter input. Both predriver stages share the VDD source with the
reference PLL, MOS charge pump/VCO, and MOS receiver.

The same one-SPICE MOS TX/RC2/RX/reference-PLL circuit is run in two
conditions (ideal-direct and physical-prebuffer), with alpha 0/.30 and
exactly the same PRBS7 symbols and source clocks. The transistor
pre-driver is independently sized: not the original 2004 MUX or slew
control. Partial source power includes these added CMOS gates but not
the entire original 27.12mW link budget.
"""
from __future__ import annotations
import argparse,csv,json,math,shutil
from pathlib import Path
import p3_transistor_driver as TX
import p3_reference_pll_integrated_mos_link as LINK
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"scripts"))
import audit_physical_mos_ffe_coverage as AUDIT

ALPHAS=(0.,.30)
MODES=("ideal", "physical")
BITS=256

def circuit(bits,alpha,mode):
    deck=LINK.netlist(bits,alpha)
    if mode=="ideal":return deck
    if mode!="physical":raise ValueError(mode)
    lines=["* Independent physical CMOS TX predriver 2 stage buffers"]
    for weight in TX.WEIGHTS:
        for typ in ("GU","GD"):
            source=f"V{typ}{weight}"
            old=f"{source} {typ.lower()}{weight} 0 PWL"
            new=f"{source} pre_{typ.lower()}{weight} 0 PWL"
            if deck.count(old)!=1:
                raise ValueError(f"Cannot find unique PWL source {source}")
            deck=deck.replace(old,new,1)
            buf=f"buf{typ.lower()}{weight}"
            out=f"{typ.lower()}{weight}"
            inp=f"pre_{typ.lower()}{weight}"
            final_p=6+3*weight
            final_n=final_p/2
            lines.extend([
              f"XPDRV1_{typ}{weight} {buf} {inp} vdd vdd 0 pch_svt_1p8v width=4u length=.18u multi=1",
              f"XNDRV1_{typ}{weight} {buf} {inp} 0 0 nch_svt_1p8v width=2u length=.18u multi=1",
              f"XPDRV2_{typ}{weight} {out} {buf} vdd vdd 0 pch_svt_1p8v width={final_p:g}u length=.18u multi=1",
              f"XNDRV2_{typ}{weight} {out} {buf} 0 0 nch_svt_1p8v width={final_n:g}u length=.18u multi=1",
            ])
    if len(lines)!=1+8*4:raise AssertionError("TX MOS pre-driver count wrong")
    deck=deck.replace(".control","\n".join(lines)+"\n.control",1)
    deck=deck.replace("quit\n.endc",
        "wrdata physical_predriver_gates.csv time v(gu8) v(gd8) v(gu1) v(gd1)\nquit\n.endc",1)
    return deck

def audit(samples,bits):
    ui=TX.UI_PS*1e-12;t0=LINK.START_DATA_NS*1e-9
    sc=[]
    for d in samples:
        r=dict(d)
        r["raw_UI_floor"]=math.floor((r["physical_clock_sample_s"]-t0)/ui)
        r["raw_UI_round"]=round((r["physical_clock_sample_s"]-t0)/ui)
        sc.append(r)
    lag=min(range(-5,6),key=lambda l:(
       AUDIT.evaluate(sc,bits,l,18,90,"floor")["invalid_or_wrong_UI"],
       AUDIT.evaluate(sc,bits,l,18,90,"floor")["missing_UI"],abs(l)))
    return {"training_integer_lag":lag,
       "test":AUDIT.evaluate(sc,bits,lag,90,246,"floor")}

def main(out,mode,alpha):
    if mode not in MODES or alpha not in ALPHAS:raise ValueError
    out.mkdir(parents=True,exist_ok=True)
    label=f"{mode}_alpha_{alpha:.2f}".replace(".","p")
    work=TX.ENGINE_DIR/("p3_mos_tx_prebuffer_"+label)
    runner=TX.SpiceRunner(work)
    src=TX.model_path("tt");dst=work/src.name
    if not dst.exists() or src.stat().st_mtime>dst.stat().st_mtime:
        shutil.copy2(src,dst)
    bits=TX.prbs7(BITS)
    runner.run(circuit(bits,alpha,mode),label)
    wave=LINK.read(work/"pll_driven_rx_wave.csv")
    pll=LINK.frequency(wave)
    samples,original=LINK.evaluate(wave,bits,LINK.START_DATA_NS)
    heldout=audit(samples,bits)
    # Integral over the actual 256-bit data interval, NOT the 1.2us
    # PLL acquisition interval. Do not compare to silicon full budget.
    interval=[w for w in wave if w["time_s"]>=LINK.START_DATA_NS*1e-9]
    power={
        "PLL_plus_RX_plus_pMOS_prebuffer_1p8V_mW":
            LINK.time_weighted_power_mW(interval,"power_vdd_source_A",1.8),
        "TX_output_signal_supply_0p5V_mW":
            LINK.time_weighted_power_mW(interval,"power_tx_source_A",.5),
    }
    power["partial_sum_mW"]=sum(power.values())
    report={
       "mode":mode,"FFE_alpha":alpha,"n_tx_data_bits":BITS,
       "actual_transistor_predriver":mode=="physical",
       "physical_MOS":"DB HiTek 180nm NMOS 8:4:2:1 bank / optional CMOS buffer / RX latches / MOS switched CP+VCO",
       "reference_PLL":"XSPICE ideal 450MHz reference and 2-DFF PFD/4",
       "not_actual_original_2004_mux_driver":True,
       "fixed_two_pole_RC_channel_not_measured_RG58":True,
       "PLL_result":pll,"postrun_initial_score":original,
       "heldout_unique_UI_score":heldout,
       "partial_source_power":power,
       "gates_PWL_only_before_first_CMOS_buffer":mode=="physical",
       "not_total_27p12mW_silicon_power":True}
    (out/(label+".json")).write_text(json.dumps(report,indent=2)+"\n")
    with (out/(label+"_MOS_decisions.csv")).open("w",newline="") as f:
        w=csv.DictWriter(f,fieldnames=list(samples[0]))
        w.writeheader();w.writerows(samples)
    h=heldout["test"]
    print(f"PHYSICAL_TX_PREDRIVER mode={mode} alpha={alpha} "
          f"fVCO={pll['vco_GHz']:.9f}GHz "
          f"heldout_errors={h['invalid_or_wrong_UI']}/{h['expected_unique_bits']} "
          f"missing={h['missing_UI']} wrong={h['wrong_regenerated_UI']} "
          f"P_1p8V_mW={power['PLL_plus_RX_plus_pMOS_prebuffer_1p8V_mW']:.4f} "
          f"P_tx_0p5V_mW={power['TX_output_signal_supply_0p5V_mW']:.4f}",
          flush=True)
    return report

if __name__=="__main__":
    p=argparse.ArgumentParser()
    p.add_argument("--mode",choices=MODES,required=True)
    p.add_argument("--alpha",type=float,choices=ALPHAS,required=True)
    p.add_argument("--out",type=Path,default=Path("results/spice/p3_mos_TX_predriver"))
    a=p.parse_args()
    main(a.out,a.mode,a.alpha)
