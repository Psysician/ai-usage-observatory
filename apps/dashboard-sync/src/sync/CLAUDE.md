# CLAUDE.md

## Overview

This directory contains redaction and export logic for optional team sharing of dashboard views.

## Index

| File | Contents (WHAT) | Read When (WHEN) |
| ------------ | ---------------------------------------- | ------------------------------------------------------ |
| `__init__.py` | Sync module package marker | Updating sync module imports |
| `redaction_policy.py` | Recursive payload redaction rules, allowlist handling, sensitive-key detection | Changing redaction guarantees or debugging leaked identifiers |
| `share_service.py` | Team-share export assembly, metadata wrapping, redaction-policy integration | Modifying share payload format or team export behavior |
