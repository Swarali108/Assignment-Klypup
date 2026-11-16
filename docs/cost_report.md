# Cost report

Generated 2026-11-14 13:12 UTC by `python -m tools.cost_report` from `cost_log.csv`, `outputs/runs.csv` and `outputs/<event_id>/ranked.json`.

| Event | Fresh cost (estimate) | Latest run cost | Latest run wall time | Latest run calls (cached) | Latest fresh run: cost, wall time | Callable people | Fresh cost per callable person | Spent on this event |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| garware_buyback | $0.0118 | $0.0000 | 0.9 s | 7 (7) | $0.0004, 8.3 s | 2 | $0.0059 | $0.0123 |
| sedemac_ipo | $0.0243 | $0.0000 | 13.1 s | 27 (27) | $0.0032, 51.7 s | 19 | $0.0013 | $0.0816 |
| spacenet_ofs | $0.0047 | $0.0000 | 0.4 s | 4 (4) | $0.0047, 20.0 s | 2 | $0.0024 | $0.0047 |

Total development spend: **$0.0987** over 617 logged calls (charged_usd where OpenRouter reported it, else our cost_usd estimate; the ping row is excluded). 1 call has no price and is not in the sum.

Fresh cost is an estimate: the cost log does not record which earlier call a cache hit came from, so each cached call is priced at the last uncached call with the same agent, model and person.

## Pricing source (copied from tools/llm.py)

- USD per 1,000,000 tokens, as (input, output). None means the rate is not filled in.
- Model page: https://openrouter.ai/anthropic/claude-haiku-5.5
- Date checked: 2026-11-13
- Fill each tuple from that page before a real run. Do not guess a rate.
- `"anthropic/claude-haiku-5.5": (0.10, 0.50)` (USD per 1M input, output tokens)
- Source: GET https://openrouter.ai/api/v1/models, fetched 2026-11-13T14:32:06Z through
- tools/fetch.py. data[].pricing for this id: prompt 0.000002, completion 0.00001 per token.
- `"anthropic/claude-sonnet-5.5": (2.00, 10.00)` (USD per 1M input, output tokens)
