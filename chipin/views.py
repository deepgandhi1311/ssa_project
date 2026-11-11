from django.contrib.auth.decorators import login_required
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.contrib.auth.models import User
from django.utils import timezone
from django.conf import settings
from .models import Group, Invite
from .forms import GroupCreationForm, CommentForm
from django.urls import reverse
from .models import GroupJoinRequest, Comment
from .models import Event

@login_required
def home(request):
    user = request.user
    pending_invitations = user.pending_invitations.all() # Get pending group invitations for the current user
    user_groups = user.group_memberships.all()  # Get groups the user is a member of
    user_join_requests = GroupJoinRequest.objects.filter(user=user)  # Get join requests sent by the user
    available_groups = Group.objects.exclude(members=user).exclude(join_requests__user=user) # Get groups the user is not a member of and the user has not requested to join
    context = {
        'pending_invitations': pending_invitations,
        'user_groups': user_groups,
        'user_join_requests': user_join_requests,
        'available_groups': available_groups
    }
    return render(request, 'chipin/home.html', context)



@login_required
def create_group(request):
    if request.method == 'POST':
        form = GroupCreationForm(request.POST, user=request.user)
        if form.is_valid():
            group = form.save()
            messages.success(request, f'Group "{group.name}" created successfully!')
            return redirect('chipin:group_detail', group_id=group.id)
    else:
        form = GroupCreationForm(user=request.user)
    return render(request, 'chipin/create_group.html', {'form': form})

@login_required
def group_detail(request, group_id, edit_comment_id=None):
    group = get_object_or_404(Group, id=group_id)
    is_member = request.user in group.members.all()

    # Only fetch comments for group members
    comments = group.comments.all().order_by('-created_at') if is_member else []
    events = group.events.all()

    # Comment handling restricted to members
    comment_to_edit = None
    form = None
    if is_member:
        if edit_comment_id:
            comment_to_edit = get_object_or_404(Comment, id=edit_comment_id)
            if comment_to_edit.user != request.user:
                return redirect('chipin:group_detail', group_id=group.id)

        if request.method == 'POST':
            if comment_to_edit:
                form = CommentForm(request.POST, instance=comment_to_edit)
            else:
                form = CommentForm(request.POST)
            if form.is_valid():
                comment = form.save(commit=False)
                comment.user = request.user
                comment.group = group
                comment.save()
                return redirect('chipin:group_detail', group_id=group.id)
        else:
            form = CommentForm(instance=comment_to_edit) if comment_to_edit else CommentForm()

    # Calculate event share and gather joined member info
    event_share_info = {}
    for event in events:
        event_share = event.calculate_share()
        user_eligible = request.user.profile.max_spend >= event_share
        user_has_joined = request.user in event.members.all()
        
        event_share_info[event] = {
            'share': event_share,
            'eligible': user_eligible,
            'status': event.status,
            'joined': user_has_joined,
            'members': event.members.all()  # Pass members who joined this event
        }

    return render(request, 'chipin/group_detail.html', {
        'group': group,
        'comments': comments,
        'form': form,
        'comment_to_edit': comment_to_edit,
        'events': events,
        'event_share_info': event_share_info,
        'is_member': is_member,
    })

@login_required
def delete_group(request, group_id):
    group = get_object_or_404(Group, id=group_id)
    if request.user == group.admin:
        group.delete()
        messages.success(request, f'Group "{group.name}" has been deleted.')
    else:
        messages.error(request, "You do not have permission to delete this group.")
    return redirect('chipin:home')

@login_required
def invite_users(request, group_id):
    group = get_object_or_404(Group, id=group_id)
    excluded_ids = list(group.members.values_list('id', flat=True)) + list(group.invited_users.values_list('id', flat=True))
    users_not_in_group = User.objects.exclude(id__in=excluded_ids)

    if request.method == 'POST':
        user_id = request.POST.get('user_id')
        invited_user = get_object_or_404(User, id=user_id)      
        
        if invited_user in group.invited_users.all():
            messages.info(request, f'{invited_user.profile.nickname} has already been invited.')
        else:
            group.invited_users.add(invited_user)
            messages.success(request, f'Invitation sent to {invited_user.profile.nickname}.')
        return redirect('chipin:group_detail', group_id=group.id)  

    return render(request, 'chipin/invite_users.html', {
        'group': group,
        'users_not_in_group': users_not_in_group
    })

@login_required
def accept_invite(request, group_id):
    group = get_object_or_404(Group, id=group_id)
    user_id = request.GET.get('user_id')
    if user_id:
        invited_user = get_object_or_404(User, id=user_id)
        if invited_user in group.members.all():
            messages.info(request, f'{invited_user.profile.nickname} is already a member of the group "{group.name}".')
        elif invited_user in group.invited_users.all():
            group.members.add(invited_user)
            group.invited_users.remove(invited_user)  # Remove from invited list
            messages.success(request, f'{invited_user.profile.nickname} has successfully joined the group "{group.name}".')
        else:
            messages.error(request, "You are not invited to join this group.")
    else:
        messages.error(request, "Invalid invitation link.")  
    return redirect('chipin:group_detail', group_id=group.id)

@login_required
def request_to_join_group(request, group_id):
    group = get_object_or_404(Group, id=group_id)
    # Check if the user is already a member
    if request.user in group.members.all():
        messages.info(request, "You are already a member of this group.")
        return redirect('chipin:group_detail', group_id=group.id)
    # Check if the user has already submitted a join request
    join_request, created = GroupJoinRequest.objects.get_or_create(user=request.user, group=group)
    if created:
        messages.success(request, "Your request to join the group has been submitted.")
    else:
        messages.info(request, "You have already requested to join this group.")
    return redirect('chipin:group_detail', group_id=group.id)

@login_required
def delete_join_request(request, request_id):
    join_request = get_object_or_404(GroupJoinRequest, id=request_id, user=request.user)
    # Ensure the logged-in user can only delete their own join requests
    if join_request.user == request.user:
        join_request.delete()
        messages.success(request, "Your join request has been successfully deleted.")
    else:
        messages.error(request, "You are not authorised to delete this join request.")
    return redirect('chipin:home')  
    
@login_required
def leave_group(request, group_id):
    group = get_object_or_404(Group, id=group_id)
    # Check if the user is a member of the group
    if request.user in group.members.all():
        group.members.remove(request.user)  # Remove the user from the group
        messages.success(request, f'You have left the group {group.name}.')
    else:
        messages.error(request, 'You are not a member of this group.') 
    return redirect('chipin:home')  

@login_required
def vote_on_join_request(request, group_id, request_id, vote):
    group = get_object_or_404(Group, id=group_id)
    join_request = get_object_or_404(GroupJoinRequest, id=request_id) 

    # 1. Verification checks
    if request.user not in group.members.all():
        messages.error(request, "You must be a member of the group to vote.")
        return redirect('chipin:group_detail', group_id=group.id)  

    if join_request.has_user_voted(request.user):
        messages.info(request, "You have already voted on this request.")
        return redirect('chipin:group_detail', group_id=group.id)

    # 2. Register the vote choice
    if vote == 'approve':
        join_request.approved_votes.add(request.user)
        messages.success(request, "Your approval vote has been recorded.")
    elif vote == 'reject':
        join_request.rejected_votes.add(request.user)
        messages.info(request, "Your rejection vote has been recorded.")
    else:
        messages.error(request, "Invalid vote action.")
        return redirect('chipin:group_detail', group_id=group.id)

    # 3. Evaluate voting status
    total_members = group.members.count()
    if total_members > 0:
        approval_count = join_request.approved_votes.count()
        rejection_count = join_request.rejected_votes.count()

        # Check if >60% approved
        if (approval_count / total_members) >= 0.6:
            join_request.is_approved = True
            group.members.add(join_request.user)
            join_request.delete()  # Clean up request after approval
            messages.success(request, f"{join_request.user.profile.nickname} has been approved and added to the group!")

        # Optional: Check if rejections make >60% approval impossible (e.g. >40% rejected)
        elif (rejection_count / total_members) > 0.4:
            join_request.delete()  # Clean up rejected request
            messages.warning(request, f"Join request for {join_request.user.profile.nickname} was rejected.")

    return redirect('chipin:group_detail', group_id=group.id)

@login_required
def reject_invite(request, group_id):
    group = get_object_or_404(Group, id=group_id)
    
    # Query database directly using user ID for exact match
    if group.invited_users.filter(id=request.user.id).exists():
        group.invited_users.remove(request.user)
        messages.success(request, f'You have declined the invitation to join "{group.name}".')
    else:
        messages.error(request, 'You do not have a pending invitation for this group.')
        
    return redirect('chipin:home')

@login_required
def kick_member(request, group_id, user_id):
    group = get_object_or_404(Group, id=group_id)
    
    if request.user != group.admin:
        messages.error(request, "Only the group administrator can kick members.")
        return redirect('chipin:group_detail', group_id=group.id)
    
    user_to_kick = get_object_or_404(User, id=user_id)
    
    if user_to_kick == group.admin:
        messages.error(request, "The administrator cannot be kicked from the group.")
        return redirect('chipin:group_detail', group_id=group.id)

    if user_to_kick in group.members.all():
        group.members.remove(user_to_kick)
        messages.success(request, f'{user_to_kick.profile.nickname} has been removed from the group.')
    else:
        messages.error(request, 'That user is not a member of this group.')

    return redirect('chipin:group_detail', group_id=group.id)

@login_required
def cancel_invite(request, group_id, user_id):
    group = get_object_or_404(Group, id=group_id)
    
    # Only group admins can cancel invites
    if request.user != group.admin:
        messages.error(request, "Only the group administrator can cancel invitations.")
        return redirect('chipin:group_detail', group_id=group.id)
    
    user_to_remove = get_object_or_404(User, id=user_id)
    
    if user_to_remove in group.invited_users.all():
        group.invited_users.remove(user_to_remove)
        messages.success(request, f'Invitation for {user_to_remove.profile.nickname} has been canceled.')
    else:
        messages.info(request, f'{user_to_remove.profile.nickname} does not have a pending invitation.')
        
    return redirect('chipin:group_detail', group_id=group.id)

@login_required
def edit_comment(request, comment_id):
    comment = get_object_or_404(Comment, id=comment_id)
    if comment.user != request.user:  # Ensure only the comment author can edit
        return redirect('chipin:group_detail', group_id=comment.group.id)
    if request.method == 'POST':
        form = CommentForm(request.POST, instance=comment)
        if form.is_valid():
            form.save()
            return redirect('chipin:group_detail', group_id=comment.group.id)
    else:
        form = CommentForm(instance=comment)
    return render(request, 'chipin/edit_comment.html', {'form': form, 'comment': comment})

@login_required
def delete_comment(request, comment_id):
    comment = get_object_or_404(Comment, id=comment_id)
    if comment.user == request.user or request.user == comment.group.admin:  # Allow author or group admin to delete
        comment.delete()
    return redirect('chipin:group_detail', group_id=comment.group.id)

@login_required
def create_event(request, group_id):
    group = get_object_or_404(Group, id=group_id)
    if request.user != group.admin:
        messages.error(request, "Only the group administrator can create events.")
        return redirect('chipin:group_detail', group_id=group.id)
    if request.method == 'POST':
        event_name = request.POST.get('name')
        event_date = request.POST.get('date')
        total_spend = request.POST.get('total_spend')
        event = Event.objects.create(
            name=event_name,
            date=event_date,
            total_spend=total_spend,
            group=group
        )
        messages.success(request, f'Event "{event_name}" created successfully!')
        return redirect('chipin:group_detail', group_id=group.id)
    return render(request, 'chipin/create_event.html', {'group': group})

@login_required
def join_event(request, group_id, event_id):
    group = get_object_or_404(Group, id=group_id)
    event = get_object_or_404(Event, id=event_id, group=group)

    # Restrict joining event if the user is not a group member
    if request.user not in group.members.all():
        messages.error(request, "You must be a member of the group to join this event.")
        return redirect('chipin:group_detail', group_id=group.id)

    event_share = event.calculate_share()  
    if request.user.profile.max_spend < event_share:
        messages.error(request, f"Your max spend of ${request.user.profile.max_spend} is too low to join this event.")
        return redirect('chipin:group_detail', group_id=group.id)

    if request.user in event.members.all():
        messages.info(request, "You have already joined this event.")
        return redirect('chipin:group_detail', group_id=group.id)

    event.members.add(request.user)   
    messages.success(request, f"You have successfully joined the event '{event.name}'.")  
    event.check_status()
    event.save()
    return redirect('chipin:group_detail', group_id=group.id)


@login_required
def update_event_status(request, group_id, event_id):
    group = get_object_or_404(Group, id=group_id)
    event = get_object_or_404(Event, id=event_id, group=group)
    # Ensure that only the group admin can update the event status
    if request.user != group.admin:
        messages.error(request, "Only the group administrator can update the event status.")
        return redirect('chipin:group_detail', group_id=group.id)
    # Calculate the share per member
    event_share = event.calculate_share()
    # Check if all members can afford the event share
    sufficient_funds = True
    for member in group.members.all():
        if member.profile.max_spend < event_share:
            sufficient_funds = False
            break
    # Update the event status based on the members' ability to cover the share
    if sufficient_funds:
        event.status = "Active"
        messages.success(request, f"The event '{event.name}' is now Active. All members can cover the cost.")
    else:
        event.status = "Pending"
        messages.warning(request, f"The event '{event.name}' remains Pending. Some members cannot cover the cost.")
    # Save the updated event status
    event.save()
    return redirect('chipin:group_detail', group_id=group.id)

@login_required
def leave_event(request, group_id, event_id):
    group = get_object_or_404(Group, id=group_id)
    event = get_object_or_404(Event, id=event_id, group=group)
    # Check if the user is part of the event
    if request.user not in event.members.all():
        messages.error(request, "You are not a member of this event.")
        return redirect('chipin:group_detail', group_id=group.id)
    # Remove the user from the event
    event.members.remove(request.user)
    messages.success(request, f"You have successfully left the event '{event.name}'.")
    # Optionally, check if the event status should be updated
    event.check_status()
    event.save()
    return redirect('chipin:group_detail', group_id=group.id)

@login_required
def delete_event(request, group_id, event_id):
    group = get_object_or_404(Group, id=group_id)
    event = get_object_or_404(Event, id=event_id, group=group)
    # Ensure only the group admin can delete the event
    if request.user != group.admin:
        messages.error(request, "Only the group administrator can delete events.")
        return redirect('chipin:group_detail', group_id=group.id)
    # Delete the event
    event.delete()
    messages.success(request, f"The event '{event.name}' has been deleted.")
    return redirect('chipin:group_detail', group_id=group.id)