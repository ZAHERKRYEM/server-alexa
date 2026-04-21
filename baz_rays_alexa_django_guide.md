# Baz Rays — Alexa Skill + Django Integration Guide

A complete beginner-friendly guide to building an Alexa Skill that controls devices
(turn on/off) by sending voice commands to a Django API.

---

## Table of Contents

1. [How It All Works (Big Picture)](#1-how-it-all-works)
2. [Prerequisites](#2-prerequisites)
3. [Create the Alexa Skill in the Developer Console](#3-create-the-alexa-skill)
4. [Set Up the Django API](#4-set-up-the-django-api)
5. [How Alexa Intents Are Received in Django](#5-how-alexa-intents-are-received-in-django)
6. [How Django Sends a Response Back to Alexa](#6-how-django-sends-a-response-back-to-alexa)
7. [Full Working Code Example](#7-full-working-code-example)
8. [Testing the Skill](#8-testing-the-skill)
9. [Deploying Properly](#9-deploying-properly)
10. [Common Errors & Fixes](#10-common-errors--fixes)

---

## 1. How It All Works

Here is the complete flow from voice to response:

```
You speak →  Alexa device  →  Amazon servers (NLU)  →  Your Django server
                                                              ↓
You hear  ←  Alexa device  ←  Amazon servers         ←  JSON response
```

**Step-by-step:**

1. You say: *"Alexa, ask Baz Rays to turn on the lights"*
2. Amazon's servers convert your speech into a structured JSON payload called a **Request**
3. That JSON is sent via HTTPS POST to your **Django endpoint** (your webhook URL)
4. Django reads the intent name and slot values from the JSON
5. Django does its work (e.g., toggle a device), then returns a JSON **Response**
6. Amazon reads the response and Alexa speaks it back to you

The key insight: **Alexa talks to Django using plain JSON over HTTPS.** Django does not need
any special Alexa SDK — it just needs to parse and return the right JSON structure.

---

## 2. Prerequisites

Before you start, make sure you have:

| Tool | Why you need it | Get it from |
|------|----------------|-------------|
| Amazon Developer Account | To create the Alexa Skill | developer.amazon.com |
| Python 3.9+ | To run Django | python.org |
| pip | Python package manager | comes with Python |
| ngrok (for local testing) | Exposes localhost to the internet | ngrok.com |
| Basic Django knowledge | Understanding views and URLs | docs.djangoproject.com |

---

## 3. Create the Alexa Skill

### 3.1 — Log into the Alexa Developer Console

Go to: https://developer.amazon.com/alexa/console/ask

Click **"Create Skill"**.

### 3.2 — Configure the New Skill

Fill in the form:

- **Skill name:** `Baz Rays`
- **Primary locale:** English (UK) or English (US) — your choice
- **Model:** `Custom`
- **Hosting:** `Provision your own` ← IMPORTANT — this means *you* host the backend (Django)

Click **"Next"**, then choose **"Start from Scratch"**, then click **"Create Skill"**.

### 3.3 — Set the Invocation Name

This is the phrase users say to wake your skill.

In the left sidebar, click **"Invocation"**.

Set **Skill Invocation Name** to: `baz rays`

> Users will say: *"Alexa, open Baz Rays"* or *"Alexa, ask Baz Rays to..."*

Click **"Save Model"**.

### 3.4 — Create Intents

Intents represent what the user wants to do. We'll create two intents:
`TurnOnIntent` and `TurnOffIntent`.

#### Create TurnOnIntent

1. In the left sidebar, click **"Intents"** → **"+ Add Intent"**
2. Choose **"Create custom intent"**
3. Name it: `TurnOnIntent`
4. Click **"Create custom intent"**
5. Under **"Sample Utterances"**, add these phrases (press Enter after each):
   - `turn on the {device}`
   - `switch on {device}`
   - `turn {device} on`
   - `activate {device}`
   - `power on {device}`

#### Create TurnOffIntent

Repeat the same steps with:
- Intent name: `TurnOffIntent`
- Sample utterances:
  - `turn off the {device}`
  - `switch off {device}`
  - `turn {device} off`
  - `deactivate {device}`
  - `power off {device}`

### 3.5 — Create a Slot (the `{device}` variable)

A **slot** is a variable in your utterance — in this case, the device name.

1. In the left sidebar, click **"Slot Types"** → **"+ Add Slot Type"**
2. Name it: `DEVICE_TYPE`
3. Add these slot values (the devices your skill can control):
   - `lights`
   - `fan`
   - `TV`
   - `heater`
   - `air conditioning`

Now link this slot to your intents:

1. Click **TurnOnIntent** in the sidebar
2. Scroll to **"Intent Slots"**
3. You'll see `device` listed — set its **Slot Type** to `DEVICE_TYPE`
4. Repeat for **TurnOffIntent**

### 3.6 — Set the Endpoint (your Django URL)

1. In the left sidebar click **"Endpoint"**
2. Select **"HTTPS"**
3. In the **Default Region** field enter your Django URL:
   ```
   https://your-domain.com/alexa/
   ```
   (For local testing with ngrok, this will be something like `https://abc123.ngrok.io/alexa/`)
4. For the SSL certificate option, select:
   - **"My development endpoint is a sub-domain of a domain that has a wildcard certificate"**
   (when using ngrok)
   - **"My development endpoint has a certificate from a trusted certificate authority"**
   (when deployed with a real SSL cert)
5. Click **"Save Endpoints"**

### 3.7 — Build the Model

Click **"Build Model"** (top of the page). Wait ~30 seconds for it to compile.

You'll see a green "Build Successful" message when done.

---

## 4. Set Up the Django API

### 4.1 — Install Django

```bash
# Create a project folder
mkdir baz_rays_project
cd baz_rays_project

# Create a virtual environment
python -m venv venv
source venv/bin/activate       # On Windows: venv\Scripts\activate

# Install dependencies
pip install django
pip install requests            # Optional: for outgoing HTTP calls
```

### 4.2 — Create the Django Project

```bash
django-admin startproject baz_rays .
python manage.py startapp alexa_skill
```

Your folder structure should now look like:

```
baz_rays_project/
├── baz_rays/
│   ├── settings.py
│   ├── urls.py
│   └── wsgi.py
├── alexa_skill/
│   ├── views.py
│   └── urls.py     ← you'll create this
├── manage.py
└── venv/
```

### 4.3 — Register the App

Open `baz_rays/settings.py` and add `alexa_skill` to `INSTALLED_APPS`:

```python
INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    # ... other apps ...
    'alexa_skill',   # ← add this line
]
```

### 4.4 — Disable CSRF for the Alexa Endpoint

Alexa's servers won't send a Django CSRF token, so we need to exempt our endpoint.
We handle this with a decorator on the view (shown in Section 7).

---

## 5. How Alexa Intents Are Received in Django

When Alexa calls your endpoint, it sends a **POST request** with a JSON body.
Here is what that body looks like for *"turn on the lights"*:

```json
{
  "version": "1.0",
  "session": {
    "sessionId": "amzn1.echo-api.session.abc123",
    "application": {
      "applicationId": "amzn1.ask.skill.your-skill-id"
    },
    "new": true
  },
  "request": {
    "type": "IntentRequest",
    "requestId": "amzn1.echo-api.request.xyz789",
    "intent": {
      "name": "TurnOnIntent",
      "confirmationStatus": "NONE",
      "slots": {
        "device": {
          "name": "device",
          "value": "lights",
          "confirmationStatus": "NONE"
        }
      }
    }
  }
}
```

**Key fields to extract in Django:**

| Field | How to access it | Example value |
|-------|-----------------|---------------|
| Request type | `data["request"]["type"]` | `"IntentRequest"` |
| Intent name | `data["request"]["intent"]["name"]` | `"TurnOnIntent"` |
| Slot value | `data["request"]["intent"]["slots"]["device"]["value"]` | `"lights"` |

**There are also special request types** (not intents) you must handle:

- `LaunchRequest` — fired when user opens the skill with no command (*"Alexa, open Baz Rays"*)
- `SessionEndedRequest` — fired when the session closes; you must return a 200 OK but Alexa ignores your response text

---

## 6. How Django Sends a Response Back to Alexa

Your Django view must return a JSON response in **exactly** this format:

```json
{
  "version": "1.0",
  "response": {
    "outputSpeech": {
      "type": "PlainText",
      "text": "Turning on the lights."
    },
    "shouldEndSession": true
  }
}
```

**Key fields:**

| Field | Purpose |
|-------|---------|
| `version` | Always `"1.0"` |
| `outputSpeech.type` | `"PlainText"` or `"SSML"` (for richer speech) |
| `outputSpeech.text` | What Alexa will say out loud |
| `shouldEndSession` | `true` = close the skill, `false` = keep listening |

**Optional fields you can add:**

```json
{
  "version": "1.0",
  "response": {
    "outputSpeech": {
      "type": "PlainText",
      "text": "Turning on the lights."
    },
    "reprompt": {
      "outputSpeech": {
        "type": "PlainText",
        "text": "Is there anything else you'd like to control?"
      }
    },
    "card": {
      "type": "Simple",
      "title": "Baz Rays",
      "content": "Turned on the lights."
    },
    "shouldEndSession": false
  }
}
```

- `reprompt` — what Alexa says if the user doesn't respond (only used when `shouldEndSession` is `false`)
- `card` — shows a card in the Alexa app on the user's phone

---

## 7. Full Working Code Example

### 7.1 — `alexa_skill/views.py`

```python
import json
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST


# ─────────────────────────────────────────────
# Helper: Build an Alexa-compatible JSON response
# ─────────────────────────────────────────────
def build_response(speech_text, should_end_session=True, reprompt_text=None):
    """
    Returns a dict that Django will serialise into the JSON format Alexa expects.

    Args:
        speech_text (str): What Alexa will say out loud.
        should_end_session (bool): Whether to close the skill after speaking.
        reprompt_text (str | None): What to say if the user doesn't respond.
    """
    response = {
        "version": "1.0",
        "response": {
            "outputSpeech": {
                "type": "PlainText",
                "text": speech_text,
            },
            "shouldEndSession": should_end_session,
        },
    }

    if reprompt_text:
        response["response"]["reprompt"] = {
            "outputSpeech": {
                "type": "PlainText",
                "text": reprompt_text,
            }
        }

    return response


# ─────────────────────────────────────────────
# Helper: Extract slot value safely
# ─────────────────────────────────────────────
def get_slot_value(intent_data, slot_name):
    """
    Safely extracts a slot value from an intent.
    Returns None if the slot is missing or has no value.
    """
    slots = intent_data.get("slots", {})
    slot = slots.get(slot_name, {})
    return slot.get("value")  # Returns None if "value" key is absent


# ─────────────────────────────────────────────
# Simulated device state (replace with DB in production)
# ─────────────────────────────────────────────
device_states = {}  # e.g., {"lights": "on", "fan": "off"}


def control_device(device, action):
    """
    Simulates turning a device on or off.
    In a real app, this would call a smart home API or update a database.

    Returns:
        str: A human-readable confirmation message.
    """
    if not device:
        return "I'm sorry, I didn't catch which device you meant."

    device = device.lower()
    action = action.lower()  # "on" or "off"

    device_states[device] = action

    # Build a natural confirmation sentence
    if action == "on":
        return f"OK, I've turned on the {device}."
    else:
        return f"OK, I've turned off the {device}."


# ─────────────────────────────────────────────
# Intent handlers
# ─────────────────────────────────────────────
def handle_launch():
    """Called when the user opens the skill with no specific command."""
    speech = (
        "Welcome to Baz Rays! "
        "You can say things like: turn on the lights, or turn off the fan. "
        "What would you like to do?"
    )
    return build_response(speech, should_end_session=False, reprompt_text="What device would you like to control?")


def handle_turn_on(intent_data):
    """Handles TurnOnIntent."""
    device = get_slot_value(intent_data, "device")
    message = control_device(device, "on")
    return build_response(message)


def handle_turn_off(intent_data):
    """Handles TurnOffIntent."""
    device = get_slot_value(intent_data, "device")
    message = control_device(device, "off")
    return build_response(message)


def handle_help():
    """Handles the built-in AMAZON.HelpIntent."""
    speech = (
        "With Baz Rays, you can control your devices by voice. "
        "Try saying: turn on the lights, or turn off the fan."
    )
    return build_response(speech, should_end_session=False)


def handle_cancel_or_stop():
    """Handles AMAZON.CancelIntent and AMAZON.StopIntent."""
    return build_response("Goodbye!")


def handle_fallback():
    """Handles AMAZON.FallbackIntent — when Alexa isn't sure what the user said."""
    speech = "Sorry, I didn't understand that. Try saying: turn on the lights."
    return build_response(speech, should_end_session=False)


# ─────────────────────────────────────────────
# Main webhook view
# ─────────────────────────────────────────────
@csrf_exempt       # Alexa doesn't send Django's CSRF token
@require_POST      # Alexa always sends POST requests
def alexa_webhook(request):
    """
    The single endpoint that receives ALL requests from Alexa.
    Alexa sends a JSON body; we parse it, route to the right handler,
    and return a JSON response.
    """
    try:
        body = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({"error": "Invalid JSON"}, status=400)

    request_type = body.get("request", {}).get("type")

    # ── LaunchRequest: user opened the skill with no command ──
    if request_type == "LaunchRequest":
        response_data = handle_launch()

    # ── IntentRequest: user said something specific ──
    elif request_type == "IntentRequest":
        intent = body["request"]["intent"]
        intent_name = intent.get("name")

        if intent_name == "TurnOnIntent":
            response_data = handle_turn_on(intent)

        elif intent_name == "TurnOffIntent":
            response_data = handle_turn_off(intent)

        elif intent_name == "AMAZON.HelpIntent":
            response_data = handle_help()

        elif intent_name in ("AMAZON.CancelIntent", "AMAZON.StopIntent"):
            response_data = handle_cancel_or_stop()

        elif intent_name == "AMAZON.FallbackIntent":
            response_data = handle_fallback()

        else:
            # Unknown intent — respond gracefully
            response_data = build_response(
                "I'm not sure how to handle that. Try saying: turn on the lights."
            )

    # ── SessionEndedRequest: session closed (user said "cancel", timeout, etc.) ──
    elif request_type == "SessionEndedRequest":
        # Alexa ignores the response body here, but we must return 200 OK
        response_data = {"version": "1.0", "response": {}}

    else:
        response_data = build_response("Something went wrong. Please try again.")

    return JsonResponse(response_data)
```

### 7.2 — `alexa_skill/urls.py`

Create this new file:

```python
from django.urls import path
from . import views

urlpatterns = [
    path("alexa/", views.alexa_webhook, name="alexa_webhook"),
]
```

### 7.3 — `baz_rays/urls.py`

Wire the app's URLs into the main project:

```python
from django.contrib import admin
from django.urls import path, include

urlpatterns = [
    path("admin/", admin.site.urls),
    path("", include("alexa_skill.urls")),   # ← add this line
]
```

### 7.4 — `baz_rays/settings.py` changes

Add your domain (or ngrok URL) to `ALLOWED_HOSTS`:

```python
ALLOWED_HOSTS = [
    "localhost",
    "127.0.0.1",
    "abc123.ngrok.io",          # your ngrok subdomain (changes each time unless paid plan)
    "your-production-domain.com",
]
```

### 7.5 — Run the development server

```bash
python manage.py migrate    # sets up the SQLite database (needed even if we don't use it yet)
python manage.py runserver
```

Django is now running at `http://127.0.0.1:8000`.

---

## 8. Testing the Skill

### 8.1 — Expose your local server with ngrok

Open a **second terminal** (keep Django running in the first):

```bash
# If ngrok isn't installed: https://ngrok.com/download
ngrok http 8000
```

You'll see output like:

```
Forwarding  https://abc123.ngrok.io -> http://localhost:8000
```

Copy the `https://...ngrok.io` URL.

### 8.2 — Update the Alexa Endpoint

1. Go back to the Alexa Developer Console
2. Click **"Endpoint"** in the left sidebar
3. Replace the endpoint URL with: `https://abc123.ngrok.io/alexa/`
4. Click **"Save Endpoints"**

### 8.3 — Test in the Alexa Simulator

1. In the Alexa Developer Console, click **"Test"** in the top nav
2. Change **"Skill testing is enabled in:"** to **"Development"**
3. In the text box, type (or click the mic and speak):
   - `open baz rays`
   - `turn on the lights`
   - `turn off the fan`

**You should see:**
- The JSON request Alexa sent (on the left)
- The JSON response Django returned (on the right)
- Alexa's spoken response text

### 8.4 — Test with a real Alexa device

If you have an Echo device logged into the **same Amazon account** as your developer account:

1. Say: *"Alexa, open Baz Rays"*
2. Say: *"Turn on the lights"*

It will call your ngrok → Django server in real time!

### 8.5 — Check Django logs

In your Django terminal you'll see:

```
[20/Apr/2026 12:00:00] "POST /alexa/ HTTP/1.1" 200 185
```

For debugging, add a print statement in your view:

```python
body = json.loads(request.body)
print("Received request:", json.dumps(body, indent=2))   # ← add this temporarily
```

---

## 9. Deploying Properly

When you're ready to go live (not just local testing), follow these steps.

### 9.1 — Choose a hosting platform

| Platform | Beginner-friendly? | Free tier? | Notes |
|---------|-------------------|-----------|-------|
| **Railway** | ✅ Very easy | ✅ Yes | Recommended for beginners |
| **Render** | ✅ Easy | ✅ Yes | Good free tier |
| **Heroku** | ✅ Easy | ❌ Paid | Well-documented |
| **DigitalOcean** | ⚠️ Moderate | ❌ Paid | More control |
| **AWS EC2/EB** | ❌ Complex | ✅ Limited | Overkill for small skills |

### 9.2 — Prepare Django for production

**Install production dependencies:**

```bash
pip install gunicorn whitenoise
pip freeze > requirements.txt
```

**Update `settings.py` for production:**

```python
import os

# Security — never hardcode secrets in production
SECRET_KEY = os.environ.get("DJANGO_SECRET_KEY", "your-fallback-dev-key")

DEBUG = os.environ.get("DEBUG", "False") == "True"

ALLOWED_HOSTS = [
    os.environ.get("ALLOWED_HOST", "localhost"),
    "your-production-domain.com",
]

# Static files (needed even if you don't use them)
STATIC_URL = "/static/"
STATIC_ROOT = os.path.join(BASE_DIR, "staticfiles")

# WhiteNoise: serve static files without a separate CDN
MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",   # ← add this, second in list
    # ... rest of middleware ...
]
```

**Create a `Procfile`** (tells the server how to start Django):

```
web: gunicorn baz_rays.wsgi --log-file -
```

### 9.3 — Set up HTTPS

**Alexa requires HTTPS.** Your hosting platform must provide a valid SSL certificate.

- Railway, Render, and Heroku provide HTTPS automatically — nothing extra needed.
- On a VPS (DigitalOcean, etc.), use **Let's Encrypt** with Certbot:
  ```bash
  sudo apt install certbot python3-certbot-nginx
  sudo certbot --nginx -d your-domain.com
  ```

### 9.4 — Update the Alexa Endpoint (final time)

Once deployed:

1. Go to Alexa Developer Console → **Endpoint**
2. Set the URL to: `https://your-production-domain.com/alexa/`
3. SSL certificate: select **"My development endpoint has a certificate from a trusted certificate authority"**
4. Click **"Save Endpoints"** and **"Build Model"**

### 9.5 — (Optional) Verify Alexa Request Signatures

For production, Amazon recommends verifying that incoming requests actually come from
Alexa (not someone trying to fake requests to your endpoint). Use the
`ask-sdk-core` library or manually verify the `SignatureCertChainUrl` and `Signature`
headers. A simpler approach for small projects: check the `applicationId` in each request:

```python
ALEXA_APP_ID = "amzn1.ask.skill.your-skill-id-here"   # from the Alexa console

@csrf_exempt
@require_POST
def alexa_webhook(request):
    body = json.loads(request.body)

    # Verify the request comes from your skill
    app_id = body.get("session", {}).get("application", {}).get("applicationId")
    if app_id != ALEXA_APP_ID:
        return JsonResponse({"error": "Forbidden"}, status=403)

    # ... rest of your view ...
```

---

## 10. Common Errors & Fixes

| Error | Likely cause | Fix |
|-------|-------------|-----|
| `There was a problem with the requested skill's response` | Django returned a non-200 status or invalid JSON | Check Django logs; make sure `JsonResponse` is returned for all paths |
| `The remote endpoint could not be called` | Alexa can't reach your server | Check ngrok is running; confirm the URL in the Alexa console matches |
| CSRF verification failed | Missing `@csrf_exempt` decorator | Add `@csrf_exempt` above `@require_POST` on your view |
| Slot value is `None` | User said something Alexa didn't recognise | Add more sample utterances; use `get_slot_value()` safely |
| `SessionEndedRequest` causes an error | Handler is missing | Always handle `SessionEndedRequest` and return `200 OK` |
| SSL handshake error | Self-signed certificate | Use ngrok (for dev) or Let's Encrypt (for prod) |
| `ALLOWED_HOSTS` error | Missing host in Django settings | Add ngrok/production domain to `ALLOWED_HOSTS` |

---

## Quick Reference: File Structure

```
baz_rays_project/
├── baz_rays/
│   ├── settings.py        ← add ALLOWED_HOSTS, install alexa_skill app
│   ├── urls.py            ← include("alexa_skill.urls")
│   └── wsgi.py
├── alexa_skill/
│   ├── views.py           ← all the Alexa logic lives here
│   └── urls.py            ← path("alexa/", views.alexa_webhook)
├── requirements.txt       ← django, gunicorn, whitenoise
├── Procfile               ← web: gunicorn baz_rays.wsgi
└── manage.py
```

---

*Built with Django · Powered by the Alexa Skills Kit · Baz Rays 🔆*
