# CLAUDE.md

## Overview

This directory contains provider-specific log parsers and adapters into canonical ingest records.

## Index

| File | Contents (WHAT) | Read When (WHEN) |
| ------------ | ---------------------------------------- | ------------------------------------------------------ |
| `__init__.py` | Provider parser package marker | Updating provider package imports |
| `claude_local.py` | Claude local-record parser, field coercion, adaptation into ingest-ready payloads | Extending Claude ingestion or debugging local Claude parse failures |
| `codex_lb_request_logs.py` | codex-lb request-log parser, provider inference, adaptation into ingest-ready payloads | Integrating codex-lb changes or debugging proxy-log ingestion |
| `codex_lb_sqlite.py` | codex-lb SQLite request-log mapper into ingest-ready payloads | Integrating direct codex-lb `store.db` ingestion |
| `openai_codex_local.py` | OpenAI Codex local-record parser and ingest adaptation | Extending OpenAI local ingestion or tracing parse defects |
