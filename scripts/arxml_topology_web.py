"""Serve a local browser UI for ARXML topology generation."""

# flake8: noqa: E501

from __future__ import annotations

import argparse
import json
import logging
import mimetypes
import tempfile
import threading
import uuid
import webbrowser
from email import policy
from email.parser import BytesParser
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote, urlparse

from arxml_to_topology import generate_topology

logger = logging.getLogger(__name__)

PAGE = """<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>FLYNC Topology Explorer</title>
  <style>
    :root { color-scheme: light; --ink: #182126; --muted: #657178; --paper: #f3f0e8; --panel: #fffdf8; --line: #d7d0c2; --accent: #c34f2f; --accent-dark: #8f3020; --teal: #146b67; }
    * { box-sizing: border-box; }
    [hidden] { display: none !important; }
    body { margin: 0; min-height: 100vh; color: var(--ink); background: radial-gradient(circle at 80% 0%, #fff8df 0, transparent 35%), var(--paper); font: 15px/1.5 Georgia, serif; }
    header { padding: 34px clamp(22px, 6vw, 86px) 28px; border-bottom: 1px solid var(--line); }
    .eyebrow { color: var(--accent-dark); font: 700 11px/1.2 "Trebuchet MS", sans-serif; letter-spacing: .16em; text-transform: uppercase; }
    h1 { max-width: 700px; margin: 8px 0 8px; font-size: clamp(34px, 6vw, 68px); line-height: .98; font-weight: 500; }
    header p { max-width: 680px; margin: 0; color: var(--muted); font-size: 17px; }
    main { display: grid; grid-template-columns: minmax(260px, 350px) 1fr; gap: 22px; padding: 26px clamp(22px, 6vw, 86px) 60px; }
    section { background: color-mix(in srgb, var(--panel) 92%, transparent); border: 1px solid var(--line); box-shadow: 0 14px 40px #56452a12; }
    .controls { padding: 22px; align-self: start; }
    label { display: block; margin-bottom: 8px; font: 700 12px "Trebuchet MS", sans-serif; letter-spacing: .04em; text-transform: uppercase; }
    input { width: 100%; padding: 12px; border: 1px solid #bcb3a4; background: #fffefa; color: var(--ink); font: 14px Consolas, monospace; }
    input[type=file] { padding: 9px; font: 13px "Trebuchet MS", sans-serif; }
    .field-label { margin-top: 18px; }
    button { width: 100%; margin-top: 14px; padding: 13px 16px; border: 0; background: var(--accent); color: white; cursor: pointer; font: 700 13px "Trebuchet MS", sans-serif; letter-spacing: .04em; text-transform: uppercase; }
    button:hover { background: var(--accent-dark); }
    button:disabled { cursor: wait; opacity: .55; }
    .hint, #status { color: var(--muted); font-size: 13px; }
    .hint { margin: 14px 0 0; }
    #status { min-height: 44px; margin: 18px 0 0; padding-top: 14px; border-top: 1px solid var(--line); white-space: pre-wrap; }
    #log { max-height: 150px; overflow: auto; margin: 14px 0 0; padding: 10px; background: #f0ece2; color: #526067; font: 11px/1.45 Consolas, monospace; }
    .viewer { display: flex; min-height: 620px; height: min(78vh, 900px); flex-direction: column; overflow: hidden; }
    .viewer-head { display: flex; justify-content: space-between; gap: 14px; align-items: center; padding: 16px 20px; border-bottom: 1px solid var(--line); font: 700 13px "Trebuchet MS", sans-serif; }
    .links { display: flex; flex-wrap: wrap; gap: 12px; font-weight: 400; }
    a { color: var(--teal); }
    #diagram { display: block; width: 100%; height: 100%; min-height: 0; border: 0; background: white; object-fit: contain; object-position: top center; }
    .empty { display: grid; flex: 1; min-height: 0; place-items: center; padding: 30px; color: var(--muted); text-align: center; }
    @media (max-width: 800px) { main { grid-template-columns: 1fr; } .viewer { min-height: 520px; height: 70vh; } }
  </style>
</head>
<body>
  <header><div class="eyebrow">FLYNC / ARXML importer</div><h1>Topology Explorer</h1><p>Point the local converter at an ARXML folder, then inspect the generated architecture diagram directly in your browser.</p></header>
  <main>
    <section class="controls">
    <form id="form"><label for="input">ARXML folder path</label><input id="input" name="input" placeholder="D:\\path\\to\\arxml-folder"><label class="field-label" for="picker">Or browse a local folder</label><input id="picker" type="file" webkitdirectory directory multiple accept=".arxml"><p class="hint">Choose a folder to upload its nested <code>.arxml</code> files, or type a local path to keep large extracts on disk.</p><button id="submit" type="submit">Generate diagram</button></form>
    <div id="status">Ready. Java must be available on PATH for SVG/HTML rendering.</div><pre id="log" aria-live="polite">Waiting for a generation run.</pre>
    </section>
    <section class="viewer"><div class="viewer-head"><span>Generated architecture</span><span class="links" id="links"></span></div><div id="empty" class="empty">Your rendered topology will appear here.</div><img id="diagram" hidden alt="Generated FLYNC topology diagram"></section>
  </main>
  <script>
        const form = document.querySelector('#form'); const input = document.querySelector('#input'); const picker = document.querySelector('#picker'); const submit = document.querySelector('#submit'); const status = document.querySelector('#status'); const log = document.querySelector('#log'); const image = document.querySelector('#diagram'); const empty = document.querySelector('#empty'); const links = document.querySelector('#links');
        picker.addEventListener('change', () => { if (picker.files.length) { input.value = ''; status.textContent = `${picker.files.length} local files selected.`; } });
        const waitForJob = async (jobId) => { while (true) { const response = await fetch(`/api/job/${jobId}`); const data = await response.json(); log.textContent = data.logs.join('\\n'); log.scrollTop = log.scrollHeight; if (data.state === 'done') return data; if (data.state === 'error') throw new Error(data.error || 'Generation failed; check the backend log.'); await new Promise(resolve => setTimeout(resolve, 350)); } };
        form.addEventListener('submit', async (event) => { event.preventDefault(); submit.disabled = true; links.replaceChildren(); image.hidden = true; empty.hidden = false; log.textContent = 'Starting generation...';
            try { let response; if (picker.files.length) { const body = new FormData(); for (const file of picker.files) body.append('files', file, file.webkitRelativePath || file.name); response = await fetch('/api/generate-upload', { method: 'POST', body }); } else { if (!input.value) throw new Error('Choose a folder or enter a local folder path.'); response = await fetch('/api/generate', { method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({input_folder: input.value}) }); } const data = await response.json(); if (!response.ok) throw new Error(data.error || 'Generation failed'); const job = await waitForJob(data.job_id); const result = job.result;
                image.src = result.svg + '?t=' + Date.now(); image.hidden = false; empty.hidden = true; links.innerHTML = `<a href="${result.config}" download>FLYNC config ZIP</a><a href="${result.svg}" download>SVG download</a><a href="${result.html}" target="_blank">HTML viewer</a><a href="${result.puml}" download>PUML source</a>`; status.textContent = `Generated ${result.files} ARXML files into ${result.ecus} ECU models.`;
            } catch (error) { status.textContent = error.message; log.textContent += `\\nError: ${error.message}`; } finally { submit.disabled = false; }
        });
  </script>
</body>
</html>"""


class TopologyServer(ThreadingHTTPServer):
    """Local server carrying generated artifact sessions."""

    def __init__(self, address: tuple[str, int], temp_root: Path):
        super().__init__(address, TopologyHandler)
        self.temp_root = temp_root
        self.sessions: dict[str, Path] = {}
        self.jobs: dict[str, dict] = {}
        self.lock = threading.Lock()


class TopologyHandler(BaseHTTPRequestHandler):
    """Serve the UI and local generated topology artifacts."""

    server: TopologyServer

    def do_GET(self):  # noqa: N802
        parsed = urlparse(self.path)
        if parsed.path == "/":
            self._send_bytes(PAGE.encode("utf-8"), "text/html; charset=utf-8")
            return
        parts = [unquote(part) for part in parsed.path.split("/") if part]
        if len(parts) == 3 and parts[0] == "api" and parts[1] == "job":
            self._send_json(self._job_status(parts[2]))
            return
        if len(parts) == 4 and parts[0] == "api" and parts[1] == "artifact":
            self._serve_artifact(parts[2], parts[3])
            return
        self.send_error(HTTPStatus.NOT_FOUND)

    def do_POST(self):  # noqa: N802
        request_path = urlparse(self.path).path
        if request_path == "/api/generate-upload":
            self.do_POST_upload()
            return
        if request_path != "/api/generate":
            self.send_error(HTTPStatus.NOT_FOUND)
            return
        try:
            length = int(self.headers.get("Content-Length", "0"))
            payload = json.loads(self.rfile.read(length))
            input_folder = Path(payload["input_folder"])
            if not input_folder.is_dir():
                raise ValueError(f"Input folder does not exist: {input_folder}")
            self._send_json({"job_id": self._start_job(input_folder)})
        except (KeyError, json.JSONDecodeError, OSError, RuntimeError, ValueError) as exc:
            self._send_json({"error": str(exc)}, HTTPStatus.BAD_REQUEST)

    def do_POST_upload(self):
        """Start a job from files selected by the browser folder picker."""
        content_type = self.headers.get("Content-Type", "")
        if not content_type.startswith("multipart/form-data"):
            self._send_json({"error": "Expected a folder upload"}, HTTPStatus.BAD_REQUEST)
            return
        try:
            length = int(self.headers.get("Content-Length", "0"))
            message = BytesParser(policy=policy.default).parsebytes(f"Content-Type: {content_type}\r\n\r\n".encode() + self.rfile.read(length))
            upload_root = Path(tempfile.mkdtemp(prefix="arxml-upload-", dir=self.server.temp_root))
            count = 0
            for part in message.iter_attachments():
                filename = part.get_filename()
                if not filename or not filename.lower().endswith(".arxml"):
                    continue
                relative = Path(filename.replace("/", "\\"))
                if relative.is_absolute() or ".." in relative.parts:
                    raise ValueError("Invalid uploaded relative path")
                target = upload_root / relative
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(part.get_payload(decode=True) or b"")
                count += 1
            if count == 0:
                raise ValueError("No .arxml files were selected")
            self._send_json({"job_id": self._start_job(upload_root)})
        except (OSError, ValueError) as exc:
            self._send_json({"error": str(exc)}, HTTPStatus.BAD_REQUEST)

    def _start_job(self, input_folder: Path) -> str:
        job_id = uuid.uuid4().hex
        with self.server.lock:
            self.server.jobs[job_id] = {"state": "running", "logs": ["Input accepted."]}
        threading.Thread(target=self._run_job, args=(job_id, input_folder), daemon=True).start()
        return job_id

    def _run_job(self, job_id: str, input_folder: Path):
        try:
            output_folder = self.server.temp_root / job_id
            generate_topology(input_folder, output_folder, progress=lambda message: self._log(job_id, message))
            result = {
                "ecus": _count_ecus(input_folder),
                "files": len(list(input_folder.rglob("*.arxml"))),
                "svg": f"/api/artifact/{job_id}/topology.svg",
                "html": f"/api/artifact/{job_id}/topology.html",
                "puml": f"/api/artifact/{job_id}/topology.puml",
                "config": f"/api/artifact/{job_id}/flync_config.zip",
            }
            with self.server.lock:
                self.server.sessions[job_id] = output_folder
                self.server.jobs[job_id].update(state="done", logs=self.server.jobs[job_id]["logs"] + ["Diagram ready."], result=result)
        except (OSError, RuntimeError, ValueError) as exc:
            with self.server.lock:
                logs = self.server.jobs[job_id]["logs"] + [f"Generation failed: {exc}"]
                self.server.jobs[job_id].update(state="error", logs=logs, error=str(exc))

    def _log(self, job_id: str, message: str):
        logger.info("[%s] %s", job_id[:8], message)
        with self.server.lock:
            self.server.jobs[job_id]["logs"].append(message)

    def _job_status(self, job_id: str) -> dict:
        with self.server.lock:
            job = self.server.jobs.get(job_id)
            if job is None:
                return {"state": "error", "logs": [], "error": "Unknown generation job"}
            return dict(job)

    def _serve_artifact(self, session_id: str, filename: str):
        with self.server.lock:
            folder = self.server.sessions.get(session_id)
        if folder is None or filename not in {"topology.svg", "topology.html", "topology.puml", "flync_config.zip"}:
            self.send_error(HTTPStatus.NOT_FOUND)
            return
        path = folder / filename
        if not path.is_file():
            self.send_error(HTTPStatus.NOT_FOUND)
            return
        self._send_bytes(path.read_bytes(), mimetypes.guess_type(filename)[0] or "application/octet-stream")

    def _send_json(self, payload: dict, status: HTTPStatus = HTTPStatus.OK):
        self._send_bytes(json.dumps(payload).encode("utf-8"), "application/json", status)

    def _send_bytes(self, content: bytes, content_type: str, status: HTTPStatus = HTTPStatus.OK):
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(content)))
        self.end_headers()
        self.wfile.write(content)

    def log_message(self, format, *args):
        return


def _count_ecus(input_folder: Path) -> int:
    """Return the normalized ECU count without exposing source names."""
    from flync_converter.base import ConverterConfig
    from flync_converter.converters.arxml_converter import ARXMLConverter

    return len(ARXMLConverter(ConverterConfig(config_path=str(input_folder))).decode().ecus)


def main() -> int:
    """Start the local topology web application."""
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    parser = argparse.ArgumentParser(description="Open a browser UI for ARXML topology generation.")
    parser.add_argument("--host", default="127.0.0.1", help="Interface to bind; defaults to localhost.")
    parser.add_argument("--port", type=int, default=8765, help="Port to serve; defaults to 8765.")
    parser.add_argument("--no-browser", action="store_true", help="Do not open the browser automatically.")
    args = parser.parse_args()
    temp_root = Path(tempfile.mkdtemp(prefix="flync-topology-web-"))
    server = TopologyServer((args.host, args.port), temp_root)
    url = f"http://{args.host}:{args.port}/"
    print(f"FLYNC topology web app: {url}")
    if not args.no_browser:
        webbrowser.open(url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopping FLYNC topology web app.")
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
