import json
from channels.generic.websocket import AsyncWebsocketConsumer
from channels.db import database_sync_to_async
from django.contrib.auth.models import AnonymousUser
from django.utils import timezone


class NotificationConsumer(AsyncWebsocketConsumer):
    """
    Handles two WebSocket event types:
      - 'notification'   : a system notification was created
      - 'unread_count'   : badge update for both notifications + messages
      - 'chat_message'   : a new direct message arrived in a conversation
    """

    async def connect(self):
        self.user = self.scope.get('user')
        if self.user is None or isinstance(self.user, AnonymousUser):
            await self.close()
            return

        self.group_name = f'user_{self.user.id}'
        await self.channel_layer.group_add(self.group_name, self.channel_name)
        await self.accept()

        # Push current counts immediately on connect
        await self._push_counts()

    async def disconnect(self, close_code):
        if hasattr(self, 'group_name'):
            await self.channel_layer.group_discard(self.group_name, self.channel_name)

    async def receive(self, text_data):
        try:
            data = json.loads(text_data)
        except (json.JSONDecodeError, ValueError):
            return

        if data.get('type') == 'mark_notification_read':
            await self.mark_notification_read(data.get('notification_id'))
            await self._push_counts()

        elif data.get('type') == 'mark_messages_read':
            await self.mark_messages_read(data.get('allocation_id'))
            await self._push_counts()

    # ------------------------------------------------------------------ #
    # Channel layer event handlers (called by group_send from views)      #
    # ------------------------------------------------------------------ #

    async def send_notification(self, event):
        """Push a system notification toast + update badge."""
        await self.send(text_data=json.dumps({
            'type':            'notification',
            'title':           event['title'],
            'message':         event['message'],
            'notification_id': event.get('notification_id'),
            'notif_type':      event.get('notif_type', 'info'),
            'link':            event.get('link', ''),
        }))
        await self._push_counts()

    async def chat_message(self, event):
        """Push a real-time chat message to the recipient's socket."""
        await self.send(text_data=json.dumps({
            'type':          'chat_message',
            'message_id':    event['message_id'],
            'allocation_id': event['allocation_id'],
            'sender_id':     event['sender_id'],
            'sender_name':   event['sender_name'],
            'content':       event['content'],
            'created_at':    event['created_at'],
        }))
        await self._push_counts()

    # ------------------------------------------------------------------ #
    # Helpers                                                              #
    # ------------------------------------------------------------------ #

    async def _push_counts(self):
        notif_count = await self.get_unread_notification_count()
        msg_count   = await self.get_unread_message_count()
        await self.send(text_data=json.dumps({
            'type':         'unread_count',
            'count':        notif_count + msg_count,
            'notif_count':  notif_count,
            'msg_count':    msg_count,
        }))

    # ------------------------------------------------------------------ #
    # DB helpers (run in thread pool)                                      #
    # ------------------------------------------------------------------ #

    @database_sync_to_async
    def get_unread_notification_count(self):
        from .models import Notification
        return Notification.objects.filter(user=self.user, is_read=False).count()

    @database_sync_to_async
    def get_unread_message_count(self):
        from .models import Message
        return Message.objects.filter(recipient=self.user, is_read=False).count()

    @database_sync_to_async
    def mark_notification_read(self, notification_id):
        from .models import Notification
        if notification_id:
            Notification.objects.filter(
                id=notification_id, user=self.user
            ).update(is_read=True)

    @database_sync_to_async
    def mark_messages_read(self, allocation_id):
        from .models import Message
        if allocation_id:
            Message.objects.filter(
                recipient=self.user,
                allocation_id=allocation_id,
                is_read=False
            ).update(is_read=True)
