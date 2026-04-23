import json
import uuid
from urllib.parse import urlencode

from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.shortcuts import render, redirect
from django.contrib.auth import authenticate, login

from .models import AuthCode, AccessToken


# ─────────────────────────────────────────────
# 🔐 AUTHORIZE ENDPOINT
# ─────────────────────────────────────────────

def authorize_view(request):
    """
    Alexa يفتح هذا الرابط في WebView.
    المطلوب:
      - response_type = "code"
      - client_id     (يطابق ما في Alexa Console)
      - redirect_uri
      - state
    """
    redirect_uri  = request.GET.get("redirect_uri", "").strip()
    state         = request.GET.get("state", "").strip()
    response_type = request.GET.get("response_type", "")
    # client_id يمكن التحقق منه هنا إن أردت
    # client_id = request.GET.get("client_id", "")

    # ── حماية: تأكد من الحقول الأساسية ──
    if not redirect_uri or not state:
        return JsonResponse(
            {"error": "invalid_request", "message": "missing redirect_uri or state"},
            status=400,
        )

    if response_type != "code":
        return JsonResponse(
            {"error": "unsupported_response_type"},
            status=400,
        )

    # ── إذا المستخدم غير مسجّل دخوله → أرسله لصفحة Login ──
    if not request.user.is_authenticated:
        params = urlencode({"redirect_uri": redirect_uri, "state": state})
        return redirect(f"/login/?{params}")

    # ── المستخدم مسجّل → أنشئ auth code وأعده لـ Alexa ──
    code = str(uuid.uuid4())
    AuthCode.objects.create(user=request.user, code=code)

    separator = "&" if "?" in redirect_uri else "?"
    return redirect(f"{redirect_uri}{separator}state={state}&code={code}")


# ─────────────────────────────────────────────
# 🔐 LOGIN PAGE
# ─────────────────────────────────────────────

def login_view(request):
    # redirect_uri و state يأتيان من GET params (الرابط نفسه)
    # أو من hidden fields في الـ POST  — نأخذ من كليهما احتياطاً
    redirect_uri = (
        request.POST.get("redirect_uri")
        or request.GET.get("redirect_uri", "")
    ).strip()

    state = (
        request.POST.get("state")
        or request.GET.get("state", "")
    ).strip()

    if request.method == "POST":
        username = request.POST.get("username", "").strip()
        password = request.POST.get("password", "")

        user = authenticate(request, username=username, password=password)

        if user:
            login(request, user)

            # بعد تسجيل الدخول → أكمل دورة OAuth
            if redirect_uri and state:
                params = urlencode({
                    "redirect_uri": redirect_uri,
                    "state": state,
                    "response_type": "code",
                })
                return redirect(f"/authorize/?{params}")

            # fallback: لو لم تكن هناك بيانات OAuth
            return JsonResponse({"error": "missing_redirect_data"}, status=400)

        # كلمة مرور خاطئة
        return render(request, "login.html", {
            "error": "Invalid username or password. Please try again.",
            "redirect_uri": redirect_uri,
            "state": state,
        })

    # GET → اعرض صفحة اللوجين
    return render(request, "login.html", {
        "redirect_uri": redirect_uri,
        "state": state,
    })


# ─────────────────────────────────────────────
# 🔐 TOKEN ENDPOINT
# ─────────────────────────────────────────────

@csrf_exempt
def token_view(request):
    """
    Alexa يطلب access_token بعد الحصول على auth code.
    يرسل: grant_type, code, redirect_uri, client_id, client_secret
    """
    try:
        # Alexa يرسل كـ application/x-www-form-urlencoded
        if request.content_type and "application/json" in request.content_type:
            data = json.loads(request.body)
        else:
            data = request.POST

        grant_type = data.get("grant_type", "")
        code       = data.get("code", "")

        # ── دعم authorization_code فقط (يمكن إضافة refresh_token لاحقاً) ──
        if grant_type != "authorization_code":
            return JsonResponse(
                {"error": "unsupported_grant_type"},
                status=400,
            )

        if not code:
            return JsonResponse({"error": "missing_code"}, status=400)

        auth_code = AuthCode.objects.get(code=code)

        token = str(uuid.uuid4())
        AccessToken.objects.create(user=auth_code.user, token=token)

        # احذف الـ auth code بعد الاستخدام (استخدام مرة واحدة فقط)
        auth_code.delete()

        return JsonResponse({
            "access_token": token,
            "token_type":   "Bearer",
            "expires_in":   3600,
        })

    except AuthCode.DoesNotExist:
        return JsonResponse({"error": "invalid_code"}, status=400)

    except Exception as e:
        print("TOKEN ERROR:", str(e))
        return JsonResponse({"error": "server_error"}, status=500)


# ─────────────────────────────────────────────
# 🔑 USER FROM TOKEN
# ─────────────────────────────────────────────

def get_user_from_token(token):
    try:
        return AccessToken.objects.get(token=token).user
    except Exception:
        return None


# ─────────────────────────────────────────────
# 🧠 ALEXA HELPERS
# ─────────────────────────────────────────────

def build_response(text, should_end_session=True, reprompt=None):
    response = {
        "version": "1.0",
        "response": {
            "outputSpeech": {"type": "PlainText", "text": text},
            "shouldEndSession": should_end_session,
        },
    }
    if reprompt:
        response["response"]["reprompt"] = {
            "outputSpeech": {"type": "PlainText", "text": reprompt}
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
        "Welcome to Baz Rays. You can say: turn on the lights, or turn off the fan.",
        should_end_session=False,
        reprompt="What would you like to control?",
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
        should_end_session=False,
    )


def handle_stop():
    return build_response("Goodbye from Baz Rays!")


def handle_fallback():
    return build_response(
        "Sorry, I didn't understand that. Try saying turn on or turn off.",
        should_end_session=False,
    )


# ─────────────────────────────────────────────
# 🚀 MAIN ALEXA WEBHOOK
# ─────────────────────────────────────────────

@csrf_exempt
def alexa_webhook(request):
    if request.method == "GET":
        return JsonResponse({"message": "Alexa endpoint is working ✅"})

    try:
        body = json.loads(request.body)
        print("REQUEST:\n", json.dumps(body, indent=2))

        access_token = (
            body.get("context", {})
                .get("System", {})
                .get("user", {})
                .get("accessToken")
        )

        user = get_user_from_token(access_token)

        if not user:
            # المستخدم لم يربط حسابه بعد
            return JsonResponse({
                "version": "1.0",
                "response": {
                    "outputSpeech": {
                        "type": "PlainText",
                        "text": "Please link your account first. Open the Alexa app and complete account linking.",
                    },
                    "card": {"type": "LinkAccount"},
                    "shouldEndSession": True,
                },
            })

        request_type = body.get("request", {}).get("type")

        if request_type == "LaunchRequest":
            response_data = handle_launch()

        elif request_type == "IntentRequest":
            intent = body["request"]["intent"]
            name   = intent.get("name")

            handlers = {
                "TurnOnIntent":          lambda: handle_turn_on(intent),
                "TurnOffIntent":         lambda: handle_turn_off(intent),
                "AMAZON.HelpIntent":     handle_help,
                "AMAZON.StopIntent":     handle_stop,
                "AMAZON.CancelIntent":   handle_stop,
                "AMAZON.FallbackIntent": handle_fallback,
            }

            response_data = handlers.get(name, handle_fallback)()

        elif request_type == "SessionEndedRequest":
            response_data = {"version": "1.0", "response": {}}

        else:
            response_data = build_response("Goodbye.")

        print("RESPONSE:\n", json.dumps(response_data, indent=2))
        return JsonResponse(response_data)

    except Exception as e:
        print("ERROR:", str(e))
        return JsonResponse({
            "version": "1.0",
            "response": {
                "outputSpeech": {"type": "PlainText", "text": "An internal error occurred."},
                "shouldEndSession": True,
            },
        })


# أضف هذه الـ views الجديدة في نهاية views.py الموجود

# ─────────────────────────────────────────────
# 📱  APP AUTHORIZE  →  POST /api/app-authorize/
# ─────────────────────────────────────────────
# Flutter يستدعيه مباشرة بعد تسجيل الدخول
# يرجع callback_url جاهز لـ Alexa

@csrf_exempt
def app_authorize_view(request):
    if request.method != "POST":
        return JsonResponse({"error": "method_not_allowed"}, status=405)

    try:
        data         = json.loads(request.body)
        username     = data.get("username", "")
        password     = data.get("password", "")
        redirect_uri = data.get("redirect_uri", "")
        state        = data.get("state", "")
        client_id    = data.get("client_id", "")

   
        # تحقق من الـ params
        if not redirect_uri or not state:
            return JsonResponse({"error": "missing_oauth_params"}, status=400)

        # authenticate المستخدم
        from django.contrib.auth import authenticate as dj_authenticate
        user = dj_authenticate(username=username, password=password)

        if user is None:
            return JsonResponse({"error": "invalid_credentials"}, status=401)

        # أنشئ Auth Code
        code = str(uuid.uuid4())
        AuthCode.objects.create(user=user, code=code)

        # ابنِ الـ callback URL الجاهز
        params       = urlencode({"state": state, "code": code})
        callback_url = f"{redirect_uri}?{params}"

        return JsonResponse({
            "success":      True,
            "callback_url": callback_url,
            "username":     user.username,
        })

    except Exception:
        
        return JsonResponse({"error": "server_error"}, status=500)


# ─────────────────────────────────────────────
# 📱  APP LOGIN  →  POST /api/login/
# ─────────────────────────────────────────────
# تسجيل دخول عادي من التطبيق (بدون Alexa)

@csrf_exempt
def app_login_view(request):
    if request.method != "POST":
        return JsonResponse({"error": "method_not_allowed"}, status=405)

    try:
        data     = json.loads(request.body)
        username = data.get("username", "")
        password = data.get("password", "")

        from django.contrib.auth import authenticate as dj_authenticate
        user = dj_authenticate(username=username, password=password)

        if user is None:
            return JsonResponse({"error": "invalid_credentials"}, status=401)

        # أنشئ Access Token للتطبيق
        token = str(uuid.uuid4())
        AccessToken.objects.create(user=user, token=token)

        return JsonResponse({
            "access_token": token,
            "username":     user.username,
            "first_name":   user.first_name,
        })

    except Exception:
        
        return JsonResponse({"error": "server_error"}, status=500)


# ─────────────────────────────────────────────
# 🔗  ANDROID APP LINKS VERIFICATION
#     GET /.well-known/assetlinks.json
# ─────────────────────────────────────────────
# Android يتحقق من هذا الملف لإثبات ملكية الـ App Link
# يجب استبدال SHA256_FINGERPRINT بـ fingerprint تطبيقك

def assetlinks_view(request):
    # 👇 استبدل هذه القيمة بـ SHA-256 fingerprint من keystore تطبيقك
    # الحصول عليها: keytool -list -v -keystore your-key.jks
    SHA256_FINGERPRINT = "44:F1:F5:7D:ED:6F:3D:76:8F:2E:6C:FE:0E:5D:D0:23:A8:BC:A0:05:B7:86:36:0D:54:FE:DD:6E:27:1C:35:F6"

    data = [{
        "relation": ["delegate_permission/common.handle_all_urls"],
        "target": {
            "namespace": "android_app",
            "package_name": "com.example.app",  # ← غيّر لـ package name تطبيقك
            "sha256_cert_fingerprints": [SHA256_FINGERPRINT]
        }
    }]

    from django.http import JsonResponse
    return JsonResponse(data, safe=False)


# ─────────────────────────────────────────────
# 🌐  ALEXA-LOGIN PAGE  →  GET /alexa-login/
# ─────────────────────────────────────────────
# هذا الرابط يفتحه Alexa → Android يعترضه ويفتح التطبيق
# لو لم يكن التطبيق مثبتاً، يظهر صفحة ويب احتياطية

def alexa_login_redirect_view(request):
    redirect_uri = request.GET.get("redirect_uri", "")
    state        = request.GET.get("state", "")
    client_id    = request.GET.get("client_id", "")

    # Fallback: لو لم يُفتح التطبيق، وجّه للـ web login
    qs = urlencode({"redirect_uri": redirect_uri, "state": state})
    return redirect(f"/login/?{qs}")
