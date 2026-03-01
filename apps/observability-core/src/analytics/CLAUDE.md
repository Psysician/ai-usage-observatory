# CLAUDE.md

## Overview

This directory contains deterministic analytics primitives for tokens, costs, and freshness metadata.

## Index

| File | Contents (WHAT) | Read When (WHEN) |
| ------------ | ---------------------------------------- | ------------------------------------------------------ |
| `cost_layers.py` | Estimated vs billed cost aggregation, bucketed cost rollups, layer label helpers | Updating cost semantics or debugging estimated/billed variance |
| `freshness.py` | Source watermark derivation and freshness-state classification helpers | Tuning stale thresholds or tracing freshness metadata issues |
| `token_aggregates.py` | Token aggregation by bucket/provider/project plus attribution-coverage metrics | Modifying token math or analyzing unknown-project token share |
