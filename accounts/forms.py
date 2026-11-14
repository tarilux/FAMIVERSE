import re

from django import forms
from django.db import transaction
from django.utils import timezone

from .models import Account, ChildProfile


class LoginForm(forms.Form):
    username = forms.CharField(max_length=150)
    pin = forms.CharField(max_length=6, strip=False, widget=forms.PasswordInput)


class ChildCreateForm(forms.Form):
    username = forms.CharField(max_length=150)
    first_name = forms.CharField(max_length=80)
    date_of_birth = forms.DateField(
        widget=forms.DateInput(attrs={"type": "date"}),
    )
    pin = forms.CharField(max_length=6, strip=False, widget=forms.PasswordInput)
    language = forms.ChoiceField(choices=ChildProfile.Language.choices)
    maturity = forms.ChoiceField(choices=ChildProfile.Maturity.choices)
    avatar = forms.ImageField(required=False)

    def clean_username(self):
        username = self.cleaned_data["username"].strip()
        if Account.objects.filter(username__iexact=username).exists():
            raise forms.ValidationError("Cet identifiant est déjà utilisé.")
        return username

    def clean_pin(self):
        pin = self.cleaned_data["pin"]
        if not re.fullmatch(r"\d{4,6}", pin):
            raise forms.ValidationError("Le code doit contenir 4 à 6 chiffres.")
        return pin

    def clean_date_of_birth(self):
        date_of_birth = self.cleaned_data["date_of_birth"]
        if date_of_birth >= timezone.localdate():
            raise forms.ValidationError("La date de naissance doit être passée.")
        return date_of_birth

    def clean_avatar(self):
        avatar = self.cleaned_data.get("avatar")
        if avatar and avatar.size > 5 * 1024 * 1024:
            raise forms.ValidationError("La photo ne peut pas dépasser 5 Mo.")
        return avatar

    @transaction.atomic
    def save(self, family):
        account = Account(
            username=self.cleaned_data["username"],
            role=Account.Role.CHILD,
            family=family,
            first_name=self.cleaned_data["first_name"],
        )
        account.set_password(self.cleaned_data["pin"])
        account.save()
        return ChildProfile.objects.create(
            user=account,
            first_name=self.cleaned_data["first_name"],
            date_of_birth=self.cleaned_data["date_of_birth"],
            language=self.cleaned_data["language"],
            maturity=self.cleaned_data["maturity"],
            avatar=self.cleaned_data.get("avatar"),
        )
