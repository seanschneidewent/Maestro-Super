# Test Quarantine Notes

The files below are excluded from default `pytest` collection in `services/api/pytest.ini`
because they target legacy pre-V3 architecture that has been removed:

- `tests/test_models.py`
- `tests/test_smart_fast_mode.py`
- `tests/test_big_maestro_code_bboxes.py`

## Why Quarantined

- They import removed symbols/modules from the old query and orchestration stack.
- Running them during V3 stabilization causes import-time failures unrelated to V3 behavior.

## Unquarantine Criteria

- Replace references to removed pre-V3 modules/models with current V3 equivalents.
- Ensure each file passes in the default local environment and in CI.
- Remove the corresponding `--ignore` entry from `pytest.ini` after validation.
