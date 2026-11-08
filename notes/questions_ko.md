# P3 예상 질문과 검증 가능한 답변 (20분 발표 + 10분 Q&A)

## Q1. 왜 기존 TX에 단순한 고역통과 필터를 넣지 않고 Segmented Driver로 구현했나요?
**답:** FFE 적용 계수가 변할 때 source impedance가 변하면 전송선 반사가 증가합니다. 논문의 segmented voltage-mode driver는 각 segment의 pull-up 또는 pull-down 선택을 변경하되 총 conductance를 유지하므로 대략 50Ω termination을 달성합니다. 근거: Section III, Fig. 7, Fig. 10.

**English (IEEE):** The segmented voltage-mode driver redistributes tap weights while maintaining approximately constant aggregate output conductance, thereby preserving source termination.
**한국어 뉘앙스:** 탭별 가중치가 바뀌더라도 합성 출력 컨덕턴스가 거의 일정해 반사 억제를 유지한다는 의미.

## Q2. 2-Tap FFE는 어떤 주파수 성분을 강조하나요?
**답:** `H(z)=1−αz⁻¹`. `0≤α≤1`에서 DC 크기는 `1−α`, Nyquist 크기는 `1+α`이므로 고주파가 상대적으로 강조됩니다. 강의 정규화 후에는 Nyquist 크기 1, DC 크기 `(1−α)/(1+α)`입니다.

## Q3. α를 크게 하면 언제나 Eye가 열리나요?
**답:** 아닙니다. ISI가 줄 수 있지만 출력 스윙 예산 내에서 유효 main cursor와 긴 run의 DC amplitude가 감소합니다. 채널 꼬리, noise, sampling phase에 따라 최적 α가 존재합니다. 이번 2-pole surrogate에서는 α≈0.28 근처가 가장 좋았습니다. 이것을 실리콘의 최적값으로 해석하지 않습니다.

## Q4. `Σ|c|=1`은 논문 식 (1)과 똑같나요?
**답:** 아닙니다. 원문은 `y[n]=x[n]−αx[n−1]`이며, L1 제약은 강의의 TX 전압 swing-budget 분석을 위한 정규화입니다. 따라서 수식 표기 시 “paper expression”과 “normalized behavioral model”을 명확히 분리했습니다.

## Q5. 왜 56-Gb/s 코드를 3.6-Gb/s P3에 그대로 적용하지 않았나요?
**답:** 강의 `sim3_ffe.py`는 별도의 56-Gb/s 채널과 3/5/9탭 ZF FFE 예제입니다. P3는 3.6-Gb/s low-common-mode, 단일 종단, 2tap segmented voltage-mode driver입니다. 서로 다른 채널/아키텍처이므로 직접 비교하면 잘못된 결론이 됩니다.

## Q6. 논문은 FFE 후 Eye 37 mV라는데, 왜 모델은 70.1 mV인가요?
**답:** 원문은 실제 케이블+PCB 12-dB 채널의 측정입니다. 모델은 Nyquist 감쇠만 맞춘 이상화된 2-pole RC 채널과 무잡음 RX를 사용했습니다. 채널 위상/군지연/고차 손실, 패키지 기생성분, RX noise, PLL jitter 등의 차이를 반영하지 못합니다. 70.1 mV는 **문헌 값의 재현값이 아닙니다.**

## Q7. Nyquist loss만으로 Eye opening을 예측할 수 있나요?
**답:** 안 됩니다. ISI는 time-domain sampled impulse response 전체에 의존합니다. 본 연구에서 같은 12 dB 손실을 갖춘 1-pole과 2-pole 모델의 결과가 현저히 달랐다는 점을 보여 주었습니다.

## Q8. 왜 이 논문은 Low Common-Mode Signaling을 선택했나요?
**답:** 드라이버에서 정적/동적 전력 사용을 줄일 수 있기 때문입니다. 논문 Table I에서 동일한 3.6-Gb/s/250-mVpp 기준 HCM single-ended와 LCM single-ended driver의 total simulated power가 각각 약 8.174 mW, 1.494 mW입니다. **전체 링크 측정 전력과 혼동하면 안 됩니다.**

## Q9. 27 mW 전력은 송신기 하나의 전력인가요?
**답:** 아니요. Table IV의 two-end active link 구성으로 9.66+5.6+4.67+5.6+1.59 = 27.12 mW입니다. TX core만 약 9.66 mW입니다. 27.12/3.6 ≈ 7.53 mW/Gb/s입니다.

## Q10. RX comparator에서 왜 bandwidth를 약 2 GHz로 제한했나요?
**답:** 3.6-Gb/s NRZ의 유용한 신호 대역폭은 약 1.8 GHz입니다. 그보다 지나치게 넓은 bandwidth는 노이즈 적분을 늘립니다. 논문에서는 대략 2 GHz 근처로 preamplifier bandwidth를 제한해 잡음을 줄이고, offset calibration을 함께 설계합니다.

## Q11. Timing Recovery가 어떻게 PLL 전력을 줄이나요?
**답:** 별도의 phase interpolator 대신 charge pump의 전류 불균형으로 정적 phase offset을 형성합니다. PLL 구조를 송수신에 공유하고 switched-capacitor filter로 주기 ripple을 줄입니다. 실제 절감량은 논문 전체 전력표에 근거해 설명해야 하며, 개별 회로의 전력 절감량을 시뮬레이션으로 산출하지 않았습니다.

## Q12. 3/5/9 Tap을 더하면 왜 성능이 크게 좋아지지 않나요?
**답:** 복잡한 채널의 ISI tail은 더 많이 제거할 수 있으나 `Σ|c|=1` 제약하에서 메인 탭 가중치가 줄어들어 잡음 마진을 잃을 수 있습니다. 순수 zero-forcing이 항상 noise-optimal하지는 않으며, 이번 수치는 특정 RC 채널의 예시입니다.

## Q13. BER을 제시하지 않은 이유는 무엇인가요?
**답:** 모델은 receiver thermal noise, data/clock jitter, decision circuit 및 패키지의 측정 모델을 갖고 있지 않습니다. 단순 Eye height만으로 측정 BER을 보고하면 과장입니다. 원문에서는 장시간 BER count를 확보할 수 없어 Noise 기반 BER 추정을 했다는 한계도 명시합니다(Section VI).

## Q14. What would make a more faithful reproduction?
**답:** 원 논문의 실제 channel S-parameters 또는 측정 impulse response, transistor-level voltage-mode driver 구현, output impedance sweep, receiver comparator noise and offset, CDR jitter/phase loop model이 필요합니다. 현재 프로젝트에서는 정확도 향상에 필요한 데이터가 제공되지 않았습니다.

---

질문 담당 규칙(최신 공지): **매 발표의 다음 순서 조**가 질문을 맡으며, 발표자를 제외한 조원마다 최소 1개의 질문이 필요합니다. 실제 조 번호 및 질문 대상 논문은 최신 배정표에서 최종 확인해야 합니다.
