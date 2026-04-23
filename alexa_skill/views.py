import json
import uuid
import base64
import traceback
from urllib.parse import urlencode

from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.shortcuts import render, redirect
from django.contrib.auth import authenticate, login
from django.views.decorators.http import require_http_methods

from .models import AuthCode, AccessToken, Device

# ─────────────────────────────────────────────
# ⚙️  CONFIG
# ─────────────────────────────────────────────

CLIENT_ID     = "test"
CLIENT_SECRET = "test"


# ══════════════════════════════════════════════
#  🔐  OAuth – Authorize / Login / Token
# ══════════════════════════════════════════════

def authorize_view(request):
    redirect_uri  = request.GET.get("redirect_uri", "").strip()
    state         = request.GET.get("state", "").strip()
    response_type = request.GET.get("response_type", "")

    if not redirect_uri or not state:
        return JsonResponse({"error": "invalid_request"}, status=400)

    if response_type != "code":
        return JsonResponse({"error": "unsupported_response_type"}, status=400)

    if not request.user.is_authenticated:
        params = urlencode({"redirect_uri": redirect_uri, "state": state})
        return redirect(f"/login/?{params}")

    code = str(uuid.uuid4())
    AuthCode.objects.create(user=request.user, code=code)

    separator = "&" if "?" in redirect_uri else "?"
    return redirect(f"{redirect_uri}{separator}state={state}&code={code}")


def login_view(request):
    redirect_uri = (
        request.POST.get("redirect_uri") or request.GET.get("redirect_uri", "")
    ).strip()
    state = (
        request.POST.get("state") or request.GET.get("state", "")
    ).strip()

    if request.method == "POST":
        username = request.POST.get("username", "").strip()
        password = request.POST.get("password", "")
        user = authenticate(request, username=username, password=password)

        if user:
            login(request, user)
            if redirect_uri and state:
                params = urlencode({
                    "redirect_uri": redirect_uri,
                    "state": state,
                    "response_type": "code",
                })
                return redirect(f"/authorize/?{params}")
            return JsonResponse({"error": "missing_redirect_data"}, status=400)

        return render(request, "login.html", {
            "error": "اسم المستخدم أو كلمة المرور غير صحيحة.",
            "redirect_uri": redirect_uri,
            "state": state,
        })

    return render(request, "login.html", {
        "redirect_uri": redirect_uri,
        "state": state,
    })


@csrf_exempt
def token_view(request):
    try:
        ct = request.content_type or ""
        data = json.loads(request.body) if "application/json" in ct else request.POST

        grant_type    = data.get("grant_type", "")
        code_value    = data.get("code", "")
        client_id_in  = data.get("client_id", "")
        client_sec_in = data.get("client_secret", "")

        auth_header = request.META.get("HTTP_AUTHORIZATION", "")
        if auth_header.startswith("Basic "):
            decoded = base64.b64decode(auth_header[6:]).decode("utf-8")
            client_id_in, _, client_sec_in = decoded.partition(":")

        if client_id_in != CLIENT_ID or client_sec_in != CLIENT_SECRET:
            return JsonResponse({"error": "invalid_client"}, status=401)

        if grant_type != "authorization_code":
            return JsonResponse({"error": "unsupported_grant_type"}, status=400)

        if not code_value:
            return JsonResponse({"error": "missing_code"}, status=400)

        try:
            auth_code = AuthCode.objects.get(code=code_value, used=False)
        except AuthCode.DoesNotExist:
            return JsonResponse({"error": "invalid_grant"}, status=400)

        token = str(uuid.uuid4())
        AccessToken.objects.create(user=auth_code.user, token=token)
        auth_code.used = True
        auth_code.save()

        return JsonResponse({
            "access_token": token,
            "token_type":   "Bearer",
            "expires_in":   3600,
        })

    except Exception:
        print(traceback.format_exc())
        return JsonResponse({"error": "server_error"}, status=500)


# ══════════════════════════════════════════════
#  🔑  Helpers
# ══════════════════════════════════════════════

def get_user_from_token(token_str):
    if not token_str:
        return None
    try:
        return AccessToken.objects.get(token=token_str).user
    except AccessToken.DoesNotExist:
        return None


def build_response(text, should_end_session=True, reprompt=None):
    r = {
        "version": "1.0",
        "response": {
            "outputSpeech": {"type": "PlainText", "text": text},
            "shouldEndSession": should_end_session,
        },
    }
    if reprompt:
        r["response"]["reprompt"] = {
            "outputSpeech": {"type": "PlainText", "text": reprompt}
        }
    return r


def get_slot_value(intent, name):
    return intent.get("slots", {}).get(name, {}).get("value")


# ══════════════════════════════════════════════
#  🔌  Device Logic – DB Based
# ══════════════════════════════════════════════

def find_device(user, spoken_name):
    """
    يبحث عن جهاز المستخدم بالاسم.
    يدعم تطابق كامل أو جزئي (case-insensitive).
    مثال: قال "الاضاءة" → يجد "الإضاءة"
    """
    if not spoken_name:
        return None

    spoken = spoken_name.strip().lower()

    # 1. تطابق كامل
    try:
        return user.devices.get(name__iexact=spoken)
    except Device.DoesNotExist:
        pass

    # 2. تطابق جزئي
    matches = user.devices.filter(name__icontains=spoken)
    if matches.count() == 1:
        return matches.first()

    return None


def control_device(user, spoken_name, action):
    """
    يغيّر حالة الجهاز في DB ويرجع نص للـ Alexa.
    يفصل تماماً بين المستخدمين (user-scoped).
    """
    if not spoken_name:
        devices = user.devices.all()
        if devices.exists():
            names = "، ".join(d.name for d in devices)
            return f"لم أفهم اسم الجهاز. أجهزتك المسجّلة: {names}."
        return "لم أفهم اسم الجهاز، ولا يوجد لديك أجهزة مسجّلة بعد."

    device = find_device(user, spoken_name)

    if not device:
        devices = user.devices.all()
        if devices.exists():
            names = "، ".join(d.name for d in devices)
            return f"لم أجد جهازاً باسم {spoken_name}. أجهزتك المسجّلة: {names}."
        return f"لم أجد جهازاً باسم {spoken_name}. لم تسجّل أي جهاز بعد."

    device.is_on = (action == "on")
    device.save()

    verb = "تم تشغيل" if action == "on" else "تم إيقاف"
    return f"{verb} {device.name}."


# ══════════════════════════════════════════════
#  🎯  Alexa Intent Handlers
# ══════════════════════════════════════════════

def handle_launch(user):
    name    = user.first_name or user.username
    count   = user.devices.count()
    devices = user.devices.all()

    if count == 0:
        return build_response(
            f"أهلاً {name}، مرحباً بك في Baz Rays. لم تسجّل أي جهاز بعد، "
            "أضف أجهزتك من التطبيق.",
            should_end_session=False,
        )

    on_devices  = [d.name for d in devices if d.is_on]
    off_devices = [d.name for d in devices if not d.is_on]

    status_parts = []
    if on_devices:
        status_parts.append(f"يعمل حالياً: {'، '.join(on_devices)}")
    if off_devices:
        status_parts.append(f"مطفأ: {'، '.join(off_devices)}")

    status = ". ".join(status_parts)
    return build_response(
        f"أهلاً {name}. لديك {count} جهاز. {status}. ماذا تريد؟",
        should_end_session=False,
        reprompt="قل مثلاً: شغّل الإضاءة.",
    )


def handle_turn_on(intent, user):
    device = get_slot_value(intent, "device")
    return build_response(control_device(user, device, "on"))


def handle_turn_off(intent, user):
    device = get_slot_value(intent, "device")
    return build_response(control_device(user, device, "off"))


def handle_list_devices(user):
    devices = user.devices.all()
    if not devices.exists():
        return build_response("لم تسجّل أي جهاز بعد. أضف أجهزتك من التطبيق.")

    on_list  = [d.name for d in devices if d.is_on]
    off_list = [d.name for d in devices if not d.is_on]

    parts = []
    if on_list:
        parts.append(f"شغّال: {'، '.join(on_list)}")
    if off_list:
        parts.append(f"مطفأ: {'، '.join(off_list)}")

    return build_response("أجهزتك: " + ". ".join(parts) + ".", should_end_session=False)


def handle_help():
    return build_response(
        "يمكنك قول: شغّل الإضاءة، أو أوقف المكيف، أو اذكر أجهزتي.",
        should_end_session=False,
    )


def handle_stop():
    return build_response("إلى اللقاء من Baz Rays!")


def handle_fallback():
    return build_response(
        "لم أفهم، قل مساعدة لمعرفة الأوامر.",
        should_end_session=False,
    )


# ══════════════════════════════════════════════
#  🚀  Alexa Webhook
# ══════════════════════════════════════════════

@csrf_exempt
def alexa_webhook(request):
    if request.method == "GET":
        return JsonResponse({"status": "ok", "message": "Alexa endpoint is working ✅"})

    try:
        body = json.loads(request.body)
        print("ALEXA REQUEST:\n", json.dumps(body, indent=2))

        access_token = (
            body.get("context", {})
                .get("System", {})
                .get("user", {})
                .get("accessToken")
        )

        user = get_user_from_token(access_token)

        if not user:
            return JsonResponse({
                "version": "1.0",
                "response": {
                    "outputSpeech": {
                        "type": "PlainText",
                        "text": "يرجى ربط حسابك أولاً من تطبيق Alexa.",
                    },
                    "card": {"type": "LinkAccount"},
                    "shouldEndSession": True,
                },
            })

        request_type = body.get("request", {}).get("type")

        if request_type == "LaunchRequest":
            response_data = handle_launch(user)

        elif request_type == "IntentRequest":
            intent = body["request"]["intent"]
            name   = intent.get("name")

            handlers = {
                "TurnOnIntent":          lambda: handle_turn_on(intent, user),
                "TurnOffIntent":         lambda: handle_turn_off(intent, user),
                "ListDevicesIntent":     lambda: handle_list_devices(user),
                "AMAZON.HelpIntent":     handle_help,
                "AMAZON.StopIntent":     handle_stop,
                "AMAZON.CancelIntent":   handle_stop,
                "AMAZON.FallbackIntent": handle_fallback,
            }

            response_data = handlers.get(name, handle_fallback)()

        elif request_type == "SessionEndedRequest":
            response_data = {"version": "1.0", "response": {}}

        else:
            response_data = build_response("وداعاً!")

        print("ALEXA RESPONSE:\n", json.dumps(response_data, indent=2))
        return JsonResponse(response_data)

    except Exception:
        print("ALEXA ERROR:\n", traceback.format_exc())
        return JsonResponse(build_response("حدث خطأ داخلي."))


# ══════════════════════════════════════════════
#  📱  Flutter App APIs
# ══════════════════════════════════════════════

@csrf_exempt
def app_login_view(request):
    if request.method != "POST":
        return JsonResponse({"error": "method_not_allowed"}, status=405)
    try:
        data     = json.loads(request.body)
        username = data.get("username", "")
        password = data.get("password", "")

        user = authenticate(username=username, password=password)
        if user is None:
            return JsonResponse({"error": "invalid_credentials"}, status=401)

        token = str(uuid.uuid4())
        AccessToken.objects.create(user=user, token=token)

        return JsonResponse({
            "access_token": token,
            "username":     user.username,
            "first_name":   user.first_name,
        })
    except Exception:
        return JsonResponse({"error": "server_error"}, status=500)


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

        if not redirect_uri or not state:
            return JsonResponse({"error": "missing_oauth_params"}, status=400)

        user = authenticate(username=username, password=password)
        if user is None:
            return JsonResponse({"error": "invalid_credentials"}, status=401)

        code = str(uuid.uuid4())
        AuthCode.objects.create(user=user, code=code)

        params       = urlencode({"state": state, "code": code})
        callback_url = f"{redirect_uri}?{params}"

        return JsonResponse({
            "success":      True,
            "callback_url": callback_url,
            "username":     user.username,
        })
    except Exception:
        return JsonResponse({"error": "server_error"}, status=500)


# ── Devices API ──

def _auth_from_header(request):
    """يستخرج المستخدم من Authorization: Bearer <token>"""
    auth = request.META.get("HTTP_AUTHORIZATION", "")
    if auth.startswith("Bearer "):
        return get_user_from_token(auth[7:])
    return None


@csrf_exempt
def devices_view(request):
    """
    GET  /api/devices/  → قائمة أجهزة المستخدم
    POST /api/devices/  → إضافة جهاز جديد
    """
    user = _auth_from_header(request)
    if not user:
        return JsonResponse({"error": "unauthorized"}, status=401)

    if request.method == "GET":
        devices = user.devices.all()
        return JsonResponse({
            "devices": [
                {"id": d.id, "name": d.name, "is_on": d.is_on}
                for d in devices
            ]
        })

    if request.method == "POST":
        data = json.loads(request.body)
        name = data.get("name", "").strip()

        if not name:
            return JsonResponse({"error": "name_required"}, status=400)

        if len(name) > 100:
            return JsonResponse({"error": "name_too_long"}, status=400)

        if user.devices.filter(name__iexact=name).exists():
            return JsonResponse({"error": "device_exists"}, status=409)

        device = Device.objects.create(user=user, name=name)
        return JsonResponse(
            {"id": device.id, "name": device.name, "is_on": device.is_on},
            status=201,
        )

    return JsonResponse({"error": "method_not_allowed"}, status=405)


@csrf_exempt
def device_detail_view(request, device_id):
    """
    PATCH  /api/devices/<id>/  → تبديل حالة الجهاز
    DELETE /api/devices/<id>/  → حذف الجهاز
    """
    user = _auth_from_header(request)
    if not user:
        return JsonResponse({"error": "unauthorized"}, status=401)

    try:
        device = user.devices.get(id=device_id)   # يضمن الفصل بين المستخدمين
    except Device.DoesNotExist:
        return JsonResponse({"error": "not_found"}, status=404)

    if request.method == "PATCH":
        data      = json.loads(request.body)
        device.is_on = data.get("is_on", device.is_on)
        device.save()
        return JsonResponse({"id": device.id, "name": device.name, "is_on": device.is_on})

    if request.method == "DELETE":
        device.delete()
        return JsonResponse({"deleted": True})

    return JsonResponse({"error": "method_not_allowed"}, status=405)


# ── App Links / Misc ──

def assetlinks_view(request):
    SHA256_FINGERPRINT = "44:F1:F5:7D:ED:6F:3D:76:8F:2E:6C:FE:0E:5D:D0:23:A8:BC:A0:05:B7:86:36:0D:54:FE:DD:6E:27:1C:35:F6"
    data = [{
        "relation": ["delegate_permission/common.handle_all_urls"],
        "target": {
            "namespace": "android_app",
            "package_name": "com.example.app",
            "sha256_cert_fingerprints": [SHA256_FINGERPRINT],
        },
    }]
    return JsonResponse(data, safe=False)


def alexa_login_redirect_view(request):
    redirect_uri = request.GET.get("redirect_uri", "")
    state        = request.GET.get("state", "")
    qs = urlencode({"redirect_uri": redirect_uri, "state": state})
    return redirect(f"/login/?{qs}")