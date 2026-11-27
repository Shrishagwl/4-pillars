| variant | system | accuracy | macro_f1 | false_dispatches_per_run | cost_per_run | api_calls_per_run | brier |
|---|---|---|---|---|---|---|---|
| today's API | engine-v1 | 81% | 0.81 | 0 | $89 | 43.83 | 0.36 |
| today's API | engine-v2 | 94% | 0.94 | 1.71 | $1,119 | 43.83 | 0.11 |
| today's API | B0 | 25% | 0.10 | 3.76 | $3,101 | 0 | 1.50 |
| + outage shapes | engine-v1 | 88% | 0.88 | 0 | $86 | 43.83 | 0.23 |
| + outage shapes | engine-v2 | 94% | 0.94 | 1.71 | $1,098 | 43.83 | 0.10 |
| + outage shapes | B0 | 25% | 0.10 | 3.76 | $3,101 | 0 | 1.50 |
| + restore event | engine-v1 | 82% | 0.82 | 0 | $94 | 32.65 | 0.34 |
| + restore event | engine-v2 | 96% | 0.96 | 1.69 | $1,087 | 32.65 | 0.09 |
| + restore event | B0 | 25% | 0.10 | 2.76 | $2,451 | 0 | 1.50 |
| + both | engine-v1 | 90% | 0.89 | 0 | $93 | 32.65 | 0.21 |
| + both | engine-v2 | 96% | 0.96 | 1.69 | $1,084 | 32.65 | 0.08 |
| + both | B0 | 25% | 0.10 | 2.76 | $2,451 | 0 | 1.50 |
