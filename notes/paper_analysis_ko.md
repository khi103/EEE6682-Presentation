# P3 논문 분석 및 발표 내용 검증 (2026-11-09)

## 출처와 범위
- 논문: K.-L. J. Wong, H. Hatamkhani, M. Mansuri, and C.-K. K. Yang, “A 27-mW 3.6-Gb/s I/O transceiver,” *IEEE J. Solid-State Circuits*, vol. 39, no. 4, pp. 602–612, Apr. 2004, doi: 10.1109/JSSC.2004.825259.
- 강의: EEE6682 논문 발표 안내 PDF (업로드된 원본). 20분 발표/10분 Q&A로 변경된 이후 공지를 최우선 적용.
- 비교 대상 강의 파일: `khi103/serdes-lecture-site/linksim_H-L/sim3_ffe.py`; 이 코드는 56 Gb/s, 3/5/9-Tap ZF FFE 데모이며 P3 실리콘의 원본 설계 파일이 아님.
- 모든 모의실험은 독자적으로 작성한 **시스템 수준 행동 모델**로 수행. 원 논문의 트랜지스터 수준 회로/측정 케이블의 S-parameter 복제는 아님.

## 1. 한 문장 핵심
전압형 2-Tap Pre-emphasis, 50 Ω source termination, 저전력 RX comparator, charge-pump mismatch 기반 위상 복구를 결합하여 0.18-μm CMOS에서 3.6 Gb/s, 27.12 mW 송수신 링크를 구현했다.

## 2. 논문의 실제 정량값
| 항목 | 논문 결과 | 근거 |
|---|---|---|
| 전송 속도 | 3.6 Gb/s/포트 | Abstract; Section VI |
| 비트 시간 | 277.78 ps/UI (= 역수로 계산) | 3.6 Gb/s에서 파생 |
| Nyquist | 1.8 GHz (= NRZ 전송 속도의 절반) | Section III/IV |
| 반도체 | 0.18 μm CMOS, 아날로그 1.8 V | Abstract, measurement |
| 정합 | 50 Ω source/load | Section II–III, Fig. 7–10 |
| 최대 수신 입력 감도 | 약 35 mV | Section VI, Fig. 27 |
| 보상 채널 손실 | 12 dB (8-cm FR4 + 6.5-m RG58) | Section VI, Fig. 25 |
| Fig. 25 Equalization 후 Eye height | 37 mV | Section VI, Fig. 25 |
| Fig. 25 Equalization 후 Eye width | 189 ps | Section VI, Fig. 25 |
| Fig. 25 계수 | α = 0.3 | Fig. 25(b) caption |
| 출력 임피던스의 계수별 변동 | 10% 이내 | Fig. 10/Section III |
| 전체 링크 동작 전력 | 27.12 mW | Table IV (9.66+5.6+4.67+5.6+1.59) |
| 에너지 효율 정규화 | 7.5 mW/Gb/s (27.12/3.6=7.53) | Abstract; Section VI |
| 면적 | 약 0.2 mm² | Abstract |

**용어 주의:** “27 mW transmitter”가 아니라 *송신 측과 수신 측을 합친 활성 링크 전력*이다. 측정되는 회로의 TX core 부분은 9.66 mW(Table III)이다.

## 3. 송신기: 원문 식과 발표에 필요한 파생식
논문 Equation (1), Section III:

\[y[n]=x[n]-\alpha x[n-1]\]

주파수 응답의 일반적인 해석(논문 식을 수학적으로 변환):

\[H_{TX}(e^{j\omega T})=1-\alpha e^{-j\omega T}.\]

\[|H_{TX}(0)|=|1-\alpha|,\qquad |H_{TX}(\pi/T)|=|1+\alpha|.\]

강의의 `Σ|c|=1`을 만족시키도록 **별도로 정규화한** 행동 모델:

\[c_0=1/(1+\alpha),\quad c_1=-\alpha/(1+\alpha),\quad \sum |c_k|=1.\]

따라서 (0≤α≤1) 장시간 반복 데이터의 DC swing 비율은 `(1−α)/(1+α)`. **이는 구현된 실리콘의 출력 파형이 그대로 이 비율이라고 주장하는 식이 아니라 시스템 예산 모델이다.**

Fig. 7(a)의 4-bit binary-weighted segment를 상호보완적으로 선택하여 총 출력 conductance가 일정: `G_total = Σ_i G_i = 1/50Ω`. **P3의 독창성은 전압형 FFE 설정을 바꾸면서도 약 50Ω 출력을 유지한다는 점.** 시뮬레이션의 L1 norm=1 조건만으로 50Ω 동작을 재현한 것은 아니다.

추가 구현 요소: PVT tracking impedance controller(Fig. 8), slew-rate control(Fig. 11–12), 16:1 multiplexer(Fig. 6). Slew constraint ~1/3 UI의 논문 설계 목표와 최대 112ps TX rise / 107ps fall 측정을 혼동하지 말 것.

## 4. 저전력 송수신기 구성
- Section II / Fig. 3–5: 각 I/O pin은 half-duplex, PLL은 TX/RX에 공유되므로 동시에 송수신하지 않음. LCM single-ended signaling, 50Ω 종단, receiver node around 250 mV common mode.
- Table I: **3.6 Gb/s, 출력 swing 250 mV 조건의 시뮬레이션**에서 HCM(single ended) driver total 8.174 mW, LCM(single ended) 1.494 mW. 링크 전체 전력 숫자로 오인하지 말 것.
- Section IV: RX에는 4개의 고속 sampler, bandwidth-limited comparator(대략 2 GHz), 디지털 offset calibration. 논문에서는 최대 약 75 mV 예상 offset이 약 5 mV까지 개선될 수 있음을 시뮬레이션으로 제시.
- Section V: primary PLL frequency acquisition와 secondary phase acquisition. Bang-bang detector → digital counter → digitally controlled charge pump current mismatch. SC filter는 charge-pump ripple 저감. 원 논문은 phase interpolator 없이 위상 이동을 만든다는 점을 강조.

## 5. 원문 측정과 새 시뮬레이션의 구분
### 논문에서 직접 관찰된 결과
- Fig. 25: 12-dB cable+PCB channel에서 Equalization 이전 닫힌 eye, α=0.3 후 37 mV × 189 ps eye.
- Fig. 10: impedance approximately 50 Ω with ≤10% variation across pre-emphasis settings.
- Table IV: 전체 활성 링크 전력 27.12 mW.

### 본 프로젝트에서 실행한 행동 모델의 결과 (2026-11-09, 생성 JSON 기준)
- NRZ 3.6 Gb/s, 250 mVpp, VCM 250 mV, Nyquist 1.8 GHz.
- 채널: 측정한 채널 응답이 아니라, Nyquist에서 12 dB 손실을 갖도록 조정한 2-pole RC 모델(fc ≈ 1.0425 GHz each).
- 110 ps Gaussian 10–90% TX rise-time *illustration*; PRBS7; oversampling 32; no noise/jitter/CMOS matching/PLL.
- 1-Tap baseline worst-case eye 33.90 mV, width 147.57 ps.
- 2-Tap `α=0.3`, `c=[0.7692,−0.2308]`: eye 70.13 mV, width 173.61 ps.
- 3-Tap ZF: eye 65.24 mV; 5-Tap ZF: 70.14 mV; 9-Tap ZF: 70.20 mV. 3/5/9는 강의 관련 확장 실험이며 **P3 칩의 구조가 아니다.**
- 고정 출력 예산에서는 pre-emphasis 강화와 유효 DC swing 감소 사이에 trade-off가 있다.
- 1pole RC도 12 dB Nyquist이지만 no FFE 6.26 mV / α=0.3 56.80 mV로 결과가 변함. 같은 Nyquist loss 하나만으로 Fig.25 값을 맞출 수 없는 이유를 보여준다.

## 6. 비교와 비판
- 논문 37 mV 및 189 ps vs 행동 모델 70.13 mV 및 173.61 ps. 값이 일치하지 않는 것이 **버그라고 단정할 수 없으며**, 채널 펄스 꼬리, 기생용량, receiver noise, TX circuit settling, 정확한 termination, PLL jitter 등이 모두 다름.
- 이 결과를 **“Fig.25 exact reproduction”**, **“transistor-level verified”**, **“measured BER”** 로 표현하면 안 된다.
- 3/5/9tap 눈 개선이 제한되는 것은 peak swing budget under L1-normalization, 채널 형태, timing phase의 상호 작용 때문이다. 더 많은 taps가 항상 좋은 것은 아니다.
- 본 프로젝트는 원 논문의 50Ω 유지 및 27mW 전력을 재현하지 않는다. 해당 항목은 원문 보고값만 설명한다.

## 7. 필수 발표 체크리스트
- 최신 공지: 발표 20분, 질의응답 10분. 슬라이드는 발표 전날 23:59까지 LearnUs.
- 최초 안내문: 영어 PPT 15장 이하, 문제정의 → 구조 → 핵심 아이디어 → **실행한 재현 그래프 ≥1장** → 비판적 질문.
- 마지막 슬라이드에 **실제 조원별 역할 분담** 기재 (현재 조원 정보 제공되지 않아 placeholder).
- 앞 조 질문 담당은 다음 조라는 최신 공지; 발표 조 번호/발표일은 수정된 배정표를 확인해야 하므로 본 문서에 임의 기입하지 않음.
- 발표자의 이름/학번/역할 분담/발표일은 사용자 최종 확인 필요.
