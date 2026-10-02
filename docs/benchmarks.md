# Checking public benchmarks for contamination

`toolkit-mmqa contamination` reads benchmark files from disk. It never downloads
anything itself, so you choose exactly which version of a benchmark you check
against. This page shows how to fetch common public benchmarks as JSONL and
which `--eval-field` to use.

Check one or more benchmarks against your training data:

```bash
toolkit-mmqa contamination \
  --train my_train.jsonl --train-field text \
  --benchmark gsm8k=gsm8k_test.jsonl \
  --benchmark humaneval=HumanEval.jsonl \
  --eval-field question \
  --out contamination.json
```

`--eval-field` applies to every benchmark in one run. When benchmarks use
different field names, run the command once per benchmark (or pass the field
list that all of them share).

## Direct downloads (no extra dependencies)

| Benchmark | Command | Text field(s) |
|---|---|---|
| GSM8K test (1,319 problems) | `curl -L -o gsm8k_test.jsonl https://raw.githubusercontent.com/openai/grade-school-math/master/grade_school_math/data/test.jsonl` | `question` (add `answer` to include solutions) |
| GSM8K train (7,473 problems) | `curl -L -o gsm8k_train.jsonl https://raw.githubusercontent.com/openai/grade-school-math/master/grade_school_math/data/train.jsonl` | `question` |
| HumanEval (164 problems) | `curl -L https://github.com/openai/human-eval/raw/master/data/HumanEval.jsonl.gz \| gunzip > HumanEval.jsonl` | `prompt` (add `canonical_solution` for solutions) |

## Hugging Face Hub

With the `[hf]` extra (`pip install ".[hf]"`), pass a Hub split directly as
`hf:NAME[:CONFIG]:SPLIT[@REVISION]`:

```bash
toolkit-mmqa contamination --train my_train.jsonl --train-field text \
  --benchmark mmlu=hf:cais/mmlu:all:test --eval-field question --out mmlu.json
```

Pin `@REVISION` (a commit hash on the Hub) so the report's digest is
reproducible. Or export a split to JSONL once with the `datasets` library:

```python
from datasets import load_dataset

load_dataset("cais/mmlu", "all", split="test").to_json("mmlu_test.jsonl")
load_dataset("allenai/ai2_arc", "ARC-Challenge", split="test").to_json("arc_challenge_test.jsonl")
load_dataset("Rowan/hellaswag", split="validation").to_json("hellaswag_val.jsonl")
load_dataset("openai/gsm8k", "main", split="test").to_json("gsm8k_test.jsonl")
```

| Dataset | Text field(s) |
|---|---|
| `cais/mmlu` | `question` (add `choices`; list fields are joined with newlines) |
| `allenai/ai2_arc` | `question` |
| `Rowan/hellaswag` | `ctx` |
| `openai/gsm8k` | `question` |

Check the license of each benchmark before redistributing any copy of it.

## Choosing methods and thresholds

- `exact,ngram` (default) is fast and follows the 13-gram definition used in the
  GPT-3 contamination study (Brown et al. 2020, Appendix C): an example is
  flagged if any of its 13-word sequences appears in training data.
- Short examples (8 to 12 words) are flagged only when the whole example appears
  in a training record. Examples under 8 words are checked by `exact` only; the
  report counts them as `ngram_unchecked_count`.
- Add `minhash` to catch light edits and paraphrase (character-trigram Jaccard
  similarity, default threshold 0.8). It is slower; see the README benchmark.
- `--ngram-threshold 0.5` flags only records with at least half of their
  13-grams in training data, if any single shared 13-gram is too strict for your
  data (for example, boilerplate instructions shared by many prompts).
- `--max-contamination 0.01` lets a CI gate tolerate up to 1% contaminated
  records per target instead of failing on the first one.
