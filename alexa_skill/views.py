import json
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST


# ── Your real Skill ID from the request ──────────────────────────────────────
ALEXA_APP_ID = "amzn1.ask.skill.26ff76bc-9f5d-4283-a2da-6f6e9b655548"


# ─────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────
def build_response(speech_text, should_end_session=True, reprompt_text=None):
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
            "outputSpeech": {"type": "PlainText", "text": reprompt_text}
        }
    return response


def get_slot_value(intent_data, slot_name):
    slots = intent_data.get("slots", {})
    return slots.get(slot_name, {}).get("value")


# ─────────────────────────────────────────────
# Device state (replace with DB in production)
# ─────────────────────────────────────────────
device_states = {}


def control_device(device, action):
    if not device:
        return "I didn't catch which device you meant. Please try again."
    device_states[device.lower()] = action
    verb = "turned on" if action == "on" else "turned off"
    return f"OK, I've {verb} the {device}."


# ─────────────────────────────────────────────
# Intent handlers
# ─────────────────────────────────────────────
def handle_launch():
    return build_response(
        "Welcome to Baz Rays! You can say: turn on the lights, or turn off the fan. "
        "What would you like to control?",
        should_end_session=False,
        reprompt_text="Which device would you like to control?",
    )


def handle_turn_on(intent):
    device = get_slot_value(intent, "device")
    return build_response(control_device(device, "on"))


def handle_turn_off(intent):
    device = get_slot_value(intent, "device")
    return build_response(control_device(device, "off"))


def handle_help():
    return build_response(
        "You can say: turn on the lights, turn off the fan, or turn on the TV. "
        "What would you like to do?",
        should_end_session=False,
        reprompt_text="What device would you like to control?",
    )


def handle_stop_cancel():
    return build_response("Goodbye from Baz Rays!")


def handle_fallback():
    return build_response(
        "Sorry, I didn't get that. Try saying: turn on the lights.",
        should_end_session=False,
    )


# ─────────────────────────────────────────────
# Main webhook (FIXED + DEBUG)
# ─────────────────────────────────────────────
@csrf_exempt
@require_POST
def alexa_webhook(request):
    try:
        # ── Parse JSON safely ─────────────────────────────
        try:
            body = json.loads(request.body)
            print("REQUEST:\n", json.dumps(body, indent=2))
        except json.JSONDecodeError:
            return JsonResponse({
                "version": "1.0",
                "response": {
                    "outputSpeech": {
                        "type": "PlainText",
                        "text": "Invalid request format."
                    },
                    "shouldEndSession": True
                }
            }, safe=False)

        # ── (اختياري) تحقق من skill ID ─────────────────────
        app_id = (
            body.get("session", {}).get("application", {}).get("applicationId")
            or body.get("context", {}).get("System", {}).get("application", {}).get("applicationId")
        )
        print("APP ID:", app_id)

        # ❗ معطّل مؤقتًا للتجربة
        # if app_id != ALEXA_APP_ID:
        #     return JsonResponse({"error": "Forbidden"}, status=403)

        request_type = body.get("request", {}).get("type")

        # ── LaunchRequest ─────────────────────────────────
        if request_type == "LaunchRequest":
            response_data = handle_launch()

        # ── IntentRequest ────────────────────────────────
        elif request_type == "IntentRequest":
            intent = body.get("request", {}).get("intent", {})
            intent_name = intent.get("name")

            handlers = {
                "TurnOnIntent":          lambda: handle_turn_on(intent),
                "TurnOffIntent":         lambda: handle_turn_off(intent),
                "AMAZON.HelpIntent":     handle_help,
                "AMAZON.CancelIntent":   handle_stop_cancel,
                "AMAZON.StopIntent":     handle_stop_cancel,
                "AMAZON.FallbackIntent": handle_fallback,
            }

            handler = handlers.get(intent_name)
            if handler:
                response_data = handler()
            else:
                response_data = build_response(
                    "I'm not sure how to handle that. Try saying: turn on the lights."
                )

        # ── SessionEndedRequest ──────────────────────────
        elif request_type == "SessionEndedRequest":
            response_data = {"version": "1.0", "response": {}}

        # ── Unknown request ──────────────────────────────
        else:
            response_data = build_response(
                "Something went wrong. Please try again."
            )

        # ── Print response (debug) ───────────────────────
        print("RESPONSE:\n", json.dumps(response_data, indent=2))

        # ✅ IMPORTANT FIX
        return JsonResponse(response_data, safe=False)

    except Exception as e:
        # ── Catch ANY crash so Alexa doesn't break ───────
        print("ERROR:", str(e))

        return JsonResponse({
            "version": "1.0",
            "response": {
                "outputSpeech": {
                    "type": "PlainText",
                    "text": "Internal server error."
                },
                "shouldEndSession": True
            }
        }, safe=False)