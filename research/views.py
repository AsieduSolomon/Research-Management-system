from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.db.models import Count, Q, Avg
from django.utils import timezone
from django.core.paginator import Paginator
from django.http import JsonResponse, HttpResponseForbidden
from django.views.decorators.http import require_http_methods
from django.views.decorators.csrf import csrf_protect
from functools import wraps
import json
import os

from .models import (
    User, SupervisorProfile, Proposal, Allocation,
    ProgressReport, Meeting, Milestone, Notification, AuditLog, SupervisorNote, Message
)
from .forms import (
    UserRegistrationForm, ProposalForm, DocumentSubmissionForm,
    ReviewForm, MeetingForm, MilestoneForm
)
from .utils import (
    extract_text_from_file, generate_keywords_from_text,
    get_chaotic_allocation, compute_interest_match_matrix
)


# ==================== CUSTOM DECORATORS ====================

def role_required(*roles):
    """Decorator: ensure the logged-in user has one of the given roles."""
    def decorator(view_func):
        @wraps(view_func)
        def wrapper(request, *args, **kwargs):
            if not request.user.is_authenticated:
                messages.warning(request, 'Please log in to access this page.')
                return redirect('login')
            if request.user.role not in roles and not request.user.is_superuser:
                messages.error(request, 'You do not have permission to access this page.')
                return redirect('dashboard')
            return view_func(request, *args, **kwargs)
        return wrapper
    return decorator


def ajax_required(view_func):
    """Decorator: only allow XHR requests."""
    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        if not request.headers.get('x-requested-with') == 'XMLHttpRequest':
            return HttpResponseForbidden('AJAX request required.')
        return view_func(request, *args, **kwargs)
    return wrapper


# ==================== HELPERS ====================

def _get_client_ip(request):
    xff = request.META.get('HTTP_X_FORWARDED_FOR')
    if xff:
        return xff.split(',')[0].strip()
    return request.META.get('REMOTE_ADDR', '')


# ==================== AUTHENTICATION VIEWS ====================

def home(request):
    """Landing page."""
    if request.user.is_authenticated:
        return redirect('dashboard')
    return render(request, 'research/home.html')


def register(request):
    """User self-registration (students only)."""
    if request.user.is_authenticated:
        return redirect('dashboard')

    if request.method == 'POST':
        form = UserRegistrationForm(request.POST)
        if form.is_valid():
            user = form.save(commit=False)
            user.role = 'student'
            user.save()

            Notification.objects.create(
                user=user,
                title='Welcome to STU Research Portal! 🎓',
                message='Your account has been created successfully. You can now submit research proposals and track your progress.',
                notification_type='success'
            )

            login(request, user)
            messages.success(request, f'Welcome {user.first_name or user.username}! Your account has been created successfully.')
            return redirect('student_dashboard')
        else:
            for field, errors in form.errors.items():
                for error in errors:
                    messages.error(request, f'{field.replace("_", " ").title()}: {error}')
    else:
        form = UserRegistrationForm()

    return render(request, 'research/register.html', {'form': form})


@csrf_protect
def user_login(request):
    """Login with email + password."""
    if request.user.is_authenticated:
        return redirect('dashboard')

    if request.method == 'POST':
        email = request.POST.get('username', '').strip()
        password = request.POST.get('password', '')

        if not email or not password:
            messages.error(request, 'Please enter both email and password.')
            return render(request, 'research/login.html')

        # Look up user by email; handle multiple matches gracefully
        try:
            user_obj = User.objects.get(email=email)
        except User.DoesNotExist:
            messages.error(request, 'No account found with this email address.')
            return render(request, 'research/login.html')
        except User.MultipleObjectsReturned:
            messages.error(request, 'Multiple accounts share this email. Contact admin.')
            return render(request, 'research/login.html')

        user = authenticate(request, username=user_obj.username, password=password)
        if user is not None:
            if not user.is_active:
                messages.error(request, 'Your account has been deactivated. Contact admin.')
                return render(request, 'research/login.html')

            login(request, user)
            user.last_seen = timezone.now()
            user.save(update_fields=['last_seen'])

            AuditLog.objects.create(
                user=user,
                action='LOGIN',
                module='Authentication',
                description=f'User {user.email} logged in',
                ip_address=_get_client_ip(request)
            )

            messages.success(request, f'Welcome back, {user.get_full_name() or user.username}!')
            redirect_map = {
                'admin': 'admin_dashboard',
                'supervisor': 'supervisor_dashboard',
                'student': 'student_dashboard',
            }
            return redirect(redirect_map.get(user.role, 'dashboard'))
        else:
            messages.error(request, 'Invalid email or password.')

    return render(request, 'research/login.html')


def user_logout(request):
    """Logout and redirect to login page."""
    if request.user.is_authenticated:
        AuditLog.objects.create(
            user=request.user,
            action='LOGOUT',
            module='Authentication',
            description=f'User {request.user.email} logged out',
            ip_address=_get_client_ip(request)
        )
        logout(request)
        messages.success(request, 'You have been logged out successfully.')
    return redirect('login')


@login_required
def dashboard(request):
    """Role-based dashboard router."""
    role_redirect = {
        'admin': 'admin_dashboard',
        'supervisor': 'supervisor_dashboard',
        'student': 'student_dashboard',
    }
    return redirect(role_redirect.get(request.user.role, 'home'))


# ==================== ADMIN VIEWS ====================

@login_required
@role_required('admin')
def admin_dashboard(request):
    """Admin dashboard with statistics."""
    today = timezone.now().date()

    stats = {
        'total_users': User.objects.count(),
        'total_students': User.objects.filter(role='student').count(),
        'total_supervisors': User.objects.filter(role='supervisor').count(),
        'total_proposals': Proposal.objects.count(),
        'pending_proposals': Proposal.objects.filter(status__in=['submitted', 'under_review']).count(),
        'approved_proposals': Proposal.objects.filter(status='approved').count(),
        'rejected_proposals': Proposal.objects.filter(status='rejected').count(),
        'active_allocations': Allocation.objects.filter(status='active').count(),
        'total_reports': ProgressReport.objects.count(),
        'pending_reviews': ProgressReport.objects.filter(status='submitted').count(),
        'total_meetings': Meeting.objects.count(),
        'upcoming_meetings': Meeting.objects.filter(
            meeting_date__gte=timezone.now(), status='scheduled'
        ).count(),
        'completion_rate': 0,
    }

    total = stats['total_proposals']
    if total > 0:
        stats['completion_rate'] = int((stats['approved_proposals'] / total) * 100)

    monthly_proposals = (
        Proposal.objects
        .filter(submission_date__year=today.year)
        .values('submission_date__month')
        .annotate(count=Count('id'))
        .order_by('submission_date__month')
    )

    # Recent proposals — this is what the dashboard template iterates over
    recent_proposals = (
        Proposal.objects
        .select_related('student')
        .order_by('-created_at')[:10]
    )

    proposals_by_status = list(
        Proposal.objects.values('status').annotate(count=Count('id'))
    )
    proposals_by_department = list(
        Proposal.objects
        .exclude(department='')
        .values('department')
        .annotate(count=Count('id'))
        .order_by('-count')[:10]
    )

    context = {
        'stats': stats,
        'monthly_proposals': monthly_proposals,
        'recent_proposals': recent_proposals,
        'proposals_by_status': proposals_by_status,
        'proposals_by_department': proposals_by_department,
        'section': 'dashboard',
    }
    return render(request, 'research/admin/dashboard.html', context)


@login_required
@role_required('admin')
def admin_users(request):
    """List all users with filtering and pagination."""
    users = User.objects.all().order_by('-date_joined')

    role_filter = request.GET.get('role', '')
    status_filter = request.GET.get('status', '')
    search_query = request.GET.get('search', '')

    if role_filter:
        users = users.filter(role=role_filter)
    if status_filter == 'active':
        users = users.filter(is_active=True)
    elif status_filter == 'inactive':
        users = users.filter(is_active=False)
    if search_query:
        users = users.filter(
            Q(username__icontains=search_query) |
            Q(email__icontains=search_query) |
            Q(first_name__icontains=search_query) |
            Q(last_name__icontains=search_query) |
            Q(student_id__icontains=search_query)
        )

    total_count = users.count()
    paginator = Paginator(users, 20)
    page_obj = paginator.get_page(request.GET.get('page'))

    context = {
        'page_obj': page_obj,
        'role_filter': role_filter,
        'status_filter': status_filter,
        'search_query': search_query,
        'total_count': total_count,
        'section': 'users',
    }
    return render(request, 'research/admin/users.html', context)


@login_required
@role_required('admin')
def admin_user_create(request):
    """Create a new user."""
    if request.method == 'POST':
        form = UserRegistrationForm(request.POST)
        if form.is_valid():
            user = form.save(commit=False)
            role = request.POST.get('role', 'student')
            user.role = role
            user.save()

            if role == 'supervisor':
                try:
                    max_students = int(request.POST.get('max_students', 5))
                except (ValueError, TypeError):
                    max_students = 5
                SupervisorProfile.objects.get_or_create(
                    user=user,
                    defaults={
                        'specialization': request.POST.get('specialization', ''),
                        'max_students': max_students,
                    }
                )

            AuditLog.objects.create(
                user=request.user,
                action='CREATE_USER',
                module='Admin',
                description=f'Created user: {user.username} ({role})',
                ip_address=_get_client_ip(request)
            )
            messages.success(request, f'User {user.username} created successfully.')
            return redirect('admin_users')
        else:
            for field, errors in form.errors.items():
                for error in errors:
                    messages.error(request, error)
    else:
        form = UserRegistrationForm()

    context = {'form': form, 'section': 'users', 'is_edit': False}
    return render(request, 'research/admin/user_form.html', context)


@login_required
@role_required('admin')
def admin_user_edit(request, user_id):
    """Edit an existing user."""
    edit_user = get_object_or_404(User, id=user_id)

    if request.method == 'POST':
        edit_user.first_name = request.POST.get('first_name', '')
        edit_user.last_name = request.POST.get('last_name', '')
        edit_user.email = request.POST.get('email', '')
        edit_user.department = request.POST.get('department', '')
        edit_user.phone = request.POST.get('phone', '')
        edit_user.is_active = request.POST.get('is_active') == 'on'

        new_role = request.POST.get('role', edit_user.role)
        edit_user.role = new_role

        edit_user.save()

        if new_role == 'supervisor':
            try:
                max_students = int(request.POST.get('max_students', 5))
            except (ValueError, TypeError):
                max_students = 5
            profile, _ = SupervisorProfile.objects.get_or_create(user=edit_user)
            profile.specialization = request.POST.get('specialization', profile.specialization)
            profile.max_students = max_students
            profile.bio = request.POST.get('bio', profile.bio)
            profile.qualifications = request.POST.get('qualifications', profile.qualifications)
            profile.save()

        AuditLog.objects.create(
            user=request.user,
            action='EDIT_USER',
            module='Admin',
            description=f'Edited user: {edit_user.username}',
            ip_address=_get_client_ip(request)
        )
        messages.success(request, f'User {edit_user.username} updated successfully.')
        return redirect('admin_users')

    context = {'edit_user': edit_user, 'section': 'users', 'is_edit': True}
    return render(request, 'research/admin/user_form.html', context)


@login_required
@role_required('admin')
def admin_user_toggle(request, user_id):
    """Toggle user active status."""
    user = get_object_or_404(User, id=user_id)

    # Prevent admin from deactivating themselves
    if user == request.user:
        if request.headers.get('x-requested-with') == 'XMLHttpRequest':
            return JsonResponse({'status': 'error', 'message': 'Cannot deactivate yourself.'}, status=400)
        messages.error(request, 'You cannot deactivate your own account.')
        return redirect('admin_users')

    user.is_active = not user.is_active
    user.save(update_fields=['is_active'])

    AuditLog.objects.create(
        user=request.user,
        action='TOGGLE_USER',
        module='Admin',
        description=f'Toggled user {user.username} to {"active" if user.is_active else "inactive"}',
        ip_address=_get_client_ip(request)
    )

    if request.headers.get('x-requested-with') == 'XMLHttpRequest':
        return JsonResponse({'status': 'success', 'is_active': user.is_active})

    messages.success(request, f'User {user.username} has been {"activated" if user.is_active else "deactivated"}.')
    return redirect('admin_users')


@login_required
@role_required('admin')
def admin_proposals(request):
    """List all proposals with filtering."""
    proposals = Proposal.objects.select_related('student').order_by('-created_at')

    status_filter = request.GET.get('status', '')
    department_filter = request.GET.get('department', '')
    search_query = request.GET.get('search', '')

    if status_filter:
        proposals = proposals.filter(status=status_filter)
    if department_filter:
        proposals = proposals.filter(department=department_filter)
    if search_query:
        proposals = proposals.filter(
            Q(title__icontains=search_query) |
            Q(abstract__icontains=search_query) |
            Q(student__first_name__icontains=search_query) |
            Q(student__last_name__icontains=search_query) |
            Q(student__username__icontains=search_query)
        )

    departments = (
        Proposal.objects
        .exclude(department='')
        .values_list('department', flat=True)
        .distinct()
        .order_by('department')
    )
    total_count = proposals.count()

    paginator = Paginator(proposals, 20)
    page_obj = paginator.get_page(request.GET.get('page'))

    context = {
        'page_obj': page_obj,
        'status_filter': status_filter,
        'department_filter': department_filter,
        'search_query': search_query,
        'departments': departments,
        'total_count': total_count,
        'section': 'proposals',
    }
    return render(request, 'research/admin/proposals.html', context)


@login_required
@role_required('admin')
def admin_proposal_review(request, proposal_id):
    """Review and update a proposal's status."""
    proposal = get_object_or_404(Proposal, id=proposal_id)

    if request.method == 'POST':
        status = request.POST.get('status', '').strip()
        valid_statuses = [s for s, _ in Proposal.STATUS_CHOICES]
        if status not in valid_statuses:
            messages.error(request, 'Invalid status selected.')
            return redirect('admin_proposal_review', proposal_id=proposal_id)

        comments = request.POST.get('comments', '')
        proposal.status = status
        proposal.admin_comments = comments
        proposal.review_date = timezone.now()
        proposal.save()

        notification_map = {
            'approved': ('Proposal Approved! 🎉', 'Your proposal has been approved. A supervisor will be assigned soon.', 'success'),
            'rejected': ('Proposal Rejected', f'Your proposal has been rejected. Feedback: {comments}', 'danger'),
            'revision_required': ('Revision Required', f'Please revise your proposal. Comments: {comments}', 'warning'),
            'under_review': ('Proposal Under Review', 'Your proposal is being reviewed by the admin.', 'info'),
        }

        if status in notification_map:
            title, msg, ntype = notification_map[status]
            Notification.objects.create(
                user=proposal.student,
                title=title,
                message=msg,
                notification_type=ntype,
                link='/student/proposals/'
            )

        AuditLog.objects.create(
            user=request.user,
            action='REVIEW_PROPOSAL',
            module='Admin',
            description=f'Set proposal "{proposal.title[:60]}" to {status}',
            ip_address=_get_client_ip(request)
        )

        messages.success(request, f'Proposal marked as {status.replace("_", " ")}.')

        if request.headers.get('x-requested-with') == 'XMLHttpRequest':
            return JsonResponse({'status': 'success', 'proposal_status': status})

        return redirect('admin_proposals')

    context = {'proposal': proposal, 'section': 'proposals'}
    return render(request, 'research/admin/proposal_review.html', context)


@login_required
@role_required('admin')
def admin_allocations(request):
    """Manage supervisor allocations."""
    # Proposals that are approved and do NOT yet have an allocation.
    # With a OneToOneField reverse relation, the correct filter is:
    #   exclude(pk__in=Allocation.objects.values('proposal_id'))
    # because Django's isnull on a reverse OneToOne can behave unexpectedly.
    allocated_proposal_ids = Allocation.objects.values_list('proposal_id', flat=True)
    approved_proposals = list(
        Proposal.objects
        .filter(status='approved')
        .exclude(pk__in=allocated_proposal_ids)
        .select_related('student')
        .order_by('-created_at')
    )

    # Evaluate to a list so we can safely annotate each supervisor object
    supervisors = list(
        User.objects
        .filter(role='supervisor', is_active=True)
        .select_related('supervisor_profile')
        .order_by('first_name', 'last_name')
    )
    allocations = (
        Allocation.objects
        .select_related('student', 'supervisor', 'proposal', 'allocated_by',
                        'supervisor__supervisor_profile')
        .order_by('-allocation_date')
    )

    # Annotate each supervisor with live capacity data (safe on a list)
    for sup in supervisors:
        if hasattr(sup, 'supervisor_profile'):
            sup.current_count = sup.supervisor_profile.current_students
            sup.max_capacity = sup.supervisor_profile.max_students
        else:
            sup.current_count = Allocation.objects.filter(supervisor=sup, status='active').count()
            sup.max_capacity = 5

    if request.method == 'POST' and 'manual_allocate' in request.POST:
        proposal_id = request.POST.get('proposal_id')
        supervisor_id = request.POST.get('supervisor_id')
        notes = request.POST.get('notes', '')

        proposal = get_object_or_404(Proposal, id=proposal_id, status='approved')
        supervisor = get_object_or_404(User, id=supervisor_id, role='supervisor')

        # Guard against duplicate allocation
        if Allocation.objects.filter(proposal=proposal).exists():
            messages.error(request, 'This proposal already has an allocation.')
            return redirect('admin_allocations')

        # Check capacity via the live property
        if hasattr(supervisor, 'supervisor_profile'):
            if supervisor.supervisor_profile.is_at_capacity:
                messages.error(request, f'{supervisor.get_full_name()} has reached maximum capacity.')
                return redirect('admin_allocations')

        Allocation.objects.create(
            proposal=proposal,
            student=proposal.student,
            supervisor=supervisor,
            allocated_by=request.user,
            notes=notes,
            match_score=0.0
        )

        Notification.objects.create(
            user=proposal.student,
            title='Supervisor Assigned! 🎉',
            message=f'You have been assigned to {supervisor.get_full_name()} as your supervisor.',
            notification_type='success',
            link='/student/dashboard/'
        )
        Notification.objects.create(
            user=supervisor,
            title='New Student Assigned',
            message=f'You have been assigned to supervise {proposal.student.get_full_name()} for: {proposal.title[:60]}',
            notification_type='info',
            link='/supervisor/dashboard/'
        )

        AuditLog.objects.create(
            user=request.user,
            action='ALLOCATE_SUPERVISOR',
            module='Admin',
            description=f'Allocated {proposal.student.username} to {supervisor.username}',
            ip_address=_get_client_ip(request)
        )

        messages.success(request, 'Supervisor allocated successfully.')
        return redirect('admin_allocations')

    context = {
        'approved_proposals': approved_proposals,
        'supervisors': supervisors,
        'allocations': allocations,
        'section': 'allocations',
    }
    return render(request, 'research/admin/allocations.html', context)


@login_required
@role_required('admin')
@require_http_methods(['POST'])
def admin_chaotic_allocation(request):
    """Run the chaotic allocation algorithm for all unallocated approved proposals."""
    allocated_ids = Allocation.objects.values_list('proposal_id', flat=True)
    unallocated = list(
        Proposal.objects
        .filter(status='approved')
        .exclude(pk__in=allocated_ids)
        .select_related('student')
    )

    if not unallocated:
        messages.warning(request, 'No unallocated approved proposals found.')
        return redirect('admin_allocations')

    supervisors = list(
        User.objects
        .filter(role='supervisor', is_active=True)
        .select_related('supervisor_profile')
    )

    # Only include supervisors who still have capacity
    available_sups = []
    supervisor_capacities = {}
    for s in supervisors:
        if hasattr(s, 'supervisor_profile'):
            profile = s.supervisor_profile
            remaining = profile.remaining_capacity
        else:
            existing = Allocation.objects.filter(supervisor=s, status='active').count()
            remaining = max(5 - existing, 0)
        if remaining > 0:
            available_sups.append(s)
            supervisor_capacities[s.id] = remaining

    if not available_sups:
        messages.error(request, 'No available supervisors with remaining capacity.')
        return redirect('admin_allocations')

    proposal_ids = [p.id for p in unallocated]
    student_ids = [p.student.id for p in unallocated]
    supervisor_ids = [s.id for s in available_sups]

    match_matrix = compute_interest_match_matrix(student_ids, supervisor_ids)

    allocation_result = get_chaotic_allocation(
        proposal_ids, student_ids, supervisor_ids,
        supervisor_capacities, match_matrix
    )

    # Build lookup maps for O(1) access
    proposal_map = {p.id: p for p in unallocated}
    sup_map = {s.id: s for s in available_sups}

    allocated_count = 0
    for prop_id, student_id, sup_id, score in allocation_result:
        proposal = proposal_map.get(prop_id)
        supervisor = sup_map.get(sup_id)
        if not proposal or not supervisor:
            continue

        # Defensive: skip if somehow already allocated in this run
        if Allocation.objects.filter(proposal=proposal).exists():
            continue

        Allocation.objects.create(
            proposal=proposal,
            student=proposal.student,
            supervisor=supervisor,
            allocated_by=request.user,
            notes=f'Chaotic allocation (match score: {score:.2f})',
            match_score=score
        )

        Notification.objects.create(
            user=proposal.student,
            title='Supervisor Assigned! 🎯',
            message=(
                f'You have been allocated to {supervisor.get_full_name()} via intelligent matching. '
                f'Match quality: {score:.0%}'
            ),
            notification_type='success',
            link='/student/dashboard/'
        )
        Notification.objects.create(
            user=supervisor,
            title='New Student Assigned (Auto-Match)',
            message=(
                f'{proposal.student.get_full_name()} has been allocated to you '
                f'with match score {score:.0%}.'
            ),
            notification_type='info',
            link='/supervisor/dashboard/'
        )
        allocated_count += 1

    AuditLog.objects.create(
        user=request.user,
        action='CHAOTIC_ALLOCATION',
        module='Admin',
        description=f'Chaotic allocation assigned {allocated_count} of {len(unallocated)} students to supervisors',
        ip_address=_get_client_ip(request)
    )

    if allocated_count == 0:
        messages.warning(request, 'Chaotic allocation ran but no assignments were made (check supervisor capacity).')
    else:
        messages.success(request, f'Chaotic allocation completed! {allocated_count} student(s) allocated.')
    return redirect('admin_allocations')


@login_required
@role_required('admin')
def admin_reports(request):
    """Generate and export reports."""
    from datetime import timedelta

    date_range = request.GET.get('date_range', 'all')
    today = timezone.now().date()

    if date_range == 'week':
        start_date = today - timedelta(days=7)
    elif date_range == 'month':
        start_date = today - timedelta(days=30)
    elif date_range == 'year':
        start_date = today - timedelta(days=365)
    else:
        start_date = None

    proposals = Proposal.objects.all()
    if start_date:
        proposals = proposals.filter(created_at__date__gte=start_date)

    summary = {
        'total_proposals': proposals.count(),
        'approved': proposals.filter(status='approved').count(),
        'rejected': proposals.filter(status='rejected').count(),
        'pending': proposals.filter(status__in=['submitted', 'under_review']).count(),
        'total_students': User.objects.filter(role='student').count(),
        'total_supervisors': User.objects.filter(role='supervisor').count(),
        'active_allocations': Allocation.objects.filter(status='active').count(),
        'completion_rate': 0,
    }
    if summary['total_proposals'] > 0:
        summary['completion_rate'] = int((summary['approved'] / summary['total_proposals']) * 100)

    if request.GET.get('export') == 'csv':
        import csv
        from django.http import HttpResponse
        from django.utils import timezone as tz

        response = HttpResponse(content_type='text/csv')
        response['Content-Disposition'] = (
            f'attachment; filename="proposals_report_{tz.now().strftime("%Y%m%d")}.csv"'
        )
        writer = csv.writer(response)
        writer.writerow(['ID', 'Title', 'Student', 'Department', 'Status',
                         'Submission Date', 'Review Date'])
        for p in proposals.select_related('student')[:5000]:
            writer.writerow([
                p.id, p.title,
                p.student.get_full_name() or p.student.username,
                p.department, p.status,
                p.submission_date, p.review_date
            ])
        return response

    context = {
        'summary': summary,
        'date_range': date_range,
        'section': 'reports',
    }
    return render(request, 'research/admin/reports.html', context)


@login_required
@role_required('admin')
def admin_audit_log(request):
    """View audit log with filtering."""
    logs = AuditLog.objects.select_related('user').order_by('-created_at')

    action_filter = request.GET.get('action', '')
    user_filter = request.GET.get('user', '')

    if action_filter:
        logs = logs.filter(action=action_filter)
    if user_filter:
        logs = logs.filter(user__username__icontains=user_filter)

    paginator = Paginator(logs, 50)
    page_obj = paginator.get_page(request.GET.get('page'))

    actions = AuditLog.objects.values_list('action', flat=True).distinct().order_by('action')

    context = {
        'page_obj': page_obj,
        'actions': actions,
        'action_filter': action_filter,
        'user_filter': user_filter,
        'section': 'audit',
    }
    return render(request, 'research/admin/audit_log.html', context)


# ==================== STUDENT VIEWS ====================

@login_required
@role_required('student')
def student_dashboard(request):
    """Student dashboard overview."""
    user = request.user
    proposals = Proposal.objects.filter(student=user).order_by('-created_at')
    allocation = Allocation.objects.filter(student=user, status='active').first()

    all_reports = ProgressReport.objects.filter(student=user).order_by('-submitted_at')
    reports = all_reports[:5]

    meetings = Meeting.objects.filter(
        student=user,
        meeting_date__gte=timezone.now(),
        status='scheduled'
    ).order_by('meeting_date')[:5]

    # Stats
    submitted_proposals = proposals.filter(
        status__in=['submitted', 'under_review', 'approved', 'rejected', 'revision_required']
    ).count()

    progress = 0
    if allocation:
        reviewed_count = ProgressReport.objects.filter(
            allocation=allocation, status__in=['reviewed', 'approved']
        ).count()
        progress = min(reviewed_count * 10, 100)

    pending_proposals = proposals.filter(
        status__in=['draft', 'submitted', 'under_review', 'revision_required']
    ).count()
    pending_feedback = all_reports.filter(status='submitted').count()

    context = {
        'proposals': proposals,
        'submitted_proposals': submitted_proposals,
        'allocation': allocation,
        'reports': reports,
        'meetings': meetings,
        'progress': progress,
        'pending_proposals': pending_proposals,
        'pending_feedback': pending_feedback,
        'unread_notifications': user.get_unread_notification_count(),
        'section': 'dashboard',
    }
    return render(request, 'research/student/dashboard.html', context)


@login_required
@role_required('student')
def student_proposals(request):
    """Student proposal management."""
    user = request.user

    if request.method == 'POST':
        form = ProposalForm(request.POST, request.FILES)
        if form.is_valid():
            proposal = form.save(commit=False)
            proposal.student = user

            # Auto-extract keywords from uploaded document
            if not proposal.keywords and 'document' in request.FILES:
                # File not yet saved — save first, then extract
                proposal.save()
                file_path = proposal.document.path
                ext = os.path.splitext(proposal.document.name)[1].lower()
                text = extract_text_from_file(file_path, ext)
                if text:
                    proposal.keywords = generate_keywords_from_text(text)

            if 'save_draft' in request.POST:
                proposal.status = 'draft'
                proposal.save()
                messages.success(request, 'Proposal saved as draft. You can edit and submit later.')
            else:
                proposal.status = 'submitted'
                proposal.submission_date = timezone.now()
                proposal.save()

                for admin in User.objects.filter(role='admin', is_active=True):
                    Notification.objects.create(
                        user=admin,
                        title='New Proposal Submitted',
                        message=f'{user.get_full_name() or user.username} submitted: "{proposal.title[:50]}"',
                        notification_type='info',
                        link='/dashboard/admin/proposals/'
                    )
                messages.success(request, 'Proposal submitted for review! You will be notified when reviewed.')

            return redirect('student_proposals')
        else:
            for error in form.errors.values():
                messages.error(request, str(error[0]))
    else:
        form = ProposalForm()

    proposals = Proposal.objects.filter(student=user).order_by('-created_at')
    context = {
        'form': form,
        'proposals': proposals,
        'section': 'proposals',
    }
    return render(request, 'research/student/proposals.html', context)


@login_required
@role_required('student')
def student_edit_proposal(request, proposal_id):
    """Edit an existing draft/revision-required proposal."""
    proposal = get_object_or_404(Proposal, id=proposal_id, student=request.user)

    if proposal.status not in ['draft', 'revision_required']:
        messages.error(request, 'This proposal cannot be edited in its current state.')
        return redirect('student_proposals')

    if request.method == 'POST':
        form = ProposalForm(request.POST, request.FILES, instance=proposal)
        if form.is_valid():
            proposal = form.save(commit=False)

            if 'save_draft' in request.POST:
                proposal.status = 'draft'
                proposal.save()
                messages.success(request, 'Proposal updated and saved as draft.')
            else:
                proposal.status = 'submitted'
                proposal.submission_date = timezone.now()
                proposal.save()

                for admin in User.objects.filter(role='admin', is_active=True):
                    Notification.objects.create(
                        user=admin,
                        title='Proposal Resubmitted',
                        message=f'{request.user.get_full_name() or request.user.username} resubmitted: "{proposal.title[:50]}"',
                        notification_type='info',
                        link='/dashboard/admin/proposals/'
                    )
                messages.success(request, 'Proposal resubmitted for review!')

            return redirect('student_proposals')
    else:
        form = ProposalForm(instance=proposal)

    context = {
        'form': form,
        'proposal': proposal,
        'section': 'proposals',
        'is_edit': True,
    }
    return render(request, 'research/student/proposals.html', context)


@login_required
@role_required('student')
def student_delete_proposal(request, proposal_id):
    """Delete a draft proposal and its associated file."""
    proposal = get_object_or_404(Proposal, id=proposal_id, student=request.user)

    if proposal.status not in ['draft', 'revision_required']:
        messages.error(request, 'Only draft proposals can be deleted.')
        return redirect('student_proposals')

    # Use the storage API to delete the file (handles both local and cloud storage)
    if proposal.document:
        try:
            proposal.document.delete(save=False)
        except Exception:
            pass

    proposal.delete()
    messages.success(request, 'Proposal deleted successfully.')
    return redirect('student_proposals')


@login_required
@role_required('student')
def student_documents(request):
    """Submit documents for supervisor review."""
    user = request.user
    allocation = Allocation.objects.filter(student=user, status='active').first()

    if request.method == 'POST' and allocation:
        form = DocumentSubmissionForm(request.POST, request.FILES)
        if form.is_valid():
            report = form.save(commit=False)
            report.allocation = allocation
            report.student = user
            report.status = 'submitted'
            report.save()

            Notification.objects.create(
                user=allocation.supervisor,
                title='New Document for Review',
                message=f'{user.get_full_name() or user.username} submitted "{report.title}" for your review.',
                notification_type='info',
                link='/supervisor/documents/'
            )
            messages.success(request, f'Document "{report.title}" submitted for review!')
            return redirect('student_documents')
        else:
            for error in form.errors.values():
                messages.error(request, str(error[0]))
    else:
        form = DocumentSubmissionForm() if allocation else None

    documents = ProgressReport.objects.filter(student=user).order_by('-submitted_at')
    context = {
        'form': form,
        'documents': documents,
        'allocation': allocation,
        'section': 'documents',
    }
    return render(request, 'research/student/documents.html', context)


# ==================== SUPERVISOR VIEWS ====================

@login_required
@role_required('supervisor')
def supervisor_dashboard(request):
    """Supervisor overview dashboard."""
    user = request.user
    allocations = list(
        Allocation.objects
        .filter(supervisor=user, status='active')
        .select_related('student', 'proposal')
    )

    # Annotate allocations with live progress data
    for alloc in allocations:
        reports = ProgressReport.objects.filter(allocation=alloc)
        alloc.avg_progress = int(
            reports.aggregate(Avg('percentage_complete'))['percentage_complete__avg'] or 0
        )
        alloc.pending_docs = reports.filter(status='submitted').count()
        alloc.overdue_milestones = Milestone.objects.filter(
            allocation=alloc,
            due_date__lt=timezone.now().date(),
            status__in=['pending', 'in_progress']
        ).count()

    pending_reports = ProgressReport.objects.filter(
        allocation__supervisor=user, status='submitted'
    ).count()

    upcoming_meetings = Meeting.objects.filter(
        supervisor=user,
        meeting_date__gte=timezone.now(),
        status='scheduled'
    ).order_by('meeting_date')[:5]

    overdue_milestones = Milestone.objects.filter(
        allocation__supervisor=user,
        due_date__lt=timezone.now().date(),
        status__in=['pending', 'in_progress']
    ).select_related('allocation__student').order_by('due_date')[:5]

    recent_submissions = ProgressReport.objects.filter(
        allocation__supervisor=user,
        status='submitted'
    ).select_related('student', 'allocation').order_by('-submitted_at')[:5]

    context = {
        'allocations': allocations,
        'total_students': len(allocations),
        'pending_reports': pending_reports,
        'upcoming_meetings': upcoming_meetings,
        'overdue_milestones': overdue_milestones,
        'recent_submissions': recent_submissions,
        'section': 'dashboard',
    }
    return render(request, 'research/supervisor/dashboard.html', context)


@login_required
@role_required('supervisor')
def supervisor_students(request):
    """Overview of all assigned students with progress."""
    user = request.user
    allocations = list(
        Allocation.objects
        .filter(supervisor=user, status='active')
        .select_related('student', 'proposal')
        .order_by('student__first_name')
    )

    for alloc in allocations:
        reports = ProgressReport.objects.filter(allocation=alloc)
        alloc.avg_progress = int(
            reports.aggregate(Avg('percentage_complete'))['percentage_complete__avg'] or 0
        )
        alloc.report_count  = reports.count()
        alloc.pending_docs  = reports.filter(status='submitted').count()
        alloc.last_report   = reports.order_by('-submitted_at').first()
        alloc.total_milestones = Milestone.objects.filter(allocation=alloc).count()
        alloc.done_milestones  = Milestone.objects.filter(allocation=alloc, status='completed').count()
        alloc.overdue_milestones = Milestone.objects.filter(
            allocation=alloc,
            due_date__lt=timezone.now().date(),
            status__in=['pending', 'in_progress']
        ).count()

    context = {
        'allocations': allocations,
        'section': 'students',
    }
    return render(request, 'research/supervisor/students.html', context)


@login_required
@role_required('supervisor')
def supervisor_student_detail(request, student_id):
    """Full detail page for one supervised student — hub for all actions."""
    supervisor = request.user
    student    = get_object_or_404(User, id=student_id, role='student')
    allocation = get_object_or_404(Allocation, student=student, supervisor=supervisor, status='active')

    reports    = ProgressReport.objects.filter(allocation=allocation).order_by('-submitted_at')
    meetings   = Meeting.objects.filter(allocation=allocation).order_by('-meeting_date')
    milestones = Milestone.objects.filter(allocation=allocation).order_by('due_date')
    notes      = SupervisorNote.objects.filter(allocation=allocation, supervisor=supervisor)

    # ---- POST: add supervisor note ----
    if request.method == 'POST' and 'add_note' in request.POST:
        note_content = request.POST.get('note_content', '').strip()
        if note_content:
            SupervisorNote.objects.create(
                allocation=allocation,
                supervisor=supervisor,
                content=note_content
            )
            messages.success(request, 'Note saved.')
        else:
            messages.error(request, 'Note cannot be empty.')
        return redirect('supervisor_student_detail', student_id=student_id)

    # ---- POST: delete note ----
    if request.method == 'POST' and 'delete_note' in request.POST:
        note_id = request.POST.get('note_id')
        SupervisorNote.objects.filter(id=note_id, supervisor=supervisor).delete()
        messages.success(request, 'Note deleted.')
        return redirect('supervisor_student_detail', student_id=student_id)

    # ---- POST: review a report inline ----
    if request.method == 'POST' and 'review_report' in request.POST:
        report_id = request.POST.get('report_id')
        feedback  = request.POST.get('feedback', '').strip()
        rating_raw = request.POST.get('rating')
        new_status = request.POST.get('report_status', 'reviewed')

        report = get_object_or_404(ProgressReport, id=report_id, allocation=allocation)
        if not feedback:
            messages.error(request, 'Feedback is required.')
            return redirect('supervisor_student_detail', student_id=student_id)

        report.supervisor_feedback = feedback
        try:
            r = int(rating_raw)
            if 1 <= r <= 5:
                report.supervisor_rating = r
        except (TypeError, ValueError):
            pass
        report.status      = new_status if new_status in ['reviewed', 'approved'] else 'reviewed'
        report.reviewed_at = timezone.now()
        report.save()

        Notification.objects.create(
            user=student,
            title='Document Reviewed' if report.status == 'reviewed' else 'Document Approved ✅',
            message=f'Your submission "{report.title}" has been {report.status} by {supervisor.get_full_name() or supervisor.username}.',
            notification_type='success' if report.status == 'approved' else 'info',
            link='/student/documents/'
        )
        messages.success(request, f'Review saved for "{report.title}".')
        return redirect('supervisor_student_detail', student_id=student_id)

    # ---- POST: send a notification/reminder to student ----
    if request.method == 'POST' and 'send_reminder' in request.POST:
        reminder_msg = request.POST.get('reminder_message', '').strip()
        if reminder_msg:
            Notification.objects.create(
                user=student,
                title=f'Message from your supervisor',
                message=reminder_msg,
                notification_type='warning',
                link='/student/dashboard/'
            )
            AuditLog.objects.create(
                user=supervisor,
                action='SEND_REMINDER',
                module='Supervisor',
                description=f'Sent reminder to {student.username}: {reminder_msg[:80]}',
                ip_address=_get_client_ip(request)
            )
            messages.success(request, f'Reminder sent to {student.get_full_name() or student.username}.')
        else:
            messages.error(request, 'Message cannot be empty.')
        return redirect('supervisor_student_detail', student_id=student_id)

    total_reports    = reports.count()
    reviewed_reports = reports.filter(status__in=['reviewed', 'approved']).count()
    completion_pct   = int((reviewed_reports / total_reports) * 100) if total_reports > 0 else 0
    avg_progress     = int(
        reports.aggregate(Avg('percentage_complete'))['percentage_complete__avg'] or 0
    )

    context = {
        'student':          student,
        'allocation':       allocation,
        'reports':          reports,
        'meetings':         meetings,
        'milestones':       milestones,
        'notes':            notes,
        'total_reports':    total_reports,
        'reviewed_reports': reviewed_reports,
        'completion_pct':   completion_pct,
        'avg_progress':     avg_progress,
        'section':          'students',
    }
    return render(request, 'research/supervisor/student_detail.html', context)


@login_required
@role_required('supervisor')
def supervisor_documents(request):
    """Review all student-submitted documents and reports."""
    user = request.user

    type_filter   = request.GET.get('type', '')
    student_filter = request.GET.get('student', '')

    pending_qs = ProgressReport.objects.filter(
        allocation__supervisor=user, status='submitted'
    ).select_related('student', 'allocation__proposal')

    reviewed_qs = ProgressReport.objects.filter(
        allocation__supervisor=user, status__in=['reviewed', 'approved']
    ).select_related('student', 'allocation__proposal')

    if type_filter:
        pending_qs  = pending_qs.filter(report_type=type_filter)
        reviewed_qs = reviewed_qs.filter(report_type=type_filter)
    if student_filter:
        pending_qs  = pending_qs.filter(student__id=student_filter)
        reviewed_qs = reviewed_qs.filter(student__id=student_filter)

    pending_docs  = pending_qs.order_by('-submitted_at')
    reviewed_docs = reviewed_qs.order_by('-reviewed_at')

    if request.method == 'POST':
        report_id  = request.POST.get('report_id')
        feedback   = request.POST.get('feedback', '').strip()
        rating_raw = request.POST.get('rating')
        new_status = request.POST.get('report_status', 'reviewed')

        if not feedback:
            messages.error(request, 'Feedback is required.')
            return redirect('supervisor_documents')

        report = get_object_or_404(ProgressReport, id=report_id, allocation__supervisor=user)
        report.supervisor_feedback = feedback
        try:
            r = int(rating_raw)
            if 1 <= r <= 5:
                report.supervisor_rating = r
        except (TypeError, ValueError):
            pass
        report.status      = new_status if new_status in ['reviewed', 'approved'] else 'reviewed'
        report.reviewed_at = timezone.now()
        report.save()

        Notification.objects.create(
            user=report.student,
            title='Document Reviewed' if report.status == 'reviewed' else 'Document Approved ✅',
            message=f'Your submission "{report.title}" has been {report.status} by {user.get_full_name() or user.username}.',
            notification_type='success' if report.status == 'approved' else 'info',
            link='/student/documents/'
        )
        messages.success(request, f'Review submitted for "{report.title}".')
        return redirect('supervisor_documents')

    # Students dropdown for filter
    my_students = User.objects.filter(
        allocations_as_student__supervisor=user,
        allocations_as_student__status='active'
    ).distinct()

    context = {
        'pending_docs':  pending_docs,
        'reviewed_docs': reviewed_docs,
        'type_filter':   type_filter,
        'student_filter': student_filter,
        'my_students':   my_students,
        'report_types':  ProgressReport.TYPE_CHOICES,
        'section':       'documents',
    }
    return render(request, 'research/supervisor/documents.html', context)


@login_required
@role_required('supervisor')
def supervisor_milestones(request, student_id):
    """Create, edit, and manage milestones for a specific student."""
    supervisor = request.user
    student    = get_object_or_404(User, id=student_id, role='student')
    allocation = get_object_or_404(Allocation, student=student, supervisor=supervisor, status='active')
    milestones = Milestone.objects.filter(allocation=allocation).order_by('due_date')

    # Auto-mark overdue milestones
    today = timezone.now().date()
    milestones.filter(
        due_date__lt=today,
        status__in=['pending', 'in_progress']
    ).update(status='overdue')

    # ---- POST: create milestone ----
    if request.method == 'POST' and 'create_milestone' in request.POST:
        title       = request.POST.get('title', '').strip()
        description = request.POST.get('description', '').strip()
        due_date_str = request.POST.get('due_date', '')
        if not title or not due_date_str:
            messages.error(request, 'Title and due date are required.')
            return redirect('supervisor_milestones', student_id=student_id)
        try:
            from datetime import date
            due_date = date.fromisoformat(due_date_str)
        except ValueError:
            messages.error(request, 'Invalid date format.')
            return redirect('supervisor_milestones', student_id=student_id)

        Milestone.objects.create(
            allocation=allocation,
            title=title,
            description=description,
            due_date=due_date,
            created_by=supervisor
        )
        Notification.objects.create(
            user=student,
            title='New Milestone Set',
            message=f'Your supervisor has added a new milestone: "{title}" due {due_date.strftime("%b %d, %Y")}.',
            notification_type='info',
            link='/student/dashboard/'
        )
        messages.success(request, f'Milestone "{title}" created.')
        return redirect('supervisor_milestones', student_id=student_id)

    # ---- POST: update milestone status ----
    if request.method == 'POST' and 'update_milestone' in request.POST:
        ms_id      = request.POST.get('milestone_id')
        new_status = request.POST.get('milestone_status')
        milestone  = get_object_or_404(Milestone, id=ms_id, allocation=allocation)
        valid = [s for s, _ in Milestone.STATUS_CHOICES]
        if new_status in valid:
            milestone.status = new_status
            if new_status == 'completed':
                milestone.completed_date = today
            milestone.save()
            messages.success(request, f'Milestone updated to "{new_status}".')
        return redirect('supervisor_milestones', student_id=student_id)

    # ---- POST: delete milestone ----
    if request.method == 'POST' and 'delete_milestone' in request.POST:
        ms_id = request.POST.get('milestone_id')
        Milestone.objects.filter(id=ms_id, allocation=allocation).delete()
        messages.success(request, 'Milestone deleted.')
        return redirect('supervisor_milestones', student_id=student_id)

    context = {
        'student':    student,
        'allocation': allocation,
        'milestones': milestones,
        'today':      today,
        'section':    'students',
    }
    return render(request, 'research/supervisor/milestones.html', context)


@login_required
@role_required('supervisor')
def supervisor_meeting_update(request, meeting_id):
    """Mark a meeting as completed and record minutes."""
    supervisor = request.user
    meeting    = get_object_or_404(Meeting, id=meeting_id, supervisor=supervisor)

    if request.method == 'POST':
        action = request.POST.get('action')
        if action == 'complete':
            minutes = request.POST.get('minutes', '').strip()
            meeting.status  = 'completed'
            meeting.minutes = minutes
            meeting.save()
            Notification.objects.create(
                user=meeting.student,
                title='Meeting Completed',
                message=f'Meeting "{meeting.title}" has been marked as completed by your supervisor.',
                notification_type='info',
                link='/meetings/'
            )
            messages.success(request, 'Meeting marked as completed.')
        elif action == 'cancel':
            meeting.status = 'cancelled'
            meeting.save()
            Notification.objects.create(
                user=meeting.student,
                title='Meeting Cancelled',
                message=f'Meeting "{meeting.title}" on {meeting.meeting_date.strftime("%b %d, %Y")} has been cancelled.',
                notification_type='warning',
                link='/meetings/'
            )
            messages.warning(request, 'Meeting cancelled.')
        return redirect('meetings')

    context = {
        'meeting': meeting,
        'section': 'meetings',
    }
    return render(request, 'research/supervisor/meeting_update.html', context)


@login_required
@role_required('supervisor')
def supervisor_progress_overview(request):
    """Full progress overview across all supervised students."""
    user = request.user
    allocations = list(
        Allocation.objects
        .filter(supervisor=user, status='active')
        .select_related('student', 'proposal')
        .order_by('student__first_name')
    )
    today = timezone.now().date()

    student_data = []
    for alloc in allocations:
        reports    = ProgressReport.objects.filter(allocation=alloc)
        milestones = Milestone.objects.filter(allocation=alloc)
        meetings   = Meeting.objects.filter(allocation=alloc, status='completed')

        avg_progress = int(
            reports.aggregate(Avg('percentage_complete'))['percentage_complete__avg'] or 0
        )
        overdue = milestones.filter(
            due_date__lt=today, status__in=['pending', 'in_progress']
        ).count()
        pending_docs = reports.filter(status='submitted').count()
        last_submission = reports.order_by('-submitted_at').first()

        student_data.append({
            'allocation':       alloc,
            'avg_progress':     avg_progress,
            'total_reports':    reports.count(),
            'reviewed_reports': reports.filter(status__in=['reviewed', 'approved']).count(),
            'total_milestones': milestones.count(),
            'done_milestones':  milestones.filter(status='completed').count(),
            'overdue':          overdue,
            'pending_docs':     pending_docs,
            'total_meetings':   meetings.count(),
            'last_submission':  last_submission,
        })

    context = {
        'student_data': student_data,
        'section':      'progress',
    }
    return render(request, 'research/supervisor/progress_overview.html', context)


# ==================== SHARED VIEWS ====================

@login_required
def meetings(request):
    """Schedule and view meetings."""
    user = request.user

    if user.role == 'student':
        allocation = Allocation.objects.filter(student=user, status='active').first()
        user_meetings = Meeting.objects.filter(student=user).order_by('-meeting_date')
        can_schedule = allocation is not None
    elif user.role == 'supervisor':
        allocation = None
        user_meetings = Meeting.objects.filter(supervisor=user).order_by('-meeting_date')
        can_schedule = True
    else:
        allocation = None
        user_meetings = Meeting.objects.all().order_by('-meeting_date')
        can_schedule = False

    if request.method == 'POST' and can_schedule:
        form = MeetingForm(request.POST)
        if form.is_valid():
            meeting = form.save(commit=False)

            if user.role == 'student' and allocation:
                meeting.allocation = allocation
                meeting.student = user
                meeting.supervisor = allocation.supervisor
            elif user.role == 'supervisor':
                student_id = request.POST.get('student_id')
                if not student_id:
                    messages.error(request, 'Please select a student.')
                    return redirect('meetings')
                student = get_object_or_404(User, id=student_id, role='student')
                student_allocation = Allocation.objects.filter(
                    student=student, supervisor=user, status='active'
                ).first()
                if not student_allocation:
                    messages.error(request, 'You are not assigned as supervisor for this student.')
                    return redirect('meetings')
                meeting.allocation = student_allocation
                meeting.student = student
                meeting.supervisor = user

            meeting.save()

            other_user = meeting.student if user.role == 'supervisor' else meeting.supervisor
            Notification.objects.create(
                user=other_user,
                title='Meeting Scheduled',
                message=f'A meeting "{meeting.title}" has been scheduled for {meeting.meeting_date.strftime("%Y-%m-%d %H:%M")}.',
                notification_type='info',
                link='/meetings/'
            )
            messages.success(request, f'Meeting "{meeting.title}" scheduled successfully.')
            return redirect('meetings')
    else:
        form = MeetingForm()

    students = []
    if user.role == 'supervisor':
        sup_allocations = Allocation.objects.filter(supervisor=user, status='active').select_related('student')
        students = [{'id': a.student.id, 'name': a.student.get_full_name() or a.student.username}
                    for a in sup_allocations]

    context = {
        'meetings': user_meetings,
        'form': form,
        'can_schedule': can_schedule,
        'students': students,
        'section': 'meetings',
    }
    return render(request, 'research/meetings.html', context)


@login_required
def notifications(request):
    """View and manage notifications."""
    user = request.user
    notifications_list = Notification.objects.filter(user=user).order_by('-created_at')

    if request.method == 'POST' and 'mark_all_read' in request.POST:
        notifications_list.filter(is_read=False).update(is_read=True)
        messages.success(request, 'All notifications marked as read.')
        return redirect('notifications')

    if request.headers.get('x-requested-with') == 'XMLHttpRequest':
        notif_id = request.GET.get('notification_id') or request.POST.get('notification_id')
        if notif_id:
            Notification.objects.filter(id=notif_id, user=user).update(is_read=True)
            return JsonResponse({'status': 'success'})

    paginator = Paginator(notifications_list, 20)
    page_obj = paginator.get_page(request.GET.get('page'))

    context = {
        'page_obj': page_obj,
        'unread_count': user.get_unread_notification_count(),
        'section': 'notifications',
    }
    return render(request, 'research/notifications.html', context)


@login_required
def profile(request):
    """User profile management."""
    user = request.user

    if request.method == 'POST':
        user.first_name = request.POST.get('first_name', '').strip()
        user.last_name = request.POST.get('last_name', '').strip()
        user.phone = request.POST.get('phone', '').strip()
        user.department = request.POST.get('department', '').strip()

        if 'profile_pic' in request.FILES:
            # Delete old profile pic to avoid orphan files
            if user.profile_pic:
                try:
                    user.profile_pic.delete(save=False)
                except Exception:
                    pass
            user.profile_pic = request.FILES['profile_pic']

        new_password = request.POST.get('new_password', '').strip()
        confirm_password = request.POST.get('confirm_password', '').strip()

        if new_password:
            if new_password != confirm_password:
                messages.error(request, 'Passwords do not match.')
                return redirect('profile')
            if len(new_password) < 8:
                messages.error(request, 'Password must be at least 8 characters.')
                return redirect('profile')
            user.set_password(new_password)
            user.save()
            messages.success(request, 'Password changed. Please log in again.')
            logout(request)
            return redirect('login')

        user.save()
        messages.success(request, 'Profile updated successfully.')
        return redirect('profile')

    context = {'section': 'profile'}
    return render(request, 'research/profile.html', context)




# ==================== CHAT / MESSAGING VIEWS ====================

@login_required
def conversation_list(request):
    """
    List all conversations the current user is part of.
    Students see one thread (their supervisor).
    Supervisors see one thread per student.
    Admins see nothing (no allocation-based conversations).
    """
    user = request.user
    conversations = []

    if user.role == 'student':
        allocations = Allocation.objects.filter(
            student=user, status='active'
        ).select_related('supervisor', 'proposal')
        for alloc in allocations:
            last_msg = Message.objects.filter(allocation=alloc).order_by('-created_at').first()
            unread   = Message.objects.filter(allocation=alloc, recipient=user, is_read=False).count()
            conversations.append({
                'allocation': alloc,
                'other_user': alloc.supervisor,
                'last_msg':   last_msg,
                'unread':     unread,
            })

    elif user.role == 'supervisor':
        allocations = Allocation.objects.filter(
            supervisor=user, status='active'
        ).select_related('student', 'proposal')
        for alloc in allocations:
            last_msg = Message.objects.filter(allocation=alloc).order_by('-created_at').first()
            unread   = Message.objects.filter(allocation=alloc, recipient=user, is_read=False).count()
            conversations.append({
                'allocation': alloc,
                'other_user': alloc.student,
                'last_msg':   last_msg,
                'unread':     unread,
            })

    # Sort: conversations with unread messages first, then by latest message
    conversations.sort(
        key=lambda c: (
            -c['unread'],
            -(c['last_msg'].created_at.timestamp() if c['last_msg'] else 0)
        )
    )

    total_unread = sum(c['unread'] for c in conversations)

    context = {
        'conversations': conversations,
        'total_unread':  total_unread,
        'section':       'chat',
    }
    return render(request, 'research/chat/conversation_list.html', context)


@login_required
def conversation(request, allocation_id):
    """
    The WhatsApp-style chat thread for one allocation.
    Handles both page load (GET) and AJAX message send (POST).
    """
    user       = request.user
    allocation = get_object_or_404(Allocation, id=allocation_id)

    # Security: only the supervisor or student of this allocation may access it
    if user != allocation.supervisor and user != allocation.student:
        messages.error(request, 'You do not have access to this conversation.')
        return redirect('conversation_list')

    # Mark all unread messages from the other person as read on open
    Message.objects.filter(
        allocation=allocation, recipient=user, is_read=False
    ).update(is_read=True)

    # ---- AJAX POST: send a message ----
    if request.method == 'POST' and request.headers.get('x-requested-with') == 'XMLHttpRequest':
        content_text = request.POST.get('content', '').strip()
        if not content_text:
            return JsonResponse({'status': 'error', 'message': 'Message cannot be empty.'}, status=400)

        recipient = allocation.student if user == allocation.supervisor else allocation.supervisor

        msg = Message.objects.create(
            allocation=allocation,
            sender=user,
            recipient=recipient,
            content=content_text,
        )

        # Push real-time via WebSocket to the recipient
        from channels.layers import get_channel_layer
        from asgiref.sync import async_to_sync
        channel_layer = get_channel_layer()
        if channel_layer:
            async_to_sync(channel_layer.group_send)(
                f'user_{recipient.id}',
                {
                    'type':          'chat_message',
                    'message_id':    msg.id,
                    'allocation_id': allocation.id,
                    'sender_id':     user.id,
                    'sender_name':   user.get_full_name() or user.username,
                    'content':       msg.content,
                    'created_at':    msg.created_at.strftime('%H:%M'),
                }
            )

        # Also create a Notification so the recipient sees it in the bell dropdown
        Notification.objects.create(
            user=recipient,
            title=f'New message from {user.get_full_name() or user.username}',
            message=content_text[:120],
            notification_type='info',
            link=f'/chat/{allocation.id}/',
        )

        # Push notification count update to recipient via WS
        if channel_layer:
            async_to_sync(channel_layer.group_send)(
                f'user_{recipient.id}',
                {
                    'type':            'send_notification',
                    'title':           f'New message from {user.get_full_name() or user.username}',
                    'message':         content_text[:120],
                    'notif_type':      'info',
                    'link':            f'/chat/{allocation.id}/',
                }
            )

        return JsonResponse({
            'status':     'ok',
            'message_id': msg.id,
            'content':    msg.content,
            'sender_id':  user.id,
            'created_at': msg.created_at.strftime('%H:%M'),
            'sender_name': user.get_full_name() or user.username,
        })

    # ---- Normal GET: load the page ----
    chat_messages = Message.objects.filter(
        allocation=allocation
    ).select_related('sender').order_by('created_at')

    other_user = allocation.student if user == allocation.supervisor else allocation.supervisor

    from datetime import date, timedelta
    today     = date.today().strftime('%Y-%m-%d')
    yesterday = (date.today() - timedelta(days=1)).strftime('%Y-%m-%d')

    context = {
        'allocation':     allocation,
        'other_user':     other_user,
        'chat_messages':  chat_messages,
        'today':          today,
        'yesterday':      yesterday,
        'section':        'chat',
    }
    return render(request, 'research/chat/conversation.html', context)


@login_required
@ajax_required
def get_unread_message_count(request):
    """Return total unread message count for the current user."""
    count = Message.objects.filter(recipient=request.user, is_read=False).count()
    return JsonResponse({'count': count})

# ==================== AJAX VIEWS ====================

@login_required
@ajax_required
def get_notification_count(request):
    """Return unread notification count as JSON."""
    count = request.user.get_unread_notification_count()
    return JsonResponse({'count': count})


@login_required
@ajax_required
def mark_notification_read_ajax(request):
    """Mark a single notification as read."""
    notif_id = request.POST.get('notification_id')
    if notif_id:
        Notification.objects.filter(id=notif_id, user=request.user).update(is_read=True)
        return JsonResponse({'status': 'success'})
    return JsonResponse({'status': 'error', 'message': 'notification_id required'}, status=400)


@login_required
@ajax_required
def get_recent_notifications(request):
    """Return 5 most recent unread notifications as JSON."""
    notifs = Notification.objects.filter(
        user=request.user, is_read=False
    ).order_by('-created_at')[:5]
    data = {
        'count': notifs.count(),
        'notifications': [
            {
                'id':      n.id,
                'title':   n.title,
                'message': n.message[:100],
                'type':    n.notification_type,
                'time':    n.created_at.strftime('%b %d, %H:%M'),
                'link':    n.link,
            }
            for n in notifs
        ]
    }
    return JsonResponse(data)
