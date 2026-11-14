from django.core.management.base import BaseCommand, CommandError

from accounts.models import Account
from core.models import Family
from missions.models import MissionCategory, MissionTemplate

MISSIONS = (
    ("Rangement", "التنظيم", "3-5", "Ranger ses jouets", "ترتيب الألعاب", 10, 15),
    ("Autonomie", "الاستقلالية", "3-5", "Faire son lit", "ترتيب السرير", 10, 15),
    ("Autonomie", "الاستقلالية", "3-5", "Se brosser les dents", "تنظيف الأسنان", 5, 10),
    ("Rangement", "التنظيم", "3-5", "Ranger ses chaussures", "ترتيب الأحذية", 5, 10),
    ("Autonomie", "الاستقلالية", "3-5", "Mettre ses vêtements au linge sale", "وضع الملابس المتسخة في سلة الغسيل", 5, 10),
    ("Maison", "المنزل", "3-5", "Poser les couverts", "وضع أدوات المائدة", 5, 10),
    ("Scolaire", "الدراسة", "6-9", "Faire ses devoirs", "إنجاز الواجبات المدرسية", 20, 30),
    ("Scolaire", "الدراسة", "6-9", "Préparer son cartable", "تحضير الحقيبة المدرسية", 10, 15),
    ("Entraide", "التعاون", "6-9", "Nourrir un animal", "إطعام حيوان أليف", 10, 15),
    ("Maison", "المنزل", "6-9", "Mettre ou débarrasser la table", "تجهيز المائدة أو رفعها", 15, 20),
    ("Autonomie", "الاستقلالية", "6-9", "Accrocher son manteau", "تعليق المعطف", 5, 10),
    ("Autonomie", "الاستقلالية", "6-9", "Se laver et s'habiller seul", "الاغتسال وارتداء الملابس بمفرده", 10, 15),
    ("Maison", "المنزل", "10+", "Sortir et trier les poubelles", "إخراج النفايات وفرزها", 15, 25),
    ("Maison", "المنزل", "10+", "Arroser les plantes", "سقي النباتات", 10, 15),
    ("Maison", "المنزل", "10+", "Vider le lave-vaisselle", "إفراغ غسالة الصحون", 20, 30),
    ("Maison", "المنزل", "10+", "Passer l'aspirateur dans sa chambre", "تنظيف الغرفة بالمكنسة الكهربائية", 25, 35),
    ("Maison", "المنزل", "10+", "Plier le linge", "طيّ الملابس", 20, 30),
    ("Entraide", "التعاون", "10+", "Aider à préparer le repas", "المساعدة في إعداد الطعام", 20, 25),
    ("Attitude et bienveillance", "السلوك والتعاون", "all", "Lire pendant 15 minutes", "القراءة لمدة 15 دقيقة", 15, 25),
    ("Attitude et bienveillance", "السلوك والتعاون", "all", "Aider spontanément son frère ou sa sœur", "مساعدة الأخ أو الأخت بمبادرة منه", 15, 20),
    ("Attitude et bienveillance", "السلوك والتعاون", "all", "Ne pas utiliser les écrans avant d'avoir terminé ses tâches", "عدم استخدام الشاشات قبل إنهاء المهام", 25, 40),
)


class Command(BaseCommand):
    help = "Add the suggested bilingual mission library to a family."

    def add_arguments(self, parser):
        parser.add_argument("--family-id", type=int)

    def handle(self, *args, **options):
        family_id = options["family_id"]
        if family_id:
            family = Family.objects.filter(pk=family_id).first()
            if family is None:
                raise CommandError("Famille introuvable.")
        else:
            families = list(Family.objects.order_by("pk")[:2])
            if len(families) != 1:
                raise CommandError(
                    "Indiquez --family-id si l'installation contient zéro ou plusieurs familles."
                )
            family = families[0]

        parent = Account.objects.filter(
            family=family,
            role=Account.Role.PARENT,
            is_active=True,
        ).order_by("pk").first()
        if parent is None:
            raise CommandError("Cette famille ne possède aucun compte parent actif.")

        categories = {}
        for french, arabic, *_ in MISSIONS:
            categories[french], _ = MissionCategory.objects.get_or_create(
                family=family,
                name=french,
                defaults={"name_ar": arabic},
            )

        created = 0
        for french_category, arabic_category, age_band, title, title_ar, coins, xp in MISSIONS:
            _, was_created = MissionTemplate.objects.get_or_create(
                family=family,
                title=title,
                defaults={
                    "created_by": parent,
                    "category": categories[french_category],
                    "title_ar": title_ar,
                    "coins_reward": coins,
                    "xp_reward": xp,
                    "suggested_age_band": age_band,
                },
            )
            created += int(was_created)

        self.stdout.write(
            self.style.SUCCESS(
                f"Bibliothèque prête : {created} nouveau(x) modèle(s), "
                f"{len(MISSIONS) - created} déjà présent(s)."
            )
        )
