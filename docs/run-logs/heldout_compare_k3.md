## Before / After — held-out split=`test`

| Metric | Baseline | Optimized | Δ |
| --- | ---: | ---: | ---: |
| Composite (0-100) | 41.00 | 74.67 | +33.67 |
| Mutation score | 0.400 | 0.742 | +0.342 |
| Branch coverage | 0.417 | 0.750 | +0.333 |
| Line coverage | 0.417 | 0.750 | +0.333 |
| Pass rate | 0.417 | 0.750 | +0.333 |
| Valid rate | 0.833 | 0.833 | +0.000 |
| Avg turns | 9.00 | 15.08 | +6.08 |
| Total cost (USD) | 0.8337 | 1.5720 | +0.7383 |

### Per-task composite

| Task | Baseline | Optimized | Δ |
| --- | ---: | ---: | ---: |
| linked_list | 66.67 | 100.00 | +33.33 |
| csv_parser | 0.00 | 33.33 | +33.33 |
| date_range | 33.33 | 66.67 | +33.34 |
| calculator | 64.00 | 98.67 | +34.67 |