# On-Device Document Corner Detection — Design Spec

**Date:** 2026-03-28
**Scope:** Spec 1 of 2 — TFLite integration + dataset logging. Spec 2 (Vertex AI automated retraining pipeline) is separate.

---

## Goal

Replace the server-side `/detect` call with on-device YOLOv8n-pose TFLite inference for document corner detection. Eliminate network latency from the crop-preview flow. Log every confirmed quad to GCS to build a training dataset for future model retraining.

---

## Architecture

```
capture.tsx
  → crop-preview.tsx
      → documentDetector.ts
          → react-native-fast-tflite (YOLOv8n-pose, 4 keypoints)
          → if confidence < 0.5: return null → defaultQuad()
          → normalize corners → CropOverlay
  → user adjusts corners → confirms
  → job submitted to worker with confirmed_crop_quad
      → worker logs {image, quad} to GCS  ← dataset building
      → worker does perspective warp as usual
```

The worker `/detect` endpoint is **not called from the app**. It remains in the codebase but is unused by the client. `documentDetector.ts` is a pure TFLite adapter.

---

## Section 1: TFLite Model

**Architecture:** YOLOv8n-pose with 4 keypoints (one per document corner).

| Property | Value |
|---|---|
| Model variant | YOLOv8n-pose |
| Keypoints | 4 (TL, TR, BR, BL) |
| Input | 640×640 RGB, normalized 0–1 |
| Output | Keypoints in 640×640 px space → divide by 640 → normalized 0–1 |
| Model size | ~3MB TFLite |
| Inference speed | ~30–50ms on mid-range Android CPU |

**Initial training data:**
- MIDV-500 (500 identity document images with corner annotations)
- SmartDoc 2015 (document photos with corner ground truth)

Training is a one-time manual step — either locally or on Vertex AI — producing `doc_corners.tflite`.

**Model delivery:** Bundled in APK as `app-v2/assets/models/doc_corners.tflite`. Model updates ship via normal app updates until Spec 2 adds OTA model swapping.

**Confidence threshold:** If best detection confidence < 0.5, return `null`. Caller falls back to `defaultQuad()`.

---

## Section 2: App Integration

### New dependency

`react-native-fast-tflite` — Expo config plugin, Android-only for now. Add to `app.json` plugins, run `expo prebuild` to generate `android/`.

### `documentDetector.ts` — full rewrite

Replaces the `fetch(WORKER_URL/detect)` call with TFLite inference:

```ts
const model = await loadTensorflowModel(require('../assets/models/doc_corners.tflite'))
const output = await model.run([imagePixels])  // 640×640 RGB tensor
const corners = postProcess(output)            // decode YOLO pose, normalize
// returns [[x,y],[x,y],[x,y],[x,y]] normalized 0–1, or null
```

`postProcess`:
1. Decode YOLO pose output tensor
2. Pick highest-confidence detection
3. If confidence < 0.5 → return `null`
4. Return 4 corners normalized to 0–1 relative to input image dimensions

### `crop-preview.tsx` — minor change

Remove the "No document detected — adjust corners manually" message. Since detection is local and instant, `null` just means low confidence — not a network failure. The user still sees their image with the default quad and adjustable corners. No error state needed.

### Unchanged

`CropOverlay.tsx`, `captureSession.ts`, `capture.tsx`, worker enhancement pipeline — no changes.

---

## Section 3: Dataset Logging

### Worker change — `worker/worker.py`

After job receipt, before enhancement, write to GCS if `confirmed_crop_quad` is present:

```python
if payload.confirmed_crop_quad:
    log_detection_sample(
        image_bytes=raw_image,
        quad=payload.confirmed_crop_quad,
        document_type=payload.document_type,
        job_id=job_id,
    )
```

### GCS layout

```
gs://rythmiq-one-dataset/detection/
  {job_id}/image.jpg      ← original full-res image
  {job_id}/quad.json      ← {corners: [[x,y]×4], doc_type, timestamp, job_id}
```

Note: `rythmiq-one-dataset` bucket does not exist yet — must be created before deployment.

### Constraints

- No new API endpoints
- No app changes
- Non-blocking: GCS write is fire-and-forget; a logging failure must never fail the enhancement job
- No database — raw files in GCS only
- Data format is intentionally minimal; Spec 2 will formalise schema for training

---

## File Map

### New files
| File | Purpose |
|---|---|
| `app-v2/assets/models/doc_corners.tflite` | Bundled TFLite model |
| `scripts/train_initial_model.py` | One-time training script: download MIDV-500/SmartDoc, train YOLOv8n-pose, export TFLite |
| `worker/processors/dataset_logger.py` | `log_detection_sample()` — writes image + quad to GCS |

### Modified files
| File | Change |
|---|---|
| `app-v2/app.json` | Add `react-native-fast-tflite` config plugin |
| `app-v2/package.json` | Add `react-native-fast-tflite` |
| `app-v2/services/documentDetector.ts` | Replace server fetch with TFLite inference |
| `app-v2/app/(tabs)/crop-preview.tsx` | Remove "No document detected" error message |
| `worker/worker.py` | Call `log_detection_sample` when `confirmed_crop_quad` present |

---

## Out of Scope (Spec 2)

- Vertex AI automated retraining pipeline
- OTA model updates (download new `.tflite` without app update)
- Model versioning / A-B testing
- iOS support
