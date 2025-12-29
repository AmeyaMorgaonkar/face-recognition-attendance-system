#!/usr/bin/env python
"""Set up teacher user accounts for testing."""
import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'attendance_system.settings')
django.setup()

from django.contrib.auth.models import User
from core.models import Teacher

def setup_teacher_accounts():
    """Create user accounts for all teachers without one."""
    teachers = Teacher.objects.filter(user__isnull=True)
    
    if not teachers.exists():
        print("All teachers already have user accounts!")
        # Show existing teachers
        for teacher in Teacher.objects.all():
            print(f"  - {teacher.name}: {teacher.email} (user: {teacher.user.username if teacher.user else 'None'})")
        return
    
    for teacher in teachers:
        # Create username from email or name
        if teacher.email:
            username = teacher.email.split('@')[0].lower()
        else:
            username = teacher.name.lower().replace(' ', '_').replace('.', '')
        
        # Ensure unique username
        base_username = username
        counter = 1
        while User.objects.filter(username=username).exists():
            username = f"{base_username}{counter}"
            counter += 1
        
        # Create user
        user = User.objects.create_user(
            username=username,
            email=teacher.email,
            password='teacher123',
            first_name=teacher.name.split()[0] if teacher.name else '',
            last_name=' '.join(teacher.name.split()[1:]) if teacher.name and len(teacher.name.split()) > 1 else ''
        )
        
        teacher.user = user
        teacher.save()
        
        print(f"✅ Created account for {teacher.name}")
        print(f"   Email: {teacher.email}")
        print(f"   Username: {username}")
        print(f"   Password: teacher123")
        print()

if __name__ == '__main__':
    print("\n🎓 Setting up Teacher Accounts\n")
    print("="*40)
    setup_teacher_accounts()
    print("="*40)
    print("\nTeachers can now login at /teacher/")
    print("Default password: teacher123\n")
