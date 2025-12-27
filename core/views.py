"""
Views for the Attendance System
"""

from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth import login, logout
from django.contrib.auth.decorators import login_required
from django.contrib.auth.views import LoginView
from django.contrib import messages
from django.http import JsonResponse
from django.utils import timezone
from django.db.models import Count, Q
from datetime import datetime, timedelta

from .models import Student, Classroom, Timetable, Lecture, Attendance, Subject
from .forms import StudentLoginForm


class StudentLoginView(LoginView):
    """Login view for students"""
    template_name = 'core/login.html'
    authentication_form = StudentLoginForm
    redirect_authenticated_user = False  # Handle manually to avoid redirect loops
    
    def dispatch(self, request, *args, **kwargs):
        # If already authenticated, redirect appropriately
        if request.user.is_authenticated:
            if hasattr(request.user, 'student_profile'):
                return redirect('/dashboard/')
            elif request.user.is_staff:
                return redirect('/admin/')
            # User is logged in but has no profile - log them out
            logout(request)
        return super().dispatch(request, *args, **kwargs)
    
    def get_success_url(self):
        # Check if user has student profile
        if hasattr(self.request.user, 'student_profile'):
            return '/dashboard/'
        elif self.request.user.is_staff:
            return '/admin/'
        return '/dashboard/'


def logout_view(request):
    """Logout view"""
    logout(request)
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
    
    # Get today's schedule
    today = timezone.now().date()
    day_of_week = today.weekday()
    todays_schedule = Timetable.objects.filter(
        classroom=student.classroom,
        day_of_week=day_of_week
    ).order_by('start_time')
    
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
