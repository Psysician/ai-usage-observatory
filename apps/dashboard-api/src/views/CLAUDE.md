# CLAUDE.md

## Overview

This directory contains validated view-spec models and in-memory view persistence logic.

## Index

| File | Contents (WHAT) | Read When (WHEN) |
| ------------ | ---------------------------------------- | ----------------------------------------------------- |
| `__init__.py` | View module package marker | Adjusting module exports or imports |
| `view_model.py` | View schema normalization, binding validation, deterministic spec checks | Changing view schema rules or debugging spec validation failures |
| `view_service.py` | In-memory view store, create/update/clone/list operations, snapshot export | Modifying persistence behavior or investigating state mutation issues |
