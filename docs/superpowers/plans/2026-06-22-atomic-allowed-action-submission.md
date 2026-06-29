# Atomic Allowed Action Submission Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make immediately allowed action submission atomic through the durable outbox boundary.

**Architecture:** Replace the two store calls in the allowed path with one combined store operation. Reuse the existing persistence helpers and keep blocked and approval-required paths unchanged.

**Tech Stack:** Python 3.13, FastAPI application services, SQLAlchemy async sessions, pytest.

---

### Task 1: Define the atomic application-store boundary

**Files:**
- Modify: `tests/application/test_event_store_dispatch_contract.py`
- Modify: `src/api/application/services/action.py`

- [ ] **Step 1: Write a failing test** asserting an allowed action uses one store call that receives the action, policy decision, and event envelope.
- [ ] **Step 2: Run the targeted test** with `python -m pytest tests/application/test_event_store_dispatch_contract.py -q` and confirm it fails because the combined operation is absent.
- [ ] **Step 3: Update `ActionService.request_action`** to build the envelope before persistence and call the combined operation for allowed decisions; retain `record_policy_result` for blocked and approval-required decisions.
- [ ] **Step 4: Run the targeted test** and confirm it passes.

### Task 2: Implement the one-transaction store operation

**Files:**
- Modify: `tests/application/test_event_store_dispatch_contract.py`
- Modify: `src/api/infrastructure/orchestration/store.py`

- [ ] **Step 1: Add a failing store contract test** requiring action/policy/scope, job/run, event-store, and dispatch writes before a single commit.
- [ ] **Step 2: Run the targeted test** and confirm it fails because the combined store method is absent.
- [ ] **Step 3: Implement the combined operation** by reusing existing private helpers and executing all writes through one session.
- [ ] **Step 4: Run the targeted test** and confirm it passes.

### Task 3: Verify regression safety

**Files:**
- Verify: `src/api/application/services/action.py`
- Verify: `src/api/infrastructure/orchestration/store.py`
- Verify: `tests/application/test_event_store_dispatch_contract.py`

- [ ] **Step 1: Run action/outbox tests** with `python -m pytest tests/application/test_event_store_dispatch_contract.py tests/application/test_actions_api_contract.py tests/application/test_event_dispatcher.py -q`.
- [ ] **Step 2: Run the full suite** with `python -m pytest -q`.
- [ ] **Step 3: Run `git diff --check`** and inspect the final scoped diff.
