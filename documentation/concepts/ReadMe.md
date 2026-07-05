---
title: Aiko Services distributed system infrastructure documentation
description: Index of OKF concept documents for Storage, HyperSpace, Category,
  Dependency and ProcessManager
type: index
audience: [architects, developers, end-users]
status: draft
version: "0.6"
last_updated: 2026-07-05
---

# Aiko Services: distributed system infrastructure

This directory documents the core infrastructure concepts that turn a
collection of independent Aiko Services into a unified, persistent,
distributed system: **Storage**, **HyperSpace**, **Category**,
**Dependency** and **ProcessManager**.

The documentation follows the Open Knowledge Format (OKF) conventions:

- **One concept per file**, each self-contained and individually linkable
- **YAML front-matter** carrying metadata: title, description, type,
  audience, status, source files and related concepts
- **Audience-first sections** in every concept document, ordered from
  broadest to most specialised audience: *Overview*, then
  *For application developers* (Command-line usage, Public API), then
  *For framework developers* (Design, Implementation notes, CRC card)
- **Explicit cross-links** between related concepts

The full section structure and writing guidance is defined in the
constitution's OKF Concepts documentation template
(`documentation/constitution/okf_concept_template.md`).

## Start here

- [Design overview](design_overview.md) — executive summary and conceptual
  diagram of how all five concepts fit together. Read this first.

## Concepts

| Concept | One-line summary | Source |
|---------|------------------|--------|
| [Dependency](dependency.md) | A reference to a distributed Service: discovery filter, lifecycle manager and storage location | `src/aiko_services/main/dependency.py` |
| [Category](category.md) | An Actor that groups Entries — Dependencies and other Categories — into a named collection | `src/aiko_services/main/category.py` |
| [HyperSpace](hyperspace.md) | The root Category and LifeCycleManager of Categories: a unified, navigable network graph of distributed Services | `src/aiko_services/main/hyperspace.py` |
| [Storage](storage.md) | The persistence SPI (Service Provider Interface) and its file-system implementation, StorageFile | `src/aiko_services/main/storage/storage.py`, `src/aiko_services/main/storage/storage_file.py` |
| [ProcessManager](process_manager.md) | Unified, distributed creation and destruction of operating system processes — analogous to Unix `init` (pid 1) | `src/aiko_services/main/process_manager.py` |

## Reading paths

- **Architects / evaluators**: [Design overview](design_overview.md) only.
- **Application developers**: [Design overview](design_overview.md), then
  the *For application developers* sections of [HyperSpace](hyperspace.md),
  [Category](category.md) and [ProcessManager](process_manager.md).
- **Framework developers**: everything, paying particular attention to the
  *For framework developers* sections and the Composite design pattern
  described in [Dependency](dependency.md) and [Storage](storage.md).

## Status

These subsystems are under active development (version 0.6). Each document
distinguishes **implemented** behaviour from **planned / work-in-progress**
behaviour, based on the source code as of 2026-07-04.
