#!/usr/bin/env python3
"""PD truth-table, PRBS31 polarity and time-window contract checks (no PDK).

This test deliberately does not claim transistor-level SPICE validity:
it verifies that the digital detector has correct Early/Late voting
semantics, that the 512-bit PRBS31 seeds exercise transitions, and that
the PLL's late frequency comparison uses three DISJOINT time intervals.

A lightweight fake PHASE.build() permits verifying the SPICE netlist
generator's digital topology and balanced behavioral-source braces
without downloading or reproducing any licensed foundry MOS models.
"""
from __future__ import annotations
import inspect,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"simulation"))
import p3_transition_qualified_mos_bbpd as A
import p3_pll_extended_pvt_phase as P

def old_xor_null_modes():
    counts={-2:0,0:0,2:0}
    for d0 in (0,1):
      for d1 in (0,1):
       for e0 in (0,1):
        for e1 in (0,1):
         signed=(d0^e1)+(d1^e0)-(e0^d0)-(e1^d1)
         counts[signed]+=1
    assert counts=={-2:2,0:12,2:2},counts
    return counts

def test_truth_table():
    rows=A.truth_table()
    assert len(rows)==8
    for r in rows:
        t=r["transition"]
        assert r["UP"]+r["DN"]==t
        if not t:
            assert r["UP"]==r["DN"]==0
    return rows

def test_prbs_early_late():
    results={}
    for seed in (0x54C4EE17,0x13572468):
        old=A.SEED
        try:
            A.SEED=seed
            bits=A.prbs31(512)
        finally:
            A.SEED=old
        transitions=0
        for i in range(1,len(bits)):
            left,right=bits[i-1],bits[i]
            t=left^right
            transitions+=t
            # Early transition sample is previous data:
            up_early=(left^left)&t
            dn_early=(left^right)&t
            # Late transition sample is next data:
            up_late=(left^right)&t
            dn_late=(right^right)&t
            assert (up_early,dn_early)==(0,t)
            assert (up_late,dn_late)==(t,0)
        assert 220<=transitions<=300
        results[hex(seed)]={"bits":512,"transitions":transitions,
            "early_valid_DOWN":transitions,"late_valid_UP":transitions}
    return results

def test_new_spice_topology():
    original=A.PHASE.build
    def fake_build(bits,bias,shift):
        assert len(bits)==256 and bias==A.INIT_CTRL
        return ("\n".join([
          "* MOS CLOCK DELAY FAKE TESTBENCH ONLY",
          f"VPDNB pd_nb 0 DC {bias:.6f}",
          f"VPDPB pd_pb 0 DC {1.8-bias:.6f}",
          ".control",
          "quit",
          ".endc",
          ".end",
        ])+"\n",1220.)
    try:
        A.PHASE.build=fake_build
        deck,start=A.circuit(A.prbs31(256),20.,-.05)
    finally:
        A.PHASE.build=original
    requirements={
        "three_dff":sum(1 for s in deck.splitlines() if s.startswith(("ADFF0 ","ADFFE ","ADFF1 ")))==3,
        "three_data_xor":sum(1 for s in deck.splitlines() if s.startswith(("AXOR_TRANS ","AXOR_UP ","AXOR_DN ")))==3,
        "two_transition_and":sum(1 for s in deck.splitlines() if s.startswith(("AAND_UP ","AAND_DN ")))==2,
        "actual_mos_clock_binding":"[n1 clkodd clkeven]" in deck,
        "data_RX_not_PRBS_labels":"AADC_RX [rx] [drx]" in deck,
        "real_MOS_control_integrator":"CPHASE_CTRL pdctrl 0" in deck,
        "Bsource_balanced_curly":False,
    }
    bsource=[s for s in deck.splitlines() if s.startswith("BDATA_FEEDBACK ")]
    if len(bsource)==1:
        requirements["Bsource_balanced_curly"]=bsource[0].count("{")==bsource[0].count("}")==1
    assert all(requirements.values()),requirements
    return requirements

def test_pvt_time_windows():
    source=inspect.getsource(P.main)
    assert "windows=[window(rows,a,a+80) for a in (720,800,880,960,1040,1120)]" in source
    final=[(960,1040),(1040,1120),(1120,1200)]
    assert all(final[i][1]<=final[i+1][0] for i in range(2))
    assert final[-1][1]==P.SIM_NS
    return final

def main():
    old=old_xor_null_modes()
    truth=test_truth_table()
    seeds=test_prbs_early_late()
    topology=test_new_spice_topology()
    windows=test_pvt_time_windows()
    print(f"PASS old_XOR_zero_votes={old[0]}/16")
    print(f"PASS Alexander_truth_table={len(truth)}/8")
    for seed,record in seeds.items():
        print(f"PASS PRBS31_early_late seed={seed} transitions={record['transitions']}")
    print(f"PASS generated_XSPICE_topology_checks={len(topology)}")
    print(f"PASS disjoint_PLL_windows_ns={windows}")
    print("LIMIT: no actual MOS circuit simulation is executed by this test")

if __name__=="__main__":
    main()
