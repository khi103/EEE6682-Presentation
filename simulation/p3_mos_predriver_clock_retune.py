#!/usr/bin/env python3
"""Physical MOS-TX gate predriver plus tunable physical MOS RX clock delay.

A 2-stage CMOS TX gate driver was shown to consume extra switching
power and erase the original FFE benefit under the SAME fixed
reference-PLL RX clock. This independent follow-up inserts a physical
2-stage current-starved MOS clock phase actuator into that full
transistor simulation and tests whether retiming the receiver can
recover the missing FFE margin. The bias is set externally per run,
NOT chosen by real-data BBPD in the circuit. TX clock, channel,
reference PLL, TX predriver, RX latch all remain on one SPICE netlist.

The reconstructed gate drivers and clock phase shifter are NOT the
author's 2004 circuit or proof of silicon-level power/BER.
"""
from __future__ import annotations
import argparse,csv,json,shutil
from pathlib import Path
import p3_transistor_driver as TX
import p3_reference_pll_integrated_mos_link as LINK
import p3_mos_physical_phase_delay as DELAY
import p3_mos_tx_predriver as PRE

ALPHAS=(0.,.3)
BIASES=(.95,1.1,1.25)

def build(bits,alpha,bias):
    base=PRE.circuit(bits,alpha,"physical")
    # Extract ONLY the independently sized physical starved-MOS clock
    # buffer cells and static gate biases (not the testbench or TX data).
    ref,_=DELAY.build(bits,bias,0.)
    mark="* Two physical current-starved MOS inverter clock delay stages"
    if ref.count(mark)!=1:raise RuntimeError("Delay MOS block not found")
    extra=mark+ref.split(mark,1)[1].split(".control",1)[0]
    oldp="XPCLK_E clkeven n1 vdd vdd 0 pch_svt_1p8v"
    oldn="XNCLK_E clkeven n1 0 0 nch_svt_1p8v"
    if base.count(oldp)!=1 or base.count(oldn)!=1:
        raise RuntimeError("Unable to find original physical clock inverters")
    base=base.replace(oldp,"XPCLK_E clkeven ph2 vdd vdd 0 pch_svt_1p8v",1)
    base=base.replace(oldn,"XNCLK_E clkeven ph2 0 0 nch_svt_1p8v",1)
    return base.replace(".control",extra+"\n.control",1)

def main(out,bias,alpha):
    if bias not in BIASES or alpha not in ALPHAS:raise ValueError
    out.mkdir(parents=True,exist_ok=True)
    label=f"alpha_{alpha:.2f}_vctrl_{bias:.2f}".replace(".","p")
    work=TX.ENGINE_DIR/("p3_physical_tx_driver_and_mos_phase_"+label)
    sim=PRE.TXGateLargeRunner(work)
    src=TX.model_path("tt");copy=work/src.name
    if not copy.exists() or src.stat().st_mtime>copy.stat().st_mtime:
        shutil.copy2(src,copy)
    bits=TX.prbs7(PRE.BITS)
    result={"alpha":alpha,"external_physical_MOS_delay_bias_V":bias,
       "physical_TX_gate_prebuffers":True,"physical_RX_clock_delay_MOS_stages":2,
       "actual_data_CDR":False,"sample_clock_source":"physical 450MHz reference PLL MOS VCO and static transistor delay",
       "not_original_P3_2004_circuit":True}
    try:
        sim.run(build(bits,alpha,bias),label)
        rows=LINK.read(work/"pll_driven_rx_wave.csv")
        pll=LINK.frequency(rows)
        samples,orig=LINK.evaluate(rows,bits,LINK.START_DATA_NS)
        audit=PRE.audit(samples,bits)
        focus=[x for x in rows if x["time_s"]>=LINK.START_DATA_NS*1e-9]
        power={
          "partial_1p8V_PLL_RX_TX_buffer_clock_mW":
             LINK.time_weighted_power_mW(focus,"power_vdd_source_A",1.8),
          "partial_0p5V_TX_signal_mW":
             LINK.time_weighted_power_mW(focus,"power_tx_source_A",.5),
        }
        result.update({"status":"simulated","pll":pll,
                       "postrun_latch_score":orig,"heldout":audit,
                       "partial_source_power":power})
        with (out/(label+"_MOS_latch_decisions.csv")).open("w",newline="") as f:
            w=csv.DictWriter(f,fieldnames=list(samples[0]))
            w.writeheader();w.writerows(samples)
    except Exception as exc:
        result.update({"status":"simulation_or_readout_failed",
                       "error":f"{type(exc).__name__}: {str(exc)[-900:]}"})
    (out/(label+".json")).write_text(json.dumps(result,indent=2)+"\n")
    a=result.get("heldout",{}).get("test",{})
    print(f"PHYSICAL_PREDRIVER_CLOCK_RETUNE alpha={alpha} delay_bias={bias} "
          f"status={result['status']} errors={a.get('invalid_or_wrong_UI')}/"
          f"{a.get('expected_unique_bits')} missing={a.get('missing_UI')} "
          f"wrong={a.get('wrong_regenerated_UI')} "
          f"PLL_GHz={result.get('pll',{}).get('vco_GHz')}",flush=True)
    return result

if __name__=="__main__":
    p=argparse.ArgumentParser()
    p.add_argument("--bias",type=float,choices=BIASES,required=True)
    p.add_argument("--alpha",type=float,choices=ALPHAS,required=True)
    p.add_argument("--out",type=Path,default=Path("results/spice/p3_mos_predriver_clock_retune"))
    args=p.parse_args()
    main(args.out,args.bias,args.alpha)
