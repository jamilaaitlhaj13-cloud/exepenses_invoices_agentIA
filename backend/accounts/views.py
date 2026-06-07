from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework_simplejwt.tokens import RefreshToken
from django.contrib.auth import authenticate

from .serializers import RegisterSerializer, CompanyProfileSerializer
from .models import Company


def _tokens_for_user(user):
    refresh = RefreshToken.for_user(user)
    return {
        'access':  str(refresh.access_token),
        'refresh': str(refresh),
    }


class RegisterView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        serializer = RegisterSerializer(data=request.data)
        if serializer.is_valid():
            company = serializer.save()
            tokens  = _tokens_for_user(company)
            return Response({
                'message':      'Compte créé avec succès.',
                'company_name': company.company_name,
                'company_id':   company.id,
                **tokens,
            }, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class LoginView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        email    = request.data.get('email', '').strip().lower()
        password = request.data.get('password', '')

        user = authenticate(request, username=email, password=password)
        if not user:
            return Response(
                {'error': 'Email ou mot de passe incorrect.'},
                status=status.HTTP_401_UNAUTHORIZED,
            )

        tokens = _tokens_for_user(user)
        return Response({
            'company_name': user.company_name,
            'company_id':   user.id,
            'industry':     user.get_industry_display(),
            **tokens,
        })


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
