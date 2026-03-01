# CLAUDE.md

## Overview

This directory contains integration tests for custom views, certified widgets, and shared snapshot stability.

## Index

| File | Contents (WHAT) | Read When (WHEN) |
| ------------ | ---------------------------------------- | ------------------------------------------------------ |
| `__init__.py` | Integration test package marker | Fixing test discovery/import behavior |
| `test_custom_views_widgets.py` | End-to-end view create/update/clone flows, resolver validation checks, restart snapshot stability assertions | Investigating dashboard API regressions or extending view/widget behavior |
