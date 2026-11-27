# Engine vs baselines

200 runs per system, same seeds for all.

| System | Accuracy | Macro F1 | Jaccard | Time to verdict | Never right | False dispatches / run | Cost / run | Saved vs B0 | API calls / run | Brier |
|---|---|---|---|---|---|---|---|---|---|---|
| engine-v1 | 81% | 0.81 | 0.91 | 150 s | 19% | 0.00 | $89 | $3,012 | 43.8 | 0.357 |
| engine-v2 | 94% | 0.94 | 0.91 | 150 s | 6% | 1.71 | $1,119 | $1,982 | 43.8 | 0.114 |
| B0 | 25% | 0.10 | 0.76 | 1113 s | 75% | 3.76 | $3,101 | $0 | 0.0 | 1.500 |
| B1 | 28% | 0.19 | 0.76 | 1077 s | 72% | 2.86 | $2,557 | $544 | 121.4 | 1.440 |

## Accuracy by fault type

| System | meter_fault | network | power | tamper |
|---|---|---|---|---|
| engine-v1 | 72% | 96% | 98% | 58% |
| engine-v2 | 100% | 92% | 98% | 84% |
| B0 | 100% | 0% | 0% | 0% |
| B1 | 72% | 40% | 0% | 0% |
