from django.contrib.auth.models import AbstractUser, BaseUserManager
from django.db import models


INDUSTRY_CHOICES = [
    ('tech',          'Technologie / IT'),
    ('finance',       'Finance & Banque'),
    ('healthcare',    'Sante'),
    ('retail',        'Commerce & Distribution'),
    ('manufacturing', 'Industrie & Production'),
    ('consulting',    'Conseil & Services'),
    ('education',     'Education'),
    ('real_estate',   'Immobilier'),
    ('transport',     'Transport & Logistique'),
    ('other',         'Autre'),
]


class CompanyManager(BaseUserManager):
    def create_user(self, email, password=None, **extra_fields):
        if not email:
            raise ValueError('Email requis')
        email = self.normalize_email(email)
        user  = self.model(email=email, **extra_fields)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_superuser(self, email, password=None, **extra_fields):
        extra_fields.setdefault('is_staff',     True)
        extra_fields.setdefault('is_superuser', True)
        return self.create_user(email, password, **extra_fields)


class Company(AbstractUser):
    """One account = one company."""
    username     = None
    email        = models.EmailField(unique=True)
    company_name = models.CharField(max_length=200)
    industry     = models.CharField(max_length=50, choices=INDUSTRY_CHOICES, default='other')
    phone        = models.CharField(max_length=20,  blank=True)
    country      = models.CharField(max_length=100, default='Maroc')
    city         = models.CharField(max_length=100, blank=True)
    rc_number    = models.CharField(max_length=50,  blank=True, verbose_name='N RC / SIRET')
    logo         = models.ImageField(upload_to='logos/', null=True, blank=True)
    created_at   = models.DateTimeField(auto_now_add=True)

    # Email verification
    is_email_verified = models.BooleanField(default=False)
    verification_code = models.CharField(max_length=6, blank=True)
    code_expires_at   = models.DateTimeField(null=True, blank=True)

    USERNAME_FIELD  = 'email'
    REQUIRED_FIELDS = ['company_name']

    objects = CompanyManager()

    class Meta:
        verbose_name        = 'Entreprise'
        verbose_name_plural = 'Entreprises'

    def __str__(self):
        return self.company_name
