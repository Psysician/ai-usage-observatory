# Metric Dictionary: AI Usage Observatory

Version: 0.1
Date: March 1, 2026

## 1. Conventions
- Cost unit: USD unless explicitly configured otherwise.
- Token unit: integer token counts from normalized event ledger.
- Time grain defaults: hour, day, month.
- Dimensions available by default: `project`, `provider`, `model`, `model_family`, `time`.
- `unknown` project must remain visible in all attribution-sensitive metrics.

## 2. Metric Certification Levels
- `CERTIFIED`: safe for shared/org dashboards.
- `EXPERIMENTAL`: exploratory; personal views by default.

## 3. Core Metrics
| Metric ID | Formula | Dimensions | Grain | Certification | Notes |
|---|---|---|---|---|---|
| `tokens_input_non_cached` | `sum(input_tokens_non_cached)` | project, provider, model | hour/day/month | CERTIFIED | Full-rate input tokens |
| `tokens_output` | `sum(output_tokens)` | project, provider, model | hour/day/month | CERTIFIED | Includes assistant output tokens |
| `tokens_cache_read` | `sum(cache_read_tokens)` | project, provider, model | hour/day/month | CERTIFIED | Provider semantics may differ |
| `tokens_cache_write` | `sum(cache_write_tokens)` | project, provider, model | hour/day/month | CERTIFIED | May be zero for providers without write billing |
| `tokens_reasoning` | `sum(reasoning_tokens)` | project, provider, model | hour/day/month | CERTIFIED | Nullable by provider/model |
| `tokens_total` | `sum(input_non_cached + output + cache_read + cache_write + reasoning)` | project, provider, model | hour/day/month | CERTIFIED | Unified total token surface |
| `requests_total` | `count(distinct request_id)` | project, provider, model | hour/day/month | CERTIFIED | From request-level sources |
| `requests_failed` | `count_if(status in error)` | project, provider, model | hour/day/month | CERTIFIED | Error classification normalized |
| `error_rate` | `requests_failed / requests_total` | project, provider, model | hour/day/month | CERTIFIED | Null-safe division |
| `latency_p50_ms` | `p50(latency_ms)` | project, provider, model | hour/day/month | CERTIFIED | Requires latency source availability |
| `latency_p95_ms` | `p95(latency_ms)` | project, provider, model | hour/day/month | CERTIFIED | High-tail diagnosis |

## 4. Cost Metrics
| Metric ID | Formula | Dimensions | Grain | Certification | Notes |
|---|---|---|---|---|---|
| `cost_estimated_usd` | `sum(component_tokens * rate_card_component)` | project, provider, model | hour/day/month | CERTIFIED | Uses versioned rate cards |
| `cost_billed_usd` | `sum(reconciled_invoice_cost)` | project, provider, model | day/month | CERTIFIED | May be delayed |
| `cost_variance_usd` | `cost_billed_usd - cost_estimated_usd` | project, provider, model | day/month | CERTIFIED | Reconciliation delta |
| `cost_variance_pct` | `(billed - estimated) / estimated` | project, provider, model | day/month | CERTIFIED | Null-safe when estimate=0 |
| `cost_per_1k_tokens_est` | `cost_estimated_usd / tokens_total * 1000` | project, provider, model | day/month | CERTIFIED | Efficiency KPI |
| `cost_per_request_est` | `cost_estimated_usd / requests_total` | project, provider, model | day/month | CERTIFIED | Null-safe division |
| `provider_cost_share_pct` | `provider_cost / total_cost` | provider | day/month | CERTIFIED | Portfolio mix |
| `project_cost_share_pct` | `project_cost / total_cost` | project | day/month | CERTIFIED | Chargeback input |

## 5. Attribution and Quality Metrics
| Metric ID | Formula | Dimensions | Grain | Certification | Notes |
|---|---|---|---|---|---|
| `attribution_coverage_pct` | `attributed_events / total_events` | project, provider | hour/day/month | CERTIFIED | Project-level trust indicator |
| `unknown_project_tokens` | `sum(tokens_total where project='unknown')` | provider, model | hour/day/month | CERTIFIED | Must stay visible |
| `unknown_project_cost_est` | `sum(cost_estimated where project='unknown')` | provider, model | hour/day/month | CERTIFIED | Attribution debt |
| `freshness_staleness_seconds` | `now - source_watermark` | source, provider | minute/hour | CERTIFIED | Data timeliness |
| `freshness_state` | classification from staleness thresholds | source, provider | realtime | CERTIFIED | `live/warm/stale/partial` |
| `parse_error_rate` | `parser_failures / parser_attempts` | source | hour/day | CERTIFIED | Ingest health |

## 6. Cache and Efficiency Metrics
| Metric ID | Formula | Dimensions | Grain | Certification | Notes |
|---|---|---|---|---|---|
| `cache_hit_rate_tokens` | `cache_read_tokens / (cache_read_tokens + input_non_cached)` | project, provider, model | hour/day/month | CERTIFIED | Proxy for reuse efficiency |
| `output_input_ratio` | `tokens_output / tokens_input_non_cached` | project, provider, model | day/month | CERTIFIED | Workload shape indicator |
| `retry_rate` | `retries / requests_total` | project, provider, model | hour/day/month | CERTIFIED | Reliability impact |
| `timeout_rate` | `timeouts / requests_total` | project, provider, model | hour/day/month | CERTIFIED | Reliability impact |

## 7. Memory Metrics (Claude)
| Metric ID | Formula | Dimensions | Grain | Certification | Notes |
|---|---|---|---|---|---|
| `memory_file_count` | `count(memory_files)` | project | day/week | CERTIFIED | Metadata only |
| `memory_total_bytes` | `sum(file_size_bytes)` | project | day/week | CERTIFIED | Metadata only |
| `memory_updates_7d` | `count(files changed in 7d)` | project | day/week | CERTIFIED | Activity level |
| `memory_bytes_delta_7d` | `bytes_now - bytes_7d_ago` | project | day/week | CERTIFIED | Growth/churn |
| `memory_staleness_days` | `days_since_latest_mtime` | project | day/week | CERTIFIED | Freshness indicator |
| `memory_usage_ratio` | `memory_total_bytes / tokens_total` | project | week/month | EXPERIMENTAL | Correlative, not causal |
| `memory_error_correlation` | `corr(memory_staleness_days, error_rate)` | project | week/month | EXPERIMENTAL | Correlation only |

## 8. Budget and Forecast Metrics
| Metric ID | Formula | Dimensions | Grain | Certification | Notes |
|---|---|---|---|---|---|
| `budget_month_usd` | configured budget | project/team/org | month | CERTIFIED | From policy config |
| `cost_mtd_est_usd` | `sum(cost_estimated current month)` | project/team/org | month | CERTIFIED | Month-to-date |
| `burn_rate_pct` | `projected_month_end / budget_month` | project/team/org | day/month | CERTIFIED | Forecast pressure |
| `projected_month_end_est_usd` | `(cost_mtd / elapsed_days) * days_in_month` | project/team/org | day/month | CERTIFIED | Linear forecast baseline |
| `budget_remaining_usd` | `budget_month - cost_mtd` | project/team/org | day/month | CERTIFIED | Runway |

## 9. Anomaly Metrics
| Metric ID | Formula | Dimensions | Grain | Certification | Notes |
|---|---|---|---|---|---|
| `cost_spike_zscore` | `(current - mean_baseline) / std_baseline` | project/provider/model | day | EXPERIMENTAL | Baseline config-dependent |
| `error_spike_pct` | `(error_rate_now - baseline_error_rate) / baseline_error_rate` | project/provider/model | day | EXPERIMENTAL | Needs minimum volume guard |
| `cache_regression_pct` | `(cache_hit_rate_now - baseline_cache_hit_rate) / baseline` | project/provider/model | day | EXPERIMENTAL | Baseline config-dependent |

## 10. Mandatory Payload Fields
Every metric response must include:
- `metric_id`
- `value`
- `dimensions`
- `time_bucket`
- `freshness_state`
- `source_watermark`
- `attribution_coverage_pct`
- `cost_layer` (`estimated|billed|combined` when relevant)
- `provenance` (source adapters/rate card version)

## 11. Guardrails
- Any chart mixing estimated and billed values must show a visible label.
- Any attribution-sensitive chart must show unknown bucket presence.
- Any memory metric with correlation semantics must include "not causal" annotation.
