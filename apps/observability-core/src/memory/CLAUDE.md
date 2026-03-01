# CLAUDE.md

## Overview

This directory contains metadata-first Claude memory scanning and churn/index analytics.

## Index

| File | Contents (WHAT) | Read When (WHEN) |
| ------------ | ---------------------------------------- | ------------------------------------------------------ |
| `claude_memory_scanner.py` | Memory file scanning, project/path fingerprinting, freshness classification, snapshot assembly | Updating memory discovery behavior or diagnosing scan metadata gaps |
| `memory_churn_metrics.py` | Growth/churn math over memory snapshots and project-level trend shaping | Tuning churn calculations or investigating trend anomalies |
| `memory_fact_index.py` | Snapshot indexing, freshness rollups, project-level fact aggregation helpers | Refining memory insight aggregation or debugging index composition |
