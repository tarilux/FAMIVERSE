from django import forms

from accounts.models import ChildProfile

from .models import MissionCategory, MissionTemplate


class MissionCategoryForm(forms.ModelForm):
    class Meta:
        model = MissionCategory
        fields = ("name", "name_ar")
        labels = {
            "name": "Nom de la catégorie (français)",
            "name_ar": "Nom de la catégorie (arabe, facultatif)",
        }


class MissionTemplateForm(forms.ModelForm):
    class Meta:
        model = MissionTemplate
        fields = (
            "title",
            "title_ar",
            "description",
            "description_ar",
            "category",
            "suggested_age_band",
            "coins_reward",
            "xp_reward",
        )
        labels = {
            "title": "Nom de la mission",
            "title_ar": "Nom de la mission (arabe, facultatif)",
            "description": "Description",
            "description_ar": "Description (arabe, facultatif)",
            "category": "Catégorie",
            "suggested_age_band": "Âge conseillé",
            "coins_reward": "Pièces",
            "xp_reward": "XP",
        }
        widgets = {
            "description": forms.Textarea(attrs={"rows": 3}),
            "coins_reward": forms.NumberInput(attrs={"min": 0}),
            "xp_reward": forms.NumberInput(attrs={"min": 0}),
        }

    def __init__(self, *args, family, language="fr", **kwargs):
        super().__init__(*args, **kwargs)
        self.family = family
        self.fields["category"].required = False
        self.fields["category"].queryset = MissionCategory.objects.filter(
            family=family, archived_at__isnull=True
        )
        if language == "ar":
            self.fields["category"].label_from_instance = (
                lambda category: category.name_ar or category.name
            )

    def save(self, *, created_by):
        creating = self.instance._state.adding
        mission = super().save(commit=False)
        if creating:
            mission.family = self.family
            mission.created_by = created_by
        mission.full_clean()
        mission.save()
        return mission


class MissionAssignmentForm(forms.Form):
    children = forms.ModelMultipleChoiceField(
        queryset=ChildProfile.objects.none(),
        widget=forms.CheckboxSelectMultiple,
        label="Enfants",
    )
    due_date = forms.DateField(
        required=False,
        widget=forms.DateInput(attrs={"type": "date"}),
        label="Échéance",
    )

    def __init__(self, *args, family, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["children"].queryset = ChildProfile.objects.filter(
            user__family=family,
            user__is_active=True,
            archived_at__isnull=True,
        ).select_related("user")


class MissionSubmissionForm(forms.Form):
    note = forms.CharField(max_length=500, required=False, label="Message au parent")
