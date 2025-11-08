# FILE: app/student/routes.py

from flask import flash, render_template, abort, redirect, url_for
from flask_login import login_required, current_user
from app.services import get_student_dashboard_data
from app.student import bp
# --- [NEW] Added models and datetime ---
from app.models import Student, Semester, Classroom, WeeklyScheduleSlot, TimetableEntry, Course, Enrollment, CourseGrade # Import Enrollment model
from sqlalchemy.orm import selectinload
from datetime import datetime, date, time
# --- [END NEW] ---

# Assuming db instance is available for querying (e.g. from app import db)
try:
    from app import db 
    from app.models import AcademicYear, GradeLevel # Ensure these are imported if needed
except ImportError:
    # Safegaurd for deployment environment where 'db' may not be in 'app' namespace
    db = None 

# Decorator สำหรับตรวจสอบว่าเป็นนักเรียนหรือไม่
from functools import wraps

def student_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated or not current_user.has_role('Student'):
            abort(403) # Forbidden
        # เพิ่มการตรวจสอบว่า User นี้ผูกกับ Student จริงๆ
        if not current_user.student_profile:
             # อาจจะ Log error หรือ redirect ไปหน้าแจ้งปัญหา
             abort(403)
        return f(*args, **kwargs)
    return decorated_function

@bp.route('/dashboard')
@login_required
# @student_required # You might want to re-enable this
def dashboard():
    """หน้า Dashboard หลักสำหรับนักเรียน"""
    student = current_user.student_profile
    if not student:
        flash('ไม่พบข้อมูลนักเรียนที่เชื่อมโยงกับบัญชีผู้ใช้นี้ กรุณาติดต่อผู้ดูแล', 'danger')
        return redirect(url_for('auth.logout'))
    # --- [NEW] Find current semester and time ---
    # Original: now = datetime.now()
    
    # --- [TEMP FIX] Hardcode date and time for testing (2025, 9, 5 @ 12:50:00 - Friday) ---
    # ใช้เวลา 12:50:00 น. เพื่อให้ครอบคลุมช่วงพักเที่ยง (ถ้าตารางเรียนถูกกำหนด)
    now = datetime(2025, 9, 5, 12, 0, 0) 
    # --- [END TEMP FIX] ---
    
    current_time = now.time()
    current_day_of_week = now.isoweekday() # Monday=1, Sunday=7

    current_semester = Semester.query.filter_by(is_current=True).first()
    if not current_semester:
        flash('ไม่พบข้อมูลภาคเรียนปัจจุบัน กรุณาติดต่อผู้ดูแล', 'warning')
        # Render a limited dashboard
        return render_template('student/dashboard.html',
                               title='แดชบอร์ดนักเรียน',
                               student=student,
                               current_slot_info=None,
                               today_schedule=[],
                               course_summaries={},
                               assessment_summary=[],
                               warnings=[])
    
    # --- [FIXED] Get classroom using Enrollment and current semester ---
    # 1. Find the Enrollment record for this student in the current semester's academic year
    # NOTE: Assuming current_semester has an academic_year_id attribute
    current_academic_year_id = current_semester.academic_year_id
    
    enrollment = Enrollment.query.join(Classroom).filter(
        Enrollment.student_id == student.id,
        Classroom.academic_year_id == current_academic_year_id
    ).first()
    
    # 2. Extract Classroom and Grade Level
    classroom = enrollment.classroom if enrollment else None
    grade_level_id = classroom.grade_level_id if classroom else None
    
    if not classroom:
        flash('ไม่พบห้องเรียนที่ลงทะเบียนสำหรับภาคเรียนปัจจุบัน กรุณาติดต่อผู้ดูแล', 'warning')
        # Render a limited dashboard
        return render_template('student/dashboard.html',
                               title='แดชบอร์ดนักเรียน',
                               student=student,
                               current_slot_info=None,
                               today_schedule=[],
                               course_summaries={},
                               assessment_summary=[],
                               warnings=[])
    # --- [END FIXED] ---

    
    # --- [REVISED] Call Service Function ---
    dashboard_data = get_student_dashboard_data(student.id)
    if not dashboard_data:
         flash('เกิดข้อผิดพลาดในการดึงข้อมูลแดชบอร์ด', 'danger')
         # Continue rendering with schedule data (if schedule found)
    
    # --- [NEW] Transform academic_summary to dict for easier lookup ---
    # academic_summary contains grades/summaries for the current semester
    academic_summary = dashboard_data.get('academic_summary', []) if dashboard_data else []
    assessment_summary = dashboard_data.get('assessment_summary', []) if dashboard_data else []
    warnings = dashboard_data.get('warnings', []) if dashboard_data else []

    course_summaries = {}
    for summary in academic_summary:
        if hasattr(summary, 'course') and summary.course:
            course_summaries[summary.course.id] = summary
    # --- [END NEW] ---

    
    current_slot_info = None
    current_entry_data = None
    next_slot_info = None
    next_entry_data = None
    today_schedule = []
    current_slot_period = 0


    # --- [NEW] Query for schedule IF classroom and grade_level are found ---
    if classroom and grade_level_id:
        
        # 1. Find Current Slot
        current_slot = WeeklyScheduleSlot.query.filter(
            WeeklyScheduleSlot.semester_id == current_semester.id,
            WeeklyScheduleSlot.grade_level_id == grade_level_id,
            WeeklyScheduleSlot.day_of_week == current_day_of_week,
            WeeklyScheduleSlot.start_time <= current_time,
            WeeklyScheduleSlot.end_time > current_time
        ).first()

        if current_slot:
            current_slot_period = current_slot.period_number
            current_slot_info = {
                'period': current_slot.period_number,
                'start': current_slot.start_time.strftime('%H:%M'),
                'end': current_slot.end_time.strftime('%H:%M'),
                'is_teaching': current_slot.is_teaching_period,
                'activity': current_slot.activity_name
            }
            # Find matching TimetableEntry (Must match the specific classroom's course)
            current_entry = TimetableEntry.query.join(Course).filter(
                TimetableEntry.weekly_schedule_slot_id == current_slot.id,
                Course.classroom_id == classroom.id # Match the specific classroom
            ).options(
                selectinload(TimetableEntry.course).selectinload(Course.subject),
                selectinload(TimetableEntry.course).selectinload(Course.room),
                selectinload(TimetableEntry.course).selectinload(Course.teachers)
            ).first()

            if current_entry:
                teacher_names = ", ".join([t.full_name for t in current_entry.course.teachers])
                current_entry_data = {
                    'course_id': current_entry.course_id,
                    'subject': current_entry.course.subject.name if current_entry.course.subject else 'N/A',
                    'subject_code': current_entry.course.subject.subject_code if current_entry.course.subject else '',
                    'room': current_entry.course.room.name if current_entry.course.room else '-',
                    'teachers': teacher_names
                }

        # 2. Find Next Slot
        next_slot_period_start = current_slot_period + 1
        
        next_slot = WeeklyScheduleSlot.query.filter(
            WeeklyScheduleSlot.semester_id == current_semester.id,
            WeeklyScheduleSlot.grade_level_id == grade_level_id,
            WeeklyScheduleSlot.day_of_week == current_day_of_week,
            WeeklyScheduleSlot.period_number >= next_slot_period_start,
        ).order_by(WeeklyScheduleSlot.period_number.asc()).first()

        # Fallback check for next slot if outside any slot (e.g. before school starts or after school ends)
        if not current_slot and not next_slot:
             # Find the first slot of the day that hasn't started yet
             next_slot = WeeklyScheduleSlot.query.filter(
                WeeklyScheduleSlot.semester_id == current_semester.id,
                WeeklyScheduleSlot.grade_level_id == grade_level_id,
                WeeklyScheduleSlot.day_of_week == current_day_of_week,
                WeeklyScheduleSlot.start_time > current_time # Find first slot after current time
             ).order_by(WeeklyScheduleSlot.period_number.asc()).first()
        
        
        if next_slot:
            next_slot_info = {
                'period': next_slot.period_number,
                'start': next_slot.start_time.strftime('%H:%M'),
                'end': next_slot.end_time.strftime('%H:%M'),
                'is_teaching': next_slot.is_teaching_period,
                'activity': next_slot.activity_name
            }
            # Find matching TimetableEntry
            next_entry = TimetableEntry.query.join(Course).filter(
                TimetableEntry.weekly_schedule_slot_id == next_slot.id,
                Course.classroom_id == classroom.id
            ).options(
                selectinload(TimetableEntry.course).selectinload(Course.subject),
                selectinload(TimetableEntry.course).selectinload(Course.room)
            ).first()

            if next_entry:
                next_entry_data = {
                    'subject': next_entry.course.subject.name if next_entry.course.subject else 'N/A',
                    'room': next_entry.course.room.name if next_entry.course.room else '-'
                }

        # 3. Find Today's Schedule
        today_entries = TimetableEntry.query.join(Course).join(WeeklyScheduleSlot).filter(
            Course.classroom_id == classroom.id,
            Course.semester_id == current_semester.id,
            WeeklyScheduleSlot.day_of_week == current_day_of_week
        ).options(
            selectinload(TimetableEntry.slot),
            selectinload(TimetableEntry.course).selectinload(Course.subject),
            selectinload(TimetableEntry.course).selectinload(Course.room),
            selectinload(TimetableEntry.course).selectinload(Course.teachers)
        ).order_by(WeeklyScheduleSlot.period_number.asc()).all()

        for entry in today_entries:
            slot = entry.slot
            teacher_names = ", ".join([t.full_name for t in entry.course.teachers])
            today_schedule.append({
                'period': slot.period_number,
                'start': slot.start_time.strftime('%H:%M'),
                'end': slot.end_time.strftime('%H:%M'),
                'is_teaching': slot.is_teaching_period,
                'activity': slot.activity_name,
                'course_id': entry.course_id,
                'subject': entry.course.subject.name if entry.course.subject else 'N/A',
                'subject_code': entry.course.subject.subject_code if entry.course.subject else '',
                'room': entry.course.room.name if entry.course.room else '-',
                'teachers': teacher_names,
                'is_current': (current_slot and slot.id == current_slot.id)
            })
    # --- [END NEW] ---

    return render_template('student/dashboard.html',
                           title='แดชบอร์ดนักเรียน',
                           student=student,
                           # [NEW] Pass new schedule data
                           current_slot_info=current_slot_info,
                           current_entry_data=current_entry_data,
                           next_slot_info=next_slot_info,
                           next_entry_data=next_entry_data,
                           today_schedule=today_schedule,
                           course_summaries=course_summaries,
                           # [REVISED] Pass original data as well
                           academic_summary=academic_summary, # Keep for desktop/fallback
                           assessment_summary=assessment_summary,
                           warnings=warnings)

@bp.route('/grade_history')
@login_required
# @student_required # Re-enable if needed
def grade_history():
    """หน้าประวัติผลการเรียนทั้งหมดของนักเรียน"""
    student = current_user.student_profile
    if not student:
        flash('ไม่พบข้อมูลนักเรียนที่เชื่อมโยงกับบัญชีผู้ใช้นี้ กรุณาติดต่อผู้ดูแล', 'danger')
        return redirect(url_for('auth.logout'))

    if db is None:
        # Fallback if database object cannot be imported
        flash('ไม่สามารถเชื่อมต่อฐานข้อมูลเพื่อดึงประวัติผลการเรียนได้', 'danger')
        return render_template('student/grade_history.html',
                               title='ประวัติผลการเรียนทั้งหมด',
                               student=student,
                               sorted_history=[])

    # 1. [REVISED] Fetch ALL CourseGrades for this student
    # This is the "Single Source of Truth" for grades
    all_grades = db.session.query(CourseGrade).filter_by(
        student_id=student.id
    ).options(
        selectinload(CourseGrade.course).options(
            selectinload(Course.subject),
            selectinload(Course.semester).selectinload(Semester.academic_year),
            selectinload(Course.classroom).selectinload(Classroom.grade_level) # Need classroom for Grade Level
        )
    ).all()

    # 2. Group results by Grade Level (name) and then by Semester (key)
    grade_history_data = {}

    for course_grade in all_grades:
        course = course_grade.course

        # Skip if data is incomplete (e.g., course deleted but grade remained)
        if not (course and course.subject and course.semester and 
                course.semester.academic_year and course.classroom and 
                course.classroom.grade_level):
            continue 

        grade_name = course.classroom.grade_level.name
        academic_year = course.semester.academic_year.year
        semester_term = course.semester.term

        # Sub-key: Semester (e.g., '1/2568')
        semester_key = f"{semester_term}/{academic_year}"

        if grade_name not in grade_history_data:
            grade_history_data[grade_name] = {}

        if semester_key not in grade_history_data[grade_name]:
            grade_history_data[grade_name][semester_key] = {
                'semester_name': semester_key,
                'courses': []
            }

        # --- [FIXED] Get data directly from the query ---
        final_grade = course_grade.final_grade
        credit = course.subject.credit

        grade_history_data[grade_name][semester_key]['courses'].append({
            'course_id': course.id,
            'subject_name': course.subject.name,
            'subject_code': course.subject.subject_code,
            'final_grade': final_grade if final_grade is not None else '-', 
            'credit': credit if credit is not None else '-'
        })

    # 3. Sort structure: 1. Grade Level (M.1, M.2), 2. Semester (1/2568, 2/2568)
    sorted_history_list = []

    # Sort Grade Levels (e.g., 'ม.1', 'ม.2', ...)
    sorted_grade_names = sorted(grade_history_data.keys())

    for grade_name in sorted_grade_names:
        semesters_dict = grade_history_data[grade_name]

        # Sort Semesters (e.g., '1/2568', '2/2568', '1/2569')
        sorted_semester_keys = sorted(semesters_dict.keys())

        sorted_semesters_list = [semesters_dict[key] for key in sorted_semester_keys]

        # Sort courses within each semester (e.g., by subject code)
        for semester_data in sorted_semesters_list:
            semester_data['courses'].sort(key=lambda x: x['subject_code'])

        sorted_history_list.append((grade_name, sorted_semesters_list))

    return render_template('student/grade_history.html',
                           title='ประวัติผลการเรียนทั้งหมด',
                           student=student,
                           sorted_history=sorted_history_list)

# Redirect หน้าหลักของ /student ไป dashboard
@bp.route('/')
@login_required
# @student_required
def index():
    return redirect(url_for('student.dashboard'))