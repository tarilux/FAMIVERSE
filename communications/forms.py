from django import forms
from django.utils import timezone

from accounts.models import ChildProfile


class FamilyMessageForm(forms.Form):
    recipient = forms.ChoiceField()
    content = forms.CharField(
        max_length=2000,
        required=False,
        widget=forms.Textarea(attrs={"rows": 4}),
    )
    content_ar = forms.CharField(
        max_length=2000,
        required=False,
        widget=forms.Textarea(attrs={"rows": 4, "dir": "rtl"}),
    )
    expires_at = forms.DateTimeField(
        required=False,
        widget=forms.DateTimeInput(attrs={"type": "datetime-local"}),
    )

    def __init__(self, *args, family, language="fr", **kwargs):
        super().__init__(*args, **kwargs)
        self.language = language
        children = ChildProfile.objects.filter(
            user__family=family,
            user__is_active=True,
            archived_at__isnull=True,
        ).order_by("first_name", "pk")
        if language == "ar":
            choices = [("all", "جميع الأطفال")]
            choices.extend((str(child.pk), child.first_name) for child in children)
            self.fields["recipient"].label = "المستلم"
            self.fields["content_ar"].label = "الرسالة بالعربية (اختياري)"
            self.fields["expires_at"].label = "تاريخ الانتهاء (اختياري)"
            self.fields["recipient"].error_messages["invalid_choice"] = (
                "اختر مستلمًا صالحًا."
            )
            self.fields["content"].label = "الرسالة بالفرنسية (أو املأ الحقل العربي)"
            self.fields["content"].error_messages.update(
                {"max_length": "يجب ألا تتجاوز الرسالة ٢٠٠٠ حرف."}
            )
            self.fields["content_ar"].error_messages.update(
                {"max_length": "يجب ألا تتجاوز الرسالة ٢٠٠٠ حرف."}
            )
            self.fields["expires_at"].error_messages.update(
                {
                    "invalid": "أدخل تاريخًا ووقتًا صالحين.",
                    "invalid_date": "أدخل تاريخًا صالحًا.",
                    "invalid_time": "أدخل وقتًا صالحًا.",
                }
            )
        else:
            choices = [("all", "Tous les enfants")]
            choices.extend((str(child.pk), child.first_name) for child in children)
            self.fields["recipient"].label = "Destinataire"
            self.fields["content_ar"].label = "Message en arabe (facultatif)"
            self.fields["expires_at"].label = "Date d'expiration (facultative)"
            self.fields["recipient"].error_messages["invalid_choice"] = (
                "Choisissez un destinataire valide."
            )
            self.fields["content"].label = "Message en français (ou remplissez le champ arabe)"
            self.fields["content"].error_messages.update(
                {"max_length": "Le message ne peut pas dépasser 2 000 caractères."}
            )
            self.fields["content_ar"].error_messages.update(
                {"max_length": "Le message ne peut pas dépasser 2 000 caractères."}
            )
            self.fields["expires_at"].error_messages.update(
                {
                    "invalid": "Saisissez une date et une heure valides.",
                    "invalid_date": "Saisissez une date valide.",
                    "invalid_time": "Saisissez une heure valide.",
                }
            )
        self.fields["recipient"].choices = choices

    def clean_expires_at(self):
        expires_at = self.cleaned_data.get("expires_at")
        if expires_at and expires_at <= timezone.now():
            raise forms.ValidationError(
                (
                    "يجب أن يكون تاريخ الانتهاء في المستقبل."
                    if self.language == "ar"
                    else "La date d'expiration doit être dans le futur."
                )
            )
        return expires_at

    def clean(self):
        cleaned_data = super().clean()
        content = cleaned_data.get("content", "").strip()
        content_ar = cleaned_data.get("content_ar", "").strip()
        if not content and not content_ar:
            message = (
                "أدخل الرسالة بالفرنسية أو بالعربية."
                if self.language == "ar"
                else "Saisissez le message en français ou en arabe."
            )
            self.add_error("content", message)
        cleaned_data["content"] = content or content_ar
        cleaned_data["content_ar"] = content_ar or content
        return cleaned_data
