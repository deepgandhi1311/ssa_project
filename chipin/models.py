import uuid
from datetime import timedelta
from django.conf import settings
from django.db import models
from django.contrib.auth.models import User
from django.urls import reverse
from django.utils import timezone

def default_invite_expiry():
    return timezone.now() + timedelta(days=14)

class Group(models.Model):
    name = models.CharField(max_length=100)
    admin = models.ForeignKey(User, related_name='admin_groups', on_delete=models.CASCADE)
    members = models.ManyToManyField(User, related_name='group_memberships', blank=True)
    invited_users = models.ManyToManyField(User, related_name='pending_invitations', blank=True)
    def __str__(self):
        return self.name

class Invite(models.Model):
    group = models.ForeignKey(Group, on_delete=models.CASCADE, related_name="invites")
    invited_user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="group_invites")
    token = models.UUIDField(default=uuid.uuid4, editable=False, unique=True)
    invited_by = models.ForeignKey(User, on_delete=models.CASCADE, related_name="sent_invites")
    accepted = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField(default=default_invite_expiry)
    def __str__(self):
        return f"Invite to '{self.group.name}' for {self.invited_user.username}"
    def is_expired(self):
        return timezone.now() > self.expires_at
    def accept_url(self):
        return settings.SITE_ORIGIN + reverse("chipin:accept_invite", args=[str(self.token)])
    @property
    def invitee_email(self):
        return (self.invited_user.email or "").strip()

class GroupJoinRequest(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    group = models.ForeignKey(Group, on_delete=models.CASCADE, related_name='join_requests')
    is_approved = models.BooleanField(default=False)
    
    # Track approvals and rejections separately
    approved_votes = models.ManyToManyField(User, related_name='approved_join_requests', blank=True)
    rejected_votes = models.ManyToManyField(User, related_name='rejected_join_requests', blank=True)
    
    created_at = models.DateTimeField(auto_now_add=True)

    def has_user_voted(self, user):
        return self.approved_votes.filter(id=user.id).exists() or self.rejected_votes.filter(id=user.id).exists()

class Comment(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE)  # User who posted the comment
    group = models.ForeignKey(Group, related_name='comments', on_delete=models.CASCADE)  # Group associated with the comment
    content = models.TextField()  # The comment content
    created_at = models.DateTimeField(auto_now_add=True)  # Timestamp when the comment was posted
    updated_at = models.DateTimeField(auto_now=True)  # Timestamp for the latest update

    def __str__(self):
        return f"{self.user.username}: {self.content[:20]}..."  # Show only first 20 chars for preview

class Event(models.Model):

    class Status(models.TextChoices):
        PENDING = "Pending", "Pending"
        ACTIVE = "Active", "Active"
        ARCHIVED = "Archived", "Archived"

    name = models.CharField(max_length=100)
    date = models.DateField()
    total_spend = models.DecimalField(max_digits=10, decimal_places=2)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING)
    archived_at = models.DateTimeField(null=True, blank=True)
    group = models.ForeignKey(Group, related_name='events', on_delete=models.CASCADE)
    members = models.ManyToManyField(User, related_name='event_memberships', blank=True)

    def calculate_share(self):
        members_count = self.group.members.count()
        if members_count == 0:
            return 0
        return self.total_spend / members_count

    def check_status(self):
        share = self.calculate_share()
        for member in self.group.members.all():
            if member.profile.max_spend < share:
                self.status = self.Status.PENDING
                return False
        self.status = self.Status.ACTIVE
        return True