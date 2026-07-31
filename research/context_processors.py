from .models import Notification


def notification_count(request):
    if request.user.is_authenticated:
        notif_count = Notification.objects.filter(user=request.user, is_read=False).count()
        # Import here to avoid circular import at module level
        try:
            from .models import Message
            msg_count = Message.objects.filter(recipient=request.user, is_read=False).count()
        except Exception:
            msg_count = 0
        return {
            'unread_notification_count': notif_count,
            'unread_msg_count': msg_count,
        }
    return {'unread_notification_count': 0, 'unread_msg_count': 0}


def user_role(request):
    if request.user.is_authenticated:
        return {'user_role': request.user.role}
    return {'user_role': None}
