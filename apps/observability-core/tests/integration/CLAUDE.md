# CLAUDE.md

## Overview

This directory contains ingestion and attribution integration tests for canonical event correctness.

## Index

| File | Contents (WHAT) | Read When (WHEN) |
| ------------ | ---------------------------------------- | ------------------------------------------------------ |
| `__init__.py` | Integration test package marker | Fixing test package import/discovery behavior |
| `test_ingest_attribution_pipeline.py` | End-to-end parser-to-store pipeline checks, aggregate parity checks, attribution confidence/reason assertions | Investigating ingestion/attribution regressions or extending acceptance coverage |
| `test_local_ingest_runner_codex_lb_sqlite.py` | codex-lb SQLite ingest runner backfill/incremental checkpoint behavior (`id:<n>`) | Validating direct `~/.codex-lb/store.db` ingestion and checkpoint semantics |
