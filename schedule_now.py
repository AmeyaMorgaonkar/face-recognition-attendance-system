import os
import sys
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'attendance_system.settings')
django.setup()

from core.models import Room, Classroom, Subject, Teacher, Timetable, Lecture
from django.utils import timezone
import datetime

def schedule_lecture(division='CS-A', duration_minutes=5):
    """Schedule a lecture starting now (as a one-time extra lecture)."""
    now = timezone.localtime()
    today = now.date()
    
    # Get or use defaults
    room = Room.objects.first()
    classroom = Classroom.objects.filter(name=division).first()
    subject = Subject.objects.first()
    teacher = Teacher.objects.first()
    
    if not all([room, classroom, subject, teacher]):
        print("Error: Missing required data. Run setup_sample_data() first.")
        return None
    
    # Calculate times
    start_time = datetime.time(now.hour, now.minute)
    end_minute = now.minute + duration_minutes
    end_hour = now.hour
    if end_minute >= 60:
        end_minute -= 60
        end_hour += 1
    end_time = datetime.time(end_hour, end_minute)
    
    # Create new one-time entry (not recurring, won't affect weekly timetable)
    t = Timetable.objects.create(
        room=room,
        classroom=classroom,
        day_of_week=now.weekday(),
        start_time=start_time,
        end_time=end_time,
        subject=subject,
        teacher=teacher,
        is_recurring=False,
        extra_date=today,
    )
    
    # Also create the Lecture entry so it's ready
    lecture = Lecture.objects.create(
        timetable=t,
        date=today,
        status='scheduled'
    )
    
    print(f"\n✅ Extra Lecture Scheduled (won't affect weekly timetable)")
    print(f"   Class: {classroom.name}")
    print(f"   Subject: {subject.name}")
    print(f"   Time: {start_time.strftime('%I:%M %p')} - {end_time.strftime('%I:%M %p')}")
    print(f"   Room: {room.name}")
    print(f"   Date: {today} (one-time only)")
    print(f"\n👉 Run 'python main.py' to start face recognition!\n")
    
    return t

if __name__ == '__main__':
    # Default: CS-A for 5 minutes
    division = sys.argv[1] if len(sys.argv) > 1 else 'CS-A'
    duration = int(sys.argv[2]) if len(sys.argv) > 2 else 5
    
    print(f"\nScheduling {division} lecture for {duration} minutes...")
    schedule_lecture(division, duration)
