from django.core.management.base import BaseCommand, CommandError

from accounts.models import Account
from core.models import Family
from rewards.models import Reward


REWARDS = (
    ("screens", "30 minutes d'écran", "٣٠ دقيقة من الشاشات", 30),
    ("screens", "1 heure de console le week-end", "ساعة ألعاب في عطلة نهاية الأسبوع", 50),
    ("screens", "Choisir un film", "اختيار فيلم", 25),
    ("screens", "Popcorn au cinéma", "فشار في السينما", 80),
    ("food", "Choisir un repas", "اختيار وجبة", 40),
    ("food", "Glace ou crêpe", "مثلجات أو فطيرة", 60),
    ("food", "Pizza ou burger maison", "بيتزا أو برغر منزلي", 70),
    ("food", "Préparer un gâteau avec un parent", "تحضير كعكة مع أحد الوالدين", 35),
    ("privileges", "Se coucher 30 minutes plus tard", "النوم متأخرًا ٣٠ دقيقة", 50),
    ("privileges", "Inviter un ami pour une soirée", "دعوة صديق لقضاء أمسية", 100),
    ("privileges", "Joker pour éviter une tâche", "إعفاء من مهمة واحدة", 120),
    ("privileges", "Choisir la musique dans la voiture", "اختيار الموسيقى في السيارة", 15),
    ("outings", "Parc indoor", "مدينة ألعاب داخلية", 150),
    ("outings", "Piscine, accrobranche ou pique-nique", "مسبح أو تسلق أو نزهة", 120),
    ("outings", "Sortie vélo ou promenade individuelle", "جولة بالدراجة أو مشي", 70),
    ("outings", "Zoo ou aquarium", "حديقة حيوانات أو أكواريوم", 200),
    ("material", "Cartes Pokémon", "بطاقات بوكيمون", 90),
    ("material", "Livre, BD ou manga", "كتاب أو قصة مصورة", 80),
    ("material", "Coloriage et crayons", "كتاب تلوين وأقلام", 50),
    ("material", "Jouet ou figurine", "لعبة أو مجسم", 150),
)


class Command(BaseCommand):
    help = "Add the suggested bilingual reward catalog to a family."

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

        created = 0
        for category, name, name_ar, price in REWARDS:
            _, was_created = Reward.objects.get_or_create(
                family=family,
                name=name,
                defaults={
                    "created_by": parent,
                    "category": category,
                    "name_ar": name_ar,
                    "price_coins": price,
                },
            )
            created += int(was_created)
        self.stdout.write(
            self.style.SUCCESS(
                f"Catalogue prêt : {created} nouvelle(s) récompense(s), "
                f"{len(REWARDS) - created} déjà présente(s)."
            )
        )
