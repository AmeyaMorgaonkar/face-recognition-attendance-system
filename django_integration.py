"""
Django integration helper for face recognition system.
Provides functions to interact with the Django database.
"""

import os
import sys
import requests
from urllib.parse import urljoin

# Django server URL
DJANGO_SERVER_URL = "http://127.0.0.1:8000"


class AttendanceAPI:
    """
    Helper class to interact with Django attendance system API.
    Used by the face recognition system to mark attendance.
    """
    
    def __init__(self, base_url=DJANGO_SERVER_URL):
        self.base_url = base_url
        self.session = requests.Session()
        self.active_lecture_id = None
        self.active_classroom_id = None
    
    def get_active_lecture(self, classroom_id):
        """Get the currently active lecture for a classroom"""
        try:
            url = urljoin(self.base_url, f'/api/active-lecture/{classroom_id}/')
            response = self.session.get(url)
            data = response.json()
            
            if data.get('success'):
                self.active_lecture_id = data.get('lecture_id')
                self.active_classroom_id = classroom_id
                return data
            return None
        except Exception as e:
            print(f"Error getting active lecture: {e}")
            return None
    
    def start_lecture(self, timetable_id=None, classroom_id=None):
        """Start a lecture based on timetable or classroom"""
        try:
            url = urljoin(self.base_url, '/api/start-lecture/')
            data = {}
            if timetable_id:
                data['timetable_id'] = timetable_id
            elif classroom_id:
                data['classroom_id'] = classroom_id
            
            response = self.session.post(url, data=data)
            result = response.json()
            
            if result.get('success'):
                self.active_lecture_id = result.get('lecture_id')
                print(f"Lecture started: {result.get('message')}")
            else:
                print(f"Could not start lecture: {result.get('message')}")
            
            return result
        except Exception as e:
            print(f"Error starting lecture: {e}")
            return {'success': False, 'message': str(e)}
    
    def end_lecture(self, lecture_id=None):
        """End an active lecture"""
        lecture_id = lecture_id or self.active_lecture_id
        if not lecture_id:
            print("No active lecture to end")
            return {'success': False, 'message': 'No active lecture'}
        
        try:
            url = urljoin(self.base_url, '/api/end-lecture/')
            response = self.session.post(url, data={'lecture_id': lecture_id})
            result = response.json()
            
            if result.get('success'):
                print(f"Lecture ended. Present: {result.get('present')}/{result.get('total_students')}")
                self.active_lecture_id = None
            
            return result
        except Exception as e:
            print(f"Error ending lecture: {e}")
            return {'success': False, 'message': str(e)}
    
    def mark_attendance(self, face_folder_name, lecture_id=None):
        """
        Mark attendance for a recognized face.
        
        Args:
            face_folder_name: Name of the folder in known_faces/ (maps to student)
            lecture_id: Optional lecture ID, uses active lecture if not provided
        
        Returns:
            dict with success status and message
        """
        lecture_id = lecture_id or self.active_lecture_id
        if not lecture_id:
            return {'success': False, 'message': 'No active lecture'}
        
        try:
            url = urljoin(self.base_url, '/api/mark-attendance/')
            response = self.session.post(url, data={
                'face_folder_name': face_folder_name,
                'lecture_id': lecture_id
            })
            return response.json()
        except Exception as e:
            print(f"Error marking attendance: {e}")
            return {'success': False, 'message': str(e)}
    
    def get_schedule(self, classroom_id):
        """Get today's schedule for a classroom"""
        try:
            url = urljoin(self.base_url, f'/api/schedule/{classroom_id}/')
            response = self.session.get(url)
            return response.json()
        except Exception as e:
            print(f"Error getting schedule: {e}")
            return {'success': False, 'message': str(e)}
    
    def is_server_running(self):
        """Check if Django server is running"""
        try:
            response = self.session.get(self.base_url, timeout=2)
            return True
        except:
            return False


# Direct Django database access (for when running in same process)
def setup_django():
    """Setup Django environment for direct database access"""
    import django
    from pathlib import Path
    
    # Add project to path
    project_path = Path(__file__).resolve().parent
    if str(project_path) not in sys.path:
        sys.path.insert(0, str(project_path))
    
    os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'attendance_system.settings')
    django.setup()


class DirectAttendanceManager:
    """
    Direct database access for attendance marking.
    Use this when running Django and face recognition in same process.
    """
    
    def __init__(self):
        setup_django()
        from core.models import Student, Lecture, Attendance, Classroom, Timetable
        self.Student = Student
        self.Lecture = Lecture
        self.Attendance = Attendance
        self.Classroom = Classroom
        self.Timetable = Timetable
        self.active_lecture = None
    
    def get_active_lecture(self, classroom_id):
        """Get active lecture for a classroom"""
        try:
            classroom = self.Classroom.objects.get(id=classroom_id)
            self.active_lecture = self.Lecture.objects.filter(
                timetable__classroom=classroom,
                status='active'
            ).first()
            return self.active_lecture
        except self.Classroom.DoesNotExist:
            return None
    
    def start_lecture_by_timetable(self, timetable_id):
        """Start a lecture from a timetable entry"""
        from django.utils import timezone
        
        try:
            timetable = self.Timetable.objects.get(id=timetable_id)
            today = timezone.now().date()
            
            lecture, created = self.Lecture.objects.get_or_create(
                timetable=timetable,
                date=today,
                defaults={'status': 'scheduled'}
            )
            
            if lecture.status != 'active':
                lecture.start_lecture()
            
            self.active_lecture = lecture
            return lecture
        except self.Timetable.DoesNotExist:
            return None
    
    def mark_attendance(self, face_folder_name):
        """Mark attendance for a student by face folder name"""
        if not self.active_lecture:
            return {'success': False, 'message': 'No active lecture'}
        
        try:
            student = self.Student.objects.get(face_folder_name=face_folder_name)
            
            # Verify student belongs to this class
            if student.classroom != self.active_lecture.timetable.classroom:
                return {
                    'success': False,
                    'message': f'{student.name} is not in this class'
                }
            
            attendance, created = self.Attendance.objects.get_or_create(
                lecture=self.active_lecture,
                student=student,
                defaults={'status': 'absent'}
            )
            
            if attendance.status != 'present':
                attendance.mark_present(by_face_recognition=True)
                return {
                    'success': True,
                    'message': f'Marked {student.name} present',
                    'student_name': student.name,
                    'already_marked': False
                }
            else:
                return {
                    'success': True,
                    'message': f'{student.name} already marked',
                    'student_name': student.name,
                    'already_marked': True
                }
                
        except self.Student.DoesNotExist:
            return {
                'success': False,
                'message': f'No student with face folder: {face_folder_name}'
            }
    
    def end_lecture(self):
        """End the current lecture"""
        if self.active_lecture:
            self.active_lecture.end_lecture()
            self.active_lecture = None
            return True
        return False
    
    def get_classrooms(self):
        """Get all classrooms"""
        return list(self.Classroom.objects.all().values('id', 'name'))
    
    def get_todays_timetable(self, classroom_id):
        """Get today's timetable for a classroom"""
        from django.utils import timezone
        
        today = timezone.now()
        day_of_week = today.weekday()
        
        return list(self.Timetable.objects.filter(
            classroom_id=classroom_id,
            day_of_week=day_of_week
        ).values(
            'id', 'subject__name', 'teacher__name', 
            'start_time', 'end_time'
        ).order_by('start_time'))
