"""Sanity tests for the independently written behavioral simulator."""
import importlib.util
from pathlib import Path
import numpy as np
P=Path(__file__).resolve().parents[1]/'simulation'/'p3_reproduce.py'
spec=importlib.util.spec_from_file_location('p3_reproduce',P)
m=importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)

def test_prbs7_period():
    b=m.m_sequence(254)
    assert np.array_equal(b[:127],b[127:])
    assert len(np.unique(b))==2

def test_matched_loss():
    for order in (1,2):
        assert abs(m.channel_db(np.array([1.8e9]),order)[0]+12)<1e-10

def test_ffe_voltage_budget():
    a=.3
    c=np.array([1.,-a])/(1+a)
    assert abs(np.abs(c).sum()-1)<1e-12
    assert np.max(np.abs(m.make_drive(m.m_sequence(127),c))) <= m.VPP/2+1e-9

def test_equalization_and_zero_forcing():
    bits=m.m_sequence(1024)
    _,base=m.simulate(bits,[1.])
    _,eq=m.simulate(bits,[1/1.3,-.3/1.3])
    eye_b=m.eye_metrics(bits,base)
    eye_e=m.eye_metrics(bits,eq)
    assert eye_e['eye_v']>eye_b['eye_v']
    assert eye_e['eye_v']>0
    h,i=m.impulse_response()
    cs=m.sbr_cursors(h,i,eye_b['lag'],eye_b['phase'],kmin=-5,kmax=18)
    for n,p in [(3,1),(5,1),(9,2)]:
        coeff=m.zf_coefficients(cs,n,p)
        assert len(coeff)==n
        assert np.isfinite(coeff).all()
        assert abs(np.abs(coeff).sum()-1)<1e-10
