from datetime import date, timedelta

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from accounts.models import Account, ChildProfile
from core.models import Family
from habits.models import HabitOccurrence, HabitTemplate
from habits.services import decide_habit, submit_habit
from missions.models import MissionTemplate
from missions.services import assign_mission, decide_missions, submit_mission
from progression.models import CoinTransaction
from rewards.models import Reward
from rewards.services import decide_reward_request, request_reward

from .models import FamilyMessage, MessageRecipient, Notification
from .services import send_family_message


class CommunicationTests(TestCase):
    def setUp(self):
        self.family = Family.objects.create(name="Famille Test")
        self.other_family = Family.objects.create(name="Autre famille")
        self.parent = Account.objects.create_user(
            username="parent",
            password="4826",
            first_name="Parent",
            role=Account.Role.PARENT,
            family=self.family,
        )
        self.other_parent = Account.objects.create_user(
            username="other-parent",
            password="2719",
            role=Account.Role.PARENT,
            family=self.other_family,
        )
        self.child = self.create_child(self.family, "lea", "Léa")
        self.sibling = self.create_child(self.family, "adam", "Adam")
        self.other_child = self.create_child(
            self.other_family, "sara", "Sara"
        )

    def create_child(self, family, username, first_name):
        user = Account.objects.create_user(
            username=username,
            password="7315",
            role=Account.Role.CHILD,
            family=family,
        )
        return ChildProfile.objects.create(
            user=user,
            first_name=first_name,
            date_of_birth=date(2017, 5, 10),
        )

    def test_parent_can_send_targeted_and_family_messages(self):
        self.client.force_login(self.parent)
        url = reverse("communications:sent_messages")
        expiry = (timezone.localtime() + timedelta(days=1)).strftime(
            "%Y-%m-%dT%H:%M"
        )
        response = self.client.post(
            url,
            {
                "recipient": str(self.child.pk),
                "content": "Bonne journée",
                "content_ar": "أتمنى لك يومًا سعيدًا",
                "expires_at": expiry,
            },
        )
        self.assertRedirects(response, url)
        targeted = FamilyMessage.objects.get()
        self.assertEqual(
            targeted.expires_at.date(),
            (timezone.localtime() + timedelta(days=1)).date(),
        )
        self.assertEqual(
            list(targeted.recipients.values_list("child_id", flat=True)),
            [self.child.pk],
        )

        response = self.client.post(
            url,
            {
                "recipient": "all",
                "content_ar": "عيد سعيد",
            },
        )
        self.assertRedirects(response, url)
        broadcast = FamilyMessage.objects.order_by("-pk").first()
        self.assertEqual(broadcast.content, "عيد سعيد")
        self.assertEqual(broadcast.content_ar, "عيد سعيد")
        self.assertEqual(broadcast.recipients.count(), 2)
        self.assertEqual(
            Notification.objects.filter(kind="new_message").count(), 3
        )
        self.assertFalse(
            Notification.objects.filter(
                recipient=self.other_child.user,
                kind=Notification.Kind.NEW_MESSAGE,
            ).exists()
        )

        self.client.force_login(self.child.user)
        inbox = self.client.get(
            reverse("communications:message_inbox"),
            HTTP_ACCEPT_LANGUAGE="ar",
        )
        self.assertContains(inbox, "أتمنى لك يومًا سعيدًا")
        self.assertContains(inbox, "عيد سعيد")
        self.assertEqual(inbox.context["unread_message_count"], 2)
        self.assertContains(inbox, 'dir="rtl"')

        delivery = MessageRecipient.objects.get(
            message=targeted, child=self.child
        )
        read_url = reverse(
            "communications:message_read",
            args=[delivery.pk, "read"],
        )
        self.assertRedirects(
            self.client.post(read_url),
            reverse("communications:message_inbox"),
        )
        delivery.refresh_from_db()
        self.assertIsNotNone(delivery.read_at)
        self.assertEqual(
            self.client.get(reverse("communications:message_inbox")).context[
                "unread_message_count"
            ],
            1,
        )
        self.assertEqual(
            Notification.objects.filter(
                recipient=self.child.user,
                read_at__isnull=True,
            ).count(),
            1,
        )
        unread_url = reverse(
            "communications:message_read",
            args=[delivery.pk, "unread"],
        )
        self.client.post(unread_url)
        delivery.refresh_from_db()
        self.assertIsNone(delivery.read_at)
        self.assertEqual(
            Notification.objects.filter(
                recipient=self.child.user,
                read_at__isnull=True,
            ).count(),
            2,
        )

    def test_message_and_notification_access_is_limited_to_recipient(self):
        message = send_family_message(
            self.parent,
            str(self.child.pk),
            "Pour Léa uniquement",
        )
        delivery = MessageRecipient.objects.get(message=message)
        notification = Notification.objects.get(message=message)

        self.client.force_login(self.sibling.user)
        self.assertNotContains(
            self.client.get(reverse("communications:message_inbox")),
            "Pour Léa uniquement",
        )
        self.assertEqual(
            self.client.post(
                reverse(
                    "communications:message_read",
                    args=[delivery.pk, "read"],
                )
            ).status_code,
            404,
        )
        self.assertEqual(
            self.client.post(
                reverse(
                    "communications:notification_read",
                    args=[notification.pk, "read"],
                )
            ).status_code,
            404,
        )

        self.client.force_login(self.other_parent)
        self.assertNotContains(
            self.client.get(reverse("communications:sent_messages")),
            "Pour Léa uniquement",
        )

    def test_mission_habit_and_reward_workflows_create_notifications(self):
        template = MissionTemplate.objects.create(
            family=self.family,
            created_by=self.parent,
            title="Lire un chapitre",
            title_ar="قراءة فصل",
            coins_reward=10,
            xp_reward=10,
        )
        occurrence = assign_mission(
            template, [self.child.pk], self.parent
        )[0]
        self.assertTrue(
            Notification.objects.filter(
                recipient=self.child.user,
                kind=Notification.Kind.MISSION_ASSIGNED,
            ).exists()
        )
        submit_mission(occurrence.pk, self.child.user)
        self.assertTrue(
            Notification.objects.filter(
                recipient=self.parent,
                kind=Notification.Kind.MISSION_SUBMITTED,
            ).exists()
        )
        decide_missions([occurrence.pk], self.parent, approve=True)
        self.assertTrue(
            Notification.objects.filter(
                recipient=self.child.user,
                kind=Notification.Kind.MISSION_APPROVED,
            ).exists()
        )
        rejected_occurrence = assign_mission(
            template, [self.child.pk], self.parent
        )[0]
        submit_mission(rejected_occurrence.pk, self.child.user)
        decide_missions(
            [rejected_occurrence.pk], self.parent, approve=False
        )
        self.assertTrue(
            Notification.objects.filter(
                recipient=self.child.user,
                kind=Notification.Kind.MISSION_REJECTED,
            ).exists()
        )

        habit = HabitTemplate.objects.create(
            family=self.family,
            created_by=self.parent,
            title="Ranger son bureau",
            title_ar="ترتيب المكتب",
            starts_on=date.today(),
        )
        habit.children.add(self.child)
        habit_occurrence = HabitOccurrence.objects.create(
            template=habit,
            child=self.child,
            scheduled_date=date.today(),
            title=habit.title,
            title_ar=habit.title_ar,
        )
        submit_habit(habit_occurrence.pk, self.child.user)
        decide_habit(habit_occurrence.pk, self.parent, approve=False)
        self.assertTrue(
            Notification.objects.filter(
                recipient=self.parent,
                kind=Notification.Kind.HABIT_SUBMITTED,
            ).exists()
        )
        self.assertTrue(
            Notification.objects.filter(
                recipient=self.child.user,
                kind=Notification.Kind.HABIT_REJECTED,
            ).exists()
        )
        approved_habit_occurrence = HabitOccurrence.objects.create(
            template=habit,
            child=self.child,
            scheduled_date=date.today() + timedelta(days=1),
            title=habit.title,
            title_ar=habit.title_ar,
        )
        submit_habit(approved_habit_occurrence.pk, self.child.user)
        decide_habit(approved_habit_occurrence.pk, self.parent, approve=True)
        self.assertTrue(
            Notification.objects.filter(
                recipient=self.child.user,
                kind=Notification.Kind.HABIT_APPROVED,
            ).exists()
        )

        reward = Reward.objects.create(
            family=self.family,
            created_by=self.parent,
            category=Reward.Category.MATERIAL,
            name="Un livre",
            name_ar="كتاب",
            price_coins=5,
        )
        reward_request, created = request_reward(reward.pk, self.child.user)
        self.assertTrue(created)
        self.assertTrue(
            Notification.objects.filter(
                recipient=self.parent,
                kind=Notification.Kind.REWARD_REQUESTED,
            ).exists()
        )
        decide_reward_request(reward_request.pk, self.parent, approve=True)
        self.assertTrue(
            Notification.objects.filter(
                recipient=self.child.user,
                kind=Notification.Kind.REWARD_ACCEPTED,
            ).exists()
        )
        rejected_reward = Reward.objects.create(
            family=self.family,
            created_by=self.parent,
            category=Reward.Category.MATERIAL,
            name="Un deuxième livre",
            price_coins=1,
        )
        rejected_request, _ = request_reward(
            rejected_reward.pk, self.child.user
        )
        decide_reward_request(
            rejected_request.pk, self.parent, approve=False
        )
        self.assertTrue(
            Notification.objects.filter(
                recipient=self.child.user,
                kind=Notification.Kind.REWARD_REJECTED,
            ).exists()
        )

    def test_notification_history_can_be_marked_read_and_unread(self):
        send_family_message(self.parent, str(self.child.pk), "À lire")
        notification = Notification.objects.get(recipient=self.child.user)
        self.client.force_login(self.child.user)
        list_url = reverse("communications:notification_list")
        response = self.client.get(list_url)
        self.assertContains(response, "Nouveau message")
        self.assertEqual(response.context["unread_notification_count"], 1)

        read_url = reverse(
            "communications:notification_read",
            args=[notification.pk, "read"],
        )
        self.assertRedirects(self.client.post(read_url), list_url)
        notification.refresh_from_db()
        self.assertIsNotNone(notification.read_at)

        unread_url = reverse(
            "communications:notification_read",
            args=[notification.pk, "unread"],
        )
        self.assertRedirects(self.client.post(unread_url), list_url)
        notification.refresh_from_db()
        self.assertIsNone(notification.read_at)
