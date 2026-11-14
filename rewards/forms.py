from django import forms
from django.db import transaction

from .models import Reward


class RewardForm(forms.ModelForm):
    class Meta:
        model = Reward
        fields = (
            "category",
            "name",
            "name_ar",
            "description",
            "description_ar",
            "price_coins",
        )
        labels = {
            "category": "Catégorie",
            "name": "Nom de la récompense",
            "name_ar": "Nom en arabe (facultatif)",
            "description": "Description",
            "description_ar": "Description en arabe (facultatif)",
            "price_coins": "Prix en pièces",
        }
        widgets = {
            "description": forms.Textarea(attrs={"rows": 3}),
            "description_ar": forms.Textarea(attrs={"rows": 3}),
            "price_coins": forms.NumberInput(attrs={"min": 1}),
        }

    def __init__(self, *args, language="fr", **kwargs):
        super().__init__(*args, **kwargs)
        if language == "ar":
            self.fields["category"].choices = (
                ("screens", "الشاشات والترفيه"),
                ("food", "الحلويات والمأكولات"),
                ("privileges", "الامتيازات"),
                ("outings", "النزهات"),
                ("material", "المستلزمات"),
            )
            for name, label in {
                "category": "الفئة",
                "name": "اسم المكافأة",
                "name_ar": "الاسم بالعربية (اختياري)",
                "description": "الوصف",
                "description_ar": "الوصف بالعربية (اختياري)",
                "price_coins": "السعر بالقطع",
            }.items():
                self.fields[name].label = label

    @transaction.atomic
    def save(self, *, family, created_by):
        creating = self.instance._state.adding
        reward = super().save(commit=False)
        if creating:
            reward.family = family
            reward.created_by = created_by
        reward.full_clean()
        reward.save()
        return reward
