from django import forms
from django.db import transaction

from accounts.models import ChildProfile

from .models import HabitTemplate


WEEKDAY_LABELS = {
    "fr": ("Lundi", "Mardi", "Mercredi", "Jeudi", "Vendredi", "Samedi", "Dimanche"),
    "ar": ("الاثنين", "الثلاثاء", "الأربعاء", "الخميس", "الجمعة", "السبت", "الأحد"),
}
WEEKDAYS = tuple((str(index), label) for index, label in enumerate(WEEKDAY_LABELS["fr"]))


class HabitTemplateForm(forms.ModelForm):
    children = forms.ModelMultipleChoiceField(
        queryset=ChildProfile.objects.none(),
        widget=forms.CheckboxSelectMultiple,
        label="Enfants",
    )
    weekdays = forms.MultipleChoiceField(
        choices=WEEKDAYS,
        required=False,
        widget=forms.CheckboxSelectMultiple,
        label="Jours de la semaine",
    )

    class Meta:
        model = HabitTemplate
        fields = (
            "title",
            "title_ar",
            "description",
            "description_ar",
            "frequency",
            "time_of_day",
            "scheduled_time",
            "coins_reward",
            "xp_reward",
        )
        labels = {
            "title": "Nom de l'habitude",
            "title_ar": "Nom en arabe (facultatif)",
            "description": "Description",
            "description_ar": "Description en arabe (facultatif)",
            "frequency": "Fréquence",
            "time_of_day": "Moment de la journée",
            "scheduled_time": "Heure précise (facultative)",
            "coins_reward": "Pièces",
            "xp_reward": "XP",
        }
        widgets = {
            "description": forms.Textarea(attrs={"rows": 3}),
            "description_ar": forms.Textarea(attrs={"rows": 3}),
            "scheduled_time": forms.TimeInput(attrs={"type": "time"}),
            "coins_reward": forms.NumberInput(attrs={"min": 0}),
            "xp_reward": forms.NumberInput(attrs={"min": 0}),
        }

    def __init__(self, *args, family, language="fr", **kwargs):
        super().__init__(*args, **kwargs)
        self.family = family
        self.language = language
        self.fields["children"].queryset = ChildProfile.objects.filter(
            user__family=family,
            user__is_active=True,
            archived_at__isnull=True,
        ).select_related("user")
        if self.instance.pk:
            self.initial["children"] = self.instance.children.values_list(
                "pk", flat=True
            )
            self.initial["weekdays"] = [str(day) for day in self.instance.weekdays]
        if language == "ar":
            self.fields["frequency"].choices = (
                (HabitTemplate.Frequency.DAILY, "يومي"),
                (HabitTemplate.Frequency.WEEKLY, "أسبوعي"),
            )
            self.fields["time_of_day"].choices = (
                (HabitTemplate.TimeOfDay.ANYTIME, "في أي وقت"),
                (HabitTemplate.TimeOfDay.MORNING, "صباحًا"),
                (HabitTemplate.TimeOfDay.AFTERNOON, "بعد الظهر"),
                (HabitTemplate.TimeOfDay.EVENING, "مساءً"),
            )
            self.fields["weekdays"].choices = tuple(
                (str(index), label)
                for index, label in enumerate(WEEKDAY_LABELS["ar"])
            )
            self.fields["children"].label = "الأطفال"
            self.fields["weekdays"].label = "أيام الأسبوع"
            self.fields["title"].label = "اسم العادة"
            self.fields["title_ar"].label = "الاسم بالعربية (اختياري)"
            self.fields["description"].label = "الوصف"
            self.fields["description_ar"].label = "الوصف بالعربية (اختياري)"
            self.fields["frequency"].label = "التكرار"
            self.fields["time_of_day"].label = "وقت اليوم"
            self.fields["scheduled_time"].label = "وقت محدد (اختياري)"
            self.fields["coins_reward"].label = "القطع"
            self.fields["xp_reward"].label = "نقاط الخبرة"

    def clean(self):
        cleaned_data = super().clean()
        frequency = cleaned_data.get("frequency")
        weekdays = cleaned_data.get("weekdays", [])
        if frequency == HabitTemplate.Frequency.WEEKLY:
            self.instance.weekdays = [
                int(day) for day in weekdays if day.isdigit()
            ]
        elif frequency == HabitTemplate.Frequency.DAILY:
            self.instance.weekdays = []
        if frequency == HabitTemplate.Frequency.WEEKLY and not weekdays:
            message = (
                "اختر يومًا واحدًا على الأقل."
                if self.language == "ar"
                else "Sélectionnez au moins un jour."
            )
            self.add_error("weekdays", message)
        if frequency == HabitTemplate.Frequency.DAILY and weekdays:
            self.add_error(
                "weekdays",
                (
                    "تُستخدم الأيام مع التكرار الأسبوعي فقط."
                    if self.language == "ar"
                    else "Les jours ne s'appliquent qu'au rythme hebdomadaire."
                ),
            )
        if not cleaned_data.get("children"):
            message = (
                "اختر طفلًا واحدًا على الأقل."
                if self.language == "ar"
                else "Sélectionnez au moins un enfant."
            )
            self.add_error("children", message)
        return cleaned_data

    @transaction.atomic
    def save(self, *, created_by):
        creating = self.instance._state.adding
        habit = super().save(commit=False)
        if creating:
            habit.family = self.family
            habit.created_by = created_by
        habit.weekdays = [
            int(day) for day in self.cleaned_data.get("weekdays", [])
        ]
        habit.full_clean()
        habit.save()
        habit.children.set(self.cleaned_data["children"])
        return habit
