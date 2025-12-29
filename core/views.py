"""
Views for the Attendance System
"""

import os
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth import login, logout
from django.contrib.auth.decorators import login_required
from django.contrib.auth.views import LoginView
from django.contrib import messages
from django.http import JsonResponse
from django.utils import timezone
from django.db.models import Count, Q
from django.conf import settings
from datetime import datetime, timedelta

from .models import Student, Classroom, Timetable, Lecture, Attendance, Subject, Teacher, Room, CancelledLecture
from .forms import StudentLoginForm, PhotoUploadForm, TeacherLoginForm, ScheduleExtraLectureForm


def student_login(request):
    """Login view for students using Division + Roll No"""
    if request.user.is_authenticated:
        if hasattr(request.user, 'student_profile'):
            return redirect('dashboard')
        elif request.user.is_staff:
            return redirect('/admin/')
        logout(request)
    
    if request.method == 'POST':
        form = StudentLoginForm(request.POST)
        if form.is_valid():
            user = form.cleaned_data.get('user')
            if user:
                login(request, user)
                messages.success(request, f'Welcome, {user.student_profile.name}!')
                return redirect('dashboard')
    else:
        form = StudentLoginForm()
    
    return render(request, 'core/login.html', {'form': form})


def logout_view(request):
    """Logout view - redirect to appropriate login page"""
    # Check user type before logging out
    is_teacher = hasattr(request.user, 'teacher_profile') if request.user.is_authenticated else False
    logout(request)
    if is_teacher:
        return redirect('teacher_login')
    return redirect('login')


@login_required
def dashboard(request):
    """
    Student dashboard showing their attendance statistics.
    """
    # Check if user is a student
    try:
        student = request.user.student_profile
    except (Student.DoesNotExist, AttributeError):
        # Not a student - if admin, redirect to admin
        if request.user.is_staff:
            return redirect('/admin/')
        messages.error(request, "You don't have a student profile. Please contact admin.")
        logout(request)
        return redirect('login')
    
    # Get all attendance records for this student
    attendance_records = Attendance.objects.filter(student=student).select_related(
        'lecture', 'lecture__timetable', 'lecture__timetable__subject', 
        'lecture__timetable__teacher', 'lecture__timetable__classroom'
    ).order_by('-lecture__date')
    
    # Calculate statistics
    total_lectures = attendance_records.count()
    present_count = attendance_records.filter(status='present').count()
    absent_count = attendance_records.filter(status='absent').count()
    late_count = attendance_records.filter(status='late').count()
    
    attendance_percentage = (present_count / total_lectures * 100) if total_lectures > 0 else 0
    
    # Get subject-wise attendance
    subjects = Subject.objects.filter(
        timetable_entries__classroom=student.classroom
    ).distinct()
    
    subject_attendance = []
    for subject in subjects:
        subject_records = attendance_records.filter(lecture__timetable__subject=subject)
        total = subject_records.count()
        present = subject_records.filter(status='present').count()
        percentage = (present / total * 100) if total > 0 else 0
        subject_attendance.append({
            'subject': subject,
            'total': total,
            'present': present,
            'percentage': round(percentage, 1)
        })
    
    # Get recent attendance (last 10)
    recent_attendance = attendance_records[:10]
    
    # Get today's and tomorrow's dates
    today = timezone.now().date()
    tomorrow = today + timedelta(days=1)
    day_of_week = today.weekday()
    tomorrow_day_of_week = tomorrow.weekday()
    
    # Get today's schedule (recurring entries only, excluding cancelled)
    todays_schedule = Timetable.objects.filter(
        classroom=student.classroom,
        day_of_week=day_of_week,
        is_recurring=True
    ).exclude(
        cancellations__date=today
    ).order_by('start_time')
    
    # Get tomorrow's schedule (recurring, excluding cancelled)
    tomorrows_schedule = Timetable.objects.filter(
        classroom=student.classroom,
        day_of_week=tomorrow_day_of_week,
        is_recurring=True
    ).exclude(
        cancellations__date=tomorrow
    ).order_by('start_time')
    
    # Get cancelled lectures for today (for student's class)
    cancelled_today = CancelledLecture.objects.filter(
        timetable__classroom=student.classroom,
        date=today
    ).select_related('timetable', 'timetable__subject', 'timetable__teacher')
    
    # Get cancelled lectures for tomorrow
    cancelled_tomorrow = CancelledLecture.objects.filter(
        timetable__classroom=student.classroom,
        date=tomorrow
    ).select_related('timetable', 'timetable__subject', 'timetable__teacher')
    
    # Get extra lectures for today (for student's class)
    extra_today = Timetable.objects.filter(
        classroom=student.classroom,
        is_recurring=False,
        extra_date=today
    ).order_by('start_time')
    
    # Get extra lectures for tomorrow
    extra_tomorrow = Timetable.objects.filter(
        classroom=student.classroom,
        is_recurring=False,
        extra_date=tomorrow
    ).order_by('start_time')
    
    # Combine cancelled and extra for display
    has_schedule_changes = (cancelled_today.exists() or cancelled_tomorrow.exists() or 
                           extra_today.exists() or extra_tomorrow.exists())
    
    context = {
        'student': student,
        'total_lectures': total_lectures,
        'present_count': present_count,
        'absent_count': absent_count,
        'late_count': late_count,
        'attendance_percentage': round(attendance_percentage, 1),
        'subject_attendance': subject_attendance,
        'recent_attendance': recent_attendance,
        'todays_schedule': todays_schedule,
        'tomorrows_schedule': tomorrows_schedule,
        'today': today,
        'tomorrow': tomorrow,
        'cancelled_today': cancelled_today,
        'cancelled_tomorrow': cancelled_tomorrow,
        'extra_today': extra_today,
        'extra_tomorrow': extra_tomorrow,
        'has_schedule_changes': has_schedule_changes,
    }
    
    return render(request, 'core/dashboard.html', context)


@login_required
def attendance_history(request):
    """View full attendance history"""
    try:
        student = request.user.student_profile
    except Student.DoesNotExist:
        messages.error(request, "You don't have a student profile.")
        return redirect('login')
    
    # Filter options
    subject_filter = request.GET.get('subject', '')
    status_filter = request.GET.get('status', '')
    date_from = request.GET.get('date_from', '')
    date_to = request.GET.get('date_to', '')
    
    attendance_records = Attendance.objects.filter(student=student).select_related(
        'lecture', 'lecture__timetable', 'lecture__timetable__subject',
        'lecture__timetable__teacher'
    ).order_by('-lecture__date')
    
    if subject_filter:
        attendance_records = attendance_records.filter(lecture__timetable__subject_id=subject_filter)
    if status_filter:
        attendance_records = attendance_records.filter(status=status_filter)
    if date_from:
        attendance_records = attendance_records.filter(lecture__date__gte=date_from)
    if date_to:
        attendance_records = attendance_records.filter(lecture__date__lte=date_to)
    
    # Get subjects for filter dropdown
    subjects = Subject.objects.filter(
        timetable_entries__classroom=student.classroom
    ).distinct()
    
    context = {
        'student': student,
        'attendance_records': attendance_records,
        'subjects': subjects,
        'selected_subject': subject_filter,
        'selected_status': status_filter,
        'date_from': date_from,
        'date_to': date_to,
    }
    
    return render(request, 'core/attendance_history.html', context)


@login_required
def upload_photo(request):
    """Handle photo uploads for face recognition"""
    try:
        student = request.user.student_profile
    except Student.DoesNotExist:
        messages.error(request, "You don't have a student profile.")
        return redirect('login')
    
    if request.method == 'POST':
        photo_type = request.POST.get('photo_type', 'straight')
        photo_file = request.FILES.get('photo')
        
        if photo_file:
            # Create folder path: known_faces/DivisionName_RollNo/
            folder_name = student.get_face_folder()
            base_path = os.path.join(settings.BASE_DIR, 'known_faces', folder_name)
            os.makedirs(base_path, exist_ok=True)
            
            # Determine filename based on photo type
            filename = f"{photo_type}.jpg"
            file_path = os.path.join(base_path, filename)
            
            # Save the file
            with open(file_path, 'wb+') as destination:
                for chunk in photo_file.chunks():
                    destination.write(chunk)
            
            # Update student record with relative path
            relative_path = f"{folder_name}/{filename}"
            if photo_type == 'straight':
                student.photo_straight = relative_path
            elif photo_type == 'left':
                student.photo_left = relative_path
            elif photo_type == 'right':
                student.photo_right = relative_path
            
            # Update face_folder_name to match the new format
            student.face_folder_name = folder_name
            student.save()
            
            messages.success(request, f'{photo_type.title()} photo uploaded successfully!')
            
            # Return JSON response for AJAX calls
            if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                return JsonResponse({
                    'success': True,
                    'photo_type': photo_type,
                    'message': f'{photo_type.title()} photo uploaded successfully!'
                })
        else:
            messages.error(request, 'No photo file received')
            if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                return JsonResponse({'success': False, 'message': 'No photo file received'})
    
    return redirect('dashboard')


@login_required
def delete_photo(request):
    """Delete a photo for face recognition (for testing purposes)"""
    try:
        student = request.user.student_profile
    except Student.DoesNotExist:
        messages.error(request, "You don't have a student profile.")
        return redirect('login')
    
    if request.method == 'POST':
        photo_type = request.POST.get('photo_type', '')
        
        if photo_type in ['straight', 'left', 'right']:
            # Get the current photo path
            if photo_type == 'straight':
                photo_path = student.photo_straight
                student.photo_straight = ''
            elif photo_type == 'left':
                photo_path = student.photo_left
                student.photo_left = ''
            elif photo_type == 'right':
                photo_path = student.photo_right
                student.photo_right = ''
            
            # Delete the actual file if it exists
            if photo_path:
                full_path = os.path.join(settings.BASE_DIR, 'known_faces', photo_path)
                if os.path.exists(full_path):
                    os.remove(full_path)
            
            student.save()
            messages.success(request, f'{photo_type.title()} photo deleted successfully!')
        else:
            messages.error(request, 'Invalid photo type')
    
    return redirect('dashboard')


@login_required
def timetable_view(request):
    """View the weekly timetable for the student's class"""
    try:
        student = request.user.student_profile
    except Student.DoesNotExist:
        messages.error(request, "You don't have a student profile.")
        return redirect('login')
    
    # Get all timetable entries for the student's classroom (recurring only)
    timetable_entries = Timetable.objects.filter(
        classroom=student.classroom,
        is_recurring=True
    ).select_related('subject', 'teacher', 'room').order_by('day_of_week', 'start_time')
    
    # Organize by day
    days = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday']
    timetable_by_day = {}
    for day_idx, day_name in enumerate(days):
        day_entries = timetable_entries.filter(day_of_week=day_idx)
        if day_entries.exists():
            timetable_by_day[day_name] = day_entries
    
    context = {
        'student': student,
        'timetable_by_day': timetable_by_day,
        'days': days[:5],  # Monday to Friday only for display
    }
    
    return render(request, 'core/timetable.html', context)


# ============ API Views for Face Recognition Integration ============

def api_get_active_lecture(request, classroom_id):
    """
    API endpoint to get the currently active lecture for a classroom.
    Used by face recognition system to know which lecture to mark attendance for.
    """
    try:
        classroom = Classroom.objects.get(id=classroom_id)
        active_lecture = Lecture.objects.filter(
            timetable__classroom=classroom,
            status='active'
        ).first()
        
        if active_lecture:
            return JsonResponse({
                'success': True,
                'lecture_id': active_lecture.id,
                'subject': str(active_lecture.subject),
                'teacher': str(active_lecture.teacher),
                'started_at': active_lecture.started_at.isoformat() if active_lecture.started_at else None,
            })
        else:
            return JsonResponse({
                'success': False,
                'message': 'No active lecture for this classroom'
            })
    except Classroom.DoesNotExist:
        return JsonResponse({'success': False, 'message': 'Classroom not found'})


def api_mark_attendance(request):
    """
    API endpoint to mark attendance for a student.
    Called by the face recognition system when a face is recognized.
    
    Expected POST data:
    - face_folder_name: The folder name in known_faces/ (maps to student)
    - lecture_id: ID of the active lecture
    """
    if request.method != 'POST':
        return JsonResponse({'success': False, 'message': 'POST method required'})
    
    face_folder_name = request.POST.get('face_folder_name')
    lecture_id = request.POST.get('lecture_id')
    
    if not face_folder_name or not lecture_id:
        return JsonResponse({'success': False, 'message': 'Missing required fields'})
    
    try:
        # Find student by face folder name
        student = Student.objects.get(face_folder_name=face_folder_name)
        lecture = Lecture.objects.get(id=lecture_id, status='active')
        
        # Check if student belongs to this class
        if student.classroom != lecture.timetable.classroom:
            return JsonResponse({
                'success': False,
                'message': f'Student {student.name} is not in {lecture.timetable.classroom}'
            })
        
        # Mark attendance
        attendance, created = Attendance.objects.get_or_create(
            lecture=lecture,
            student=student,
            defaults={'status': 'absent'}
        )
        
        if attendance.status != 'present':
            attendance.mark_present(by_face_recognition=True)
            return JsonResponse({
                'success': True,
                'message': f'Attendance marked for {student.name}',
                'student_name': student.name,
                'roll_no': student.roll_no,
                'already_marked': False
            })
        else:
            return JsonResponse({
                'success': True,
                'message': f'{student.name} already marked present',
                'student_name': student.name,
                'roll_no': student.roll_no,
                'already_marked': True
            })
            
    except Student.DoesNotExist:
        return JsonResponse({
            'success': False,
            'message': f'No student found with face folder: {face_folder_name}'
        })
    except Lecture.DoesNotExist:
        return JsonResponse({
            'success': False,
            'message': 'Lecture not found or not active'
        })


def api_start_lecture(request):
    """
    API endpoint to start a lecture.
    Can be called manually or based on timetable.
    
    POST data:
    - timetable_id: ID of the timetable entry
    OR
    - classroom_id: Classroom ID (will find timetable based on current day/time)
    """
    if request.method != 'POST':
        return JsonResponse({'success': False, 'message': 'POST method required'})
    
    timetable_id = request.POST.get('timetable_id')
    classroom_id = request.POST.get('classroom_id')
    
    try:
        if timetable_id:
            timetable = Timetable.objects.get(id=timetable_id)
        elif classroom_id:
            # Find timetable entry for current day/time
            now = timezone.now()
            current_time = now.time()
            day_of_week = now.weekday()
            
            timetable = Timetable.objects.filter(
                classroom_id=classroom_id,
                day_of_week=day_of_week,
                start_time__lte=current_time,
                end_time__gte=current_time
            ).first()
            
            if not timetable:
                return JsonResponse({
                    'success': False,
                    'message': 'No scheduled lecture at this time for this classroom'
                })
        else:
            return JsonResponse({
                'success': False,
                'message': 'Provide timetable_id or classroom_id'
            })
        
        # Create or get lecture for today
        today = timezone.now().date()
        lecture, created = Lecture.objects.get_or_create(
            timetable=timetable,
            date=today,
            defaults={'status': 'scheduled'}
        )
        
        if lecture.status == 'active':
            return JsonResponse({
                'success': True,
                'message': 'Lecture already active',
                'lecture_id': lecture.id,
                'already_started': True
            })
        
        lecture.start_lecture()
        
        return JsonResponse({
            'success': True,
            'message': f'Lecture started: {timetable.subject} for {timetable.classroom}',
            'lecture_id': lecture.id,
            'subject': str(timetable.subject),
            'classroom': str(timetable.classroom),
            'already_started': False
        })
        
    except Timetable.DoesNotExist:
        return JsonResponse({'success': False, 'message': 'Timetable entry not found'})


def api_end_lecture(request):
    """API endpoint to end a lecture"""
    if request.method != 'POST':
        return JsonResponse({'success': False, 'message': 'POST method required'})
    
    lecture_id = request.POST.get('lecture_id')
    
    try:
        lecture = Lecture.objects.get(id=lecture_id)
        lecture.end_lecture()
        
        # Get attendance summary
        total = lecture.attendance_records.count()
        present = lecture.attendance_records.filter(status='present').count()
        
        return JsonResponse({
            'success': True,
            'message': 'Lecture ended',
            'total_students': total,
            'present': present,
            'absent': total - present
        })
    except Lecture.DoesNotExist:
        return JsonResponse({'success': False, 'message': 'Lecture not found'})


def api_get_todays_schedule(request, classroom_id):
    """Get today's schedule for a classroom"""
    try:
        classroom = Classroom.objects.get(id=classroom_id)
        today = timezone.now()
        day_of_week = today.weekday()
        
        schedule = Timetable.objects.filter(
            classroom=classroom,
            day_of_week=day_of_week
        ).order_by('start_time')
        
        schedule_data = []
        for entry in schedule:
            # Check if lecture exists for today
            lecture = Lecture.objects.filter(
                timetable=entry,
                date=today.date()
            ).first()
            
            schedule_data.append({
                'timetable_id': entry.id,
                'subject': str(entry.subject),
                'teacher': str(entry.teacher),
                'start_time': entry.start_time.strftime('%H:%M'),
                'end_time': entry.end_time.strftime('%H:%M'),
                'lecture_id': lecture.id if lecture else None,
                'lecture_status': lecture.status if lecture else 'not_started'
            })
        
        return JsonResponse({
            'success': True,
            'classroom': str(classroom),
            'day': today.strftime('%A'),
            'date': today.date().isoformat(),
            'schedule': schedule_data
        })
    except Classroom.DoesNotExist:
        return JsonResponse({'success': False, 'message': 'Classroom not found'})


# =====================
# TEACHER VIEWS
# =====================

def teacher_login(request):
    """Login view for teachers"""
    if request.user.is_authenticated:
        if hasattr(request.user, 'teacher_profile'):
            return redirect('teacher_dashboard')
        elif hasattr(request.user, 'student_profile'):
            return redirect('dashboard')
        elif request.user.is_staff:
            return redirect('/admin/')
        logout(request)
    
    if request.method == 'POST':
        form = TeacherLoginForm(request.POST)
        if form.is_valid():
            user = form.cleaned_data.get('user')
            if user:
                login(request, user)
                messages.success(request, f'Welcome, {user.teacher_profile.name}!')
                return redirect('teacher_dashboard')
    else:
        form = TeacherLoginForm()
    
    return render(request, 'core/teacher/login.html', {'form': form})


def get_teacher_or_redirect(request):
    """Helper to get teacher profile or redirect"""
    try:
        return request.user.teacher_profile
    except (Teacher.DoesNotExist, AttributeError):
        return None


@login_required
def teacher_dashboard(request):
    """Teacher dashboard showing their lectures"""
    teacher = get_teacher_or_redirect(request)
    if not teacher:
        messages.error(request, "You don't have a teacher profile.")
        logout(request)
        return redirect('teacher_login')
    
    today = timezone.now().date()
    tomorrow = today + timedelta(days=1)
    current_time = timezone.now().time()
    day_of_week = today.weekday()
    tomorrow_day_of_week = tomorrow.weekday()
    
    # Get today's timetable for this teacher (recurring + today's extras, excluding cancelled)
    from django.db.models import Q
    todays_recurring = Timetable.objects.filter(
        teacher=teacher, 
        day_of_week=day_of_week, 
        is_recurring=True
    ).exclude(cancellations__date=today)
    
    todays_extras = Timetable.objects.filter(
        teacher=teacher, 
        is_recurring=False, 
        extra_date=today
    )
    
    todays_schedule = (todays_recurring | todays_extras).order_by('start_time')
    
    # Prepare schedule with lecture status
    schedule_with_status = []
    for entry in todays_schedule:
        lecture = Lecture.objects.filter(timetable=entry, date=today).first()
        
        # Determine if class is current, upcoming, or past
        is_current = entry.start_time <= current_time <= entry.end_time
        is_past = entry.end_time < current_time
        
        schedule_with_status.append({
            'timetable': entry,
            'lecture': lecture,
            'is_current': is_current,
            'is_past': is_past,
            'can_start': not lecture and (is_current or not is_past),
            'can_manage': lecture is not None,
            'is_extra': not entry.is_recurring,
        })
    
    # Get tomorrow's schedule (recurring, excluding cancelled)
    tomorrows_recurring = Timetable.objects.filter(
        teacher=teacher,
        day_of_week=tomorrow_day_of_week,
        is_recurring=True
    ).exclude(cancellations__date=tomorrow)
    
    tomorrows_extras = Timetable.objects.filter(
        teacher=teacher,
        is_recurring=False,
        extra_date=tomorrow
    )
    
    tomorrows_schedule = (tomorrows_recurring | tomorrows_extras).order_by('start_time')
    
    # Get cancelled lectures for today
    cancelled_today = CancelledLecture.objects.filter(
        timetable__teacher=teacher,
        date=today
    ).select_related('timetable', 'timetable__subject', 'timetable__classroom')
    
    # Get recent lectures (past 7 days)
    recent_lectures = Lecture.objects.filter(
        timetable__teacher=teacher,
        date__gte=today - timedelta(days=7)
    ).order_by('-date', '-started_at')[:10]
    
    # Get upcoming schedule (this week) - recurring only
    all_timetable = Timetable.objects.filter(teacher=teacher, is_recurring=True).order_by('day_of_week', 'start_time')
    
    context = {
        'teacher': teacher,
        'todays_schedule': schedule_with_status,
        'tomorrows_schedule': tomorrows_schedule,
        'cancelled_today': cancelled_today,
        'recent_lectures': recent_lectures,
        'all_timetable': all_timetable,
        'today': today,
        'tomorrow': tomorrow,
        'current_time': current_time,
    }
    
    return render(request, 'core/teacher/dashboard.html', context)


@login_required
def teacher_start_lecture(request, timetable_id):
    """Start a lecture from timetable"""
    teacher = get_teacher_or_redirect(request)
    if not teacher:
        messages.error(request, "Access denied.")
        return redirect('teacher_login')
    
    timetable = get_object_or_404(Timetable, id=timetable_id, teacher=teacher)
    today = timezone.now().date()
    
    # Check if lecture already exists
    lecture, created = Lecture.objects.get_or_create(
        timetable=timetable,
        date=today,
        defaults={'status': 'scheduled'}
    )
    
    if lecture.status == 'scheduled':
        result = lecture.start_lecture()
        messages.success(request, f'Lecture started! {result}')
    elif lecture.status == 'active':
        messages.info(request, 'Lecture is already active.')
    else:
        messages.warning(request, f'Lecture status is: {lecture.status}')
    
    return redirect('teacher_manage_attendance', lecture_id=lecture.id)


@login_required
def teacher_end_lecture(request, lecture_id):
    """End a lecture"""
    teacher = get_teacher_or_redirect(request)
    if not teacher:
        messages.error(request, "Access denied.")
        return redirect('teacher_login')
    
    lecture = get_object_or_404(Lecture, id=lecture_id, timetable__teacher=teacher)
    
    if lecture.status == 'active':
        lecture.end_lecture()
        messages.success(request, 'Lecture ended successfully.')
    else:
        messages.warning(request, f'Cannot end lecture with status: {lecture.status}')
    
    return redirect('teacher_dashboard')


@login_required
def teacher_manage_attendance(request, lecture_id):
    """Manage attendance for a lecture with multi-select"""
    teacher = get_teacher_or_redirect(request)
    if not teacher:
        messages.error(request, "Access denied.")
        return redirect('teacher_login')
    
    lecture = get_object_or_404(Lecture, id=lecture_id, timetable__teacher=teacher)
    
    if request.method == 'POST':
        # Get list of present students
        present_ids = request.POST.getlist('present_students')
        
        # Update all attendance records
        for attendance in lecture.attendance_records.all():
            if str(attendance.student.id) in present_ids:
                if attendance.status != 'present':
                    attendance.status = 'present'
                    attendance.marked_at = timezone.now()
                    attendance.marked_by_face_recognition = False
                    attendance.save()
            else:
                if attendance.status != 'absent':
                    attendance.status = 'absent'
                    attendance.marked_at = None
                    attendance.marked_by_face_recognition = False
                    attendance.save()
        
        messages.success(request, 'Attendance updated successfully!')
        return redirect('teacher_manage_attendance', lecture_id=lecture_id)
    
    # Get attendance records
    attendance_records = lecture.attendance_records.select_related('student').order_by('student__roll_no')
    
    # Count stats
    total = attendance_records.count()
    present = attendance_records.filter(status='present').count()
    absent = total - present
    
    context = {
        'teacher': teacher,
        'lecture': lecture,
        'attendance_records': attendance_records,
        'total': total,
        'present': present,
        'absent': absent,
        'percentage': round(present / total * 100, 1) if total > 0 else 0,
    }
    
    return render(request, 'core/teacher/manage_attendance.html', context)


@login_required
def teacher_lecture_history(request):
    """View all past lectures for a teacher"""
    teacher = get_teacher_or_redirect(request)
    if not teacher:
        messages.error(request, "Access denied.")
        return redirect('teacher_login')
    
    # Get filter parameters
    classroom_filter = request.GET.get('classroom', '')
    subject_filter = request.GET.get('subject', '')
    date_from = request.GET.get('date_from', '')
    date_to = request.GET.get('date_to', '')
    
    lectures = Lecture.objects.filter(
        timetable__teacher=teacher
    ).select_related('timetable', 'timetable__classroom', 'timetable__subject')
    
    if classroom_filter:
        lectures = lectures.filter(timetable__classroom_id=classroom_filter)
    if subject_filter:
        lectures = lectures.filter(timetable__subject_id=subject_filter)
    if date_from:
        lectures = lectures.filter(date__gte=date_from)
    if date_to:
        lectures = lectures.filter(date__lte=date_to)
    
    lectures = lectures.order_by('-date', '-started_at')
    
    # Get filter options
    classrooms = Classroom.objects.filter(timetable_entries__teacher=teacher).distinct()
    subjects = Subject.objects.filter(timetable_entries__teacher=teacher).distinct()
    
    context = {
        'teacher': teacher,
        'lectures': lectures,
        'classrooms': classrooms,
        'subjects': subjects,
        'filters': {
            'classroom': classroom_filter,
            'subject': subject_filter,
            'date_from': date_from,
            'date_to': date_to,
        }
    }
    
    return render(request, 'core/teacher/lecture_history.html', context)


@login_required
def teacher_schedule_extra(request):
    """Schedule an extra lecture"""
    teacher = get_teacher_or_redirect(request)
    if not teacher:
        messages.error(request, "Access denied.")
        return redirect('teacher_login')
    
    if request.method == 'POST':
        form = ScheduleExtraLectureForm(request.POST)
        if form.is_valid():
            # Create a one-time timetable entry (not recurring)
            timetable = Timetable.objects.create(
                room=form.cleaned_data['room'],
                classroom=form.cleaned_data['classroom'],
                subject=form.cleaned_data['subject'],
                teacher=teacher,
                day_of_week=form.cleaned_data['date'].weekday(),
                start_time=form.cleaned_data['start_time'],
                end_time=form.cleaned_data['end_time'],
                is_recurring=False,
                extra_date=form.cleaned_data['date'],
            )
            
            # Create the lecture for that specific date
            lecture = Lecture.objects.create(
                timetable=timetable,
                date=form.cleaned_data['date'],
                status='scheduled'
            )
            
            messages.success(request, f'Extra lecture scheduled for {form.cleaned_data["classroom"]} on {form.cleaned_data["date"]}')
            return redirect('teacher_dashboard')
    else:
        # Default date to today
        form = ScheduleExtraLectureForm(initial={'date': timezone.now().date()})
    
    context = {
        'teacher': teacher,
        'form': form,
    }
    
    return render(request, 'core/teacher/schedule_extra.html', context)


@login_required  
def teacher_timetable(request):
    """View teacher's weekly timetable"""
    teacher = get_teacher_or_redirect(request)
    if not teacher:
        messages.error(request, "Access denied.")
        return redirect('teacher_login')
    
    # Get all timetable entries grouped by day (recurring only)
    timetable_entries = Timetable.objects.filter(teacher=teacher, is_recurring=True).order_by('day_of_week', 'start_time')
    
    # Group by day
    days = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday']
    timetable_by_day = {}
    for day_num, day_name in enumerate(days):
        entries = timetable_entries.filter(day_of_week=day_num)
        if entries.exists():
            timetable_by_day[day_name] = entries
    
    context = {
        'teacher': teacher,
        'timetable_by_day': timetable_by_day,
    }
    
    return render(request, 'core/teacher/timetable.html', context)


@login_required
def teacher_cancel_lectures(request):
    """View to cancel lectures for a specific date"""
    teacher = get_teacher_or_redirect(request)
    if not teacher:
        messages.error(request, "Access denied.")
        return redirect('teacher_login')
    
    selected_date = request.GET.get('date', timezone.now().date().isoformat())
    try:
        selected_date = datetime.strptime(selected_date, '%Y-%m-%d').date()
    except:
        selected_date = timezone.now().date()
    
    day_of_week = selected_date.weekday()
    
    # Get recurring lectures for this teacher on this day
    recurring_lectures = Timetable.objects.filter(
        teacher=teacher,
        day_of_week=day_of_week,
        is_recurring=True
    ).order_by('start_time')
    
    # Check which ones are already cancelled
    lectures_with_status = []
    for timetable in recurring_lectures:
        is_cancelled = CancelledLecture.objects.filter(
            timetable=timetable,
            date=selected_date
        ).exists()
        lectures_with_status.append({
            'timetable': timetable,
            'is_cancelled': is_cancelled,
        })
    
    # Handle cancel/uncancel actions
    if request.method == 'POST':
        action = request.POST.get('action')
        timetable_id = request.POST.get('timetable_id')
        reason = request.POST.get('reason', '')
        
        try:
            timetable = Timetable.objects.get(id=timetable_id, teacher=teacher)
            
            if action == 'cancel':
                CancelledLecture.objects.get_or_create(
                    timetable=timetable,
                    date=selected_date,
                    defaults={
                        'reason': reason,
                        'cancelled_by': teacher
                    }
                )
                messages.success(request, f'Lecture cancelled for {selected_date}')
            elif action == 'uncancel':
                CancelledLecture.objects.filter(
                    timetable=timetable,
                    date=selected_date
                ).delete()
                messages.success(request, f'Lecture restored for {selected_date}')
                
        except Timetable.DoesNotExist:
            messages.error(request, 'Lecture not found')
        
        return redirect(f"{request.path}?date={selected_date.isoformat()}")
    
    context = {
        'teacher': teacher,
        'selected_date': selected_date,
        'day_name': ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday'][day_of_week],
        'lectures_with_status': lectures_with_status,
    }
    
    return render(request, 'core/teacher/cancel_lectures.html', context)
