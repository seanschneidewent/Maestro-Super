# Fast Mode Eval Dataset

Use `fast_mode_eval_dataset.sample.json` as a starting template for replay cases.

Run harness:

```bash
cd services/api
python scripts/evaluate_fast_mode.py \
  --project-id <PROJECT_UUID> \
  --dataset ../docs/modes/eval/fast_mode_eval_dataset.sample.json \
  --k 4
```
