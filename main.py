#!/usr/bin/env python
"""
Main entry point for Face Recognition Attendance System with Django integration.

Usage:
    python main.py                    # Run face recognition (manual mode)
    python main.py auto <classroom>   # Auto mode - monitors timetable, starts 15min before lecture
    python main.py runserver          # Start Django web server
    python main.py migrate            # Run database migrations
    python main.py createsuperuser    # Create admin user
    python main.py setup              # Initial setup (migrate + create sample data)
    python main.py shell              # Django shell
"""

import sys
import os
from datetime import datetime, timedelta, time as dt_time
import time as time_module

# Add project to path and setup Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'attendance_system.settings')


def run_django_command(args):
    """Run Django management commands"""
    from django.core.management import execute_from_command_line
    execute_from_command_line(['manage.py'] + args)


def run_face_recognition():
    """
    Run the face recognition attendance system - FULLY AUTOMATIC.
    
    - Opens camera immediately (uses Room 101 by default)
    - Automatically detects which lecture is active based on current time
    - Only marks attendance for students belonging to the currently active class
    - Auto-starts and auto-ends lectures based on timetable
    - No user prompts needed
    """
    import time
    import cv2
    import functions
    from datetime import datetime, timedelta
    
    # Setup Django for database access
    import django
    django.setup()
    
    from django.utils import timezone
    from core.models import Room, Classroom, Timetable, Lecture, Attendance, Student
    
    # Initialize face recognizer
    face_recognizer = functions.FaceRecognizer(known_faces_dir="known_faces")
    
    # Try to load existing model, or train from known_faces directory
    print("Loading face recognition model...")
    if not face_recognizer.load_model():
        print("No existing model found. Training from known_faces directory...")
        face_recognizer.load_known_faces()
    print("Ready!")
    
    # Get default room (Room 101)
    try:
        room = Room.objects.get(name="Room 101")
    except Room.DoesNotExist:
        room = Room.objects.first()
        if not room:
            print("No rooms found! Run 'python main.py setup' first.")
            return
    
    print("\n" + "="*60)
    print("FACE RECOGNITION ATTENDANCE SYSTEM")
    print(f"Room: {room.name}")
    print("="*60)
    print("\nCamera will open and automatically detect lectures based on time.")
    print("Controls: 'q' to quit, 'c' to capture face, 'r' to retrain")
    print("-"*60)
    
    video = cv2.VideoCapture(room.camera_index)
    
    if not video.isOpened():
        print(f"Error: Could not open camera {room.camera_index}")
        return
    
    # State tracking
    active_lecture = None
    active_timetable = None
    marked_in_session = set()
    last_check_time = None
    
    def get_current_timetable_entry():
        """Get the timetable entry for the current time slot in this room."""
        from django.db.models import Q
        now = timezone.localtime()
        current_time = now.time()
        current_day = now.weekday()
        today = now.date()
        
        # Find timetable entry where current time is within start and end time
        # Include both recurring entries and extra lectures for today
        return Timetable.objects.filter(
            Q(room=room, day_of_week=current_day, is_recurring=True) |
            Q(room=room, is_recurring=False, extra_date=today),
            start_time__lte=current_time,
            end_time__gt=current_time
        ).select_related('classroom', 'subject', 'teacher').first()
    
    def start_lecture_for_timetable(timetable_entry):
        """Start or get existing lecture for a timetable entry."""
        today = timezone.localtime().date()
        
        # Check if lecture already exists for today
        lecture, created = Lecture.objects.get_or_create(
            timetable=timetable_entry,
            date=today,
            defaults={'status': 'scheduled'}
        )
        
        if lecture.status == 'scheduled':
            lecture.start_lecture(carry_forward=True)
            print(f"\n✓ LECTURE STARTED: {timetable_entry.subject.name}")
            print(f"  Class: {timetable_entry.classroom.name}")
            print(f"  Time: {timetable_entry.start_time} - {timetable_entry.end_time}")
        
        return lecture
    
    def end_lecture(lecture):
        """End the current lecture."""
        if lecture and lecture.status == 'active':
            lecture.end_lecture()
            print(f"\n✓ LECTURE ENDED: {lecture.timetable.subject.name}")
            # Show attendance summary
            present = lecture.attendance_records.filter(status='present').count()
            total = lecture.attendance_records.count()
            print(f"  Attendance: {present}/{total} present")
    
    def mark_attendance_for_face(face_name, lecture):
        """Mark attendance for a recognized face if they belong to the active class."""
        if not lecture or not face_name or face_name == "Unknown":
            return None
        
        try:
            student = Student.objects.get(face_folder_name=face_name)
        except Student.DoesNotExist:
            return {'success': False, 'message': f'No student found for face: {face_name}'}
        
        # Check if student belongs to the class that has this lecture
        if student.classroom != lecture.timetable.classroom:
            return {
                'success': False, 
                'message': f'{student.name} is from {student.classroom.name}, not {lecture.timetable.classroom.name}'
            }
        
        # Mark attendance
        attendance, created = Attendance.objects.get_or_create(
            lecture=lecture,
            student=student,
            defaults={'status': 'present', 'marked_at': timezone.now(), 'marked_by_face_recognition': True}
        )
        
        if not created and attendance.status != 'present':
            attendance.status = 'present'
            attendance.marked_at = timezone.now()
            attendance.marked_by_face_recognition = True
            attendance.save()
            return {'success': True, 'student_name': student.name, 'already_marked': False}
        elif created:
            return {'success': True, 'student_name': student.name, 'already_marked': False}
        else:
            return {'success': True, 'student_name': student.name, 'already_marked': True}
    
    print("\nWaiting for lectures to start...")
    
    while True:
        check, frame = video.read()
        
        if not check:
            continue
        
        now = timezone.localtime()
        
        # Check timetable every second
        if last_check_time is None or (now - last_check_time).seconds >= 1:
            last_check_time = now
            current_timetable = get_current_timetable_entry()
            
            # Handle lecture transitions
            if current_timetable != active_timetable:
                # End previous lecture if exists
                if active_lecture:
                    end_lecture(active_lecture)
                    active_lecture = None
                    marked_in_session.clear()
                
                # Start new lecture if there's a timetable entry
                if current_timetable:
                    active_timetable = current_timetable
                    active_lecture = start_lecture_for_timetable(current_timetable)
                    marked_in_session.clear()
                else:
                    active_timetable = None
                    if active_lecture:
                        print("\nNo lecture scheduled for current time. Waiting...")
        
        # Recognize faces in the frame
        frame, recognized = face_recognizer.recognize_faces(frame)
        
        # Mark attendance for recognized faces
        if active_lecture and recognized:
            for name in recognized:
                if name not in marked_in_session and name != "Unknown":
                    result = mark_attendance_for_face(name, active_lecture)
                    if result:
                        if result.get('success'):
                            if not result.get('already_marked'):
                                print(f"✓ ATTENDANCE: {result.get('student_name', name)} marked PRESENT for {active_lecture.timetable.classroom.name}")
                            marked_in_session.add(name)
                        else:
                            # Only print once per face per session
                            if name not in marked_in_session:
                                print(f"✗ {result.get('message')}")
                                marked_in_session.add(name)
        
        # Display info on frame
        if active_lecture:
            cv2.putText(frame, f"CLASS: {active_lecture.timetable.classroom.name}", (10, 30),
                       cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2)
            cv2.putText(frame, f"SUBJECT: {active_lecture.timetable.subject.name}", (10, 60),
                       cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 0), 2)
            end_time = active_lecture.timetable.end_time.strftime("%H:%M")
            cv2.putText(frame, f"Ends at: {end_time}", (10, 90),
                       cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 1)
        else:
            cv2.putText(frame, "No active lecture", (10, 30),
                       cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 0, 255), 2)
            # Show next lecture (recurring or extra for today)
            from django.db.models import Q
            today = now.date()
            next_lecture = Timetable.objects.filter(
                Q(room=room, day_of_week=now.weekday(), is_recurring=True) |
                Q(room=room, is_recurring=False, extra_date=today),
                start_time__gt=now.time()
            ).order_by('start_time').first()
            if next_lecture:
                cv2.putText(frame, f"Next: {next_lecture.classroom.name} at {next_lecture.start_time.strftime('%H:%M')}", 
                           (10, 60), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 1)
        
        # Show current time
        cv2.putText(frame, now.strftime("%H:%M:%S"), (frame.shape[1] - 100, 30),
                   cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 2)
        
        cv2.imshow("Face Recognition Attendance System", frame)
        
        key = cv2.waitKey(1)
        
        if key == ord('q'):
            if active_lecture:
                end_lecture(active_lecture)
            break
        
        elif key == ord('c'):
            # Capture face
            cv2.destroyAllWindows()
            person_name = input("Enter the person's name (use folder name for attendance): ").strip()
            if person_name:
                success = face_recognizer.capture_face(frame, person_name)
                if success:
                    print("Retraining model with new face...")
                    face_recognizer.load_known_faces()
            else:
                print("No name entered, skipping capture.")
        
        elif key == ord('r'):
            print("Retraining from known_faces directory...")
            face_recognizer.load_known_faces()
            marked_in_session.clear()
    
    video.release()
    cv2.destroyAllWindows()


def run_auto_attendance(room_name=None):
    """
    Automated attendance mode for a specific ROOM (not classroom).
    
    - Camera is placed in a Room
    - Monitors timetable to see which Classroom uses this Room at what time
    - Starts camera 15 minutes before each scheduled lecture
    - Auto-creates lecture and starts attendance when lecture time begins
    - For back-to-back lectures of the SAME classroom, carries forward attendance
    - For different classrooms, creates fresh attendance
    - Marks all students who didn't appear as absent when lecture ends
    """
    import cv2
    import functions
    import django
    django.setup()
    
    from django.utils import timezone
    from core.models import Room, Classroom, Timetable, Lecture, Attendance, Student
    
    # Initialize face recognizer
    face_recognizer = functions.FaceRecognizer(known_faces_dir="known_faces")
    
    print("Loading face recognition model...")
    if not face_recognizer.load_model():
        print("No existing model found. Training from known_faces directory...")
        face_recognizer.load_known_faces()
    print("Ready!")
    
    # Get room
    if room_name:
        try:
            room = Room.objects.get(name__iexact=room_name)
        except Room.DoesNotExist:
            print(f"Room '{room_name}' not found!")
            rooms = Room.objects.all()
            print("Available rooms:")
            for r in rooms:
                print(f"  - {r.name}")
            return
    else:
        rooms = list(Room.objects.all())
        if not rooms:
            print("No rooms found. Run 'python main.py setup' first.")
            return
        
        print("\nAvailable Rooms (each has a camera):")
        for idx, r in enumerate(rooms, 1):
            print(f"  {idx}. {r.name} (camera index: {r.camera_index})")
        
        try:
            choice = input("\nSelect room number: ").strip()
            room = rooms[int(choice) - 1]
        except (ValueError, IndexError):
            print("Invalid selection")
            return
    
    print(f"\n{'='*60}")
    print(f"AUTO ATTENDANCE MODE - {room.name}")
    print(f"{'='*60}")
    print("System will automatically:")
    print("  • Start camera 15 minutes before each lecture in this room")
    print("  • Detect which class is scheduled and mark their attendance")
    print("  • Carry forward attendance for back-to-back same-class lectures")
    print("  • Mark remaining students absent when lecture ends")
    print("\nPress 'q' to quit at any time")
    print(f"{'='*60}\n")
    
    EARLY_START_MINUTES = 15  # Start camera this many minutes before lecture
    
    video = None
    active_lecture = None
    current_timetable = None
    marked_in_session = set()
    camera_active = False
    current_classroom = None  # Track which classroom is currently being attended
    
    def get_next_lecture_info():
        """Get the next upcoming lecture from timetable FOR THIS ROOM"""
        now = timezone.now()
        current_time = now.time()
        day_of_week = now.weekday()
        
        # Get today's remaining lectures IN THIS ROOM
        todays_lectures = Timetable.objects.filter(
            room=room,
            day_of_week=day_of_week,
            end_time__gt=current_time  # Lecture hasn't ended yet
        ).order_by('start_time')
        
        if todays_lectures.exists():
            return todays_lectures.first(), now.date()
        
        # No more lectures today, check next days
        for days_ahead in range(1, 8):
            future_date = now.date() + timedelta(days=days_ahead)
            future_day = future_date.weekday()
            
            future_lectures = Timetable.objects.filter(
                room=room,
                day_of_week=future_day
            ).order_by('start_time')
            
            if future_lectures.exists():
                return future_lectures.first(), future_date
        
        return None, None
    
    def time_until(target_time, target_date):
        """Calculate seconds until a target datetime"""
        now = timezone.now()
        target_datetime = timezone.make_aware(
            datetime.combine(target_date, target_time)
        )
        delta = target_datetime - now
        return delta.total_seconds()
    
    def start_camera():
        nonlocal video, camera_active
        if not camera_active:
            video = cv2.VideoCapture(room.camera_index)
            camera_active = True
            print(f"📷 Camera started (index {room.camera_index})")
    
    def stop_camera():
        nonlocal video, camera_active
        if camera_active and video:
            video.release()
            cv2.destroyAllWindows()
            camera_active = False
            print("📷 Camera stopped")
    
    def mark_attendance_for_face(face_name, lecture):
        """Mark attendance for a recognized face, checking if they belong to current class"""
        try:
            student = Student.objects.get(face_folder_name=face_name)
            
            # Check if student belongs to the classroom for this lecture
            if student.classroom != lecture.timetable.classroom:
                return {
                    'success': False, 
                    'message': f'{student.name} is from {student.classroom}, not {lecture.timetable.classroom}'
                }
            
            attendance, created = Attendance.objects.get_or_create(
                lecture=lecture,
                student=student,
                defaults={'status': 'absent'}
            )
            
            if attendance.status != 'present':
                attendance.status = 'present'
                attendance.marked_at = timezone.now()
                attendance.marked_by_face_recognition = True
                attendance.save()
                return {
                    'success': True,
                    'message': f'Marked {student.name} present',
                    'student_name': student.name,
                    'already_marked': False
                }
            else:
                return {
                    'success': True,
                    'student_name': student.name,
                    'already_marked': True
                }
        except Student.DoesNotExist:
            return {'success': False, 'message': f'No student with face folder: {face_name}'}
    
    try:
        while True:
            now = timezone.now()
            current_time = now.time()
            today = now.date()
            
            # If no active lecture, find the next one
            if not active_lecture:
                next_timetable, lecture_date = get_next_lecture_info()
                
                if not next_timetable:
                    print("No upcoming lectures found in timetable for this room.")
                    time_module.sleep(60)
                    continue
                
                # Calculate time until lecture starts
                seconds_until_start = time_until(next_timetable.start_time, lecture_date)
                seconds_until_early_start = seconds_until_start - (EARLY_START_MINUTES * 60)
                
                # Check if it's a different lecture than current
                if current_timetable != next_timetable or not camera_active:
                    current_timetable = next_timetable
                    
                    if seconds_until_early_start > 0:
                        # Not yet time to start
                        print(f"\n⏰ Next in {room.name}: {next_timetable.subject.name}")
                        print(f"   Class: {next_timetable.classroom.name}")
                        print(f"   Time: {next_timetable.start_time} on {lecture_date}")
                        print(f"   Camera will start in {int(seconds_until_early_start // 60)} minutes")
                        
                        # Wait until early start time (check every 30 seconds)
                        while seconds_until_early_start > 0:
                            time_module.sleep(min(30, seconds_until_early_start))
                            seconds_until_early_start = time_until(
                                next_timetable.start_time, lecture_date
                            ) - (EARLY_START_MINUTES * 60)
                            
                            # Check for quit
                            if camera_active:
                                key = cv2.waitKey(1)
                                if key == ord('q'):
                                    raise KeyboardInterrupt
                    
                    # Time to start camera (15 min before)
                    if not camera_active:
                        print(f"\n🔔 Starting camera for: {next_timetable.subject.name}")
                        print(f"   Class: {next_timetable.classroom.name}")
                        print(f"   Lecture starts at {next_timetable.start_time}")
                        start_camera()
                
                # Check if lecture should start now
                seconds_until_start = time_until(next_timetable.start_time, lecture_date)
                
                if seconds_until_start <= 0 and lecture_date == today:
                    # Start the lecture!
                    lecture, created = Lecture.objects.get_or_create(
                        timetable=next_timetable,
                        date=today,
                        defaults={'status': 'scheduled'}
                    )
                    
                    if lecture.status != 'active':
                        # Check if this is a back-to-back lecture for same class
                        is_same_class_continuation = (
                            current_classroom is not None and 
                            current_classroom == next_timetable.classroom
                        )
                        
                        result_msg = lecture.start_lecture(carry_forward=is_same_class_continuation)
                        
                        print(f"\n✅ LECTURE STARTED: {next_timetable.subject.name}")
                        print(f"   Class: {next_timetable.classroom.name}")
                        print(f"   Room: {room.name}")
                        print(f"   Teacher: {next_timetable.teacher.name}")
                        print(f"   Ends at: {next_timetable.end_time}")
                        print(f"   {result_msg}")
                        
                        if lecture.carried_from:
                            print(f"   📋 Attendance carried from: {lecture.carried_from.timetable.subject.name}")
                    
                    active_lecture = lecture
                    current_classroom = next_timetable.classroom
                    
                    # If attendance was carried forward, pre-populate marked_in_session
                    if lecture.carried_from:
                        for att in lecture.attendance_records.filter(status='present'):
                            if att.student.face_folder_name:
                                marked_in_session.add(att.student.face_folder_name)
                    else:
                        marked_in_session.clear()
            
            # If lecture is active, check if it should end
            if active_lecture:
                end_time = active_lecture.timetable.end_time
                seconds_until_end = time_until(end_time, today)
                
                if seconds_until_end <= 0:
                    # Lecture ended
                    present_count = active_lecture.attendance_records.filter(status='present').count()
                    total_count = active_lecture.attendance_records.count()
                    absent_count = total_count - present_count
                    
                    print(f"\n⏹️  LECTURE ENDED: {active_lecture.timetable.subject.name}")
                    print(f"   Class: {active_lecture.timetable.classroom.name}")
                    print(f"   Present: {present_count}/{total_count}")
                    print(f"   Absent: {absent_count}")
                    
                    active_lecture.end_lecture()
                    
                    # Check if there's another lecture soon IN THIS ROOM
                    next_tt, next_date = get_next_lecture_info()
                    
                    if next_tt and next_date == today:
                        seconds_to_next = time_until(next_tt.start_time, next_date)
                        
                        # Check if same class continues (back-to-back)
                        if next_tt.classroom == current_classroom:
                            print(f"\n📋 Same class continues: {next_tt.subject.name}")
                            print(f"   Attendance will be carried forward")
                        else:
                            print(f"\n🔄 Different class next: {next_tt.classroom.name} - {next_tt.subject.name}")
                            current_classroom = None  # Reset for new class
                            marked_in_session.clear()
                        
                        if seconds_to_next < (EARLY_START_MINUTES + 5) * 60:
                            print(f"   Starting in {int(seconds_to_next // 60)} minutes")
                            active_lecture = None
                            continue
                    else:
                        current_classroom = None
                    
                    active_lecture = None
                    
                    # No immediate next lecture, stop camera
                    if not next_tt or next_date != today:
                        stop_camera()
                        current_timetable = None
                        marked_in_session.clear()
                    continue
            
            # Process camera frame if active
            if camera_active and video:
                check, frame = video.read()
                
                if check:
                    # Recognize faces
                    frame, recognized = face_recognizer.recognize_faces(frame)
                    
                    # Mark attendance if lecture is active
                    if active_lecture and recognized:
                        for name in recognized:
                            if name not in marked_in_session and name != "Unknown":
                                result = mark_attendance_for_face(name, active_lecture)
                                if result.get('success'):
                                    if not result.get('already_marked'):
                                        print(f"✓ PRESENT: {result.get('student_name', name)}")
                                    marked_in_session.add(name)
                                elif 'not' in result.get('message', '').lower():
                                    # Student from different class - just ignore silently
                                    pass
                    
                    # Display info on frame
                    if active_lecture:
                        remaining = time_until(active_lecture.timetable.end_time, today)
                        mins_remaining = max(0, int(remaining // 60))
                        
                        cv2.putText(frame, f"ROOM: {room.name}", 
                                   (10, 25), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 2)
                        cv2.putText(frame, f"CLASS: {active_lecture.timetable.classroom.name}", 
                                   (10, 50), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 0), 2)
                        cv2.putText(frame, f"LECTURE: {active_lecture.timetable.subject.name}", 
                                   (10, 75), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 0), 2)
                        cv2.putText(frame, f"Time left: {mins_remaining} min | Present: {len(marked_in_session)}", 
                                   (10, 100), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 0), 2)
                        
                        if active_lecture.carried_from:
                            cv2.putText(frame, "* Attendance carried forward", 
                                       (10, 125), cv2.FONT_HERSHEY_SIMPLEX, 0.4, (255, 255, 0), 1)
                    else:
                        cv2.putText(frame, f"ROOM: {room.name}", 
                                   (10, 25), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 2)
                        cv2.putText(frame, "Waiting for lecture...", 
                                   (10, 50), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 165, 0), 2)
                        if current_timetable:
                            cv2.putText(frame, f"Next: {current_timetable.classroom.name} - {current_timetable.subject.name}", 
                                       (10, 75), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 165, 0), 2)
                            cv2.putText(frame, f"At: {current_timetable.start_time}", 
                                       (10, 100), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 165, 0), 2)
                    
                    cv2.imshow(f"Auto Attendance - {room.name}", frame)
                
                key = cv2.waitKey(1)
                if key == ord('q'):
                    break
            else:
                # No camera, just wait
                time_module.sleep(1)
    
    except KeyboardInterrupt:
        print("\n\nShutting down...")
    
    finally:
        if active_lecture:
            print(f"Ending active lecture: {active_lecture.timetable.subject.name}")
            active_lecture.end_lecture()
        stop_camera()
        print("Auto attendance stopped.")


def setup_sample_data():
    """Create sample data for testing"""
    import django
    django.setup()
    
    from django.contrib.auth.models import User
    from core.models import Room, Classroom, Student, Teacher, Subject, Timetable
    import datetime
    
    print("Setting up sample data...")
    
    # Create rooms (physical locations with cameras)
    room, _ = Room.objects.get_or_create(
        name="Room 101",
        defaults={'description': 'Main lecture hall - Ground Floor', 'camera_index': 0}
    )
    print(f"  ✓ Room: {room.name} (camera index: {room.camera_index})")
    
    room2, _ = Room.objects.get_or_create(
        name="Room 102",
        defaults={'description': 'Computer Lab - Ground Floor', 'camera_index': 1}
    )
    print(f"  ✓ Room: {room2.name} (camera index: {room2.camera_index})")
    
    # Create classrooms (student divisions)
    cs_a, _ = Classroom.objects.get_or_create(
        name="CS-A",
        defaults={'description': 'Computer Science Section A'}
    )
    print(f"  ✓ Division: {cs_a.name}")
    
    cs_b, _ = Classroom.objects.get_or_create(
        name="CS-B",
        defaults={'description': 'Computer Science Section B'}
    )
    print(f"  ✓ Division: {cs_b.name}")
    
    # Create subjects (4 subjects for 4 hours per day)
    subjects_data = [
        ('CS101', 'Data Structures'),
        ('CS102', 'Database Management'),
        ('CS103', 'Operating Systems'),
        ('CS104', 'Computer Networks'),
    ]
    subjects = []
    for code, name in subjects_data:
        subject, _ = Subject.objects.get_or_create(code=code, defaults={'name': name})
        subjects.append(subject)
        print(f"  ✓ Subject: {subject}")
    
    # Create teachers
    teachers_data = ['Dr. Smith', 'Prof. Johnson', 'Dr. Williams', 'Prof. Davis']
    teachers = []
    for name in teachers_data:
        teacher, _ = Teacher.objects.get_or_create(name=name)
        teachers.append(teacher)
        print(f"  ✓ Teacher: {teacher.name}")
    
    # Create 5 students for each division
    student_names = {
        'CS-A': ['Ameya', 'Rahul', 'Priya', 'Sneha', 'Arjun'],
        'CS-B': ['Vikram', 'Neha', 'Rohan', 'Ananya', 'Karan']
    }
    
    print("\n  Creating students...")
    for division, classroom in [('CS-A', cs_a), ('CS-B', cs_b)]:
        for idx, name in enumerate(student_names[division], 1):
            roll_no = f"{idx:03d}"  # 001, 002, 003, etc.
            # Make roll_no unique by including division
            unique_roll_no = f"{division}-{roll_no}"  # CS-A-001, CS-B-001
            username = f"{division.lower().replace('-', '')}_{roll_no}"  # csa_001, csb_001
            
            # Create user
            user, created = User.objects.get_or_create(
                username=username,
                defaults={'first_name': name}
            )
            if created:
                user.set_password('password123')
                user.save()
            
            # Create student
            student, created = Student.objects.get_or_create(
                roll_no=unique_roll_no,
                classroom=classroom,
                defaults={
                    'user': user,
                    'name': name,
                    'face_folder_name': f"{division}_{roll_no}"
                }
            )
            if created:
                print(f"    ✓ {division} - {roll_no}: {name} (login: {division} + {roll_no})")
    
    # Clear existing timetable for clean setup
    Timetable.objects.filter(classroom__in=[cs_a, cs_b]).delete()
    
    # Create weekly timetable (same every week, Mon-Fri, 4 hours per day)
    # CS-A: 9:00-13:00, CS-B: 14:00-18:00 (both in Room 101)
    
    # Time slots (4 one-hour lectures per day)
    cs_a_times = [
        (datetime.time(9, 0), datetime.time(10, 0)),
        (datetime.time(10, 0), datetime.time(11, 0)),
        (datetime.time(11, 30), datetime.time(12, 30)),
        (datetime.time(12, 30), datetime.time(13, 30)),
    ]
    
    cs_b_times = [
        (datetime.time(14, 0), datetime.time(15, 0)),
        (datetime.time(15, 0), datetime.time(16, 0)),
        (datetime.time(16, 30), datetime.time(17, 30)),
        (datetime.time(17, 30), datetime.time(18, 30)),
    ]
    
    print("\n  Creating timetable...")
    for day in range(5):  # Monday to Friday
        day_name = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday'][day]
        
        # CS-A morning lectures
        for idx, (start, end) in enumerate(cs_a_times):
            subject = subjects[idx % len(subjects)]
            teacher = teachers[idx % len(teachers)]
            
            Timetable.objects.create(
                room=room,
                classroom=cs_a,
                day_of_week=day,
                start_time=start,
                end_time=end,
                subject=subject,
                teacher=teacher
            )
        
        # CS-B afternoon lectures
        for idx, (start, end) in enumerate(cs_b_times):
            subject = subjects[idx % len(subjects)]
            teacher = teachers[idx % len(teachers)]
            
            Timetable.objects.create(
                room=room,
                classroom=cs_b,
                day_of_week=day,
                start_time=start,
                end_time=end,
                subject=subject,
                teacher=teacher
            )
    
    print(f"    ✓ {cs_a.name}: 9:00 AM - 1:30 PM in {room.name}")
    print(f"    ✓ {cs_b.name}: 2:00 PM - 6:30 PM in {room.name}")
    
    print("\n" + "="*60)
    print("SETUP COMPLETE!")
    print("="*60)
    print("\nStudents created (5 per division):")
    print("-"*40)
    print(f"{'Division':<10} {'Roll No':<10} {'Name':<15} {'Password'}")
    print("-"*40)
    for division, classroom in [('CS-A', cs_a), ('CS-B', cs_b)]:
        for student in Student.objects.filter(classroom=classroom):
            print(f"{division:<10} {student.roll_no:<10} {student.name:<15} password123")
    print("-"*40)
    print("\nLogin using: Division + Roll Number + Password")
    print("Example: Select 'CS-A', enter '001', password 'password123'")
    print("\nNext steps:")
    print("  1. Run 'python main.py runserver' to start web server")
    print("  2. Visit http://127.0.0.1:8000/ to login")
    print("  3. Upload 3 photos for each student from dashboard")
    print("  4. Run 'python main.py' to start face recognition")


def main():
    if len(sys.argv) > 1:
        command = sys.argv[1]
        
        if command == 'runserver':
            run_django_command(['runserver'])
        
        elif command == 'auto':
            # Auto attendance mode - now room-based
            room_name = sys.argv[2] if len(sys.argv) > 2 else None
            run_auto_attendance(room_name)
        
        elif command == 'migrate':
            run_django_command(['makemigrations', 'core'])
            run_django_command(['migrate'])
        
        elif command == 'createsuperuser':
            run_django_command(['createsuperuser'])
        
        elif command == 'setup':
            # Run migrations first
            run_django_command(['makemigrations', 'core'])
            run_django_command(['migrate'])
            # Then create sample data
            setup_sample_data()
        
        elif command == 'shell':
            run_django_command(['shell'])
        
        else:
            # Pass through to Django management
            run_django_command(sys.argv[1:])
    else:
        # Run face recognition by default
        run_face_recognition()


if __name__ == "__main__":
    main()