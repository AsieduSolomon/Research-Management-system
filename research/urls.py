from django.urls import path
from . import views

urlpatterns = [
    # Authentication
    path('', views.home, name='home'),
    path('register/', views.register, name='register'),
    path('login/', views.user_login, name='login'),
    path('logout/', views.user_logout, name='logout'),
    path('dashboard/', views.dashboard, name='dashboard'),

    # Admin
    path('dashboard/admin/', views.admin_dashboard, name='admin_dashboard'),
    path('dashboard/admin/users/', views.admin_users, name='admin_users'),
    path('dashboard/admin/users/create/', views.admin_user_create, name='admin_user_create'),
    path('dashboard/admin/users/<int:user_id>/edit/', views.admin_user_edit, name='admin_user_edit'),
    path('dashboard/admin/user/toggle/<int:user_id>/', views.admin_user_toggle, name='admin_user_toggle'),
    path('dashboard/admin/proposals/', views.admin_proposals, name='admin_proposals'),
    path('dashboard/admin/proposals/<int:proposal_id>/review/', views.admin_proposal_review, name='admin_proposal_review'),
    path('dashboard/admin/allocations/', views.admin_allocations, name='admin_allocations'),
    path('dashboard/admin/chaotic-allocation/', views.admin_chaotic_allocation, name='admin_chaotic_allocation'),
    path('dashboard/admin/reports/', views.admin_reports, name='admin_reports'),
    path('dashboard/admin/audit-log/', views.admin_audit_log, name='admin_audit_log'),

    # Student
    path('student/dashboard/', views.student_dashboard, name='student_dashboard'),
    path('student/proposals/', views.student_proposals, name='student_proposals'),
    path('student/proposals/<int:proposal_id>/edit/', views.student_edit_proposal, name='student_edit_proposal'),
    path('student/proposals/<int:proposal_id>/delete/', views.student_delete_proposal, name='student_delete_proposal'),
    path('student/documents/', views.student_documents, name='student_documents'),

    # Supervisor
    path('supervisor/dashboard/', views.supervisor_dashboard, name='supervisor_dashboard'),
    path('supervisor/students/', views.supervisor_students, name='supervisor_students'),
    path('supervisor/students/<int:student_id>/', views.supervisor_student_detail, name='supervisor_student_detail'),
    path('supervisor/students/<int:student_id>/milestones/', views.supervisor_milestones, name='supervisor_milestones'),
    path('supervisor/documents/', views.supervisor_documents, name='supervisor_documents'),
    path('supervisor/progress/', views.supervisor_progress_overview, name='supervisor_progress_overview'),
    path('supervisor/meetings/<int:meeting_id>/update/', views.supervisor_meeting_update, name='supervisor_meeting_update'),

    # Shared
    path('meetings/', views.meetings, name='meetings'),
    path('notifications/', views.notifications, name='notifications'),
    path('profile/', views.profile, name='profile'),

    # Chat / Messaging
    path('chat/', views.conversation_list, name='conversation_list'),
    path('chat/<int:allocation_id>/', views.conversation, name='conversation'),
    path('api/unread-messages/', views.get_unread_message_count, name='api_unread_messages'),

    # AJAX
    path('api/notification-count/', views.get_notification_count, name='api_notification_count'),
    path('api/mark-notification-read/', views.mark_notification_read_ajax, name='api_mark_notification_read'),
    path('api/recent-notifications/', views.get_recent_notifications, name='api_recent_notifications'),
]
