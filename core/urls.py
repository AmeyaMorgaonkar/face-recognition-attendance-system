from django.urls import path
from . import views

urlpatterns = [
    # Auth URLs
    path('', views.StudentLoginView.as_view(), name='login'),
    path('login/', views.StudentLoginView.as_view(), name='login'),
    path('logout/', views.logout_view, name='logout'),
    
    # Student Dashboard
    path('dashboard/', views.dashboard, name='dashboard'),
    path('attendance/history/', views.attendance_history, name='attendance_history'),
    
    # API endpoints for face recognition integration
    path('api/active-lecture/<int:classroom_id>/', views.api_get_active_lecture, name='api_active_lecture'),
    path('api/mark-attendance/', views.api_mark_attendance, name='api_mark_attendance'),
    path('api/start-lecture/', views.api_start_lecture, name='api_start_lecture'),
    path('api/end-lecture/', views.api_end_lecture, name='api_end_lecture'),
    path('api/schedule/<int:classroom_id>/', views.api_get_todays_schedule, name='api_schedule'),
]
