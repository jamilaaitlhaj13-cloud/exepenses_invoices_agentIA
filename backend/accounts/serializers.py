from rest_framework import serializers
from django.contrib.auth.password_validation import validate_password
from .models import Company


class RegisterSerializer(serializers.ModelSerializer):
    password  = serializers.CharField(write_only=True, validators=[validate_password])
    password2 = serializers.CharField(write_only=True, label='Confirmer le mot de passe')

    class Meta:
        model  = Company
        fields = [
            'email', 'password', 'password2',
            'company_name', 'industry', 'phone',
            'country', 'city', 'rc_number',
        ]

    def validate(self, attrs):
        if attrs['password'] != attrs.pop('password2'):
            raise serializers.ValidationError({'password': 'Les mots de passe ne correspondent pas.'})
        return attrs

    def create(self, validated_data):
        return Company.objects.create_user(**validated_data)


class CompanyProfileSerializer(serializers.ModelSerializer):
    class Meta:
        model  = Company
        fields = [
            'id', 'email', 'company_name', 'industry',
            'phone', 'country', 'city', 'rc_number',
            'logo', 'created_at',
        ]
        read_only_fields = ['id', 'email', 'created_at']
