# Profile Options and Execution Budgets Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the active tool profile the source of truth for typed option defaults and hard execution ceilings, validate requests before job creation, and carry effective limits into runner command construction.

**Architecture:** Add standalone application contracts for option schemas and execution budgets, project them through the existing manifest-backed catalog, and normalize `ActionRequest` inside `ActionService` before policy evaluation. Persist the normalized values in existing JSON fields and event payloads. Workers continue using `ToolInvocation`; runner adapters receive bounded timeout, rate, and concurrency values as typed keyword arguments and still construct argument lists without shell execution.

**Tech Stack:** Python 3.12+, Pydantic 2, FastAPI, SQLAlchemy async, YAML, pytest.

---

## File Structure

- Create `src/api/application/execution_limits.py`
  - Defines typed option schemas, requested/effective budgets, strict validation,
    default application, and hard-ceiling resolution.
- Modify `src/api/application/pipeline/yaml_config.py`
  - Adds `options` and `budgets` to profile manifest validation while retaining
    compatible `allowed_options`.
- Modify `src/api/application/capability_catalog.py`
  - Materializes option schemas and budgets into catalog entries and exposes
    normalization helpers.
- Modify `src/api/application/action_catalog.py`
  - Exposes typed profile schema and budget through `CatalogDetail`.
- Modify `src/api/infrastructure/tool_catalog/store.py`
  - Reconstructs typed schema/budget from the stored `manifest_fragment`.
- Modify `src/api/application/contracts.py`
  - Adds requested budget to `ActionRequest` and effective budget to
    `ToolInvocation`.
- Modify `src/api/application/services/action.py`
  - Normalizes parameters and budgets before policy, rejects invalid requests,
    and writes effective limits into metadata/event payloads.
- Modify `src/api/presentation/rest/routes/actions.py`
  - Maps action input validation failures to HTTP 422.
- Modify `src/api/config.py` and `src/api/application/di.py`
  - Defines system ceilings and injects them into `ActionService`.
- Modify `src/api/application/pipeline/invocation.py`
  - Rebuilds effective budget from the stored event and clamps supported runner
    keyword arguments.
- Modify `src/api/infrastructure/orchestration/store.py`
  - Copies effective budget into initial `runs.run_payload`.
- Modify `src/api/application/pipeline/pipeline.yaml`
  - Migrates `httpx`, `katana`, `ffuf`, and `naabu` profiles to typed schemas
    and hard budgets.
- Modify four CLI runners
  - Applies bounded timeout, rate, and internal concurrency through argument
    lists.
- Add focused tests under `tests/application` and `tests/infrastructure`.

### Task 1: Define Strict Option and Budget Contracts

**Files:**
- Create: `src/api/application/execution_limits.py`
- Test: `tests/application/test_execution_limits.py`

- [ ] **Step 1: Write failing contract tests**

Add tests covering strict values, defaults, enum/range rejection, required
fields, forbidden keys, and budget ceiling resolution:

```python
def test_option_schema_applies_defaults_without_string_coercion() -> None:
    schema = {
        "depth": ToolOptionSpec(
            type="integer",
            default=2,
            minimum=1,
            maximum=5,
        ),
        "headless": ToolOptionSpec(type="boolean", default=False),
    }

    assert normalize_options(schema, {"depth": 4}) == {
        "depth": 4,
        "headless": False,
    }

    with pytest.raises(ActionInputValidationError, match="depth must be integer"):
        normalize_options(schema, {"depth": "4"})


def test_requested_budget_cannot_exceed_profile_or_system_ceiling() -> None:
    system = ExecutionBudget(
        max_duration_seconds=1800,
        max_targets=1000,
        rate_per_second=1000,
        concurrency=5,
    )
    profile = ExecutionBudget(
        max_duration_seconds=120,
        max_targets=20,
        rate_per_second=10,
        concurrency=2,
    )

    assert resolve_execution_budget(
        system=system,
        profile=profile,
        requested=ExecutionBudgetRequest(max_targets=10),
    ) == ExecutionBudget(
        max_duration_seconds=120,
        max_targets=10,
        rate_per_second=10,
        concurrency=2,
    )

    with pytest.raises(ActionInputValidationError, match="max_targets exceeds"):
        resolve_execution_budget(
            system=system,
            profile=profile,
            requested=ExecutionBudgetRequest(max_targets=21),
        )
```

- [ ] **Step 2: Run tests and verify RED**

Run:

```powershell
.\.tmp_pytest\Scripts\python.exe -m pytest tests\application\test_execution_limits.py -q
```

Expected: collection fails because `api.application.execution_limits` does not
exist.

- [ ] **Step 3: Implement the minimal contracts**

Create:

```python
OptionType = Literal["integer", "number", "boolean", "string"]


class ActionInputValidationError(ValueError):
    pass


class ToolOptionSpec(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    type: OptionType
    default: Any = None
    required: bool = False
    minimum: float | None = None
    maximum: float | None = None
    enum: tuple[Any, ...] = ()

    @model_validator(mode="after")
    def validate_contract(self) -> "ToolOptionSpec":
        if self.minimum is not None and self.maximum is not None:
            if self.minimum > self.maximum:
                raise ValueError("minimum cannot exceed maximum")
        if self.type not in {"integer", "number"}:
            if self.minimum is not None or self.maximum is not None:
                raise ValueError("minimum/maximum require a numeric option")
        if self.required and self.default is None:
            return self
        if self.default is not None:
            self.validate_value("default", self.default)
        for value in self.enum:
            self.validate_value("enum", value)
        return self

    def validate_value(self, name: str, value: Any) -> Any:
        expected = {
            "integer": lambda item: isinstance(item, int) and not isinstance(item, bool),
            "number": lambda item: (
                isinstance(item, (int, float)) and not isinstance(item, bool)
            ),
            "boolean": lambda item: isinstance(item, bool),
            "string": lambda item: isinstance(item, str),
        }[self.type]
        if not expected(value):
            raise ActionInputValidationError(f"{name} must be {self.type}")
        if self.minimum is not None and value < self.minimum:
            raise ActionInputValidationError(f"{name} is below minimum")
        if self.maximum is not None and value > self.maximum:
            raise ActionInputValidationError(f"{name} exceeds maximum")
        if self.enum and value not in self.enum:
            raise ActionInputValidationError(f"{name} is not an allowed value")
        return value


class ExecutionBudget(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    max_duration_seconds: float | None = Field(default=None, gt=0)
    max_targets: int | None = Field(default=None, gt=0)
    rate_per_second: float | None = Field(default=None, gt=0)
    concurrency: int | None = Field(default=None, gt=0)


class ExecutionBudgetRequest(ExecutionBudget):
    pass
```

Implement `normalize_options()` and `resolve_execution_budget()` with explicit
errors and no coercion.

- [ ] **Step 4: Run tests and verify GREEN**

Run the Task 1 command. Expected: all tests pass.

- [ ] **Step 5: Commit Task 1**

```powershell
git add src/api/application/execution_limits.py tests/application/test_execution_limits.py
git commit -m "feat: add typed execution limit contracts"
```

### Task 2: Extend Manifest and Catalog Projection

**Files:**
- Modify: `src/api/application/pipeline/yaml_config.py`
- Modify: `src/api/application/capability_catalog.py`
- Modify: `src/api/application/action_catalog.py`
- Modify: `src/api/infrastructure/tool_catalog/store.py`
- Test: `tests/application/test_capability_catalog_manifest_snapshot.py`
- Test: `tests/application/test_pipeline_yaml.py`
- Test: `tests/infrastructure/test_tool_catalog_store.py`

- [ ] **Step 1: Write failing manifest/catalog tests**

Add:

```python
def test_profile_supports_typed_options_and_hard_budgets() -> None:
    config = PipelineConfig.model_validate(
        {
            "workers": {"demo": {"type": "scan"}},
            "capabilities": {
                "demo": {
                    "label": "Demo",
                    "request_event": "demo_requested",
                    "queue": "analysis",
                    "default_profile": "safe",
                    "mode": "manual",
                    "profiles": {
                        "safe": {
                            "label": "Safe",
                            "safety_level": "safe_active",
                            "options": {
                                "timeout": {
                                    "type": "integer",
                                    "default": 30,
                                    "minimum": 1,
                                    "maximum": 60,
                                }
                            },
                            "budgets": {
                                "max_duration_seconds": 60,
                                "max_targets": 5,
                                "rate_per_second": 10,
                                "concurrency": 2,
                            },
                        }
                    },
                }
            },
        }
    )

    profile = config.capabilities["demo"].profiles["safe"]
    assert profile.allowed_option_names == ("timeout",)
    assert profile.budgets.max_targets == 5


def test_catalog_hash_changes_when_profile_budget_changes() -> None:
    config = load_pipeline_config(DEFAULT_PIPELINE_CONFIG_PATH)
    original = build_tool_catalog_snapshot(config)
    payload = deepcopy(config.model_dump(mode="json"))
    payload["capabilities"]["httpx"]["profiles"]["safe-web-probe"]["budgets"][
        "max_targets"
    ] = 99

    changed = build_tool_catalog_snapshot(
        PipelineConfig.model_validate(payload)
    )

    assert changed.catalog_hash != original.catalog_hash
```

Also assert `CatalogDetail.option_schema` and
`CatalogDetail.execution_budget` are rebuilt from `manifest_fragment`.

- [ ] **Step 2: Run tests and verify RED**

```powershell
.\.tmp_pytest\Scripts\python.exe -m pytest tests\application\test_capability_catalog_manifest_snapshot.py tests\application\test_pipeline_yaml.py tests\infrastructure\test_tool_catalog_store.py -q
```

Expected: failures for missing `options`, `budgets`, `option_schema`, and
`execution_budget`.

- [ ] **Step 3: Extend profile validation**

In `ProfileSpecConfig` add:

```python
options: dict[str, ToolOptionSpec] = Field(default_factory=dict)
budgets: ExecutionBudget = Field(default_factory=ExecutionBudget)

@property
def allowed_option_names(self) -> tuple[str, ...]:
    return tuple(sorted(self.options or dict.fromkeys(self.allowed_options)))

@model_validator(mode="after")
def option_sources_must_agree(self) -> "ProfileSpecConfig":
    forbidden = set(self.allowed_option_names) & FORBIDDEN_OPTION_KEYS
    if forbidden:
        raise ValueError(f"forbidden option names: {sorted(forbidden)}")
    if self.options and self.allowed_options:
        if set(self.options) != set(self.allowed_options):
            raise ValueError("allowed_options and options must declare the same keys")
    return self
```

Import the forbidden-key constant from a neutral module or move it from
`policy.py` into `execution_limits.py` to avoid a policy/config dependency.

- [ ] **Step 4: Project typed profile data**

Extend `ToolCatalogEntry` and `CatalogDetail`:

```python
option_schema: dict[str, ToolOptionSpec] = Field(default_factory=dict)
execution_budget: ExecutionBudget = Field(default_factory=ExecutionBudget)
```

Populate them from profile payload. Keep the PostgreSQL table unchanged:
`manifest_fragment` remains the durable projection source for these structured
fields, and `allowed_options` remains the indexed compatibility summary.

- [ ] **Step 5: Run tests and verify GREEN**

Run the Task 2 command. Expected: all pass.

- [ ] **Step 6: Commit Task 2**

```powershell
git add src/api/application/pipeline/yaml_config.py src/api/application/capability_catalog.py src/api/application/action_catalog.py src/api/infrastructure/tool_catalog/store.py tests/application/test_capability_catalog_manifest_snapshot.py tests/application/test_pipeline_yaml.py tests/infrastructure/test_tool_catalog_store.py
git commit -m "feat: project typed profile schemas and budgets"
```

### Task 3: Migrate First Four Profiles and Add System Ceilings

**Files:**
- Modify: `src/api/application/pipeline/pipeline.yaml`
- Modify: `src/api/config.py`
- Test: `tests/application/test_profile_execution_budgets.py`
- Test: `tests/test_p0_hardening_contracts.py`

- [ ] **Step 1: Write failing configuration tests**

Assert:

```python
def test_first_runner_profiles_have_typed_options_and_budgets() -> None:
    config = load_pipeline_config()
    for capability_id in ("httpx", "katana", "ffuf", "naabu"):
        for profile in config.capabilities[capability_id].profiles.values():
            assert profile.options
            assert profile.budgets.max_duration_seconds
            assert profile.budgets.max_targets
            assert profile.budgets.concurrency


def test_system_execution_ceilings_are_positive() -> None:
    settings = Settings()
    assert settings.MAX_ACTION_DURATION_SECONDS > 0
    assert settings.MAX_ACTION_TARGETS > 0
    assert settings.MAX_ACTION_RATE_PER_SECOND > 0
    assert settings.ORCHESTRATOR_MAX_CONCURRENT > 0
```

- [ ] **Step 2: Run tests and verify RED**

```powershell
.\.tmp_pytest\Scripts\python.exe -m pytest tests\application\test_profile_execution_budgets.py tests\test_p0_hardening_contracts.py -q
```

- [ ] **Step 3: Add conservative system settings**

Add to `Settings`:

```python
MAX_ACTION_DURATION_SECONDS: float = 1800
MAX_ACTION_TARGETS: int = 1000
MAX_ACTION_RATE_PER_SECOND: float = 1000
```

Use existing `ORCHESTRATOR_MAX_CONCURRENT` as the system concurrency ceiling.

- [ ] **Step 4: Migrate profiles**

Use strict schemas and these ceilings:

```yaml
httpx/safe-web-probe:
  options:
    timeout: {type: integer, default: 60, minimum: 1, maximum: 120}
  budgets:
    max_duration_seconds: 120
    max_targets: 100
    rate_per_second: 50
    concurrency: 20

katana/safe-crawl:
  options:
    depth: {type: integer, default: 2, minimum: 1, maximum: 5}
    js_crawl: {type: boolean, default: true}
    headless: {type: boolean, default: false}
    timeout: {type: integer, default: 120, minimum: 1, maximum: 600}
  budgets:
    max_duration_seconds: 600
    max_targets: 20
    rate_per_second: 10
    concurrency: 2

ffuf/content-discovery-light:
  options:
    timeout: {type: integer, default: 300, minimum: 1, maximum: 600}
  budgets:
    max_duration_seconds: 600
    max_targets: 1
    rate_per_second: 10
    concurrency: 5
```

For both Naabu profiles declare strict port/rate/mode schemas. Set passive
defaults to `scan_mode: passive`; set active defaults to `scan_mode: active`,
`top_ports: "100"`, `scan_type: "c"`, and require approval as today.

- [ ] **Step 5: Run tests and verify GREEN**

Run the Task 3 command.

- [ ] **Step 6: Commit Task 3**

```powershell
git add src/api/application/pipeline/pipeline.yaml src/api/config.py tests/application/test_profile_execution_budgets.py tests/test_p0_hardening_contracts.py
git commit -m "feat: define initial profile execution ceilings"
```

### Task 4: Normalize Actions Before Policy and Job Creation

**Files:**
- Modify: `src/api/application/contracts.py`
- Modify: `src/api/application/services/action.py`
- Modify: `src/api/application/di.py`
- Modify: `src/api/presentation/rest/app.py`
- Modify: `src/api/presentation/rest/routes/actions.py`
- Test: `tests/application/test_action_input_validation.py`
- Test: `tests/application/test_actions_api_contract.py`

- [ ] **Step 1: Write failing action-boundary tests**

Cover default application, wrong type, budget escalation, and target overflow:

```python
@pytest.mark.asyncio
async def test_action_service_applies_profile_defaults_before_policy() -> None:
    service, store, policy = make_service(
        option_schema={
            "depth": ToolOptionSpec(type="integer", default=2, minimum=1, maximum=5)
        },
        profile_budget=ExecutionBudget(max_targets=5, max_duration_seconds=60),
    )
    action = action_request(options={})

    await service.request_action(action)

    assert policy.received_options == {"depth": 2}
    assert store.allowed_queued[0][0].metadata["effective_budget"]["max_targets"] == 5


@pytest.mark.asyncio
async def test_invalid_action_input_creates_no_policy_record_or_job() -> None:
    action = action_request(options={"depth": "3"})
    with pytest.raises(ActionInputValidationError):
        await service.request_action(action)
    assert store.policy_results == []
    assert store.allowed_queued == []
```

Add a route contract asserting `ActionInputValidationError` maps to HTTP 422.

- [ ] **Step 2: Run tests and verify RED**

```powershell
.\.tmp_pytest\Scripts\python.exe -m pytest tests\application\test_action_input_validation.py tests\application\test_actions_api_contract.py -q
```

- [ ] **Step 3: Extend public action contracts**

Add:

```python
budget: ExecutionBudgetRequest | None = None
_effective_budget: ExecutionBudget | None = PrivateAttr(default=None)

@property
def effective_budget(self) -> ExecutionBudget:
    if self._effective_budget is None:
        raise RuntimeError("ActionRequest execution budget has not been resolved")
    return self._effective_budget
```

Update `bind_profile()` so it accepts normalized `options` and an effective
budget, replaces `action.options`, and builds `ScanProfile` from those values.

- [ ] **Step 4: Inject system ceilings and normalize in `_resolve`**

Add `system_budget: ExecutionBudget` to `ActionService`, defaulting to the
settings-derived value in DI and scheduler startup.

In `_resolve`:

```python
detail = await self.catalog.get_detail(action.catalog_id)
options = normalize_options(detail.option_schema, action.options)
budget = resolve_execution_budget(
    system=self.system_budget,
    profile=detail.execution_budget,
    requested=action.budget,
)
if budget.max_targets is not None and len(action.targets) > budget.max_targets:
    raise ActionInputValidationError(
        f"target count {len(action.targets)} exceeds max_targets {budget.max_targets}"
    )
action.bind_profile(
    capability_id=detail.capability,
    profile_id=detail.profile,
    options=options,
    execution_budget=budget,
)
action.metadata = {
    **action.metadata,
    "effective_budget": budget.model_dump(mode="json"),
}
```

- [ ] **Step 5: Map validation failure to HTTP 422**

Catch `ActionInputValidationError` in `create_action` and raise:

```python
raise HTTPException(status_code=422, detail=str(exc)) from exc
```

- [ ] **Step 6: Run tests and verify GREEN**

Run the Task 4 command.

- [ ] **Step 7: Commit Task 4**

```powershell
git add src/api/application/contracts.py src/api/application/services/action.py src/api/application/di.py src/api/presentation/rest/app.py src/api/presentation/rest/routes/actions.py tests/application/test_action_input_validation.py tests/application/test_actions_api_contract.py
git commit -m "feat: validate action options and hard budgets"
```

### Task 5: Persist and Rebuild Effective Budgets

**Files:**
- Modify: `src/api/application/contracts.py`
- Modify: `src/api/application/services/action.py`
- Modify: `src/api/application/pipeline/invocation.py`
- Modify: `src/api/infrastructure/orchestration/store.py`
- Test: `tests/application/test_execution_contracts.py`
- Test: `tests/application/test_worker_invocation.py`
- Test: `tests/application/test_event_store_dispatch_contract.py`

- [ ] **Step 1: Write failing propagation tests**

Add:

```python
def test_tool_invocation_requires_effective_execution_budget() -> None:
    invocation = ToolInvocation(
        action_id=uuid4(),
        job_id=uuid4(),
        run_id=uuid4(),
        program_id=uuid4(),
        capability_id="httpx",
        profile_id="safe-web-probe",
        targets=["https://example.com"],
        options={"timeout": 30},
        safety_level=SafetyLevel.SAFE_ACTIVE,
        scope_decision_id=uuid4(),
        policy_decision_id=uuid4(),
        campaign_id=uuid4(),
        correlation_id=uuid4(),
        execution_budget=ExecutionBudget(max_targets=5),
    )
    assert invocation.execution_budget.max_targets == 5


def test_build_invocation_rebuilds_budget_from_action_event() -> None:
    event = _event(
        execution_budget={
            "max_duration_seconds": 60,
            "max_targets": 20,
            "rate_per_second": 10,
            "concurrency": 2,
        }
    )
    invocation = build_invocation(event, event["targets"])
    assert invocation.execution_budget.concurrency == 2
```

Assert `_payload()` includes `execution_budget` and `create_allowed_action`
stores it in initial `runs.run_payload`.

- [ ] **Step 2: Run tests and verify RED**

```powershell
.\.tmp_pytest\Scripts\python.exe -m pytest tests\application\test_execution_contracts.py tests\application\test_worker_invocation.py tests\application\test_event_store_dispatch_contract.py -q
```

- [ ] **Step 3: Implement propagation**

Add `execution_budget: ExecutionBudget` to `ToolInvocation`.

In `_payload()` add:

```python
"execution_budget": action.effective_budget.model_dump(mode="json"),
```

In `build_invocation()` parse the same payload into `ExecutionBudget`.

When creating the initial run, store:

```python
run_payload={
    "options": dict(action.profile.options),
    "execution_budget": action.effective_budget.model_dump(mode="json"),
},
```

- [ ] **Step 4: Run tests and verify GREEN**

Run the Task 5 command.

- [ ] **Step 5: Commit Task 5**

```powershell
git add src/api/application/contracts.py src/api/application/services/action.py src/api/application/pipeline/invocation.py src/api/infrastructure/orchestration/store.py tests/application/test_execution_contracts.py tests/application/test_worker_invocation.py tests/application/test_event_store_dispatch_contract.py
git commit -m "feat: propagate effective execution budgets"
```

### Task 6: Apply Budgets to Runner Arguments

**Files:**
- Modify: `src/api/application/pipeline/invocation.py`
- Modify: `src/api/infrastructure/runners/httpx_cli.py`
- Modify: `src/api/infrastructure/runners/katana_cli.py`
- Modify: `src/api/infrastructure/runners/ffuf_cli.py`
- Modify: `src/api/infrastructure/runners/naabu_cli.py`
- Test: `tests/application/test_runner_tool_invocation_options.py`

- [ ] **Step 1: Write failing clamp tests**

Extend existing tests:

```python
async def test_httpx_budget_clamps_timeout_and_threads(monkeypatch) -> None:
    invocation = _invocation(
        "httpx",
        {"timeout": 90},
        budget=ExecutionBudget(max_duration_seconds=30, concurrency=3),
    )
    await _consume(run_raw(runner, targets, invocation))
    captured = RecordingExecutor.calls[0]
    assert captured.timeout == 30
    assert captured.command[captured.command.index("-t") + 1] == "3"


async def test_naabu_budget_clamps_rate_and_concurrency(monkeypatch) -> None:
    invocation = _invocation(
        "naabu",
        {"rate": 100, "scan_mode": "active"},
        budget=ExecutionBudget(
            max_duration_seconds=60,
            rate_per_second=25,
            concurrency=2,
        ),
    )
    await _consume(run_raw(runner, ["api.example.com"], invocation))
    command = RecordingExecutor.calls[0].command
    assert command[command.index("-rate") + 1] == "25"
    assert command[command.index("-c") + 1] == "2"
```

- [ ] **Step 2: Run tests and verify RED**

```powershell
.\.tmp_pytest\Scripts\python.exe -m pytest tests\application\test_runner_tool_invocation_options.py -q
```

- [ ] **Step 3: Merge budget kwargs in `run_raw`**

Build a copy of normalized options:

```python
options = dict(invocation.options if invocation is not None else {})
if invocation is not None:
    budget = invocation.execution_budget
    if budget.max_duration_seconds is not None:
        options["timeout"] = min(
            float(options.get("timeout", budget.max_duration_seconds)),
            budget.max_duration_seconds,
        )
    if budget.rate_per_second is not None and "rate" in params:
        options["rate"] = min(
            float(options.get("rate", budget.rate_per_second)),
            budget.rate_per_second,
        )
    if budget.concurrency is not None and "concurrency" in params:
        options["concurrency"] = budget.concurrency
```

Preserve signature filtering so unsupported budget dimensions never become CLI
arguments.

- [ ] **Step 4: Add typed concurrency to runners**

- HTTPX: clamp `-t` to `concurrency`.
- Katana: use `concurrency` for `-c` and `-p`.
- FFUF: use `concurrency` for `-t`.
- Naabu: use `concurrency` for `-c`.

All commands remain `list[str]` passed to `CommandExecutor`.

- [ ] **Step 5: Run tests and verify GREEN**

Run Task 6 command plus:

```powershell
.\.tmp_pytest\Scripts\python.exe -m pytest tests\application\test_worker_invocation.py -q
```

- [ ] **Step 6: Commit Task 6**

```powershell
git add src/api/application/pipeline/invocation.py src/api/infrastructure/runners/httpx_cli.py src/api/infrastructure/runners/katana_cli.py src/api/infrastructure/runners/ffuf_cli.py src/api/infrastructure/runners/naabu_cli.py tests/application/test_runner_tool_invocation_options.py
git commit -m "feat: enforce execution budgets in runner arguments"
```

### Task 7: Documentation and Full Verification

**Files:**
- Modify: `docs/architecture/mvp-gap-audit.md`
- Modify: `docs/architecture/patch-plan-to-mvp.md`

- [ ] **Step 1: Update roadmap status**

Document that:

- typed profile option schemas/defaults are implemented for the first four
  runners;
- per-action hard ceilings are validated before job creation;
- effective budgets are persisted and passed to workers;
- distributed rate limiting and campaign consumption accounting remain future
  work.

- [ ] **Step 2: Run focused verification**

```powershell
.\.tmp_pytest\Scripts\python.exe -m pytest tests\application\test_execution_limits.py tests\application\test_capability_catalog_manifest_snapshot.py tests\application\test_profile_execution_budgets.py tests\application\test_action_input_validation.py tests\application\test_execution_contracts.py tests\application\test_worker_invocation.py tests\application\test_runner_tool_invocation_options.py -q
```

Expected: all pass.

- [ ] **Step 3: Run full verification**

```powershell
.\.tmp_pytest\Scripts\python.exe -m pytest -q -rs
```

Expected: zero failures. Integration/E2E tests may remain skipped when Docker is
unavailable.

- [ ] **Step 4: Run syntax and diff checks**

```powershell
.\.tmp_pytest\Scripts\python.exe -m py_compile src\api\application\execution_limits.py src\api\application\contracts.py src\api\application\services\action.py src\api\application\pipeline\invocation.py
git diff --check
```

- [ ] **Step 5: Commit documentation**

```powershell
git add docs/architecture/mvp-gap-audit.md docs/architecture/patch-plan-to-mvp.md
git commit -m "docs: record typed profile execution budgets"
```
