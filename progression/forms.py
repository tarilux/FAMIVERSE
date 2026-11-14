from django import forms

from .models import BadgeDefinition


class BalanceAdjustmentForm(forms.Form):
    class Currency:
        COINS = "coins"
        XP = "xp"

    currency = forms.ChoiceField(
        choices=((Currency.COINS, "Pièces"), (Currency.XP, "XP")),
    )
    direction = forms.ChoiceField(
        choices=(("add", "Ajouter"), ("remove", "Retirer")),
    )
    amount = forms.IntegerField(min_value=1, max_value=9223372036854775807)
    reason = forms.CharField(max_length=240)
    confirm = forms.BooleanField(required=True)

    def __init__(self, *args, language="fr", **kwargs):
        super().__init__(*args, **kwargs)
        if language == "ar":
            self.fields["currency"].choices = (
                (self.Currency.COINS, "القطع"),
                (self.Currency.XP, "نقاط الخبرة"),
            )
            self.fields["direction"].choices = (
                ("add", "إضافة"),
                ("remove", "خصم"),
            )
            for name, label in {
                "currency": "نوع الرصيد",
                "direction": "العملية",
                "amount": "المبلغ",
                "reason": "السبب",
                "confirm": "أؤكد هذا التعديل",
            }.items():
                self.fields[name].label = label
            self.fields["currency"].error_messages["invalid_choice"] = (
                "اختر نوع رصيد صالحًا."
            )
            self.fields["direction"].error_messages["invalid_choice"] = (
                "اختر عملية صالحة."
            )
            self.fields["amount"].error_messages.update(
                {
                    "required": "أدخل المبلغ.",
                    "invalid": "يجب أن يكون المبلغ عددًا صحيحًا.",
                    "min_value": "يجب أن يكون المبلغ أكبر من صفر.",
                    "max_value": "المبلغ أكبر من الحد المسموح.",
                }
            )
            self.fields["reason"].error_messages.update(
                {
                    "required": "أدخل سبب التعديل.",
                    "max_length": "يجب ألا يتجاوز السبب ٢٤٠ حرفًا.",
                }
            )
            self.fields["confirm"].error_messages["required"] = (
                "يجب تأكيد هذا التعديل."
            )
        else:
            for name, label in {
                "currency": "Type de solde",
                "direction": "Opération",
                "amount": "Montant",
                "reason": "Motif",
                "confirm": "Je confirme cet ajustement",
            }.items():
                self.fields[name].label = label
            self.fields["currency"].error_messages["invalid_choice"] = (
                "Choisissez un type de solde valide."
            )
            self.fields["direction"].error_messages["invalid_choice"] = (
                "Choisissez une opération valide."
            )
            self.fields["amount"].error_messages.update(
                {
                    "required": "Indiquez un montant.",
                    "invalid": "Le montant doit être un entier.",
                    "min_value": "Le montant doit être supérieur à zéro.",
                    "max_value": "Le montant dépasse la limite autorisée.",
                }
            )
            self.fields["reason"].error_messages.update(
                {
                    "required": "Indiquez le motif de l'ajustement.",
                    "max_length": "Le motif ne peut pas dépasser 240 caractères.",
                }
            )
            self.fields["confirm"].error_messages["required"] = (
                "La confirmation de l'ajustement est obligatoire."
            )


class ManualBadgeForm(forms.Form):
    badge = forms.ModelChoiceField(
        queryset=BadgeDefinition.objects.filter(manual_only=True),
        label="Badge à attribuer",
    )
    confirm = forms.BooleanField(
        required=True,
        label="Confirmer l'attribution de ce badge",
    )

    def __init__(self, *args, language="fr", **kwargs):
        super().__init__(*args, **kwargs)
        if language == "ar":
            self.fields["badge"].label = "شارة لمنحها"
            self.fields["confirm"].label = "تأكيد منح هذه الشارة"
            self.fields["badge"].label_from_instance = (
                lambda badge: badge.name_ar or badge.name
            )
        else:
            self.fields["badge"].label_from_instance = lambda badge: badge.name
