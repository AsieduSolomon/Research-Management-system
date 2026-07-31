from django import forms
from django.contrib.auth.forms import AuthenticationForm, UserCreationForm
from .models import User, Proposal, ProgressReport, Meeting, Milestone


class LoginForm(AuthenticationForm):
    username = forms.EmailField(
        widget=forms.EmailInput(attrs={'class': 'form-control', 'placeholder': 'Email Address'})
    )


class UserRegistrationForm(UserCreationForm):
    email = forms.EmailField(
        required=True,
        widget=forms.EmailInput(attrs={'class': 'form-control', 'placeholder': 'Email Address'})
    )
    student_id = forms.CharField(
        max_length=50, required=False,
        widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Student/Staff ID (optional)'})
    )
    department = forms.CharField(
        max_length=100, required=False,
        widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Department (optional)'})
    )
    phone = forms.CharField(
        max_length=20, required=False,
        widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Phone Number (optional)'})
    )
    first_name = forms.CharField(
        max_length=150, required=True,
        widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'First Name'})
    )
    last_name = forms.CharField(
        max_length=150, required=True,
        widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Last Name'})
    )
    username = forms.CharField(
        max_length=150, required=True,
        widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Username'})
    )
    password1 = forms.CharField(
        widget=forms.PasswordInput(attrs={'class': 'form-control', 'placeholder': 'Password'}),
        label="Password"
    )
    password2 = forms.CharField(
        widget=forms.PasswordInput(attrs={'class': 'form-control', 'placeholder': 'Confirm Password'}),
        label="Confirm Password"
    )

    class Meta:
        model = User
        fields = ['username', 'email', 'student_id', 'first_name', 'last_name',
                  'department', 'phone', 'password1', 'password2']

    def __init__(self, *args, **kwargs):
        # Accept an optional `instance` so the form works for both create and edit
        # (admin_user_edit uses raw POST, but this guards future use of the form)
        self._edit_instance = kwargs.pop('edit_instance', None)
        super().__init__(*args, **kwargs)

    def clean_email(self):
        email = self.cleaned_data.get('email')
        qs = User.objects.filter(email=email)
        # Exclude the current instance when editing
        if self._edit_instance:
            qs = qs.exclude(pk=self._edit_instance.pk)
        if qs.exists():
            raise forms.ValidationError('This email is already registered.')
        return email

    def save(self, commit=True):
        user = super().save(commit=False)
        user.email = self.cleaned_data['email']
        user.student_id = self.cleaned_data.get('student_id') or None  # avoid blank unique clash
        user.department = self.cleaned_data.get('department', '')
        user.phone = self.cleaned_data.get('phone', '')
        user.first_name = self.cleaned_data['first_name']
        user.last_name = self.cleaned_data['last_name']
        if commit:
            user.save()
        return user


class ProposalForm(forms.ModelForm):
    class Meta:
        model = Proposal
        fields = ['title', 'abstract', 'objectives', 'methodology', 'background',
                  'expected_outcomes', 'keywords', 'department', 'program',
                  'academic_year', 'document']
        widgets = {
            'title': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Enter proposal title'}),
            'abstract': forms.Textarea(attrs={'class': 'form-control', 'rows': 4, 'placeholder': 'Brief summary of your research'}),
            'objectives': forms.Textarea(attrs={'class': 'form-control', 'rows': 4, 'placeholder': 'List your research objectives'}),
            'methodology': forms.Textarea(attrs={'class': 'form-control', 'rows': 4, 'placeholder': 'Describe your research methods'}),
            'background': forms.Textarea(attrs={'class': 'form-control', 'rows': 4, 'placeholder': 'Literature review and context'}),
            'expected_outcomes': forms.Textarea(attrs={'class': 'form-control', 'rows': 3, 'placeholder': 'What do you expect to achieve?'}),
            'keywords': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'e.g., machine learning, healthcare'}),
            'department': forms.TextInput(attrs={'class': 'form-control'}),
            'program': forms.TextInput(attrs={'class': 'form-control'}),
            'academic_year': forms.TextInput(attrs={'class': 'form-control'}),
            'document': forms.FileInput(attrs={'class': 'form-control'}),
        }


class DocumentSubmissionForm(forms.ModelForm):
    class Meta:
        model = ProgressReport
        fields = ['title', 'content', 'report_type', 'document']
        widgets = {
            'title': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'e.g., Literature Review Chapter'}),
            'content': forms.Textarea(attrs={'class': 'form-control', 'rows': 5, 'placeholder': 'Notes or description for your supervisor'}),
            'report_type': forms.Select(attrs={'class': 'form-control'}),
            'document': forms.FileInput(attrs={'class': 'form-control'}),
        }


class ReviewForm(forms.Form):
    feedback = forms.CharField(
        widget=forms.Textarea(attrs={'class': 'form-control', 'rows': 5, 'placeholder': 'Provide detailed feedback...'})
    )
    rating = forms.ChoiceField(
        choices=[(i, f"{'⭐' * i} ({i}/5)") for i in range(1, 6)],
        widget=forms.Select(attrs={'class': 'form-control'})
    )


class MeetingForm(forms.ModelForm):
    meeting_date = forms.DateTimeField(
        widget=forms.DateTimeInput(attrs={'class': 'form-control', 'type': 'datetime-local'})
    )

    class Meta:
        model = Meeting
        fields = ['title', 'description', 'meeting_date', 'location', 'meeting_type']
        widgets = {
            'title': forms.TextInput(attrs={'class': 'form-control'}),
            'description': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
            'location': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Room number or Zoom link'}),
            'meeting_type': forms.Select(attrs={'class': 'form-control'}),
        }


class MilestoneForm(forms.ModelForm):
    due_date = forms.DateField(
        widget=forms.DateInput(attrs={'class': 'form-control', 'type': 'date'})
    )

    class Meta:
        model = Milestone
        fields = ['title', 'description', 'due_date']
        widgets = {
            'title': forms.TextInput(attrs={'class': 'form-control'}),
            'description': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
        }
