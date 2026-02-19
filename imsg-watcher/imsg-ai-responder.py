#!/usr/bin/env python3
"""
iMessage AI Responder - Full conversation via Gemini
- Maintains conversation history (last 20 messages)
- Calls Gemini API for each message
- Returns plain text response for iMessage
"""

import urllib.request
import urllib.error
import json
import os
import sys
import ssl
from datetime import datetime
from pathlib import Path

# Configure SSL certificates
ssl_context = None
cert_paths = [
    '/usr/local/etc/openssl@3/cert.pem',
    '/usr/local/etc/openssl@1.1/cacert.pem',
    '/etc/ssl/certs/ca-certificates.crt',
    '/etc/ssl/certs/ca-bundle.crt',
]

try:
    import certifi
    cert_paths.insert(0, certifi.where())
except ImportError:
    pass

for path in cert_paths:
    if path and os.path.isfile(path):
        try:
            ssl_context = ssl.create_default_context(cafile=path)
            break
        except Exception:
            continue

if not ssl_context:
    ssl._create_default_https_context = ssl._create_unverified_context
    ssl_context = ssl._create_unverified_context()

# Configuration
SCRIPT_DIR = Path(__file__).parent
HISTORY_FILE = SCRIPT_DIR / ".conversation-history.json"
LOG_FILE = SCRIPT_DIR / "logs" / "ai-responder.log"
MAX_HISTORY = 20

# Ensure logs directory exists
LOG_FILE.parent.mkdir(parents=True, exist_ok=True)

def load_env():
    """Load API key from .env file."""
    env_path = Path.home() / ".claude" / ".env"
    api_key = None

    if env_path.exists():
        try:
            with open(env_path, 'r') as f:
                for line in f:
                    if line.startswith('GOOGLE_API_KEY='):
                        api_key = line.split('=', 1)[1].strip().strip('"\'')
                        break
        except Exception as e:
            log(f"⚠️ Error reading .env: {e}")

    return api_key or os.getenv('GOOGLE_API_KEY')

def log(msg):
    """Log to file."""
    try:
        timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        with open(LOG_FILE, 'a') as f:
            f.write(f"[{timestamp}] {msg}\n")
    except Exception as e:
        print(f"Log error: {e}", file=sys.stderr)

def load_history():
    """Load conversation history from JSON file."""
    if not HISTORY_FILE.exists():
        return []

    try:
        with open(HISTORY_FILE, 'r') as f:
            return json.load(f)
    except Exception as e:
        log(f"⚠️ Error loading history: {e}")
        return []

def save_history(history):
    """Save conversation history to JSON file, keep last N messages."""
    # Trim to last MAX_HISTORY messages
    history = history[-MAX_HISTORY:] if len(history) > MAX_HISTORY else history

    try:
        with open(HISTORY_FILE, 'w') as f:
            json.dump(history, f, indent=2)
    except Exception as e:
        log(f"⚠️ Error saving history: {e}")

def call_gemini(user_message, history):
    """Call Gemini API with conversation context."""
    api_key = load_env()

    if not api_key:
        log("❌ GOOGLE_API_KEY not found")
        return None

    # System prompt
    system_prompt = """You are Bessie, Vinod's personal AI assistant accessible via iMessage.
Be helpful, concise, and conversational. Keep responses brief for mobile reading (2-4 sentences max unless detail is specifically requested).
You have full context of the conversation history.
Identify yourself as Bessie when appropriate."""

    # Build message history for Gemini
    messages = []

    # Add system prompt as first user message if no history
    if not history:
        messages.append({
            "role": "user",
            "parts": [{"text": system_prompt + "\n\nUser: " + user_message}]
        })
    else:
        # Add conversation history
        for msg in history:
            messages.append({
                "role": msg["role"],
                "parts": [{"text": msg["content"]}]
            })

        # Add current user message
        messages.append({
            "role": "user",
            "parts": [{"text": user_message}]
        })

    # Build Gemini API request (without system field)
    payload = {
        "contents": messages
    }

    try:
        model = "gemini-2.0-flash"
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"

        req = urllib.request.Request(
            f"{url}?key={api_key}",
            data=json.dumps(payload).encode('utf-8'),
            headers={'Content-Type': 'application/json'}
        )

        with urllib.request.urlopen(req, timeout=10, context=ssl_context) as response:
            result = json.loads(response.read().decode('utf-8'))

            if 'candidates' in result and len(result['candidates']) > 0:
                content = result['candidates'][0].get('content', {})
                if 'parts' in content and len(content['parts']) > 0:
                    return content['parts'][0].get('text', '')

        log("⚠️ Gemini API returned empty response")
        return None

    except urllib.error.HTTPError as e:
        error_body = e.read().decode('utf-8')
        log(f"❌ Gemini API error ({e.code}): {error_body}")
        return None
    except Exception as e:
        log(f"❌ Gemini API error: {e}")
        return None

def main():
    """Main entry point."""
    if len(sys.argv) < 2:
        log("❌ No message provided")
        return None

    user_message = sys.argv[1]

    # Load conversation history
    history = load_history()

    # Call Gemini API
    response = call_gemini(user_message, history)

    if response:
        # Add user message and response to history
        history.append({
            "role": "user",
            "content": user_message,
            "timestamp": datetime.now().isoformat()
        })
        history.append({
            "role": "assistant",
            "content": response,
            "timestamp": datetime.now().isoformat()
        })

        # Save updated history
        save_history(history)

        # Print response to stdout (captured by shell script)
        print(response)
        log(f"✓ Response sent: {response[:50]}...")
        return 0
    else:
        log("❌ No response from Gemini API")
        return 1

if __name__ == '__main__':
    sys.exit(main() if main() is not None else 1)
