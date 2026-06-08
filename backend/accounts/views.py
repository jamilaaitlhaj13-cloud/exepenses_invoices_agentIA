import random
import string
from datetime import timedelta

from django.contrib.auth import authenticate
from django.core.mail import send_mail
from django.conf import settings
from django.utils import timezone

from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework_simplejwt.tokens import RefreshToken

from .serializers import RegisterSerializer, CompanyProfileSerializer
from .models import Company


def _tokens_for_user(user):
    refresh = RefreshToken.for_user(user)
    return {
        "access":  str(refresh.access_token),
        "refresh": str(refresh),
    }


def _generate_code(length=6):
    return "".join(random.choices(string.digits, k=length))


def _send_code(user):
    """Genere un code 6 chiffres, sauvegarde, envoie par email."""
    code = _generate_code()
    user.verification_code = code
    user.code_expires_at   = timezone.now() + timedelta(minutes=15)
    user.save(update_fields=["verification_code", "code_expires_at"])
    try:
        send_mail(
            subject="SmartExpenseAgent - Verification code",
            message=(
                f"Hello {user.company_name},\n\n"
                f"Your verification code is: {code}\n\n"
                f"This code is valid for 15 minutes.\n\n"
                f"If you did not create an account, please ignore this email.\n\n"
                f"-- SmartExpenseAgent"
            ),
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[user.email],
            fail_silently=False,
        )
    except Exception as e:
        import logging
        logging.getLogger(__name__).error(f"Email send failed for {user.email}: {e}")


class RegisterView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        serializer = RegisterSerializer(data=request.data)
        if serializer.is_valid():
            company = serializer.save()
            tokens  = _tokens_for_user(company)
            return Response({
                "message":      "Compte cree avec succes.",
                "company_name": company.company_name,
                "company_id":   company.id,
                **tokens,
            }, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class LoginView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        email    = request.data.get("email", "").strip().lower()
        password = request.data.get("password", "")

        user = authenticate(request, username=email, password=password)
        if not user:
            return Response(
                {"error": "Email ou mot de passe incorrect."},
                status=status.HTTP_401_UNAUTHORIZED,
            )

        tokens = _tokens_for_user(user)
        return Response({
            "company_name": user.company_name,
            "company_id":   user.id,
            "industry":     user.get_industry_display(),
            **tokens,
        })


class SendVerificationView(APIView):
    """POST /api/auth/send-verification/  { email }"""
    permission_classes = [AllowAny]

    def post(self, request):
        email = request.data.get("email", "").strip().lower()
        try:
            user = Company.objects.get(email=email)
        except Company.DoesNotExist:
            return Response({"message": "If this email exists, a code has been sent."})

        if user.is_email_verified:
            return Response({"message": "Email already verified."})

        _send_code(user)
        # En mode DEBUG : retourner le code dans la réponse pour faciliter les tests
        response_data = {"message": "Verification code sent."}
        if getattr(settings, "DEBUG", False):
            response_data["debug_code"] = user.verification_code
        return Response(response_data)


class VerifyEmailView(APIView):
    """POST /api/auth/verify-email/  { email, code }"""
    permission_classes = [AllowAny]

    def post(self, request):
        email = request.data.get("email", "").strip().lower()
        code  = request.data.get("code",  "").strip()

        try:
            user = Company.objects.get(email=email)
        except Company.DoesNotExist:
            return Response({"error": "Invalid email."}, status=status.HTTP_400_BAD_REQUEST)

        if user.is_email_verified:
            return Response({"message": "Already verified."})

        if not user.verification_code or not user.code_expires_at:
            return Response(
                {"error": "No code found. Please request a new one."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if timezone.now() > user.code_expires_at:
            return Response(
                {"error": "Code expired. Please request a new one."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if user.verification_code != code:
            return Response(
                {"error": "Invalid code. Please check and try again."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        user.is_email_verified = True
        user.verification_code = ""
        user.code_expires_at   = None
        user.save(update_fields=["is_email_verified", "verification_code", "code_expires_at"])
        return Response({"message": "Email verified successfully."})


class ProfileView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        serializer = CompanyProfileSerializer(request.user)
        return Response(serializer.data)

    def patch(self, request):
        serializer = CompanyProfileSerializer(
            request.user, data=request.data, partial=True
        )
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
