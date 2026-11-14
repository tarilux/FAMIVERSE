from django.db import migrations


LEVELS = (
    (1, "Explorateur", "مستكشف", 0),
    (2, "Aventurier", "مغامر", 100),
    (3, "Bâtisseur", "بنّاء", 250),
    (4, "Inventeur", "مخترع", 450),
    (5, "Gardien", "حارس", 700),
    (6, "Champion", "بطل", 1000),
    (7, "Héros", "فارس", 1400),
    (8, "Maître", "خبير", 1900),
    (9, "Légende", "أسطورة", 2500),
    (10, "Étoile FAMIVERSE", "نجم فاميفيرس", 3200),
)

BADGES = (
    (
        "first_mission", "Première mission", "المهمة الأولى",
        "Pour une première mission validée.", "لإتمام أول مهمة بنجاح.",
        "missions", "mission_count", 1, "", False, "mission",
    ),
    (
        "regularity_3_days", "Régularité : 3 jours", "المواظبة: ٣ أيام",
        "Pour une activité validée pendant 3 jours consécutifs.",
        "لإنجاز نشاط معتمد لمدة ٣ أيام متتالية.",
        "regularity", "streak_days", 3, "", False, "calendar",
    ),
    (
        "regularity_7_days", "Régularité : 7 jours", "المواظبة: ٧ أيام",
        "Pour une activité validée pendant 7 jours consécutifs.",
        "لإنجاز نشاط معتمد لمدة ٧ أيام متتالية.",
        "regularity", "streak_days", 7, "", False, "calendar",
    ),
    (
        "regularity_30_days", "Régularité : 30 jours", "المواظبة: ٣٠ يومًا",
        "Pour une activité validée pendant 30 jours consécutifs.",
        "لإنجاز نشاط معتمد لمدة ٣٠ يومًا متتاليًا.",
        "regularity", "streak_days", 30, "", False, "calendar",
    ),
    (
        "regularity_100_missions", "100 missions régulières", "١٠٠ مهمة مواظبة",
        "Pour 100 missions validées.", "لإتمام ١٠٠ مهمة بنجاح.",
        "regularity", "mission_count", 100, "", False, "mission",
    ),
    (
        "missions_10", "10 missions", "١٠ مهام",
        "Pour 10 missions validées.", "لإتمام ١٠ مهام بنجاح.",
        "missions", "mission_count", 10, "", False, "mission",
    ),
    (
        "missions_25", "25 missions", "٢٥ مهمة",
        "Pour 25 missions validées.", "لإتمام ٢٥ مهمة بنجاح.",
        "missions", "mission_count", 25, "", False, "mission",
    ),
    (
        "missions_100", "100 missions accomplies", "١٠٠ مهمة مكتملة",
        "Pour 100 missions validées.", "لإتمام ١٠٠ مهمة بنجاح.",
        "missions", "mission_count", 100, "", False, "mission",
    ),
    (
        "tidying_20", "Champion du rangement", "بطل الترتيب",
        "Pour 20 missions de catégorie Rangement validées.",
        "لإتمام ٢٠ مهمة معتمدة في فئة الترتيب.",
        "missions", "category_count", 20, "rangement", False, "home",
    ),
    (
        "education_20", "Curieux et appliqué", "فضولي ومجتهد",
        "Pour 20 missions éducatives ou scolaires validées.",
        "لإتمام ٢٠ مهمة تعليمية أو دراسية معتمدة.",
        "missions", "category_count", 20, "education", False, "book",
    ),
    (
        "without_reminder_10", "Autonome sans rappel", "مستقل دون تذكير",
        "Attribué par le parent après 10 missions réalisées sans rappel.",
        "يمنحه الوالد بعد إنجاز ١٠ مهام دون تذكير.",
        "autonomy", "manual", 10, "", True, "autonomy",
    ),
    (
        "on_time_20", "Toujours à l'heure", "دائمًا في الموعد",
        "Pour 20 missions soumises au plus tard à leur date d'échéance.",
        "لإرسال ٢٠ مهمة في موعدها أو قبله.",
        "autonomy", "on_time_missions", 20, "", False, "clock",
    ),
    (
        "without_delay_30", "Sans retard", "دون تأخير",
        "Attribué par le parent après 30 missions réalisées sans retard.",
        "يمنحه الوالد بعد إنجاز ٣٠ مهمة دون تأخير.",
        "autonomy", "manual", 30, "", True, "clock",
    ),
    (
        "spontaneous_help_5", "Coup de main spontané", "مساعدة بمبادرة",
        "Attribué par le parent après 5 aides spontanées.",
        "يمنحه الوالد بعد تقديم ٥ مساعدات بمبادرة ذاتية.",
        "family", "manual", 5, "", True, "heart",
    ),
    (
        "collective_missions_10", "Esprit d'équipe", "روح الفريق",
        "Attribué par le parent après 10 missions collectives.",
        "يمنحه الوالد بعد ١٠ مهام جماعية.",
        "family", "manual", 10, "", True, "team",
    ),
    (
        "family_projects_5", "Projet familial", "مشروع عائلي",
        "Attribué par le parent après 5 projets familiaux.",
        "يمنحه الوالد بعد ٥ مشاريع عائلية.",
        "family", "manual", 5, "", True, "family",
    ),
    (
        "first_coin", "Première pièce", "القطعة الأولى",
        "Pour une première pièce gagnée grâce à une mission ou une habitude.",
        "للحصول على أول قطعة من مهمة أو عادة.",
        "savings", "first_coin", 1, "", False, "coin",
    ),
    (
        "saved_100", "Économies : 100 pièces", "مدخرات: ١٠٠ قطعة",
        "Pour un solde d'au moins 100 pièces.", "عند بلوغ رصيد ١٠٠ قطعة.",
        "savings", "coins_saved", 100, "", False, "coin",
    ),
    (
        "earned_500", "500 pièces gagnées", "٥٠٠ قطعة مكتسبة",
        "Pour 500 pièces gagnées grâce aux missions et habitudes.",
        "لكسب ٥٠٠ قطعة من المهام والعادات.",
        "savings", "coins_earned", 500, "", False, "coin",
    ),
    (
        "birthday", "Joyeux anniversaire", "عيد ميلاد سعيد",
        "Attribué manuellement par le parent pour un anniversaire.",
        "يمنحه الوالد يدويًا بمناسبة عيد الميلاد.",
        "special", "manual", 1, "", True, "star",
    ),
    (
        "year_end_challenge", "Défi de fin d'année", "تحدي نهاية العام",
        "Attribué manuellement par le parent.", "يمنحه الوالد يدويًا.",
        "special", "manual", 1, "", True, "star",
    ),
    (
        "royal", "Badge royal", "شارة ملكية",
        "Attribué manuellement par le parent.", "يمنحه الوالد يدويًا.",
        "special", "manual", 1, "", True, "crown",
    ),
)


def seed_reference_data(apps, schema_editor):
    LevelDefinition = apps.get_model("progression", "LevelDefinition")
    BadgeDefinition = apps.get_model("progression", "BadgeDefinition")
    for level, name, name_ar, xp_required in LEVELS:
        LevelDefinition.objects.get_or_create(
            level=level,
            defaults={
                "name": name,
                "name_ar": name_ar,
                "xp_required": xp_required,
            },
        )
    for (
        slug,
        name,
        name_ar,
        description,
        description_ar,
        category,
        rule,
        threshold,
        criteria_value,
        manual_only,
        icon,
    ) in BADGES:
        BadgeDefinition.objects.get_or_create(
            slug=slug,
            defaults={
                "name": name,
                "name_ar": name_ar,
                "description": description,
                "description_ar": description_ar,
                "category": category,
                "rule": rule,
                "threshold": threshold,
                "criteria_value": criteria_value,
                "manual_only": manual_only,
                "icon": icon,
            },
        )


class Migration(migrations.Migration):
    dependencies = [("progression", "0003_badgedefinition_leveldefinition_badgeaward")]
    operations = [migrations.RunPython(seed_reference_data, migrations.RunPython.noop)]
