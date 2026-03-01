# CLAUDE.md

## Overview

This directory contains API routes that expose metrics, project summaries, and memory insights.

## Index

| File | Contents (WHAT) | Read When (WHEN) |
| ------------ | ---------------------------------------- | ------------------------------------------------------ |
| `memory_insights.py` | Memory-insight endpoint, freshness/error metadata shaping, no-raw-content response assembly | Modifying memory insight responses or debugging freshness/error envelopes |
| `metrics.py` | Metrics endpoint, token/cost merge logic, time-bucket validation, freshness wiring | Changing aggregate metrics contract or tracing provider/project split calculations |
| `projects.py` | Project-focused metrics endpoint, per-project token/cost payload assembly, attribution metadata exposure | Updating project analytics output or debugging attribution audit fields |
