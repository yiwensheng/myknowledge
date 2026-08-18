# Self-Distill Implementation Plan

> **For agentic workers:** Implement task-by-task. Steps use checkbox syntax.

**Goal:** Ship distill skeleton + wiki-distill workflow + ask/produce injection.

**Architecture:** `lib/distill.py` owns skeleton + run + prompt block; skill action `distill`; startup ensure; onboarding v4 step.

**Tech Stack:** Python FastAPI backend, existing RAG `scope_paths`, Electron onboarding.js

---

### Task 1: lib/distill.py + config + tests

- [ ] Add `distill` to CONTENT_DIRS / WATCH_DIRS
- [ ] Implement ensure / run_distill / distill_context_block
- [ ] Unit test skeleton idempotent

### Task 2: Skill + workflow + startup

- [ ] skills/wiki-distill/SKILL.md
- [ ] skills.py action distill; workflows.py meta
- [ ] server startup ensure_distill_skeleton

### Task 3: Inject + onboarding

- [ ] llm.py ask/produce inject block
- [ ] onboarding.js v4 + distill step
