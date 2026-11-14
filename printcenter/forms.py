from django import forms

from accounts.models import ChildProfile

from .models import PrintCalendarBlock, PrintSettings


WEEKDAY_CHOICES = (
    (0, "Lundi"),
    (1, "Mardi"),
    (2, "Mercredi"),
    (3, "Jeudi"),
    (4, "Vendredi"),
    (5, "Samedi"),
    (6, "Dimanche"),
)


class PrintRequestForm(forms.Form):
    child = forms.ModelChoiceField(queryset=ChildProfile.objects.none())
    kind = forms.ChoiceField(
        choices=(("missions", "Missions du jour"), ("progress", "Progression"))
    )

    def __init__(self, *args, family=None, language="fr", child_only=False, **kwargs):
        super().__init__(*args, **kwargs)
        if family is not None:
            self.fields["child"].queryset = ChildProfile.objects.filter(
                user__family=family, archived_at__isnull=True
            )
        if child_only:
            self.fields.pop("child")
        if language == "ar":
            self.fields["kind"].choices = (
                ("missions", "مهام اليوم"),
                ("progress", "التقدم"),
            )
            if "child" in self.fields:
                self.fields["child"].label = "الطفل"
        else:
            if "child" in self.fields:
                self.fields["child"].label = "Enfant"
            self.fields["kind"].label = "Type de ticket"


class PrintSettingsForm(forms.ModelForm):
    weekdays = forms.MultipleChoiceField(
        choices=tuple((str(day), label) for day, label in WEEKDAY_CHOICES),
        required=False,
        widget=forms.CheckboxSelectMultiple,
        label="Jours prévus",
    )

    class Meta:
        model = PrintSettings
        fields = (
            "schedule_time",
            "top_margin_mm",
            "bottom_margin_mm",
            "density",
            "feed_lines",
            "automatic_cut",
            "weekdays",
            "calendar_confirmed",
        )
        widgets = {
            "schedule_time": forms.TimeInput(attrs={"type": "time"}),
            "top_margin_mm": forms.NumberInput(attrs={"min": 0, "max": 50}),
            "bottom_margin_mm": forms.NumberInput(attrs={"min": 0, "max": 50}),
            "density": forms.NumberInput(attrs={"min": 0, "max": 15}),
            "feed_lines": forms.NumberInput(attrs={"min": 0, "max": 20}),
        }

    def __init__(self, *args, language="fr", **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["weekdays"].initial = [
            str(day) for day in (self.instance.weekdays or [])
        ]
        if language == "ar":
            self.fields["weekdays"].choices = (
                ("0", "الاثنين"),
                ("1", "الثلاثاء"),
                ("2", "الأربعاء"),
                ("3", "الخميس"),
                ("4", "الجمعة"),
                ("5", "السبت"),
                ("6", "الأحد"),
            )
            for name, label in {
                "schedule_time": "وقت الطباعة المخطط",
                "top_margin_mm": "الهامش العلوي (مم)",
                "bottom_margin_mm": "الهامش السفلي (مم)",
                "density": "الكثافة (0–15)",
                "feed_lines": "أسطر تغذية الورق",
                "automatic_cut": "القطع التلقائي",
                "weekdays": "أيام الأسبوع",
                "calendar_confirmed": "تم التحقق من تقويم العائلة يدويًا",
            }.items():
                self.fields[name].label = label
        else:
            for name, label in {
                "schedule_time": "Heure prévue",
                "top_margin_mm": "Marge supérieure (mm)",
                "bottom_margin_mm": "Marge inférieure (mm)",
                "density": "Densité (0–15)",
                "feed_lines": "Avance papier (lignes)",
                "automatic_cut": "Coupe automatique",
                "weekdays": "Jours prévus",
                "calendar_confirmed": "Calendrier familial vérifié manuellement",
            }.items():
                self.fields[name].label = label

    def clean_weekdays(self):
        return [int(day) for day in self.cleaned_data["weekdays"]]

    def save(self, commit=True):
        settings = super().save(commit=False)
        settings.weekdays = [int(day) for day in self.cleaned_data["weekdays"]]
        settings.full_clean()
        if commit:
            settings.save()
        return settings


class PrintCalendarBlockForm(forms.ModelForm):
    class Meta:
        model = PrintCalendarBlock
        fields = ("kind", "label", "starts_on", "ends_on")
        widgets = {
            "starts_on": forms.DateInput(attrs={"type": "date"}),
            "ends_on": forms.DateInput(attrs={"type": "date"}),
        }

    def __init__(self, *args, language="fr", **kwargs):
        super().__init__(*args, **kwargs)
        if language == "ar":
            self.fields["kind"].choices = (
                ("school_break", "عطلة مدرسية"),
                ("public_holiday", "يوم عطلة رسمية"),
            )
            for name, label in {
                "kind": "النوع",
                "label": "الاسم",
                "starts_on": "تاريخ البداية",
                "ends_on": "تاريخ النهاية",
            }.items():
                self.fields[name].label = label
        else:
            for name, label in {
                "kind": "Type de période",
                "label": "Nom de la période",
                "starts_on": "Date de début",
                "ends_on": "Date de fin",
            }.items():
                self.fields[name].label = label
