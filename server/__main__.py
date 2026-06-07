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

"""Run the Hive server.

    .venv/bin/python -m server --port 8000
"""

import argparse
import logging

import uvicorn

from .app import create_app


def main():
    parser = argparse.ArgumentParser("hive")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--no-audio", action="store_true",
                        help="Don't auto-start the baseline music on launch.")
    parser.add_argument("--no-tunnel", action="store_true",
                        help="Don't open the Cloudflare tunnel on launch (LAN only).")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, force=True)
    app = create_app(port=args.port, autostart_audio=not args.no_audio,
                     open_tunnel_on_boot=not args.no_tunnel)
    uvicorn.run(app, host=args.host, port=args.port, log_level="warning")


if __name__ == "__main__":
    main()
