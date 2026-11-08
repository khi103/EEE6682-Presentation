#!/usr/bin/env python3
"""Original, self-contained *behavioral* study of Wong et al., JSSC 2004.

NOT a device-level recreation, not the paper's measured RG58/FR4 S-parameters.
The channel is a matched-loss RC surrogate. All figures generated from simulation.
NRZ single-ended, 3.6 Gb/s, swing 250 mVpp, low-common-mode 250 mV.

Uses an explicitly constrained FFE (sum abs taps = 1). The paper's raw
pre-emphasis polynomial is 1 - alpha*z^-1, with an output-conductance design that
maintains approximately 50-ohm termination. Here, output voltage is constrained;
we do not simulate MOS driver segmentation or matching.
"""
import argparse
import json
from pathlib import Path

import numpy as np
from scipy.signal import lfilter
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

GBPS=3.6
BITRATE=GBPS*1e9
UI=1/BITRATE
OSR=32
DT=UI/OSR
VPP=0.250
VCM=0.250
LOSS_DB=12.0
RT_PS=110.0
SEED=3162004


def gaussian_kernel(rise_ps=RT_PS):
    # Gaussian step response: 10%-90% rise time = 2.5631*sigma.
    sigma_samples=rise_ps*1e-12/(2.563103*DT)
    side=int(np.ceil(5.5*sigma_samples))
    t=np.arange(-side,side+1,dtype=float)
    k=np.exp(-0.5*(t/sigma_samples)**2)
    return k/k.sum()


def fc_for_nyquist_loss(order=2, loss_db=LOSS_DB):
    # RC^order transfer |H|=(1+(f/fc)^2)^(-order/2)
    nyq=BITRATE/2
    fc=nyq/np.sqrt(10**(loss_db/(10*order))-1)
    return fc


def channel_db(freq, order=2, loss_db=LOSS_DB):
    fc=fc_for_nyquist_loss(order,loss_db)
    return -10.0*order*np.log10(1+(freq/fc)**2)


def channel_wave(samples, order=2, loss_db=LOSS_DB):
    fc=fc_for_nyquist_loss(order,loss_db)
    tau=1/(2*np.pi*fc)
    p=np.exp(-DT/tau)
    y=np.asarray(samples, dtype=float)
    for _ in range(order):
        y=lfilter([1-p],[1,-p],y)
    return y


def m_sequence(length):
    # PRBS7 polynomial x^7 + x^6 + 1, deterministic nonzero state.
    state=0x5d
    data=np.empty(length,dtype=np.int8)
    for k in range(length):
        data[k]=state&1
        feedback=((state>>6)^(state>>5))&1
        state=((state<<1)&0x7f)|feedback
    return data


def make_drive(bits,coeff, npre=0, rise_ps=RT_PS):
    # Noncausal pre-taps imply look-ahead: physically transmitted with an
    # npre-UI serialization delay; this model only compares pulse shapes.
    x=2*np.asarray(bits,dtype=float)-1.0
    nx=len(x)
    pad=np.pad(x,(len(coeff)+3,len(coeff)+3),mode='constant')
    v=np.zeros(nx)
    for j,c in enumerate(coeff):
        lag=j-npre
        start=len(coeff)+3-lag
        v += c*pad[start:start+nx]
    level=0.5*VPP*v
    analog=np.repeat(level,OSR)
    # Constant pre/post pad removes startup step artifacts during eye analysis.
    kernel=gaussian_kernel(rise_ps)
    analog=np.convolve(np.pad(analog,(len(kernel),len(kernel)),mode='edge'),kernel,mode='same')
    analog=analog[len(kernel):-len(kernel)]
    return analog


def simulate(bits, coeff, npre=0, order=2, loss_db=LOSS_DB, rise_ps=RT_PS):
    tx=make_drive(bits,coeff,npre,rise_ps)
    rx=channel_wave(tx,order,loss_db)
    return tx,rx


def eye_metrics(bits, rx, skip=80):
    # Pick the best phase and integral UI delay by worst-case vertical separation
    # between received ONE and ZERO symbols. No noise or BER inference.
    nbits=len(bits)
    good=(np.arange(nbits)>=skip)&(np.arange(nbits)<nbits-skip-5)
    best={'eye_v':-np.inf}
    by_lag={}
    for lag in range(5):
        n=np.flatnonzero(good & (np.arange(nbits)+lag<nbits))
        vmat=rx[((n+lag)*OSR)[:,None]+np.arange(OSR)[None,:]]
        marks=bits[n]
        pos=vmat[marks==1]
        neg=vmat[marks==0]
        vertical=np.min(pos,axis=0)-np.max(neg,axis=0)
        by_lag[lag]=vertical
        ip=int(np.argmax(vertical))
        if vertical[ip]>best['eye_v']:
            best={'eye_v':float(vertical[ip]),'lag':lag,'phase':ip,
                  'eye_width_ps':float(np.count_nonzero(vertical>0)*UI*1e12/OSR),
                  'phases_v':vertical.copy(),'mean_pos':float(pos[:,ip].mean()),
                  'mean_neg':float(neg[:,ip].mean())}
    return best


def impulse_response(coeff=(1.,),npre=0,order=2,loss_db=LOSS_DB,rise_ps=RT_PS):
    # Since convolution is linear, isolated NRZ bit excess amplitude is Vpp.
    bits=np.zeros(256,dtype=np.int8)
    index=55
    bits[index]=1
    _,rx0=simulate(np.zeros_like(bits),coeff,npre,order,loss_db,rise_ps)
    _,rx1=simulate(bits,coeff,npre,order,loss_db,rise_ps)
    return (rx1-rx0)/VPP,index


def sbr_cursors(h,index,lag,phase,kmin=-3,kmax=15):
    return {int(k):float(h[(index+lag+k)*OSR+phase]) for k in range(kmin,kmax+1)}


def zf_coefficients(channel_cursors,n_taps,n_pre):
    # Exactly the same *mathematical constraint* as the lecture's L.ffe_zf,
    # but this implementation is independently written and self-contained.
    span=np.arange(-n_pre,n_taps-n_pre)
    A=np.zeros((len(span),n_taps))
    for i in range(n_taps):
        for ri,k in enumerate(span):
            A[ri,i]=channel_cursors.get(int(k-i+n_pre),0.)
    target=(span==0).astype(float)
    try:
        raw=np.linalg.solve(A,target)
    except np.linalg.LinAlgError:
        raw=np.linalg.lstsq(A,target,rcond=None)[0]
    return raw/np.abs(raw).sum()


def theme():
    plt.rcParams.update({'font.size':10,'axes.titlesize':12,'axes.labelsize':10,
        'figure.facecolor':'white','axes.spines.top':False,'axes.spines.right':False,
        'savefig.facecolor':'white','savefig.bbox':'tight',
        'font.family':'DejaVu Sans'})


def draw_eye(ax,rx,metrics,caption,number=150):
    ph=metrics['phase']; lag=metrics['lag']
    # Trace every other PRBS window, centered about the chosen sample phase.
    for k in range(130,130+number,1):
        center=(k+lag)*OSR+ph
        a=center-OSR;b=center+OSR+1
        if a<0 or b>len(rx):continue
        xx=np.arange(-OSR,OSR+1)/OSR
        ax.plot(xx,1e3*(rx[a:b]+VCM),color='#287d99',lw=.55,alpha=.15)
    ax.axvline(0,c='#c77c29',lw=1.0,ls='--')
    ax.axhline(VCM*1e3,c='gray',lw=.6,ls=':')
    ax.set(xlim=(-1,1),ylim=(80,420),xlabel='Time relative to selected sample (UI)',ylabel='RX voltage (mV)',title=caption)
    ax.text(.03,.94,f"Worst-case eye: {max(metrics['eye_v'],0)*1e3:.1f} mV\nWidth: {metrics['eye_width_ps']:.0f} ps",transform=ax.transAxes,va='top',fontsize=9,
            bbox=dict(boxstyle='round',facecolor='white',alpha=.86,edgecolor='#c4c4c4'))
    ax.grid(alpha=.15)


def run(outdir:Path, nbits=2048):
    outdir.mkdir(exist_ok=True,parents=True)
    theme()
    bits=m_sequence(nbits)
    baseline=(1.,)
    paper_alpha=.30
    paper2=(1/(1+paper_alpha),-paper_alpha/(1+paper_alpha))
    cases={
      '1-tap, no FFE':(np.array(baseline),0),
      '2-tap, alpha=0.30':(np.array(paper2),0),
    }
    h,pi=impulse_response()
    t0,rx0=simulate(bits,baseline)
    metric0=eye_metrics(bits,rx0)
    hc=sbr_cursors(h,pi,metric0['lag'],metric0['phase'],kmin=-5,kmax=18)
    for n,p in [(3,1),(5,1),(9,2)]:
        co=zf_coefficients(hc,n,p)
        cases[f'{n}-tap ZF (lecture extension)']=(co,p)
    measures={}; curves={}; sig={}
    for name,(co,npre) in cases.items():
        tx,rx=simulate(bits,co,npre)
        met=eye_metrics(bits,rx)
        hp,ii=impulse_response(co,npre)
        cs=sbr_cursors(hp,ii,met['lag'],met['phase'],kmin=-5,kmax=18)
        main=float(cs[0]); isi=float(sum(abs(v) for k,v in cs.items() if k!=0))
        measures[name]={
          'taps':[float(v) for v in co],'n_pre':int(npre),'L1':float(sum(abs(co))),
          'max_possible_output_swing_mVpp':float(VPP*1e3),
          'DC_gain_signed_sum':float(sum(co)),
          'DC_run_amplitude_mVpp':float(VPP*abs(sum(co))*1e3),
          'worst_case_eye_height_mV':float(met['eye_v']*1e3),
          'positive_eye_height_mV':float(max(0,met['eye_v'])*1e3),
          'eye_width_ps':float(met['eye_width_ps']),
          'selected_sample_phase_UI':float(met['phase']/OSR),
          'sample_lag_UI':int(met['lag']),
          'main_cursor_mV':float(VPP*main*1e3),
          'sum_abs_other_cursors_mV':float(VPP*isi*1e3),
          'SBR_infinite_pattern_lower_bound_mV':float(VPP*(main-isi)*1e3),
          'sampled_cursors':{str(k):float(v) for k,v in cs.items()}
        }
        curves[name]={'met':met,'c':cs}
        sig[name]=(tx,rx)
        print(f"{name:32s} eye={met['eye_v']*1e3:7.2f} mV ",
              f"width={met['eye_width_ps']:7.1f} ps main={VPP*main*1e3:6.1f} mV ",
              f"ISI={VPP*isi*1e3:6.1f} mV taps={np.round(co,3)}")
    # Sweep alpha for fixed 2tap. The paper's source-termination behavior is NOT simulated.
    alphas=np.linspace(0,.8,41)
    sweep=[]
    for a in alphas:
        co=np.array([1.,-a])/(1+a)
        tx,rx=simulate(bits,co)
        mm=eye_metrics(bits,rx)
        sweep.append({'alpha':float(a),'eye_height_mV':float(mm['eye_v']*1e3),
                      'eye_width_ps':float(mm['eye_width_ps']),
                      'dc_swing_mVpp':float(VPP*1e3*(1-a)/(1+a)),
                      'main_coeff':float(co[0])})
    # 1-pole and 2-pole sensitivity at same 12 dB Nyquist loss
    sensitivity=[]
    for order in (1,2):
        for name,co in [('none',[1.]),('alpha=0.3',paper2)]:
            _,rr=simulate(bits,co,order=order)
            mt=eye_metrics(bits,rr)
            sensitivity.append(dict(order=order,label=name,eye_mV=float(mt['eye_v']*1e3),width_ps=float(mt['eye_width_ps'])))
    res={
      'source':'Independent behavioral simulation inspired by Wong et al., IEEE JSSC 2004',
      'not':'Not a transistor-level simulation or reproduction of measured 6.5m RG58 + 8cm FR4 S-parameters',
      'inputs':{'gbps':GBPS,'nrz':True,'single_ended':True,'output_swing_mVpp':VPP*1000,
        'common_mode_mV':VCM*1000,'nyquist_GHz':GBPS/2,'loss_at_nyquist_dB':LOSS_DB,
        'channel':'two cascaded RC low-pass poles (illustrative surrogate)',
        'channel_fc_GHz':fc_for_nyquist_loss(2)/1e9,
        'driver_rise_time_ps':RT_PS,'ui_ps':UI*1e12,'osr':OSR,'prbs':'PRBS7',
        'nbits':nbits,'noise_rms_mV':0,'output_normalization':'sum absolute coefficients = 1'},
      'paper_measured_reference':{'Fig_25_eq_alpha':0.3,'Fig_25_eye_height_mV':37,
        'Fig_25_eye_width_ps':189,'Fig_25_channel_loss_dB':12,
        'Table_IV_link_power_mW':27.12,'Fig_10_driver_impedance':'approx. 50 ohms, <10% variation'},
      'simulated_cases':measures,'alpha_sweep':sweep,'sensitivity':sensitivity,
      'limitations':['Unmeasured RC surrogate is not a cable/PCB S-parameter model.',
        'FFE is ideal; MOS driver output impedance and power are not modeled.',
        'No thermal noise, package parasitics, CDR, jitter or BER testing.',
        'PRBS7 and finite sample worst-case eye; results depend on channel assumption.',
        'Tap-count > 2 are lecture-inspired design extensions, not the P3 chip.']}
    (outdir/'p3_results.json').write_text(json.dumps(res,indent=2),encoding='utf-8')

    f=np.linspace(0,3e9,800)
    fig,ax=plt.subplots(figsize=(8.2,4.2))
    for order,color in [(1,'#9c7f63'),(2,'#126b86')]:
        ax.plot(f/1e9,channel_db(f,order),label=f'{order}-pole RC surrogate',lw=2,color=color)
    ax.axvline(1.8,color='#777',linestyle='--',linewidth=1)
    ax.axhline(-12,color='#777',linestyle=':',linewidth=1)
    ax.scatter([1.8],[-12],color='#d28b3e',zorder=5)
    ax.set(xlabel='Frequency (GHz)',ylabel='Channel magnitude |S21| (dB)',
        title='Illustrative loss-matched channels: -12 dB at 1.8 GHz',ylim=(-25,1))
    ax.grid(alpha=.2);ax.legend();fig.tight_layout();fig.savefig(outdir/'01_channel_loss.png',dpi=170);plt.close(fig)

    fig,axs=plt.subplots(1,2,figsize=(11.7,4.35),sharey=True)
    for ax,name in zip(axs,['1-tap, no FFE','2-tap, alpha=0.30']):
        draw_eye(ax,sig[name][1],curves[name]['met'],name)
    fig.suptitle('3.6 Gb/s NRZ eye at RX - ideal 12-dB two-pole RC surrogate (not Fig. 25 reproduction)',fontsize=12)
    fig.tight_layout();fig.savefig(outdir/'02_eye_before_after.png',dpi=170);plt.close(fig)

    fig,axs=plt.subplots(1,2,figsize=(11.7,4.1))
    av=np.array([s['alpha'] for s in sweep]);ey=np.array([s['eye_height_mV'] for s in sweep]);dc=np.array([s['dc_swing_mVpp'] for s in sweep]);ew=np.array([s['eye_width_ps'] for s in sweep])
    axs[0].plot(av,ey,color='#126b86',lw=2,label='signed worst-case eye')
    axs[0].axhline(0,color='gray',lw=1);axs[0].axvline(.3,color='#b88037',ls='--',label='paper alpha=0.3')
    axs[0].set(xlabel='2-tap alpha',ylabel='Eye height (mV)',title='Eye margin versus pre-emphasis');axs[0].legend(fontsize=8);axs[0].grid(alpha=.2)
    axs[1].plot(av,dc,color='#b88037',lw=2,label='DC run swing')
    axs[1].axhline(VPP*1e3,color='gray',ls=':',label='Peak-to-peak TX budget')
    axs[1].set(xlabel='2-tap alpha',ylabel='Swing (mVpp)',title='Normalization redistributes available TX swing')
    axs[1].legend(fontsize=8);axs[1].grid(alpha=.2)
    fig.tight_layout();fig.savefig(outdir/'03_alpha_tradeoff.png',dpi=170);plt.close(fig)

    names=list(cases); xs=np.arange(len(names)); hs=[measures[n]['worst_case_eye_height_mV'] for n in names]
    dcg=[measures[n]['DC_run_amplitude_mVpp'] for n in names]
    fig,axs=plt.subplots(1,2,figsize=(11.7,4.4))
    bars=axs[0].bar(xs,hs,color=['#a1aeb6','#bd8948','#35758a','#287d99','#1c9b94'])
    axs[0].axhline(0,color='gray',lw=1);axs[0].set(title='Signed eye height (negative = closed)',ylabel='Eye height (mV)',xticks=xs,xticklabels=['1','2','3','5','9']);axs[0].set_xlabel('Number of TX FFE taps');axs[0].grid(axis='y',alpha=.2)
    axs[1].plot(xs,dcg,'o-',color='#bd8948',lw=2)
    axs[1].set(title='DC run swing under constant peak budget',ylabel='DC swing (mVpp)',xlabel='Number of TX FFE taps',xticks=xs,xticklabels=['1','2','3','5','9']);axs[1].grid(alpha=.2)
    fig.suptitle('1/2 taps: P3 concept | 3/5/9 taps: lecture-style extension; identical 250-mVpp peak budget',fontsize=11)
    fig.tight_layout();fig.savefig(outdir/'04_tap_count_tradeoff.png',dpi=170);plt.close(fig)

    fig,axs=plt.subplots(1,2,figsize=(11.7,4.2))
    for name,color in [('1-tap, no FFE','#a1aeb6'),('2-tap, alpha=0.30','#bd8948'),('3-tap ZF (lecture extension)','#126b86')]:
        cs=curves[name]['c']; kk=np.arange(-2,11)
        axs[0].plot(kk,[VPP*cs.get(int(k),0)*1e3 for k in kk],marker='o',label=name,lw=1.5,markersize=4,color=color)
    axs[0].set(xlabel='Cursor lag (UI)',ylabel='Sampled pulse cursor (mV)',title='RX single-bit response samples');axs[0].axhline(0,color='gray',lw=.6);axs[0].legend(fontsize=7);axs[0].grid(alpha=.2)
    for i,name in enumerate(list(cases)[1:]):
        co=cases[name][0]; npre=cases[name][1]; idx=np.arange(len(co))-npre
        axs[1].plot(idx,co,marker='o',lw=1.5,markersize=4,label=name)
    axs[1].set(xlabel='FFE tap index (0 = main)',ylabel='Coefficient',title='Tap weights; sum of absolute values = 1');axs[1].axhline(0,color='gray',lw=.6);axs[1].grid(alpha=.2);axs[1].legend(fontsize=7)
    fig.tight_layout();fig.savefig(outdir/'05_sbr_and_taps.png',dpi=170);plt.close(fig)

    fig,ax=plt.subplots(figsize=(8.2,4.2))
    groups=np.arange(2); w=.34
    va=[];vb=[]
    for order in (1,2):
        d=[v for v in sensitivity if v['order']==order]
        va.append(next(v['eye_mV'] for v in d if v['label']=='none'))
        vb.append(next(v['eye_mV'] for v in d if v['label']=='alpha=0.3'))
    ax.bar(groups-w/2,va,width=w,color='#a1aeb6',label='No FFE')
    ax.bar(groups+w/2,vb,width=w,color='#126b86',label='2-tap alpha=0.3')
    ax.axhline(0,color='gray',lw=.7)
    ax.set(xticks=groups,xticklabels=['1-pole RC','2-pole RC'],ylabel='Signed eye height (mV)',title='Sensitivity: identical 12-dB Nyquist loss, different channel phase/tail')
    ax.grid(axis='y',alpha=.15);ax.legend();fig.tight_layout();fig.savefig(outdir/'06_channel_sensitivity.png',dpi=170);plt.close(fig)
    print('Created',outdir)
    return res


def main():
    ap=argparse.ArgumentParser()
    ap.add_argument('--out',type=Path,default=Path(__file__).resolve().parent.parent/'results')
    ap.add_argument('--nbits',type=int,default=2048)
    args=ap.parse_args()
    run(args.out,args.nbits)

if __name__=='__main__':main()
