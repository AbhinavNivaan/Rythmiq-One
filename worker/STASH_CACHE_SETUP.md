# Camber Stash-Based Dependency Caching

## Overview

This document describes how to use Camber Stash to cache Python dependencies and PaddleOCR models, eliminating the ~30s pip install overhead on each job.

## Performance Results

| Metric | Without Cache | With Cache | Improvement |
|--------|---------------|------------|-------------|
| pip install | ~30s | 0s | -30s |
| Model download | ~4s | 0s | -4s |
| Module import | ~22s | ~22s | 0s |
| Model load | ~22s | ~20s | ~2s |
| Actual compute | ~3s | ~3s | 0s |
| **Job Runtime** | **~60s** | **~35s** | **~42%** |

## Cache Setup (One-Time)

The cache is already set up at:
- **Dependencies**: `stash://abhinavprakash15151692/latency-test/worker/cached_deps/`
- **Models**: `stash://abhinavprakash15151692/latency-test/worker/paddlex_models/`

### Re-creating the Cache (if needed)

```bash
camber job create --engine base \
  --path stash://abhinavprakash15151692/latency-test/worker \
  --cmd 'pip install --target=/home/camber/workdir/cached_deps boto3==1.34.17 paddleocr==3.4.0 paddlepaddle==3.0.0 opencv-python-headless==4.9.0.80 httpx==0.26.0 numpy==1.26.3 pillow==10.2.0 && \
         export PYTHONPATH=/home/camber/workdir/cached_deps:$PYTHONPATH && \
         PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK=True python3 -c "from paddleocr import PaddleOCR; ocr = PaddleOCR(use_angle_cls=True, lang=\"en\")" && \
         cp -r ~/.paddlex /home/camber/workdir/paddlex_models' \
  --size small
```

## Using the Cache in Jobs

### Option 1: Shell Command Prefix

Add this to the start of your job command:

```bash
ln -sf /home/camber/workdir/paddlex_models /home/camber/.paddlex && \
export PYTHONPATH=/home/camber/workdir/cached_deps:$PYTHONPATH && \
export PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK=True && \
# Your actual command here
python3 worker.py
```

### Option 2: Bootstrap Script

Create a wrapper script in your Stash path:

```bash
#!/bin/bash
# bootstrap.sh - Sets up cached environment
ln -sf /home/camber/workdir/paddlex_models /home/camber/.paddlex
export PYTHONPATH=/home/camber/workdir/cached_deps:$PYTHONPATH
export PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK=True
exec "$@"
```

Then use: `./bootstrap.sh python3 worker.py`

## Key Environment Variables

| Variable | Value | Purpose |
|----------|-------|---------|
| `PYTHONPATH` | `/home/camber/workdir/cached_deps:$PYTHONPATH` | Use cached pip packages |
| `PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK` | `True` | Skip model host connectivity check |

## Key Paths

| Path | Contents |
|------|----------|
| `/home/camber/workdir/` | Your Stash `--path` mounted here |
| `/home/camber/workdir/cached_deps/` | Cached pip packages (~141 packages, ~500MB) |
| `/home/camber/workdir/paddlex_models/` | Cached OCR models (~200MB) |
| `/home/camber/.paddlex` | Symlinked to paddlex_models |

## Validation Test

Run this to verify cache is working:

```bash
camber job create --engine base \
  --path stash://abhinavprakash15151692/latency-test/worker \
  --cmd 'ln -sf /home/camber/workdir/paddlex_models /home/camber/.paddlex && \
         export PYTHONPATH=/home/camber/workdir/cached_deps:$PYTHONPATH && \
         export PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK=True && \
         python3 -c "from paddleocr import PaddleOCR; ocr = PaddleOCR(lang=\"en\"); print(\"SUCCESS\")"' \
  --size small
```

Expected: "Model files already exist. Using cached files." messages.

## Limitations

1. **Module import time**: ~22s is unavoidable (Python loading compiled extensions)
2. **Model load time**: ~20s for loading models into memory
3. **No venv support**: Camber doesn't persist venvs, so we use `pip --target` instead

## Job IDs for Reference

| Job ID | Description | Result |
|--------|-------------|--------|
| 15370 | Setup job - installed all deps | ✅ Success (8min) |
| 15371 | First cached test | 46s (models re-downloaded) |
| 15372 | Symlink approach | 44s (models cached) |
| 15373 | Full worker test | 35s job, 20.5s runtime |

## Next Steps for Further Optimization

1. **Pre-compile bytecode**: Could cache `.pyc` files
2. **Lazy loading**: Only initialize OCR when needed
3. **Model streaming**: Stream models instead of full load
4. **GPU nodes**: Would speed up model inference significantly
