"""Test end-to-end della vista live in un browser reale (Chromium headless).

Avvia il server, apre la chat con una webcam finta, accende la camera e verifica
che oggetti/volti vengano riconosciuti e arrivino al server (/vision).

Uso:
    ./.venv/bin/pip install playwright && ./.venv/bin/playwright install chromium
    ./.venv/bin/python tests/e2e_browser.py [video.mjpeg|video.y4m]

Un file MJPEG si crea concatenando JPEG:  cat foto.jpg foto.jpg > foto.mjpeg
Variabili opzionali: CHROMIUM_PATH (binario), BROWSER_PROXY (http://host:porta).
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parent.parent
PORT = int(os.getenv("E2E_PORT", "8766"))


def main() -> int:
    video = sys.argv[1] if len(sys.argv) > 1 else None
    env = dict(os.environ, DB_PATH="/tmp/e2e_maggiordomo.db", SCHEDULER_ENABLED="false",
               LIVE_DESCRIBE_ENABLED="false")
    srv = subprocess.Popen([str(ROOT / ".venv/bin/uvicorn"), "agent.server:app", "--port", str(PORT)],
                           cwd=ROOT, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    ok = False
    try:
        for _ in range(40):
            try:
                urllib.request.urlopen(f"http://127.0.0.1:{PORT}/health", timeout=1)
                break
            except Exception:
                time.sleep(0.5)
        args = ["--use-fake-device-for-media-stream", "--use-fake-ui-for-media-stream",
                "--no-sandbox", "--enable-unsafe-swiftshader"]
        if os.getenv("BROWSER_PROXY"):
            args += [f"--proxy-server={os.environ['BROWSER_PROXY']}", "--ignore-certificate-errors",
                     "--proxy-bypass-list=127.0.0.1;localhost"]
        if video:
            args.append(f"--use-file-for-fake-video-capture={video}")
        launch = {"args": args, "headless": True}
        if os.getenv("CHROMIUM_PATH"):
            launch["executable_path"] = os.environ["CHROMIUM_PATH"]
        with sync_playwright() as p:
            browser = p.chromium.launch(**launch)
            page = browser.new_context(permissions=["camera", "microphone"]).new_page()
            logs: list[str] = []
            page.on("console", lambda m: logs.append(f"[{m.type}] {m.text}"))
            page.on("pageerror", lambda e: logs.append(f"[pageerror] {e}"))
            page.goto(f"http://127.0.0.1:{PORT}/", wait_until="load")
            page.click("#camBtn")
            objs = faces = ""
            for _ in range(60):
                time.sleep(1)
                objs = page.text_content("#liveObjs") or ""
                faces = page.text_content("#liveFaces") or ""
                if ("oggetti:" in objs or "nessun oggetto" in objs or "non caricato" in objs) and "volti:" in faces:
                    break
            time.sleep(3)
            vis = json.load(urllib.request.urlopen(f"http://127.0.0.1:{PORT}/vision?session=default"))
            errs = [l for l in logs if ("[error]" in l or "[pageerror]" in l)]
            print("liveObjs :", objs)
            print("liveFaces:", faces)
            print("vision   :", json.dumps(vis, ensure_ascii=False)[:600])
            print("errori JS:", len(errs))
            for e in errs[:10]:
                print("   ", e[:200])
            ok = vis.get("active") and "non caricato" not in objs and "non caricata" not in faces and not errs
            browser.close()
    finally:
        srv.terminate()
    print("RISULTATO:", "OK" if ok else "PROBLEMI")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
