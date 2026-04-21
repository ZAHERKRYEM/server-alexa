import json
import uuid

from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.shortcuts import render, redirect
from django.contrib.auth import authenticate, login

from .models import AuthCode, AccessToken


# ─────────────────────────────────────────────
# 🔐 TOKEN ENDPOINT
# ─────────────────────────────────────────────

@csrf_exempt
def token_view(request):
    try:
        data = json.loads(request.body)

        code = data.get("code")

        auth_code = AuthCode.objects.get(code=code)

        token = str(uuid.uuid4())

        AccessToken.objects.create(
            user=auth_code.user,
            token=token
        )

        return JsonResponse({
            "access_token": token,
            "token_type": "Bearer"
        })

    except AuthCode.DoesNotExist:
        return JsonResponse({"error": "invalid_code"}, status=400)

    except Exception as e:
        print("TOKEN ERROR:", str(e))
        return JsonResponse({"error": "server_error"}, status=500)


# ─────────────────────────────────────────────
# 🔐 AUTHORIZE ENDPOINT
# ─────────────────────────────────────────────

def authorize_view(request):
    redirect_uri = request.GET.get("redirect_uri")
    state = request.GET.get("state")

    if not request.user.is_authenticated:
        return redirect(f"/login/?redirect_uri={redirect_uri}&state={state}")

    code = str(uuid.uuid4())

    AuthCode.objects.create(
        user=request.user,
        code=code
    )

    # IMPORTANT: لازم نرجع state + code
    return redirect(f"{redirect_uri}?state={state}&code={code}")


# ─────────────────────────────────────────────
# 🔐 LOGIN PAGE
# ─────────────────────────────────────────────

def login_view(request):
    redirect_uri = request.GET.get("redirect_uri")
    state = request.GET.get("state")

    if request.method == "POST":
        username = request.POST.get("username")
        password = request.POST.get("password")

        user = authenticate(username=username, password=password)

        if user:
            login(request, user)

            return redirect(
                f"/authorize/?redirect_uri={redirect_uri}&state={state}"
            )

    return render(request, "login.html")


# ─────────────────────────────────────────────
# 🔑 USER FROM TOKEN
# ─────────────────────────────────────────────

def get_user_from_token(token):
    try:
        return AccessToken.objects.get(token=token).user
    except:
        return None


# ─────────────────────────────────────────────
# 🧠 ALEXA HELPERS
# ─────────────────────────────────────────────

def build_response(text, should_end_session=True, reprompt=None):
    response = {
        "version": "1.0",
        "response": {
            "outputSpeech": {
                "type": "PlainText",
                "text": text,
            },
            "shouldEndSession": should_end_session,
        },
    }

    if reprompt:
        response["response"]["reprompt"] = {
            "outputSpeech": {
                "type": "PlainText",
                "text": reprompt
            }
        }

    return response


def get_slot_value(intent, name):
    return intent.get("slots", {}).get(name, {}).get("value")


# ─────────────────────────────────────────────
# 🔌 DEVICE LOGIC
# ─────────────────────────────────────────────

device_states = {}

def control_device(device, action):
    if not device:
        return "I didn't catch which device you meant."

    device_states[device.lower()] = action
    verb = "turned on" if action == "on" else "turned off"

    return f"OK, I've {verb} the {device}."


# ─────────────────────────────────────────────
# 🎯 INTENT HANDLERS
# ─────────────────────────────────────────────

def handle_launch():
    return build_response(
        "Welcome to Baz Rays. Please link your account in the Alexa app.",
        should_end_session=True
    )


def handle_turn_on(intent):
    device = get_slot_value(intent, "device")
    return build_response(control_device(device, "on"))


def handle_turn_off(intent):
    device = get_slot_value(intent, "device")
    return build_response(control_device(device, "off"))


def handle_help():
    return build_response(
        "Say turn on the lights or turn off the fan.",
        should_end_session=False
    )


def handle_stop():
    return build_response("Goodbye from Baz Rays!")


def handle_fallback():
    return build_response(
        "Sorry, I didn't understand that.",
        should_end_session=False
    )


# ─────────────────────────────────────────────
# 🚀 MAIN ALEXA WEBHOOK
# ─────────────────────────────────────────────

@csrf_exempt
def alexa_webhook(request):

    if request.method == "GET":
        return JsonResponse({"message": "Alexa endpoint is working"})

    try:
        body = json.loads(request.body)
        print("REQUEST:\n", json.dumps(body, indent=2))

        # ── 🔑 ACCESS TOKEN ─────────────────
        access_token = (
            body.get("context", {})
            .get("System", {})
            .get("user", {})
            .get("accessToken")
        )

        user = get_user_from_token(access_token)

        # ❌ Not linked
        if not user:
            return JsonResponse({
                "version": "1.0",
                "response": {
                    "outputSpeech": {
                        "type": "PlainText",
                        "text": "Please link your account in the Alexa app."
                    },
                    "shouldEndSession": True
                }
            })

        request_type = body.get("request", {}).get("type")

        # ── LaunchRequest ──
        if request_type == "LaunchRequest":
            response_data = handle_launch()

        # ── IntentRequest ──
        elif request_type == "IntentRequest":
            intent = body["request"]["intent"]
            name = intent.get("name")

            handlers = {
                "TurnOnIntent": lambda: handle_turn_on(intent),
                "TurnOffIntent": lambda: handle_turn_off(intent),
                "AMAZON.HelpIntent": handle_help,
                "AMAZON.StopIntent": handle_stop,
                "AMAZON.CancelIntent": handle_stop,
                "AMAZON.FallbackIntent": handle_fallback,
            }

            response_data = handlers.get(name, handle_fallback)()

        else:
            response_data = build_response("Goodbye")

        print("RESPONSE:\n", json.dumps(response_data, indent=2))

        return JsonResponse(response_data)

    except Exception as e:
        print("ERROR:", str(e))

        return JsonResponse({
            "version": "1.0",
            "response": {
                "outputSpeech": {
                    "type": "PlainText",
                    "text": "Internal error occurred."
                },
                "shouldEndSession": True
            }
        })