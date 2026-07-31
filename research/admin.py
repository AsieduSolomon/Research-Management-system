from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from .models import (
    User, SupervisorProfile, Proposal, Allocation,
    ProgressReport, Meeting, Milestone, Notification, AuditLog, SupervisorNote, Message
)

class CustomUserAdmin(UserAdmin):
    list_display = ('username', 'email', 'first_name', 'last_name', 'role', 'student_id', 'department', 'is_active', 'last_login')
    list_filter = ('role', 'is_active', 'department')
    search_fields = ('username', 'email', 'first_name', 'last_name', 'student_id')
    ordering = ('-date_joined',)
    
    fieldsets = UserAdmin.fieldsets + (
        ('Additional Info', {'fields': ('role', 'student_id', 'phone', 'department', 'profile_pic', 'last_seen')}),
    )
    
    add_fieldsets = UserAdmin.add_fieldsets + (
        ('Additional Info', {'fields': ('role', 'student_id', 'phone', 'department')}),
    )


class SupervisorProfileAdmin(admin.ModelAdmin):
    list_display = ('user', 'specialization', 'max_students', 'current_students', 'available')
    list_filter = ('available', 'max_students')
    search_fields = ('user__username', 'user__email', 'specialization')
    raw_id_fields = ('user',)


class ProposalAdmin(admin.ModelAdmin):
    list_display = ('title', 'student', 'status', 'submission_date', 'review_date')
    list_filter = ('status', 'department', 'program', 'academic_year')
    search_fields = ('title', 'abstract', 'keywords', 'student__username', 'student__email')
    raw_id_fields = ('student',)
    readonly_fields = ('created_at', 'updated_at')
    
    fieldsets = (
        ('Basic Information', {
            'fields': ('student', 'title', 'status', 'keywords', 'department', 'program', 'academic_year')
        }),
        ('Research Content', {
            'fields': ('abstract', 'objectives', 'methodology', 'background', 'expected_outcomes')
        }),
        ('Review Information', {
            'fields': ('admin_comments', 'submission_date', 'review_date')
        }),
        ('File', {
            'fields': ('document',)
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )


class AllocationAdmin(admin.ModelAdmin):
    list_display = ('proposal', 'student', 'supervisor', 'match_score', 'status', 'allocation_date')
    list_filter = ('status', 'allocation_date')
    search_fields = ('proposal__title', 'student__username', 'supervisor__username')
    raw_id_fields = ('proposal', 'student', 'supervisor', 'allocated_by')


class ProgressReportAdmin(admin.ModelAdmin):
    list_display = ('title', 'student', 'report_type', 'status', 'submitted_at', 'reviewed_at')
    list_filter = ('report_type', 'status', 'submitted_at')
    search_fields = ('title', 'content', 'student__username')
    raw_id_fields = ('allocation', 'student')


class MeetingAdmin(admin.ModelAdmin):
    list_display = ('title', 'student', 'supervisor', 'meeting_date', 'status', 'meeting_type')
    list_filter = ('status', 'meeting_type', 'meeting_date')
    search_fields = ('title', 'student__username', 'supervisor__username')
    raw_id_fields = ('allocation', 'student', 'supervisor')


class MilestoneAdmin(admin.ModelAdmin):
    list_display = ('title', 'allocation', 'due_date', 'status')
    list_filter = ('status', 'due_date')
    search_fields = ('title', 'description')
    raw_id_fields = ('allocation', 'created_by')


class NotificationAdmin(admin.ModelAdmin):
    list_display = ('title', 'user', 'notification_type', 'is_read', 'created_at')
    list_filter = ('notification_type', 'is_read', 'created_at')
    search_fields = ('title', 'message', 'user__username')
    raw_id_fields = ('user',)


class AuditLogAdmin(admin.ModelAdmin):
    list_display = ('user', 'action', 'module', 'created_at')
    list_filter = ('action', 'module', 'created_at')
    search_fields = ('user__username', 'action', 'description')
    readonly_fields = ('created_at',)
    raw_id_fields = ('user',)


# Register all models with the admin site
admin.site.register(User, CustomUserAdmin)
admin.site.register(SupervisorProfile, SupervisorProfileAdmin)
admin.site.register(Proposal, ProposalAdmin)
admin.site.register(Allocation, AllocationAdmin)
admin.site.register(ProgressReport, ProgressReportAdmin)
admin.site.register(Meeting, MeetingAdmin)
admin.site.register(Milestone, MilestoneAdmin)
admin.site.register(Notification, NotificationAdmin)
admin.site.register(AuditLog, AuditLogAdmin)

class SupervisorNoteAdmin(admin.ModelAdmin):
    list_display = ('supervisor', 'allocation', 'created_at')
    list_filter = ('created_at',)
    search_fields = ('supervisor__username', 'content')
    raw_id_fields = ('allocation', 'supervisor')
    readonly_fields = ('created_at', 'updated_at')


admin.site.register(SupervisorNote, SupervisorNoteAdmin)


class MessageAdmin(admin.ModelAdmin):
    list_display = ('sender', 'recipient', 'allocation', 'is_read', 'created_at')
    list_filter  = ('is_read', 'created_at')
    search_fields = ('sender__username', 'recipient__username', 'content')
    raw_id_fields = ('allocation', 'sender', 'recipient')
    readonly_fields = ('created_at',)


admin.site.register(Message, MessageAdmin)
