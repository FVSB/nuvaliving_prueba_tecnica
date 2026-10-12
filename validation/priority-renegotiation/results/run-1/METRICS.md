# Metrics

## Summary

| Metric | Value |
|---|---|
| work orders | 8 |
| scheduled | 7 |
| requires review | 1 |
| preemptions | 2 |
| displaced work orders | ['WO-003', 'WO-004'] |
| holds released | 2 |
| handyman declines | 0 |
| slot suggestion tables | 4 |
| outgoing messages | 66 |
| inbound messages | 53 |
| wall clock seconds | 161.6 |
| checks passed | 10 |
| checks total | 10 |

## Per work order

| WO | Urgency | Lang | Result | Time to terminal (s) | Msgs tenant | Msgs handyman | Inbound | Revisions | Displaced | Declines |
|---|---|---|---|---|---|---|---|---|---|---|
| WO-001 | Critical | en | scheduled | 49.2 | 3 | 3 | 5 | 2 | 0 | 0 |
| WO-002 | High | es | scheduled | 39.3 | 4 | 3 | 5 | 2 | 0 | 0 |
| WO-003 | Low | en | scheduled | 123.5 | 8 | 8 | 14 | 9 | 1 | 0 |
| WO-004 | Medium | es | scheduled | 161.6 | 9 | 8 | 14 | 8 | 1 | 0 |
| WO-005 | High | en | requires_review | 5.1 | 1 | 0 | 1 | 0 | 0 | 0 |
| WO-006 | Low | es | scheduled | 88.4 | 4 | 3 | 5 | 2 | 0 | 0 |
| WO-007 | Critical | es | scheduled | 85.7 | 3 | 3 | 4 | 2 | 0 | 0 |
| WO-008 | Medium | en | scheduled | 26.1 | 3 | 3 | 5 | 2 | 0 | 0 |

## Checks

| Check | Result | Note |
|---|---|---|
| every work order ends with exactly one terminal result | PASS | {'WO-001': 1, 'WO-002': 1, 'WO-003': 1, 'WO-004': 1, 'WO-005': 1, 'WO-006': 1, 'WO-007': 1, 'WO-008': 1} |
| stdout carries exactly one RESULT frame per work order | PASS |  |
| stderr is empty | PASS |  |
| no two scheduled visits overlap | PASS | [] |
| scheduled visits are inside 09:00-19:00 | PASS |  |
| at least one higher-urgency order displaced a tentative hold | PASS |  |
| every displacement goes from a strictly higher to a lower urgency | PASS | [] |
| each displaced tenant receives a displacement notice | PASS | ['WO-003', 'WO-004'] |
| displaced orders end with a different, non-overlapping slot | PASS | ['WO-003', 'WO-004'] |
| silent tenant produces requires_review with a no-response reason | PASS | ['WO-005'] |
