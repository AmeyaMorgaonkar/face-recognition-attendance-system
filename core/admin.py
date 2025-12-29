from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from .models import Room, Student, Classroom, Teacher, Subject, Timetable, Lecture, Attendance


@admin.register(Room)
class RoomAdmin(admin.ModelAdmin):
    list_display = ['name', 'description', 'camera_index']
    search_fields = ['name']


@admin.register(Classroom)
class ClassroomAdmin(admin.ModelAdmin):
    list_display = ['name', 'description', 'student_count']
    search_fields = ['name']
    
    def student_count(self, obj):
        return obj.students.count()
    student_count.short_description = 'Students'


@admin.register(Student)
class StudentAdmin(admin.ModelAdmin):
    list_display = ['roll_no', 'name', 'classroom', 'face_folder_name', 'user']
    list_filter = ['classroom']
    search_fields = ['roll_no', 'name']
    autocomplete_fields = ['user', 'classroom']


@admin.register(Teacher)
class TeacherAdmin(admin.ModelAdmin):
    list_display = ['name', 'email']
    search_fields = ['name', 'email']


@admin.register(Subject)
class SubjectAdmin(admin.ModelAdmin):
    list_display = ['code', 'name']
    search_fields = ['code', 'name']


@admin.register(Timetable)
class TimetableAdmin(admin.ModelAdmin):
    list_display = ['room', 'classroom', 'subject', 'teacher', 'day_of_week', 'start_time', 'end_time']
    list_filter = ['room', 'classroom', 'day_of_week', 'subject', 'teacher']
    search_fields = ['room__name', 'classroom__name', 'subject__name', 'teacher__name']


@admin.register(Lecture)
class LectureAdmin(admin.ModelAdmin):
    list_display = ['date', 'room', 'classroom', 'subject', 'teacher', 'status', 'started_at', 'carried_from']
    list_filter = ['status', 'date', 'timetable__room', 'timetable__classroom']
    search_fields = ['timetable__subject__name', 'timetable__classroom__name', 'timetable__room__name']
    date_hierarchy = 'date'
    
    def room(self, obj):
        return obj.timetable.room
    
    def classroom(self, obj):
        return obj.timetable.classroom
    
    def subject(self, obj):
        return obj.timetable.subject
    
    def teacher(self, obj):
        return obj.timetable.teacher


@admin.register(Attendance)
class AttendanceAdmin(admin.ModelAdmin):
    list_display = ['student', 'lecture', 'status', 'marked_at', 'marked_by_face_recognition']
    list_filter = ['status', 'marked_by_face_recognition', 'lecture__date', 'lecture__timetable__room']
    search_fields = ['student__roll_no', 'student__name']
    autocomplete_fields = ['student', 'lecture']
