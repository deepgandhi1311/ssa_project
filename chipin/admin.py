from django.contrib import admin
from .models import Group, GroupJoinRequest, Invite

@admin.register(Group)
class GroupAdmin(admin.ModelAdmin):
    list_display = ("name", "admin")

@admin.register(GroupJoinRequest)
class GroupJoinRequestAdmin(admin.ModelAdmin):
    list_display = ("user", "group")