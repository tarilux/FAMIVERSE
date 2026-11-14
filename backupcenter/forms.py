from django import forms

from .models import BackupRun, BackupSettings


WEEKDAY_CHOICES = (
    (0, "Lundi"),
    (1, "Mardi"),
    (2, "Mercredi"),
    (3, "Jeudi"),
    (4, "Vendredi"),
    (5, "Samedi"),
    (6, "Dimanche"),
)


class BackupSettingsForm(forms.ModelForm):
    weekday = forms.ChoiceField(
        choices=tuple((str(day), label) for day, label in WEEKDAY_CHOICES),
        required=True,
    )

    class Meta:
        model = BackupSettings
        fields = ("enabled", "frequency", "weekday", "schedule_time", "retention_count")
        widgets = {
            "schedule_time": forms.TimeInput(attrs={"type": "time"}),
            "retention_count": forms.NumberInput(attrs={"min": 1, "max": 365}),
        }

    def __init__(self, *args, language="fr", **kwargs):
        super().__init__(*args, **kwargs)
        if language == "ar":
            self.fields["enabled"].label = "تفعيل النسخ الاحتياطي التلقائي"
            self.fields["frequency"].choices = (
                ("daily", "يوميًا"),
                ("weekly", "أسبوعيًا"),
            )
            self.fields["frequency"].label = "التكرار"
            self.fields["weekday"].label = "يوم الأسبوع"
            self.fields["weekday"].choices = (
                ("0", "الاثنين"),
                ("1", "الثلاثاء"),
                ("2", "الأربعاء"),
                ("3", "الخميس"),
                ("4", "الجمعة"),
                ("5", "السبت"),
                ("6", "الأحد"),
            )
            self.fields["schedule_time"].label = "الوقت"
            self.fields["retention_count"].label = "عدد النسخ التلقائية المحتفظ بها"
        else:
            for name, label in {
                "enabled": "Activer les sauvegardes automatiques",
                "frequency": "Fréquence",
                "weekday": "Jour de la semaine (sauvegarde hebdomadaire)",
                "schedule_time": "Heure",
                "retention_count": "Nombre de versions automatiques à conserver",
            }.items():
                self.fields[name].label = label

    def clean_weekday(self):
        return int(self.cleaned_data["weekday"])

    def save(self, commit=True):
        settings = super().save(commit=False)
        settings.full_clean()
        if commit:
            settings.save()
        return settings


class RestoreBackupForm(forms.Form):
    backup = forms.ModelChoiceField(queryset=BackupRun.objects.none(), required=False)
    upload = forms.FileField(required=False)
    confirmation = forms.CharField(max_length=20)
    confirm_overwrite = forms.BooleanField(required=True)

    def __init__(self, *args, family=None, language="fr", **kwargs):
        super().__init__(*args, **kwargs)
        if family is not None:
            self.fields["backup"].queryset = BackupRun.objects.filter(
                family=family,
                status=BackupRun.Status.COMPLETED,
                kind__in=(
                    BackupRun.Kind.MANUAL,
                    BackupRun.Kind.SCHEDULED,
                    BackupRun.Kind.IMPORTED,
                    BackupRun.Kind.PRE_RESTORE,
                ),
            ).exclude(file_name="")
        if language == "ar":
            self.fields["backup"].label = "النسخة الاحتياطية"
            self.fields["upload"].label = "أو ارفع أرشيفًا تم تصديره"
            self.fields["confirmation"].label = "اكتب RESTAURER للتأكيد"
            self.fields["confirm_overwrite"].label = "أؤكد أن البيانات الحالية ستُستبدل"
        else:
            self.fields["backup"].label = "Sauvegarde à restaurer"
            self.fields["upload"].label = "Ou importer une archive exportée"
            self.fields["confirmation"].label = "Saisissez RESTAURER pour confirmer"
            self.fields["confirm_overwrite"].label = "Je confirme le remplacement des données actuelles"

    def clean(self):
        cleaned_data = super().clean()
        if bool(cleaned_data.get("backup")) == bool(cleaned_data.get("upload")):
            raise forms.ValidationError(
                "Choisissez une sauvegarde existante ou importez une archive, pas les deux."
            )
        uploaded_file = cleaned_data.get("upload")
        if uploaded_file and uploaded_file.size > 1_000_000_000:
            self.add_error("upload", "L'archive dépasse la taille maximale autorisée.")
        return cleaned_data

    def clean_confirmation(self):
        confirmation = self.cleaned_data["confirmation"]
        if confirmation != "RESTAURER":
            raise forms.ValidationError("La confirmation doit être exactement RESTAURER.")
        return confirmation
