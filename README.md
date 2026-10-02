# toolkit-mmqa: dataset pre-flight and contamination check

[![License: Apache-2.0](https://img.shields.io/badge/license-Apache--2.0-blue.svg)](LICENSE)

A pip-installable, zero-GPU QA gate for fine-tuning and evaluation datasets.
Run it before you train or evaluate; it fails CI when something is wrong and
writes a report you can sign as an [in-toto](https://in-toto.io) attestation.

- **Contamination:** find evaluation and benchmark records that also appear in
  the training data (exact, word 13-gram and MinHash matching), with every
  leaked record and the training records it matches.
- **Record-level dedup:** exact and near-duplicate records in JSONL, JSON, CSV
  or text datasets (or Hugging Face Hub splits), with a deduplicated copy.
- **File-level QA:** byte-identical files, near-duplicate text files, a
  per-file SHA-256 manifest, and file-by-file diffs between dataset versions.
- **Media checks:** corrupt images, resolution statistics and perceptual-hash
  near-duplicates; corrupt, truncated or empty audio and durations.
- **Reports:** every command writes one canonical-JSON report envelope (an
  in-toto Statement v1) with a `pass` / `fail` / `error` verdict that matches
  the exit code.

The core has no dependencies. Heavy integrations are optional extras.
Video is not supported yet (video files are compared as bytes only). See
[Capability status](#capability-status).

## 5-minute example: is GSM8K's test set in its training set?

GSM8K (grade-school math, MIT license) ships a 7,473-question training split
and a 1,319-question test split.

```bash
pip install "toolkit-mmqa[fast] @ git+https://github.com/AKIVA-AI/toolkit-mmqa.git"

curl -L -o gsm8k_train.jsonl https://raw.githubusercontent.com/openai/grade-school-math/master/grade_school_math/data/train.jsonl
curl -L -o gsm8k_test.jsonl https://raw.githubusercontent.com/openai/grade-school-math/master/grade_school_math/data/test.jsonl

toolkit-mmqa contamination --train gsm8k_train.jsonl --eval test=gsm8k_test.jsonl \
  --field question --format markdown
echo "exit code $?"
```

Output (0.4 s):

```text
Verdict: **fail** (exit code 1)

| Target | Records | Contaminated | Fraction |
|---|---|---|---|
| test | 1319 | 3 | 0.0023 |

| Target | Index | Methods | Preview |
|---|---|---|---|
| test | 581 | ngram | Max plans to watch two movies this weekend. The first movie is 1 hour and 30 min |
| test | 602 | ngram | A plane travels 1200 miles in 3 hours. At the same rate, how many additional hou |
| test | 632 | ngram | Max bought stamps at the post office. Some of the stamps had a snowflake design, |
exit code 1
```

Three test questions share at least one 13-word sequence with a training
question. The JSON report (`--out contamination.json`) says exactly where; for
test question 602, 7 of its 13 distinct 13-grams occur in training questions
1314 and 5162:

```json
{
  "index": 602,
  "methods": ["ngram"],
  "ngram": {"matched": 7, "overlap": 0.538462, "size": 13, "total": 13},
  "preview": "A plane travels 1200 miles in 3 hours. At the same rate, how many additional hours would it take to travel an additional 2000 miles?",
  "target": "test",
  "train_match_count": 2,
  "train_matches": [
    {"id": null, "index": 1314, "source": "gsm8k_train.jsonl"},
    {"id": null, "index": 5162, "source": "gsm8k_train.jsonl"}
  ]
}
```

The training split itself has no exact duplicate questions but 7
near-duplicate pairs (for example, questions 1174 and 7233 at estimated
similarity 0.91). Finding them takes 2.8 s:

```bash
toolkit-mmqa dedup --input gsm8k_train.jsonl --field question --near-dup \
  --write-deduped gsm8k_train.dedup.jsonl --out dedup.json
```

To make this a CI gate, keep the exit code: `0` pass, `1` fail, `2` error. Allow
a small rate with `--max-contamination 0.01`, or add `--methods
exact,ngram,minhash` to also catch lightly edited copies. To check public
benchmarks such as MMLU or HumanEval, see [docs/benchmarks.md](docs/benchmarks.md).

## GitHub Action

```yaml
- uses: actions/checkout@v4
- uses: AKIVA-AI/toolkit-mmqa@v1.0.0
  with:
    args: contamination --train data/train.jsonl --eval data/test.jsonl --field question
    extras: fast            # optional: fast, image, audio, hf, signing
    report: mmqa-report.json
```

The step fails when the verdict is `fail` or `error`, writes the Markdown
summary to the job summary, and exposes `verdict` and `report` outputs. Pass
any command's arguments without `--out`. The tag exists once v1.0.0 is
released; until then use a commit SHA.

## Capability status

| Capability | Status | Notes |
|---|---|---|
| Exact-duplicate files (SHA-256) | Working | Any file type. `scan` |
| Per-file manifest in scan output | Working | `files: {path: {sha256, size}}` |
| File-level diff of two scans | Working | `diff`: added / removed / modified files and duplicate-group changes |
| Summary report | Working | `report` |
| Report envelope (in-toto Statement v1, canonical JSON) | Working | Default output of every command; `--format markdown` for people |
| Train/eval and benchmark contamination (exact, 13-gram, MinHash) | Working | `contamination`: lists each contaminated record with the training records it matches; CI gate with `--max-contamination` |
| Hugging Face Hub datasets as input | Working (optional `[hf]` extra) | `hf:NAME[:CONFIG]:SPLIT[@REVISION]` wherever `contamination` and `dedup` take a file; streamed |
| Record-level dedup (JSONL / JSON / CSV / text) | Working | `dedup`: exact (normalized) and near-duplicate records, optional deduplicated copy of a JSONL file |
| CI gate | Working | `scan`/`dedup --fail-on ...` and `contamination --max-contamination` exit 1 with verdict `fail` |
| Near-duplicate text (MinHash, character trigrams) | Working, small to medium corpora | `scan --near-dup-text`, `dedup --near-dup`, `contamination --methods ...,minhash`. In memory, single process; vectorized with the optional `[fast]` extra (NumPy, about 12x faster). Not built for web-scale corpora |
| Ed25519 signing and verification | Working (optional extra) | `scan --sign`, `verify`. `verify` checks the signature only; it does not re-hash files on disk. No key-generation command (use the Python API) |
| Image checks: decode errors, resolution stats, pHash/dHash near-duplicates | Working (optional `[image]` extra, Pillow) | `scan --image-checks`. Hashes match the `imagehash` library bit for bit |
| Audio checks: decode errors, truncation, empty files, duration / sample-rate stats | Working | `scan --audio-checks`. WAV via the standard library; FLAC, Ogg, MP3, AIFF with the `[audio]` extra (soundfile) |
| Audio fingerprinting (near-duplicate audio) | Planned | Not implemented |
| Video checks | Planned | Not implemented; video files are compared as bytes only |
| Media quality checks | Partial | Corrupt images and audio: Working. Blur, exposure, silence, empty text: Planned |
| GitHub Action | Working | `uses: AKIVA-AI/toolkit-mmqa@<ref>`; smoke-tested in CI |
| PyPI package | Planned | Not published yet; install from source. The release workflow is ready and waits on the one-time PyPI setup in [RELEASING.md](RELEASING.md). |

## Install

Not on PyPI yet. Install from source:

```bash
git clone https://github.com/AKIVA-AI/toolkit-mmqa.git
cd toolkit-mmqa
pip install .              # core, no dependencies
pip install ".[signing]"   # adds `cryptography` for --sign / verify
pip install ".[image]"     # adds Pillow for --image-checks
pip install ".[audio]"     # adds soundfile for FLAC / Ogg / MP3 / AIFF in --audio-checks
pip install ".[fast]"      # adds NumPy: vectorized MinHash (same results, ~12x faster)
pip install ".[hf]"        # adds datasets: read Hugging Face Hub datasets (hf:...)
```

Requires Python 3.10+.

## Quick start

```bash
# Exact duplicates + per-file manifest
toolkit-mmqa scan --root ./my-dataset --out scan.json

# Also look for near-duplicate text files
toolkit-mmqa scan --root ./my-dataset --near-dup-text --near-dup-threshold 0.85 --out scan.json

# Summary statistics
toolkit-mmqa report --input scan.json

# What changed between two versions of a dataset?
toolkit-mmqa diff --old scan_v1.json --new scan_v2.json

# Did any test question leak into the training set? (exit 1 if so)
toolkit-mmqa contamination --train train.jsonl --eval test.jsonl --field question --out contamination.json

# Duplicate and near-duplicate records in a JSONL file, plus a clean copy
toolkit-mmqa dedup --input train.jsonl --near-dup --write-deduped train.dedup.jsonl --out dedup.json

# CI gate: exit 1 if any file is duplicated
toolkit-mmqa scan --root ./my-dataset --fail-on exact-duplicates --out scan.json
```

## CLI reference

### Global flags

| Flag | Description |
|------|-------------|
| `--version` | Print version and exit |
| `--verbose`, `-v` | Verbose logging (DEBUG) to stderr |
| `--log-format {text,json}` | Log format (default `text`) |

Exit codes (the same for every command):

| Code | Verdict | Meaning |
|---|---|---|
| `0` | `pass` | Ran and every `--fail-on` check passed |
| `1` | `fail` | A `--fail-on` check failed (the report is still written) |
| `2` | `error` | Usage or input error; no verdict could be reached |
| `3` | `error` | Unexpected error |

### Output: `--out` and `--format`

Every command that writes a report takes:

| Flag | Default | Description |
|------|---------|-------------|
| `--out` | stdout | Output path |
| `--format` | `json` | `json`: the [report envelope](#report-envelope) (canonical JSON). `markdown`: a human-readable summary. `legacy-json` (`scan`, `report`, `diff` only): the pre-1.0 bare object, kept for one minor version |

### `scan`

Recursively hashes every file under `--root` and groups byte-identical files.

| Flag | Default | Description |
|------|---------|-------------|
| `--root` | required | Directory to scan |
| `--extensions` | all | Comma-separated extensions to include, e.g. `txt,jsonl` |
| `--max-file-size` | none | Skip files larger than this many bytes |
| `--follow-symlinks` / `--skip-symlinks` | skip | Whether to follow symbolic links |
| `--progress` | off | Progress bar on stderr |
| `--near-dup-text` | off | Also run near-duplicate text detection (see below) |
| `--near-dup-threshold` | `0.8` | Similarity (0 to 1) at or above which two text files are near-duplicates. Requires `--near-dup-text` |
| `--workers` | `1` | Threads hashing files in parallel |
| `--fail-on` | none | Comma-separated checks that fail the run (exit 1): `exact-duplicates`, `near-duplicates` (needs `--near-dup-text`), `corrupt-media` (needs `--image-checks` or `--audio-checks`), `image-near-duplicates` (needs `--image-checks`) |
| `--sign` | off | Sign the report with an Ed25519 private key (needs `[signing]`). With `--format json` this writes a detached signature to `<out>.sig` and needs `--out` |
| `--sign-key` | none | Path to the private key PEM (required with `--sign`) |
| `--image-checks` | off | Decode every image (by extension), report corrupt files, resolution statistics and perceptual near-duplicates. Needs `[image]` |
| `--audio-checks` | off | Decode every audio file (by extension) and report corrupt, truncated or empty files, durations, sample rates and channel counts |
| `--image-hash-distance` | `8` | Maximum pHash Hamming distance (of 64 bits) for two images to be near-duplicates |

**Near-duplicate text.** With `--near-dup-text`, every hashed file that is UTF-8
text (no NUL byte, strict decode) is shingled into character trigrams and
compared with 128-permutation MinHash. The similarity is an estimate of the
Jaccard similarity of the trigram sets. Files that are not text are listed in
`skipped_non_text`. Pairs are found with LSH banding. The band layout is chosen
so that every pair whose estimate reaches the threshold is always compared, so
LSH gives the same result as comparing all pairs. All text files are loaded
into memory; use `--extensions` and `--max-file-size` to bound large datasets.
Exact duplicates also appear as near-duplicates (similarity 1.0).

**Image checks.** With `--image-checks`, every file with an image extension
(`jpg`, `jpeg`, `png`, `gif`, `bmp`, `webp`, `tif`, `tiff`, `ppm`, `pgm`, `pbm`)
is fully decoded with Pillow; files that fail (wrong format, truncated data,
decompression-bomb limits) are listed as corrupt with the error. Each decoded
image gets a 64-bit pHash and dHash with the same definitions as the
[imagehash](https://github.com/JohannesBuchner/imagehash) library (grayscale,
Lanczos resize, DCT or neighbour differences). Images whose pHashes differ in
at most `--image-hash-distance` bits are grouped as near-duplicates; resized
and re-compressed copies usually differ by 0 to 4 bits, unrelated images by
about 32. Candidate pairs are found by splitting hashes into
`distance + 1` chunks, which cannot miss a pair within the distance.

**Audio checks.** With `--audio-checks`, every file with an audio extension
(`wav`, `flac`, `ogg`, `oga`, `opus`, `mp3`, `aif`, `aiff`) is decoded to the
end. PCM WAV uses the standard library, which also compares the frame count in
the header with the data actually present, so truncated files are caught.
Other formats, and WAV encodings the standard library cannot read, use
libsndfile through the `[audio]` extra; without it they are listed as
`unsupported`, not corrupt. Files with no audio frames count as corrupt.
Duration is frames divided by the sample rate.

### `report`

| Flag | Default | Description |
|------|---------|-------------|
| `--input` | required | Scan report (envelope or legacy JSON) |

### `diff`

| Flag | Default | Description |
|------|---------|-------------|
| `--old` | required | Older scan report |
| `--new` | required | Newer scan report |

Files are matched by relative path. Both scans must contain the `files`
manifest (scans made by versions before the manifest was added are rejected
with exit code 2; re-scan to diff them).

### `contamination`

Finds evaluation or benchmark records that also appear in the training data.
Use it for train/eval split overlap (`--eval`) and for benchmark contamination
(`--benchmark`); both are checked the same way.

```bash
toolkit-mmqa contamination --train train.jsonl --eval test=test.jsonl \
  --field question --out contamination.json
```

| Flag | Default | Description |
|------|---------|-------------|
| `--train [NAME=]SOURCE` | required | Training data: a file or `hf:...`. Repeat for several files (shards) |
| `--eval [NAME=]SOURCE` | | Evaluation split to check. Repeatable |
| `--benchmark [NAME=]SOURCE` | | Benchmark to check (reported with role `benchmark`). Repeatable. See [docs/benchmarks.md](docs/benchmarks.md) for fetching public benchmarks |
| `--field` | `text` | Record field(s) with the text, comma-separated (joined with newlines) |
| `--train-field`, `--eval-field` | `--field` | Per-side field override |
| `--id-field` | none | Field reported as the record id |
| `--methods` | `exact,ngram` | Any of `exact`, `ngram`, `minhash` |
| `--ngram-size` | `13` | Word n-gram length |
| `--min-ngram-size` | `8` | Records with this many tokens up to `ngram-size - 1` are matched as a whole |
| `--ngram-threshold` | `0` | Minimum fraction of a record's n-grams found in training data; `0` flags any overlap |
| `--minhash-threshold` | `0.8` | Minimum estimated Jaccard similarity of character trigrams |
| `--max-contamination` | `0` | Exit 1 (verdict `fail`) when any target's contaminated fraction is above this |
| `--max-train-matches` | `5` | Training records listed per contaminated record |

Input files are JSONL, a JSON array, CSV (with a header) or plain text (one
record per line), chosen by extension. A source can also be a Hugging Face Hub
dataset split, `hf:NAME[:CONFIG]:SPLIT[@REVISION]` (for example
`hf:openai/gsm8k:main:test`), with the `[hf]` extra; it is streamed. In the
report, a Hub source has `uri` `hf://datasets/NAME`, and its digest is the
SHA-256 of the records read (one canonical JSON line `{"id", "index", "text"}`
per record), so pin `@REVISION` for a reproducible digest. Reading is fail-closed: a malformed line
or a missing field is an error (exit 2) that names the file and line, and with
`--out` an `error` report is written.

**Methods.** Text is normalized first (Unicode NFKC, lowercase, `\w+` tokens),
so case, punctuation and spacing do not hide a copy.

- `exact`: the normalized texts are equal.
- `ngram`: the record shares a word 13-gram with a training record. This is the
  definition from the GPT-3 contamination study (Brown et al. 2020, Appendix C).
  The report gives the fraction of the record's distinct n-grams found in
  training data. Records of 8 to 12 tokens are flagged when the whole record
  appears in a training record; shorter records are checked by `exact` only and
  counted in `ngram_unchecked_count`.
- `minhash`: estimated Jaccard similarity of character-trigram sets is at least
  the threshold. It catches light edits. The LSH band layout never misses a pair
  whose estimate reaches the threshold.

The evaluation side is indexed in memory and training files are streamed, so
memory grows with the evaluation set, not the training set.

### `dedup`

Finds duplicate records inside text datasets (not just duplicate files).

```bash
toolkit-mmqa dedup --input train.jsonl --field text --near-dup \
  --write-deduped train.dedup.jsonl --out dedup.json
```

| Flag | Default | Description |
|------|---------|-------------|
| `--input [NAME=]SOURCE` | required | Dataset file (JSONL, JSON array, CSV or text) or `hf:...` Hub split. Repeat to deduplicate across sources |
| `--field` | `text` | Record field(s) with the text, comma-separated |
| `--id-field` | none | Field reported as the record id |
| `--near-dup` | off | Also find near-duplicates (MinHash, character trigrams) |
| `--near-dup-threshold` | `0.8` | Estimated Jaccard similarity for `--near-dup` |
| `--fail-on` | none | `exact-duplicates`, `near-duplicates`: exit 1 when found |
| `--write-deduped PATH` | none | Copy of the single JSONL or text input without removable records; kept lines are copied byte for byte |

Two records are exact duplicates when their normalized texts are equal (NFKC,
lowercase, `\w+` tokens). Duplicates are grouped transitively (exact and near
groups are merged) and the first record of each group, in input order, is kept;
the others are listed as `removable`. Records with no word characters are
counted as `empty_record_count` and never grouped. All records are held in
memory.

### `verify`

| Flag | Default | Description |
|------|---------|-------------|
| `--input` | required | Signed report |
| `--public-key` | required | Ed25519 public key PEM |
| `--signature` | `<input>.sig` | Detached signature file |

Prints `Signature is VALID` (exit 0) or `Signature is INVALID` (exit 2). A
detached signature covers the exact bytes of the report file, including the
per-file manifest and any near-duplicate results, so a valid signature means
the report is unchanged since signing. If there is no `.sig` file, `verify`
checks the embedded `signature` field of a `--format legacy-json` scan. It does
not check that files on disk still match; re-scan and compare the subject
digest for that.

Create a key pair with the Python API:

```python
from pathlib import Path
from toolkit_mmqa.signing import generate_ed25519_keypair

kp = generate_ed25519_keypair()
Path("mmqa_private.pem").write_text(kp.private_key_pem)  # keep this private
Path("mmqa_public.pem").write_text(kp.public_key_pem)
```

The private key is written unencrypted; protect it with filesystem permissions.

Any report can also be signed with the toolkit's shared signing tool, the
optional [toolkit-ml-provenance](https://github.com/AKIVA-AI/toolkit-ml-provenance)
(Ed25519, or Sigstore keyless with its `sigstore` extra):

```bash
toolkit-mlsbom sign-file scan.json
toolkit-mlsbom verify-file scan.json
```

## Report envelope

By default every report is an [in-toto Statement v1](https://github.com/in-toto/attestation/blob/main/spec/v1/statement.md),
the attestation format used by SLSA and Sigstore, written as canonical JSON
(UTF-8, sorted keys, no whitespace, trailing newline) so its SHA-256 is stable.
The format is specified in [docs/report-envelope.md](docs/report-envelope.md)
with a JSON Schema in [schemas/report-envelope.v1.json](schemas/report-envelope.v1.json).

```json
{
  "_type": "https://in-toto.io/Statement/v1",
  "subject": [{"name": "my-dataset", "digest": {"sha256": "5d1c..."}}],
  "predicateType": "https://github.com/AKIVA-AI/toolkit-mmqa/report/v1",
  "predicate": {
    "tool": {"name": "toolkit-mmqa", "version": "1.0.0"},
    "kind": "mmqa.scan",
    "created_at": "2026-09-26T18:00:00Z",
    "verdict": "pass",
    "exit_code": 0,
    "inputs": [],
    "summary": {"file_count": 3, "duplicate_group_count": 1, "failed_checks": [], "...": "..."},
    "details": {"files": {"...": "..."}, "duplicates": [["a.txt", "b.txt"]], "...": "..."}
  }
}
```

**Dataset digest.** For `scan`, the subject is the scanned directory and its
digest is the SHA-256 of the canonical JSON (sorted keys, no whitespace, no
trailing newline) of `{relative_path: sha256}` over every hashed file. Paths
use `/` on every platform. Two scans of identical contents have the same
subject digest, so the report attests to exactly which files were checked.

### `predicate.summary` by kind

| Kind | Summary fields |
|---|---|
| `mmqa.scan` | `file_count`, `total_bytes`, `duplicate_group_count`, `duplicate_file_count`, `unique_content_count`, `skipped_files`, `near_duplicate_group_count` (with `--near-dup-text`), `image_count`, `image_near_duplicate_group_count`, `audio_count`, `audio_unsupported_count`, `audio_total_seconds` (with `--audio-checks`), `corrupt_media_count` (with either), `fail_on`, `failed_checks` |
| `mmqa.report` | `file_count`, `total_bytes`, `avg_file_size`, `duplicate_group_count`, `duplicate_file_count`, `unique_file_count`, `unique_content_count`, `largest_group_size` |
| `mmqa.contamination` | `train_record_count`, `eval_record_count`, `contaminated_count`, `contaminated_fraction` (per target), `max_contamination`, `failed_targets`, `methods` |
| `mmqa.dedup` | `record_count`, `exact_duplicate_group_count`, `exact_duplicate_count`, `near_duplicate_group_count` (with `--near-dup`), `removable_count`, `kept_count`, `empty_record_count`, `fail_on`, `failed_checks` |
| `mmqa.diff` | `added_file_count`, `removed_file_count`, `modified_file_count`, `unchanged_file_count`, `added_duplicate_group_count`, `removed_duplicate_group_count` |

For `report` and `diff` the subject is the (newer) scan's dataset and
`inputs` lists the scan files read, with their SHA-256.

### `predicate.details` for `mmqa.scan`

| Field | Description |
|-------|-------------|
| `file_count`, `total_bytes` | Files hashed and their total size |
| `duplicates` | Groups (2+ paths) of byte-identical files, largest group first |
| `files` | Per-file manifest: relative path to `{sha256, size}` |
| `skipped_count`, `skipped_oversized`, `skipped_symlinks` | Files not hashed (I/O error, over `--max-file-size`, symlink) |
| `metadata` | Tool version, scanned root, UTC timestamp, filters used |
| `images` | Only with `--image-checks`: `checked_count`, `decoded_count`, `corrupt` (`path`, `error`), `resolution` (min / median / max width and height), `max_distance`, `near_duplicate_groups`, `near_duplicate_pairs` (`a`, `b`, `distance`), and per-image `hashes` (`width`, `height`, `mode`, `phash`, `dhash`) |
| `audio` | Only with `--audio-checks`: `checked_count`, `decoded_count`, `corrupt` (`path`, `error`), `unsupported` (`path`, `reason`), `duration` (total / min / median / max seconds), `sample_rates` and `channels` histograms, and per-file `files` (`duration`, `frames`, `sample_rate`, `channels`) |
| `near_duplicates` | Only with `--near-dup-text`: threshold, number of text files, skipped non-text paths, groups, and pairwise similarity scores (keyed `"a|b"`) |

With `--format legacy-json` the scan prints this `details` object on its own
(plus an embedded `signature` with `--sign`).

### `predicate.details` for `mmqa.contamination`

| Field | Description |
|-------|-------------|
| `parameters` | Methods, n-gram sizes and thresholds used |
| `train` | Each training file and its record count |
| `targets` | Per target: `name`, `role`, `record_count`, `contaminated_count`, `contaminated_fraction`, `by_method` counts, `ngram_unchecked_count` |
| `contaminated_records` | One entry per contaminated record: `target`, `index` (0-based record position), `id`, `methods`, `preview`, `ngram` (`size`, `matched`, `total`, `overlap`), `minhash_similarity`, `train_match_count`, `train_matches` (`source`, `index`, `id`) |

The subject lists the evaluation and benchmark files; `inputs` lists the
training files, each with its SHA-256.

### `predicate.details` for `mmqa.dedup`

| Field | Description |
|-------|-------------|
| `parameters` | Fields, normalization, near-duplicate settings |
| `exact_groups` | Groups of exact-duplicate records, each record as `{source, index, id}`, in input order |
| `near_groups`, `near_pairs` | With `--near-dup`: near-duplicate groups and verified pairs with their similarity |
| `removable` | Records dropped when the first record of each group is kept |
| `deduped_file` | With `--write-deduped`: output path and records written |

### `predicate.details` for `mmqa.diff`

| Field | Description |
|-------|-------------|
| `added_files` | Paths only in the new scan |
| `removed_files` | Paths only in the old scan |
| `modified_files` | Paths in both scans whose SHA-256 changed |
| `unchanged_file_count` | Paths in both scans with the same SHA-256 |
| `added_duplicate_groups` / `removed_duplicate_groups` / `unchanged_duplicate_groups` | Duplicate-group changes |

A file that was renamed shows up as one removed path and one added path.

### `mmqa.report` summary fields

| Field | Description |
|-------|-------------|
| `file_count`, `total_bytes`, `avg_file_size` | Size statistics |
| `duplicate_group_count` | Number of duplicate groups |
| `duplicate_file_count` | Files that belong to any duplicate group |
| `unique_file_count` | Files with no byte-identical copy |
| `unique_content_count` | Distinct contents: the file count after exact deduplication (one file kept per group) |
| `largest_group_size` | Size of the largest duplicate group |

## Performance

MinHash signatures (used by `--near-dup-text`, `dedup --near-dup` and the
`minhash` contamination method) are computed in pure Python by default. With
the `[fast]` extra they are vectorized with NumPy and are bit-identical (tested).
Measured with [`benchmarks/bench_minhash.py`](benchmarks/bench_minhash.py) in a
container limited to 2 CPUs (Python 3.12, 128 permutations, 2,000 documents of
about 870 characters):

| Path | Time | Documents per second |
|---|---|---|
| Pure Python | 13.75 s | 145 |
| NumPy (`[fast]`) | 1.16 s | 1,726 |

End to end, `contamination --methods exact,ngram,minhash` on GSM8K (7,473
training questions against 1,319 test questions) takes 30.9 s in pure Python
and 2.7 s with `[fast]`; `exact,ngram` alone takes 0.4 s.

`scan --workers N` hashes files on N threads. Everything is in memory and in one
process: thousands to low millions of records, not web-scale corpora.

## Python API

```python
from pathlib import Path
from toolkit_mmqa import diff_scans, find_near_duplicates, generate_report, scan

result = scan(root=Path("./my-dataset"))
print(len(result.duplicates), "duplicate groups in", result.file_count, "files")

summary = generate_report(result.to_json())
print("distinct contents:", summary.unique_content_count)

texts = {"a.txt": Path("a.txt").read_text(), "b.txt": Path("b.txt").read_text()}
dedup = find_near_duplicates(texts, threshold=0.8)
print(dedup.near_duplicate_groups)
```

Contamination and record dedup:

```python
from pathlib import Path
from toolkit_mmqa import Target, check_contamination, dedup_records, load_records
from toolkit_mmqa import SourceRecords

train = load_records(Path("gsm8k_train.jsonl"), fields=["question"])
test = load_records(Path("gsm8k_test.jsonl"), fields=["question"])
result = check_contamination([("train", train)], [Target("test", test)])
print(result.targets[0]["contaminated_count"], [r["index"] for r in result.records])

dups = dedup_records([SourceRecords("train", train)], near_duplicates=True)
print(len(dups.removable), "removable records")
```

## Docker

The image includes the `image`, `audio`, `fast` and `signing` extras.

```bash
docker build -t toolkit-mmqa .
docker run --rm -v "$PWD:/data" toolkit-mmqa scan --root /data --image-checks --audio-checks
```

## Development

```bash
pip install -e ".[dev]"    # all extras plus test tools (imagehash is the test reference)
pytest -q
ruff check src/ tests/
pyright src/
```

CI also runs the suite with no extras installed (`pip install -e . pytest`) to
keep the core dependency-free; tests that need an extra skip themselves.

See [CONTRIBUTING.md](CONTRIBUTING.md) and [CHANGELOG.md](CHANGELOG.md).

## Contributing and security

Contributions are welcome: see [CONTRIBUTING.md](CONTRIBUTING.md) and the
[Code of Conduct](CODE_OF_CONDUCT.md). Please report security problems
privately, as described in [SECURITY.md](SECURITY.md).

## Releasing

Releases are cut by pushing a `vX.Y.Z` tag. CI runs the tests, builds the
sdist and wheel, checks them, attaches them to a GitHub Release and publishes
them to PyPI with Trusted Publishing. [RELEASING.md](RELEASING.md) describes
the process and how to verify a release.

## License

Apache License 2.0. See [LICENSE](LICENSE) and [NOTICE](NOTICE).

Releases before the relicensing remain available under the MIT License.
