import uuid
from django.db import models
from django.contrib.auth.models import User


class AuthCode(models.Model):
    user       = models.ForeignKey(User, on_delete=models.CASCADE)
    code       = models.CharField(max_length=255, unique=True)
    used       = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"AuthCode({self.user.username})"


class AccessToken(models.Model):
    user       = models.ForeignKey(User, on_delete=models.CASCADE)
    token      = models.CharField(max_length=255, unique=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"AccessToken({self.user.username})"


class Device(models.Model):
    """
    جهاز مسجّل لمستخدم معيّن.
    كل مستخدم يرى ويتحكم في أجهزته فقط.
    """
    user       = models.ForeignKey(User, on_delete=models.CASCADE, related_name="devices")
    name       = models.CharField(max_length=100)          # اسم الجهاز (نص حر)
    is_on      = models.BooleanField(default=False)        # الحالة: شغّال / مطفي
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        # كل مستخدم لا يمكنه تسجيل جهازين بنفس الاسم
        unique_together = ("user", "name")
        ordering = ["name"]

    def __str__(self):
        status = "ON" if self.is_on else "OFF"
        return f"{self.user.username} → {self.name} [{status}]"