# FILE: app/academic/routes.py
from collections import defaultdict
from datetime import datetime
import random, json
from sqlite3 import IntegrityError
from statistics import StatisticsError, mode
from flask import current_app, jsonify, redirect, render_template, abort, flash, request, url_for
from flask_login import login_required, current_user
from flask_wtf import FlaskForm
from flask_wtf.csrf import generate_csrf, validate_csrf, CSRFError
from sqlalchemy.orm import joinedload, selectinload
from sqlalchemy import and_, func, inspect, or_
from app.academic import bp
from app import db
from app.models import (AcademicYear, AdvisorAssessmentRecord, AdvisorAssessmentScore, AssessmentItem, AssessmentTemplate, AssessmentTopic, Classroom, Course, CourseGrade, Enrollment, GradeLevel, GradedItem, Indicator, Notification, RepeatCandidate, Role,
                        LessonPlan, LearningUnit, Room, Semester, Student, TimeSlot, Standard, 
                        Subject, TimetableEntry, User, SubjectGroup, WeeklyScheduleSlot, QualitativeScore)
from app.services import calculate_final_grades_for_course, calculate_grade_statistics, check_graduation_readiness, log_action
from . import bp

@bp.route('/dashboard')
@login_required
def dashboard():
    # Note: Add role-based security check for academic affairs personnel here
    if not current_user.has_role('Academic'):
        abort(403)

    current_semester = Semester.query.filter_by(is_current=True).first_or_404()
    form = FlaskForm()
    grades_pending_review = Course.query.filter(
        Course.semester_id == current_semester.id,
        Course.grade_submission_status == 'เสนอฝ่ายวิชาการ'
    ).all()
    
    # 1. Get the selected group_id from the URL query parameters
    selected_group_id = request.args.get('group_id', type=int)

    # 2. Fetch all subject groups for the dropdown menu
    all_subject_groups = SubjectGroup.query.order_by(SubjectGroup.name).all()

    # --- 1. Comprehensive Query for ALL data needed on the page ---
    # This single query is more efficient as it fetches all related data at once.
    all_plans_in_semester = LessonPlan.query.filter(
        LessonPlan.academic_year_id == current_semester.academic_year_id
    ).options(
        selectinload(LessonPlan.learning_units).selectinload(LearningUnit.indicators).joinedload(Indicator.standard).joinedload(Standard.learning_strand),
        selectinload(LessonPlan.learning_units).selectinload(LearningUnit.assessment_items).joinedload(AssessmentItem.topic).joinedload(AssessmentTopic.template),
        selectinload(LessonPlan.learning_units).selectinload(LearningUnit.assessment_items).joinedload(AssessmentItem.topic).joinedload(AssessmentTopic.parent),
        joinedload(LessonPlan.subject).joinedload(Subject.subject_group),
        joinedload(LessonPlan.courses).joinedload(Course.teachers) # Eager load teachers for checklist
    ).all()

    # --- 2. Process Data for Overview Tabs (Indicators & Topics by Group) ---
    indicators_by_group = defaultdict(lambda: defaultdict(lambda: defaultdict(list)))
    topics_by_group = defaultdict(lambda: defaultdict(lambda: defaultdict(list)))
    all_unique_indicators = set()
    all_unique_topics = set()

    for plan in all_plans_in_semester:
        group_name = plan.subject.subject_group.name
        
        unique_indicators_in_plan = {ind for unit in plan.learning_units for ind in unit.indicators}
        all_unique_indicators.update(unique_indicators_in_plan)
        for indicator in unique_indicators_in_plan:
            if indicator.standard and indicator.standard.learning_strand:
                indicators_by_group[group_name][indicator.standard.learning_strand.name][indicator.standard].append(indicator)

        unique_topics_in_plan = {item.topic for unit in plan.learning_units for item in unit.assessment_items if item.topic}
        all_unique_topics.update(unique_topics_in_plan)
        for topic in unique_topics_in_plan:
            if topic.template:
                if topic.parent:
                    topics_by_group[group_name][topic.template.name][topic.parent].append(topic)
                elif topic not in topics_by_group[group_name][topic.template.name]:
                    topics_by_group[group_name][topic.template.name][topic] = []
    
    # Create the "All Overview" tab data
    indicators_overview = defaultdict(lambda: defaultdict(list))
    for indicator in sorted(list(all_unique_indicators), key=lambda x: x.code):
        if indicator.standard and indicator.standard.learning_strand:
            indicators_overview[indicator.standard.learning_strand.name][indicator.standard].append(indicator)
    
    topics_overview = defaultdict(lambda: defaultdict(list))
    for topic in sorted(list(all_unique_topics), key=lambda x: (x.template.id, x.parent_id or 0, x.id)):
        if topic.template:
            if topic.parent: topics_overview[topic.template.name][topic.parent].append(topic)
            elif topic not in topics_overview[topic.template.name]: topics_overview[topic.template.name][topic] = []

    # Combine for final template variable
    final_indicators_data = {"ภาพรวมทั้งหมด": indicators_overview, **indicators_by_group}
    final_topics_data = {"ภาพรวมทั้งหมด": topics_overview, **topics_by_group}


    # --- 3. Filter and process the Checklist plans ---
    if selected_group_id:
        plans_for_checklist = [p for p in all_plans_in_semester if p.subject.subject_group_id == selected_group_id]
    else:
        plans_for_checklist = all_plans_in_semester
    
    # Apply status filter and sort for checklist
    relevant_statuses = ['เสนอฝ่ายวิชาการ', 'รอการอนุมัติจากผู้อำวยการ', 'อนุมัติใช้งาน', 'ต้องการการแก้ไข']
    plans_for_checklist = [p for p in plans_for_checklist if p.status in relevant_statuses]
    plans_for_checklist.sort(key=lambda p: (
        relevant_statuses.index(p.status) if p.status in relevant_statuses else 99,
        -p.id
    ))
    
    for plan in plans_for_checklist:
        report = {'components_status': {}}
        all_units = plan.learning_units
        
        # Correct score calculation
        formative_total = sum(item.max_score for unit in all_units for item in unit.graded_items if item.max_score)
        midterm_total = sum(unit.midterm_score for unit in all_units if unit.midterm_score)
        final_total = sum(unit.final_score for unit in all_units if unit.final_score)
        
        score_during_semester = formative_total + midterm_total
        score_final = final_total
        
        report['formative_score'] = {'value': score_during_semester, 'status': score_during_semester > 0}
        report['final_score'] = {'value': score_final, 'status': score_final > 0}
        
        # Period calculation
        total_hours = sum(unit.hours for unit in all_units if unit.hours)
        expected_total_periods = (plan.subject.credit or 0) * 40
        report['total_periods'] = {'value': total_hours, 'status': total_hours >= expected_total_periods}

        # Component checks
        report['components_status']['indicators'] = any(unit.indicators for unit in all_units)
        report['components_status']['core_concepts'] = any(unit.core_concepts for unit in all_units)
        report['components_status']['learning_objectives'] = any(unit.learning_objectives for unit in all_units)
        report['components_status']['learning_content'] = any(unit.learning_content for unit in all_units)
        report['components_status']['learning_activities'] = any(unit.learning_activities for unit in all_units)
        report['components_status']['media_sources'] = any(unit.media_sources for unit in all_units)
        report['components_status']['sub_units'] = any(unit.sub_units for unit in all_units)
        report['components_status']['assessment_items'] = any(unit.assessment_items for unit in all_units)
        
        plan.completeness_report = report

    # --- 4. School-wide Stats and Workloads ---
    plan_stats = {status: len([p for p in all_plans_in_semester if p.status == status]) for status in set(p.status for p in all_plans_in_semester)}
    all_teachers = User.query.filter(User.roles.any(name='Teacher')).all()
    teacher_count = len(all_teachers)

    grouped_workloads = defaultdict(list)
    for teacher in all_teachers:
        courses_taught = Course.query.filter(
            Course.teachers.any(id=teacher.id), 
            Course.semester_id == current_semester.id
        ).options(joinedload(Course.subject)).all()

        if not courses_taught:
            continue # Skip teachers with no assigned courses in the current semester

        unique_subject_ids, total_credits, total_periods_per_week = set(), 0, 0
        for course in courses_taught:
            total_periods_per_week += (course.subject.credit or 0) * 2
            if course.subject.id not in unique_subject_ids:
                total_credits += (course.subject.credit or 0)
                unique_subject_ids.add(course.subject.id)
        
        workload_data = {
            'name': teacher.full_name, 
            'credits': total_credits, 
            'periods': total_periods_per_week
        }
        
        teacher_groups = [group.name for group in teacher.member_of_groups]
        if not teacher_groups:
            grouped_workloads['ไม่มีกลุ่มสาระฯ'].append(workload_data)
        else:
            for group_name in teacher_groups:
                grouped_workloads[group_name].append(workload_data)

    # --- 5. [เพิ่มใหม่] คำนวณความคืบหน้าการส่งแผนฯ แยกตามระดับชั้น ---
    all_grade_levels = GradeLevel.query.all()
    m_ton_grade_ids = {gl.id for gl in all_grade_levels if gl.level_group == 'm-ton'}
    m_plai_grade_ids = {gl.id for gl in all_grade_levels if gl.level_group == 'm-plai'}

    # 2.1 ดึง Course ทั้งหมดที่ส่งเกรดแล้ว และ Course ทั้งหมดในเทอม (Single Source of Truth)
    all_courses_in_semester = Course.query.filter_by(semester_id=current_semester.id).options(
        joinedload(Course.subject).joinedload(Subject.subject_group),
        joinedload(Course.classroom).joinedload(Classroom.grade_level)
    ).all()

    submitted_courses = [c for c in all_courses_in_semester if c.grade_submission_status in ['เสนอฝ่ายวิชาการ', 'อนุมัติใช้งาน', 'รอตรวจสอบ', 'รอการอนุมัติจากผู้อำนวยการ']]

    # 2.2 [แก้ไข] คำนวณ Progress Bar ม.ต้น/ม.ปลาย จากการส่งเกรด
    all_grade_levels = GradeLevel.query.all()
    m_ton_grade_ids = {gl.id for gl in all_grade_levels if gl.level_group == 'm-ton'}
    m_plai_grade_ids = {gl.id for gl in all_grade_levels if gl.level_group == 'm-plai'}

    total_m_ton, submitted_m_ton = 0, 0
    total_m_plai, submitted_m_plai = 0, 0

    for course in all_courses_in_semester:
        if not course.classroom: continue
        grade_level_id = course.classroom.grade_level_id
        is_submitted = course.grade_submission_status in ['เสนอฝ่ายวิชาการ', 'อนุมัติใช้งาน', 'รอตรวจสอบ', 'รอการอนุมัติจากผู้อำนวยการ']
        
        if grade_level_id in m_ton_grade_ids:
            total_m_ton += 1
            if is_submitted: submitted_m_ton += 1
        elif grade_level_id in m_plai_grade_ids:
            total_m_plai += 1
            if is_submitted: submitted_m_plai += 1

    m_ton_progress = {'total': total_m_ton, 'submitted': submitted_m_ton, 'percentage': (submitted_m_ton / total_m_ton * 100) if total_m_ton > 0 else 0}
    m_plai_progress = {'total': total_m_plai, 'submitted': submitted_m_plai, 'percentage': (submitted_m_plai / total_m_plai * 100) if total_m_plai > 0 else 0}

    # 2.3 จัดกลุ่มข้อมูลเกรดสำหรับตารางทั้ง 2 รูปแบบ
    grades_by_group = defaultdict(list)
    grades_by_grade_level = defaultdict(list)
    all_student_grades_data = []

    for course in submitted_courses:
        calculated_data, _ = calculate_final_grades_for_course(course)
        all_student_grades_data.extend(calculated_data)
        grades_by_group[course.subject.subject_group].extend(calculated_data)
        grades_by_grade_level[course.classroom.grade_level].extend(calculated_data)

    # 2.4 คำนวณสถิติสำหรับแต่ละกลุ่ม/ระดับชั้น
    group_summary_stats = []
    for group in sorted(grades_by_group.keys(), key=lambda g: g.name):
        if stats := calculate_grade_statistics(grades_by_group[group]):
            group_summary_stats.append({'group': group, 'stats': stats})

    grade_level_summary_stats = []
    for gl in sorted(grades_by_grade_level.keys(), key=lambda g: g.id):
        if stats := calculate_grade_statistics(grades_by_grade_level[gl]):
            grade_level_summary_stats.append({'grade_level': gl, 'stats': stats})

    overall_stats = calculate_grade_statistics(all_student_grades_data)
    chart_data = {'labels': ['4', '3.5', '3', '2.5', '2', '1.5', '1', '0', 'ร', 'มส'], 'data': [overall_stats['grade_distribution'].get(l, 0) for l in ['4', '3.5', '3', '2.5', '2', '1.5', '1', '0', 'ร', 'มส']]} if overall_stats else None

    return render_template(
        'academic/dashboard.html',
        title='ฝ่ายวิชาการ',
        plans_for_checklist=plans_for_checklist,
        grouped_workloads=grouped_workloads,
        stats=plan_stats,
        teacher_count=teacher_count,
        all_subject_groups=all_subject_groups,
        selected_group_id=selected_group_id,
        used_indicators_by_group=final_indicators_data,
        used_assessment_topics_by_group=final_topics_data,
        overall_stats=overall_stats,
        group_summary_stats=group_summary_stats,
        grade_level_summary_stats=grade_level_summary_stats,
        chart_data=chart_data,
        m_ton_progress=m_ton_progress,
        m_plai_progress=m_plai_progress,        
        form=form,
        grades_pending_review=grades_pending_review        
    )

@bp.route('/plan/<int:plan_id>/approve', methods=['POST'])
@login_required
def approve_plan(plan_id): # Maybe rename to approve_plan_academic?
    if not current_user.has_role('Academic'): abort(403)
    plan = LessonPlan.query.get_or_404(plan_id)
    original_status = plan.status
    new_status = 'อนุมัติใช้งาน' # Final approved status

    # Check if status is appropriate ('เสนอฝ่ายวิชาการ' or maybe 'รอการอนุมัติจากผู้อำนวยการ' if director involved)
    # if original_status not in ['เสนอฝ่ายวิชาการ', 'รอการอนุมัติจากผู้อำนวยการ']:
    #     flash(f'แผนไม่อยู่ในสถานะ "{original_status}" ไม่สามารถอนุมัติได้', 'warning')
    #     return redirect(url_for('academic.review_plan', plan_id=plan_id))

    try:
        plan.status = new_status
        # --- Log Action ---
        log_action("Approve Lesson Plan (Academic/Final)", model=LessonPlan, record_id=plan.id, old_value=original_status, new_value=new_status)
        db.session.commit()
        flash(f'แผนการสอนสำหรับวิชา "{plan.subject.name}" ได้รับการอนุมัติใช้งานแล้ว', 'success')
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Error approving plan {plan_id} (Academic): {e}", exc_info=True)
        # --- Log Failure ---
        log_action(f"Approve Lesson Plan Failed (Academic): {type(e).__name__}", model=LessonPlan, record_id=plan.id, old_value=original_status, new_value=new_status)
        try: db.session.commit()
        except: db.session.rollback()
        flash(f'เกิดข้อผิดพลาดในการอนุมัติแผน: {e}', 'danger')

    return redirect(url_for('academic.dashboard'))

@bp.route('/plan/<int:plan_id>/return', methods=['POST']) # Returns plan to Teacher
@login_required
def return_plan(plan_id):
    if not current_user.has_role('Academic'): abort(403)
    plan = LessonPlan.query.get_or_404(plan_id)
    revision_notes = request.form.get('revision_notes', 'ส่งกลับเพื่อแก้ไขจากฝ่ายวิชาการ')
    original_status = plan.status
    new_status = 'ต้องการการแก้ไข'

    try:
        plan.status = new_status
        plan.revision_notes = revision_notes
        # --- Log Action ---
        log_action(
            "Return Lesson Plan to Teacher (Academic)", model=LessonPlan, record_id=plan.id,
            old_value=original_status, new_value={'status': new_status, 'notes': revision_notes}
        )
        db.session.commit()
        flash(f'แผนการสอนสำหรับวิชา "{plan.subject.name}" ถูกส่งกลับไปยังครูผู้สอนเพื่อแก้ไข', 'warning')
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Error returning plan {plan_id} (Academic): {e}", exc_info=True)
        # --- Log Failure ---
        log_action(f"Return Lesson Plan Failed (Academic): {type(e).__name__}", model=LessonPlan, record_id=plan.id, old_value=original_status, new_value={'status': new_status})
        try: db.session.commit()
        except: db.session.rollback()
        flash(f'เกิดข้อผิดพลาดในการส่งแผนกลับ: {e}', 'danger')

    return redirect(url_for('academic.dashboard'))

@bp.route('/plan/<int:plan_id>/submit-for-approval', methods=['POST'])
@login_required
def submit_for_approval(plan_id):
    if not current_user.has_role('Academic'):
        abort(403)
    
    plan = LessonPlan.query.get_or_404(plan_id)
    plan.status = 'รอการอนุมัติ' # สถานะใหม่สำหรับส่งให้ผู้บริหาร
    db.session.commit()
    flash(f'แผนการสอนสำหรับวิชา "{plan.subject.name}" ได้รับการเสนอเพื่อขออนุมัติแล้ว', 'success')
    return redirect(url_for('academic.dashboard'))

@bp.route('/plan/<int:plan_id>/return-for-revision', methods=['POST'])
@login_required
def return_for_revision(plan_id):
    if not current_user.has_role('Academic'):
        abort(403)
        
    plan = LessonPlan.query.get_or_404(plan_id)
    revision_notes = request.form.get('revision_notes', 'ส่งกลับจากฝ่ายวิชาการ')
    plan.status = 'ต้องการการแก้ไข' # ส่งกลับไปให้ครูแก้ไข
    plan.revision_notes = revision_notes
    db.session.commit()
    flash(f'แผนการสอนสำหรับวิชา "{plan.subject.name}" ถูกส่งกลับไปยังครูผู้สอนเพื่อแก้ไข', 'warning')
    return redirect(url_for('academic.dashboard'))

@bp.route('/plan/<int:plan_id>/review')
@login_required
def review_plan(plan_id):
    # Note: Add security check for academic role
    plan = LessonPlan.query.options(
        # Eager load ข้อมูลทั้งหมดที่จำเป็นสำหรับหน้า review_plan
        joinedload(LessonPlan.subject),
        joinedload(LessonPlan.academic_year),
        selectinload(LessonPlan.learning_units).selectinload(LearningUnit.indicators).joinedload(Indicator.standard).joinedload(Standard.learning_strand),
        selectinload(LessonPlan.learning_units).selectinload(LearningUnit.graded_items).joinedload(GradedItem.dimension),
        selectinload(LessonPlan.learning_units).selectinload(LearningUnit.assessment_items).joinedload(AssessmentItem.topic).joinedload(AssessmentTopic.template),
        selectinload(LessonPlan.learning_units).selectinload(LearningUnit.assessment_items).joinedload(AssessmentItem.topic).joinedload(AssessmentTopic.parent)
    ).get_or_404(plan_id)

    # --- START: Calculation Block (เหมือนกับของ Department) ---
    total_units = len(plan.learning_units)
    total_periods = sum(unit.hours for unit in plan.learning_units if unit.hours)
    total_indicators = sum(len(unit.indicators) for unit in plan.learning_units)
    
    formative_total = sum(item.max_score for unit in plan.learning_units for item in unit.graded_items if item.max_score)
    midterm_total = sum(unit.midterm_score for unit in plan.learning_units if unit.midterm_score)
    final_total = sum(unit.final_score for unit in plan.learning_units if unit.final_score)
    score_during_semester = formative_total + midterm_total
    score_final = final_total
    total_score = score_during_semester + score_final

    actual_ratio_str = "N/A"
    if total_score > 0:
        ratio_during = round((score_during_semester / total_score) * 100)
        ratio_final = 100 - ratio_during
        actual_ratio_str = f"{ratio_during}:{ratio_final}"

    # Dynamic button logic for Academic Affairs
    approve_button_text = "เสนอผู้อำนวยการเพื่อพิจารณา"
    approve_action_url = url_for('academic.submit_to_director', plan_id=plan.id)
    
    # You will need to pass all the same variables as the department's review_plan
    # For brevity, only new ones are shown here.
    return render_template('department/review_plan.html', # Reusing the same template
                           title=f"ตรวจสอบแผน: {plan.subject.name}",
                           plan=plan,
                           score_during_semester=score_during_semester,
                           score_final=score_final,
                           actual_ratio_str=actual_ratio_str,
                           total_units=total_units,
                           total_periods=total_periods,
                           total_indicators=total_indicators,
                           approve_button_text=approve_button_text,
                           approve_action_url=approve_action_url)

@bp.route('/plan/<int:plan_id>/submit-to-director', methods=['POST']) # Submits plan from Academic to Director
@login_required
def submit_to_director(plan_id):
    if not current_user.has_role('Academic'): abort(403)
    plan = LessonPlan.query.get_or_404(plan_id)
    original_status = plan.status
    new_status = 'รอการอนุมัติจากผู้อำนวยการ'

    # Check status? Should be 'เสนอฝ่ายวิชาการ'
    if original_status != 'เสนอฝ่ายวิชาการ':
         flash(f'แผนไม่อยู่ในสถานะ "{original_status}" ไม่สามารถเสนอผู้อำนวยการได้', 'warning')
         return redirect(url_for('academic.review_plan', plan_id=plan_id))

    try:
        plan.status = new_status
        # --- Log Action ---
        log_action(
            "Submit Lesson Plan to Director (Academic)", model=LessonPlan, record_id=plan.id,
            old_value=original_status, new_value=new_status
        )
        # TODO: Add notification for Director
        db.session.commit()
        flash('เสนอแผนการสอนให้ผู้อำนวยการเพื่อพิจารณาเรียบร้อยแล้ว', 'success')
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Error submitting plan {plan_id} to director (Academic): {e}", exc_info=True)
        # --- Log Failure ---
        log_action(f"Submit Plan to Director Failed (Academic): {type(e).__name__}", model=LessonPlan, record_id=plan.id, old_value=original_status, new_value=new_status)
        try: db.session.commit()
        except: db.session.rollback()
        flash(f'เกิดข้อผิดพลาดในการเสนอแผน: {e}', 'danger')

    return redirect(url_for('academic.dashboard'))

# Add this new route for final approval
@bp.route('/plan/<int:plan_id>/approve-final', methods=['POST'])
@login_required
# (Add security decorator for academic role)
def approve_final(plan_id):
    plan = LessonPlan.query.get_or_404(plan_id)
    plan.status = 'อนุมัติใช้งาน' # Using a more final status name
    db.session.commit()
    flash('อนุมัติแผนการสอนเรียบร้อยแล้ว', 'success')
    return redirect(url_for('academic.dashboard'))

@bp.route('/timetable/manage/<int:semester_id>')
@login_required
def manage_timetable(semester_id):
    semester = Semester.query.get_or_404(semester_id)
    
    all_classrooms = Classroom.query.filter_by(academic_year_id=semester.academic_year_id).order_by(Classroom.name).all()
    all_teachers = User.query.filter(User.roles.any(Role.name == 'Teacher')).order_by(User.first_name).all()
    all_rooms = Room.query.order_by(Room.name).all()

    # --- START: ส่วนที่แก้ไข ---
    all_courses = Course.query.filter_by(semester_id=semester_id).options(
        joinedload(Course.subject), 
        joinedload(Course.classroom),
        joinedload(Course.teachers), 
        joinedload(Course.room),
        joinedload(Course.lesson_plan).selectinload(LessonPlan.constraints) # ดึง Constraints มาด้วย
    ).all()
    
    courses_data = []
    for c in all_courses:
        constraints = {}
        manual_notes = None
        if c.lesson_plan:
            constraints = {const.constraint_type: const.value for const in c.lesson_plan.constraints}
            manual_notes = c.lesson_plan.manual_scheduling_notes
        
        courses_data.append({
            'id': c.id, 
            'subject_name': f"{c.subject.subject_code} - {c.subject.name}",
            'classroom_id': c.classroom_id, 
            'classroom_name': c.classroom.name,
            'teacher_ids': [t.id for t in c.teachers],
            'teachers_name': [t.full_name for t in c.teachers],
            'room_id': c.room_id, 
            'room_name': c.room.name if c.room else 'N/A',
            'periods_needed': int((c.subject.credit or 0) * 2),
            'constraints': constraints, # เพิ่มข้อมูลเงื่อนไข
            'manual_notes': manual_notes # <--- เพิ่มข้อมูลบันทึกส่วนตัว
        })
    # --- END: ส่วนที่แก้ไข ---

    all_entries = TimetableEntry.query.join(WeeklyScheduleSlot).filter(
        WeeklyScheduleSlot.semester_id == semester_id
    ).options(
        joinedload(TimetableEntry.course).selectinload(Course.subject),
        joinedload(TimetableEntry.course).selectinload(Course.classroom),
        joinedload(TimetableEntry.course).selectinload(Course.teachers),
        joinedload(TimetableEntry.course).selectinload(Course.room),
        joinedload(TimetableEntry.slot)
    ).all()

    all_slots = WeeklyScheduleSlot.query.filter_by(semester_id=semester_id).all()
    
    entries_data = [{
        'id': e.id,
        'day': e.slot.day_of_week, 
        'period': e.slot.period_number,
        'course': next((c for c in courses_data if c['id'] == e.course_id), None)
    } for e in all_entries]

    slots_data = [
        {'id': s.id, 'day': s.day_of_week, 'period': s.period_number, 'is_teaching': s.is_teaching_period, 
         'activity': s.activity_name, 'grade_level_id': s.grade_level_id} 
        for s in all_slots
    ]

    form = FlaskForm()

    return render_template(
        'academic/manage_timetable.html',
        title='จัดตารางสอน',
        semester=semester,
        all_classrooms_json=json.dumps([{'id': c.id, 'name': c.name, 'grade_level_id': c.grade_level_id} for c in all_classrooms]),
        all_teachers_json=json.dumps([{'id': t.id, 'name': t.full_name} for t in all_teachers]),
        all_rooms_json=json.dumps([{'id': r.id, 'name': r.name} for r in all_rooms]),
        all_courses_json=json.dumps(courses_data),
        all_entries_json=json.dumps(entries_data),
        all_slots_json=json.dumps(slots_data),
        form=form
    )

@bp.route('/timetable/my-schedule')
@login_required
def teacher_timetable():
    if not (current_user.has_role('Teacher') or current_user.has_role('Academic')):
        abort(403)

    semester = Semester.query.filter_by(is_current=True).first_or_404()

    # 1. Fetch all timetable entries for the current semester with necessary details
    all_entries = TimetableEntry.query.join(WeeklyScheduleSlot).filter(
        WeeklyScheduleSlot.semester_id == semester.id
    ).options(
        joinedload(TimetableEntry.slot),
        joinedload(TimetableEntry.course).selectinload(Course.subject),
        joinedload(TimetableEntry.course).selectinload(Course.classroom),
        joinedload(TimetableEntry.course).selectinload(Course.teachers),
        joinedload(TimetableEntry.course).selectinload(Course.room)
    ).all()

    # 2. Filter entries for the current user
    my_entries = [entry for entry in all_entries if current_user in entry.course.teachers]

    # 3. Structure data for the grid
    schedule_grid = defaultdict(lambda: None)
    for entry in my_entries:
        key = f"{entry.slot.day_of_week}-{entry.slot.period_number}"
        # --- MODIFIED SECTION ---
        schedule_grid[key] = {
            'entry_id': entry.id, # ADD THIS LINE
            'subject_name': entry.course.subject.subject_code,
            'classroom_name': entry.course.classroom.name,
            'room_name': entry.course.room.name if entry.course.room else 'N/A'
        }

    # 4. Get all possible time slots for rendering the table structure
    time_slots = TimeSlot.query.filter_by(semester_id=semester.id).order_by(TimeSlot.period_number).all()

    return render_template(
        'academic/teacher_timetable.html',
        title='ตารางสอนของฉัน',
        semester=semester,
        schedule_grid=schedule_grid,
        time_slots=time_slots
    )

@bp.route('/api/timetable/auto-schedule', methods=['POST'])
@login_required
def auto_schedule_timetable():
    data = request.get_json()
    semester_id = data.get('semester_id')
    if not semester_id:
        return jsonify({'status': 'error', 'message': 'Semester ID is required'}), 400

    # --- PHASE 1: ระบุกลุ่มเป้าหมายทั้งหมด และแยกกลุ่มที่จัดแล้วกับยังไม่จัด ---
    target_courses_query = Course.query.filter_by(semester_id=semester_id)
    classroom_id = data.get('classroom_id')
    teacher_id = data.get('teacher_id')
    room_id = data.get('room_id')

    if classroom_id:
        target_courses_query = target_courses_query.filter_by(classroom_id=classroom_id)
    elif teacher_id:
        target_courses_query = target_courses_query.filter(Course.teachers.any(User.id == teacher_id))
    elif room_id:
        target_courses_query = target_courses_query.filter_by(room_id=room_id)
    else:
        return jsonify({'status': 'error', 'message': 'A target is required.'}), 400

    all_target_courses = target_courses_query.options(
        joinedload(Course.subject),
        joinedload(Course.classroom).joinedload(Classroom.grade_level),
        joinedload(Course.teachers),
        joinedload(Course.room),
        joinedload(Course.lesson_plan).selectinload(LessonPlan.constraints)
    ).all()

    if not all_target_courses:
        return jsonify({'status': 'success', 'message': 'No courses found.', 'unscheduled_courses': []})

    # --- PHASE 2: สร้าง Conflict Map จากทุกวิชาที่ถูกจัดไปแล้ว (ทั้งในและนอกกลุ่มเป้าหมาย) ---
    all_entries_in_semester = TimetableEntry.query.join(WeeklyScheduleSlot).filter(
        WeeklyScheduleSlot.semester_id == semester_id
    ).options(
        joinedload(TimetableEntry.course).selectinload(Course.teachers),
        joinedload(TimetableEntry.course).selectinload(Course.room),
        joinedload(TimetableEntry.course).selectinload(Course.classroom),
        joinedload(TimetableEntry.slot)
    ).all()

    already_scheduled_periods = defaultdict(int)
    for entry in all_entries_in_semester:
        already_scheduled_periods[entry.course_id] += 1
        
    courses_to_process = [
        c for c in all_target_courses 
        if already_scheduled_periods.get(c.id, 0) < int((c.subject.credit or 0) * 2)
    ]
    
    if not courses_to_process:
        return jsonify({'status': 'success', 'message': 'All target courses are already fully scheduled.', 'unscheduled_courses': []})

    teacher_schedule, classroom_schedule, room_schedule = defaultdict(set), defaultdict(set), defaultdict(set)
    occupied_slot_ids = {entry.weekly_schedule_slot_id for entry in all_entries_in_semester}
    for entry in all_entries_in_semester:
        day, period, course = entry.slot.day_of_week, entry.slot.period_number, entry.course
        if course:
            classroom_schedule[course.classroom_id].add((day, period))
            for teacher in course.teachers:
                teacher_schedule[teacher.id].add((day, period))
            if course.room_id:
                room_schedule[course.room_id].add((day, period))

    # --- PHASE 3: CLEAR OLD SCHEDULE FOR TARGETS ---

    # --- PHASE 4: REVISED SCHEDULING ALGORITHM ---
    all_slots = WeeklyScheduleSlot.query.filter_by(semester_id=semester_id).all()
    
    # สร้าง "พจนานุกรม" ของ Slot แยกตามระดับชั้น เพื่อให้ดึงใช้ได้ง่าย
    slots_by_grade = defaultdict(list)
    for s in all_slots:
        slots_by_grade[s.grade_level_id].append(s)

    # จัดลำดับความสำคัญใหม่: 1. วิชาที่ต้องการคาบคู่มาก่อน, 2. วิชาที่มีหน่วยกิตเยอะ (คาบเยอะ) มาก่อน
    courses_to_process.sort(key=lambda c: (
        -1 if c.lesson_plan and any(
            const.constraint_type == 'period_arrangement' and const.value == 'consecutive'
            for const in c.lesson_plan.constraints
        ) else 0,
        -int(c.subject.credit or 0)
    ))

    max_passes, pass_count, progress_made = 10, 0, True
    while progress_made and pass_count < max_passes and courses_to_process:
        pass_count, progress_made, remaining_courses_this_pass = pass_count + 1, False, []
        for course in courses_to_process:
            remaining_periods = int((course.subject.credit or 0) * 2) - already_scheduled_periods.get(course.id, 0)
            if remaining_periods <= 0: continue
            course_grade_level_id = course.classroom.grade_level_id
            relevant_slots = slots_by_grade.get(course_grade_level_id, [])
            teacher_ids, constraints = {t.id for t in course.teachers}, {c.constraint_type: c.value for c in course.lesson_plan.constraints} if course.lesson_plan else {}
            arrangement, time_preference = constraints.get('period_arrangement', 'separate'), constraints.get('time_preference', 'any')
            possible_slots = []
            for slot in relevant_slots:
                if slot.id in occupied_slot_ids or not slot.is_teaching_period: continue
                day, period = slot.day_of_week, slot.period_number
                if any((day, period) in teacher_schedule[tid] for tid in teacher_ids): continue
                if (day, period) in classroom_schedule[course.classroom_id] and course.classroom_id is not None: continue
                if course.room_id and (day, period) in room_schedule[course.room_id]: continue
                if pass_count <= 2 and ((time_preference == 'morning' and slot.period_number > 5) or (time_preference == 'afternoon' and slot.period_number < 6)): continue
                possible_slots.append(slot)
            
            placements_to_make = []
            if arrangement == 'consecutive' and remaining_periods > 1:
                num_pairs_needed = remaining_periods // 2
                found_pairs, used_in_this_search = [], set()
                slots_by_day = defaultdict(list)
                for s in possible_slots: slots_by_day[s.day_of_week].append(s)
                day_keys = list(slots_by_day.keys())
                random.shuffle(day_keys)
                for day in day_keys:
                    if len(found_pairs) >= num_pairs_needed: break
                    s_slots = sorted(slots_by_day[day], key=lambda x: x.period_number)
                    i = 0
                    while i < len(s_slots) - 1:
                        if len(found_pairs) >= num_pairs_needed: break
                        slot1, slot2 = s_slots[i], s_slots[i+1]
                        if slot1.id not in used_in_this_search and slot2.id not in used_in_this_search and slot2.period_number == slot1.period_number + 1:
                            found_pairs.append([slot1, slot2]); used_in_this_search.add(slot1.id); used_in_this_search.add(slot2.id); i += 2
                        else: i += 1
                if len(found_pairs) >= num_pairs_needed:
                    placements_to_make.extend(slot for pair in found_pairs for slot in pair)
            else:
                if len(possible_slots) >= remaining_periods:
                    placements_to_make.extend(random.sample(possible_slots, remaining_periods))

            if len(placements_to_make) >= remaining_periods:
                progress_made = True
                for slot in placements_to_make:
                    day, period = slot.day_of_week, slot.period_number
                    occupied_slot_ids.add(slot.id)
                    classroom_schedule[course.classroom_id].add((day, period))
                    for t in course.teachers: teacher_schedule[t.id].add((day, period))
                    if course.room_id: room_schedule[course.room_id].add((day, period))
                    db.session.add(TimetableEntry(course_id=course.id, weekly_schedule_slot_id=slot.id))
                already_scheduled_periods[course.id] += len(placements_to_make)
            else:
                remaining_courses_this_pass.append(course)
        courses_to_process = remaining_courses_this_pass

    # --- PHASE 5: ANALYZE UNSCHEDULED COURSES & FINALIZE (REVISED LOGIC) ---
    unscheduled_courses_report = []
    if courses_to_process:
        for course in courses_to_process:
            required = int((course.subject.credit or 0) * 2) - already_scheduled_periods.get(course.id, 0)
            course_grade_level_id = course.classroom.grade_level_id
            
            relevant_slots_for_analysis = slots_by_grade.get(course_grade_level_id, [])
            truly_available_for_grade = [s for s in relevant_slots_for_analysis if s.is_teaching_period and s.id not in occupied_slot_ids]
            available_slot_count = len(truly_available_for_grade)
            
            reasons = defaultdict(int)
            teacher_ids = {t.id for t in course.teachers}
            constraints = {c.constraint_type: c.value for c in course.lesson_plan.constraints} if course.lesson_plan else {}
            time_preference = constraints.get('time_preference', 'any')

            for slot in truly_available_for_grade:
                day, period = slot.day_of_week, slot.period_number
                if time_preference == 'morning' and slot.period_number > 5: reasons['ติดเงื่อนไข "ต้องสอนช่วงเช้า"'] += 1; continue
                if time_preference == 'afternoon' and slot.period_number < 6: reasons['ติดเงื่อนไข "ต้องสอนช่วงบ่าย"'] += 1; continue
                if any((day, period) in teacher_schedule[tid] for tid in teacher_ids): reasons['ครูผู้สอนไม่ว่าง'] += 1; continue
                if (day, period) in classroom_schedule[course.classroom_id]: reasons['ห้องเรียนไม่ว่าง'] += 1; continue
                if course.room_id and (day, period) in room_schedule[course.room_id]: reasons[f'ห้อง {course.room.name} ไม่ว่าง'] += 1; continue
                    
        summary = f"มีคาบว่างสำหรับระดับชั้นนี้ {available_slot_count} คาบ (ต้องการ {required} คาบ)"
        if reasons:
            top_reason_text = max(reasons, key=reasons.get)
            summary += f"สาเหตุหลัก: {top_reason_text} ({reasons[top_reason_text]} คาบ)"
        elif available_slot_count < required: summary += "สาเหตุ: มีคาบว่างไม่พอ"
        else: summary += "สาเหตุ: ไม่สามารถหาคาบคู่ได้"
        
        unscheduled_courses_report.append({'subject_name': f"{course.subject.subject_code} ({course.classroom.name})", 'reason': summary})

    db.session.commit()
    return jsonify({'status': 'success', 'message': 'AI scheduling complete.', 'unscheduled_courses': unscheduled_courses_report})

@bp.route('/api/timetable/entry', methods=['POST'])
@login_required
def save_timetable_entry():
    data = request.get_json()
    if not data:
        return jsonify({'status': 'error', 'message': 'Invalid request'}), 400

    # (ส่วน CSRF Validation สามารถคงไว้ได้)
    try:
        validate_csrf(request.headers.get('X-CSRFToken'))
    except CSRFError as e:
        return jsonify({'status': 'error', 'message': str(e)}), 400
        
    course_id = data.get('course_id')
    day = data.get('day')
    period = data.get('period')
    semester_id = data.get('semester_id')

    # --- VALIDATION ENGINE (ส่วนนี้ถูกต้องแล้ว) ---
    target_course = Course.query.get(course_id)
    if not target_course:
        return jsonify({'status': 'error', 'message': 'ไม่พบรายวิชาที่ระบุ'}), 404

    slot = WeeklyScheduleSlot.query.filter_by(semester_id=semester_id, day_of_week=day, period_number=period).first()
    if not slot:
        return jsonify({'status': 'error', 'message': 'ไม่พบช่องตารางสอน'}), 404
        
    existing_entry_in_slot = TimetableEntry.query.filter_by(weekly_schedule_slot_id=slot.id).first()
    
    classroom_conflict = TimetableEntry.query.join(WeeklyScheduleSlot).join(Course).filter(
        WeeklyScheduleSlot.semester_id == semester_id,
        WeeklyScheduleSlot.day_of_week == day,
        WeeklyScheduleSlot.period_number == period,
        Course.classroom_id == target_course.classroom_id,
        TimetableEntry.id != (existing_entry_in_slot.id if existing_entry_in_slot else 0)
    ).first()
    if classroom_conflict:
        return jsonify({'status': 'error', 'message': f'ห้องเรียน {target_course.classroom.name} มีเรียนวิชาอื่นในเวลานี้แล้ว'}), 400

    teacher_ids = {t.id for t in target_course.teachers}
    teacher_conflict = TimetableEntry.query.join(WeeklyScheduleSlot).join(Course).join(Course.teachers).filter(
        WeeklyScheduleSlot.semester_id == semester_id,
        WeeklyScheduleSlot.day_of_week == day,
        WeeklyScheduleSlot.period_number == period,
        User.id.in_(teacher_ids),
        TimetableEntry.id != (existing_entry_in_slot.id if existing_entry_in_slot else 0)
    ).first()
    if teacher_conflict:
        conflicting_teacher = User.query.get(list(teacher_ids.intersection(t.id for t in teacher_conflict.course.teachers))[0])
        return jsonify({'status': 'error', 'message': f'ครู {conflicting_teacher.full_name} มีสอนคาบอื่นในเวลานี้แล้ว'}), 400
        
    if target_course.room_id:
        room_conflict = TimetableEntry.query.join(WeeklyScheduleSlot).join(Course).filter(
            WeeklyScheduleSlot.semester_id == semester_id,
            WeeklyScheduleSlot.day_of_week == day,
            WeeklyScheduleSlot.period_number == period,
            Course.room_id == target_course.room_id,
            TimetableEntry.id != (existing_entry_in_slot.id if existing_entry_in_slot else 0)
        ).first()
        if room_conflict:
            return jsonify({'status': 'error', 'message': f'ห้อง {target_course.room.name} ถูกใช้งานในเวลานี้แล้ว'}), 400

    # --- START: ส่วนที่แก้ไข ---
    # ใช้ตัวแปรชื่อ 'entry' เพียงตัวเดียว
    entry = TimetableEntry.query.filter_by(weekly_schedule_slot_id=slot.id).first()
    
    if entry:
        # ถ้ามีรายการเก่าในช่องนี้อยู่แล้ว ให้อัปเดต course_id
        entry.course_id = course_id
    else:
        # ถ้าช่องนี้ว่าง ให้สร้างรายการใหม่และเก็บลงในตัวแปร 'entry'
        entry = TimetableEntry(course_id=course_id, weekly_schedule_slot_id=slot.id)
        db.session.add(entry)
    # --- END: ส่วนที่แก้ไข ---
    
    try:
        db.session.commit()
        # ตอนนี้ 'entry' จะมีข้อมูลเสมอ ไม่ว่าจะมาจากเงื่อนไข if หรือ else
        course = Course.query.get(course_id)
        teachers = [t.full_name for t in course.teachers]
        return jsonify({
            'status': 'success',
            'entry_id': entry.id, # <--- บรรทัดนี้จะทำงานได้ถูกต้องแล้ว
            'course': {
                'id': course.id,
                'subject_name': f"{course.subject.subject_code} - {course.subject.name}",
                'classroom_id': course.classroom.id,
                'classroom_name': course.classroom.name,
                'teacher_ids': [t.id for t in course.teachers],
                'teachers_name': teachers,
                'room_id': course.room_id,
                'room_name': course.room.name if course.room else 'N/A',
                'periods_needed': int((course.subject.credit or 0) * 2),
                'constraints': {c.constraint_type: c.value for c in course.lesson_plan.constraints} if course.lesson_plan else {}
            }
        })
    except IntegrityError as e:
        db.session.rollback()
        return jsonify({'status': 'error', 'message': 'เกิดข้อผิดพลาดในการบันทึกข้อมูลซ้ำซ้อน'}), 500
    
# [NEW] API endpoint to forcefully delete a timetable entry by its ID.
@bp.route('/api/timetable/entry/<int:entry_id>', methods=['DELETE'])
@login_required
def delete_timetable_entry(entry_id):
    """
    Deletes a single timetable entry. Used for manual adjustments on the frontend.
    """
    entry = TimetableEntry.query.get_or_404(entry_id)
    
    try:
        db.session.delete(entry)
        db.session.commit()
        return jsonify({'status': 'success', 'message': 'Entry deleted successfully.'})
    except Exception as e:
        db.session.rollback()
        return jsonify({'status': 'error', 'message': f'Failed to delete entry: {str(e)}'}), 500

# [NEW] API endpoint to move a timetable entry to a new slot.
@bp.route('/api/timetable/entry/<int:entry_id>/move', methods=['POST'])
@login_required
def move_timetable_entry(entry_id):
    """
    Moves a timetable entry to a new slot. Used for drag-and-drop functionality.
    Performs validation before moving.
    """
    entry = TimetableEntry.query.get_or_404(entry_id)
    data = request.get_json()
    new_slot_id = data.get('new_slot_id')

    if not new_slot_id:
        return jsonify({'status': 'error', 'message': 'New slot ID is required.'}), 400

    new_slot = WeeklyScheduleSlot.query.get(new_slot_id)
    if not new_slot:
        return jsonify({'status': 'error', 'message': 'New slot not found.'}), 404

    # --- Server-side Validation ---
    # 1. Check if the new slot is a teaching period
    if not new_slot.is_teaching_period:
        return jsonify({'status': 'error', 'message': f'Cannot move to an activity slot: {new_slot.activity_name}.'}), 400

    # 2. Check if the new slot is already occupied by another course
    existing_entry = TimetableEntry.query.filter_by(weekly_schedule_slot_id=new_slot_id).first()
    if existing_entry:
        return jsonify({'status': 'error', 'message': 'Target slot is already occupied.'}), 409 # 409 Conflict

    # (You can add more checks here for teacher/classroom availability if needed)

    try:
        entry.weekly_schedule_slot_id = new_slot_id
        db.session.commit()
        return jsonify({'status': 'success', 'message': 'Entry moved successfully.'})
    except Exception as e:
        db.session.rollback()
        return jsonify({'status': 'error', 'message': f'Failed to move entry: {str(e)}'}), 500

@bp.route('/api/student/<int:student_id>/details')
@login_required
# @academic_required # decorator to check for 'Academic' role
def get_student_details_for_status(student_id):
    student = db.session.get(Student, student_id)
    if not student:
        return jsonify({'status': 'error', 'message': 'ไม่พบนักเรียน'}), 404
    return jsonify({
        'status': 'success',
        'student': {
            'id': student.id,
            'full_name': f"{student.first_name} {student.last_name}",
            'current_status': student.status
        }
    })

@bp.route('/api/student/<int:student_id>/update-status', methods=['POST'])
@login_required
# @academic_required
def update_student_status(student_id):
    student = db.session.get(Student, student_id)
    if not student:
        return jsonify({'status': 'error', 'message': 'ไม่พบนักเรียน'}), 404

    data = request.get_json()
    new_status = data.get('status')
    notes = data.get('notes', '')

    if not new_status:
        return jsonify({'status': 'error', 'message': 'กรุณาระบุสถานะใหม่'}), 400

    old_status = student.status
    student.status = new_status
    
    # Logic to notify relevant teachers
    teachers_to_notify = set()
    # Find all courses the student is in for the current semester
    current_semester = Semester.query.filter_by(is_current=True).first()
    if current_semester:
        enrollment = student.enrollments.filter(Enrollment.classroom.has(academic_year_id=current_semester.academic_year_id)).first()
        if enrollment:
            # Add advisor
            for advisor in enrollment.classroom.advisors:
                teachers_to_notify.add(advisor)
            # Add all subject teachers
            courses_in_classroom = Course.query.filter_by(classroom_id=enrollment.classroom_id, semester_id=current_semester.id).all()
            for course in courses_in_classroom:
                for teacher in course.teachers:
                    teachers_to_notify.add(teacher)
    
    title = "แจ้งเตือนการเปลี่ยนแปลงสถานะนักเรียน"
    message = f"สถานะของนักเรียน {student.first_name} {student.last_name} ได้เปลี่ยนจาก '{old_status}' เป็น '{new_status}'\nหมายเหตุ: {notes}"
    
    for user in teachers_to_notify:
        notification = Notification(user_id=user.id, title=title, message=message, notification_type='STUDENT_STATUS')
        db.session.add(notification)

    db.session.commit()
    return jsonify({'status': 'success', 'message': f'อัปเดตสถานะนักเรียนเป็น {new_status} เรียบร้อยแล้ว'})        

@bp.route('/grade-reports/dashboard')
@login_required
# @academic_required
def grade_dashboard():
    semester = Semester.query.filter_by(is_current=True).first_or_404()
    form = FlaskForm()
    
    # 1. ดึงข้อมูล Course ทั้งหมดที่ส่งเกรดแล้วในเทอมนี้ (Single Source of Truth)
    all_submitted_courses = Course.query.filter(
        Course.semester_id == semester.id,
        Course.grade_submission_status.in_(['รอตรวจสอบ', 'อนุมัติแล้ว'])
    ).options(
        joinedload(Course.subject).joinedload(Subject.subject_group),
        joinedload(Course.classroom).joinedload(Classroom.grade_level)
    ).all()

    # 2. ประมวลผลข้อมูลทั้งหมดเพื่อสร้างสถิติ
    all_student_grades_data = []
    progress_by_group = defaultdict(lambda: {'submitted': 0, 'total': 0})
    
    all_courses_in_semester = Course.query.filter_by(semester_id=semester.id).all()
    for c in all_courses_in_semester:
        group_id = c.subject.subject_group_id
        progress_by_group[group_id]['total'] += 1

    for course in all_submitted_courses:
        calculated_data, _ = calculate_final_grades_for_course(course)
        all_student_grades_data.extend(calculated_data)
        progress_by_group[course.subject.subject_group_id]['submitted'] += 1
        
    overall_stats = calculate_grade_statistics(all_student_grades_data)

    # 3. เตรียมข้อมูลสำหรับ Chart
    chart_data = None
    if overall_stats:
        labels = ['4', '3.5', '3', '2.5', '2', '1.5', '1', '0', 'ร', 'มส']
        data = [overall_stats['grade_distribution'].get(l, 0) for l in labels]
        chart_data = {'labels': labels, 'data': data}

    # 4. เตรียมข้อมูล Progress Bar แยกตามกลุ่มสาระ
    all_groups = SubjectGroup.query.all()
    group_progress_list = []
    for group in all_groups:
        progress = progress_by_group[group.id]
        total = progress['total']
        percentage = (progress['submitted'] / total * 100) if total > 0 else 0
        group_progress_list.append({
            'group': group,
            'submitted': progress['submitted'],
            'total': total,
            'percentage': percentage
        })

    return render_template('academic/grade_dashboard.html',
                           title='ภาพรวมผลการเรียน',
                           overall_stats=overall_stats,
                           chart_data=chart_data,
                           group_progress_list=group_progress_list,
                           form=form,
                           semester=semester)

@bp.route('/grade-reports/subject-group/<int:group_id>')
@login_required
# @academic_required
def subject_group_overview(group_id):
    group = SubjectGroup.query.get_or_404(group_id)
    semester = Semester.query.filter_by(is_current=True).first_or_404()

    # ดึงข้อมูลเฉพาะกลุ่มสาระฯ นี้
    submitted_courses = Course.query.join(Subject).filter(
        Course.semester_id == semester.id,
        Subject.subject_group_id == group_id,
        Course.grade_submission_status.in_(['รอตรวจสอบ', 'อนุมัติแล้ว'])
    ).all()

    all_student_grades_data = []
    for course in submitted_courses:
        calculated_data, _ = calculate_final_grades_for_course(course)
        all_student_grades_data.extend(calculated_data)
        
    overall_stats = calculate_grade_statistics(all_student_grades_data)
    
    chart_data = None
    if overall_stats:
        labels = ['4', '3.5', '3', '2.5', '2', '1.5', '1', '0', 'ร', 'มส']
        data = [overall_stats['grade_distribution'].get(l, 0) for l in labels]
        chart_data = {'labels': labels, 'data': data}

    # 1. เพื่อคำนวณ Progress (ส่งแล้ว/ทั้งหมด) เราจำเป็นต้องดึง Course "ทั้งหมด" ในกลุ่มสาระฯ นี้
    all_courses_in_group = Course.query.join(Subject).join(Classroom).filter(
        Course.semester_id == semester.id,
        Subject.subject_group_id == group_id
    ).options(
        joinedload(Course.classroom).joinedload(Classroom.grade_level)
    ).all()
    
    # 2. เตรียม ID ของระดับชั้น ม.ต้น และ ม.ปลาย
    all_grade_levels = GradeLevel.query.all()
    m_ton_grade_ids = {gl.id for gl in all_grade_levels if gl.level_group == 'm-ton'}
    m_plai_grade_ids = {gl.id for gl in all_grade_levels if gl.level_group == 'm-plai'}

    # 3. วนลูปเพื่อนับจำนวนทั้งหมด และจำนวนที่ส่งแล้ว
    total_m_ton = 0
    submitted_m_ton = 0
    total_m_plai = 0
    submitted_m_plai = 0

    for course in all_courses_in_group:
        grade_level_id = course.classroom.grade_level_id
        is_submitted = course.grade_submission_status in ['รอตรวจสอบ', 'อนุมัติแล้ว']

        if grade_level_id in m_ton_grade_ids:
            total_m_ton += 1
            if is_submitted:
                submitted_m_ton += 1
        elif grade_level_id in m_plai_grade_ids:
            total_m_plai += 1
            if is_submitted:
                submitted_m_plai += 1

    # 4. สร้าง Dictionary สำหรับส่งไปหน้าเว็บ
    m_ton_percentage = (submitted_m_ton / total_m_ton * 100) if total_m_ton > 0 else 0
    m_ton_progress = {'total': total_m_ton, 'submitted': submitted_m_ton, 'percentage': m_ton_percentage}

    m_plai_percentage = (submitted_m_plai / total_m_plai * 100) if total_m_plai > 0 else 0
    m_plai_progress = {'total': total_m_plai, 'submitted': submitted_m_plai, 'percentage': m_plai_percentage}


    return render_template('academic/subject_group_overview.html',
                           title=f"ภาพรวมกลุ่มสาระฯ {group.name}",
                           group=group,
                           overall_stats=overall_stats,
                           chart_data=chart_data)

@bp.route('/grade-reports/level-overview/<level_group>')
@login_required
#@academic_required
def level_overview(level_group):
    if level_group not in ['m-ton', 'm-plai']:
        abort(404)

    title = "ภาพรวมมัธยมศึกษาตอนต้น" if level_group == 'm-ton' else "ภาพรวมมัธยมศึกษาตอนปลาย"
    semester = Semester.query.filter_by(is_current=True).first_or_404()
    form = FlaskForm()

    # 1. Single Source of Truth & Setup
    grade_levels_in_group = GradeLevel.query.filter_by(level_group=level_group).order_by(GradeLevel.id).all()
    grade_level_ids = {gl.id for gl in grade_levels_in_group}
    grade_level_map = {gl.id: gl for gl in grade_levels_in_group}

    all_courses_in_level = Course.query.filter(
        Course.semester_id == semester.id,
        Course.classroom.has(Classroom.grade_level_id.in_(grade_level_ids))
    ).options(
        joinedload(Course.subject).joinedload(Subject.subject_group),
        joinedload(Course.classroom).joinedload(Classroom.grade_level)
    ).all()

    # 2. Filter data and perform calculations in a single pass
    submitted_courses = [c for c in all_courses_in_level if c.grade_submission_status in ['เสนอฝ่ายวิชาการ', 'อนุมัติใช้งาน', 'รอตรวจสอบ', 'รอการอนุมัติจากผู้อำนวยการ']]
    grades_pending_review = [c for c in submitted_courses if c.grade_submission_status == 'เสนอฝ่ายวิชาการ']
    
    all_student_grades_data = []
    grades_by_grade_level = defaultdict(list)
    grades_by_group = defaultdict(list)

    for course in submitted_courses:
        calculated_data, _ = calculate_final_grades_for_course(course)
        all_student_grades_data.extend(calculated_data)
        grades_by_grade_level[course.classroom.grade_level].extend(calculated_data)
        grades_by_group[course.subject.subject_group].extend(calculated_data)

    # 3. Calculate statistics for both tables
    overall_stats = calculate_grade_statistics(all_student_grades_data)

    grade_level_summary_stats = []
    for gl in sorted(grades_by_grade_level.keys(), key=lambda g: g.id):
        if stats := calculate_grade_statistics(grades_by_grade_level[gl]):
            grade_level_summary_stats.append({'grade_level': gl, 'stats': stats})

    group_summary_stats = []
    for group in sorted(grades_by_group.keys(), key=lambda g: g.name):
        if stats := calculate_grade_statistics(grades_by_group[group]):
            group_summary_stats.append({'group': group, 'stats': stats})

    # 4. Calculate data for Progress Cards
    progress_by_grade = defaultdict(lambda: {'total': 0, 'submitted': 0})
    for course in all_courses_in_level:
        progress_by_grade[course.classroom.grade_level_id]['total'] += 1
    for course in submitted_courses:
        progress_by_grade[course.classroom.grade_level_id]['submitted'] += 1

    progress_cards_data = []
    for gl in grade_levels_in_group:
        data = progress_by_grade[gl.id]
        progress_cards_data.append({
            'grade_level': gl,
            'total': data['total'],
            'submitted': data['submitted'],
            'percentage': (data['submitted'] / data['total'] * 100) if data['total'] > 0 else 0
        })
            
    # 5. Prepare data for Chart
    chart_data = None
    if overall_stats:
        labels = ['4', '3.5', '3', '2.5', '2', '1.5', '1', '0', 'ร', 'มส']
        data = [overall_stats['grade_distribution'].get(l, 0) for l in labels]
        chart_data = {'labels': labels, 'data': data}

    # 6. Render the template with ALL necessary data
    return render_template('academic/level_overview.html',
                           title=title,
                           level_group=level_group,
                           form=form,
                           overall_stats=overall_stats,
                           chart_data=chart_data,
                           grades_pending_review=grades_pending_review,
                           progress_cards_data=progress_cards_data,
                           grade_level_summary_stats=grade_level_summary_stats,
                           group_summary_stats=group_summary_stats,
                           semester=semester)

@bp.route('/grade-reports/submit-level-grades/<level_group>', methods=['POST'])
@login_required
#@academic_required
def submit_level_grades(level_group):
    semester = Semester.query.filter_by(is_current=True).first_or_404()
    grade_level_ids = {gl.id for gl in GradeLevel.query.filter_by(level_group=level_group).all()}

    courses_to_submit = Course.query.filter(
        Course.semester_id == semester.id,
        Course.grade_submission_status == 'เสนอฝ่ายวิชาการ',
        Course.classroom.has(Classroom.grade_level_id.in_(grade_level_ids))
    ).all()

    for course in courses_to_submit:
        course.grade_submission_status = 'รอการอนุมัติจากผู้อำนวยการ'
    
    db.session.commit()
    flash(f'ส่งผลการเรียนสำหรับสายชั้นนี้จำนวน {len(courses_to_submit)} รายการให้ผู้อำนวยการฯ เรียบร้อยแล้ว', 'success')
    return redirect(url_for('academic.level_overview', level_group=level_group))

@bp.route('/grade-reports/submit-all-to-director', methods=['POST'])
@login_required
#@academic_required
def submit_all_grades_to_director():
    """
    Handles the submission of all 'เสนอฝ่ายวิชาการ' grades to the director.
    Triggered from the main academic dashboard.
    """
    semester = Semester.query.filter_by(is_current=True).first_or_404()
    courses_to_submit = Course.query.filter_by(
        semester_id=semester.id,
        grade_submission_status='เสนอฝ่ายวิชาการ'
    ).all()

    for course in courses_to_submit:
        course.grade_submission_status = 'รอการอนุมัติจากผู้อำนวยการ'
        # Optional: Add logic here to create a notification for the director
    
    if courses_to_submit:
        db.session.commit()
        flash(f'ส่งผลการเรียนจำนวน {len(courses_to_submit)} รายการให้ผู้อำนวยการเพื่อพิจารณาเรียบร้อยแล้ว', 'success')
    else:
        flash('ไม่พบผลการเรียนที่รอการตรวจสอบเพื่อส่งต่อ', 'info')
        
    return redirect(url_for('academic.dashboard'))

@bp.route('/grade-reports/grade-level-detail/<int:grade_level_id>')
@login_required
#@academic_required
def grade_level_detail(grade_level_id):
    grade_level = GradeLevel.query.get_or_404(grade_level_id)
    semester = Semester.query.filter_by(is_current=True).first_or_404()
    form = FlaskForm()
    
    # 1. ดึงข้อมูล Course ที่ส่งแล้วทั้งหมดในระดับชั้นนี้
    all_courses_in_level = Course.query.filter(
        Course.semester_id == semester.id,
        Course.classroom.has(Classroom.grade_level_id == grade_level_id)
    ).options(
        joinedload(Course.subject),
        joinedload(Course.teachers)
    ).all()

    submitted_courses = [c for c in all_courses_in_level if c.grade_submission_status in ['เสนอฝ่ายวิชาการ', 'อนุมัติใช้งาน', 'รอตรวจสอบ', 'รอการอนุมัติจากผู้อำนวยการ']]
    grades_pending_review = [c for c in submitted_courses if c.grade_submission_status == 'เสนอฝ่ายวิชาการ']
    
    # 2. จัดกลุ่มข้อมูลตามรายวิชา
    all_student_grades_data = []
    grades_by_subject = defaultdict(list)
    teachers_by_subject = defaultdict(set)
    for course in submitted_courses:
        calculated_data, _ = calculate_final_grades_for_course(course)
        all_student_grades_data.extend(calculated_data)
        grades_by_subject[course.subject].extend(calculated_data)
        for teacher in course.teachers:
            teachers_by_subject[course.subject].add(teacher.full_name)

    # 3. คำนวณสถิติ
    overall_stats = calculate_grade_statistics(all_student_grades_data)
    subject_summary_stats = []
    for subject in sorted(grades_by_subject.keys(), key=lambda s: s.subject_code):
        if stats := calculate_grade_statistics(grades_by_subject[subject]):
            subject_summary_stats.append({
                'subject': subject,
                'stats': stats,
                'teachers_str': ', '.join(sorted(list(teachers_by_subject[subject])))
            })
            
    # 4. เตรียมข้อมูล Chart
    chart_data = None
    if overall_stats:
        labels = ['4', '3.5', '3', '2.5', '2', '1.5', '1', '0', 'ร', 'มส']
        data = [overall_stats['grade_distribution'].get(l, 0) for l in labels]
        chart_data = {'labels': labels, 'data': data}

    return render_template('academic/grade_level_detail.html',
                           title=f"ภาพรวมผลการเรียน {grade_level.name}",
                           grade_level=grade_level,
                           form=form,
                           overall_stats=overall_stats,
                           subject_summary_stats=subject_summary_stats,
                           grades_pending_review=grades_pending_review,
                           chart_data=chart_data,
                           semester=semester)

@bp.route('/grade-reports/submit-grade-level/<int:grade_level_id>', methods=['POST'])
@login_required
#@academic_required
def submit_grade_level_grades_from_detail(grade_level_id):
    semester = Semester.query.filter_by(is_current=True).first_or_404()
    courses_to_submit = Course.query.filter(
        Course.semester_id == semester.id,
        Course.grade_submission_status == 'เสนอฝ่ายวิชาการ',
        Course.classroom.has(Classroom.grade_level_id == grade_level_id)
    ).all()

    for course in courses_to_submit:
        course.grade_submission_status = 'รอการอนุมัติจากผู้อำนวยการ'
    
    if courses_to_submit:
        db.session.commit()
        flash(f'ส่งผลการเรียนสำหรับระดับชั้นนี้จำนวน {len(courses_to_submit)} รายการให้ผู้อำนวยการฯ เรียบร้อยแล้ว', 'success')
    
    return redirect(url_for('academic.grade_level_detail', grade_level_id=grade_level_id))

@bp.route('/subject-summary-dept/<int:subject_id>/<int:grade_level_id>')
@login_required
def view_subject_summary_dept(subject_id, grade_level_id):
    subject = Subject.query.get_or_404(subject_id)
    grade_level = GradeLevel.query.get_or_404(grade_level_id)
    semester = Semester.query.filter_by(is_current=True).first_or_404()
    
    # 1. ค้นหา Course ทั้งหมดที่ตรงกับวิชาและระดับชั้น
    courses_in_subject = Course.query.filter(
        Course.semester_id == semester.id,
        Course.subject_id == subject_id,
        Course.classroom.has(Classroom.grade_level_id == grade_level_id)
    ).options(
        joinedload(Course.classroom),
        joinedload(Course.teachers)
    ).order_by(Course.classroom_id).all()

    submitted_courses = [c for c in courses_in_subject if c.grade_submission_status not in ['ยังไม่ส่ง', 'pending']]

    # 2. คำนวณสถิติแยกตามห้องเรียน และรวบรวมข้อมูลทั้งหมด
    all_student_grades_data = []
    summary_data_by_classroom = {}
    grand_max_score = 0

    for course in submitted_courses:
        student_grades, max_scores = calculate_final_grades_for_course(course)
        all_student_grades_data.extend(student_grades)
        
        # ใช้ course.id ที่ไม่ซ้ำกันเป็น key
        summary_data_by_classroom[course.id] = {
            'name': course.classroom.name,
            'stats': calculate_grade_statistics(student_grades)
        }
        if max_scores['grand_total'] > grand_max_score:
            grand_max_score = max_scores['grand_total']

    # 3. คำนวณสถิติภาพรวมของทั้งวิชา
    overall_stats = calculate_grade_statistics(all_student_grades_data)

    # 4. เตรียมข้อมูล Chart
    chart_data = None
    if overall_stats:
        labels = ['4', '3.5', '3', '2.5', '2', '1.5', '1', '0', 'ร', 'มส']
        data = [overall_stats['grade_distribution'].get(l, 0) for l in labels]
        chart_data = {'labels': labels, 'data': data}
        
    all_teachers = list({teacher for course in submitted_courses for teacher in course.teachers})

    return render_template('department/subject_summary_dept.html',
                           title=f"สรุปผลการเรียน: {subject.name}",
                           subject=subject,
                           grade_level=grade_level,
                           semester=semester,
                           summary_data_by_classroom=summary_data_by_classroom,
                           overall_stats=overall_stats,
                           chart_data=chart_data,
                           grand_max_score=grand_max_score,
                           courses_count=len(submitted_courses),
                           all_teachers=all_teachers)

@bp.route('/grade-reports/subject-summary/<int:subject_id>/<int:grade_level_id>')
@login_required
#@academic_required
def subject_summary(subject_id, grade_level_id):
    subject = Subject.query.get_or_404(subject_id)
    grade_level = GradeLevel.query.get_or_404(grade_level_id)
    semester = Semester.query.filter_by(is_current=True).first_or_404()

    # 1. Single Source of Truth: ค้นหา Course ทั้งหมดที่เกี่ยวข้อง
    courses = Course.query.filter(
        Course.semester_id == semester.id,
        Course.subject_id == subject_id,
        Course.classroom.has(Classroom.grade_level_id == grade_level_id),
        Course.grade_submission_status.in_(['เสนอฝ่ายวิชาการ', 'อนุมัติใช้งาน', 'รอตรวจสอบ', 'รอการอนุมัติจากผู้อำนวยการ'])
    ).options(joinedload(Course.teachers), joinedload(Course.classroom)).all()

    if not courses:
        flash(f'ไม่พบข้อมูลผลการเรียนที่ส่งแล้วสำหรับวิชา {subject.name} ในระดับชั้นนี้', 'warning')
        return redirect(url_for('academic.grade_level_detail', grade_level_id=grade_level_id))

    # 2. ประมวลผลข้อมูล
    all_teachers = sorted(list({teacher for course in courses for teacher in course.teachers}), key=lambda t: t.full_name)
    all_student_grades_data = []
    summary_data = {'by_classroom': {}}
    grand_max_score = 0

    for course in courses:
        student_grades, max_scores = calculate_final_grades_for_course(course)
        if not student_grades: continue

        all_student_grades_data.extend(student_grades)
        classroom_stats = calculate_grade_statistics(student_grades)
        summary_data['by_classroom'][course.classroom.id] = {
            'name': course.classroom.name,
            'stats': classroom_stats
        }
        if max_scores['grand_total'] > grand_max_score:
            grand_max_score = max_scores['grand_total']
            
    # 3. คำนวณสถิติภาพรวมและ Chart
    overall_stats = calculate_grade_statistics(all_student_grades_data)
    summary_data['overall'] = {'stats': overall_stats}
    
    if overall_stats:
        labels = ['4', '3.5', '3', '2.5', '2', '1.5', '1', '0', 'ร', 'มส']
        data = [overall_stats['grade_distribution'].get(l, 0) for l in labels]
        summary_data['chart_data'] = {'labels': labels, 'data': data}

    return render_template('academic/subject_summary.html',
                           title=f"สรุปผลการเรียน: {subject.name}",
                           subject=subject,
                           grade_level=grade_level,
                           semester=semester,
                           courses_count=len(courses),
                           all_teachers=all_teachers,
                           summary_data=summary_data,
                           grand_max_score=grand_max_score)

@bp.route('/grade-reports/subject-detail/<int:subject_id>/<int:grade_level_id>')
@login_required
#@academic_required
def subject_detail(subject_id, grade_level_id):
    subject = Subject.query.get_or_404(subject_id)
    grade_level = GradeLevel.query.get_or_404(grade_level_id)
    semester = Semester.query.filter_by(is_current=True).first_or_404()

    # 1. ค้นหา Course ทั้งหมดที่ตรงกับวิชาและระดับชั้นที่เลือก และมีการส่งเกรดแล้ว
    courses = Course.query.filter(
        Course.semester_id == semester.id,
        Course.subject_id == subject_id,
        Course.classroom.has(Classroom.grade_level_id == grade_level_id),
        Course.grade_submission_status.in_(['เสนอฝ่ายวิชาการ', 'อนุมัติใช้งาน', 'รอตรวจสอบ', 'รอการอนุมัติจากผู้อำนวยการ'])
    ).order_by(Course.classroom_id).all()

    # 2. คำนวณเกรดของนักเรียนในแต่ละ Course (ห้องเรียน)
    courses_with_data = []
    for course in courses:
        student_grades, max_scores = calculate_final_grades_for_course(course)
        courses_with_data.append({
            'course': course,
            'student_grades': student_grades,
            'max_scores': max_scores
        })

    return render_template('academic/subject_detail.html',
                           title=f"ผลการเรียนรายบุคคล: {subject.name}",
                           subject=subject,
                           grade_level=grade_level,
                           courses_with_data=courses_with_data)

@bp.route('/remediation-overview')
@login_required
def remediation_overview():
    if not current_user.has_role('Academic'):
        abort(403)

    semester = Semester.query.filter_by(is_current=True).first_or_404()

    # --- THE FIX IS HERE: Query for a TUPLE of (CourseGrade, Enrollment) for ALL students in the system ---
    all_grades_in_process_q = db.session.query(CourseGrade, Enrollment).join(
        Course, CourseGrade.course_id == Course.id
    ).join(
        Enrollment, and_(
            CourseGrade.student_id == Enrollment.student_id,
            Course.classroom_id == Enrollment.classroom_id
        )
    ).filter(
        Course.semester_id == semester.id,
        or_(
            CourseGrade.final_grade.in_(['0', 'ร', 'มส']),
            CourseGrade.remediation_status != 'None'
        )
    ).options(
        joinedload(CourseGrade.student),
        joinedload(CourseGrade.course).joinedload(Course.subject).joinedload(Subject.subject_group),
        joinedload(CourseGrade.course).joinedload(Course.classroom)
    ).all()

    # --- Grouping logic similar to Teacher and Dept Head ---
    pending_approval = []
    forwarded_to_director = []
    awaiting_teacher_action = []

    for grade_obj, enrollment_obj in all_grades_in_process_q:
        item_tuple = (grade_obj, enrollment_obj)
        if grade_obj.remediation_status == 'Submitted to Academic Affairs':
            pending_approval.append(item_tuple)
        elif grade_obj.remediation_status in ['Pending Director Approval', 'Approved']:
            forwarded_to_director.append(item_tuple)
        else: # Covers 'None', 'In Progress', 'Completed' and initial failures
            awaiting_teacher_action.append(item_tuple)

    # --- Stats Calculation ---
    stats = {
        'pending': len(pending_approval),
        'forwarded': len(forwarded_to_director),
        'awaiting': len(awaiting_teacher_action),
        'total': len(all_grades_in_process_q)
    }
    
    # Calculate percentages for the progress bar
    if stats['total'] > 0:
        stats['percent_pending'] = (stats['pending'] / stats['total']) * 100
        stats['percent_forwarded'] = (stats['forwarded'] / stats['total']) * 100
        stats['percent_awaiting'] = 100 - stats['percent_pending'] - stats['percent_forwarded']
    else:
        stats['percent_pending'] = 0
        stats['percent_forwarded'] = 0
        stats['percent_awaiting'] = 0


    return render_template('academic/remediation_overview.html',
                           title="รวบรวมและเสนออนุมัติผลการซ่อม",
                           semester=semester,
                           stats=stats,
                           pending_approval_students=pending_approval,
                           forwarded_to_director_students=forwarded_to_director,
                           awaiting_teacher_action_students=awaiting_teacher_action)

@bp.route('/api/remediation/forward-to-director', methods=['POST'])
@login_required
def forward_remediation_to_director():
    if not current_user.has_role('Academic'):
        return jsonify({'status': 'error', 'message': 'Permission Denied'}), 403

    current_semester = Semester.query.filter_by(is_current=True).first_or_404()
    course_ids_in_semester = db.session.query(Course.id).filter(
        Course.semester_id == current_semester.id
    ).scalar_subquery()

    records_to_update = CourseGrade.query.filter(
        CourseGrade.course_id.in_(course_ids_in_semester),
        CourseGrade.remediation_status == 'Submitted to Academic Affairs'
    ).options(db.load_only(CourseGrade.id)).all()

    if not records_to_update:
        return jsonify({'status': 'info', 'message': 'ไม่พบผลการซ่อมที่รอการส่งต่อ'}), 200

    updated_ids = [r.id for r in records_to_update]
    new_status = 'Pending Director Approval'
    old_status = 'Submitted to Academic Affairs'

    try:
        updated_count = CourseGrade.query.filter(
             CourseGrade.id.in_(updated_ids)
        ).update({'remediation_status': new_status}, synchronize_session=False)

        # --- Log Bulk Action ---
        log_action(
            "Forward Remediation to Director (Academic Bulk)", model=CourseGrade,
            new_value={'count': updated_count, 'new_status': new_status, 'semester_id': current_semester.id},
            old_value={'old_status': old_status}
        )
        # TODO: Add notification for the Director

        db.session.commit()
        return jsonify({
            'status': 'success',
            'message': f'เสนอผลการซ่อมของนักเรียน {updated_count} คนให้ผู้อำนวยการอนุมัติเรียบร้อยแล้ว'
        })
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Error forwarding remediation (Academic): {e}", exc_info=True)
        # --- Log Failure ---
        log_action(f"Forward Remediation Failed (Academic): {type(e).__name__}", model=CourseGrade)
        try: db.session.commit()
        except: db.session.rollback()
        return jsonify({'status': 'error', 'message': f'เกิดข้อผิดพลาด: {e}'}), 500

@bp.route('/assessment-approval')
@login_required
# @Role.permission_required('Academic') # Assuming decorator exists or add check
def assessment_approval():
    current_semester = Semester.query.filter_by(is_current=True).first_or_404()

    # --- Part 1: Get ALL Submitted Records (No changes needed here) ---
    records_in_process = db.session.query(AdvisorAssessmentRecord, Enrollment).join(
        Enrollment, AdvisorAssessmentRecord.student_id == Enrollment.student_id
    ).join(
        Classroom, Enrollment.classroom_id == Classroom.id 
    ).filter(
        AdvisorAssessmentRecord.semester_id == current_semester.id,
        Classroom.academic_year_id == current_semester.academic_year_id, 
        AdvisorAssessmentRecord.status.in_([
            'Submitted to Academic Affairs',  # รายการที่ต้องตรวจสอบ (Pending ของคุณ)
            'Pending Director Approval',      # รายการที่ส่งต่อให้ ผอ. แล้ว
            'Approved'                        # รายการที่ ผอ. อนุมัติแล้ว
        ])
    ).options(
        joinedload(AdvisorAssessmentRecord.student),
        joinedload(Enrollment.classroom).joinedload(Classroom.grade_level), 
        joinedload(Enrollment.classroom).joinedload(Classroom.advisors), 
        joinedload(AdvisorAssessmentRecord.scores).joinedload(AdvisorAssessmentScore.topic) 
    ).order_by(Classroom.grade_level_id, Enrollment.classroom_id, Enrollment.roll_number).all()

    # --- Part 2: Group by GRADE LEVEL then Classroom ---
    records_by_grade_level = defaultdict(lambda: defaultdict(lambda: {'records': [], 'advisors': []}))
    processed_classrooms = set()
    all_pending_academic_records = [] 
    
    templates = AssessmentTemplate.query.options(joinedload(AssessmentTemplate.rubric_levels), joinedload(AssessmentTemplate.topics)).all()
    first_template = next((t for t in templates if t.rubric_levels), None) 
    rubric_map = {r.value: r.label for r in first_template.rubric_levels} if first_template else {}
    total_pending_academic = 0

    stats = { 'pending': 0, 'approved': 0 } # Initialize stats correctly here

    for record, enrollment in records_in_process:
        classroom = enrollment.classroom
        classroom_name = classroom.name 
        grade_level = classroom.grade_level 
        grade_level_name = grade_level.name 

        if classroom.id not in processed_classrooms:
            records_by_grade_level[grade_level_name][classroom_name]['advisors'] = [adv.first_name for adv in classroom.advisors]
            processed_classrooms.add(classroom.id)
        
        summary_dist = defaultdict(int) 
        pending_scores_for_mode = [] 
        for score in record.scores:
            if score.topic and score.topic.parent_id is None: 
                label = rubric_map.get(score.score_value, 'N/A')
                summary_dist[label] += 1
                if record.status == 'Submitted to Academic Affairs': 
                    pending_scores_for_mode.append(score.score_value)
        item_tuple = (record, enrollment, dict(summary_dist)) 

        records_by_grade_level[grade_level_name][classroom_name]['records'].append(item_tuple) 
        
        if record.status == 'Submitted to Academic Affairs': 
            total_pending_academic += 1
            all_pending_academic_records.append(record) 
            
    stats['pending'] = total_pending_academic
    stats['approved'] = len(records_in_process) - total_pending_academic
    # --- END REVISED PART 2 ---

    # --- Part 3: Calculate Statistics for STACKED BAR CHART (Using ALL Submitted Records) ---
    assessment_stats_by_template = {}
    for template in templates:
        assessment_stats_by_template[template.id] = {'id': template.id,'name': template.name,'topic_labels': [],'datasets': []}
        
    if records_in_process: 
        all_record_ids_in_view = [r.id for r, e in records_in_process] 
        all_scores_in_view = db.session.query(AdvisorAssessmentScore).options(joinedload(AdvisorAssessmentScore.topic)).filter(
            AdvisorAssessmentScore.record_id.in_(all_record_ids_in_view)
        ).all()
        
        scores_by_template = defaultdict(lambda: defaultdict(lambda: defaultdict(int)))
        for score in all_scores_in_view: 
            if score.topic and score.topic.template_id and score.topic.parent_id is None:
                template = next((t for t in templates if t.id == score.topic.template_id), None)
                if template:
                    rubric_map_local = {r.value: r.label for r in template.rubric_levels} 
                    label = rubric_map_local.get(score.score_value, 'N/A')
                    scores_by_template[template.id][score.topic.name][label] += 1

        for template in templates:
            if template.id in scores_by_template:
                rubric_map_local = {r.value: r.label for r in template.rubric_levels}
                chart_labels = sorted(list(rubric_map_local.values()), key=lambda x: [k for k, v in rubric_map_local.items() if v == x][0], reverse=True)
                topic_labels = sorted(scores_by_template[template.id].keys())
                datasets = []
                colors = {'ดีเยี่ยม': 'rgba(40, 167, 69, 0.7)', 'ดี': 'rgba(0, 123, 255, 0.7)', 'ผ่าน': 'rgba(255, 193, 7, 0.7)', 'ไม่ผ่าน': 'rgba(220, 53, 69, 0.7)'}
                for i, label in enumerate(chart_labels):
                    data = [scores_by_template[template.id][topic].get(label, 0) for topic in topic_labels]
                    datasets.append({'label': label, 'data': data, 'backgroundColor': colors.get(label, 'rgba(108, 117, 125, 0.7)')})
                assessment_stats_by_template[template.id]['topic_labels'] = topic_labels
                assessment_stats_by_template[template.id]['datasets'] = datasets

    # --- Calculation for overall_mode_distribution (remains the same) ---
    overall_mode_distribution = defaultdict(int)
    if all_pending_academic_records:
        pending_record_ids = [r.id for r in all_pending_academic_records]
        all_pending_scores_q = db.session.query(
            AdvisorAssessmentScore.record_id, 
            AdvisorAssessmentScore.score_value
        ).join(AdvisorAssessmentScore.topic).filter(
            AdvisorAssessmentScore.record_id.in_(pending_record_ids),
            AssessmentTopic.parent_id == None 
        ).all()
        scores_by_record = defaultdict(list)
        for record_id, score_value in all_pending_scores_q:
            scores_by_record[record_id].append(score_value)
        for record_id, scores in scores_by_record.items():
            if scores:
                try:
                    calculated_mode = mode(scores)
                except StatisticsError: 
                    calculated_mode = max(scores)
                mode_label = rubric_map.get(calculated_mode, 'N/A')
                overall_mode_distribution[mode_label] += 1

    return render_template('academic/assessment_approval.html', 
                           title='เสนออนุมัติผลการประเมิน',
                           semester=current_semester,
                           stats=stats,
                           records_by_grade_level=dict(records_by_grade_level), # Pass the nested structure
                           assessment_stats=assessment_stats_by_template,
                           overall_mode_distribution=dict(overall_mode_distribution))

@bp.route('/api/approve-assessments', methods=['POST']) # Forwarding Assessments to Director
@login_required
def approve_assessments(): # Renaming recommended: forward_assessments_to_director_api
    if not current_user.has_role('Academic'): abort(403)
    current_semester = Semester.query.filter_by(is_current=True).first_or_404()

    records_to_update = AdvisorAssessmentRecord.query.filter(
        AdvisorAssessmentRecord.semester_id == current_semester.id,
        AdvisorAssessmentRecord.status == 'Submitted to Academic Affairs'
    ).options(db.load_only(AdvisorAssessmentRecord.id)).all()

    if not records_to_update:
        return jsonify({'status': 'info', 'message': 'ไม่พบรายการประเมินที่รอการส่งต่อ'}), 200

    record_ids = [r.id for r in records_to_update]
    new_status = 'Pending Director Approval' # Sending to Director
    old_status = 'Submitted to Academic Affairs'

    try:
        updated_count = AdvisorAssessmentRecord.query.filter(
            AdvisorAssessmentRecord.id.in_(record_ids)
        ).update({'status': new_status}, synchronize_session=False)

        # --- Log Bulk Action ---
        log_action(
            "Forward Assessments to Director (Academic Bulk)", model=AdvisorAssessmentRecord,
            new_value={'count': updated_count, 'new_status': new_status, 'semester_id': current_semester.id},
            old_value={'old_status': old_status}
        )
        # TODO: Add Notification for Director

        db.session.commit()
        response_data = {'status': 'success', 'message': f'ส่งต่อผลการประเมิน {updated_count} รายการให้ผู้อำนวยการเรียบร้อยแล้ว'}
        print("----- DEBUG API: Returning JSON:", response_data) # Keep if helpful
        return jsonify(response_data)
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Error forwarding assessments (Academic): {e}", exc_info=True)
        # --- Log Failure ---
        log_action(f"Forward Assessments Failed (Academic): {type(e).__name__}", model=AdvisorAssessmentRecord)
        try: db.session.commit()
        except: db.session.rollback()
        return jsonify({'status': 'error', 'message': f'เกิดข้อผิดพลาด: {e}'}), 500

@bp.route('/api/academic/forward-to-director', methods=['POST'])
@login_required
def forward_to_director():
    if not current_user.has_role('Academic'):
        abort(403)
    
    current_semester = Semester.query.filter_by(is_current=True).first_or_404()

    updated_count = AdvisorAssessmentRecord.query.filter(
        AdvisorAssessmentRecord.semester_id == current_semester.id,
        AdvisorAssessmentRecord.status == 'Submitted to Academic Affairs'
    ).update({'status': 'Pending Director Approval'}, synchronize_session=False)

    if updated_count > 0:
        db.session.commit()

    return jsonify({'status': 'success', 'message': f'ส่งต่อผลการประเมิน {updated_count} รายการให้ผู้อำนวยการเรียบร้อยแล้ว'})

# ==========================================================
# [NEW] API สำหรับ MODAL (ตาม Gold Standard)
# ==========================================================
@bp.route('/api/assessment-record/<int:record_id>/details')
@login_required
def get_assessment_details(record_id):
    # 1. ดึงข้อมูลหลัก (Record และ Enrollment)
    record = db.session.get(AdvisorAssessmentRecord, record_id)
    enrollment = None
    if record:
        enrollment = Enrollment.query.join(Classroom).filter(
            Enrollment.student_id == record.student_id,
            Classroom.academic_year_id == record.semester.academic_year_id
        ).first()

    # 2. ตรวจสอบสิทธิ์ (ฝ่ายวิชาการดูได้ทุกคน ไม่ต้องเช็คสายชั้น)
    if not record or not enrollment or not current_user.has_role('Academic'):
        abort(404)

    # 3. ดึง "หลักฐาน" (Evidence Pool) ทั้งหมดของนักเรียนในเทอมนั้น
    evidence_scores_query = db.session.query(
        QualitativeScore,
        Subject.name.label('subject_name')
    ).join(
        Course, QualitativeScore.course_id == Course.id
    ).join(
        Subject, Course.subject_id == Subject.id
    ).filter(
        QualitativeScore.student_id == record.student_id,
        Course.semester_id == record.semester_id
    ).all()

    # 4. สร้าง Map ของ Rubric Levels ทั้งหมด
    all_templates = AssessmentTemplate.query.options(joinedload(AssessmentTemplate.rubric_levels)).all()
    global_rubric_map = {}
    for t in all_templates:
        for r in t.rubric_levels:
            global_rubric_map[(t.id, r.value)] = r.label

    # 5. จัดกลุ่มหลักฐานตาม Topic ID
    evidence_by_topic_id = defaultdict(list)
    for q_score, subject_name in evidence_scores_query:
        evidence_by_topic_id[q_score.assessment_topic_id].append({
            'subject': subject_name,
            'score_value': q_score.score_value
        })

    # 6. ดึงข้อมูลคะแนนสรุป (Advisor's Score)
    scores_by_topic_id = {s.topic_id: s.score_value for s in record.scores}
    
    # 7. สร้างข้อมูล JSON ที่จะส่งกลับ
    response_data = []
    templates = AssessmentTemplate.query.options(joinedload(AssessmentTemplate.topics), joinedload(AssessmentTemplate.rubric_levels)).all()

    for template in templates:
        local_rubric_map = {r.value: r.label for r in template.rubric_levels}
        
        template_data = {
            'id': template.id,
            'name': template.name,
            'rubric_map': local_rubric_map,
            'topics': []
        }
        
        main_topics = sorted([t for t in template.topics if not t.parent_id], key=lambda t: t.id)
        has_data = False

        for topic in main_topics:
            score_value = scores_by_topic_id.get(topic.id)
            
            if score_value is not None:
                has_data = True
                
                evidence_list_for_topic = []
                for ev in evidence_by_topic_id.get(topic.id, []):
                    evidence_list_for_topic.append({
                        'subject': ev['subject'],
                        'score_label': local_rubric_map.get(ev['score_value'], 'N/A')
                    })
                score_label = local_rubric_map.get(score_value, score_value)
                template_data['topics'].append({
                    'name': topic.name,
                    'score': score_value,
                    'score_label': score_label,
                    'evidence_scores': evidence_list_for_topic
                })

        if has_data: 
            response_data.append(template_data)
            
    return jsonify(response_data)

@bp.route('/graduation-approval', methods=['GET'])
@login_required
# @academic_affair_or_director_required
def graduation_approval():
    # ... (code to get current_semester, current_academic_year, form) ...
    form = FlaskForm() # For CSRF
    current_semester = Semester.query.filter_by(is_current=True).first()
    # ... (Error handling for semester) ...
    current_academic_year_id = current_semester.academic_year_id
    current_academic_year = db.session.get(AcademicYear, current_academic_year_id)

    graduating_grade_short_names = ['ม.3', 'ม.6']
    graduating_students_data = []
    # ... (code to query enrollments - same as before) ...
    enrollments = Enrollment.query.join(Classroom).join(GradeLevel).filter(
        Classroom.academic_year_id == current_academic_year_id,
        GradeLevel.short_name.in_(graduating_grade_short_names)
    ).options(
        joinedload(Enrollment.student),
        joinedload(Enrollment.classroom).joinedload(Classroom.grade_level)
    ).order_by(Classroom.name, Enrollment.roll_number).all()


    for en in enrollments:
        student = en.student
        is_ready, reason = check_graduation_readiness(student.id, current_academic_year_id)
        graduating_students_data.append({
            'enrollment_id': en.id,
            'student_id': student.id,
            'student_code': student.student_id,
            'full_name': f"{student.name_prefix or ''}{student.first_name} {student.last_name}".strip(),
            'classroom_name': en.classroom.name,
            'current_status': student.status,
            'is_ready': is_ready,
            'reason': reason # Pass the potentially detailed reason
        })

    return render_template('academic/graduation_approval.html',
                           # [REVISED] Title
                           title='ตรวจสอบและเสนอชื่อผู้สำเร็จการศึกษา',
                           form=form,
                           academic_year=current_academic_year,
                           students_data=graduating_students_data)


# [REVISED] Function to handle submission for director's approval
@bp.route('/graduation-approval/submit', methods=['POST'])
@login_required
# @academic_affair_or_director_required
def submit_graduation_approval():
    form = FlaskForm()
    if not form.validate_on_submit():
         flash('Invalid request (CSRF token missing or expired)', 'danger')
         return redirect(url_for('academic.graduation_approval'))

    verified_student_ids = request.form.getlist('approved_students', type=int) # Renamed variable
    current_academic_year_id = request.form.get('academic_year_id', type=int)

    if not current_academic_year_id:
         flash('ข้อมูลปีการศึกษาไม่ถูกต้อง', 'danger')
         return redirect(url_for('academic.graduation_approval'))

    submitted_count = 0
    errors = []

    # --- Find Graduating Students Again for Validation ---
    graduating_grade_short_names = ['ม.3', 'ม.6']
    valid_student_ids_in_year = { en.student_id for en in Enrollment.query.join(Classroom).join(GradeLevel).filter(
        Classroom.academic_year_id == current_academic_year_id,
        GradeLevel.short_name.in_(graduating_grade_short_names)).options(db.load_only(Enrollment.student_id)).all()
    }

    students_to_verify = Student.query.filter(Student.id.in_(verified_student_ids)).all()

    for student in students_to_verify:
         if student.id not in valid_student_ids_in_year:
              errors.append(f"นักเรียน {student.full_name} ไม่ได้อยู่ในระดับชั้น ม.3/ม.6 ในปีการศึกษานี้")
              continue

         is_ready, reason = check_graduation_readiness(student.id, current_academic_year_id)
         if is_ready is True:
              # --- [REVISED ACTION] Instead of changing status, set a flag/status for director ---
              # Option 1: Add a new field to Student model (e.g., graduation_status)
              # student.graduation_status = 'Pending Director Approval'
              # Option 2: Use a separate table (if more complex workflow needed)
              # graduation_request = GraduationApprovalRequest(student_id=student.id, academic_year_id=..., status='Pending Director')
              # db.session.add(graduation_request)

              # --- For now, let's just count and flash a message ---
              # We will add the actual status update/notification later when building Director part
              if student.status == 'กำลังศึกษา': # Only count those who are not already graduated
                   submitted_count += 1
              elif student.status == 'จบการศึกษา':
                   errors.append(f"นักเรียน {student.full_name} มีสถานะจบการศึกษาอยู่แล้ว")
              else:
                   errors.append(f"สถานะปัจจุบันของ {student.full_name} คือ '{student.status}', ไม่สามารถเสนอชื่อได้")

         elif is_ready is False:
              errors.append(f"นักเรียน {student.full_name} ยังไม่พร้อมจบ ({reason}) - ไม่สามารถเสนอชื่อได้")
         else:
              errors.append(f"ไม่สามารถตรวจสอบสถานะความพร้อมของ {student.full_name} ได้ ({reason})")

    if errors:
         for error in errors: flash(f'ข้อผิดพลาด: {error}', 'danger')

    if submitted_count > 0:
         # In a real scenario, commit the status changes/new requests here
         # try:
         #     db.session.commit()
         # except Exception as e:
         #     db.session.rollback()
         #     flash(f'เกิดข้อผิดพลาดในการบันทึก: {e}', 'danger')
         #     return redirect(url_for('academic.graduation_approval'))

         # TODO: Create Notifications for Director

         flash(f'เสนอรายชื่อนักเรียน {submitted_count} คน ให้ผู้อำนวยการอนุมัติจบหลักสูตรเรียบร้อยแล้ว', 'success')
    elif not errors: # No one submitted and no errors
         flash('กรุณาเลือกนักเรียนที่พร้อมจบการศึกษาเพื่อเสนอชื่อ', 'info')


    return redirect(url_for('academic.graduation_approval'))

@bp.route('/review-repeat-candidates')
@login_required
# @academic_required
def review_repeat_candidates_academic():
    """Displays candidates pending Academic Affairs review."""
    form = FlaskForm() # For CSRF

    # Find candidates whose status is pending Academic review
    candidates = db.session.query(RepeatCandidate).filter(
        RepeatCandidate.status.like('Pending Academic Review%') # Match both 'Repeat' and 'Promote' pending
    ).options(
        joinedload(RepeatCandidate.student),
        joinedload(RepeatCandidate.previous_enrollment).joinedload(Enrollment.classroom).joinedload(Classroom.grade_level), # Load grade level too
        joinedload(RepeatCandidate.academic_year) # Year failed
    ).order_by(RepeatCandidate.updated_at.asc()).all() # Show oldest first

    return render_template('academic/review_repeat_candidates_academic.html',
                           title='พิจารณานักเรียนซ้ำชั้น/เลื่อนชั้นพิเศษ (ฝ่ายวิชาการ)',
                           candidates=candidates,
                           form=form)

@bp.route('/review-repeat-candidates/submit/<int:candidate_id>', methods=['POST'])
@login_required
# @academic_required
def submit_academic_decision(candidate_id):
    candidate = db.session.get(RepeatCandidate, candidate_id)
    # ... (Security Check - unchanged) ...
    if (not candidate or not candidate.status.startswith('Pending Academic Review')):
         flash('ไม่พบข้อมูลหรือสถานะไม่ถูกต้อง', 'danger')
         return redirect(url_for('academic.review_repeat_candidates_academic'))

    decision = request.form.get('decision')
    notes = request.form.get('notes', '')
    original_status = candidate.status
    new_status = None

    if decision == 'approve':
        if candidate.status.endswith('(Repeat)'): new_status = 'Pending Director Approval (Repeat)'
        elif candidate.status.endswith('(Promote)'): new_status = 'Pending Director Approval (Promote)'
        else: new_status = 'Pending Director Approval'
    elif decision == 'reject':
        new_status = 'Rejected by Academic Affairs'
    else:
        flash('กรุณาเลือกการดำเนินการ (เห็นด้วย/ไม่เห็นด้วย)', 'warning')
        return redirect(url_for('academic.review_repeat_candidates_academic'))

    try:
        candidate.status = new_status
        candidate.academic_notes = notes
        # --- Log Action ---
        log_action(
            f"Academic Review Repeat Candidate ({decision})", model=RepeatCandidate, record_id=candidate.id,
            old_value=original_status, new_value={'status': new_status, 'notes': notes}
        )
        db.session.commit()
        # TODO: Add Notification for Director if approved
        if decision == 'approve':
            flash(f'ส่งเรื่องของ {candidate.student.full_name} ให้ผู้อำนวยการพิจารณาต่อเรียบร้อยแล้ว', 'success')
        else:
            flash(f'บันทึกผลการพิจารณา (ไม่เห็นด้วย) สำหรับ {candidate.student.first_name} เรียบร้อยแล้ว', 'info')
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Error submitting academic decision for candidate {candidate_id}: {e}", exc_info=True)
        # --- Log Failure ---
        log_action(f"Academic Review Repeat Candidate Failed: {type(e).__name__}", model=RepeatCandidate, record_id=candidate.id)
        try: db.session.commit()
        except: db.session.rollback()
        flash(f'เกิดข้อผิดพลาด: {e}', 'danger')

    return redirect(url_for('academic.review_repeat_candidates_academic'))

@bp.route('/manage-repeat-enrollment')
@login_required
# @academic_required
def manage_repeat_enrollment():
    """
    Displays approved repeat/promote candidates for Academic Affairs
    to enroll them into a new classroom.
    """
    form = FlaskForm() # For CSRF
    current_semester = Semester.query.filter_by(is_current=True).first_or_404()
    target_academic_year_id = current_semester.academic_year_id # We enroll into the CURRENT year
    target_academic_year = current_semester.academic_year

    # Find candidates who were approved for action relating to *last* year,
    # and need enrollment in the *current* year.
    # This logic assumes promotion process happens *before* the new year starts
    # Let's adjust: Find candidates approved for action *into* the current year.
    # This requires RepeatCandidate to store target_year_id, or we assume it's always "current_year"
    
    # Simpler Logic: Find all approved candidates who DON'T have an enrollment in the current year yet.
    
    # 1. Find all students approved for action (Repeat or Promote)
    approved_candidates = db.session.query(RepeatCandidate).filter(
        RepeatCandidate.status.like('Approved%') # Approved (Repeat), Approved (Promote)
    ).options(
        joinedload(RepeatCandidate.student),
        joinedload(RepeatCandidate.academic_year) # Year they failed
    ).all()

    # 2. Find student IDs who ALREADY have an enrollment in the current year
    enrolled_student_ids = db.session.query(Enrollment.student_id).join(Classroom).filter(
        Classroom.academic_year_id == target_academic_year_id
    ).scalar_subquery()

    # 3. Filter list to show only those NOT yet enrolled
    candidates_to_enroll = [
        c for c in approved_candidates if c.student_id not in enrolled_student_ids
    ]

    # 4. Get all classrooms for the current year (target year)
    target_classrooms = Classroom.query.filter_by(
        academic_year_id=target_academic_year_id
    ).order_by(Classroom.name).all()

    return render_template('academic/manage_repeat_enrollment.html',
                           title='จัดสรรห้องเรียนนักเรียนซ้ำชั้น/เลื่อนชั้นพิเศษ',
                           candidates=candidates_to_enroll,
                           classrooms=target_classrooms,
                           academic_year=target_academic_year,
                           form=form)

@bp.route('/api/enroll-repeater', methods=['POST'])
@login_required
# @academic_required
def api_enroll_repeater():
    data = request.get_json()
    student_id = data.get('student_id')
    target_classroom_id = data.get('classroom_id')
    candidate_id = data.get('candidate_id')
    roll_number = data.get('roll_number')

    if not all([student_id, target_classroom_id, candidate_id, roll_number]):
        return jsonify({'status': 'error', 'message': 'ข้อมูลไม่ครบถ้วน'}), 400

    # Validation (unchanged)
    candidate = db.session.get(RepeatCandidate, candidate_id)
    target_classroom = db.session.get(Classroom, target_classroom_id)
    student = db.session.get(Student, student_id)
    if not candidate or not target_classroom or not student: return jsonify({'status': 'error', 'message': 'ข้อมูลไม่ถูกต้อง'}), 404
    if not candidate.status.startswith('Approved'): return jsonify({'status': 'error', 'message': 'นักเรียนยังไม่ได้รับการอนุมัติขั้นสุดท้าย'}), 403
    existing_enrollment = Enrollment.query.join(Classroom).filter(
        Enrollment.student_id == student_id,
        Classroom.academic_year_id == target_classroom.academic_year_id
    ).first()
    if existing_enrollment: return jsonify({'status': 'error', 'message': f'นักเรียนมีห้องเรียนในปีการศึกษานี้แล้ว ({existing_enrollment.classroom.name})'}), 409

    try:
        new_enrollment = Enrollment(
            student_id=student_id,
            classroom_id=target_classroom_id,
            roll_number=int(roll_number)
        )
        db.session.add(new_enrollment)
        db.session.flush() # Get ID

        old_candidate_status = candidate.status
        candidate.status = f"{candidate.status} - Enrolled"

        # --- Log Actions ---
        log_action(
            "Enroll Repeat/Promote Candidate", model=Enrollment, record_id=new_enrollment.id,
            new_value={'student_id': student_id, 'classroom_id': target_classroom_id, 'roll_number': roll_number, 'candidate_id': candidate_id}
        )
        log_action(
            "Update Repeat Candidate Status (Enrolled)", model=RepeatCandidate, record_id=candidate.id,
            old_value=old_candidate_status, new_value=candidate.status
        )
        # --- End Log ---

        db.session.commit()
        return jsonify({'status': 'success', 'message': f'จัดสรรห้องเรียน {target_classroom.name} ให้ {student.first_name} สำเร็จ'})
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Error enrolling repeater: {e}", exc_info=True)
        # --- Log Failure ---
        log_action(f"Enroll Repeater Failed: {type(e).__name__}", model=Enrollment, new_value={'student_id': student_id, 'classroom_id': target_classroom_id})
        try: db.session.commit()
        except: db.session.rollback()
        # --- End Log ---
        return jsonify({'status': 'error', 'message': f'Database error: {e}'}), 500