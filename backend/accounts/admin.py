from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from .models import Company


@admin.register(Company)
class CompanyAdmin(UserAdmin):
    model       = Company
    list_display = ['email', 'company_name', 'industry', 'country', 'created_at']
    ordering     = ['-created_at']
    fieldsets    = (
        (None,           {'fields': ('email', 'password')}),
        ('Entreprise',   {'fields': ('company_name', 'industry', 'phone', 'country', 'city', 'rc_number', 'logo')}),
        ('Permissions',  {'fields': ('is_active', 'is_staff', 'is_superuser')}),
    )
    add_fieldsets = (
        (None, {
            'classes': ('wide',),
            'fields':  ('email', 'company_name', 'password1', 'password2'),
        }),
    )
    search_fields = ['email', 'company_name']
