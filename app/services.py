# FILE: app/services.py

from collections import Counter, defaultdict
import json
import statistics
from flask import current_app, url_for
from flask_login import current_user
from sqlalchemy import func
from datetime import date, datetime

from app.models import (AssessmentItem, AuditLog, Course, Enrollment, GradeLevel, QualitativeScore, RepeatCandidate, Setting, Student, Score, CourseGrade, GradedItem, 
                        LearningUnit, AttendanceRecord, Subject, TimeSlot, TimetableEntry, Classroom, Semester, AcademicYear, User,
                        LessonPlan, WeeklyScheduleSlot, AdvisorAssessmentRecord, AdvisorAssessmentScore, AssessmentTemplate, AssessmentTopic, RubricLevel, AdministrativeDepartment, Indicator, PostTeachingLog, Role, Notification,
                        AttendanceWarning, SubUnit)
from . import db
from sqlalchemy.orm import joinedload, aliased, selectinload
import pandas as pd
from datetime import timedelta
# --- Constants ---
# หมายเหตุ: ในอนาคตค่านี้ควรกำหนดได้จากหน้าตั้งค่าของ Admin
WARNING_THRESHOLDS = [20.0, 40.0] # เกณฑ์การแจ้งเตือนที่ 20%

def resolve_active_attendance_warning(attendance_record: AttendanceRecord):
    """
    Finds and resolves an active attendance warning for a student in a course
    when they attend class.
    """
    student = attendance_record.student
    course = attendance_record.timetable_entry.course
    
    # ค้นหา Warning ที่ยัง Active อยู่ของนักเรียนในคอร์สนี้
    active_warning = db.session.query(AttendanceWarning).filter_by(
        student_id=student.id,
        course_id=course.id,
        status='ACTIVE'
    ).first()

    # ถ้าเจอ ให้เปลี่ยนสถานะเป็น RESOLVED
    if active_warning:
        active_warning.status = 'RESOLVED'
        # ไม่ต้อง commit ที่นี่ เพราะจะ commit ที่ routes.py
        
def check_and_create_attendance_warnings(attendance_record: AttendanceRecord):
    """
    Checks student's attendance and creates smart notifications.
    Now features Per-Student throttling and tiered thresholds.
    """
    student = attendance_record.student
    triggering_entry = attendance_record.timetable_entry
    course = triggering_entry.course
    absence_date = attendance_record.recorded_at.date()

    if not student or not course or not course.subject.credit or course.subject.credit <= 0:
        return

    total_teaching_periods = course.subject.credit * 40
    if total_teaching_periods == 0:
        return

    absent_count = db.session.query(AttendanceRecord).join(AttendanceRecord.timetable_entry).filter(
        AttendanceRecord.student_id == student.id,
        AttendanceRecord.status == 'ABSENT',
        AttendanceRecord.timetable_entry.has(course_id=course.id)
    ).count()
    
    absence_percentage = (absent_count / total_teaching_periods) * 100

    # --- [REVISED] Logic: ตรวจสอบ Threshold เป็นลำดับขั้น ---
    # หา Threshold สูงสุดที่นักเรียนคนนี้เคยถูกเตือนไปแล้ว (ไม่ว่าวิชาใดก็ตาม)
    last_triggered_threshold = db.session.query(func.max(AttendanceWarning.threshold_percent)).filter_by(
        student_id=student.id
    ).scalar() or 0

    # หา Threshold ขั้นต่อไปที่ต้องแจ้งเตือน
    next_threshold_to_trigger = None
    for t in WARNING_THRESHOLDS:
        if absence_percentage >= t and t > last_triggered_threshold:
            next_threshold_to_trigger = t
            break # เจอขั้นที่ต้องเตือนแล้ว ออกจาก loop

    # ถ้าไม่ถึงเกณฑ์ขั้นต่อไป หรือไม่มีเกณฑ์เหลือแล้ว ก็ไม่ต้องทำอะไร
    if not next_threshold_to_trigger:
        return

    is_skipping_class = False
    day_of_week = triggering_entry.slot.day_of_week
    
    other_entries_today = TimetableEntry.query.join(
        WeeklyScheduleSlot
    ).join(
        Course
    ).filter(
        Course.classroom_id == course.classroom_id,
        WeeklyScheduleSlot.day_of_week == day_of_week,
        TimetableEntry.id != triggering_entry.id
    ).all()

    if other_entries_today:
        other_entry_ids = [e.id for e in other_entries_today]
        other_attendance = db.session.query(AttendanceRecord).filter(
            AttendanceRecord.student_id == student.id,
            AttendanceRecord.timetable_entry_id.in_(other_entry_ids),
            func.date(AttendanceRecord.recorded_at) == absence_date, 
            AttendanceRecord.status.in_(['PRESENT', 'LATE'])
        ).first()
        if other_attendance:
            is_skipping_class = True

    # 5. เริ่มกระบวนการสร้างการแจ้งเตือน
    recipients = set()
    title = "แจ้งเตือนการขาดเรียนเกินกำหนด {int(next_threshold_to_trigger)}%"

    recipients.update(course.teachers)

    # 5.1) เพิ่มครูผู้สอนรายวิชา
    for teacher in course.teachers:
        recipients.add(teacher)

    # 5.2) เพิ่มครูที่ปรึกษา
    # หาห้องเรียนปัจจุบันของนักเรียน
    current_enrollment = student.enrollments.filter(
        Enrollment.classroom.has(academic_year_id=course.semester.academic_year_id)
    ).first()
    if current_enrollment:
        recipients.update(current_enrollment.classroom.advisors)
    
    # 5.3) เพิ่มฝ่ายกิจการนักเรียน (สมมติว่ามี Role ชื่อ 'Student Affairs')
    student_affairs_role = db.session.query(Role).filter_by(name='Student Affairs').first()
    if student_affairs_role:
        recipients.update(student_affairs_role.users)

    # 6. สร้าง Notification และ AttendanceWarning
    if is_skipping_class:
        message = (f"นักเรียน {student.first_name} {student.last_name} "
                    f"มีพฤติกรรมหนีเรียนวิชา {course.subject.name} (ขาด {absent_count} ครั้ง) "
                    f"เนื่องจากยังเข้าเรียนวิชาอื่นในวันเดียวกัน")
        for entry in other_entries_today:
            recipients.update(entry.course.teachers)
    else:
        message = (f"นักเรียน {student.first_name} {student.last_name} "
                    f"ขาดเรียนวิชา {course.subject.name} แล้ว {absent_count} ครั้ง "
                    f"(คิดเป็น {absence_percentage:.2f}%) และไม่พบข้อมูลเข้าเรียนวิชาอื่นในวันนี้")

    url = url_for('teacher.check_attendance', entry_id=triggering_entry.id, _external=True)

    for user in recipients:
        db.session.add(Notification(user_id=user.id, title=title, message=message, url=url, notification_type='ATTENDANCE'))

    db.session.add(AttendanceWarning(
        student_id=student.id, course_id=course.id,
        threshold_percent=int(next_threshold_to_trigger),
        absence_count_at_trigger=absent_count, status='ACTIVE'
    ))

def calculate_final_grades_for_course(course: Course):
    """
    Centralized function to calculate final grades for all students in a course,
    including the logic for '0', 'ร', and 'มส'.
    """
    if not course or not course.lesson_plan:
        return [], {}

    # --- 1. ดึงข้อมูลดิบทั้งหมดที่จำเป็นในครั้งเดียว ---
    enrollments = sorted(course.classroom.enrollments, key=lambda e: e.roll_number or 999)
    student_ids = [en.student.id for en in enrollments]
    
    all_scores = Score.query.join(GradedItem).join(LearningUnit).filter(
        LearningUnit.lesson_plan_id == course.lesson_plan.id,
        Score.student_id.in_(student_ids)
    ).all()
    all_exam_scores = CourseGrade.query.filter(
        CourseGrade.course_id == course.id,
        CourseGrade.student_id.in_(student_ids)
    ).all()
    all_attendance = db.session.query(
        AttendanceRecord.student_id, func.count(AttendanceRecord.id)
    ).join(
        TimetableEntry, AttendanceRecord.timetable_entry_id == TimetableEntry.id
    ).filter(
        AttendanceRecord.student_id.in_(student_ids),
        AttendanceRecord.status == 'ABSENT',
        TimetableEntry.course_id == course.id
    ).group_by(AttendanceRecord.student_id).all()
    summative_items = GradedItem.query.join(LearningUnit).filter(
        LearningUnit.lesson_plan_id == course.lesson_plan.id,
        GradedItem.indicator_type == 'SUMMATIVE'
    ).all()
    summative_item_ids = {item.id for item in summative_items}

    max_collected_q = db.session.query(func.sum(GradedItem.max_score)).join(LearningUnit).filter(
        LearningUnit.lesson_plan_id == course.lesson_plan.id
    ).scalar() or 0
    exam_scores_q = db.session.query(
        func.sum(LearningUnit.midterm_score), func.sum(LearningUnit.final_score)
    ).filter(LearningUnit.lesson_plan_id == course.lesson_plan.id).first()
    # ถ้า sum() ได้ None (คือไม่เคยตั้งค่าเลย) ให้เป็น 0
    max_midterm_q = exam_scores_q[0] if exam_scores_q[0] is not None else 0
    max_final_q = exam_scores_q[1] if exam_scores_q[1] is not None else 0
    grand_max_score_q = max_collected_q + max_midterm_q + max_final_q

    # --- 2. สร้าง Map เพื่อให้เข้าถึงข้อมูลได้เร็ว ---
    scores_map = defaultdict(float)
    summative_scores_map = defaultdict(list)
    for s in all_scores:
        scores_map[s.student_id] += s.score or 0
        if s.graded_item_id in summative_item_ids:
            summative_scores_map[s.student_id].append(s)

    exam_map = {es.student_id: es for es in all_exam_scores}
    absence_map = defaultdict(int, {student_id: count for student_id, count in all_attendance})
    total_periods = (course.subject.credit or 0) * 40

    def map_to_grade(p):
        if p >= 80: return '4'
        if p >= 75: return '3.5'
        if p >= 70: return '3'
        if p >= 65: return '2.5'
        if p >= 60: return '2'
        if p >= 55: return '1.5'
        if p >= 50: return '1'
        return '0'

    # --- 3. วนลูปประมวลผลนักเรียนแต่ละคนตามตรรกะใหม่ ---
    calculated_data = []
    for en in enrollments:
        student = en.student
        final_grade = ''
        
        absent_count = absence_map[student.id]
        exam_grade_obj = exam_map.get(student.id)

        # This is the flag that will be sent to all parts of the application
        has_ms_status = (total_periods > 0 and (absent_count / total_periods) >= 0.20)

        # HIERARCHY 1: Check for "มส"
        if has_ms_status and (not exam_grade_obj or not exam_grade_obj.ms_remediated_status):
            final_grade = 'มส'
        
        # HIERARCHY 2: Check for "ร" (only if not "มส")
        if not final_grade:
            has_incomplete_work = False
            
            if max_midterm_q > 0 and (exam_grade_obj is None or exam_grade_obj.midterm_score is None):
                has_incomplete_work = True
            
            if not has_incomplete_work and max_final_q > 0 and (exam_grade_obj is None or exam_grade_obj.final_score is None):
                has_incomplete_work = True

            if not has_incomplete_work and summative_items:
                student_summative_scores = summative_scores_map.get(student.id, [])
                if len(student_summative_scores) < len(summative_items):
                    has_incomplete_work = True
            
            if has_incomplete_work:
                final_grade = 'ร'

        # HIERARCHY 3: Calculate 0-4 (only if not "มส" or "ร")
        if not final_grade:
            collected = scores_map[student.id]
            midterm = exam_grade_obj.midterm_score if exam_grade_obj and exam_grade_obj.midterm_score is not None else 0
            final = exam_grade_obj.final_score if exam_grade_obj and exam_grade_obj.final_score is not None else 0
            total_score = collected + midterm + final
            percentage = (total_score / grand_max_score_q * 100) if grand_max_score_q > 0 else 0
            final_grade = map_to_grade(percentage)

        # Assemble the final data packet for this student
        collected_display = scores_map[student.id]
        midterm_display = exam_grade_obj.midterm_score if exam_grade_obj else None
        final_display = exam_grade_obj.final_score if exam_grade_obj else None
        total_score_display = collected_display + (midterm_display or 0) + (final_display or 0)
        
        calculated_data.append({
            'student': student, 'exam_grade_obj': exam_grade_obj,
            'full_name': f"{student.name_prefix or ''}{student.first_name} {student.last_name}".strip(),
            'collected_score': collected_display, 'midterm_score': midterm_display, 'final_score': final_display,
            'total_score': total_score_display, 'grade': final_grade,
            'classroom_id': en.classroom_id, 'classroom_name': en.classroom.name,
            'absent_count': absent_count,
            'total_periods': total_periods,
            'has_ms_status': has_ms_status # <-- Now included for all consumers
        })

    max_scores_info = {
        'collected': max_collected_q,
        'midterm': max_midterm_q,
        'final': max_final_q,
        'grand_total': grand_max_score_q,
        'summative_item_ids': list(summative_item_ids)
    }

    return calculated_data, max_scores_info

def calculate_grade_statistics(all_student_grades_data):
    """
    Calculates comprehensive statistics from a list of student grade data.
    Input: A list of dictionaries, where each dict is like one from calculate_final_grades_for_course.
    """
    if not all_student_grades_data:
        return {}

    grade_map = {'4': 4.0, '3.5': 3.5, '3': 3.0, '2.5': 2.5, '2': 2.0, '1.5': 1.5, '1': 1.0, '0': 0.0}
    grade_distribution = defaultdict(int)
    total_students = len(all_student_grades_data)
    numeric_grades = []
    total_scores = []
    passed_count = 0
    good_excellent_count = 0
    failed_count = 0

    for data in all_student_grades_data:
        grade = data.get('grade')
        grade_distribution[grade] += 1
        
        numeric_value = grade_map.get(grade)
        if numeric_value is not None:
            numeric_grades.append(numeric_value)

        if numeric_value is not None and numeric_value >= 1.0:
            passed_count += 1
        else:
            failed_count += 1
            
        if numeric_value is not None and numeric_value >= 3.0:
            good_excellent_count += 1

        total_scores.append(data.get('total_score', 0))

    gpa = statistics.mean(numeric_grades) if numeric_grades else 0.0
    sd = statistics.stdev(numeric_grades) if len(numeric_grades) > 1 else 0.0

    return {
        'total_students': total_students,
        'gpa': gpa,
        'sd': sd,
        'grade_distribution': dict(grade_distribution),
        'grade_percentages': {k: (v / total_students) * 100 for k, v in grade_distribution.items()},
        'passed_count': passed_count,
        'passed_percent': (passed_count / total_students) * 100 if total_students > 0 else 0,
        'failed_count': failed_count,
        'failed_percent': (failed_count / total_students) * 100 if total_students > 0 else 0,
        'good_excellent_count': good_excellent_count,
        'good_excellent_percent': (good_excellent_count / total_students) * 100 if total_students > 0 else 0,
        'min_score': min(total_scores) if total_scores else 0,
        'max_score': max(total_scores) if total_scores else 0,
    }

def get_pator05_data(course_id):
    """
    รวบรวมข้อมูลทั้งหมดที่จำเป็นสำหรับสร้างเอกสาร ปถ.05 สำหรับ Course ที่ระบุ
    """
    course = db.session.query(Course).options(
        joinedload(Course.subject).joinedload(Subject.subject_group),
        joinedload(Course.classroom).joinedload(Classroom.grade_level),
        joinedload(Course.classroom).joinedload(Classroom.advisors),
        joinedload(Course.semester).joinedload(Semester.academic_year),
        joinedload(Course.teachers),
        # [FIX 7.3.3] Load GradedItems AND Indicators separately
        joinedload(Course.lesson_plan).joinedload(LessonPlan.learning_units)
            .joinedload(LearningUnit.graded_items)
            .joinedload(GradedItem.dimension), # Load dimension for totals
        joinedload(Course.lesson_plan).joinedload(LessonPlan.learning_units)
            .joinedload(LearningUnit.indicators) # This is the list we need
            .joinedload(Indicator.standard) # Load standard for code
    ).get(course_id)

    if not course:
        return None # หรือ raise Exception

    # --- 1. ดึงข้อมูลพื้นฐาน ---
    semester = course.semester
    academic_year = semester.academic_year
    classroom = course.classroom
    subject = course.subject
    teachers = course.teachers
    advisors = classroom.advisors
    lesson_plan = course.lesson_plan

    # --- 2. ดึงข้อมูลโรงเรียน (จาก Settings) ---
    settings_keys = ['school_name', 'school_district', 'school_province', 'school_affiliation', 'school_logo_path']
    settings_q = Setting.query.filter(Setting.key.in_(settings_keys)).all()
    school_info = {s.key: s.value for s in settings_q}
    # สร้าง URL สำหรับโลโก้ (ถ้ามี)
    if school_info.get('school_logo_path'):
          school_info['school_logo_url'] = url_for('static', filename=f"uploads/{school_info['school_logo_path']}", _external=True)
    else:
          school_info['school_logo_url'] = None

    # --- [NEW] ดึงข้อมูล ผอ./รอง ผอ. จากตำแหน่ง ---
    director_full_name = ".............................." # Default placeholder
    deputy_director_full_name = ".............................." # Default placeholder

    # 1. หา ผอ. จาก Setting
    director_id_setting = Setting.query.filter_by(key='director_user_id').first()
    if director_id_setting and director_id_setting.value:
        try:
            director = db.session.get(User, int(director_id_setting.value))
            if director:
                director_full_name = director.full_name
        except (ValueError, TypeError):
            pass # Ignore if ID is invalid

    # 2. หา รอง ผอ. วิชาการ จาก Department (สมมติว่าชื่อ "ฝ่ายวิชาการ")
    # TODO: Adjust "ฝ่ายวิชาการ" if the department name is different in your system
    academic_dept = AdministrativeDepartment.query.filter_by(name="ฝ่ายวิชาการ").options(
        joinedload(AdministrativeDepartment.vice_director) # Load the user object
    ).first()
    if academic_dept and academic_dept.vice_director:
        deputy_director_full_name = academic_dept.vice_director.full_name

    # เพิ่มชื่อเข้าไปใน school_info
    school_info['director_full_name'] = director_full_name
    school_info['deputy_director_full_name'] = deputy_director_full_name
    # --- [END NEW] ---

    # --- 3. ดึงข้อมูลนักเรียนและผลการเรียนสรุป ---
    enrollments = db.session.query(Enrollment).options(
        joinedload(Enrollment.student)
    ).filter(
        Enrollment.classroom_id == classroom.id
    ).join(Student, Enrollment.student_id == Student.id) \
    .order_by(Enrollment.roll_number, Student.student_id).all()

    student_ids = [e.student_id for e in enrollments]
    course_grades = db.session.query(CourseGrade).filter(
        CourseGrade.course_id == course.id,
        CourseGrade.student_id.in_(student_ids)
    ).all()
    course_grades_map = {cg.student_id: cg for cg in course_grades}

    # --- 4. คำนวณสถิติเกรด (สำหรับหน้าปก) ---
    grade_stats = {'4': 0, '3.5': 0, '3': 0, '2.5': 0, '2': 0, '1.5': 0, '1': 0, '0': 0, 'ร': 0, 'มส': 0}
    total_students = len(enrollments)
    for cg in course_grades:
        if cg.final_grade in grade_stats:
            grade_stats[cg.final_grade] += 1
        # Handle cases where final_grade might be None initially
        elif cg.final_grade is None:
            # Decide how to count None grades if necessary, e.g., count as 'ร'
            # grade_stats['ร'] += 1
            pass

    grade_stats_percent = {k: round((v / total_students) * 100, 2) if total_students > 0 else 0 for k, v in grade_stats.items()}

    # --- 5. ดึงโครงสร้างคะแนนจาก Lesson Plan ---
    score_structure = {'units': [], 'midterm_total': 0, 'final_total': 0, 'collected_total': 0}
    if lesson_plan:
        units_data = []
        for unit in sorted(lesson_plan.learning_units, key=lambda u: u.sequence):
            unit_info = {
                'unit_id': unit.id,
                'title': unit.title,
                'items': [],
                'graded_items_structure': [], # [FIX 7.3.14] Add this for scores.html
                'midterm_score': unit.midterm_score or 0,
                'final_score': unit.final_score or 0
            }
            
            # --- [FIX 7.3.3] Step 1: Calculate K/P/A totals from GradedItems
            k_total, p_total, a_total = 0, 0, 0
            summative_items_info = []
            # Loop through GradedItems just to get totals
            for item in unit.graded_items: 
                if item.max_score is not None:
                    if item.dimension.code == 'K':
                        k_total += item.max_score
                    elif item.dimension.code == 'P':
                        p_total += item.max_score
                    elif item.dimension.code == 'A':
                        a_total += item.max_score
                # [FIX 7.3.14] Populate structure for scores.html
                unit_info['graded_items_structure'].append({
                    'id': item.id,
                    'max_score': item.max_score,
                    'dimension': item.dimension.code if item.dimension else '?'
                })
                # Check for "Summative"
                if item.indicator_type == 'SUMMATIVE':
                    # [FIX 7.3.4] Store dimension code and name
                    summative_items_info.append({
                        'name': item.name,
                        'dimension_code': item.dimension.code if item.dimension else '?'
                    })

            # --- [FIX 7.3.3] Step 2: Build item rows from Indicators
            # Loop through Indicators (from Tab 1) to build the rows
            sorted_indicators = sorted(unit.indicators, key=lambda i: (i.standard.code, i.code))
            if not sorted_indicators and (k_total > 0 or p_total > 0 or a_total > 0):
                # If no indicators, but scores exist, show a placeholder row
                unit_info['items'].append({
                    'id': f"unit_{unit.id}_placeholder",
                    'indicator_description': "(บันทึกคะแนนเก็บรวมของหน่วย)",
                    'max_score': None, 'dimension': None, 'is_summative': False
                })
            else:
                for indicator in sorted_indicators:
                    indicator_desc = f"[{indicator.standard.code} {indicator.code}] {indicator.description}"
                    unit_info['items'].append({
                        'id': indicator.id,
                        'indicator_description': indicator_desc,
                        'max_score': None, # Scores are now in summary row
                        'dimension': None, # Scores are now in summary row
                        'is_summative': False # Logic moved to summary row
                    })

            # --- [FIX 7.3.3] Step 3: Store totals in unit_info
            unit_info['k_total'] = k_total
            unit_info['p_total'] = p_total
            unit_info['a_total'] = a_total
            unit_info['unit_collected_total'] = k_total + p_total + a_total
            unit_info['summative_items_info'] = summative_items_info
            
            units_data.append(unit_info)

        score_structure['units'] = units_data
        score_structure['midterm_total'] = sum(u['midterm_score'] for u in units_data)
        score_structure['final_total'] = sum(u['final_score'] for u in units_data)
        score_structure['collected_total'] = sum(u['unit_collected_total'] for u in units_data)
        # Ensure ratios add up if defined, fallback if not
    # --- [ตรรกะการคำนวณใหม่ทั้งหมดตามหลักบัญญัติไตรยางค์] ---

    # 1. ดึง "สัดส่วนที่ตั้งค่าไว้" จาก Lesson Plan (ถ้าไม่มีให้เป็น 0)
    #    during_semester_ratio จะได้ค่า = 80
    during_semester_ratio = lesson_plan.target_mid_ratio if lesson_plan and lesson_plan.target_mid_ratio is not None else 0
    #    final_exam_ratio จะได้ค่า = 20
    final_exam_ratio = lesson_plan.target_final_ratio if lesson_plan and lesson_plan.target_final_ratio is not None else 0

    # 2. ดึง "คะแนนดิบรวม" ที่คำนวณไว้แล้ว
    collected_raw_total = score_structure['collected_total'] # ได้ค่า = 30
    midterm_raw_total = score_structure['midterm_total']     # ได้ค่า = 10

    # 3. คำนวณหา "คะแนนดิบรวมของส่วนระหว่างภาค"
    #    during_semester_raw_total = 30 + 10 = 40
    during_semester_raw_total = collected_raw_total + midterm_raw_total
    
    # 4. คำนวณสัดส่วนสุดท้าย
    final_ratio_collected = 0
    final_ratio_midterm = 0
    
    if during_semester_raw_total > 0: # (40 > 0)
        # หาตัวคูณ (Scaling Factor)
        # scaling_factor = 80 / 40 = 2
        scaling_factor = during_semester_ratio / during_semester_raw_total
        
        # คำนวณสัดส่วนสุดท้ายของคะแนนเก็บและกลางภาค
        # final_ratio_collected = 30 * 2 = 60
        final_ratio_collected = collected_raw_total * scaling_factor
        
        # final_ratio_midterm = 10 * 2 = 20
        final_ratio_midterm = midterm_raw_total * scaling_factor
    
    # 5. กำหนดค่าทั้งหมดลงใน score_structure
    
    # นี่คือสัดส่วนคะแนนเก็บที่คำนวณแล้ว (60)
    score_structure['ratio_collected'] = round(final_ratio_collected, 2) 
    
    # !! นี่คือสัดส่วนกลางภาคที่คำนวณแล้ว (20) !!
    score_structure['ratio_midterm'] = round(final_ratio_midterm, 2)
    
    # นี่คือสัดส่วนปลายภาค (20)
    score_structure['ratio_final'] = round(float(final_exam_ratio), 2) 
    
    score_structure['total_score_scaled'] = 100

    # --- 6. ดึงคะแนนเก็บ (Scores) ทั้งหมด ---
    actual_graded_item_ids = []
    if lesson_plan:
        # [FIX 7.3.17] Use list comprehension to get GradedItem IDs safely
        actual_graded_item_ids = [item_id for item_id, in db.session.query(GradedItem.id).join(LearningUnit).filter(
            LearningUnit.lesson_plan_id == lesson_plan.id
        ).distinct()]
    
    all_scores = db.session.query(Score).filter(
        Score.student_id.in_(student_ids),
        Score.graded_item_id.in_(actual_graded_item_ids) # Use the correct IDs
    ).all()
    scores_map = defaultdict(dict) # student_id -> graded_item_id -> score
    for score in all_scores:
        scores_map[score.student_id][score.graded_item_id] = score.score

    # --- 7. ดึงข้อมูลเวลาเรียน (Attendance) ---
    total_possible_hours = int((subject.credit or 0) * 2 * 20) # Correct total hours

    timetable_entry_ids = [entry.id for entry in course.timetable_entries]
    attendance_records_raw = db.session.query(
        AttendanceRecord.student_id,
        AttendanceRecord.attendance_date,
        AttendanceRecord.status,
        AttendanceRecord.timetable_entry_id # Need entry_id to map
    ).filter(
        AttendanceRecord.student_id.in_(student_ids),
        AttendanceRecord.timetable_entry_id.in_(timetable_entry_ids)
    ).all() # No specific order needed here, we'll map later

    # --- [NEW] Generate Hour-Based Schedule & Map ---
    hour_schedule_details = [] # List to store details for each hour [ {'hour': 1, 'month': 'พ.ค.', 'date': '16', 'entry_id': X, 'full_date': Y}, ...]
    entry_slot_map = {entry.id: entry.slot for entry in course.timetable_entries} # Map entry_id to slot object
    thai_months = ["ม.ค.", "ก.พ.", "มี.ค.", "เม.ย.", "พ.ค.", "มิ.ย.", "ก.ค.", "ส.ค.", "ก.ย.", "ต.ค.", "พ.ย.", "ธ.ค."]
    hour_counter = 1

    if semester.start_date and total_possible_hours > 0:
        # Sort entries by day and period to process in chronological order
        sorted_entries = sorted(course.timetable_entries, key=lambda e: (e.slot.day_of_week, e.slot.period_number))
        current_date = semester.start_date
        week_num = 0 # Start week count from 0

        # Loop until we generate the expected number of hours
        while hour_counter <= total_possible_hours:
            # Find the start date of the current processing week
            start_of_week = current_date + timedelta(days=-current_date.weekday() + (week_num * 7))

            for entry in sorted_entries:
                slot = entry.slot
                # Calculate the specific date for this entry in this week
                session_date = start_of_week + timedelta(days=slot.day_of_week - 1) # Monday is 0 for weekday()

                # Check semester boundaries (optional)
                # if semester.end_date and session_date > semester.end_date: continue

                hour_schedule_details.append({
                    'hour': hour_counter,
                    'month': thai_months[session_date.month - 1],
                    'date': str(session_date.day),
                    'entry_id': entry.id,
                    'full_date': session_date.isoformat()
                })
                hour_counter += 1
                if hour_counter > total_possible_hours: break # Stop exactly at total hours
            if hour_counter > total_possible_hours: break
            week_num += 1 # Move to the next week calculation

    # --- [NEW] Process Attendance Marks per Student per Hour ---
    attendance_marks_by_student = defaultdict(dict) # student_id -> {'H1': 'PRESENT', 'H2': 'ABSENT', ...}
    attendance_summary_by_student = defaultdict(lambda: {'total': 0, 'present': 0, 'absent': 0, 'late': 0, 'leave': 0, 'total_possible': total_possible_hours})

    # Create a map of raw records: student_id -> {(entry_id, date_iso): status}
    raw_records_map = defaultdict(dict)
    for rec in attendance_records_raw:
        raw_records_map[rec.student_id][(rec.timetable_entry_id, rec.attendance_date.isoformat())] = rec.status

    # Loop through each student and EACH HOUR in the schedule
    for student_id in student_ids:
        summary = attendance_summary_by_student[student_id]
        summary['total_possible'] = total_possible_hours

        for hour_detail in hour_schedule_details:
            hour_key = f"H{hour_detail['hour']}"
            lookup_key = (hour_detail['entry_id'], hour_detail['full_date'])
            status = raw_records_map.get(student_id, {}).get(lookup_key, 'PRESENT')
            attendance_marks_by_student[student_id][hour_key] = status
            status_map = {'PRESENT': 'present', 'ABSENT': 'absent', 'LATE': 'late', 'LEAVE': 'leave'}
            if status in status_map:
                    summary[status_map[status]] += 1
            summary['total'] += 1
    # --- End Attendance Processing ---
    schedule_by_month = defaultdict(list)
    for detail in hour_schedule_details:
        schedule_by_month[detail['month']].append(detail)
    # --- 8. ดึงข้อมูลประเมินคุณลักษณะ (ถ้าต้องการ) ---
    advisor_records = db.session.query(AdvisorAssessmentRecord).filter(
            AdvisorAssessmentRecord.student_id.in_(student_ids),
            AdvisorAssessmentRecord.semester_id == semester.id
    ).options(joinedload(AdvisorAssessmentRecord.scores).joinedload(AdvisorAssessmentScore.topic)).all()
    advisor_scores_map = {} # student_id -> topic_id -> score_value
    for rec in advisor_records:
        student_map = {}
        for score in rec.scores:
            student_map[score.topic_id] = score.score_value
        advisor_scores_map[rec.student_id] = student_map
    # อาจจะต้องดึง AssessmentTemplate และ RubricLevel มา map เป็น ดีเยี่ยม/ดี/ผ่าน ด้วย


    # --- 9. ประกอบร่างข้อมูลทั้งหมด ---
    pator05_data = {
        'school_info': school_info,
        'course_info': {
            'subject_code': subject.subject_code,
            'subject_name': subject.name,
            'credit': subject.credit,
            'hours_per_week': int(subject.credit * 2) if subject.credit else 0, # Assuming 1 credit = 2 hours/week
            'subject_group': subject.subject_group.name,
            'grade_level': classroom.grade_level.name,
            'classroom_name': classroom.name,
            'semester_term': semester.term,
            'academic_year': academic_year.year,
            'teachers': [f"{t.name_prefix or ''}{t.first_name} {t.last_name}" for t in teachers],
            'advisors': [f"{a.name_prefix or ''}{a.first_name} {a.last_name}" for a in advisors],
        },
        'hour_schedule_details': hour_schedule_details,
        'schedule_by_month': dict(schedule_by_month),
        'grade_stats': grade_stats,
        'grade_stats_percent': grade_stats_percent,
        'total_students': total_students,
        'score_structure': score_structure,
        'students_data': [],
        # เพิ่มข้อมูลเกณฑ์/คำชี้แจงจากหน้า 2, 11 ถ้าต้องการ
    }

    # วนลูปสร้างข้อมูลนักเรียนแต่ละคน
    for enrollment in enrollments:
        student = enrollment.student
        
        # --- [NEW] Logic for Remediated Midterm Score (for Export Only) ---
        course_grade = course_grades_map.get(student.id) # Get the CourseGrade object
        original_midterm_score = course_grade.midterm_score if course_grade else None
        
        midterm_score_for_export = original_midterm_score # Default to original

        if course_grade and course_grade.midterm_remediated_score is not None:
            # Policy: Use the remediated score for this export if it exists.
            # (The template/calculations below will now use this value)
            midterm_score_for_export = course_grade.midterm_remediated_score
        # --- [END NEW] ---

        student_data = {
            'roll_number': enrollment.roll_number,
            'student_id': student.student_id,
            'full_name': f"{student.name_prefix or ''}{student.first_name} {student.last_name}",
            'status': student.status, # สถานะปัจจุบันของนักเรียน
            'scores': scores_map.get(student.id, {}), # คะแนนเก็บ {item_id: score}
            
            # --- MODIFIED: Use the determined score for export ---
            'midterm_score': midterm_score_for_export,
            
            # --- MODIFIED: Simplified lookup using 'course_grade' variable ---
            'final_score': course_grade.final_score if course_grade else None,
            'final_grade': course_grade.final_grade if course_grade else None,
            'original_final_grade': course_grade.original_final_grade if course_grade else None,
            'remediation_status': course_grade.remediation_status if course_grade else 'None',
            
            'attendance': attendance_marks_by_student.get(student.id, {}), # ข้อมูลเวลาเรียน {week: [status,...]}
            'attendance_summary': attendance_summary_by_student.get(student.id, {'total': 0, 'present': 0, 'absent': 0, 'late': 0, 'leave': 0, 'total_possible': total_possible_hours}),
            'total_possible_hours': total_possible_hours, # <-- [NEW] Pass total hours
            'advisor_scores': advisor_scores_map.get(student.id, {}), # คุณลักษณะ {topic_id: score_value}
                # คำนวณคะแนนรวม (อาจต้องใช้ logic จาก calculate_final_grades_for_course)
            'total_collected': sum(s or 0 for s in scores_map.get(student.id, {}).values()),
            # 'total_score': คำนวณจาก collected + midterm + final
            # 'attendance_summary': คำนวณสรุปเวลาเรียน (มา/ขาด/ลา/สาย)
        }

        student_data['unit_totals'] = {} # student_id -> unit_id -> total
        student_scores_for_items = scores_map.get(student.id, {})
        for unit_struct in score_structure['units']:
            unit_id = unit_struct['unit_id']
            unit_total = 0
            # Loop through the ACTUAL GradedItems structure for this unit
            for item_struct in unit_struct.get('graded_items_structure', []):
                graded_item_id = item_struct['id']
                # Sum scores using the GradedItem ID
                unit_total += (student_scores_for_items.get(graded_item_id) or 0) 
            
            student_data['unit_totals'][unit_id] = unit_total  

        # คำนวณคะแนนรวมและสรุปเวลาเรียน
        # [NOTE] This calculation now correctly uses 'midterm_score_for_export'
        # because student_data['midterm_score'] was set to it.
        student_data['total_score'] = (
            (student_data['total_collected'] or 0) +
            (student_data['midterm_score'] or 0) + # This now uses the remediated score if available
            (student_data['final_score'] or 0)
        )

        pator05_data['students_data'].append(student_data)

    return pator05_data

def get_lesson_plan_export_data(plan_id):
    """
    [REVISED v9 - Dynamic Titles & Simpler Indicators] Gathers data for ALL LearningUnits.
    - Competency/Characteristic titles are now dynamic based on Template name.
    - Indicator text simplified (code + description only).
    """
    plan = db.session.query(LessonPlan).options(
        joinedload(LessonPlan.subject).joinedload(Subject.subject_group),
        joinedload(LessonPlan.academic_year),
        selectinload(LessonPlan.courses).options(
            joinedload(Course.classroom).joinedload(Classroom.grade_level),
            selectinload(Course.teachers)
        ),
        selectinload(LessonPlan.learning_units).options(
            selectinload(LearningUnit.indicators).selectinload(Indicator.standard),
            selectinload(LearningUnit.graded_items).selectinload(GradedItem.dimension),
            selectinload(LearningUnit.assessment_items).options(
                joinedload(AssessmentItem.topic).options(
                    joinedload(AssessmentTopic.template),
                    joinedload(AssessmentTopic.parent)
                )
            ),
            selectinload(LearningUnit.sub_units).options(
                 selectinload(SubUnit.indicators).selectinload(Indicator.standard),
                 selectinload(SubUnit.graded_items).selectinload(GradedItem.dimension)
            )
        )
    ).get(plan_id)

    if not plan: return None

    # --- School Info ---
    settings_keys = ['school_name', 'school_logo_path']
    settings_q = Setting.query.filter(Setting.key.in_(settings_keys)).all()
    school_info = {s.key: s.value for s in settings_q}
    if school_info.get('school_logo_path'):
         school_info['school_logo_url'] = url_for('static', filename=f"uploads/{school_info['school_logo_path']}", _external=True)
    else: school_info['school_logo_url'] = None

    # --- General Plan Info ---
    course = plan.courses[0] if plan.courses else None
    teachers = course.teachers if course else []
    teacher_names = ", ".join([t.full_name for t in teachers]) or '-'
    grade_level = course.classroom.grade_level.name if course and course.classroom and course.classroom.grade_level else '-'
    current_teacher_id = teachers[0].id if teachers else None

    # --- Main Logic ---
    all_unit_export_data = []
    sorted_units = sorted(plan.learning_units, key=lambda u: u.sequence)

    for unit in sorted_units:
        sorted_subunits = sorted(unit.sub_units, key=lambda su: su.hour_sequence)

        # --- Determine Activities ---
        if sorted_subunits: final_activities = unit.learning_activities or unit.activities or "(โปรดระบุกิจกรรม)"
        else: final_activities = unit.learning_activities or unit.activities or "(โปรดระบุกิจกรรม)"

        # --- [REVISED] Indicator Aggregation & Text Building ---
        seen_indicator_ids = set(); all_indicators = []
        # Aggregate indicators (No change in aggregation logic)
        for ind in unit.indicators:
            if ind.id not in seen_indicator_ids: all_indicators.append(ind); seen_indicator_ids.add(ind.id)
        for sub in sorted_subunits:
            for ind in sub.indicators:
                if ind.id not in seen_indicator_ids: all_indicators.append(ind); seen_indicator_ids.add(ind.id)
        sorted_all_unit_indicators = sorted(all_indicators, key=lambda i: (i.standard.code if i.standard else '', i.code)) # Added check for standard

        # Build Indicator Text (Simplified format)
        standards_text = []; indicators_text = []; seen_standards = set()
        for indicator in sorted_all_unit_indicators:
            standard = indicator.standard
            if standard and standard.id not in seen_standards:
                standards_text.append(f"มาตรฐาน {standard.code} {standard.description}")
                seen_standards.add(standard.id)
            # --- REMOVED prefix ---
            indicators_text.append(f"{indicator.code} {indicator.description}") # Just code and description
        if not standards_text: standards_text.append("(ไม่มีมาตรฐาน)")
        if not indicators_text: indicators_text.append("(ไม่มีตัวชี้วัด)")
        # --- End Revised Indicator Logic ---

        # --- Aggregate GradedItems (Assessment Methods) ---
        seen_item_ids = set(); all_graded_items = []
        # ... (Aggregation logic same as v8) ...
        for item in unit.graded_items:
             if item.id not in seen_item_ids: all_graded_items.append(item); seen_item_ids.add(item.id)
        for sub in sorted_subunits:
            for item in sub.graded_items:
                if item.id not in seen_item_ids: all_graded_items.append(item); seen_item_ids.add(item.id)
        sorted_all_unit_items = sorted(all_graded_items, key=lambda i: i.id)
        # Build Assessment Methods Text
        assessment_methods = []
        for item in sorted_all_unit_items:
            dim_code = f"({item.dimension.code})" if item.dimension else ""
            assessment_methods.append(f"ประเมิน {item.name} {dim_code}")
        if not assessment_methods: assessment_methods.append("(ไม่มีการประเมินผล)")

        # --- [REVISED] Fetch Competencies and Characteristics with Template Name ---
        # Store as {template_name: [{"main": ..., "subs": ...}, ...]}
        dynamic_sections = {}

        # Group selected topics by template
        topics_by_template = defaultdict(list)
        for assessment_item in unit.assessment_items:
             topic = assessment_item.topic
             if topic and topic.template:
                 topics_by_template[topic.template.id].append(topic)

        # Process each template that has selected topics
        for template_id, selected_topics in topics_by_template.items():
            if not selected_topics: continue
            template = selected_topics[0].template # Get template object from the first topic
            template_name = template.name
            topic_structure = defaultdict(list) # { main_topic: [sub_topic, ...] }

            for topic in selected_topics:
                 if topic.parent: # Sub-topic
                     if topic.parent.name not in topic_structure: topic_structure[topic.parent.name] = []
                     if topic.name not in topic_structure[topic.parent.name]: topic_structure[topic.parent.name].append(topic.name)
                 else: # Main topic
                     if topic.name not in topic_structure: topic_structure[topic.name] = []

            # Convert to list format for template
            structured_list = [{"main": main, "subs": subs} for main, subs in topic_structure.items()]

            # Store using template name as key (e.g., dynamic_sections['สมรรถนะ...'] = ...)
            # We assume template names are unique enough for this purpose
            dynamic_sections[template_name] = structured_list

        # --- End Revised Competency/Characteristic Logic ---

        # --- Fetch Post Teaching Log ---
        post_teaching_log_data = {'log_content': None, 'problems_obstacles': None, 'solutions': None}
        # ... (logic remains the same) ...
        if current_teacher_id:
            log_entry = PostTeachingLog.query.filter_by(learning_unit_id=unit.id, teacher_id=current_teacher_id, classroom_id=None).first()
            if log_entry:
                post_teaching_log_data['log_content'] = log_entry.log_content
                post_teaching_log_data['problems_obstacles'] = log_entry.problems_obstacles
                post_teaching_log_data['solutions'] = log_entry.solutions


        # --- Assemble Final Data Packet ---
        unit_export_data = {
            'plan_number': unit.sequence,
            'school_info': school_info,
            'plan_info': { # Basic info
                'unit_title': unit.title, 'unit_sequence': unit.sequence,
                'total_unit_hours': unit.hours or 1, 'subject_name': plan.subject.name,
                'subject_code': plan.subject.subject_code, 'subject_group': plan.subject.subject_group.name if plan.subject.subject_group else '-',
                'grade_level': grade_level, 'teacher_names': teacher_names,
            },
            'learning_standard': { 'standards_text': standards_text, 'indicators_text': indicators_text },
            'learning_objectives': unit.learning_objectives or '-',
            'core_concepts': unit.core_concepts or '-',
            'learning_content': unit.learning_content or '-',
            'activities': final_activities,
            'media_sources': unit.media_sources or '-',
            # [REVISED] Pass the dictionary containing dynamic sections
            'dynamic_sections': dynamic_sections,
            'assessment_methods': assessment_methods,
            'post_teaching_log': post_teaching_log_data
        }
        all_unit_export_data.append(unit_export_data)

    return all_unit_export_data

def get_student_dashboard_data(student_id):
    """
    ดึงข้อมูลสรุปผลการเรียน, การเข้าเรียน, การประเมิน, และการแจ้งเตือน
    สำหรับนักเรียนที่ระบุ ในภาคเรียนปัจจุบัน
    """
    student = db.session.get(Student, student_id)
    if not student:
        return None

    current_semester = Semester.query.filter_by(is_current=True).first()
    if not current_semester:
        return {
            'student': student,
            'academic_summary': [],
            'assessment_summary': [],
            'warnings': []
        }

    # --- 1. ดึงข้อมูลผลการเรียน (Academic Summary) ---
    academic_summary_list = []
    # หา Course ทั้งหมดที่นักเรียนลงทะเบียนในเทอมปัจจุบัน
    student_enrollments = Enrollment.query.join(Classroom).filter(
        Enrollment.student_id == student_id,
        Classroom.academic_year_id == current_semester.academic_year_id
    ).first() # สมมติว่านักเรียนอยู่ห้องเดียวในปีนั้น

    if student_enrollments:
        classroom_id = student_enrollments.classroom_id
        courses_in_classroom = Course.query.filter_by(
            classroom_id=classroom_id,
            semester_id=current_semester.id
        ).options(
            joinedload(Course.subject),
            joinedload(Course.teachers)
        ).all()

        for course in courses_in_classroom:
            # ใช้ Service กลางคำนวณเกรด
            all_student_grades, max_scores = calculate_final_grades_for_course(course)
            # หาข้อมูลเฉพาะของนักเรียนคนนี้
            student_grade_data = next((s for s in all_student_grades if s['student'].id == student_id), None)

            if student_grade_data:
                # ดึงข้อมูลการเข้าเรียนสำหรับวิชานี้
                attendance_counts = db.session.query(
                    AttendanceRecord.status, func.count(AttendanceRecord.id)
                ).join(TimetableEntry).filter(
                    AttendanceRecord.student_id == student_id,
                    TimetableEntry.course_id == course.id
                ).group_by(AttendanceRecord.status).all()
                attendance_summary = Counter({status: count for status, count in attendance_counts})

                academic_summary_list.append({
                    'course': course,
                    'collected_score': student_grade_data.get('collected_score', 0),
                    'midterm_score': student_grade_data.get('midterm_score'),
                    'final_score': student_grade_data.get('final_score'),
                    'total_score': student_grade_data.get('total_score', 0),
                    'grade': student_grade_data.get('grade', '-'),
                    'max_collected_score': max_scores.get('collected', 0),
                    'max_midterm_score': max_scores.get('midterm', 0),
                    'max_final_score': max_scores.get('final', 0),
                    'grand_max_score': max_scores.get('grand_total', 0),
                    'attendance': { # ใส่ค่าเริ่มต้น 0 สำหรับสถานะที่อาจไม่มี
                        'PRESENT': attendance_summary.get('PRESENT', 0),
                        'LATE': attendance_summary.get('LATE', 0),
                        'ABSENT': attendance_summary.get('ABSENT', 0),
                        'LEAVE': attendance_summary.get('LEAVE', 0),
                    }
                })

# --- 2. [REVISED] ดึงข้อมูลการประเมิน (Assessment Summary) ---
    assessment_summary_list = []
    # Dictionary to hold structured data: {template_id: {'name': ..., 'rubric_map': ..., 'topics': {topic_id: {'name': ..., 'advisor_score': ..., 'course_scores': [], 'is_main': ..., 'sub_topics': {sub_topic_id: {...}}}}}}
    structured_assessment_data = {}

    # Helper function to ensure template exists in structure
    def ensure_template_structure(template):
        if template.id not in structured_assessment_data:
            structured_assessment_data[template.id] = {
                'name': template.name,
                'rubric_map': {level.value: level.label for level in template.rubric_levels},
                'topics': {} # Store topics by ID for easier lookup
            }
        return structured_assessment_data[template.id]

    # Helper function to ensure topic exists in structure
    def ensure_topic_structure(template_struct, topic):
         # Ensure main topic exists
        main_topic_id = topic.parent_id if topic.parent_id else topic.id
        main_topic_name = topic.parent.name if topic.parent else topic.name

        if main_topic_id not in template_struct['topics']:
            template_struct['topics'][main_topic_id] = {
                'id': main_topic_id,
                'name': main_topic_name,
                'advisor_score': None,
                'course_scores': [],
                'is_main': True,
                'sub_topics': {} # Store subtopics by ID
            }
        main_topic_struct = template_struct['topics'][main_topic_id]

        # If the current topic IS a sub-topic, ensure its structure exists
        if topic.parent_id:
             if topic.id not in main_topic_struct['sub_topics']:
                  main_topic_struct['sub_topics'][topic.id] = {
                       'id': topic.id,
                       'name': topic.name,
                       'advisor_score': None,
                       'course_scores': [],
                       'is_main': False
                  }
             return main_topic_struct['sub_topics'][topic.id] # Return sub-topic structure
        else:
             return main_topic_struct # Return main topic structure

    # Process Advisor Assessment
    advisor_record = AdvisorAssessmentRecord.query.filter_by(
        student_id=student_id,
        semester_id=current_semester.id
    ).options(
        # Eager load necessary relationships including parent topics
        joinedload(AdvisorAssessmentRecord.scores).joinedload(AdvisorAssessmentScore.topic).options(
            joinedload(AssessmentTopic.template).joinedload(AssessmentTemplate.rubric_levels),
            joinedload(AssessmentTopic.parent) # Load parent
        )
    ).first()

    if advisor_record:
        for score in advisor_record.scores:
            topic = score.topic
            if not topic or not topic.template: continue # Skip if data is inconsistent
            template_struct = ensure_template_structure(topic.template)
            topic_struct = ensure_topic_structure(template_struct, topic)
            topic_struct['advisor_score'] = score.score_value

    # Process Qualitative Scores from Courses
    qualitative_scores = QualitativeScore.query.filter(
        QualitativeScore.student_id == student_id,
        QualitativeScore.course_id.in_([c.id for c in courses_in_classroom] if student_enrollments else [])
    ).options(
        joinedload(QualitativeScore.topic).options(
            joinedload(AssessmentTopic.template).joinedload(AssessmentTemplate.rubric_levels),
            joinedload(AssessmentTopic.parent) # Load parent
        ),
        joinedload(QualitativeScore.course).joinedload(Course.subject)
    ).all()

    for q_score in qualitative_scores:
        topic = q_score.topic
        if not topic or not topic.template: continue # Skip inconsistent data
        template_struct = ensure_template_structure(topic.template)
        topic_struct = ensure_topic_structure(template_struct, topic)
        topic_struct['course_scores'].append({
            'subject': q_score.course.subject.name,
            'score': q_score.score_value
        })

    # Convert the structured dictionary into the final list format for the template
    for template_id, data in structured_assessment_data.items():
        main_topic_list = []
        # Sort main topics by ID or name
        sorted_main_topic_ids = sorted(data['topics'].keys())

        for main_topic_id in sorted_main_topic_ids:
            main_topic_data = data['topics'][main_topic_id]
            sub_topic_list = []
            # Sort sub topics by ID or name
            sorted_sub_topic_ids = sorted(main_topic_data['sub_topics'].keys())

            for sub_topic_id in sorted_sub_topic_ids:
                sub_topic_list.append(main_topic_data['sub_topics'][sub_topic_id])

            main_topic_list.append({
                'name': main_topic_data['name'],
                'advisor_score': main_topic_data['advisor_score'],
                'course_scores': main_topic_data['course_scores'],
                'sub_topics': sub_topic_list # Add the sorted list of subtopics
            })

        assessment_summary_list.append({
             'name': data['name'], # Template Name
             'rubric_map': data['rubric_map'],
             'topics': main_topic_list # List of main topics, each potentially containing sub_topics
         })

    # Sort templates if needed
    assessment_summary_list.sort(key=lambda x: x['name'])

    # --- 3. ดึงการแจ้งเตือน (Warnings) ---
    active_warnings = AttendanceWarning.query.filter(
        AttendanceWarning.student_id == student_id,
        AttendanceWarning.course.has(semester_id=current_semester.id),
        AttendanceWarning.status == 'ACTIVE'
    ).options(joinedload(AttendanceWarning.course).joinedload(Course.subject)).all()

    return {
        'student': student,
        'academic_summary': sorted(academic_summary_list, key=lambda x: x['course'].subject.subject_code), # Sort by subject code
        'assessment_summary': assessment_summary_list,
        'warnings': active_warnings
    }

def check_graduation_readiness(student_id, academic_year_id):
    """
    [REVISED v2] Checks graduation readiness (M.3/M.6) based on grades and credits.
    Returns detailed reasons if not ready.

    Args:
        student_id (int): The ID of the student.
        academic_year_id (int): The ID of the academic year graduation is being considered for.

    Returns:
        tuple(bool | None, str): (is_ready, reason)
             is_ready (bool): True if ready, False otherwise. None if not applicable.
             reason (str): Explanation.
    """
    student = db.session.get(Student, student_id)
    target_year = db.session.get(AcademicYear, academic_year_id)
    if not student or not target_year:
        return None, 'Student or Academic Year not found'

    enrollment = Enrollment.query.join(Classroom).filter(
        Enrollment.student_id == student_id,
        Classroom.academic_year_id == academic_year_id
    ).join(GradeLevel).options(joinedload(Enrollment.classroom).joinedload(Classroom.grade_level)).first()

    if not enrollment or not enrollment.classroom or not enrollment.classroom.grade_level:
        return None, 'Student not enrolled or grade level info missing for graduation year'

    grade_level = enrollment.classroom.grade_level

    # --- Check graduating level and required credits ---
    required_credits = None
    if grade_level.short_name == 'ม.3': required_credits = 77 # Example
    elif grade_level.short_name == 'ม.6': required_credits = 81 # Example
    else: return None, 'Not a graduating level'
    # ---

    reasons_not_ready = [] # Store multiple reasons

    # --- 1. Check failing grades ---
    semesters_in_year = Semester.query.filter_by(academic_year_id=academic_year_id).all()
    semester_ids = [s.id for s in semesters_in_year]

    failing_grades_count = db.session.query(func.count(CourseGrade.id)).join(Course).filter(
         CourseGrade.student_id == student_id,
         Course.semester_id.in_(semester_ids),
         CourseGrade.final_grade.in_(['0', 'ร', 'มส'])
         # Optional stricter check for unresolved remediations
    ).scalar()

    if failing_grades_count > 0:
        reasons_not_ready.append(f'มีผลการเรียนไม่ผ่าน ({failing_grades_count} รายการ)')
    # ---

    # --- 2. Check accumulated credits ---
    all_year_ids_to_include = db.session.query(AcademicYear.id).filter(
        AcademicYear.year <= target_year.year
    ).scalar_subquery()

    passed_credits_result = db.session.query(func.sum(Subject.credit)).join(
        Course, Subject.id == Course.subject_id
    ).join(
        CourseGrade, Course.id == CourseGrade.course_id
    ).join(
         Semester, Course.semester_id == Semester.id
    ).filter(
        CourseGrade.student_id == student_id,
        Semester.academic_year_id.in_(all_year_ids_to_include),
        CourseGrade.final_grade.in_(['1', '1.5', '2', '2.5', '3', '3.5', '4'])
    ).scalar()

    total_credits_earned = passed_credits_result or 0

    if total_credits_earned < required_credits:
        reasons_not_ready.append(f'หน่วยกิตไม่ถึงเกณฑ์ ({total_credits_earned:.1f}/{required_credits})')
    # ---

    # --- Final Decision ---
    if not reasons_not_ready:
        return True, 'ผ่านเกณฑ์การจบหลักสูตร'
    else:
        return False, '; '.join(reasons_not_ready) # Join reasons with semicolon
    # ---

def promote_students_to_next_year(source_academic_year_id, target_academic_year_id, promotion_criteria=None):
    """
    [REVISED v2 - Auto-Create Classrooms] Service function to promote students.
    - Auto-creates target classrooms if they don't exist.
    - Moves advisors for non-graduating levels.
    - Creates new Enrollments for students meeting criteria.
    - Flags students not meeting criteria as RepeatCandidates.
    - Sets graduating students' status.

    Args:
        source_academic_year_id (int): ID of the academic year to promote FROM.
        target_academic_year_id (int): ID of the academic year to promote TO.
        promotion_criteria (dict, optional): Criteria for promotion. Defaults to None.

    Returns:
        dict: Summary of actions taken (promoted, graduated, flagged, errors, classrooms_created).
    """
    source_year = db.session.get(AcademicYear, source_academic_year_id)
    target_year = db.session.get(AcademicYear, target_academic_year_id)

    if not source_year or not target_year:
        return {'errors': ['Invalid source or target academic year ID.']}
    if source_year.year >= target_year.year:
         return {'errors': ['Target year must be after source year.']}

    summary = {'promoted': 0, 'graduated': 0, 'flagged_repeat': 0, 'classrooms_created': 0, 'errors': []}
    processed_student_ids = set()

    # --- Graduating Levels & Promotion Check (Same as before) ---
    graduating_grade_short_names = ['ม.3', 'ม.6'] # TODO: Configurable
    graduating_grade_level_ids = [gl.id for gl in GradeLevel.query.filter(GradeLevel.short_name.in_(graduating_grade_short_names)).all()]

    def check_promotion_eligibility(student_id, source_year_id):
         failed_grades = db.session.query(CourseGrade).join(Course).join(Classroom).filter(
              CourseGrade.student_id == student_id,
              Classroom.academic_year_id == source_year_id,
              CourseGrade.final_grade.in_(['0', 'ร', 'มส'])
         ).count()
         return failed_grades == 0
    # ---

    # Get source classrooms
    source_classrooms = Classroom.query.filter_by(academic_year_id=source_year.id).options(
        joinedload(Classroom.grade_level),
        selectinload(Classroom.advisors) # Removed enrollments load due to lazy='dynamic'
    ).order_by(Classroom.name).all()

    # Pre-fetch target classrooms into a map for quick lookup
    target_classrooms_map = {c.name: c for c in Classroom.query.filter_by(academic_year_id=target_year.id).all()}
    # Pre-fetch all grade levels into a map for quick lookup by short_name
    grade_levels_map = {gl.short_name: gl for gl in GradeLevel.query.all()}

    for old_classroom in source_classrooms:
        grade_level = old_classroom.grade_level
        if not grade_level:
             summary['errors'].append(f"Skipping {old_classroom.name}: Missing grade level information.")
             continue

        is_graduating_level = grade_level.id in graduating_grade_level_ids

        # --- Handle Graduating Students (Same as before) ---
        if is_graduating_level:
            # Need to load enrollments lazily now
            student_ids_in_class = [e.student_id for e in old_classroom.enrollments if e.student_id not in processed_student_ids]
            if student_ids_in_class:
                updated_count = Student.query.filter(Student.id.in_(student_ids_in_class)).update(
                    {'status': 'จบการศึกษา'}, synchronize_session=False
                )
                summary['graduated'] += updated_count
                processed_student_ids.update(student_ids_in_class)
            old_classroom.advisors = []
            continue

        # --- [REVISED] Handle Non-Graduating Students with Auto-Create Classroom ---
        target_classroom = None
        target_grade_level = None
        target_classroom_name = ""

        try:
            # 1. Calculate Target Classroom Name and Grade Level
            current_grade_num_str = grade_level.short_name.split('.')[-1]
            if not current_grade_num_str.isdigit():
                 raise ValueError(f"Cannot parse grade number from '{grade_level.short_name}'")
            next_grade_num = int(current_grade_num_str) + 1
            next_grade_short_name = f"ม.{next_grade_num}" # Assumes "ม.X" format

            target_classroom_name = old_classroom.name.replace(grade_level.short_name, next_grade_short_name)
            target_grade_level = grade_levels_map.get(next_grade_short_name)

            if not target_grade_level:
                 raise ValueError(f"Target grade level '{next_grade_short_name}' not found in database.")

            # 2. Find or Create Target Classroom
            target_classroom = target_classrooms_map.get(target_classroom_name)

            if not target_classroom:
                # --- AUTO-CREATE LOGIC ---
                print(f"Target classroom '{target_classroom_name}' not found. Creating...") # Add logging
                target_classroom = Classroom(
                    name=target_classroom_name,
                    academic_year_id=target_year.id,
                    grade_level_id=target_grade_level.id
                )
                db.session.add(target_classroom)
                db.session.flush() # IMPORTANT: Assign ID within the transaction
                target_classrooms_map[target_classroom_name] = target_classroom # Add to map
                summary['classrooms_created'] += 1
                print(f"Created classroom ID: {target_classroom.id}") # Add logging
                # --- END AUTO-CREATE ---
            else:
                 print(f"Found target classroom '{target_classroom_name}' with ID: {target_classroom.id}") # Add logging


        except ValueError as ve:
             error_msg = f"Error determining target for {old_classroom.name}: {str(ve)}"
             summary['errors'].append(error_msg)
             current_app.logger.warning(error_msg)
             continue # Skip this classroom if target cannot be determined/created
        except Exception as e: # Catch other potential errors during creation/lookup
             error_msg = f"Unexpected error processing target for {old_classroom.name}: {str(e)}"
             summary['errors'].append(error_msg)
             current_app.logger.error(error_msg, exc_info=True)
             continue


        # 3. Move Advisors (Same as before, using the found or created target_classroom)
        current_advisors = list(old_classroom.advisors)
        target_classroom.advisors = current_advisors
        old_classroom.advisors = []

        # 4. Process Students (Same as before, using the found or created target_classroom)
        # Need to load enrollments lazily now
        is_ready, reason = check_graduation_readiness(student.id, source_year.id) # Now returns tuple
        eligible = is_ready # Promotion eligibility still based on readiness in source year

        # If graduating level, check the approval status (Assume you add a field like student.graduation_approved)
        # if is_graduating_level:
        #     if student.graduation_approved: # Check flag set by Academic/Director
        #         student.status = 'จบการศึกษา'
        #         summary['graduated'] += 1
        #         processed_student_ids.add(student.id)
        #         # Skip enrollment creation for graduates
        #         continue
        #     else:
        #         # If graduation not approved (maybe still failing/pending), don't change status
        #         # Log or handle this case? For now, just skip.
        #         summary['errors'].append(f"Graduation for {student.full_name} not yet approved or student not ready.")
        #         processed_student_ids.add(student.id) # Mark as processed for this function's scope
        #         continue
        # --- End Graduating level specific check ---


        if eligible: # For non-graduating levels, 'eligible' means ready to promote
            # Create new Enrollment in target classroom
            new_enrollment = Enrollment(
                student_id=student.id,
                classroom_id=target_classroom.id,
                roll_number=enrollment.roll_number
            )
            db.session.add(new_enrollment)
            summary['promoted'] += 1
        else: # Not eligible (failing grades or insufficient credits in source year)
            # Flag as Repeat Candidate
            existing_flag = RepeatCandidate.query.filter_by(
                    student_id=student.id,
                    academic_year_id_failed=source_year.id
            ).first()
            if not existing_flag:
                flag = RepeatCandidate(
                    student_id=student.id,
                    previous_enrollment_id=enrollment.id,
                    academic_year_id_failed=source_year.id,
                    status='Pending Advisor Review',
                    advisor_notes=reason # Store the reason for flagging
                )
                db.session.add(flag)
                summary['flagged_repeat'] += 1
            # DO NOT create a new Enrollment

        processed_student_ids.add(student.id)

    try:
        print("Attempting to commit changes...") # Add logging
        db.session.commit()
        print("Commit successful.") # Add logging
    except Exception as e:
        db.session.rollback()
        error_msg = f"Database commit failed: {str(e)}"
        summary['errors'].append(error_msg)
        current_app.logger.error(f"Error during promotion commit: {e}", exc_info=True)
        print(f"Commit failed: {error_msg}") # Add logging


    print("Promotion Summary:", summary) # Add logging
    return summary

def create_blank_lesson_plan(subject_id: int, academic_year_id: int):
    """
    Creates a new, empty LessonPlan for the given subject and year.

    Args:
        subject_id: ID of the Subject.
        academic_year_id: ID of the AcademicYear.

    Returns:
        Tuple (bool, Union[int, str]): (True, new_plan_id) on success,
                                        (False, error_message) on failure.
    """
    try:
        # Check if subject and year exist
        subject = db.session.get(Subject, subject_id)
        academic_year = db.session.get(AcademicYear, academic_year_id)
        if not subject or not academic_year:
            return False, "ไม่พบข้อมูลวิชาหรือปีการศึกษา"

        # Check if plan already exists (redundant check, but safe)
        existing_plan = LessonPlan.query.filter_by(
            subject_id=subject_id,
            academic_year_id=academic_year_id
        ).first()
        if existing_plan:
            # This should ideally be caught in the route, but good failsafe
            return False, f"มีแผนการสอนสำหรับวิชา {subject.name} ในปีการศึกษา {academic_year.year} อยู่แล้ว"

        # Create the blank plan
        new_plan = LessonPlan(
            subject_id=subject_id,
            academic_year_id=academic_year_id,
            status='ฉบับร่าง'
            # Default ratios can be set here if needed, e.g., target_mid_ratio=80, target_final_ratio=20
        )
        db.session.add(new_plan)
        # Flush to get ID before commit, needed for immediate linking
        db.session.flush()
        new_plan_id = new_plan.id
        db.session.commit() # Commit the new blank plan

        return True, new_plan_id

    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Error creating blank lesson plan for subject {subject_id}, year {academic_year_id}: {e}", exc_info=True)
        return False, f"เกิดข้อผิดพลาดในการสร้างแผนใหม่: {str(e)}"
    
def copy_lesson_plan(source_plan_id: int, target_academic_year_id: int, current_user_id: int):
    """
    Creates a copy of a lesson plan for a new academic year.

    Args:
        source_plan_id: ID of the LessonPlan to copy.
        target_academic_year_id: ID of the AcademicYear for the new plan.
        current_user_id: ID of the user performing the copy.

    Returns:
        Tuple (bool, Union[int, str]): (True, new_plan_id) on success,
                                       (False, error_message) on failure.
    """
    try:
        # 1. Fetch Source Plan with related data eagerly
        source_plan = db.session.query(LessonPlan).options(
            selectinload(LessonPlan.subject), # Load subject for error message
            selectinload(LessonPlan.learning_units).options(
                selectinload(LearningUnit.graded_items).selectinload(GradedItem.dimension), # Load dimension too
                selectinload(LearningUnit.assessment_items).selectinload(AssessmentItem.topic), # Load topic
                selectinload(LearningUnit.indicators).selectinload(Indicator.standard), # Standard indicators + standard
                selectinload(LearningUnit.sub_units).options(
                     selectinload(SubUnit.indicators).selectinload(Indicator.standard),
                     selectinload(SubUnit.graded_items).selectinload(GradedItem.dimension),
                     selectinload(SubUnit.assessment_items).selectinload(AssessmentItem.topic)
                )
            ),
            selectinload(LessonPlan.custom_indicators).selectinload(Indicator.standard), # Custom indicators + standard
            selectinload(LessonPlan.constraints)
        ).get(source_plan_id)

        if not source_plan:
            return False, "ไม่พบแผนการสอนต้นทาง"

        # 2. Check for Existing Target Plan
        target_year = db.session.get(AcademicYear, target_academic_year_id) # Get target year object for message
        if not target_year:
             return False, "ไม่พบปีการศึกษาเป้าหมาย"

        existing_target_plan = LessonPlan.query.filter_by(
            subject_id=source_plan.subject_id,
            academic_year_id=target_academic_year_id
        ).first()
        if existing_target_plan:
            subject_name = source_plan.subject.name if source_plan.subject else f"ID {source_plan.subject_id}"
            return False, f"มีแผนการสอนสำหรับวิชา {subject_name} ในปีการศึกษา {target_year.year} อยู่แล้ว"

        # 3. Create New Plan Object
        new_plan = LessonPlan(
            subject_id=source_plan.subject_id,
            academic_year_id=target_academic_year_id,
            target_mid_ratio=source_plan.target_mid_ratio,
            target_final_ratio=source_plan.target_final_ratio,
            status='ฉบับร่าง', # Always start as draft
            revision_notes=None, # Clear revision notes
            manual_scheduling_notes=source_plan.manual_scheduling_notes # Keep manual notes
        )
        db.session.add(new_plan)
        # Flush to get the new_plan.id needed for custom indicators
        db.session.flush()

        # --- Mappings to track old IDs to new objects ---
        unit_map = {} # old_unit_id -> new_unit_object
        graded_item_map = {} # old_graded_item_id -> new_graded_item_object
        assessment_item_map = {} # old_assessment_item_id -> new_assessment_item_object

        # 4. Deep Copy Learning Units and their contents
        for source_unit in sorted(source_plan.learning_units, key=lambda u: u.sequence):
            new_unit = LearningUnit(
                lesson_plan=new_plan, # Associate with new plan
                title=source_unit.title,
                sequence=source_unit.sequence,
                midterm_score=source_unit.midterm_score,
                final_score=source_unit.final_score,
                topic=source_unit.topic,
                hours=source_unit.hours,
                learning_objectives=source_unit.learning_objectives,
                learning_content=source_unit.learning_content,
                learning_activities=source_unit.learning_activities,
                core_concepts=source_unit.core_concepts,
                # activities=source_unit.activities, # Deprecated
                media_sources=source_unit.media_sources
                # DO NOT COPY reflections or PostTeachingLog
            )
            db.session.add(new_unit)
            db.session.flush() # Get new_unit.id
            unit_map[source_unit.id] = new_unit

            # 4.1 Copy Standard Indicator relationships (link to existing ones)
            # Filter out custom indicators before assigning
            standard_indicators = [ind for ind in source_unit.indicators if ind.creator_type == 'ADMIN']
            new_unit.indicators = standard_indicators

            # 4.2 Deep Copy Graded Items
            for source_item in source_unit.graded_items:
                new_item = GradedItem(
                    learning_unit=new_unit, # Associate with new unit
                    name=source_item.name,
                    max_score=source_item.max_score,
                    indicator_type=source_item.indicator_type,
                    assessment_type=source_item.assessment_type,
                    assessment_dimension_id=source_item.assessment_dimension_id,
                    is_group_assignment=source_item.is_group_assignment
                )
                db.session.add(new_item)
                db.session.flush() # Get new_item.id
                graded_item_map[source_item.id] = new_item

            # 4.3 Deep Copy Assessment Items
            for source_assess_item in source_unit.assessment_items:
                new_assess_item = AssessmentItem(
                    unit=new_unit, # Associate with new unit
                    assessment_topic_id=source_assess_item.assessment_topic_id
                )
                db.session.add(new_assess_item)
                db.session.flush() # Get new_assess_item.id
                assessment_item_map[source_assess_item.id] = new_assess_item

            # 4.4 Deep Copy SubUnits (if any)
            for source_sub_unit in sorted(source_unit.sub_units, key=lambda su: su.hour_sequence):
                 new_sub_unit = SubUnit(
                      learning_unit=new_unit, # Associate with new unit
                      title=source_sub_unit.title,
                      hour_sequence=source_sub_unit.hour_sequence,
                      activities=source_sub_unit.activities
                 )
                 db.session.add(new_sub_unit) # Add first to allow relationship assignment
                 db.session.flush() # Get new_sub_unit ID

                 # Copy relationships using the maps created
                 sub_standard_indicators = [ind for ind in source_sub_unit.indicators if ind.creator_type == 'ADMIN']
                 new_sub_unit.indicators = sub_standard_indicators # Link to existing standard ones
                 new_sub_unit.graded_items = [graded_item_map[gi.id] for gi in source_sub_unit.graded_items if gi.id in graded_item_map]
                 new_sub_unit.assessment_items = [assessment_item_map[ai.id] for ai in source_sub_unit.assessment_items if ai.id in assessment_item_map]
                 # No need to add again, already added

        # 5. Deep Copy Custom Indicators (if any) linked directly to the PLAN
        # Also copy custom indicators linked to UNITS/SUBUNITS
        all_source_custom_indicators = list(source_plan.custom_indicators) # Plan level
        for su in source_plan.learning_units:
             all_source_custom_indicators.extend([ind for ind in su.indicators if ind.creator_type == 'TEACHER']) # Unit level
             for sub in su.sub_units:
                  all_source_custom_indicators.extend([ind for ind in sub.indicators if ind.creator_type == 'TEACHER']) # SubUnit level

        # Use a set to handle potential duplicates if an indicator is linked multiple times
        unique_source_custom_indicators = {ind.id: ind for ind in all_source_custom_indicators}.values()

        custom_indicator_map = {} # old_custom_id -> new_custom_object
        for source_custom_ind in unique_source_custom_indicators:
            # Check if this custom indicator was linked to a unit/subunit that was copied
            # We need to decide where the *new* custom indicator should be linked.
            # Simplest approach: Link all copied custom indicators ONLY to the new PLAN.
            new_custom_ind = Indicator(
                lesson_plan=new_plan, # Link to new plan ONLY
                code=source_custom_ind.code,
                description=source_custom_ind.description,
                standard_id=source_custom_ind.standard_id, # Assume custom standard exists
                creator_type='TEACHER',
                creator_id=current_user_id # Assign to the user doing the copy
            )
            db.session.add(new_custom_ind)
            db.session.flush()
            custom_indicator_map[source_custom_ind.id] = new_custom_ind

        # 6. Copy Constraints
        for source_constraint in source_plan.constraints:
            new_constraint = LessonPlanConstraint(
                lesson_plan=new_plan, # Link to new plan
                constraint_type=source_constraint.constraint_type,
                value=source_constraint.value
            )
            db.session.add(new_constraint)

        # 7. Commit all changes
        db.session.commit()

        # 8. Return success and the new plan ID
        return True, new_plan.id

    except Exception as e:
        db.session.rollback()
        # Use Flask's logger
        current_app.logger.error(f"Error copying lesson plan {source_plan_id}: {e}", exc_info=True)
        return False, f"เกิดข้อผิดพลาดในการคัดลอก: {str(e)}"
    
# --- [START ADDITION] New Service Function for Copying Schedule Structure ---
def copy_schedule_structure(source_semester_id: int, target_semester_id: int):
    """
    Copies WeeklyScheduleSlots and TimeSlots from source_semester to target_semester.
    Deletes existing slots in the target semester before copying.

    Args:
        source_semester_id: ID of the source Semester.
        target_semester_id: ID of the target Semester.

    Returns:
        Tuple (bool, str): (True, success_message) or (False, error_message).
    """
    source_semester = db.session.get(Semester, source_semester_id)
    target_semester = db.session.get(Semester, target_semester_id)

    if not source_semester or not target_semester:
        return False, "ไม่พบภาคเรียนต้นทางหรือปลายทาง"

    try:
        # 1. Delete existing slots in the target semester (both types)
        # Use synchronize_session=False for potentially faster bulk deletes,
        # but be aware it bypasses ORM session tracking during delete.
        WeeklyScheduleSlot.query.filter_by(semester_id=target_semester_id).delete(synchronize_session=False)
        TimeSlot.query.filter_by(semester_id=target_semester_id).delete(synchronize_session=False)
        db.session.flush() # Apply deletions immediately within the transaction

        # 2. Copy WeeklyScheduleSlots
        source_weekly_slots = WeeklyScheduleSlot.query.filter_by(semester_id=source_semester_id).all()
        new_weekly_slots = []
        if source_weekly_slots: # Only proceed if there are slots to copy
            for slot in source_weekly_slots:
                new_slot = WeeklyScheduleSlot(
                    semester_id=target_semester_id, # Link to target semester
                    grade_level_id=slot.grade_level_id, # Keep the same grade level link
                    day_of_week=slot.day_of_week,
                    period_number=slot.period_number,
                    start_time=slot.start_time,
                    end_time=slot.end_time,
                    activity_name=slot.activity_name,
                    is_teaching_period=slot.is_teaching_period
                )
                new_weekly_slots.append(new_slot)
            if new_weekly_slots:
                db.session.bulk_save_objects(new_weekly_slots)
                current_app.logger.info(f"Copied {len(new_weekly_slots)} WeeklyScheduleSlots.")


        # 3. Copy TimeSlots (General time definitions for the semester)
        source_time_slots = TimeSlot.query.filter_by(semester_id=source_semester_id).all()
        new_time_slots = []
        if source_time_slots: # Only proceed if there are slots to copy
            for t_slot in source_time_slots:
                new_t_slot = TimeSlot(
                    semester_id=target_semester_id, # Link to target semester
                    period_number=t_slot.period_number,
                    start_time=t_slot.start_time,
                    end_time=t_slot.end_time,
                    activity_name=t_slot.activity_name,
                    is_teaching_period=t_slot.is_teaching_period
                )
                new_time_slots.append(new_t_slot)
            if new_time_slots:
                db.session.bulk_save_objects(new_time_slots)
                current_app.logger.info(f"Copied {len(new_time_slots)} TimeSlots.")


        # 4. Commit all changes
        db.session.commit()
        return True, "คัดลอกโครงสร้างตารางสอนเรียบร้อยแล้ว"

    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Error copying schedule structure from {source_semester_id} to {target_semester_id}: {e}", exc_info=True)
        return False, f"เกิดข้อผิดพลาดในการคัดลอกโครงสร้าง: {str(e)}"
# --- [END ADDITION] ---

def log_action(action: str, user=None, model=None, record_id: int = None, old_value=None, new_value=None):
    """
    Creates and saves an audit log entry. Does not commit the session.

    Args:
        action (str): Description of the action performed (e.g., "Create User", "Update Lesson Plan Status").
        user (User, optional): The user performing the action. Defaults to current_user.
        model (db.Model class, optional): The SQLAlchemy model class being affected (e.g., User, LessonPlan).
        record_id (int, optional): The primary key ID of the record being affected.
        old_value (any, optional): The value before the change. Can be simple type or dict/list.
        new_value (any, optional): The value after the change. Can be simple type or dict/list.
    """
    try:
        log_user = user if user else current_user
        # Check if user object exists and is authenticated
        if not hasattr(log_user, 'is_authenticated') or not log_user.is_authenticated:
            # Avoid logging if no user context (e.g., during startup errors, failed logins handled separately)
            # Or consider a default "System" user ID if needed
            current_app.logger.warning(f"Audit log skipped for action '{action}' due to missing authenticated user context.")
            return

        # Get model name from class if provided
        model_name_str = model.__tablename__ if model and hasattr(model, '__tablename__') else None

        # Convert complex types (like dicts or lists) to JSON strings for storage
        old_value_str = None
        if old_value is not None:
            if isinstance(old_value, (dict, list)):
                try:
                    # Use default=str as a fallback for non-serializable objects like datetime
                    old_value_str = json.dumps(old_value, ensure_ascii=False, default=str)
                except TypeError as te:
                    current_app.logger.warning(f"Audit log JSON conversion failed for old_value (action: {action}): {te}. Falling back to str().")
                    old_value_str = str(old_value) # Fallback to simple string conversion
            else:
                old_value_str = str(old_value)

        new_value_str = None
        if new_value is not None:
            if isinstance(new_value, (dict, list)):
                try:
                    new_value_str = json.dumps(new_value, ensure_ascii=False, default=str)
                except TypeError as te:
                    current_app.logger.warning(f"Audit log JSON conversion failed for new_value (action: {action}): {te}. Falling back to str().")
                    new_value_str = str(new_value)
            else:
                new_value_str = str(new_value)

        # Limit string length to prevent excessively large log entries
        max_len = 1000 # Example limit, adjust as necessary
        if old_value_str and len(old_value_str) > max_len:
            old_value_str = old_value_str[:max_len] + "..."
        if new_value_str and len(new_value_str) > max_len:
            new_value_str = new_value_str[:max_len] + "..."


        log_entry = AuditLog(
            user_id=log_user.id,
            action=action, # Renamed from action_type in model? Check your AuditLog model definition. Assuming 'action'.
            model_name=model_name_str,
            record_id=record_id,
            old_value=old_value_str,
            new_value=new_value_str,
            timestamp=datetime.utcnow() # Ensure timestamp is set here
        )
        db.session.add(log_entry)
        # The commit should happen in the calling route after the main action succeeds

    except Exception as e:
        # Log the error but don't prevent the main action from completing
        # Avoid db.session.rollback() here as it might interfere with the main transaction
        current_app.logger.error(f"Error creating audit log for action '{action}': {e}", exc_info=True)

