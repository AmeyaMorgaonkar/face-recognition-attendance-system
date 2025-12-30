"""
Database Models for Face Recognition Attendance System

Database Design:
- Room: Physical room with a camera (Room 1, Room 2, etc.)
- Classroom: Student division/section (CS-A, IT-B) - students belong here
- Student: Stores student info (roll_no, name, linked to Django User for login)
- Subject: Subject names
- Teacher: Teacher info
- Timetable: Weekly schedule - Room + Day + Time → which Classroom has which Subject
- Lecture: Active/completed lecture instance for a specific date
- Attendance: Individual attendance records per student per lecture

Flow:
- Camera is placed in a Room
- Timetable defines which Classroom uses which Room at what time
- Back-to-back lectures for same Classroom in same Room carry forward attendance
"""

from django.db import models
from django.contrib.auth.models import User
from django.utils import timezone


class Room(models.Model):
    """Physical room where camera is placed"""
    name = models.CharField(max_length=50, unique=True)  # e.g., "Room 101", "Lab 1"
    description = models.TextField(blank=True)
    camera_index = models.IntegerField(default=0, help_text="Camera index for cv2.VideoCapture (0 for default)")
    
    def __str__(self):
        return self.name
    
    class Meta:
        ordering = ['name']


class Classroom(models.Model):
    """Represents a student division/section like CS-A, CS-B, IT-A, etc."""
    name = models.CharField(max_length=50, unique=True)  # e.g., "CS-A", "IT-B"
    description = models.TextField(blank=True)
    
    def __str__(self):
        return self.name
    
    class Meta:
        ordering = ['name']


class Student(models.Model):
    """Student model linked to Django User for authentication"""
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='student_profile')
    roll_no = models.CharField(max_length=20, unique=True)
    name = models.CharField(max_length=100)
    classroom = models.ForeignKey(Classroom, on_delete=models.CASCADE, related_name='students')
    face_folder_name = models.CharField(max_length=100, blank=True, help_text="Folder name in known_faces/")
    
    # Photo paths (stored relative to known_faces folder)
    photo_straight = models.CharField(max_length=255, blank=True, help_text="Front-facing photo path")
    photo_left = models.CharField(max_length=255, blank=True, help_text="Looking left photo path")
    photo_right = models.CharField(max_length=255, blank=True, help_text="Looking right photo path")
    
    def get_profile_photo_url(self):
        """Get the straight photo as profile photo"""
        if self.photo_straight:
            return f'/media/known_faces/{self.photo_straight}'
        return None
    
    def get_face_folder(self):
        """Get the folder name for this student's face photos"""
        # Format: DivisionName_RollNo (e.g., CS-A_001)
        return f"{self.classroom.name}_{self.roll_no}"
    
    def __str__(self):
        return f"{self.roll_no} - {self.name}"
    
    class Meta:
        ordering = ['roll_no']


class Teacher(models.Model):
    """Teacher model"""
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='teacher_profile', null=True, blank=True)
    name = models.CharField(max_length=100)
    email = models.EmailField(blank=True)
    
    def __str__(self):
        return self.name
    
    class Meta:
        ordering = ['name']


class Subject(models.Model):
    """Subject/Course model"""
    name = models.CharField(max_length=100)
    code = models.CharField(max_length=20, unique=True)  # e.g., "CS101"
    
    def __str__(self):
        return f"{self.code} - {self.name}"
    
    class Meta:
        ordering = ['code']


class Timetable(models.Model):
    """
    Weekly timetable entry - same every week.
    Defines which Classroom uses which Room at what time for which Subject.
    
    Example:
    - Room 101, Monday 9:00-10:00: CS-A has Data Structures with Dr. Smith
    - Room 101, Monday 10:00-11:00: CS-A has Database (back-to-back, carry forward)
    - Room 101, Monday 11:00-12:00: IT-B has OS (different class, fresh attendance)
    """
    DAYS_OF_WEEK = [
        (0, 'Monday'),
        (1, 'Tuesday'),
        (2, 'Wednesday'),
        (3, 'Thursday'),
        (4, 'Friday'),
        (5, 'Saturday'),
        (6, 'Sunday'),
    ]
    
    room = models.ForeignKey(Room, on_delete=models.CASCADE, related_name='timetable_entries', null=True, blank=True)
    classroom = models.ForeignKey(Classroom, on_delete=models.CASCADE, related_name='timetable_entries')
    subject = models.ForeignKey(Subject, on_delete=models.CASCADE, related_name='timetable_entries')
    teacher = models.ForeignKey(Teacher, on_delete=models.CASCADE, related_name='timetable_entries')
    day_of_week = models.IntegerField(choices=DAYS_OF_WEEK)
    start_time = models.TimeField()
    end_time = models.TimeField()
    is_recurring = models.BooleanField(default=True, help_text="False for extra/one-time lectures")
    extra_date = models.DateField(null=True, blank=True, help_text="Specific date for non-recurring lectures")
    
    def __str__(self):
        return f"{self.room} | {self.classroom} - {self.subject} ({self.get_day_of_week_display()} {self.start_time})"
    
    def get_previous_lecture_same_class(self):
        """
        Check if there's a lecture just before this one for the same classroom in the same room.
        Used for carrying forward attendance in back-to-back lectures.
        """
        return Timetable.objects.filter(
            room=self.room,
            classroom=self.classroom,
            day_of_week=self.day_of_week,
            end_time=self.start_time  # Previous lecture ends when this one starts
        ).first()
    
    class Meta:
        ordering = ['day_of_week', 'start_time']
        # A room can only have one class at a time
        unique_together = ['room', 'day_of_week', 'start_time']


class Lecture(models.Model):
    """
    Represents an actual lecture instance on a specific date.
    Created when a teacher starts a lecture based on the timetable.
    """
    STATUS_CHOICES = [
        ('scheduled', 'Scheduled'),
        ('active', 'Active'),  # Attendance can be marked
        ('completed', 'Completed'),
        ('cancelled', 'Cancelled'),
    ]
    
    timetable = models.ForeignKey(Timetable, on_delete=models.CASCADE, related_name='lectures')
    date = models.DateField(default=timezone.now)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='scheduled')
    started_at = models.DateTimeField(null=True, blank=True)
    ended_at = models.DateTimeField(null=True, blank=True)
    carried_from = models.ForeignKey('self', on_delete=models.SET_NULL, null=True, blank=True,
                                      related_name='carried_to', 
                                      help_text="Previous lecture from which attendance was carried forward")
    
    def __str__(self):
        return f"{self.timetable.subject} - {self.timetable.classroom} @ {self.timetable.room} ({self.date})"
    
    def start_lecture(self, carry_forward=True):
        """
        Start the lecture and enable attendance marking.
        If carry_forward=True, check for back-to-back lecture and copy attendance.
        """
        self.status = 'active'
        self.started_at = timezone.now()
        self.save()
        
        # Check for previous back-to-back lecture of same class
        previous_timetable = self.timetable.get_previous_lecture_same_class()
        previous_lecture = None
        
        if carry_forward and previous_timetable:
            previous_lecture = Lecture.objects.filter(
                timetable=previous_timetable,
                date=self.date,
                status='completed'
            ).first()
        
        if previous_lecture:
            # Carry forward attendance from previous lecture
            self.carried_from = previous_lecture
            self.save()
            
            for prev_attendance in previous_lecture.attendance_records.all():
                Attendance.objects.get_or_create(
                    lecture=self,
                    student=prev_attendance.student,
                    defaults={
                        'status': prev_attendance.status,
                        'marked_at': prev_attendance.marked_at,
                        'marked_by_face_recognition': prev_attendance.marked_by_face_recognition
                    }
                )
            return f"Carried forward {previous_lecture.attendance_records.count()} attendance records"
        else:
            # Create fresh attendance records (default absent)
            students = self.timetable.classroom.students.all()
            for student in students:
                Attendance.objects.get_or_create(
                    lecture=self,
                    student=student,
                    defaults={'status': 'absent'}
                )
            return f"Created fresh attendance for {students.count()} students"
    
    def end_lecture(self):
        """End the lecture"""
        self.status = 'completed'
        self.ended_at = timezone.now()
        self.save()
    
    @property
    def room(self):
        return self.timetable.room
    
    @property
    def classroom(self):
        return self.timetable.classroom
    
    @property
    def subject(self):
        return self.timetable.subject
    
    @property
    def teacher(self):
        return self.timetable.teacher
    
    class Meta:
        ordering = ['-date', '-started_at']
        unique_together = ['timetable', 'date']


class Attendance(models.Model):
    """
    Individual attendance record for a student in a lecture.
    This design is much better than storing as dict because:
    - Easy to query by student, date, subject, etc.
    - Proper foreign key relationships
    - Can add additional fields like marked_by, marked_at, etc.
    """
    STATUS_CHOICES = [
        ('present', 'Present'),
        ('absent', 'Absent'),
        ('late', 'Late'),
    ]
    
    lecture = models.ForeignKey(Lecture, on_delete=models.CASCADE, related_name='attendance_records')
    student = models.ForeignKey(Student, on_delete=models.CASCADE, related_name='attendance_records')
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default='absent')
    marked_at = models.DateTimeField(null=True, blank=True)
    marked_by_face_recognition = models.BooleanField(default=False)
    
    def mark_present(self, by_face_recognition=False):
        """Mark student as present"""
        self.status = 'present'
        self.marked_at = timezone.now()
        self.marked_by_face_recognition = by_face_recognition
        self.save()
    
    def __str__(self):
        return f"{self.student.roll_no} - {self.lecture} - {self.status}"
    
    class Meta:
        unique_together = ['lecture', 'student']
        ordering = ['student__roll_no']


class CancelledLecture(models.Model):
    """
    Tracks cancelled lectures for specific dates.
    This allows soft-cancellation without removing from weekly timetable.
    """
    timetable = models.ForeignKey(Timetable, on_delete=models.CASCADE, related_name='cancellations')
    date = models.DateField(help_text="The specific date this lecture is cancelled")
    reason = models.CharField(max_length=255, blank=True)
    cancelled_by = models.ForeignKey(Teacher, on_delete=models.SET_NULL, null=True, blank=True)
    cancelled_at = models.DateTimeField(auto_now_add=True)
    
    def __str__(self):
        return f"{self.timetable.subject} cancelled on {self.date}"
    
    class Meta:
        unique_together = ['timetable', 'date']
        ordering = ['-date']
