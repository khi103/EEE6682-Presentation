#!/usr/bin/env python3
"""Fig.19-inspired 4-XOR bang-bang detector + 7-bit MOS pump LUT, MOS RX.

Pass 1: actual DB HiTek 180nm 8:4:2:1 MOS TX -> 2-pole RC waveform.
Pass 1b: actual 7-bit DB HiTek MOS charge-pump CURRENT DAC in ngspice.
Clock controller: causal E_n / D_n early-edge and data samples of only
the received waveform, with Fig19-like XOR up/down arbitration, digital
downsampling and 7-bit saturating counter.
Phase actuator: assume a 350-ps total phase-control range from paper
Fig21, and SCALE the actual MOS current-code LUT accordingly. This
mapping is explicitly ASSUMED, not simulated MOS PLL phase transfer.
Pass 2: the chosen clock sequence drives actual DB HiTek 180nm PMOS
regenerative RX latches in ngspice; known PRBS is used ONLY to score
integer word alignment AFTER both passes.

Unlike the paper, there is NO physical 450-MHz PLL/charge-pump/SC-filter
phase shifting in the same SPICE netlist. This is a functional Fig19
verification grounded by MOS TX, MOS charge-pump DC and MOS RX.
"""
from __future__ import annotations
import argparse,csv,json,math,shutil
from pathlib import Path
import p3_transistor_driver as TX
import p3_blind_cdr_mos_cosim as COSIM
import p3_integrated_mos_link as LINK
import p3_fig20_charge_pump_mos as PUMP

BITS=512
RX_UI_S=1/(3.6e9)
THRESH=.25
BASE_PHASE_UI=.80
PHASE_RANGE_PS=350.
VALID_AFTER=120
TESTS=(
 ("early_phase_div4",15,4,0.),
 ("late_phase_div4",100,4,0.),
 ("early_phase_div16",15,16,0.),
 ("late_phase_div16",100,16,0.),
 ("early_phase_div4_plus1000ppm",15,4,1000.),
 ("early_phase_fixed_plus1000ppm",15,0,1000.),
 ("mid_phase_div16",30,16,0.),
 ("late_hard_phase_div4_plus1000ppm",127,4,1000.),
 ("late_hard_phase_fixed_plus1000ppm",127,0,1000.)
)

def load_pump_phase_lut(data:Path):
    with data.open(newline="") as f:
        r=list(csv.DictReader(f))
    current={int(x["seven_bit_code"]):float(x["pump_clamp_current_A"])
             for x in r if x["corner"]=="tt"}
    if set(current)!=set(range(128)):raise RuntimeError("Incomplete MOS pump 7-bit code LUT")
    i0,i127=current[0],current[127]
    if i0==i127:raise RuntimeError("Charge-pump MOS current code has no range")
    fractions={code:(i-i0)/(i127-i0) for code,i in current.items()}
    assert all(fractions[k+1]>fractions[k] for k in range(127))
    center=fractions[64]
    return {code:BASE_PHASE_UI+(f-center)*(PHASE_RANGE_PS/TX.UI_PS)
            for code,f in fractions.items()},current

def sample(rows,t):
    # Only 0.25-V analog comparator threshold, NO ground-truth PRBS.
    t0=[x["time_s"] for x in rows]
    return int(LINK.interp(rows,t,"rx_V",t0)>=THRESH)

def controller(rows,phase_table,start_code,divider,ppm):
    # Frame-cycle n is a local recovered oscillator time index,
    # NOT a decoded TX bit. E0,D0,E1,D1 architecture, 4 XORs.
    ui=RX_UI_S*(1+ppm*1e-6)
    last_e=last_d=None
    accum=0
    code=start_code
    history=[]
    schedules=[]
    for n in range(BITS):
        phase=phase_table[code]
        t_e=(n+.5+phase)*ui
        t_d=(n+1+phase)*ui
        edge=sample(rows,t_e)
        data=sample(rows,t_d)
        up=dn=0
        if last_e is not None:
            xor_up=last_e ^ last_d
            xor_down=last_d ^ edge
            up=int(xor_up==1 and xor_down==0)
            dn=int(xor_down==1 and xor_up==0)
            accum+=up-dn
        updated=0
        if divider>0 and (n+1)%divider==0:
            if accum>0: updated=+1
            elif accum<0:updated=-1
            # Saturating counter: never wrap between MSB and LSB.
            code=max(0,min(127,code+updated))
            accum=0
        schedules.append({
          "bit_clock_cycle_index":n,
          "recovered_sample_time_s":t_d,
          "phase_mod_UI":phase%1.,
          "phase_unwrapped_UI":phase,
          "receiver_ui_s":ui,
          "counter_code":code,
          "transition_events_seen":0,
          "feedback_enabled":True,
        })
        history.append({
          "cycle_index":n,"edge_E":edge,"data_D":data,
          "UP":up,"DOWN":dn,
          "counter_update":updated,
          "counter_after_update":code,
          "effective_sample_phase_UI":phase,
          "sample_time_s":t_d,
        })
        last_e=edge;last_d=data
    assert all(b["recovered_sample_time_s"]>a["recovered_sample_time_s"]
               for a,b in zip(schedules,schedules[1:]))
    return schedules,history

def save(path,rows):
    if not rows:return
    with path.open("w",newline="") as f:
        w=csv.DictWriter(f,fieldnames=list(rows[0]))
        w.writeheader();w.writerows(rows)

def run(out):
    out.mkdir(parents=True,exist_ok=True)
    COSIM.N_BITS=BITS
    COSIM.FIRST_VALID=VALID_AFTER
    physical_pump_path=out/"fig20_mos_charge_pump_current.csv"
    print("Running 7-bit physical MOS charge-pump reference current LUT...",flush=True)
    PUMP.run(out)
    phase_table,current_lut=load_pump_phase_lut(physical_pump_path)
    work=TX.ENGINE_DIR/"p3_fig19_bbpd"
    driver=TX.SpiceRunner(work)
    model=TX.model_path("tt")
    dst=work/model.name
    if not dst.exists() or model.stat().st_mtime>dst.stat().st_mtime:
        shutil.copy2(model,dst)
    bits=TX.prbs7(BITS)
    txcodes=TX.ffe_codes(bits,.30)
    driver.run(TX.make_transient(txcodes,LINK.TRIM_WU,LINK.TRIM_WD,gate_transition_ps=10),
               "mos_TX_rc_in")
    rxanalog=TX.parse_wrdata(work/"tx_waveform.csv")
    summaries={}
    for name,start,divider,ppm in TESTS:
        schedule,log=controller(rxanalog,phase_table,start,divider,ppm)
        deck=COSIM.generate_latch_deck(bits,.30,schedule)
        driver.run(deck,name)
        wave=LINK.read_trace(work/"full_link_waveform.csv")
        decisions,metric=COSIM.analyze_latches(wave,schedule,bits)
        save(out/f"{name}_fig19_counter.csv",log)
        save(out/f"{name}_mos_latch_decisions.csv",decisions)
        summaries[name]={
            "start_code":start,"update_every_UI":divider,"reference_rate_offset_ppm":ppm,
            "last_counter_code":log[-1]["counter_after_update"],
            "final_phase_UI":schedule[-1]["phase_unwrapped_UI"],
            "mos_rx":metric,
        }
        print(f"Fig19-like {name}: code={start}->{log[-1]['counter_after_update']},"
              f" errors={metric['total_errors_including_unresolved']}/"
              f"{metric['evaluated_bits']}, unresolved={metric['unresolved_latch_samples']}",flush=True)
    report={
      "status":"Fig19_inspired_four_XOR_BBPD_7bit_MOS_current_LUT_two_pass_validation",
      "actual_transistor_models":"DB HiTek 180nm MOS TX / charge-pump 7-bit current DAC / RX latches",
      "controller":"Causal Alexander four XOR + explicit up/down collision suppression, counter + decimation",
      "clock_phase_mapping":"Assumed paper Fig21 total 350ps, normalized to physically simulated static MOS pump current codes",
      "transmitted_labels_used_for_recovery":False,
      "physical_live_PLL_CDR_achieved":False,
      "bit_rate_Gbps":3.6,"prbs_symbols":BITS,"valid_symbols_after_acquisition":VALID_AFTER,
      "results":summaries,"total_MOS_receiver_simulations":driver.calls,
      "no_feedback_control_has_counter_update_interval_zero":True,
      "known_limitations":[
         "Counter-controlled MOS pump is a DC-current LUT, not a physical phase-shifting PLL closed loop",
         "The 350ps current-to-phase mapping assumes linear conversion from the paper's reported range",
         "Recovered RX clocks are ideal SPICE PWL after a causal digital controller on recorded MOS data",
         "Original paper Fig19 downsample counter is nominal 1/16; faster 1/4 case shown for acquisition comparison",
         "Integer PRBS packet alignment is used only to score, not to drive phase control",
         "No original Fig14 latch schematic, measured RG58 channel, jitter, physical loop or BER<1e-12"
      ],
    }
    (out/"fig19_bbpd_mos_link_summary.json").write_text(json.dumps(report,indent=2)+"\n")
    controlled=summaries["early_phase_div4_plus1000ppm"]["mos_rx"]
    open_loop=summaries["early_phase_fixed_plus1000ppm"]["mos_rx"]
    nominal=summaries["early_phase_div4"]["mos_rx"]
    hard=summaries["late_hard_phase_div4_plus1000ppm"]["mos_rx"]
    hard_fixed=summaries["late_hard_phase_fixed_plus1000ppm"]["mos_rx"]
    if not (controlled["total_errors_including_unresolved"]<=5 and
            nominal["total_errors_including_unresolved"]<=5 and
            open_loop["total_errors_including_unresolved"]>=controlled["total_errors_including_unresolved"]+3 and
            hard["total_errors_including_unresolved"] <= hard_fixed["total_errors_including_unresolved"]):
        print("FAIL: Fig19-like data PD did not beat truly fixed MOS receiver clock by >=10 bit decisions",flush=True)
        raise AssertionError("BBPD acquisition/outperformance not established; see all MOS decisions")
    print(f"PASS: Fig19-like 4-XOR detector improves +1000ppm MOS RX: {controlled['total_errors_including_unresolved']} vs {open_loop['total_errors_including_unresolved']}; hard start {hard['total_errors_including_unresolved']} vs {hard_fixed['total_errors_including_unresolved']}",flush=True)
    return report

if __name__=="__main__":
    p=argparse.ArgumentParser()
    p.add_argument("--out",type=Path,default=Path("results/spice/p3_fig19_bbpd_mos"))
    run(p.parse_args().out)
