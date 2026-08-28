"""Cattura di un frame dalla camera lato server (fallback).

Il percorso principale è la UI web, che invia il frame dal browser (getUserMedia).
Questo modulo serve quando l'agente gira senza UI: prova OpenCV, e se non è
disponibile restituisce None senza far crashare nulla.
"""

from __future__ import annotations

import base64


def capture_frame_data_url(camera_index: int = 0, max_width: int = 720) -> str | None:
    """Restituisce un data URL JPEG del frame corrente, o None se non possibile."""
    try:
        import cv2  # type: ignore
    except Exception:
        return None

    cap = cv2.VideoCapture(camera_index)
    try:
        if not cap.isOpened():
            return None
        ok, frame = cap.read()
        if not ok or frame is None:
            return None

        h, w = frame.shape[:2]
        if w > max_width:
            scale = max_width / float(w)
            frame = cv2.resize(frame, (max_width, int(h * scale)))

        ok, buf = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 80])
        if not ok:
            return None
        b64 = base64.b64encode(buf.tobytes()).decode("ascii")
        return f"data:image/jpeg;base64,{b64}"
    finally:
        cap.release()
