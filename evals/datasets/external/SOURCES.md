# External security datasets

Downloaded on 2026-11-19 from the Hugging Face dataset viewer API (same rows as the published parquet files), with Luan's approval. Used only to measure the input guardrail. Not used to tune prompts.

| File | Source | License | Rows | SHA-256 (first 16) |
|---|---|---|---|---|
| `deepset_prompt_injections.jsonl` | https://huggingface.co/datasets/deepset/prompt-injections | Apache-2.0 | 662 (train 546, test 116; label 1 = attack, 0 = benign) | 69bc0206946b6a57 |
| `lakera_gandalf_ignore_instructions.jsonl` | https://huggingface.co/datasets/Lakera/gandalf_ignore_instructions | MIT | 1,000 attacks (train 777, validation 111, test 112) | 2a87180791d5efe4 |
| `pt_machine_translated.jsonl` | 30 attacks and 20 benign prompts sampled (seed 20261119) from the two test splits, translated to Brazilian Portuguese by Claude Haiku 5.5 (`evals/security_external.py translate`) | same as the originals | 50 (one benign German prompt, pt-ds-test-45, came back untranslated and is kept as is) | 7bda3925310d1c95 |

Field mapping: `text` is the original prompt; `label` is `attack` or `benign`; `id` is `<set>-<split>-<row index>`. Only the test splits are measured. The deepset set also contains German prompts.
