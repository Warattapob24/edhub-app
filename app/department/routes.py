# FILE: app/department/routes.py
from collections import Counter, defaultdict
from flask import current_app, flash, redirect, render_template, jsonify, request, abort, url_for
from flask_login import login_required, current_user
from flask_wtf import FlaskForm
import numpy as np
from sqlalchemy.orm import joinedload, selectinload
from sqlalchemy import and_, func, or_
from app.department import bp
from app import db
from app.models import AssessmentItem, AssessmentTopic, Classroom, Course, CourseGrade, Curriculum, AssessmentDimension, Enrollment, GradeLevel, GradedItem, Indicator, LessonPlan, LearningUnit, Semester, Standard, Student, Subject, User, learning_unit_indicators
from app.services import calculate_final_grades_for_course

@bp.route('/dashboard')
@login_required
def dashboard():
    subject_group = current_user.led_subject_group
    if not subject_group:
        abort(403)

    current_semester = Semester.query.filter_by(is_current=True).first_or_404()
    form = FlaskForm()

    all_grade_levels = GradeLevel.query.all()
    m_ton_grade_ids = [gl.id for gl in all_grade_levels if gl.level_group == 'm-ton']
    m_plai_grade_ids = [gl.id for gl in all_grade_levels if gl.level_group == 'm-plai']

    all_grade_levels = GradeLevel.query.all()
    m_ton_grade_ids = {gl.id for gl in all_grade_levels if gl.level_group == 'm-ton'}
    m_plai_grade_ids = {gl.id for gl in all_grade_levels if gl.level_group == 'm-plai'}

    # 1. Get ALL courses for the subject group in the current semester to use as a single source of truth
    all_courses_in_group = Course.query.join(Subject).join(Classroom).filter(
        Course.semester_id == current_semester.id,
        Subject.subject_group_id == subject_group.id
    ).options(
        joinedload(Course.subject),
        joinedload(Course.classroom),
        joinedload(Course.teachers)
    ).all()

    # 2. Process the single list of courses to calculate everything consistently
    total_m_ton = 0
    submitted_m_ton = 0
    total_m_plai = 0
    submitted_m_plai = 0
    submitted_courses = []

    for course in all_courses_in_group:
        grade_level_id = course.classroom.grade_level_id
        is_submitted = course.grade_submission_status not in ['ยังไม่ส่ง', 'pending']

        if grade_level_id in m_ton_grade_ids:
            total_m_ton += 1
            if is_submitted:
                submitted_m_ton += 1
        elif grade_level_id in m_plai_grade_ids:
            total_m_plai += 1
            if is_submitted:
                submitted_m_plai += 1

        if is_submitted:
            submitted_courses.append(course)

    # 3. Create the progress dictionaries for the cards
    m_ton_percentage = (submitted_m_ton / total_m_ton * 100) if total_m_ton > 0 else 0
    m_ton_progress = {'total': total_m_ton, 'submitted': submitted_m_ton, 'percentage': m_ton_percentage}

    m_plai_percentage = (submitted_m_plai / total_m_plai * 100) if total_m_plai > 0 else 0
    m_plai_progress = {'total': total_m_plai, 'submitted': submitted_m_plai, 'percentage': m_plai_percentage}

    all_student_final_data = []
    courses_with_stats = []

    def process_stats(grade_list):
        if not grade_list: return None
        stats = {}
        # Use only non-empty strings for total_students
        valid_grades_list = [g for g in grade_list if g is not None and g != '']
        total_students = len(valid_grades_list)

        if total_students == 0: return None

        grade_counts = Counter(valid_grades_list)
        stats['grade_distribution'] = {str(g): grade_counts.get(str(g), 0) for g in ['4','3.5','3','2.5','2','1.5','1','0','ร','มส']}

        valid_grades_for_gpa = [float(g) for g in valid_grades_list if g not in ['ร', 'มส']]
        stats['gpa'] = np.mean(valid_grades_for_gpa) if valid_grades_for_gpa else 0
        stats['sd'] = np.std(valid_grades_for_gpa, ddof=1) if len(valid_grades_for_gpa) > 1 else 0

        stats['failed_count'] = grade_counts.get('0', 0) + grade_counts.get('ร', 0) + grade_counts.get('มส', 0)
        stats['passed_count'] = sum(grade_counts.get(str(g), 0) for g in ['4','3.5','3','2.5','2','1.5','1'])
        stats['good_excellent_count'] = sum(grade_counts.get(str(g), 0) for g in ['4','3.5','3'])

        stats['failed_percent'] = (stats['failed_count'] / total_students) * 100
        stats['passed_percent'] = (stats['passed_count'] / total_students) * 100
        stats['good_excellent_percent'] = (stats['good_excellent_count'] / total_students) * 100

        stats['total_students'] = total_students
        return stats

    grades_by_grade_level = defaultdict(list)
    all_student_final_data = []

    for course in submitted_courses:
        student_grades, _ = calculate_final_grades_for_course(course)
        all_student_final_data.extend(student_grades) # For overall stats
        grade_level = course.classroom.grade_level
        grades = [data['grade'] for data in student_grades]
        grades_by_grade_level[grade_level].extend(grades)

    grade_level_summary_stats = []
    sorted_grade_levels = sorted(grades_by_grade_level.keys(), key=lambda gl: gl.id)

    for gl in sorted_grade_levels:
        aggregated_grades = grades_by_grade_level[gl]
        stats = process_stats(aggregated_grades)
        if stats:
            grade_level_summary_stats.append({
                'grade_level': gl,
                'stats': stats
            })

    overall_grades = [data['grade'] for data in all_student_final_data]
    overall_stats = process_stats(overall_grades)

    chart_data = None
    if overall_stats:
        chart_labels = ['4','3.5','3','2.5','2','1.5','1','0','ร','มส']
        chart_values = [overall_stats.get('grade_distribution', {}).get(label, 0) for label in chart_labels]
        chart_data = {'labels': chart_labels, 'data': chart_values}

    # --- ส่วนเดิม: Logic สำหรับ Tab "ภาพรวมแผนการสอน" (จากโค้ดของท่าน) ---
    plans_for_checklist = (
        LessonPlan.query.join(LessonPlan.subject).filter(
            LessonPlan.status.in_(['รอการตรวจสอบ', 'เสนอฝ่ายวิชาการ', 'ผ่านการตรวจสอบ', 'รอการอนุมัติจากผู้อำนวยการ', 'อนุมัติใช้งาน']),
            Subject.subject_group_id == subject_group.id,
            LessonPlan.academic_year_id == current_semester.academic_year_id
        ).order_by(
            db.case((LessonPlan.status == 'รอการตรวจสอบ', 0), else_=1),
            LessonPlan.id.desc()
        ).options(
            joinedload(LessonPlan.subject),
            joinedload(LessonPlan.courses).joinedload(Course.classroom),
            joinedload(LessonPlan.courses).joinedload(Course.teachers),
            selectinload(LessonPlan.learning_units) # Simplified for dashboard
        ).all()
    )
    
    grades_pending_review = Course.query.join(Subject).filter(
        Course.semester_id == current_semester.id,
        Subject.subject_group_id == subject_group.id,
        Course.grade_submission_status == 'รอตรวจสอบ (หน.กลุ่มสาระ)'
    ).options(
        joinedload(Course.subject),
        joinedload(Course.classroom),
        joinedload(Course.submitted_by)
    ).order_by(Course.submitted_at.asc()).all()

    for plan in plans_for_checklist:
        report = {'components_status': {}}
        all_units = plan.learning_units
        all_graded_items = [item for unit in all_units for item in unit.graded_items]
        formative_total = sum(item.max_score for item in all_graded_items if item.max_score)
        midterm_total = sum(unit.midterm_score for unit in all_units if unit.midterm_score)
        final_total = sum(unit.final_score for unit in all_units if unit.final_score)
        score_during_semester = formative_total + midterm_total
        score_final = final_total
        report['formative_score'] = {'value': score_during_semester, 'status': score_during_semester > 0}
        report['final_score'] = {'value': score_final, 'status': score_final > 0}
        total_hours = sum(unit.hours for unit in all_units if unit.hours)
        expected_total_periods = (plan.subject.credit or 0) * 40
        report['total_periods'] = {'value': total_hours, 'status': total_hours >= expected_total_periods}
        # Component Checks
        report['components_status']['indicators'] = any(unit.indicators for unit in all_units)
        report['components_status']['core_concepts'] = any(unit.core_concepts for unit in all_units)
        report['components_status']['learning_objectives'] = any(unit.learning_objectives for unit in all_units)
        report['components_status']['learning_content'] = any(unit.learning_content for unit in all_units)
        report['components_status']['learning_activities'] = any(unit.learning_activities for unit in all_units)
        report['components_status']['media_sources'] = any(unit.media_sources for unit in all_units)
        report['components_status']['sub_units'] = any(unit.sub_units for unit in all_units)
        report['components_status']['assessment_items'] = any(unit.assessment_items for unit in all_units)
        plan.completeness_report = report

    plan_stats = {status: count for status, count in db.session.query(LessonPlan.status, func.count(LessonPlan.id)).join(Subject).filter(Subject.subject_group_id == subject_group.id, LessonPlan.academic_year_id == current_semester.academic_year_id).group_by(LessonPlan.status).all()}
    teachers_in_group = User.query.filter(User.member_of_groups.any(id=subject_group.id)).all()
    teacher_workloads = []
    for teacher in teachers_in_group:
        courses_taught = Course.query.filter(Course.teachers.any(id=teacher.id), Course.semester_id == current_semester.id).options(joinedload(Course.subject)).all()
        unique_subject_ids, total_credits, total_periods_per_week = set(), 0, 0
        for course in courses_taught:
            total_periods_per_week += (course.subject.credit or 0) * 2
            if course.subject.id not in unique_subject_ids:
                total_credits += (course.subject.credit or 0)
                unique_subject_ids.add(course.subject.id)
        teacher_workloads.append({'name': teacher.full_name, 'credits': total_credits, 'periods': total_periods_per_week})
    teacher_workloads.sort(key=lambda x: x['name'])
    # --- สิ้นสุดส่วนเดิม ---

    return render_template(
        'department/dashboard.html',
        title=f'ภาพรวมกลุ่มสาระฯ {subject_group.name}',
        form=form,
        m_ton_progress=m_ton_progress,
        m_plai_progress=m_plai_progress,
        overall_stats=overall_stats,
        chart_data=chart_data,
        grade_level_summary_stats=grade_level_summary_stats,
        subject_group=subject_group,
        plans_for_checklist=plans_for_checklist,
        stats=plan_stats,
        teacher_count=len(teachers_in_group),
        teacher_workloads=teacher_workloads,
        grades_pending_review=grades_pending_review,
        used_indicators={}, 
        used_assessment_topics={}
    )

@bp.route('/assignments')
@login_required
def assign_teaching():
    # ตรวจสอบว่าผู้ใช้เป็นหัวหน้ากลุ่มสาระฯ หรือไม่
    subject_group = current_user.led_subject_group
    if not subject_group:
        abort(403) # หรือ redirect ไปหน้าอื่นพร้อม flash message

    current_semester = Semester.query.filter_by(is_current=True).first()
    # Query Semesters and order them by year descending, then term descending
    all_semesters = Semester.query.join(Semester.academic_year).order_by(Semester.academic_year.has().desc(), Semester.term.desc()).all()


    return render_template(
        'department/assign_teaching.html',
        title=f'มอบหมายการสอน: {subject_group.name}',
        subject_group=subject_group,
        all_semesters=all_semesters,
        current_semester=current_semester
    )

@bp.route('/api/assignments-data')
@login_required
def get_department_assignments_data():
    subject_group = current_user.led_subject_group
    if not subject_group:
        return jsonify({'error': 'Unauthorized'}), 403

    semester_id = request.args.get('semester_id', type=int)
    if not semester_id:
        return jsonify({'error': 'Missing semester_id'}), 400
    
    semester = db.session.get(Semester, semester_id)
    if not semester:
        return jsonify({'error': 'Invalid semester_id'}), 404

    # 1. ดึงข้อมูลหลักสูตรทั้งหมดที่เกี่ยวข้อง
    curriculum_items = Curriculum.query.join(Subject).filter(
        Subject.subject_group_id == subject_group.id,
        Curriculum.semester_id == semester_id
    ).options(
        joinedload(Curriculum.subject),
        joinedload(Curriculum.grade_level)
    ).all()

    # 2. จัดกลุ่มข้อมูลทั้งหมดตามระดับชั้น
    data_by_grade = defaultdict(lambda: {'grade_name': '', 'subjects': set(), 'classrooms': set()})
    for item in curriculum_items:
        grade_id = item.grade_level.id
        data_by_grade[grade_id]['grade_name'] = item.grade_level.name
        data_by_grade[grade_id]['subjects'].add(item.subject)

    # 3. ดึงห้องเรียนสำหรับแต่ละระดับชั้นที่พบ
    grade_level_ids = list(data_by_grade.keys())
    all_classrooms = Classroom.query.filter(
        Classroom.grade_level_id.in_(grade_level_ids),
        Classroom.academic_year_id == semester.academic_year_id
    ).all()
    for room in all_classrooms:
        data_by_grade[room.grade_level_id]['classrooms'].add(room)

    # 4. แปลงข้อมูลให้อยู่ในรูปแบบที่ส่งออกได้
    grades_list = []
    for grade_id, data in data_by_grade.items():
        sorted_subjects = sorted(list(data['subjects']), key=lambda s: s.subject_code)
        sorted_classrooms = sorted(list(data['classrooms']), key=lambda c: c.name)
        grades_list.append({
            'grade_id': grade_id,
            'grade_name': data['grade_name'],
            'subjects': [{'id': s.id, 'code': s.subject_code, 'name': s.name, 'credit': s.credit, 'group_id': s.subject_group_id} for s in sorted_subjects],
            'classrooms': [{'id': c.id, 'name': c.name} for c in sorted_classrooms]
        })
    grades_list.sort(key=lambda g: g['grade_id'])

    # 5. คำนวณภาระงานสอนของครูแต่ละคน
    teachers_in_group = User.query.filter(User.member_of_groups.any(id=subject_group.id)).order_by(User.first_name).distinct().all()
    
    existing_courses = Course.query.filter(Course.semester_id == semester_id).all()
    assignments = {f"{c.subject_id}-{c.classroom_id}": [t.id for t in c.teachers] for c in existing_courses}

    teacher_loads = {}
    for teacher in teachers_in_group:
        courses_taught = Course.query.filter(Course.semester_id == semester_id, Course.teachers.any(id=teacher.id)).join(Course.subject).distinct().all()
        total_credits = sum(c.subject.credit for c in courses_taught)
        teacher_loads[teacher.id] = total_credits

    # ส่งข้อมูลทั้งหมดที่จำเป็นสำหรับ Frontend กลับไป
    return jsonify({
        'data_by_grade': grades_list,
        'teachers_by_group': {
            subject_group.id: [{'id': t.id, 'name': f"{(t.name_prefix or '')}{t.first_name}", 'load': teacher_loads.get(t.id, 0)} for t in teachers_in_group]
        },
        'assignments': assignments
    })

@bp.route('/plan/<int:plan_id>/review', methods=['GET'])
@login_required
def review_plan(plan_id):
    """ แสดงหน้ารายละเอียดแผนการสอน (Read-only) """
    subject_group = current_user.led_subject_group
    if not subject_group:
        abort(403)

    # Eager load ข้อมูลที่เกี่ยวข้องทั้งหมดเพื่อประสิทธิภาพ
    plan = LessonPlan.query.options(
        joinedload(LessonPlan.subject),
        joinedload(LessonPlan.academic_year),
        selectinload(LessonPlan.learning_units).selectinload(LearningUnit.indicators).joinedload(Indicator.standard).joinedload(Standard.learning_strand),
        selectinload(LessonPlan.learning_units).selectinload(LearningUnit.graded_items).joinedload(GradedItem.dimension),
        selectinload(LessonPlan.learning_units).selectinload(LearningUnit.assessment_items).joinedload(AssessmentItem.topic).joinedload(AssessmentTopic.template),
        selectinload(LessonPlan.learning_units).selectinload(LearningUnit.assessment_items).joinedload(AssessmentItem.topic).joinedload(AssessmentTopic.parent)
    ).get_or_404(plan_id)

    # การตรวจสอบความปลอดภัย: เช็คว่าแผนนี้อยู่ในกลุ่มสาระฯ ของผู้ใช้หรือไม่
    if plan.subject.subject_group_id != subject_group.id:
        abort(403)
    
    # Final, correct summary stats calculation for top cards
    total_units = len(plan.learning_units)
    all_graded_items = [item for unit in plan.learning_units for item in unit.graded_items]
    total_periods_from_units = sum(unit.hours for unit in plan.learning_units if unit.hours)

    # คำนวณคาบสอบแยกกันสำหรับกลางภาคและปลายภาค
    midterm_periods = 0
    final_periods = 0

    # ใช้ all_graded_items ที่มีอยู่แล้ว
    if any(item.assessment_type == 'midterm' for item in all_graded_items):
        midterm_periods = (plan.subject.credit or 0) * 2

    if any(item.assessment_type == 'final' for item in all_graded_items):
        final_periods = (plan.subject.credit or 0) * 2

    # รวมคาบทั้งหมด
    total_periods = total_periods_from_units + midterm_periods + final_periods
    total_indicators = sum(len(unit.indicators) for unit in plan.learning_units)

    # Final, correct score calculation logic for summary table
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

    # This entire loop replaces the previous unit processing loop
    for unit in plan.learning_units:
        # Structure indicators first
        indicators_structured_for_unit = defaultdict(lambda: defaultdict(list))
        for indicator in sorted(unit.indicators, key=lambda x: x.code):
            if indicator.standard and indicator.standard.learning_strand:
                strand_name = indicator.standard.learning_strand.name
                standard_obj = indicator.standard
                indicators_structured_for_unit[strand_name][standard_obj].append(indicator)
        unit.indicators_structured = indicators_structured_for_unit

        # Structure assessment topics
        structured_topics = defaultdict(dict)
        items_by_parent = defaultdict(list)
        unique_topics = {item.topic for item in unit.assessment_items if item.topic}
        for topic in unique_topics:
            items_by_parent[topic.parent_id].append(topic)
        for parent_id, children in items_by_parent.items():
            if parent_id is None:
                for parent_topic in children:
                    if parent_topic.template:
                        template_name = parent_topic.template.name
                        child_topics = sorted(items_by_parent.get(parent_topic.id, []), key=lambda t: t.name)
                        structured_topics[template_name][parent_topic] = child_topics
            elif parent_id not in {p.id for p_list in items_by_parent.values() for p in p_list if p.parent_id is None}:
                parent_topic = db.session.get(AssessmentTopic, parent_id)
                if parent_topic and parent_topic.template:
                    template_name = parent_topic.template.name
                    if parent_topic not in structured_topics[template_name]:
                        structured_topics[template_name][parent_topic] = sorted(children, key=lambda t: t.name)
        unit.structured_topics = structured_topics

        display_components = []
        # 1. Indicators
        if unit.indicators_structured:
            display_components.append({'type': 'indicators', 'title': 'มาตรฐานการเรียนรู้/ตัวชี้วัด', 'data': unit.indicators_structured})
        # 2. Core Concepts
        if unit.core_concepts:
            display_components.append({'type': 'content', 'title': 'สาระสำคัญ', 'data': unit.core_concepts})
        # 3. Learning Objectives
        if unit.learning_objectives:
            display_components.append({'type': 'content', 'title': 'จุดประสงค์การเรียนรู้', 'data': unit.learning_objectives})
        # 4. Learning Content
        if unit.learning_content:
            display_components.append({'type': 'content', 'title': 'สาระการเรียนรู้', 'data': unit.learning_content})
        # 5. Learning Activities
        if unit.learning_activities:
            display_components.append({'type': 'content', 'title': 'กิจกรรมการเรียนรู้', 'data': unit.learning_activities})
        # 6. Media/Resources
        if unit.media_sources:
            display_components.append({'type': 'content', 'title': 'สื่อ/แหล่งการเรียนรู้', 'data': unit.media_sources})
        # 7. Assessment Topics
        if unit.structured_topics:
            display_components.append({'type': 'assessment_topics', 'title': 'หัวข้อประเมินจากแม่แบบ', 'data': unit.structured_topics})
        # 8. Graded Items
        formative_items = [item for item in unit.graded_items if item.assessment_type == 'formative']
        if formative_items:
            display_components.append({'type': 'graded_items', 'title': 'รายการคะแนนเก็บ', 'data': formative_items})
        unit.display_components = display_components

    approve_button_text = "ผ่านการตรวจและเสนอขึ้นไป"
    approve_action_url = url_for('department.approve_plan', plan_id=plan.id)

    # Final, correct return statement
    return render_template('department/review_plan.html',
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

@bp.route('/plan/<int:plan_id>/forward', methods=['POST'])
@login_required
def forward_plan(plan_id):
    plan = LessonPlan.query.get_or_404(plan_id)
    # Security Check
    if not current_user.led_subject_group or plan.subject.subject_group_id != current_user.led_subject_group.id:
        abort(403)
    
    plan.status = 'เสนอฝ่ายวิชาการ'
    db.session.commit()
    flash(f'แผนการสอนสำหรับวิชา "{plan.subject.name}" ได้ผ่านการตรวจสอบแล้ว', 'success')
    return redirect(url_for('department.dashboard'))

# Mission 4: Routes สำหรับ Approve และ Reject (ตามพรอมต์ที่ให้มา)
bp.route('/plan/<int:plan_id>/approve', methods=['POST']) # This forwards to Academic
@login_required
def approve_plan(plan_id): # Renaming might be clearer, e.g., forward_plan_to_academic
    plan = LessonPlan.query.get_or_404(plan_id)
    # Security Check
    subject_group = current_user.led_subject_group
    if not subject_group or plan.subject.subject_group_id != subject_group.id:
        abort(403)

    original_status = plan.status
    new_status = 'เสนอฝ่ายวิชาการ'

    # Add status check? Should be 'รอการตรวจสอบ'
    if original_status != 'รอการตรวจสอบ':
         flash(f'แผนไม่อยู่ในสถานะ "{original_status}" ไม่สามารถส่งต่อได้', 'warning')
         return redirect(url_for('department.review_plan', plan_id=plan_id)) # Redirect back to review

    try:
        plan.status = new_status
        # --- Log Action ---
        log_action(
            "Forward Lesson Plan to Academic", model=LessonPlan, record_id=plan.id,
            old_value=original_status, new_value=new_status
        )
        db.session.commit()
        flash(f'แผนการสอนสำหรับวิชา "{plan.subject.name}" ได้ผ่านการตรวจสอบและส่งต่อให้ฝ่ายวิชาการแล้ว', 'success')
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Error forwarding plan {plan_id} to academic: {e}", exc_info=True)
        # --- Log Failure ---
        log_action(f"Forward Lesson Plan Failed: {type(e).__name__}", model=LessonPlan, record_id=plan.id, old_value=original_status, new_value=new_status)
        try: db.session.commit()
        except: db.session.rollback()
        flash(f'เกิดข้อผิดพลาดในการส่งต่อแผน: {e}', 'danger')

    return redirect(url_for('department.dashboard'))

@bp.route('/plan/<int:plan_id>/reject', methods=['POST']) # This returns to teacher
@login_required
def reject_plan(plan_id):
    plan = LessonPlan.query.get_or_404(plan_id)
    # Security Check
    subject_group = current_user.led_subject_group
    if not subject_group or plan.subject.subject_group_id != subject_group.id:
        abort(403)

    revision_notes = request.form.get('revision_notes', 'ส่งกลับเพื่อแก้ไขจาก หน.กลุ่มสาระ')
    original_status = plan.status
    new_status = 'ต้องการการแก้ไข'

    try:
        plan.status = new_status
        plan.revision_notes = revision_notes
        # --- Log Action ---
        log_action(
            "Return Lesson Plan to Teacher (Dept Head)", model=LessonPlan, record_id=plan.id,
            old_value=original_status, new_value={'status': new_status, 'notes': revision_notes}
        )
        db.session.commit()
        flash(f'แผนการสอนสำหรับวิชา "{plan.subject.name}" ถูกส่งกลับเพื่อแก้ไขเรียบร้อยแล้ว', 'warning')
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Error returning plan {plan_id} from dept head: {e}", exc_info=True)
        # --- Log Failure ---
        log_action(f"Return Lesson Plan Failed (Dept Head): {type(e).__name__}", model=LessonPlan, record_id=plan.id, old_value=original_status, new_value={'status': new_status})
        try: db.session.commit()
        except: db.session.rollback()
        flash(f'เกิดข้อผิดพลาดในการส่งแผนกลับ: {e}', 'danger')

    return redirect(url_for('department.dashboard'))

@bp.route('/review-grades/<int:course_id>', methods=['GET'])
@login_required
def review_course_grades(course_id):
    # Security Check
    subject_group = current_user.led_subject_group
    course = Course.query.options(joinedload(Course.subject)).get_or_404(course_id)
    if not subject_group or course.subject.subject_group_id != subject_group.id:
        abort(403)

    student_grades, max_scores = calculate_final_grades_for_course(course)
    form = FlaskForm() # สำหรับ CSRF token ในปุ่ม approve/reject

    return render_template('department/review_course_grades.html',
                           title=f"ตรวจสอบผลการเรียน: {course.subject.name}",
                           course=course,
                           student_grades=student_grades,
                           max_scores=max_scores,
                           form=form)

@bp.route('/approve-grades/<int:course_id>', methods=['POST'])
@login_required
def approve_grades(course_id): # Forwards grades to Academic
    # Security Check
    subject_group = current_user.led_subject_group
    course = Course.query.get_or_404(course_id)
    if not subject_group or course.subject.subject_group_id != subject_group.id:
        abort(403)

    form = FlaskForm()
    if form.validate_on_submit():
        original_status = course.grade_submission_status
        new_status = 'เสนอฝ่ายวิชาการ'

        # Add status check? Should be 'รอตรวจสอบ (หน.กลุ่มสาระ)'
        if original_status != 'รอตรวจสอบ (หน.กลุ่มสาระ)':
            flash(f'ผลการเรียนไม่อยู่ในสถานะ "{original_status}" ไม่สามารถส่งต่อได้', 'warning')
            return redirect(url_for('department.review_course_grades', course_id=course_id))

        try:
            course.grade_submission_status = new_status
            # --- Log Action ---
            log_action(
                "Forward Grades to Academic (Dept Head)", model=Course, record_id=course.id,
                old_value=original_status, new_value=new_status
            )
            # TODO: Add notification for Academic Affairs
            db.session.commit()
            flash(f'อนุมัติและส่งต่อผลการเรียนวิชา {course.subject.name} ให้ฝ่ายวิชาการเรียบร้อยแล้ว', 'success')
        except Exception as e:
            db.session.rollback()
            current_app.logger.error(f"Error forwarding grades for course {course_id}: {e}", exc_info=True)
            # --- Log Failure ---
            log_action(f"Forward Grades Failed (Dept Head): {type(e).__name__}", model=Course, record_id=course.id, old_value=original_status, new_value=new_status)
            try: db.session.commit()
            except: db.session.rollback()
            flash(f'เกิดข้อผิดพลาดในการส่งต่อผลการเรียน: {e}', 'danger')

    return redirect(url_for('department.dashboard')) # Redirect to dashboard

@bp.route('/return-grades/<int:course_id>', methods=['POST'])
@login_required
def return_grades_for_revision(course_id): # Returns grades to Teacher
    # Security Check
    subject_group = current_user.led_subject_group
    course = Course.query.get_or_404(course_id)
    if not subject_group or course.subject.subject_group_id != subject_group.id:
        abort(403)

    form = FlaskForm()
    if form.validate_on_submit():
        notes = request.form.get('revision_notes', 'กรุณาตรวจสอบความถูกต้องของข้อมูล (จาก หน.กลุ่มสาระ)')
        original_status = course.grade_submission_status
        new_status = 'ต้องการการแก้ไข'

        try:
            course.grade_submission_status = new_status
            course.grade_submission_notes = notes
            # --- Log Action ---
            log_action(
                "Return Grades to Teacher (Dept Head)", model=Course, record_id=course.id,
                old_value=original_status, new_value={'status': new_status, 'notes': notes}
            )
            # TODO: Add notification for the teacher(s)
            db.session.commit()
            flash(f'ส่งผลการเรียนวิชา {course.subject.name} กลับเพื่อแก้ไขเรียบร้อยแล้ว', 'warning')
        except Exception as e:
            db.session.rollback()
            current_app.logger.error(f"Error returning grades for course {course_id}: {e}", exc_info=True)
            # --- Log Failure ---
            log_action(f"Return Grades Failed (Dept Head): {type(e).__name__}", model=Course, record_id=course.id, old_value=original_status, new_value={'status': new_status})
            try: db.session.commit()
            except: db.session.rollback()
            flash(f'เกิดข้อผิดพลาดในการส่งผลการเรียนกลับ: {e}', 'danger')

    return redirect(url_for('department.dashboard')) # Redirect to dashboard

@bp.route('/level-overview/<string:level_group>')
@login_required
def level_overview(level_group):
    subject_group = current_user.led_subject_group
    if not subject_group:
        abort(403)

    current_semester = Semester.query.filter_by(is_current=True).first_or_404()

    if level_group == 'm-ton':
        title = "ภาพรวม มัธยมศึกษาตอนต้น"
    elif level_group == 'm-plai':
        title = "ภาพรวม มัธยมศึกษาตอนปลาย"
    else:
        abort(404)

    # 1. Get all grade levels for this specific level group
    grade_levels_in_group = [gl for gl in GradeLevel.query.order_by(GradeLevel.id).all() if gl.level_group == level_group]
    grade_level_ids = [gl.id for gl in grade_levels_in_group]

    # 2. Fetch ALL courses for the level group as the single source of truth
    all_courses_in_level_group = Course.query.join(Subject).join(Classroom).filter(
        Course.semester_id == current_semester.id,
        Subject.subject_group_id == subject_group.id,
        Classroom.grade_level_id.in_(grade_level_ids)
    ).options(
        joinedload(Course.subject),
        joinedload(Course.classroom),
        joinedload(Course.submitted_by) # Eager load for the pending list
    ).all()

    # 3. Now, derive the specific lists from the master list
    submitted_courses_list = [c for c in all_courses_in_level_group if c.grade_submission_status not in ['ยังไม่ส่ง', 'pending']]
    grades_pending_review = [c for c in all_courses_in_level_group if c.grade_submission_status == 'รอตรวจสอบ (หน.กลุ่มสาระ)']
    form = FlaskForm()

    # 2. Re-use the same statistics processing function
    def process_stats(grade_list):
        if not grade_list: return None
        stats = {}
        valid_grades_list = [g for g in grade_list if g is not None and g != '']
        total_students = len(valid_grades_list)

        if total_students == 0: return None

        grade_counts = Counter(valid_grades_list)
        stats['grade_distribution'] = {str(g): grade_counts.get(str(g), 0) for g in ['4','3.5','3','2.5','2','1.5','1','0','ร','มส']}

        # Grade percentages
        grade_percentages = {}
        if total_students > 0:
            for grade, count in stats['grade_distribution'].items():
                grade_percentages[grade] = (count / total_students) * 100
        stats['grade_percentages'] = grade_percentages

        valid_grades_for_gpa = [float(g) for g in valid_grades_list if g not in ['ร', 'มส']]
        stats['gpa'] = np.mean(valid_grades_for_gpa) if valid_grades_for_gpa else 0
        stats['sd'] = np.std(valid_grades_for_gpa, ddof=1) if len(valid_grades_for_gpa) > 1 else 0

        stats['failed_count'] = grade_counts.get('0', 0) + grade_counts.get('ร', 0) + grade_counts.get('มส', 0)
        stats['passed_count'] = sum(grade_counts.get(str(g), 0) for g in ['4','3.5','3','2.5','2','1.5','1'])
        stats['good_excellent_count'] = sum(grade_counts.get(str(g), 0) for g in ['4','3.5','3'])

        stats['failed_percent'] = (stats['failed_count'] / total_students) * 100 if total_students > 0 else 0
        stats['passed_percent'] = (stats['passed_count'] / total_students) * 100 if total_students > 0 else 0
        stats['good_excellent_percent'] = (stats['good_excellent_count'] / total_students) * 100 if total_students > 0 else 0

        stats['total_students'] = total_students
        return stats

    # 3. [CORRECTED] Aggregate grades by grade level for the main table
    grades_by_grade_level = defaultdict(list)
    all_student_final_data = [] # Still needed for overall stats

    for course in submitted_courses_list:
        student_grades, _ = calculate_final_grades_for_course(course)
        all_student_final_data.extend(student_grades)
        grade_level = course.classroom.grade_level
        grades = [data['grade'] for data in student_grades]
        grades_by_grade_level[grade_level].extend(grades)

    grade_level_summary_stats = []
    sorted_grade_levels = sorted(grades_by_grade_level.keys(), key=lambda gl: gl.id)

    for gl in sorted_grade_levels:
        aggregated_grades = grades_by_grade_level[gl]
        stats = process_stats(aggregated_grades)
        if stats:
            grade_level_summary_stats.append({
                'grade_level': gl,
                'stats': stats
            })

    overall_grades = [data['grade'] for data in all_student_final_data]
    overall_stats = process_stats(overall_grades)

    chart_data = None
    if overall_stats and overall_stats.get('total_students', 0) > 0:
        chart_labels = ['4','3.5','3','2.5','2','1.5','1','0','ร','มส']
        chart_values = [overall_stats.get('grade_distribution', {}).get(label, 0) for label in chart_labels]
        chart_data = {'labels': chart_labels, 'data': chart_values}

    # 4. [CORRECTED LOGIC - FINAL] Calculate true progress for the bottom cards
    progress_by_grade = {}
    for gl in grade_levels_in_group:
        # Query for the TRUE total number of courses for this specific grade level
        total_courses_in_grade = Course.query.join(Subject).join(Classroom).filter(
            Course.semester_id == current_semester.id,
            Subject.subject_group_id == subject_group.id,
            Classroom.grade_level_id == gl.id
        ).count()

        # Query for the number of SUBMITTED courses for this specific grade level
        submitted_courses_in_grade = Course.query.join(Subject).join(Classroom).filter(
            Course.semester_id == current_semester.id,
            Subject.subject_group_id == subject_group.id,
            Classroom.grade_level_id == gl.id,
            Course.grade_submission_status.notin_(['ยังไม่ส่ง', 'pending'])
        ).count()

        percentage = (submitted_courses_in_grade / total_courses_in_grade * 100) if total_courses_in_grade > 0 else 0

        progress_by_grade[gl.id] = {
            'grade_level_name': gl.name,
            'total': total_courses_in_grade,
            'submitted': submitted_courses_in_grade,
            'percentage': percentage
        }

    form = FlaskForm()
    grades_pending_review = [c for c in all_courses_in_level_group if c.grade_submission_status == 'รอตรวจสอบ (หน.กลุ่มสาระ)']        

    return render_template('department/level_overview.html',
                           title=title,
                           form=form,
                           grades_pending_review=grades_pending_review,
                           level_group=level_group,
                           grade_levels=grade_levels_in_group,
                           progress_by_grade=progress_by_grade,
                           overall_stats=overall_stats,
                           chart_data=chart_data,
                           grade_level_summary_stats=grade_level_summary_stats,
                           subject_group=subject_group)

@bp.route('/grade-level-detail/<int:grade_level_id>')
@login_required
def grade_level_detail(grade_level_id):
    subject_group = current_user.led_subject_group
    grade_level = GradeLevel.query.get_or_404(grade_level_id)
    if not subject_group or grade_level.level_group not in ['m-ton', 'm-plai'] or subject_group.id != Course.query.join(Subject).join(Classroom).filter(Classroom.grade_level_id == grade_level_id).first().subject.subject_group_id:
        abort(403)

    current_semester = Semester.query.filter_by(is_current=True).first_or_404()
    title = f"ภาพรวมระดับชั้น {grade_level.name}"

    submitted_courses = Course.query.join(Subject).join(Classroom).filter(
        Course.semester_id == current_semester.id,
        Subject.subject_group_id == subject_group.id,
        Classroom.grade_level_id == grade_level_id,
        Course.grade_submission_status.notin_(['ยังไม่ส่ง', 'pending'])
    ).options(
        joinedload(Course.subject),
        joinedload(Course.classroom),
        joinedload(Course.teachers)
    ).all()

    # Re-use the same statistics processing function
    def process_stats(grade_list):
        if not grade_list: return None
        stats = {}
        valid_grades_list = [g for g in grade_list if g is not None and g != '']
        total_students = len(valid_grades_list)
        if total_students == 0: return None
        grade_counts = Counter(valid_grades_list)
        stats['grade_distribution'] = {str(g): grade_counts.get(str(g), 0) for g in ['4','3.5','3','2.5','2','1.5','1','0','ร','มส']}

        # Grade percentages
        grade_percentages = {}
        if total_students > 0:
            for grade, count in stats['grade_distribution'].items():
                grade_percentages[grade] = (count / total_students) * 100
        stats['grade_percentages'] = grade_percentages

        valid_grades_for_gpa = [float(g) for g in valid_grades_list if g not in ['ร', 'มส']]
        stats['gpa'] = np.mean(valid_grades_for_gpa) if valid_grades_for_gpa else 0
        stats['sd'] = np.std(valid_grades_for_gpa, ddof=1) if len(valid_grades_for_gpa) > 1 else 0
        stats['failed_count'] = grade_counts.get('0', 0) + grade_counts.get('ร', 0) + grade_counts.get('มส', 0)
        stats['passed_count'] = sum(grade_counts.get(str(g), 0) for g in ['4','3.5','3','2.5','2','1.5','1'])
        stats['good_excellent_count'] = sum(grade_counts.get(str(g), 0) for g in ['4','3.5','3'])
        stats['failed_percent'] = (stats['failed_count'] / total_students) * 100 if total_students > 0 else 0
        stats['passed_percent'] = (stats['passed_count'] / total_students) * 100 if total_students > 0 else 0
        stats['good_excellent_percent'] = (stats['good_excellent_count'] / total_students) * 100 if total_students > 0 else 0
        stats['total_students'] = total_students
        return stats

    # [REVISED] Aggregate grades and teachers by SUBJECT
    grades_by_subject = defaultdict(list)
    teachers_by_subject = defaultdict(set)
    all_student_final_data = []

    for course in submitted_courses:
        student_grades, _ = calculate_final_grades_for_course(course)
        all_student_final_data.extend(student_grades)
        subject = course.subject
        grades = [data['grade'] for data in student_grades]
        grades_by_subject[subject].extend(grades)
        for teacher in course.teachers:
            teachers_by_subject[subject].add(teacher.full_name)

    subject_summary_stats = []
    sorted_subjects = sorted(grades_by_subject.keys(), key=lambda s: s.subject_code)

    for subject in sorted_subjects:
        aggregated_grades = grades_by_subject[subject]
        stats = process_stats(aggregated_grades)
        if stats:
            subject_summary_stats.append({
                'subject': subject,
                'stats': stats,
                'teachers_str': ', '.join(sorted(list(teachers_by_subject[subject])))
            })

    overall_grades = [data['grade'] for data in all_student_final_data]
    overall_stats = process_stats(overall_grades)

    chart_data = None
    if overall_stats:
        chart_labels = ['4','3.5','3','2.5','2','1.5','1','0','ร','มส']
        chart_values = [overall_stats.get('grade_distribution', {}).get(label, 0) for label in chart_labels]
        chart_data = {'labels': chart_labels, 'data': chart_values}

    form = FlaskForm()
    grades_pending_review = [c for c in submitted_courses if c.grade_submission_status == 'รอตรวจสอบ (หน.กลุ่มสาระ)']

    return render_template('department/grade_level_detail.html',
                           title=title,
                           form=form,
                           grades_pending_review=grades_pending_review,
                           grade_level=grade_level,
                           subject_summary_stats=subject_summary_stats,
                           overall_stats=overall_stats,
                           chart_data=chart_data)

@bp.route('/submit-level-grades/<string:level_group>', methods=['POST'])
@login_required
def submit_level_grades(level_group): # Submits 'รอตรวจสอบ' grades for a level group
    subject_group = current_user.led_subject_group
    if not subject_group: abort(403)
    form = FlaskForm()
    if form.validate_on_submit():
        current_semester = Semester.query.filter_by(is_current=True).first_or_404()
        grade_levels_in_group = [gl for gl in GradeLevel.query.all() if gl.level_group == level_group]
        grade_level_ids = [gl.id for gl in grade_levels_in_group]

        courses_to_submit_q = Course.query.join(Subject).join(Classroom).filter(
            Course.semester_id == current_semester.id,
            Subject.subject_group_id == subject_group.id,
            Classroom.grade_level_id.in_(grade_level_ids),
            Course.grade_submission_status == 'รอตรวจสอบ (หน.กลุ่มสาระ)'
        )
        courses_to_submit = courses_to_submit_q.options(db.load_only(Course.id)).all() # Get IDs for logging
        course_ids = [c.id for c in courses_to_submit]

        if not courses_to_submit:
            flash('ไม่พบผลการเรียนที่รอการตรวจสอบเพื่อส่งต่อ', 'warning')
        else:
            try:
                # Bulk update
                updated_count = courses_to_submit_q.update(
                    {'grade_submission_status': 'เสนอฝ่ายวิชาการ'},
                    synchronize_session=False
                )
                # --- Log Bulk Action ---
                log_action(
                    f"Forward Level Grades ({level_group}) to Academic (Bulk)", model=Course,
                    new_value={'count': updated_count, 'level_group': level_group, 'new_status': 'เสนอฝ่ายวิชาการ'},
                    old_value={'old_status': 'รอตรวจสอบ (หน.กลุ่มสาระ)'}
                )
                db.session.commit()
                # TODO: Add notification for Academic Affairs
                flash(f'ส่งต่อผลการเรียน {updated_count} รายวิชา ({level_group}) ให้ฝ่ายวิชาการเรียบร้อยแล้ว', 'success')
            except Exception as e:
                db.session.rollback()
                current_app.logger.error(f"Error submitting level grades for {level_group}: {e}", exc_info=True)
                log_action(f"Forward Level Grades Failed: {type(e).__name__}", model=Course, new_value={'level_group': level_group})
                try: db.session.commit()
                except: db.session.rollback()
                flash(f'เกิดข้อผิดพลาดในการส่งต่อผลการเรียน: {e}', 'danger')

    return redirect(url_for('department.level_overview', level_group=level_group))

@bp.route('/submit-grade-level-grades/<int:grade_level_id>', methods=['POST'])
@login_required
def submit_grade_level_grades(grade_level_id):
    subject_group = current_user.led_subject_group
    if not subject_group:
        abort(403)

    form = FlaskForm()
    if form.validate_on_submit():
        current_semester = Semester.query.filter_by(is_current=True).first_or_404()
        courses_to_submit = Course.query.join(Subject).join(Classroom).filter(
            Course.semester_id == current_semester.id,
            Subject.subject_group_id == subject_group.id,
            Classroom.grade_level_id == grade_level_id,
            Course.grade_submission_status == 'รอตรวจสอบ (หน.กลุ่มสาระ)'
        ).all()

        if not courses_to_submit:
            flash('ไม่พบผลการเรียนที่รอการตรวจสอบเพื่อส่งต่อ', 'warning')
        else:
            for course in courses_to_submit:
                course.grade_submission_status = 'เสนอฝ่ายวิชาการ'
            db.session.commit()
            flash(f'ส่งต่อผลการเรียนจำนวน {len(courses_to_submit)} รายวิชาให้ฝ่ายวิชาการเรียบร้อยแล้ว', 'success')

    return redirect(url_for('department.grade_level_detail', grade_level_id=grade_level_id))

@bp.route('/submit-all-grades', methods=['POST'])
@login_required
def submit_all_grades_to_academic():
    subject_group = current_user.led_subject_group
    if not subject_group:
        abort(403)

    current_semester = Semester.query.filter_by(is_current=True).first_or_404()
    form = FlaskForm()
    
    if form.validate_on_submit():
        courses_to_submit = Course.query.join(Subject).filter(
            Course.semester_id == current_semester.id,
            Subject.subject_group_id == subject_group.id,
            Course.grade_submission_status == 'รอตรวจสอบ (หน.กลุ่มสาระ)'
        ).all()

        if not courses_to_submit:
            flash('ไม่พบผลการเรียนที่รอการตรวจสอบเพื่อส่งต่อ', 'warning')
            return redirect(url_for('department.dashboard'))

        for course in courses_to_submit:
            course.grade_submission_status = 'เสนอฝ่ายวิชาการ'
        
        db.session.commit()
        # TODO: Add notification for Academic Affairs
        flash(f'ส่งต่อผลการเรียนจำนวน {len(courses_to_submit)} รายวิชาให้ฝ่ายวิชาการเรียบร้อยแล้ว', 'success')

    return redirect(url_for('department.dashboard'))

@bp.route('/subject-detail/<int:grade_level_id>/<int:subject_id>')
@login_required
def subject_detail(grade_level_id, subject_id):
    # Basic security and object fetching
    subject_group = current_user.led_subject_group
    grade_level = GradeLevel.query.get_or_404(grade_level_id)
    subject = Subject.query.get_or_404(subject_id)
    if not subject_group or subject.subject_group_id != subject_group.id:
        abort(403)

    current_semester = Semester.query.filter_by(is_current=True).first_or_404()

    # Get all submitted courses for this specific subject and grade level
    submitted_courses = Course.query.join(Classroom).filter(
        Course.semester_id == current_semester.id,
        Course.subject_id == subject_id,
        Classroom.grade_level_id == grade_level_id,
        Course.grade_submission_status.notin_(['ยังไม่ส่ง', 'pending'])
    ).options(
        joinedload(Course.classroom),
        joinedload(Course.teachers),
    ).order_by(Course.classroom.has(Classroom.name)).all()

    # Get all student data and max scores for each course
    courses_with_data = []
    for course in submitted_courses:
        student_grades, max_scores = calculate_final_grades_for_course(course)
        courses_with_data.append({
            'course': course,
            'student_grades': student_grades,
            'max_scores': max_scores
        })

    return render_template('department/subject_detail.html',
                           title=f"รายละเอียดวิชา {subject.name} ({grade_level.name})",
                           subject=subject,
                           grade_level=grade_level,
                           courses_with_data=courses_with_data)

@bp.route('/subject-summary/<int:subject_id>/<int:semester_id>')
@login_required
def view_subject_summary_dept(subject_id, semester_id):
    # Security and Data Fetching
    subject_group = current_user.led_subject_group
    subject = Subject.query.get_or_404(subject_id)
    semester = Semester.query.get_or_404(semester_id)
    grade_level_id = request.args.get('grade_level_id', type=int)
    grade_level = GradeLevel.query.get_or_404(grade_level_id) if grade_level_id else None
    if not subject_group or subject.subject_group_id != subject_group.id:
        abort(403)

    # Build the base query
    courses_query = Course.query.filter(
        Course.subject_id == subject.id,
        Course.semester_id == semester.id,
        Course.grade_submission_status.notin_(['ยังไม่ส่ง', 'pending'])
    )

    # Apply grade level filter if it exists
    if grade_level:
        courses_query = courses_query.join(Course.classroom).filter(
            Classroom.grade_level_id == grade_level.id
        )

    # Execute the final query
    courses = courses_query.options(
        joinedload(Course.classroom),
        joinedload(Course.teachers)
    ).order_by(Course.classroom.has(Classroom.name)).all()

    if not courses:
        abort(404)

    # --- Advanced Statistics Processing ---
    def process_advanced_stats(student_grades_list, grand_max_score):
        if not student_grades_list: return None
        stats = {}
        all_grades = [data['grade'] for data in student_grades_list if data['grade'] is not None and data['grade'] != '']
        total_students = len(all_grades)
        if total_students == 0: return None

        # Grade distribution and basic stats
        grade_counts = Counter(all_grades)
        stats['grade_distribution'] = {str(g): grade_counts.get(str(g), 0) for g in ['4','3.5','3','2.5','2','1.5','1','0','ร','มส']}

        # Grade percentages
        grade_percentages = {}
        if total_students > 0:
            for grade, count in stats['grade_distribution'].items():
                grade_percentages[grade] = (count / total_students) * 100
        stats['grade_percentages'] = grade_percentages

        # GPA, SD
        valid_grades_for_gpa = [float(g) for g in all_grades if g not in ['ร', 'มส']]
        stats['gpa'] = np.mean(valid_grades_for_gpa) if valid_grades_for_gpa else 0
        stats['sd'] = np.std(valid_grades_for_gpa, ddof=1) if len(valid_grades_for_gpa) > 1 else 0

        # Counts and Percentages
        stats['failed_count'] = grade_counts.get('0', 0) + grade_counts.get('ร', 0) + grade_counts.get('มส', 0)
        stats['passed_count'] = sum(grade_counts.get(str(g), 0) for g in ['4','3.5','3','2.5','2','1.5','1'])
        stats['good_excellent_count'] = sum(grade_counts.get(str(g), 0) for g in ['4','3.5','3'])
        stats['failed_percent'] = (stats['failed_count'] / total_students) * 100 if total_students > 0 else 0
        stats['passed_percent'] = (stats['passed_count'] / total_students) * 100 if total_students > 0 else 0
        stats['good_excellent_percent'] = (stats['good_excellent_count'] / total_students) * 100 if total_students > 0 else 0
        stats['total_students'] = total_students

        # Min/Max Scores
        all_total_scores = [data['total_score'] for data in student_grades_list]
        stats['min_score'] = min(all_total_scores) if all_total_scores else 0
        stats['max_score'] = max(all_total_scores) if all_total_scores else 0
        return stats

    # --- Data Aggregation ---
    summary_data = {'by_classroom': {}, 'overall': {'grades': []}}
    grand_max_score = 0

    for course in courses:
        student_grades, max_scores = calculate_final_grades_for_course(course)
        summary_data['by_classroom'][course.classroom.id] = {
            'name': course.classroom.name,
            'grades': student_grades,
            'stats': process_advanced_stats(student_grades, max_scores.get('grand_total', 0))
        }
        summary_data['overall']['grades'].extend(student_grades)
        if max_scores.get('grand_total', 0) > grand_max_score:
            grand_max_score = max_scores.get('grand_total', 0)

    summary_data['overall']['stats'] = process_advanced_stats(summary_data['overall']['grades'], grand_max_score)

    # Chart Data
    chart_labels = ['4','3.5','3','2.5','2','1.5','1','0','ร','มส']
    chart_values = [summary_data['overall']['stats']['grade_distribution'].get(label, 0) for label in chart_labels]
    summary_data['chart_data'] = {'labels': chart_labels, 'data': chart_values}

    all_teachers = sorted(list(set(teacher for course in courses for teacher in course.teachers)), key=lambda t: t.full_name)


    return render_template('department/subject_summary_dept.html',
                           title=f"สรุปผลการเรียนวิชา {subject.name}",
                           subject=subject,
                           semester=semester,
                           summary_data=summary_data,
                           courses_count=len(courses),
                           all_teachers=all_teachers,
                           grade_level=grade_level,
                           g_current_semester=semester,                           
                           grand_max_score=grand_max_score)

@bp.route('/remediation-overview')
@login_required
def remediation_overview():
    if not current_user.led_subject_group:
        abort(403)

    semester = Semester.query.filter_by(is_current=True).first_or_404()
    subject_group = current_user.led_subject_group

    course_ids_in_group = db.session.query(Course.id).join(Subject).filter(
        Course.semester_id == semester.id,
        Subject.subject_group_id == subject_group.id
    ).scalar_subquery()

    # --- THE FIX IS HERE: Explicitly list all statuses to ensure no one is missed ---
    all_grades_in_process_q = db.session.query(CourseGrade, Enrollment).join(
        Course, CourseGrade.course_id == Course.id
    ).join(
        Enrollment, and_(
            CourseGrade.student_id == Enrollment.student_id,
            Course.classroom_id == Enrollment.classroom_id
        )
    ).filter(
        CourseGrade.course_id.in_(course_ids_in_group),
        or_(
            CourseGrade.final_grade.in_(['0', 'ร', 'มส']),
            CourseGrade.remediation_status.in_([
                'In Progress', 'Completed', 'Submitted to Dept. Head',
                'Submitted to Academic Affairs', 'Pending Director Approval', 'Approved'
            ])
        )
    ).options(
        joinedload(CourseGrade.student),
        joinedload(CourseGrade.course).joinedload(Course.subject),
        joinedload(CourseGrade.course).joinedload(Course.classroom)
    ).all()

    # --- Grouping logic remains the same, but now receives complete data ---
    submitted_students, forwarded_students, awaiting_remediation_students = [], [], []

    for grade_obj, enrollment_obj in all_grades_in_process_q:
        item_tuple = (grade_obj, enrollment_obj)
        if grade_obj.remediation_status == 'Submitted to Dept. Head':
            submitted_students.append(item_tuple)
        elif grade_obj.remediation_status in ['Submitted to Academic Affairs', 'Pending Director Approval', 'Approved']:
            forwarded_students.append(item_tuple)
        else:
            awaiting_remediation_students.append(item_tuple)

    total_submitted = len(submitted_students)
    total_forwarded = len(forwarded_students)
    total_awaiting = len(awaiting_remediation_students)
    total_all = total_submitted + total_forwarded + total_awaiting
    
    stats = {
        'submitted_for_approval': total_submitted,
        'forwarded': total_forwarded,
        'awaiting_teacher_action': total_awaiting,
        'total': total_all,
        'percent_submitted': (total_submitted / total_all * 100) if total_all > 0 else 0,
        'percent_forwarded': (total_forwarded / total_all * 100) if total_all > 0 else 0,
        'percent_awaiting': (total_awaiting / total_all * 100) if total_all > 0 else 0
    }

    return render_template('department/remediation_overview.html',
                           title="ตรวจสอบผลการซ่อม",
                           semester=semester,
                           stats=stats,
                           submitted_students=submitted_students,
                           forwarded_students=forwarded_students,
                           awaiting_remediation_students=awaiting_remediation_students)

@bp.route('/remediation/forward-all', methods=['POST'])
@login_required
def forward_remediation_to_academic():
    if not current_user.led_subject_group: abort(403)
    semester = Semester.query.filter_by(is_current=True).first_or_404()
    subject_group = current_user.led_subject_group

    course_ids_in_group = db.session.query(Course.id).join(Subject).filter(
        Course.semester_id == semester.id,
        Subject.subject_group_id == subject_group.id
    ).scalar_subquery()

    # Get IDs before update for logging
    records_to_update = CourseGrade.query.filter(
        CourseGrade.course_id.in_(course_ids_in_group),
        CourseGrade.remediation_status == 'Submitted to Dept. Head'
    ).options(db.load_only(CourseGrade.id)).all()

    if not records_to_update:
         return jsonify({'status': 'info', 'message': 'ไม่พบผลการซ่อมที่รอการส่งต่อ'}), 200

    record_ids = [r.id for r in records_to_update]
    new_status = 'Submitted to Academic Affairs'
    old_status = 'Submitted to Dept. Head'

    try:
        updated_count = CourseGrade.query.filter(
            CourseGrade.id.in_(record_ids)
        ).update({'remediation_status': new_status}, synchronize_session=False)

        # --- Log Bulk Action ---
        log_action(
            "Forward Remediation to Academic (Bulk)", model=CourseGrade,
            new_value={'count': updated_count, 'group_id': subject_group.id, 'new_status': new_status},
            old_value={'old_status': old_status}
        )
        db.session.commit()
        # TODO: Add Notification for Academic Affairs
        return jsonify({
            'status': 'success',
            'message': f'ส่งต่อผลการซ่อมของนักเรียน {updated_count} คนให้ฝ่ายวิชาการเรียบร้อยแล้ว'
        })
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Error forwarding dept remediation: {e}", exc_info=True)
        # --- Log Failure ---
        log_action(f"Forward Dept Remediation Failed: {type(e).__name__}", model=CourseGrade, new_value={'group_id': subject_group.id})
        try: db.session.commit()
        except: db.session.rollback()
        return jsonify({'status': 'error', 'message': f'เกิดข้อผิดพลาด: {e}'}), 500