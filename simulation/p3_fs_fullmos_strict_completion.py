#!/usr/bin/env python3
"""Correct a hidden incomplete transient in full 3.6-Gb/s MOS PVT link.

The earlier full-MOS five-corner benchmark (Actions 43250910117)
returned status='simulated' for FS, FFE alpha=0.30 despite
actual MOS analog waveform ending at 1313.22ns while the declared
512-symbol burst must complete near 1362.22ns. Missing late samples
were then incorrectly counted as 168 RX errors. A simulator's
exit code / job PASS is NOT a functional full-burst success.

This regression explicitly verifies actual SPICE waveform end time
before calculating ANY full-packet receiver error count, and screens
the same FS-corner reconstructed 180nm MOS TX + full CMOS predriver,
diode-biased MOS reference PLL, two physical MOS RX latches and
physical MOS clock delay under selected clock biases and solver
integration settings. All are still independently sized circuits,
not original 2004 silicon or measured BER.
"""
from __future__ import annotations
import argparse,csv,json,math,shutil,traceback
from pathlib import Path
import p3_transistor_driver as TX
import p3_full_mos_process_ffe_link as LINK_PVT
import p3_reference_pll_integrated_mos_link as LINK
import p3_mos_tx_predriver as PRE
import p3_long_predriver_prbs31 as LONG
import p3_mos_rx_offset_stress as AUDIT

CORNERS=("fs","tt")
ALPHAS=(0.,0.30)
BIASES=(.95,1.10,1.25)
SOLVERS=("default","gear")
BITS=512
TOLERANCE_NS=.20
SEED=0x54C4EE17

def build(bits,corner,alpha,bias,solver):
    old=LINK_PVT.BIAS
    try:
        LINK_PVT.BIAS=bias
        deck=LINK_PVT.netlist(bits,corner,alpha)
    finally:
        LINK_PVT.BIAS=old
    if solver=="gear":
        deck=deck.replace(".control",
            ".options method=gear reltol=.002 gmin=1e-12\n.control",1)
    return deck

def run(out,corner,alpha,bias,solver):
    if corner not in CORNERS or alpha not in ALPHAS or bias not in BIASES or solver not in SOLVERS:
        raise ValueError
    out.mkdir(parents=True,exist_ok=True)
    tag=f"{corner}_alpha{alpha:.2f}_bias{bias:.2f}_{solver}".replace(".","p")
    working=TX.ENGINE_DIR/("p3_fs_strict_completion_"+tag)
    engine=PRE.TXGateLargeRunner(working)
    model=TX.model_path(corner);dst=working/model.name
    if not dst.exists() or model.stat().st_mtime>dst.stat().st_mtime:
        shutil.copy2(model,dst)
    expected_ns=LINK.START_DATA_NS + BITS*TX.UI_PS*1e-3 + LINK.DATA_END_DELAY_NS
    info={
      "corner":corner,"FFE_alpha":alpha,"RX_physical_delay_bias_V":bias,
      "solver":solver,"physical_MOS_reconstruction":True,
      "expected_transient_end_ns":expected_ns,
      "full_burst_completed":False,
      "full_packet_MOS_RX_scoring_valid":False,
      "original_silicon_and_ber_reproduced":False,
    }
    oldbits=LINK.BITS
    try:
        LINK.BITS=BITS
        bits=LONG.prbs31(BITS,seed=SEED)
        engine.run(build(bits,corner,alpha,bias,solver),tag)
        wave=LINK.read(working/"pll_driven_rx_wave.csv")
        last_ns=wave[-1]["time_s"]*1e9
        info["actual_transient_end_ns"]=last_ns
        info["full_burst_completed"]=last_ns>=expected_ns-TOLERANCE_NS
        info["initial_waveform_samples"]=len(wave)
        if not info["full_burst_completed"]:
            info.update({
              "status":"TRUNCATED_TRANSIENT_NOT_A_VALID_FULL_PACKET",
              "reason":f"Actual waveform ended at {last_ns:.6f}ns < expected {expected_ns:.6f}ns",
            })
        else:
            pll=LINK.frequency(wave)
            samples,raw=LINK.evaluate(wave,bits,LINK.START_DATA_NS)
            hold=AUDIT.score(samples,bits)
            info.update({"status":"COMPLETE",
              "full_packet_MOS_RX_scoring_valid":True,
              "PLL":pll,"sample_coverage":hold,
              "full_received_MOS_clocks":len(samples),
              "raw_RX_score":raw})
            with (out/(tag+"_MOS_decisions.csv")).open("w",newline="") as f:
                w=csv.DictWriter(f,fieldnames=list(samples[0]))
                w.writeheader();w.writerows(samples)
        # Decimate actual continuous RX clock and PAD voltage to identify
        # whether phase error, solver stiffness, or insufficient latch headroom.
        focus=[x for x in wave if x["time_s"]>=LINK.START_DATA_NS*1e-9]
        if focus:
            with (out/(tag+"_analog_diagnostic.csv")).open("w",newline="") as f:
                columns=["time_s","rx_V","clkeven_V","clkodd_V","vco_V"]
                w=csv.DictWriter(f,fieldnames=columns)
                w.writeheader()
                w.writerows([{k:z[k] for k in columns} for z in focus[::max(1,len(focus)//6000)]])
    except Exception as exc:
        info.update({"status":"SPICE_OR_PARSE_FAILURE",
          "error":f"{type(exc).__name__}: {str(exc)[-1400:]}"})
    finally:
        LINK.BITS=oldbits
    (out/(tag+".json")).write_text(json.dumps(info,indent=2)+"\n")
    h=info.get("sample_coverage",{}).get("holdout",{})
    print(f"STRICT_FULLMOS_FS corner={corner} alpha={alpha} clock_bias={bias} "
          f"solver={solver} status={info['status']} "
          f"last_ns={info.get('actual_transient_end_ns')} "
          f"complete={info['full_burst_completed']} "
          f"correctly_scored={info['full_packet_MOS_RX_scoring_valid']} "
          f"holdout_invalid={h.get('invalid_or_wrong_UI')}/{h.get('expected_unique_bits')} "
          f"missing={h.get('missing_UI')} wrong={h.get('wrong_regenerated_UI')} "
          f"unresolved={h.get('unresolved_UI')}",flush=True)
    return info

if __name__=="__main__":
    p=argparse.ArgumentParser()
    p.add_argument("--corner",choices=CORNERS,required=True)
    p.add_argument("--alpha",type=float,choices=ALPHAS,required=True)
    p.add_argument("--bias",type=float,choices=BIASES,required=True)
    p.add_argument("--solver",choices=SOLVERS,required=True)
    p.add_argument("--out",type=Path,default=Path("results/spice/p3_FS_MOS_strict_completion"))
    a=p.parse_args()
    run(a.out,a.corner,a.alpha,a.bias,a.solver)
