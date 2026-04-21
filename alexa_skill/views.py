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