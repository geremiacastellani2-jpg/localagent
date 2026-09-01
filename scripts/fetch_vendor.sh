#!/usr/bin/env bash
# Scarica in locale le librerie e i modelli di visione usati dalla chat web
# (MediaPipe EfficientDet per gli oggetti, face-api per i volti), così la pagina
# non dipende dalla CDN e funziona anche offline. Idempotente: salta i file già
# presenti. Cartella: web/vendor (ignorata da git).
set -uo pipefail
cd "$(dirname "$0")/.."
V=web/vendor
MP="https://cdn.jsdelivr.net/npm/@mediapipe/tasks-vision@1.0.1"
FA="https://cdn.jsdelivr.net/npm/@vladmandic/face-api@1.7.15"
GS="https://storage.googleapis.com/mediapipe-models/object_detector"
mkdir -p "$V/mediapipe/wasm" "$V/models" "$V/faceapi/model"

fetch() {  # fetch <url> <dest>
  local url="$1" dest="$2"
  if [ -s "$dest" ]; then return 0; fi
  echo "  ↓ $(basename "$dest")"
  if ! curl -fsSL --retry 3 --max-time 600 -o "$dest.part" "$url"; then
    echo "  ✗ non scaricato: $url"; rm -f "$dest.part"; return 1
  fi
  mv "$dest.part" "$dest"
}

ok=1
fetch "$MP/vision_bundle.mjs"                    "$V/mediapipe/vision_bundle.mjs" || ok=0
for f in vision_wasm_internal.js vision_wasm_internal.wasm \
         vision_wasm_nosimd_internal.js vision_wasm_nosimd_internal.wasm \
         vision_wasm_module_internal.js vision_wasm_module_internal.wasm; do
  fetch "$MP/wasm/$f" "$V/mediapipe/wasm/$f" || ok=0
done
fetch "$GS/efficientdet_lite2/float16/1/efficientdet_lite2.tflite" "$V/models/efficientdet_lite2.tflite" || ok=0
fetch "$GS/efficientdet_lite0/float16/1/efficientdet_lite0.tflite" "$V/models/efficientdet_lite0.tflite" || ok=0
fetch "$FA/dist/face-api.js" "$V/faceapi/face-api.js" || ok=0
for f in tiny_face_detector_model.bin tiny_face_detector_model-weights_manifest.json \
         face_landmark_68_model.bin face_landmark_68_model-weights_manifest.json \
         face_recognition_model.bin face_recognition_model-weights_manifest.json; do
  fetch "$FA/model/$f" "$V/faceapi/model/$f" || ok=0
done

if [ "$ok" = 1 ]; then
  cat > "$V/manifest.json" <<JSON
{"ok": true, "mediapipe": "1.0.1", "faceapi": "1.7.15", "models": ["efficientdet_lite2", "efficientdet_lite0"]}
JSON
  echo "✓ librerie di visione in locale: $V"
else
  rm -f "$V/manifest.json"
  echo "⚠ vendor incompleto: la pagina userà la CDN (serve internet)"; exit 1
fi
