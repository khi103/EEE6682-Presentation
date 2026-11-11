# P3 DB HiTek 180 nm 출력 드라이버: 실제 ngspice 검증 기록

**검증일:** 2026-11-11
**실행:** [GitHub Actions (성공)](https://github.com/khi103/EEE6682-Presentation/actions/runs/42999847513)
**원 논문:** K.-L. J. Wong et al., "A 27-mW 3.6-Gb/s I/O Transceiver," IEEE JSSC, vol. 39, no. 4, pp. 602-612, 2004.
**중요:** 본 결과는 논문 Fig. 7을 참조한 **독립적인 NMOS 드라이버 재구성 회로**의 결과이지 원 저자 칩의 설계 데이터가 아니다.

## 1. 실제 사용한 회로와 소자

- **PDK:** DB HiTek 0.18 um, 1.8 V SVT NMOS `nch_svt_1p8v`를 사용. 0.5 V 신호 공급, 1.8 V 이상적 게이트 제어.
- **구조:** 8:4:2:1 가중치 뱅크 4개. 각 뱅크의 Pull-up NMOS와 Pull-down NMOS 중 하나를 켜서 16개 출력 레벨을 만든다. 출력 노드 PAD는 50 ohm으로 VREF=0.25 V에 종단한다.
- **디바이스 규모:** TT, 27°C에서 50 ohm에 맞추기 위해 각 단위 NMOS 폭을 1.4896875 um로 보정하고 `multi=8/4/2/1`을 사용했다. 이는 **우리가 선택한 크기이며 원 논문의 트랜지스터 치수가 아니다.**
- **구현 소스:** `simulation/p3_transistor_driver.py`, 정적 연결 예제 `circuits/p3_8_4_2_1_nmos_example.cir`.
- **ngspice 환경:** ngspice-42, `ngbehavior=hs`. HSPICE 모델의 `dtemp` 전달 3곳만 **로컬 호환 복사본**에서 제거하고 원본 PDK는 그대로 보존했다.

원 저자 설계에 있는 실제 Pull-up/Pull-down 임피던스 피드백, Pre-driver/Slew-Rate 루프, 조정된 바이어스, 회로 레이아웃 및 기생성분은 복원하지 않았다. **TT에서 50 ohm에 맞춘 것은 자동 피드백의 성능을 검증한 것이 아니다.**

## 2. 재현 실행 방법

GitHub Actions 워크플로: `.github/workflows/p3_driver_spice.yml`.

Codespaces에서 수동 재현할 경우(모델의 해당 환경 사용 허가 필요):

```bash
bash scripts/run_dbhitek_smoke.sh
python3 simulation/p3_transistor_driver.py --symbols 128
python3 scripts/validate_p3_driver_results.py
python3 simulation/plot_p3_driver.py
```

**실제 수행한 검증 절차**

1. Inverter DC/Transient Smoke Test로 PDK Subcircuit 로딩 확인.
2. TT @ 27°C에서 소자 폭을 보정: 출력 PAD를 0.249/0.251 V에 각각 Clamp하고 전류 변화로 `Rout=ΔV/|ΔI|` 계산.
3. 같은 폭으로 16개 드라이버 코드(0-15)의 PAD 전압, 전원 공급 전류, Rout를 DC 측정.
4. TT/FF/SS/FS/SF @ 27°C, TT @ -20/85°C, 신호 공급 0.45/0.50/0.55 V 비교. **코너별 폭 재보정은 수행하지 않음.**
5. 3.6 Gb/s, 128-bit PRBS7에서 FFE 미적용과 2-Tap FFE (α=0.30)를 MOS 드라이버의 4-bit 제어 코드로 변환해 Transient 측정.
6. 동일한 50-ohm 종단, 100-fF PAD 커패시턴스, 2개의 버퍼 분리된 RC 극점(-12 dB @ 1.8 GHz)으로 RX 신호 재구성. 게이트 전환은 이상적 2-ps 입력.
7. 같은 PRBS, 채널, 드라이버 크기로 FFE 켬/끔 비교. 최적 샘플 위상과 동일 위상(1.20 UI) 결과를 모두 계산.

## 3. 실제 결과: 16개 전압 코드 및 임피던스

| TT @ 27°C | ngspice 재구성 결과 |
| --- | ---: |
| 출력 저항 평균, 16개 코드 | **49.952 Ω** |
| 코드별 출력 저항 최소-최대 | **49.198-50.723 Ω** |
| 실제 로드 출력 범위 | **0.09794-0.38394 V** |
| 전체 출력 스윙 | **285.99 mVpp** |
| End-point DNL 최대 절댓값 | **0.138 LSB** |
| End-point INL 최대 절댓값 | **0.341 LSB** |

**주의:** 이 모델은 250-mVpp 목표보다 큰 285.99-mVpp를 만들었다. 따라서 출력 임피던스가 50 Ω에 가깝다고 해서 논문의 출력 스윙 및 선형성이 자동으로 일치하는 것은 아니다.

## 4. PVT 및 보정 루프 필요성

아래는 코드를 7로 고정한 **증분 출력 저항**이고, 모델의 폭은 항상 TT 조건에서 보정한 값을 그대로 사용했다.

| 조건 | Rout (Ω) |
| --- | ---: |
| TT, 27°C, 0.50 V 신호 공급 | **49.998** |
| FF, 27°C, 0.50 V | **42.808** |
| SS, 27°C, 0.50 V | **58.672** |
| TT, -20°C, 0.50 V | **45.188** |
| TT, 85°C, 0.50 V | **56.185** |
| TT, 27°C, 0.45 V | **47.344** |
| TT, 27°C, 0.55 V | **52.798** |

공급전압 실험은 **0.5 V 신호 공급만** 0.45/0.55 V로 변경하고 VREF=VS/2로 따라가게 했으며, 1.8 V 게이트 공급은 고정했다.

이는 논문이 임피던스 피드백을 추가한 이유를 이해하는 **별도 재구성 실험**이다. 우리가 논문의 임피던스 보정 루프를 구현하거나 그 성능을 증명한 것은 아니다.

## 5. TX FFE의 실제 MOS Transient 비교

| 3.6 Gb/s, 동일 MOS 드라이버와 근사 채널 | FFE 미적용 | 2-Tap, α=0.30 |
| --- | ---: | ---: |
| 최적 샘플링의 RX Eye Height (mV) | **50.959** | **90.587** |
| 동일 1.20 UI 샘플링 RX Eye Height (mV) | **50.959** | **90.006** |
| 0.5 V 신호 공급 평균 전력 (mW) | **0.780** | **1.014** |

이 모델에서 Eye가 증가하는 방향은 논문 Fig. 25의 **2-Tap Pre-emphasis 적용 후 Eye가 열리는 실측 경향**과 같다. 그러나 **실측 37 mV × 189 ps 자체를 재현한 것은 아니다.**

또한 평균 전력은 **0.5 V 신호 공급에서의 전력**만 포함한다. 이상적 게이트 전원, Pre-driver, 50-ohm 종단 바이어스의 공급, 임피던스 조절, PLL/CDR 및 RX는 포함하지 않으므로 원 논문 Table III의 TX 9.66 mW와 Table IV의 전체 링크 27.12 mW를 직접 검증하는 값이 아니다.

## 6. ngspice 호환성 및 미검증 영역

ngspice는 일부 HSPICE 전용 BSIM3 모델 필드(`lref`, `wref`, `hspver`, `binflag`, `vfbflag`, `tlev`, `tlevc`)를 무시한다. 따라서 **HSPICE와 동일한 전기적 결과를 제공한다고 보증할 수 없다.** 정확한 DB HiTek 모델 검증을 위해서는 HSPICE/Spectre에서 동일 인버터 및 단일 MOS의 IV/CV 참조값과 대조해야 한다.

미구현: 원 논문 회로의 실제 바이어스 및 피드백, 실제 Pre-driver 및 Slew-Rate Control, 채널 S-parameter, 반사 및 실제 패키지, RX Comparator, PLL/CDR 및 지터, BER 및 전체 링크 소비 전력.

## 7. GitHub와 결과 파일

- 재현 코드: [P3 MOS Driver](../simulation/p3_transistor_driver.py)
- 회로 구성: [8:4:2:1 NMOS 정적 예제](../circuits/p3_8_4_2_1_nmos_example.cir)
- 자동 검증: [GitHub Actions](../.github/workflows/p3_driver_spice.yml)
- CSV: `tt_code_sweep.csv`, `pvt_corner_sweep.csv`, `baseline_mos_tx_rx.csv`, `ffe_alpha_0p30_mos_tx_rx.csv`
- JSON: `driver_summary.json`
- PNG: `fig_tx_codes_and_impedance.png`, `fig_tx_corners_and_power.png`, `fig_mos_tx_and_rx_waveforms.png`
- 다운로드: [GitHub Actions 원본 실행](https://github.com/khi103/EEE6682-Presentation/actions/runs/42999847513) > Artifacts. 데이터는 수치 파일이므로 Veusz에서 CSV로 불러와 축 및 레이블을 편집할 수 있다.

논문 발표에서는 **Python 행동 모델 → 별도의 DB HiTek NMOS 재구성 모델 → 논문 실리콘 실측**을 반드시 구별해야 한다.
