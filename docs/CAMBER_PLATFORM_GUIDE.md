# Camber Platform Guide for Rythmiq

> **Last Updated**: 30 January 2026  
> **Author**: Infrastructure Team  
> **Purpose**: Complete reference for running Rythmiq workers on Camber Cloud

---

## Table of Contents

1. [Platform Overview](#platform-overview)
2. [Key Concepts](#key-concepts)
3. [Authentication](#authentication)
4. [CLI Reference](#cli-reference)
5. [Stash (Cloud Storage)](#stash-cloud-storage)
6. [Jobs](#jobs)
7. [Apps](#apps)
8. [Python API (Jupyter Notebooks)](#python-api-jupyter-notebooks)
9. [Webhook & Callback Patterns](#webhook--callback-patterns)
10. [Rythmiq Worker Integration](#rythmiq-worker-integration)
11. [Pricing & Node Sizes](#pricing--node-sizes)
12. [Troubleshooting](#troubleshooting)
13. [Gotchas & Lessons Learned](#gotchas--lessons-learned)
14. [Quick Reference](#quick-reference)

---

## Platform Overview

**Camber** is a cloud computing platform designed for scientific computing and HPC workloads. It provides:

- **On-demand compute nodes** (CPU and GPU)
- **Managed object storage** (Stash)
- **Pre-configured engines** for scientific applications (MPI, GROMACS, LAMMPS, etc.)
- **Custom code execution** via BASE engine

### Official Resources

| Resource | URL |
|----------|-----|
| Documentation | https://docs.cambercloud.com |
| Dashboard/Login | https://app.cambercloud.com |
| CLI Installation | https://docs.cambercloud.com/docs/camber-cli/installation/ |
| Slack Community | https://join.slack.com/t/cambercloudcommunity |

### Platform Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                        Camber Cloud                             │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────────────────┐  │
│  │   Stash     │  │    Jobs     │  │         Apps            │  │
│  │  (Storage)  │  │  (Compute)  │  │  (Reusable Definitions) │  │
│  └──────┬──────┘  └──────┬──────┘  └───────────┬─────────────┘  │
│         │                │                     │                │
│         └────────────────┼─────────────────────┘                │
│                          │                                      │
│                    ┌─────▼─────┐                                │
│                    │  Engines  │                                │
│                    │ BASE, MPI │                                │
│                    │ GROMACS...│                                │
│                    └───────────┘                                │
└─────────────────────────────────────────────────────────────────┘
```

---

## Key Concepts

### Stash
Cloud object storage accessible via `stash://` URIs.
- Personal stash: `stash://your-username/path`
- Team stash: `stash://team-name/path`
- Public stash: `stash://public/path` (read-only)

### Jobs
Individual compute tasks that run on Camber nodes.
- Created via CLI or Python API
- Execute a command on specified engine
- Input/output via Stash paths

### Apps
Reusable application definitions with:
- Pre-configured commands
- Input specifications (UI forms)
- Job configurations (node size, GPU, etc.)

### Engines
Compute environments optimized for specific workloads:

| Engine | Use Case | CLI Support |
|--------|----------|-------------|
| `base` | General Python/shell scripts | ✅ |
| `mpi` | MPI parallel computing | ✅ |
| `mesa` | Stellar evolution | ✅ |
| `athena` | Astrophysical MHD | ✅ |
| `nextflow` | Bioinformatics pipelines | ✅ |
| `gromacs` | Molecular dynamics | ✅ |
| `lammps` | Materials simulation | ✅ |
| `openfoam` | CFD | ✅ |
| `container` | Custom Docker images | ⚠️ Limited |

---

## Authentication

### API Key
Your Camber API key authenticates all operations.

**Get your API key**: Log in at https://app.cambercloud.com → Settings → API Keys

### Using the API Key

```bash
# Option 1: Environment variable (recommended)
export CAMBER_API_KEY="your-api-key-here"
camber job list

# Option 2: Command-line flag
camber job list --api-key "your-api-key-here"
```

### Get User Info
```bash
camber me --api-key "$CAMBER_API_KEY"
```
Output:
```
======================User Information======================
Email:               your-email@example.com
Username:            your-username
Stash:               stash://your-username/
============================================================
```

> ⚠️ **Important**: The username shown here is required for Stash paths!

---

## CLI Reference

### Installation

```bash
# macOS
brew tap camber-ops/tap
brew install camber

# Verify
camber --version
```

### Command Structure

```
camber <resource> <action> [flags]

Resources:
  me        - User information
  stash     - File storage operations
  job       - Job management
  app       - Application management
```

### Common Flags
- `--api-key string` - API key for authentication
- `--output json` - JSON output format
- `-h, --help` - Help for command

---

## Stash (Cloud Storage)

Stash is Camber's managed object storage. Think of it like S3 with `stash://` URIs.

### Path Format
```
stash://username/path/to/file.txt
stash://team-name/shared/data/
stash://public/examples/  (read-only)
```

### List Files
```bash
# List your root directory
camber stash ls

# List specific path
camber stash ls stash://your-username/project/

# Recursive listing
camber stash ls -r stash://your-username/project/

# Include hidden files
camber stash ls -a stash://your-username/project/

# JSON output
camber stash ls --output json stash://your-username/project/
```

### Copy Files

```bash
# Upload local file to Stash
camber stash cp ./local-file.txt stash://your-username/remote/

# Upload directory (recursive)
camber stash cp -r ./local-dir stash://your-username/remote/

# Download from Stash
camber stash cp stash://your-username/file.txt ./local/

# Copy between Stash locations
camber stash cp stash://your-username/a.txt stash://your-username/backup/
```

### Create Directory
```bash
camber stash mkdir stash://your-username/new-directory
```

### Remove Files
```bash
# Remove file
camber stash rm stash://your-username/file.txt

# Remove directory (recursive)
camber stash rm -r stash://your-username/directory/

# Force (no confirmation)
camber stash rm -rf stash://your-username/directory/
```

### Test Path Existence
```bash
# Check if exists
camber stash test -e stash://your-username/file.txt

# Check if file
camber stash test -f stash://your-username/file.txt

# Check if directory
camber stash test -d stash://your-username/directory/
```

---

## Jobs

Jobs are individual compute tasks that run on Camber nodes.

### Job Lifecycle

```
PENDING → PROVISIONING → INITIALIZING → RUNNING → COMPLETED
                                              └──→ FAILED
                                              └──→ CANCELLED
```

### Create Job

```bash
camber job create \
  --engine base \
  --path stash://your-username/project/ \
  --cmd "python script.py" \
  --size small \
  --api-key "$CAMBER_API_KEY"
```

**Required flags:**
- `--engine` - Engine type (base, mpi, etc.)
- `--path` - Stash path containing your code
- `--cmd` - Command to execute
- `--size` - Node size (xxsmall, xsmall, small, medium, large)

**Optional flags:**
- `--gpu` - Enable GPU
- `--num-nodes` - Number of nodes (default: 1)

### Check Job Status
```bash
camber job get <job-id> --api-key "$CAMBER_API_KEY"
```

Output:
```
======================Job Information======================
Job ID:              12345
Status:              COMPLETED
Job Type:            BASE
Node Size:           SMALL
Command:             python script.py
With GPU:            false
Number of Nodes:     1
Start Time:          2026-01-30T02:00:00Z
Duration:            1m30s
Finish Time:         2026-01-30T02:01:30Z
===========================================================
```

### View Job Logs
```bash
# Full logs
camber job logs <job-id> --api-key "$CAMBER_API_KEY"

# Last N lines
camber job logs <job-id> --api-key "$CAMBER_API_KEY" | tail -50
```

### List Jobs
```bash
camber job list --api-key "$CAMBER_API_KEY"
```

---

## Apps

Apps are reusable application definitions that can be run multiple times.

### App Definition File (JSON)

```json
{
  "name": "my-app-name",
  "title": "Human Readable Title",
  "description": "What this app does",
  "engineType": "MPI",
  "command": "python main.py",
  "spec": [
    {
      "type": "Input",
      "label": "Parameter Name",
      "name": "PARAM_NAME",
      "description": "Description",
      "required": true
    }
  ],
  "jobConfig": [
    {
      "type": "Select",
      "label": "System Size",
      "name": "system_size",
      "options": [
        {
          "label": "Small",
          "value": "small",
          "mapValue": {
            "nodeSize": "XXSMALL",
            "numNodes": 1,
            "withGpu": false
          }
        }
      ],
      "defaultValue": "small"
    }
  ]
}
```

### Supported Input Types (spec)

| Type | Description |
|------|-------------|
| `Input` | Single-line text |
| `Textarea` | Multi-line text |
| `Select` | Dropdown selection |
| `Radio` | Radio buttons |
| `Switch` | Boolean toggle |
| `Checkbox` | Checkbox |
| `Stash File` | File from Stash |
| `Multi Stash File` | Multiple files |

### Create App
```bash
camber app create --file my-app.json --api-key "$CAMBER_API_KEY"
```

### Describe App
```bash
camber app describe my-app-name --api-key "$CAMBER_API_KEY"
```

### Run App
```bash
camber app run my-app-name \
  --input PARAM_NAME=value \
  --api-key "$CAMBER_API_KEY"
```

### Delete App
```bash
camber app delete my-app-name --api-key "$CAMBER_API_KEY"
```

### List Apps
```bash
camber app list --api-key "$CAMBER_API_KEY"
```

---

## Python API (Jupyter Notebooks)

Camber provides a Python SDK designed primarily for Jupyter notebook workflows. This is ideal for interactive development, experimentation, and data science use cases.

### Installation

```bash
pip install camber
```

### Authentication

```python
import os
os.environ['CAMBER_API_KEY'] = 'your-api-key-here'

# Or set in notebook
import camber
# API key is read from CAMBER_API_KEY environment variable
```

### Available Modules

| Module | Purpose |
|--------|---------|
| `camber.mpi` | General MPI workloads |
| `camber.stash` | File storage operations |
| `camber.mesa` | Stellar evolution (MESA) |
| `camber.athena` | Astrophysical MHD |
| `camber.changa` | N-body simulations |
| `camber.nextflow` | Bioinformatics pipelines |

### Stash Operations (Python)

```python
import camber.stash

# Access your private stash
private = camber.stash.private
public = camber.stash.public

# List files
private.ls("data/")
# ['dataset1.csv', 'dataset2.csv', 'images/']

# Change directory
private.cd("data")

# Copy files
private.cp(src_path="docs/README.md", dest_path="backup/")

# Copy directory recursively
private.cp(src_path="data", dest_path="data-backup", recursive=True)

# Remove files
private.rm("old-file.txt")
private.rm("old-directory/", recursive=True)

# Copy between stashes (team → private)
team = camber.stash.team["myteam"]
team.cp(
    dest_stash=private,
    src_path="shared-data",
    dest_path="local-copy",
    recursive=True
)

# Shorthand syntax with arrows
team.cd("~/datasets") >> private.cd("~/datasets")
```

### Creating Jobs (Python)

```python
import camber.mpi

# Create a simple MPI job
job = camber.mpi.create_job(
    command="python process_data.py",
    node_size="SMALL",
    extra_env_vars={
        "DATA_PATH": "/data/input.csv",
        "OUTPUT_PATH": "/data/output.csv"
    },
    tags=["data-processing", "batch-1"]
)

print(f"Job created: {job.job_id}")
print(f"Status: {job.status}")
```

### Scatter Jobs (Parameter Sweeps)

```python
import camber.mpi

# Run multiple jobs with different parameters
params = {
    "learning_rate": [0.001, 0.01, 0.1],
    "batch_size": [32, 64, 128]
}

jobs = camber.mpi.create_scatter_job(
    command_template="python train.py --lr {learning_rate} --batch {batch_size}",
    template_params_grid=params,
    node_size="SMALL",
    tags=["hyperparameter-sweep"]
)

# This creates 9 jobs (3 × 3 combinations)
for job in jobs:
    print(f"Job {job.job_id}: lr={job.params['learning_rate']}, batch={job.params['batch_size']}")
```

### Job Management (Python)

```python
import camber.mpi

# Get a specific job
job = camber.mpi.get_job(job_id=12345)
print(job.status)  # PENDING, RUNNING, COMPLETED, FAILED

# List all jobs
all_jobs = camber.mpi.list_jobs()

# List jobs with specific tags
tagged_jobs = camber.mpi.list_jobs(tags=["hyperparameter-sweep"])

# Delete a job
camber.mpi.delete_job(job_id=12345)
```

### Polling for Job Completion

```python
import camber.mpi
import time

job = camber.mpi.create_job(
    command="python long_running_task.py",
    node_size="MEDIUM"
)

# Poll until complete
while job.status in ["PENDING", "PROVISIONING", "INITIALIZING", "RUNNING"]:
    print(f"Job {job.job_id} status: {job.status}")
    time.sleep(30)
    job = camber.mpi.get_job(job.job_id)  # Refresh status

if job.status == "COMPLETED":
    print("Job completed successfully!")
elif job.status == "FAILED":
    print("Job failed!")
```

### CamberJob Object Attributes

```python
job.job_id        # int: Unique job identifier
job.status        # str: PENDING, RUNNING, COMPLETED, FAILED, CANCELLED
job.node_size     # str: XXSMALL, XSMALL, SMALL, MEDIUM, LARGE
job.engine_type   # str: MPI, MESA, etc.
job.command       # str: The command that was run
job.with_gpu      # bool: Whether GPU was used
job.tags          # list: Job tags
```

---

## Webhook & Callback Patterns

Camber doesn't have built-in webhook support, so we implement our own callback pattern for job completion notifications.

### Architecture

```
┌─────────────┐     ┌─────────────┐     ┌─────────────────┐
│ Rythmiq API │────▶│ Camber Job  │────▶│ Worker Process  │
│ (Submit)    │     │ (Running)   │     │ (Processing)    │
└─────────────┘     └─────────────┘     └────────┬────────┘
                                                 │
                                                 ▼ HTTP POST
┌─────────────┐     ┌─────────────────────────────────────┐
│ Rythmiq API │◀────│ Webhook Callback (job complete)    │
│ (Receive)   │     │ POST /webhooks/camber/job-complete │
└─────────────┘     └─────────────────────────────────────┘
```

### Option 1: Worker Callback (Recommended)

The worker itself calls back to Rythmiq API when processing completes.

**Worker Code Pattern:**
```python
import httpx
import os

def notify_completion(job_id: str, result: dict):
    """Send job completion webhook to Rythmiq API."""
    webhook_url = os.environ.get('WEBHOOK_URL')
    webhook_secret = os.environ.get('WEBHOOK_SECRET')
    
    if not webhook_url:
        return  # No webhook configured
    
    headers = {
        'Content-Type': 'application/json',
        'X-Webhook-Secret': webhook_secret or ''
    }
    
    payload = {
        'event': 'job.completed',
        'job_id': job_id,
        'status': result.get('status'),
        'artifacts': result.get('artifacts'),
        'metrics': result.get('metrics')
    }
    
    try:
        response = httpx.post(webhook_url, json=payload, headers=headers, timeout=30)
        response.raise_for_status()
    except Exception as e:
        # Log but don't fail the job
        print(f"Webhook notification failed: {e}")

# At end of worker processing:
result = process_job(payload)
notify_completion(payload['job_id'], result)
print(json.dumps(result))  # Still output to STDOUT
```

**Environment Variables to Pass:**
```bash
--cmd "export WEBHOOK_URL=https://your-api.com/webhooks/camber && export WEBHOOK_SECRET=secret123 && python worker.py"
```

### Option 2: API Polling

Poll Camber for job status from your backend.

**Backend Service Pattern:**
```python
import asyncio
from datetime import datetime, timedelta

class CamberJobPoller:
    def __init__(self, camber_client, callback_fn):
        self.client = camber_client
        self.callback = callback_fn
        self.active_jobs = {}  # job_id -> submission_time
    
    async def submit_job(self, job_params):
        """Submit job and start tracking."""
        job = await self.client.create_job(**job_params)
        self.active_jobs[job.job_id] = datetime.utcnow()
        return job
    
    async def poll_loop(self, interval_seconds=30):
        """Continuously poll for job completions."""
        while True:
            completed = []
            for job_id in list(self.active_jobs.keys()):
                job = await self.client.get_job(job_id)
                
                if job.status in ['COMPLETED', 'FAILED', 'CANCELLED']:
                    await self.callback(job)
                    completed.append(job_id)
            
            for job_id in completed:
                del self.active_jobs[job_id]
            
            await asyncio.sleep(interval_seconds)

# Usage:
async def on_job_complete(job):
    print(f"Job {job.job_id} finished with status: {job.status}")
    # Update database, notify user, etc.

poller = CamberJobPoller(camber_client, on_job_complete)
await poller.submit_job({...})
asyncio.create_task(poller.poll_loop())
```

### Option 3: Hybrid (Webhook + Polling Fallback)

Best reliability: try webhook first, fall back to polling.

```python
class JobCompletionHandler:
    def __init__(self):
        self.pending_callbacks = {}  # job_id -> expected_completion_time
    
    async def register_job(self, job_id: str, timeout_minutes: int = 30):
        """Register job for callback with timeout."""
        self.pending_callbacks[job_id] = {
            'registered_at': datetime.utcnow(),
            'timeout_at': datetime.utcnow() + timedelta(minutes=timeout_minutes)
        }
    
    async def handle_webhook(self, job_id: str, result: dict):
        """Handle incoming webhook from worker."""
        if job_id in self.pending_callbacks:
            del self.pending_callbacks[job_id]
        await self.process_completion(job_id, result)
    
    async def poll_for_stragglers(self):
        """Check for jobs that didn't send webhooks."""
        now = datetime.utcnow()
        for job_id, info in list(self.pending_callbacks.items()):
            if now > info['timeout_at']:
                # Webhook didn't arrive, poll Camber directly
                job = await camber_client.get_job(job_id)
                if job.status in ['COMPLETED', 'FAILED']:
                    del self.pending_callbacks[job_id]
                    await self.process_completion(job_id, {'status': job.status})
```

### Webhook Endpoint Example (FastAPI)

```python
from fastapi import FastAPI, Request, HTTPException
import hmac
import hashlib

app = FastAPI()

WEBHOOK_SECRET = os.environ.get('WEBHOOK_SECRET', '')

def verify_webhook_signature(payload: bytes, signature: str) -> bool:
    """Verify webhook signature."""
    if not WEBHOOK_SECRET:
        return True  # No secret configured
    expected = hmac.new(
        WEBHOOK_SECRET.encode(),
        payload,
        hashlib.sha256
    ).hexdigest()
    return hmac.compare_digest(expected, signature)

@app.post("/webhooks/camber/job-complete")
async def handle_camber_webhook(request: Request):
    """Handle job completion webhook from Camber worker."""
    body = await request.body()
    signature = request.headers.get('X-Webhook-Signature', '')
    
    if not verify_webhook_signature(body, signature):
        raise HTTPException(status_code=401, detail="Invalid signature")
    
    payload = await request.json()
    
    job_id = payload.get('job_id')
    status = payload.get('status')
    artifacts = payload.get('artifacts', {})
    
    # Update job status in database
    await update_job_status(job_id, status, artifacts)
    
    # Notify user if needed
    if status == 'success':
        await notify_user_job_complete(job_id)
    elif status == 'failed':
        await notify_user_job_failed(job_id, payload.get('error'))
    
    return {"received": True}
```

### ngrok for Local Development

For testing webhooks locally:

```bash
# Install ngrok
brew install ngrok

# Configure auth token
ngrok config add-authtoken YOUR_AUTH_TOKEN

# Start tunnel
ngrok http 8000

# Use the https URL as your webhook endpoint
# Example: https://abc123.ngrok-free.app/webhooks/camber/job-complete
```

---

## Rythmiq Worker Integration

### How We Use Camber

Rythmiq uses Camber's **BASE engine** to run our OCR worker:

```
┌──────────────────┐     ┌─────────────────┐     ┌──────────────────┐
│  DO Spaces       │────▶│  Camber Job     │────▶│  DO Spaces       │
│  (Input Blob)    │     │  (Worker Code)  │     │  (Output Files)  │
└──────────────────┘     └─────────────────┘     └──────────────────┘
```

### Current Setup

**Stash Location**: `stash://abhinavprakash15151692/rythmiq-worker-v2/`

**Contents**:
- `worker.py` - Main worker entrypoint
- `processors/` - OCR, quality, enhancement, schema modules
- `storage/` - DO Spaces client
- `models.py` - Data models
- `errors.py` - Error handling
- `payload.json` - Job input (updated per job)

### Submit a Job

```bash
# Set credentials
source .env

# Submit job
camber job create \
  --engine base \
  --path stash://abhinavprakash15151692/rythmiq-worker-v2 \
  --cmd "export SPACES_KEY=\${DO_SPACES_ACCESS_KEY} && export SPACES_SECRET=\${DO_SPACES_SECRET_KEY} && pip install boto3 paddleocr paddlepaddle httpx opencv-python-headless numpy pillow && cat payload.json | python worker.py" \
  --size small \
  --api-key "$CAMBER_API_KEY"
```

### Update Worker Code

```bash
# Upload latest code
camber stash cp -r ./worker stash://abhinavprakash15151692/rythmiq-worker-v2/ \
  --api-key "$CAMBER_API_KEY"
```

### Update Job Payload

```bash
# Upload payload
camber stash cp ./test-job-payload.json \
  stash://abhinavprakash15151692/rythmiq-worker-v2/payload.json \
  --api-key "$CAMBER_API_KEY"
```

### Job Payload Format

```json
{
  "job_id": "uuid-v4-here",
  "user_id": "uuid-v4-here",
  "portal_schema": {
    "id": "schema-id",
    "name": "Schema Name",
    "version": 1,
    "schema_definition": {
      "target_width": 600,
      "target_height": 800,
      "target_dpi": 300,
      "max_kb": 200,
      "filename_pattern": "{job_id}",
      "output_format": "jpeg",
      "quality": 85
    }
  },
  "input": {
    "raw_path": "blobs/uuid-here",
    "mime_type": "image/png",
    "original_filename": "document.png"
  },
  "storage": {
    "bucket": "rythmiq-one-artifacts",
    "region": "sgp1",
    "endpoint": "https://sgp1.digitaloceanspaces.com"
  }
}
```

> **Note**: Use `raw_path` (S3 key) instead of `artifact_url` for authenticated access.

---

## Pricing & Node Sizes

### CPU Nodes

| Size | Cores | Memory (GB) | Credits/Hour |
|------|-------|-------------|--------------|
| XMICRO | 1 | 4 | 0.04 |
| MICRO | 2 | 8 | 0.08 |
| XXSMALL | 4 | 16 | 0.16 |
| XSMALL | 8 | 32 | 0.32 |
| **SMALL** | **16** | **64** | **0.64** |
| MEDIUM | 32 | 128 | 1.28 |
| LARGE | 64 | 256 | 2.56 |

**Rythmiq Recommendation**: Use `SMALL` for OCR jobs (good balance of cost vs speed).

### GPU Nodes (On-Demand)

| Size | GPUs | vCPUs | Memory (GB) | Credits/Hour |
|------|------|-------|-------------|--------------|
| XSMALL | 1 | 8 | 32 | 1.5 |
| MEDIUM | 4 | 48 | 192 | 6 |
| LARGE | 8 | 192 | 768 | 12 |

### Storage (Stash)

| Capacity | Credits/Month |
|----------|---------------|
| 1 TB | 23 |

### Cost Notes
- 1 Camber Credit = 1 USD
- New accounts get **100 free credits**
- Billing only when job status is `RUNNING`

---

## Gotchas & Lessons Learned

### 1. ❌ No Direct API Endpoint

**Problem**: `https://api.camber.cloud` does not exist - it's a placeholder.

**Solution**: Use the Camber CLI (`camber`) for all operations. There is a Python API but it's primarily for notebooks.

### 2. ⚠️ Stash Paths Need Username

**Problem**: `stash://my-folder/` doesn't work.

**Solution**: Always include your username: `stash://your-username/my-folder/`

Get your username with:
```bash
camber me --api-key "$CAMBER_API_KEY"
```

### 3. ⚠️ Environment Variables in Jobs

**Problem**: Jobs don't have access to your local environment variables.

**Solution**: Export them in the command string:
```bash
--cmd "export VAR=value && python script.py"
```

### 4. ⚠️ Dependencies Not Pre-Installed

**Problem**: BASE engine has minimal Python packages.

**Solution**: Install dependencies in the command:
```bash
--cmd "pip install package1 package2 && python script.py"
```

### 5. ⚠️ Container Engine Limitations

**Problem**: The `container` engine type exists but:
- Can't pass custom inputs easily
- Limited documentation
- CLI `job create` doesn't support it

**Solution**: Use BASE engine with `pip install` for Python workloads.

### 6. ⚠️ PaddleOCR Version Compatibility

**Problem**: PaddleOCR 3.x removed `show_log` and other constructor parameters.

**Solution**: Our `worker/processors/ocr.py` includes version detection:
```python
def _detect_paddleocr_version() -> tuple:
    """Detect installed PaddleOCR version."""
    import paddleocr
    version_str = getattr(paddleocr, '__version__', '0.0.0')
    parts = version_str.split('.')
    return tuple(int(p) for p in parts[:3])
```

### 7. ⚠️ Job Input via STDIN

**Problem**: How to pass job parameters?

**Solution**: Store parameters in a JSON file on Stash, then pipe to worker:
```bash
--cmd "cat payload.json | python worker.py"
```

### 8. ⚠️ Private Artifact URLs Return 403

**Problem**: Direct URLs to DO Spaces private objects get `403 Forbidden`.

**Solution**: Use `raw_path` (S3 key) in payload instead of `artifact_url`. The worker fetches via authenticated boto3 client.

---

## Troubleshooting Guide

### Authentication Errors

#### "API key invalid" or "Unauthorized"
```
Error: Request failed with status code 401
```

**Causes & Solutions:**
1. **Wrong API key**: Verify your key at [dashboard.camber.cloud](https://dashboard.camber.cloud)
2. **Key not exported**: Ensure `export CAMBER_API_KEY="..."` is in your shell
3. **Trailing whitespace**: Copy/paste can add whitespace - trim the key
4. **Expired key**: Generate a new key from the dashboard

**Debug:**
```bash
# Test authentication
camber me --api-key "$CAMBER_API_KEY"
# Should return your username
```

#### "Permission denied" on Stash
```
Error: You don't have permission to access this stash
```

**Causes:**
- Trying to access another user's private stash
- Typo in username: `stash://abhinavprakash15151692/` vs `stash://abhinav/`

**Solution:**
```bash
# Check your exact username
camber me --api-key "$CAMBER_API_KEY"
# Use EXACTLY that username in stash paths
```

---

### Job Submission Errors

#### "Engine type not found"
```
Error: Engine 'container' not found or not available
```

**Solution**: Use `base` engine for Python workloads:
```bash
camber job create --engine base ...
```

#### "Invalid stash path"
```
Error: Path 'stash://myname/worker' is invalid
```

**Causes:**
- Missing username in path
- Wrong username

**Solution:**
```bash
# Always use full path with your username
stash://abhinavprakash15151692/rythmiq-worker-v2/
```

#### "Command failed immediately"
```
Job status: FAILED (exit code 1)
```

**Debug Steps:**
1. Check logs immediately:
   ```bash
   camber job logs JOB_ID --api-key "$CAMBER_API_KEY"
   ```

2. Common causes:
   - Missing dependencies: Add to pip install
   - Syntax error in command: Check quoting
   - File not found: Verify stash path

---

### Dependency & Import Errors

#### "ModuleNotFoundError: No module named 'X'"
```
ModuleNotFoundError: No module named 'paddleocr'
```

**Solution**: Add all dependencies to pip install in command:
```bash
--cmd "pip install boto3 paddleocr paddlepaddle httpx opencv-python-headless numpy pillow && python worker.py"
```

#### "pip: command not found"
This shouldn't happen with BASE engine. If it does:
```bash
--cmd "python -m pip install ... && python worker.py"
```

#### PaddleOCR Specific Errors

**"PaddleOCR() got an unexpected keyword argument 'show_log'"**
```
TypeError: PaddleOCR.__init__() got an unexpected keyword argument 'show_log'
```

**Cause**: PaddleOCR 3.x removed constructor parameters

**Solution**: Use version-aware initialization (implemented in our `worker/processors/ocr.py`):
```python
def _build_ocr_kwargs():
    version = _detect_paddleocr_version()
    kwargs = {'use_angle_cls': True, 'lang': 'en'}
    
    if version < (3, 0, 0):  # 2.x
        kwargs['show_log'] = False
        kwargs['use_gpu'] = False
    # 3.x: use defaults
    
    return kwargs
```

**"Segmentation fault" on PaddleOCR import (ARM64)**

**Cause**: PaddleOCR model download during import causes segfault on ARM64

**Solution**: Don't pre-download models in Docker builds:
```dockerfile
# WRONG - causes segfault on ARM64
RUN python -c "from paddleocr import PaddleOCR; PaddleOCR()"

# RIGHT - let it download at runtime
# (no pre-download step)
```

---

### Storage & File Errors

#### "403 Forbidden" on artifact download
```
botocore.exceptions.ClientError: An error occurred (403)
```

**Causes:**
1. **Wrong credentials**: Check DO_SPACES_ACCESS_KEY and DO_SPACES_SECRET_KEY
2. **Wrong bucket**: Verify bucket name and region
3. **Using URL instead of path**: Use `raw_path` not `artifact_url`

**Solution in worker:**
```python
# WRONG - uses presigned URL that expires
url = payload['input']['artifact_url']  # 403!

# RIGHT - use authenticated S3 client with raw path
raw_path = payload['input']['raw_path']  # "input/user/job/file.pdf"
s3_client.download_file(bucket, raw_path, local_path)
```

#### "File not found in Stash"
```
Error: Path 'stash://user/file.py' does not exist
```

**Debug:**
```bash
# List contents to see what's there
camber stash ls stash://USERNAME/ --api-key "$CAMBER_API_KEY"

# Check if you uploaded to the right place
camber stash ls stash://USERNAME/rythmiq-worker-v2/ --api-key "$CAMBER_API_KEY"
```

#### "No space left on device"
```
OSError: [Errno 28] No space left on device
```

**Causes:**
- Worker ephemeral storage is limited
- Downloading large files to /tmp

**Solutions:**
1. Clean up temporary files after use
2. Process files in streaming manner
3. Use larger node size for more disk space

---

### Environment Variable Issues

#### Variables not available in job
```
KeyError: 'SPACES_KEY'
```

**Cause**: Environment variables aren't passed to Camber jobs automatically

**Solution**: Export in the command string:
```bash
--cmd "export SPACES_KEY=XXX && export SPACES_SECRET=YYY && python worker.py"
```

Or use `extra_env_vars` in Python API:
```python
job = camber.mpi.create_job(
    command="python worker.py",
    extra_env_vars={
        "SPACES_KEY": "...",
        "SPACES_SECRET": "..."
    }
)
```

---

### Network & DNS Errors

#### "Name or service not known"
```
socket.gaierror: [Errno -2] Name or service not known
```

**Causes:**
- DNS resolution failed
- Service endpoint doesn't exist

**Examples we encountered:**
- `api.camber.cloud` - DOES NOT EXIST (use CLI instead)
- `sgp1.digitaloceanspaces.com` - Correct endpoint

#### "Connection refused"
```
ConnectionRefusedError: [Errno 111] Connection refused
```

**Causes:**
- Trying to connect to internal IP from Camber
- Service not running
- Firewall blocking

**Solution**: Ensure all services are publicly accessible or use proper VPN/tunneling.

---

### Job Status Issues

#### Job stuck in PENDING
**Causes:**
- No available nodes
- Queue backlog

**Solutions:**
1. Wait (usually resolves within minutes)
2. Try smaller node size
3. Check Camber status page

#### Job stuck in PROVISIONING
**Cause**: Node is being allocated

**Solution**: Wait. This typically takes 1-5 minutes for BASE engine.

#### "Job completed but no output"
**Debug:**
1. Check job logs: `camber job logs JOB_ID`
2. Ensure worker prints JSON to STDOUT
3. Check for errors that prevent reaching print statement

---

### Common Error Patterns

| Symptom | Likely Cause | Solution |
|---------|-------------|----------|
| 401 Unauthorized | Wrong/missing API key | Verify CAMBER_API_KEY |
| 403 Forbidden | Stash permission or S3 auth | Check username/credentials |
| ModuleNotFoundError | Missing pip install | Add to command |
| FileNotFoundError | Wrong stash path | Verify with `stash ls` |
| Job fails immediately | Command syntax error | Check logs for details |
| Connection refused | Wrong endpoint | Use correct service URL |
| show_log error | PaddleOCR 3.x | Use version-aware init |
| Segfault | ARM64 + PaddleOCR | Remove model pre-download |

---

### Debug Checklist

When a job fails, check in this order:

1. **Get logs first**
   ```bash
   camber job logs JOB_ID --api-key "$CAMBER_API_KEY"
   ```

2. **Check job details**
   ```bash
   camber job get JOB_ID --api-key "$CAMBER_API_KEY"
   ```

3. **Verify files are uploaded**
   ```bash
   camber stash ls stash://USERNAME/path/ --api-key "$CAMBER_API_KEY"
   ```

4. **Test locally first**
   ```bash
   # Test your command locally before submitting
   cat payload.json | python worker.py
   ```

5. **Simplify the command**
   ```bash
   # Start simple, add complexity
   --cmd "python --version"
   --cmd "pip install X && python -c 'import X; print(X.__version__)'"
   --cmd "pip install X Y Z && python worker.py"
   ```

---

## Quick Reference

### Environment Setup
```bash
# Required in .env
export CAMBER_API_KEY="your-camber-api-key"
export DO_SPACES_ACCESS_KEY="your-spaces-key"
export DO_SPACES_SECRET_KEY="your-spaces-secret"
```

### Common Commands

```bash
# Check who you are
camber me --api-key "$CAMBER_API_KEY"

# List your files
camber stash ls --api-key "$CAMBER_API_KEY"

# Upload worker code
camber stash cp -r ./worker stash://USERNAME/rythmiq-worker-v2/ --api-key "$CAMBER_API_KEY"

# Upload job payload
camber stash cp ./payload.json stash://USERNAME/rythmiq-worker-v2/payload.json --api-key "$CAMBER_API_KEY"

# Submit job
camber job create \
  --engine base \
  --path stash://USERNAME/rythmiq-worker-v2 \
  --cmd "export SPACES_KEY=XXX && export SPACES_SECRET=YYY && pip install boto3 paddleocr paddlepaddle httpx opencv-python-headless numpy pillow && cat payload.json | python worker.py" \
  --size small \
  --api-key "$CAMBER_API_KEY"

# Check job status
camber job get JOB_ID --api-key "$CAMBER_API_KEY"

# View job logs
camber job logs JOB_ID --api-key "$CAMBER_API_KEY"
```

### Successful Job Output
```json
{
  "status": "success",
  "job_id": "uuid",
  "quality_score": 0.88,
  "warnings": [],
  "artifacts": {
    "master_path": "master/user_id/job_id/job_id.enc",
    "preview_path": "output/user_id/job_id/preview.jpg"
  },
  "metrics": {
    "ocr_confidence": 0.95,
    "processing_ms": 12000
  }
}
```

---

## Related Documentation

- [DEPLOYMENT_README.md](../DEPLOYMENT_README.md) - Overall deployment guide
- [WORKER_DEPLOYMENT.md](../WORKER_DEPLOYMENT.md) - Worker deployment specifics
- [worker/processors/ocr.py](../worker/processors/ocr.py) - OCR implementation with version handling

---

## Changelog

| Date | Change |
|------|--------|
| 2026-01-30 | Initial documentation created |
| 2026-01-30 | Added PaddleOCR 3.x compatibility notes |
| 2026-01-30 | Documented BASE engine job submission |
| 2026-01-30 | Added Python API section for Jupyter notebooks |
| 2026-01-30 | Added Webhook/Callback patterns section |
| 2026-01-30 | Added comprehensive Troubleshooting guide |
