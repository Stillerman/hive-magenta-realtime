# Copyright 2026 Google LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Open a public Cloudflare quick-tunnel so phones can reach the local server."""

import logging
import re
import shutil
import subprocess
import threading
from typing import Optional

logger = logging.getLogger("hive.tunnel")

_URL_RE = re.compile(r"https://[a-z0-9-]+\.trycloudflare\.com")


class Tunnel:
    """Wraps a `cloudflared tunnel --url` subprocess and captures its public URL."""

    def __init__(self, port: int):
        self.port = port
        self.url: Optional[str] = None
        self._proc: Optional[subprocess.Popen] = None
        self._ready = threading.Event()

    def start(self, timeout: float = 30.0) -> Optional[str]:
        # Already running? Don't spawn a second cloudflared.
        if self._proc is not None and self._proc.poll() is None:
            return self.url
        exe = shutil.which("cloudflared")
        if not exe:
            logger.warning("cloudflared not found; running without a public tunnel.")
            return None
        self._proc = subprocess.Popen(
            [exe, "tunnel", "--url", f"http://localhost:{self.port}", "--no-autoupdate"],
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, bufsize=1,
        )
        threading.Thread(target=self._read_output, daemon=True).start()
        self._ready.wait(timeout=timeout)
        if self.url:
            logger.info("Tunnel ready: %s", self.url)
        else:
            logger.warning("Tunnel did not report a URL within %.0fs.", timeout)
        return self.url

    def _read_output(self) -> None:
        assert self._proc and self._proc.stdout
        for line in self._proc.stdout:
            if self.url is None:
                m = _URL_RE.search(line)
                if m:
                    self.url = m.group(0)
                    self._ready.set()
            logger.debug("cloudflared: %s", line.rstrip())

    def stop(self) -> None:
        if self._proc and self._proc.poll() is None:
            self._proc.terminate()
            try:
                self._proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self._proc.kill()
        self._proc = None
        self.url = None
        self._ready.clear()
