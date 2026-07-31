from django.db import models
from django.contrib.auth.models import AbstractUser
from django.utils import timezone
import uuid


class User(AbstractUser):
    ROLE_CHOICES = (
        ('admin', 'Administrator'),
        ('supervisor', 'Supervisor'),
        ('student', 'Student'),
    )
    role = models.CharField(max_length=20, choices=ROLE_CHOICES, default='student')
    student_id = models.CharField(max_length=50, unique=True, null=True, blank=True)
    phone = models.CharField(max_length=20, blank=True)
    department = models.CharField(max_length=100, blank=True)
    profile_pic = models.ImageField(upload_to='profile_pics/', null=True, blank=True)
    is_active = models.BooleanField(default=True)
    last_seen = models.DateTimeField(null=True, blank=True)

    def __str__(self):
        return f"{self.username} ({self.get_role_display()})"

    def get_unread_notification_count(self):
        return self.notifications.filter(is_read=False).count()


class SupervisorProfile(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='supervisor_profile')
    specialization = models.TextField(blank=True, help_text="Research areas, comma separated")
    max_students = models.PositiveIntegerField(default=5)
    bio = models.TextField(blank=True)
    qualifications = models.TextField(blank=True)
    available = models.BooleanField(default=True)

    def __str__(self):
        return f"Profile: {self.user.username}"

    @property
    def current_students(self):
        """Live count of active allocations — never stale."""
        return Allocation.objects.filter(supervisor=self.user, status='active').count()

    @property
    def remaining_capacity(self):
        return max(self.max_students - self.current_students, 0)

    @property
    def is_at_capacity(self):
        return self.current_students >= self.max_students


class Proposal(models.Model):
    STATUS_CHOICES = (
        ('draft', 'Draft'),
        ('submitted', 'Submitted'),
        ('under_review', 'Under Review'),
        ('approved', 'Approved'),
        ('rejected', 'Rejected'),
        ('revision_required', 'Revision Required'),
    )

    student = models.ForeignKey(
        User, on_delete=models.CASCADE,
        related_name='proposals',
        limit_choices_to={'role': 'student'}
    )
    title = models.CharField(max_length=500)
    abstract = models.TextField(blank=True)
    objectives = models.TextField(blank=True)
    methodology = models.TextField(blank=True)
    background = models.TextField(blank=True)
    expected_outcomes = models.TextField(blank=True)
    keywords = models.CharField(max_length=500, blank=True, help_text="Comma separated keywords")
    department = models.CharField(max_length=100, blank=True)
    program = models.CharField(max_length=100, blank=True)
    academic_year = models.CharField(max_length=20, blank=True)
    document = models.FileField(upload_to='proposals/', null=True, blank=True)
    status = models.CharField(max_length=30, choices=STATUS_CHOICES, default='draft')
    admin_comments = models.TextField(blank=True)
    submission_date = models.DateTimeField(null=True, blank=True)
    review_date = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.title[:100]

    def save(self, *args, **kwargs):
        if self.status == 'submitted' and not self.submission_date:
            self.submission_date = timezone.now()
        super().save(*args, **kwargs)


class Allocation(models.Model):
    STATUS_CHOICES = (
        ('active', 'Active'),
        ('completed', 'Completed'),
        ('terminated', 'Terminated'),
    )

    # A proposal can only ever have one allocation
    proposal = models.OneToOneField(
        Proposal, on_delete=models.CASCADE, related_name='allocation'
    )
    student = models.ForeignKey(
        User, on_delete=models.CASCADE,
        related_name='allocations_as_student',
        limit_choices_to={'role': 'student'}
    )
    supervisor = models.ForeignKey(
        User, on_delete=models.CASCADE,
        related_name='allocations_as_supervisor',
        limit_choices_to={'role': 'supervisor'}
    )
    allocated_by = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True,
        related_name='allocations_made'
    )
    # match_score is stored as a 0-1 float (e.g. 0.75 = 75%)
    match_score = models.FloatField(
        default=0.0,
        help_text="Cosine similarity score from chaotic allocation algorithm (0–1)"
    )
    allocation_date = models.DateTimeField(auto_now_add=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='active')
    notes = models.TextField(blank=True)

    def __str__(self):
        return f"{self.student.username} → {self.supervisor.username}"

    @property
    def match_score_pct(self):
        """Return match_score as an integer percentage (0-100)."""
        return int(self.match_score * 100)


class ProgressReport(models.Model):
    TYPE_CHOICES = (
        ('weekly', 'Weekly Report'),
        ('monthly', 'Monthly Report'),
        ('milestone', 'Milestone Report'),
        ('final', 'Final Report'),
        ('document', 'Document for Review'),
    )
    STATUS_CHOICES = (
        ('submitted', 'Submitted'),
        ('reviewed', 'Reviewed'),
        ('approved', 'Approved'),
    )

    allocation = models.ForeignKey(Allocation, on_delete=models.CASCADE, related_name='reports')
    student = models.ForeignKey(
        User, on_delete=models.CASCADE,
        related_name='reports',
        limit_choices_to={'role': 'student'}
    )
    report_type = models.CharField(max_length=20, choices=TYPE_CHOICES, default='document')
    title = models.CharField(max_length=500)
    content = models.TextField(blank=True, help_text="Description or notes")
    document = models.FileField(upload_to='reports/', null=True, blank=True)
    percentage_complete = models.IntegerField(default=0)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='submitted')
    supervisor_feedback = models.TextField(blank=True)
    supervisor_rating = models.IntegerField(
        null=True, blank=True,
        choices=[(i, i) for i in range(1, 6)]
    )
    submitted_at = models.DateTimeField(auto_now_add=True)
    reviewed_at = models.DateTimeField(null=True, blank=True)

    def __str__(self):
        return self.title[:100]


class Meeting(models.Model):
    TYPE_CHOICES = (
        ('physical', 'Physical'),
        ('virtual', 'Virtual'),
        ('phone', 'Phone Call'),
    )
    STATUS_CHOICES = (
        ('scheduled', 'Scheduled'),
        ('completed', 'Completed'),
        ('cancelled', 'Cancelled'),
    )

    allocation = models.ForeignKey(Allocation, on_delete=models.CASCADE, related_name='meetings')
    student = models.ForeignKey(User, on_delete=models.CASCADE, related_name='meetings_as_student')
    supervisor = models.ForeignKey(User, on_delete=models.CASCADE, related_name='meetings_as_supervisor')
    title = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    meeting_date = models.DateTimeField()
    location = models.CharField(max_length=200, blank=True)
    meeting_type = models.CharField(max_length=20, choices=TYPE_CHOICES, default='physical')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='scheduled')
    minutes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.title} - {self.meeting_date.strftime('%Y-%m-%d %H:%M')}"


class Milestone(models.Model):
    STATUS_CHOICES = (
        ('pending', 'Pending'),
        ('in_progress', 'In Progress'),
        ('completed', 'Completed'),
        ('overdue', 'Overdue'),
    )

    allocation = models.ForeignKey(Allocation, on_delete=models.CASCADE, related_name='milestones')
    title = models.CharField(max_length=300)
    description = models.TextField(blank=True)
    due_date = models.DateField()
    completed_date = models.DateField(null=True, blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    created_by = models.ForeignKey(User, on_delete=models.CASCADE, related_name='milestones_created')
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.title


class Notification(models.Model):
    TYPE_CHOICES = (
        ('info', 'Information'),
        ('success', 'Success'),
        ('warning', 'Warning'),
        ('danger', 'Danger'),
    )

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='notifications')
    title = models.CharField(max_length=200)
    message = models.TextField()
    notification_type = models.CharField(max_length=20, choices=TYPE_CHOICES, default='info')
    is_read = models.BooleanField(default=False)
    link = models.CharField(max_length=500, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return self.title


class AuditLog(models.Model):
    user = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='audit_logs')
    action = models.CharField(max_length=100)
    module = models.CharField(max_length=100, blank=True)
    description = models.TextField()
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        ts = self.created_at.strftime('%Y-%m-%d %H:%M') if self.created_at else '?'
        return f"{self.user} - {self.action} - {ts}"


class SupervisorNote(models.Model):
    """Private supervision log entry — only the supervisor can see these."""
    allocation = models.ForeignKey(
        Allocation, on_delete=models.CASCADE, related_name='supervisor_notes'
    )
    supervisor = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name='notes_written'
    )
    content = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"Note by {self.supervisor.username} on {self.created_at.strftime('%Y-%m-%d')}"


class Message(models.Model):
    """
    Direct message between a supervisor and a student,
    scoped to their supervision allocation.
    """
    allocation = models.ForeignKey(
        Allocation, on_delete=models.CASCADE, related_name='messages'
    )
    sender = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name='sent_messages'
    )
    recipient = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name='received_messages'
    )
    content = models.TextField()
    is_read = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['created_at']

    def __str__(self):
        return f"{self.sender.username} → {self.recipient.username}: {self.content[:40]}"
