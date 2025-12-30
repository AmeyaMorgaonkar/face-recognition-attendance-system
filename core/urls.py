from django.urls import path
from . import views

urlpatterns = [
    # Auth URLs
    path('', views.student_login, name='login'),
    path('login/', views.student_login, name='login'),
    path('logout/', views.logout_view, name='logout'),
    
    # Student Dashboard
    path('dashboard/', views.dashboard, name='dashboard'),
    path('attendance/history/', views.attendance_history, name='attendance_history'),
    path('timetable/', views.timetable_view, name='timetable'),
    
    # Photo upload/delete
    path('upload-photo/', views.upload_photo, name='upload_photo'),
    path('delete-photo/', views.delete_photo, name='delete_photo'),
    
    # Teacher Portal
    path('teacher/', views.teacher_login, name='teacher_login'),
    path('teacher/login/', views.teacher_login, name='teacher_login'),
    path('teacher/dashboard/', views.teacher_dashboard, name='teacher_dashboard'),
    path('teacher/timetable/', views.teacher_timetable, name='teacher_timetable'),
    path('teacher/lectures/', views.teacher_lecture_history, name='teacher_lecture_history'),
    path('teacher/schedule-extra/', views.teacher_schedule_extra, name='teacher_schedule_extra'),
    path('teacher/start-lecture/<int:timetable_id>/', views.teacher_start_lecture, name='teacher_start_lecture'),
    path('teacher/end-lecture/<int:lecture_id>/', views.teacher_end_lecture, name='teacher_end_lecture'),
    path('teacher/attendance/<int:lecture_id>/', views.teacher_manage_attendance, name='teacher_manage_attendance'),
    path('teacher/cancel-lectures/', views.teacher_cancel_lectures, name='teacher_cancel_lectures'),
    
    # API endpoints for face recognition integration
    path('api/active-lecture/<int:classroom_id>/', views.api_get_active_lecture, name='api_active_lecture'),
    path('api/mark-attendance/', views.api_mark_attendance, name='api_mark_attendance'),
    path('api/start-lecture/', views.api_start_lecture, name='api_start_lecture'),
    path('api/end-lecture/', views.api_end_lecture, name='api_end_lecture'),
    path('api/schedule/<int:classroom_id>/', views.api_get_todays_schedule, name='api_schedule'),
]
