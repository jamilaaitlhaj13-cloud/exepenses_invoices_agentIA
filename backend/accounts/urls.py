from django.urls import path
from rest_framework_simplejwt.views import TokenRefreshView
from .views import RegisterView, LoginView, ProfileView, SendVerificationView, VerifyEmailView

urlpatterns = [
    path('register/',          RegisterView.as_view(),          name='register'),
    path('login/',             LoginView.as_view(),             name='login'),
    path('refresh/',           TokenRefreshView.as_view(),      name='token_refresh'),
    path('profile/',           ProfileView.as_view(),           name='profile'),
    path('send-verification/', SendVerificationView.as_view(),  name='send_verification'),
    path('verify-email/',      VerifyEmailView.as_view(),       name='verify_email'),
]
