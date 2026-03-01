# CLAUDE.md

## Overview

This directory contains integration tests for observability metrics and memory-insight API auditability.

## Index

| File | Contents (WHAT) | Read When (WHEN) |
| ------------ | ---------------------------------------- | ------------------------------------------------------ |
| `test_memory_insights_api.py` | Memory trend/churn assertions, raw-content leak guardrails, missing-file metadata checks | Validating privacy-safe memory insight behavior |
| `test_metrics_auditability.py` | Provider/project split checks, dual-cost-layer checks, freshness transition assertions | Verifying analytics payload auditability or debugging metrics regressions |
