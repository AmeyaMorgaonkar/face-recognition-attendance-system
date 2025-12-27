from django import forms
from django.contrib.auth.forms import AuthenticationForm
from .models import Lecture


class StudentLoginForm(AuthenticationForm):
    """Custom login form for students"""
    username = forms.CharField(
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': 'Roll Number or Username',
            'autofocus': True
        })
    )
    password = forms.CharField(
        widget=forms.PasswordInput(attrs={
            'class': 'form-control',
            'placeholder': 'Password'
        })
    )


class StartLectureForm(forms.Form):
    """Form to start a lecture"""
    lecture_id = forms.IntegerField(widget=forms.HiddenInput())
