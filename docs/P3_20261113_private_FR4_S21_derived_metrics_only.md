# P3: Additional independent complex-S21 channel transfer validation

Date: 2026-11-13 KST  
Paper under study: K.-L. J. Wong et al., "A 27-mW 3.6-Gb/s I/O Transceiver," *IEEE Journal of Solid-State Circuits*, vol. 39, no. 4, pp. 602–612, Apr. 2004, doi: 10.1109/JSSC.2004.825259.

## Provenance

The original, separately permissioned lecture repository \`khi103/serdes-lecture-site\` contains four Touchstone files \`linksim_H-L/fr4_diff_100ohm*.s2p\`. The data were inspected *inside the authorized connected GitHub session*, using immutable source commit \`128f225a336a2e99405cf8a5a0bfb136f9048766\`. The files define \`# Hz S RI R 100.0\`, i.e., a 100-ohm two-port complex S21 **of a lecturer's differential FR4 example**, not the paper's 50-ohm single-ended FR4+RG58 cable. **No original Touchstone samples or licensed foundry model parameters are copied into this report/public repo.**

## Method

An independent in-memory complex-FFT LTI calculation used 2048 PRBS31 bits, 16 samples per 3.6-Gb/s UI, normalized voltage-mode two-tap FFE \`(current-α×previous)/(1+α)\`, FFT complex channel S21 with phase, matched 100-ohm ports, training symbols 128–511 to select one *shared* timing phase among all six alphas per channel, and 1488 untouched evaluation symbols 512–1999. No receiver transistor, physical CDR, random noise, external cable, or original die is represented.

### Actual complex S21, normalized vertical Eye

| Lecturer channel | \u007cS21\u007c at 1.8 GHz (dB) | α=0.0 | α=0.1 | α=0.2 | α=0.3 | α=0.4 | α=0.5 | Best tested α |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| Basic FR4 | -3.633 | 1.11756 | 1.08161 | 0.87395 | 0.69382 | 0.53943 | 0.39836 | 0.0 |
| Mid FR4 | -3.370 | 0.76415 | 0.86428 | 0.93401 | 0.94046 | 0.76013 | 0.59888 | 0.3 |
| FR4 x36 | -5.122 | 0.53632 | 0.64788 | 0.74084 | 0.77628 | 0.68891 | 0.54758 | 0.3 |
| FR4 x42 | -6.014 | 0.49900 | 0.60879 | 0.70028 | 0.75652 | 0.65013 | 0.51576 | 0.3 |

The numerical Eye values use normalized input voltage levels, **not mV measured by a physical MOS receiver**. Each ideal matched-channel training/evaluation case produced 0 decision errors over 1488 test bits with the chosen ideal threshold. This is no evidence of BER 10^-12, which requires far more independent errors and actual receiver noise, and no claim of paper-channel equivalence.

### Interpretation

The optimum normalized α for lecturer Basic channel was 0.0, but 0.3 for the other three examples; thus the best FFE coefficient depends on complex channel response. Separate transistor MOS TX/RX and synthetic RC2 experiments in this repository found α=0.4 gave the largest physical analog eye at one reconstructed RC2 setting. These results are compatible: neither is an architecture-independent optimum.

## IEEE-style academic English

> The sensitivity of a two-tap voltage-mode pre-emphasis coefficient to channel characteristics was evaluated using four distinct complex S-parameter datasets from a separate 100-Ω teaching-link model. A common sampling phase was selected using a training interval and held fixed during subsequent PRBS31 evaluation. The coefficient maximizing the normalized vertical eye differed across the evaluated channels, demonstrating that the optimum pre-emphasis setting is channel dependent. These system-level results neither reproduce the published 50-Ω cable channel nor establish the measured error rate of the reported CMOS transceiver.

**한국어 번역 뉘앙스:** 별도의 100 Ω 교육용 링크 모델에서 얻은 네 종류의 복소 S-parameter를 사용하여 2-Tap 전압형 Pre-emphasis 계수가 채널 특성에 얼마나 민감한지 평가했다. 학습 구간에서 공통 샘플링 위상을 결정하고 이후 PRBS31 평가에서 고정했다. 수직 Eye를 최대화하는 계수는 채널마다 달라졌으며, 이는 최적 계수가 채널에 의존함을 보여준다. 이 시스템 수준 결과는 논문의 50 Ω 케이블 채널을 재현하거나 실제 CMOS 송수신기의 실측 오류율을 증명하지 않는다.

The words "separate teaching-link model", "normalized" and "neither ... nor" intentionally prevent a numerical or silicon-equivalence claim.
