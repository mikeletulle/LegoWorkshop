# sf_login.py
#
# Run this once to log into Salesforce via browser and save:
#   - access_token
#   - instance_url
#   - org_id
#
# into sf_token_info.json in the current folder.
#
# expects file in same directory called sf_config.json that contains:
#{
#  "CLIENT_ID" : "xxxxx",
#  "CLIENT_SECRET" : "xxxxx"
#}
# All other code (salesforce_pubsub.py, bridge_main.py) will just read that file.

import http.server
import socketserver
import threading
import webbrowser
import urllib.parse
import requests
import json
import sys
from pathlib import Path

# ---------- CONFIGURATION ----------

# Use https://test.salesforce.com for sandboxes
LOGIN_BASE_URL = "https://login.salesforce.com"

# Must match exactly what you put in the Connected App
REDIRECT_URI = "http://localhost:8080/callback"

# File paths
TOKEN_FILE = Path("sf_token_info.json")
CONFIG_FILE = Path("sf_config.json")

# Load CLIENT_ID and CLIENT_SECRET from sf_config.json
try:
    if not CONFIG_FILE.exists():
        print(f"ERROR: {CONFIG_FILE} not found.")
        print("Please create it with the following format:")
        print('{\n  "CLIENT_ID": "...",\n  "CLIENT_SECRET": "..."\n}')
        sys.exit(1)

    with open(CONFIG_FILE, "r") as f:
        config = json.load(f)
        CLIENT_ID = config.get("CLIENT_ID")
        CLIENT_SECRET = config.get("CLIENT_SECRET")

    if not CLIENT_ID or not CLIENT_SECRET:
        print(f"ERROR: CLIENT_ID or CLIENT_SECRET missing in {CONFIG_FILE}")
        sys.exit(1)

except Exception as e:
    print(f"Error reading configuration file: {e}")
    sys.exit(1)

# -------------------------------------------------


def extract_org_id_from_identity_url(identity_url: str) -> str:
    """
    Identity URL looks like: https://login.salesforce.com/id/ORGID/USERID
    We want the ORGID.
    """
    parts = urllib.parse.urlparse(identity_url)
    segments = parts.path.strip("/").split("/")
    if len(segments) >= 3 and segments[0] == "id":
        return segments[1]
    raise ValueError(f"Cannot parse org id from identity URL: {identity_url}")


def build_auth_url(state: str) -> str:
    params = {
        "response_type": "code",
        "client_id": CLIENT_ID,
        "redirect_uri": REDIRECT_URI,
        "state": state,
        "prompt": "login",  # always show login screen
    }
    return f"{LOGIN_BASE_URL}/services/oauth2/authorize?{urllib.parse.urlencode(params)}"


class OAuthHandler(http.server.BaseHTTPRequestHandler):
    """HTTP handler that receives the /callback with ?code=..."""

    auth_code = None
    error = None
    event = None

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        if parsed.path != "/callback":
            self.send_response(404)
            self.end_headers()
            self.wfile.write(b"Not found")
            return

        params = urllib.parse.parse_qs(parsed.query)
        if "error" in params:
            OAuthHandler.error = params.get("error_description", params.get("error", ["Unknown error"]))[0]
        else:
            OAuthHandler.auth_code = params.get("code", [None])[0]

        # Simple web page for the user
        self.send_response(200)
        self.send_header("Content-Type", "text/html")
        self.end_headers()
        self.wfile.write(b"<html><body><h2>Salesforce login complete. You may close this window.</h2></body></html>")

        if OAuthHandler.event is not None:
            OAuthHandler.event.set()

    def log_message(self, format, *args):
        # silence default logging
        return


def run_local_server_and_get_code(timeout=180) -> str:
    """Start a small HTTP server and wait for the /callback with ?code="""
    event = threading.Event()
    OAuthHandler.event = event
    OAuthHandler.auth_code = None
    OAuthHandler.error = None

    with socketserver.TCPServer(("localhost", 8080), OAuthHandler) as httpd:
        thread = threading.Thread(target=httpd.serve_forever, daemon=True)
        thread.start()

        print("Local callback server running at http://localhost:8080/callback")
        print("Waiting for Salesforce to redirect back with an authorization code...")

        finished = event.wait(timeout=timeout)
        httpd.shutdown()

    if not finished:
        raise TimeoutError("Timed out waiting for Salesforce OAuth callback")

    if OAuthHandler.error:
        raise RuntimeError(f"Salesforce returned an error: {OAuthHandler.error}")

    if not OAuthHandler.auth_code:
        raise RuntimeError("No authorization code received from Salesforce")

    return OAuthHandler.auth_code


def exchange_code_for_token(code: str) -> dict:
    token_url = f"{LOGIN_BASE_URL}/services/oauth2/token"
    data = {
        "grant_type": "authorization_code",
        "code": code,
        "client_id": CLIENT_ID,
        "client_secret": CLIENT_SECRET,
        "redirect_uri": REDIRECT_URI,
    }
    print("Exchanging authorization code for access token...")
    resp = requests.post(token_url, data=data)
    resp.raise_for_status()
    return resp.json()


def main():
    # 1) Open browser to Salesforce login
    state = "lego_agent_bridge"
    auth_url = build_auth_url(state)
    print("Opening Salesforce login page in your browser...")
    print(auth_url)
    webbrowser.open(auth_url)

    # 2) Run local server, wait for callback
    try:
        code = run_local_server_and_get_code()
    except Exception as e:
        print(f"Error while waiting for callback: {e}")
        sys.exit(1)

    print(f"Got authorization code: {code[:8]}...")

    # 3) Exchange code for access token
    try:
        token_response = exchange_code_for_token(code)
    except Exception as e:
        print(f"Error exchanging code for token: {e}")
        sys.exit(1)

    access_token = token_response.get("access_token")
    instance_url = token_response.get("instance_url")
    identity_url = token_response.get("id")

    if not (access_token and instance_url and identity_url):
        print("Unexpected token response, missing access_token/instance_url/id:")
        print(json.dumps(token_response, indent=2))
        sys.exit(1)

    org_id = extract_org_id_from_identity_url(identity_url)

    data = {
        "access_token": access_token,
        "instance_url": instance_url,
        "org_id": org_id,
        "identity_url": identity_url,
        "raw_token_response": token_response,
    }
    TOKEN_FILE.write_text(json.dumps(data, indent=2))

    print("\nSUCCESS! Saved Salesforce token info to:")
    print(f"  {TOKEN_FILE.resolve()}\n")
    print("This is what salesforce_pubsub.py will read automatically.")
    print("You do NOT need to set environment variables manually.")


if __name__ == "__main__":
    main()