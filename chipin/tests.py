from django.test import TestCase
from django.contrib.auth.models import User
from django.urls import reverse
from .models import Group


class GroupInviteSecurityTests(TestCase):
    def setUp(self):
        self.admin = User.objects.create_user(username='admin@example.com', password='pw-Admin-123')
        self.outsider = User.objects.create_user(username='outsider@example.com', password='pw-Outsider-123')
        self.victim = User.objects.create_user(username='victim@example.com', password='pw-Victim-123')
        self.group = Group.objects.create(name='Trip', admin=self.admin)
        self.group.members.add(self.admin)

    def test_non_admin_cannot_invite_themselves(self):
        self.client.force_login(self.outsider)
        self.client.post(reverse('chipin:invite_users', args=[self.group.id]), {'user_id': self.outsider.id})
        self.assertFalse(self.group.invited_users.filter(id=self.outsider.id).exists())

    def test_admin_can_invite(self):
        self.client.force_login(self.admin)
        self.client.post(reverse('chipin:invite_users', args=[self.group.id]), {'user_id': self.outsider.id})
        self.assertTrue(self.group.invited_users.filter(id=self.outsider.id).exists())

    def test_cannot_accept_invite_for_another_user(self):
        self.group.invited_users.add(self.victim)
        self.client.force_login(self.outsider)
        self.client.get(reverse('chipin:accept_invite', args=[self.group.id]) + f'?user_id={self.victim.id}')
        self.assertFalse(self.group.members.filter(id=self.victim.id).exists())

    def test_uninvited_user_cannot_accept(self):
        self.client.force_login(self.outsider)
        self.client.get(reverse('chipin:accept_invite', args=[self.group.id]))
        self.assertFalse(self.group.members.filter(id=self.outsider.id).exists())

    def test_invited_user_can_accept_own_invite(self):
        self.group.invited_users.add(self.victim)
        self.client.force_login(self.victim)
        self.client.get(reverse('chipin:accept_invite', args=[self.group.id]))
        self.assertTrue(self.group.members.filter(id=self.victim.id).exists())
        self.assertFalse(self.group.invited_users.filter(id=self.victim.id).exists())
