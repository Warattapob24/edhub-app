#app/director/routes.py
from datetime import date, datetime
from statistics import StatisticsError, mode
from flask import current_app, jsonify, render_template, abort, flash, redirect, request, url_for
from flask_login import login_required, current_user
from flask_wtf import FlaskForm
from sqlalchemy import and_, func
from sqlalchemy.orm import joinedload, selectinload
from collections import defaultdict
from app.director import bp
from app import db
from app.models import (AdministrativeDepartment, AdvisorAssessmentRecord, AdvisorAssessmentScore, AssessmentTemplate, Classroom, Course, CourseGrade, Enrollment, GradeLevel, LessonPlan, QualitativeScore, RepeatCandidate, Semester, Student, SubjectGroup, User, Role, Subject, LearningUnit, Indicator, 
                        Standard, GradedItem, AssessmentDimension, AssessmentItem, 
                        AssessmentTopic, Notification)
from app.services import calculate_final_grades_for_course, calculate_grade_statistics, log_action

# ==============================================================================
# SECTION: LESSON PLAN APPROVAL (ฟังก์ชันเดิมของคุณ)
# ==============================================================================

@bp.route('/dashboard')
@login_required
def dashboard():
    # FIXED: Use consistent English role name for security check
    if not current_user.has_role('ผู้อำนวยการ'):
        abort(403)

    form = FlaskForm()

    # OPTIMIZED: Query for plans only ONCE
    plans_for_approval_list = (
        LessonPlan.query
        .filter(LessonPlan.status.in_(['รอการอนุมัติจากผู้อำนวยการ', 'อนุมัติใช้งาน']))
        .options(
            joinedload(LessonPlan.subject).joinedload(Subject.subject_group)
        )
        .join(LessonPlan.subject)
        .join(Subject.subject_group)
        # FIXED: Order by status first (pending plans on top), then by group name
        .order_by(
            db.case((LessonPlan.status == 'รอการอนุมัติจากผู้อำนวยการ', 0), else_=1),
            SubjectGroup.name, 
            LessonPlan.id
        )
        .all()
    )
    
    # Group the results from the single query
    grouped_plans = defaultdict(list)
    for plan in plans_for_approval_list:
        group_name = plan.subject.subject_group.name
        grouped_plans[group_name].append(plan)

    # Key Metrics
    total_teachers = User.query.join(User.roles).filter(Role.name == 'Teacher').count()
    approved_plans_count = LessonPlan.query.filter_by(status='อนุมัติใช้งาน').count()
    
    # Data for Plan Status Doughnut Chart
    status_counts = dict(db.session.query(LessonPlan.status, func.count(LessonPlan.id)).group_by(LessonPlan.status).all())
    plan_status_data = {
        "labels": list(status_counts.keys()),
        "data": list(status_counts.values())
    }

    # Data for Plans per Subject Group Bar Chart
    plans_per_group = (
        db.session.query(SubjectGroup.name, func.count(LessonPlan.id))
        .join(Subject, SubjectGroup.id == Subject.subject_group_id)
        .join(LessonPlan, Subject.id == LessonPlan.subject_id)
        .group_by(SubjectGroup.name)
        .order_by(SubjectGroup.name)
        .all()
    )
    plans_per_group_data = {
        "labels": [item[0] for item in plans_per_group],
        "data": [item[1] for item in plans_per_group]
    }    

    return render_template('director/dashboard.html', 
                           title="ผู้อำนวยการ", 
                           form=form,
                           plans_for_approval=plans_for_approval_list,
                           total_teachers=total_teachers,
                           approved_plans_count=approved_plans_count,
                           pending_director_approval=len(plans_for_approval_list),
                           plan_status_data=plan_status_data,
                           plans_per_group_data=plans_per_group_data,
                           grouped_plans=grouped_plans)

@bp.route('/plans/approve-all', methods=['POST'])
@login_required
def approve_all_plans():
    if not current_user.has_role('ผู้อำนวยการ'): abort(403) # Role check

    plans_to_approve = LessonPlan.query.filter_by(status='รอการอนุมัติจากผู้อำนวยการ').options(db.load_only(LessonPlan.id)).all()
    plan_ids = [p.id for p in plans_to_approve]
    count = len(plans_to_approve)
    new_status = 'อนุมัติใช้งาน'
    old_status = 'รอการอนุมัติจากผู้อำนวยการ'

    if not plans_to_approve:
        return jsonify({'status': 'info', 'message': 'ไม่พบแผนที่รออนุมัติ'}), 200

    try:
        # Bulk update
        LessonPlan.query.filter(LessonPlan.id.in_(plan_ids)).update({'status': new_status}, synchronize_session=False)

        # --- Log Bulk Action ---
        log_action(
            "Approve All Lesson Plans (Director)", model=LessonPlan,
            new_value={'count': count, 'new_status': new_status},
            old_value={'old_status': old_status}
        )
        db.session.commit()
        try:
            academic_role = db.session.query(Role).filter_by(name='Academic Affairs').first()
            if academic_role:
                title = "แผนการสอนได้รับการอนุมัติ (ทั้งหมด)"
                message = f"ผอ. ({current_user.full_name}) ได้อนุมัติแผนการสอนที่รออนุมัติทั้งหมด {count} รายการ"
                url_for_academic = url_for('academic.dashboard', _external=True) 
                for user in academic_role.users:
                    db.session.add(Notification(user_id=user.id, title=title, message=message, url=url_for_academic, notification_type='PLAN_APPROVED_ALL'))
                db.session.commit()
        except Exception as e:
            current_app.logger.error(f"Failed to send plan approval (all) notification: {e}", exc_info=True)
            pass
        flash(f'แผนการสอนทั้งหมด {count} รายการ ได้รับการอนุมัติแล้ว', 'success')
        return jsonify({'status': 'success', 'count': count})
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Error approving all plans: {e}", exc_info=True)
        # --- Log Failure ---
        log_action(f"Approve All Plans Failed (Director): {type(e).__name__}", model=LessonPlan)
        try: db.session.commit()
        except: db.session.rollback()
        return jsonify({'status': 'error', 'message': f'เกิดข้อผิดพลาด: {e}'}), 500


@bp.route('/plans/approve-by-group/<int:group_id>', methods=['POST'])
@login_required
def approve_plans_by_group(group_id):
    if not current_user.has_role('ผู้อำนวยการ'): abort(403) # Role check
    group = SubjectGroup.query.get_or_404(group_id)

    plans_to_approve = (
        LessonPlan.query
        .join(Subject)
        .filter(Subject.subject_group_id == group_id,
                LessonPlan.status == 'รอการอนุมัติจากผู้อำนวยการ')
        .options(db.load_only(LessonPlan.id)) # Only get IDs
        .all()
    )
    plan_ids = [p.id for p in plans_to_approve]
    count = len(plans_to_approve)
    new_status = 'อนุมัติใช้งาน'
    old_status = 'รอการอนุมัติจากผู้อำนวยการ'

    if not plans_to_approve:
        return jsonify({'status': 'info', 'message': f'ไม่พบแผนที่รออนุมัติสำหรับกลุ่มสาระ {group.name}'}), 200

    try:
        # Bulk update
        LessonPlan.query.filter(LessonPlan.id.in_(plan_ids)).update({'status': new_status}, synchronize_session=False)

        # --- Log Bulk Action ---
        log_action(
            f"Approve Group Lesson Plans (Director)", model=LessonPlan,
            new_value={'count': count, 'group_id': group_id, 'group_name': group.name, 'new_status': new_status},
            old_value={'old_status': old_status}
        )
        db.session.commit()
        try:
            recipients = set()
            # 1. Add Academic Affairs
            academic_role = db.session.query(Role).filter_by(name='Academic Affairs').first()
            if academic_role:
                recipients.update(academic_role.users)
            # 2. Add Subject Group Head
            if group.head:
                recipients.add(group.head)

            title = f"แผนการสอนกลุ่มสาระฯ {group.name} ได้รับการอนุมัติ"
            message = f"ผอ. ({current_user.full_name}) ได้อนุมัติแผนฯ ของกลุ่มสาระ {group.name} จำนวน {count} รายการ"
            url_for_notif = url_for('department.dashboard', _external=True) 

            for user in recipients:
                db.session.add(Notification(user_id=user.id, title=title, message=message, url=url_for_notif, notification_type='PLAN_APPROVED_GROUP'))
            db.session.commit()
        except Exception as e:
            current_app.logger.error(f"Failed to send plan approval (group) notification: {e}", exc_info=True)
            pass
        flash(f'แผนการสอนของกลุ่มสาระฯ {group.name} จำนวน {count} รายการ ได้รับการอนุมัติแล้ว', 'success')
        return jsonify({'status': 'success', 'count': count})
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Error approving plans for group {group_id}: {e}", exc_info=True)
        # --- Log Failure ---
        log_action(f"Approve Group Plans Failed (Director): {type(e).__name__}", model=LessonPlan, new_value={'group_id': group_id})
        try: db.session.commit()
        except: db.session.rollback()
        return jsonify({'status': 'error', 'message': f'เกิดข้อผิดพลาด: {e}'}), 500
    
@bp.route('/plan/<int:plan_id>/review')
@login_required
def review_plan(plan_id):
    # This function is a copy of the comprehensive one from the department/academic blueprints
    # to ensure the shared template receives all necessary data.
    plan = LessonPlan.query.options(
        joinedload(LessonPlan.subject),
        joinedload(LessonPlan.academic_year),
        selectinload(LessonPlan.learning_units).selectinload(LearningUnit.indicators).joinedload(Indicator.standard).joinedload(Standard.learning_strand),
        selectinload(LessonPlan.learning_units).selectinload(LearningUnit.graded_items).joinedload(GradedItem.dimension),
        selectinload(LessonPlan.learning_units).selectinload(LearningUnit.assessment_items).joinedload(AssessmentItem.topic).joinedload(AssessmentTopic.template),
        selectinload(LessonPlan.learning_units).selectinload(LearningUnit.assessment_items).joinedload(AssessmentItem.topic).joinedload(AssessmentTopic.parent)
    ).get_or_404(plan_id)

    # Calculation Block (reused for template consistency)
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

    # Dynamic Button Logic for Director
    approve_button_text = "อนุมัติใช้งาน"
    approve_action_url = url_for('director.approve_final', plan_id=plan.id)
    
    # Render the SHARED template with director-specific button logic
    return render_template('department/review_plan.html', 
                           title=f"พิจารณาแผน: {plan.subject.name}",
                           plan=plan,
                           score_during_semester=score_during_semester,
                           score_final=score_final,
                           actual_ratio_str=actual_ratio_str,
                           total_units=total_units,
                           total_periods=total_periods,
                           total_indicators=total_indicators,
                           approve_button_text=approve_button_text,
                           approve_action_url=approve_action_url)

@bp.route('/plan/<int:plan_id>/approve-final', methods=['POST'])
@login_required
# (Add security decorator for Director role)
def approve_final(plan_id):
    if not current_user.has_role('ผู้อำนวยการ'): abort(403) # Role check
    plan = LessonPlan.query.get_or_404(plan_id)
    original_status = plan.status
    new_status = 'อนุมัติใช้งาน'

    # Check if status is appropriate
    if original_status != 'รอการอนุมัติจากผู้อำนวยการ':
        flash(f'แผนไม่อยู่ในสถานะ "{original_status}" ไม่สามารถอนุมัติได้', 'warning')
        return redirect(url_for('director.review_plan', plan_id=plan_id))

    try:
        plan.status = new_status
        # --- Log Action ---
        log_action(
            "Approve Lesson Plan (Director Final)", model=LessonPlan, record_id=plan.id,
            old_value=original_status, new_value=new_status
        )
        db.session.commit()
        try:
            recipients = set()
            # 1. Add Academic Affairs
            academic_role = db.session.query(Role).filter_by(name='Academic Affairs').first()
            if academic_role: recipients.update(academic_role.users)
            # 2. Add Subject Group Head
            if plan.subject.subject_group and plan.subject.subject_group.head:
                recipients.add(plan.subject.subject_group.head)
            # 3. Add Teachers of courses using this plan
            courses_using_plan = Course.query.filter_by(lesson_plan_id=plan.id).options(selectinload(Course.teachers)).all()
            for course in courses_using_plan:
                recipients.update(course.teachers)

            title = f"แผนการสอน {plan.subject.name} ได้รับการอนุมัติ"
            message = f"ผอ. ({current_user.full_name}) ได้อนุมัติใช้งานแผนการสอนวิชา {plan.subject.name}"
            url_for_notif = url_for('teacher.dashboard', _external=True) 

            for user in recipients:
                db.session.add(Notification(user_id=user.id, title=title, message=message, url=url_for_notif, notification_type='PLAN_APPROVED_FINAL'))
            db.session.commit()
        except Exception as e:
            current_app.logger.error(f"Failed to send plan approval (final) notification: {e}", exc_info=True)
            pass
        flash(f'แผนการสอน "{plan.subject.name}" ได้รับการอนุมัติใช้งานเรียบร้อยแล้ว', 'success')
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Error final approving plan {plan_id}: {e}", exc_info=True)
        # --- Log Failure ---
        log_action(f"Approve Plan Final Failed (Director): {type(e).__name__}", model=LessonPlan, record_id=plan.id, old_value=original_status, new_value=new_status)
        try: db.session.commit()
        except: db.session.rollback()
        flash(f'เกิดข้อผิดพลาดในการอนุมัติ: {e}', 'danger')

    return redirect(url_for('director.dashboard'))

# ==============================================================================
# SECTION: GRADE APPROVAL (ส่วนใหม่สำหรับ "อนุมัติผลการเรียน")
# ==============================================================================

@bp.route('/grades-dashboard')
@login_required
def grades_dashboard():
    if not current_user.has_role('ผู้อำนวยการ'):
        abort(403)

    current_semester = Semester.query.filter_by(is_current=True).first_or_404()
    form = FlaskForm()

    # --- ส่วนที่ 1: ดึงข้อมูลที่รออนุมัติสำหรับ "เทอมปัจจุบัน" ---
    pending_courses = Course.query.join(Subject).filter(
        Course.semester_id == current_semester.id,
        Course.grade_submission_status == 'รอการอนุมัติจากผู้อำนวยการ'
    ).options(
        joinedload(Course.subject).joinedload(Subject.subject_group),
        joinedload(Course.classroom).joinedload(Classroom.grade_level)
    ).order_by(Subject.subject_code).all()

    # --- ส่วนที่ 2: ประมวลผลข้อมูลของ "เทอมปัจจุบัน" เพื่อสร้างสถิติหลัก ---
    all_student_grades_data = []
    grades_by_group = defaultdict(list)
    for course in pending_courses:
        calculated_data, _ = calculate_final_grades_for_course(course)
        all_student_grades_data.extend(calculated_data)
        grades_by_group[course.subject.subject_group].extend(calculated_data)

    overall_stats = calculate_grade_statistics(all_student_grades_data)
    
    group_summary_stats = []
    for group in sorted(grades_by_group.keys(), key=lambda g: g.name):
        if stats := calculate_grade_statistics(grades_by_group[group]):
            group_summary_stats.append({'group': group, 'stats': stats})

    # --- ส่วนที่ 3: [ปรับปรุง] เตรียมข้อมูลสำหรับกราฟทั้งหมด ---
    chart_data = {}
    if overall_stats:
        # กราฟ 1: การกระจายผลการเรียน (ข้อมูลพร้อม, สีจะถูกเปลี่ยนที่ Frontend)
        labels = ['4', '3.5', '3', '2.5', '2', '1.5', '1', '0', 'ร', 'มส']
        chart_data['main_grade_dist'] = {'labels': labels, 'data': [overall_stats['grade_distribution'].get(l, 0) for l in labels]}
        
        # กราฟ 2: [ปรับปรุง] คำนวณองค์ประกอบ 3 ส่วนสำหรับ Stacked Bar Chart
        chart_data['group_comparison'] = {
            'labels': [item['group'].name for item in group_summary_stats],
            'good_excellent_data': [item['stats']['good_excellent_percent'] for item in group_summary_stats],
            'passed_data': [item['stats']['passed_percent'] for item in group_summary_stats], # ใช้ % ผ่านทั้งหมด
            'failed_data': [item['stats']['failed_percent'] for item in group_summary_stats]
        }
        
    # --- ส่วนที่ 4: [ปรับปรุง] ดึงข้อมูลย้อนหลัง "รายภาคเรียน" ---
    from app.models import AcademicYear
    # ดึงข้อมูล 6 เทอมล่าสุด
    semesters_to_compare = Semester.query.join(AcademicYear).filter(
        Semester.end_date < date.today() # กรองเฉพาะเทอมที่สิ้นสุดแล้ว
    ).order_by(AcademicYear.year.desc(), Semester.term.desc()).limit(6).all()
    
    semester_comparison_data = {'labels': [], 'm_ton_passed': [], 'm_plai_passed': []}
    m_ton_ids = {gl.id for gl in GradeLevel.query.filter_by(level_group='m-ton').all()}
    m_plai_ids = {gl.id for gl in GradeLevel.query.filter_by(level_group='m-plai').all()}

    for semester in sorted(semesters_to_compare, key=lambda s: (s.academic_year.year, s.term)):
        semester_comparison_data['labels'].append(f"{semester.term}/{semester.academic_year.year}")
        
        # ดึง Course ที่อนุมัติแล้วทั้งหมดในเทอมนั้นๆ
        approved_courses = Course.query.filter(
            Course.semester_id == semester.id,
            Course.grade_submission_status == 'อนุมัติใช้งาน'
        ).options(joinedload(Course.classroom)).all()

        all_grades_in_semester = [grade for c in approved_courses for grade in calculate_final_grades_for_course(c)[0]]

        # คำนวณของ ม.ต้น
        m_ton_grades = [g for g in all_grades_in_semester if g['classroom_id'] and Classroom.query.get(g['classroom_id']).grade_level_id in m_ton_ids]
        m_ton_stats = calculate_grade_statistics(m_ton_grades)
        semester_comparison_data['m_ton_passed'].append(m_ton_stats.get('passed_percent', 0))

        # คำนวณของ ม.ปลาย
        m_plai_grades = [g for g in all_grades_in_semester if g['classroom_id'] and Classroom.query.get(g['classroom_id']).grade_level_id in m_plai_ids]
        m_plai_stats = calculate_grade_statistics(m_plai_grades)
        semester_comparison_data['m_plai_passed'].append(m_plai_stats.get('passed_percent', 0))

    chart_data['semester_comparison'] = semester_comparison_data

    return render_template('director/grades_dashboard.html',
                           title='พิจารณาผลการเรียน',
                           form=form,
                           semester=semester,
                           pending_courses=pending_courses,
                           pending_courses_count=len(pending_courses),
                           overall_stats=overall_stats,
                           chart_data=chart_data)

@bp.route('/grades/approve-all', methods=['POST'])
@login_required
def approve_all_grades():
    if not current_user.has_role('ผู้อำนวยการ'): abort(403)
    semester = Semester.query.filter_by(is_current=True).first_or_404()

    courses_to_approve_q = Course.query.filter_by(semester_id=semester.id, grade_submission_status='รอการอนุมัติจากผู้อำนวยการ')
    courses_to_approve = courses_to_approve_q.options(db.load_only(Course.id)).all()
    course_ids = [c.id for c in courses_to_approve]
    count = len(courses_to_approve)
    new_status = 'อนุมัติใช้งาน'
    old_status = 'รอการอนุมัติจากผู้อำนวยการ'

    if not courses_to_approve:
         return jsonify({'status': 'info', 'message': 'ไม่พบผลการเรียนที่รออนุมัติ'}), 200

    try:
        # Bulk Update
        courses_to_approve_q.update({'grade_submission_status': new_status}, synchronize_session=False)

        # --- Log Bulk Action ---
        log_action(
            "Approve All Grades (Director)", model=Course,
            new_value={'count': count, 'new_status': new_status, 'semester_id': semester.id},
            old_value={'old_status': old_status}
        )
        db.session.commit()
        try:
            academic_role = db.session.query(Role).filter_by(name='Academic Affairs').first()
            if academic_role:
                title = "ผลการเรียนได้รับการอนุมัติ (ทั้งหมด)"
                message = f"ผอ. ({current_user.full_name}) ได้อนุมัติผลการเรียนที่รออนุมัติทั้งหมด {count} รายการ"
                url_for_academic = url_for('academic.grades_dashboard', _external=True)
                for user in academic_role.users:
                    db.session.add(Notification(user_id=user.id, title=title, message=message, url=url_for_academic, notification_type='GRADES_APPROVED_ALL'))
                db.session.commit()
        except Exception as e:
            current_app.logger.error(f"Failed to send grade approval (all) notification: {e}", exc_info=True)
            pass
        flash(f'อนุมัติผลการเรียน {count} รายการเรียบร้อยแล้ว', 'success')
        return jsonify({'status': 'success', 'count': count})
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Error approving all grades: {e}", exc_info=True)
        # --- Log Failure ---
        log_action(f"Approve All Grades Failed (Director): {type(e).__name__}", model=Course)
        try: db.session.commit()
        except: db.session.rollback()
        return jsonify({'status': 'error', 'message': f'เกิดข้อผิดพลาด: {e}'}), 500

@bp.route('/grades/approve-one/<int:course_id>', methods=['POST'])
@login_required
def approve_one_grade(course_id):
    if not current_user.has_role('ผู้อำนวยการ'): abort(403)
    course = Course.query.get_or_404(course_id)
    original_status = course.grade_submission_status
    new_status = 'อนุมัติใช้งาน'

    if original_status == 'รอการอนุมัติจากผู้อำนวยการ':
        try:
            course.grade_submission_status = new_status
            # --- Log Action ---
            log_action(
                "Approve Grade (Director)", model=Course, record_id=course.id,
                old_value=original_status, new_value=new_status
            )
            db.session.commit()
            try:
                recipients = set()
                # 1. Add Academic Affairs
                academic_role = db.session.query(Role).filter_by(name='Academic Affairs').first()
                if academic_role: recipients.update(academic_role.users)
                # 2. Add Teachers of this course
                recipients.update(course.teachers)

                title = f"ผลการเรียนวิชา {course.subject.name} ได้รับการอนุมัติ"
                message = f"ผอ. ({current_user.full_name}) ได้อนุมัติผลการเรียนวิชา {course.subject.name} ({course.classroom.name})"
                url_for_notif = url_for('teacher.view_course', course_id=course.id, _external=True)

                for user in recipients:
                    db.session.add(Notification(user_id=user.id, title=title, message=message, url=url_for_notif, notification_type='GRADES_APPROVED_ONE'))
                db.session.commit()
            except Exception as e:
                current_app.logger.error(f"Failed to send grade approval (one) notification: {e}", exc_info=True)
                pass
            return jsonify({'status': 'success'})
        except Exception as e:
            db.session.rollback()
            current_app.logger.error(f"Error approving grade for course {course_id}: {e}", exc_info=True)
            # --- Log Failure ---
            log_action(f"Approve Grade Failed (Director): {type(e).__name__}", model=Course, record_id=course.id, old_value=original_status, new_value=new_status)
            try: db.session.commit()
            except: db.session.rollback()
            return jsonify({'status': 'error', 'message': f'เกิดข้อผิดพลาด: {e}'}), 500
    else:
        return jsonify({'status': 'error', 'message': 'สถานะไม่ถูกต้อง'}), 400

@bp.route('/grades/review/<int:course_id>')
@login_required
def review_grades(course_id):
    if not current_user.has_role('ผู้อำนวยการ'):
        abort(403)

    course = Course.query.options(
        joinedload(Course.subject),
        joinedload(Course.classroom).joinedload(Classroom.grade_level),
        joinedload(Course.teachers)
    ).get_or_404(course_id)
    
    student_grades, max_scores = calculate_final_grades_for_course(course)

    return render_template('director/review_grades.html',
                           title=f"ตรวจสอบผลการเรียน: {course.subject.name} ({course.classroom.name})",
                           course=course,
                           student_grades=student_grades,
                           max_scores=max_scores)

# ==============================================================================
# SECTION: REMEDIATION APPROVAL (Existing Logic - can remain)
# ==============================================================================
@bp.route('/remediation-approval')
@login_required
def remediation_approval():
    # Ensure user has the correct role
    if not current_user.has_role('ผู้อำนวยการ'):
        abort(403)

    semester = Semester.query.filter_by(is_current=True).first_or_404()

    # Query for all students that have reached the director's approval stage
    students_for_director = db.session.query(CourseGrade, Enrollment).join(
        Course, CourseGrade.course_id == Course.id
    ).join(
        Enrollment, and_(
            CourseGrade.student_id == Enrollment.student_id,
            Course.classroom_id == Enrollment.classroom_id
        )
    ).filter(
        Course.semester_id == semester.id,
        CourseGrade.remediation_status.in_(['Pending Director Approval', 'Approved'])
    ).options(
        joinedload(CourseGrade.student),
        joinedload(CourseGrade.course).joinedload(Course.subject).joinedload(Subject.subject_group),
        joinedload(CourseGrade.course).joinedload(Course.classroom)
    ).all()

    # Group students into 'pending' and 'approved' lists
    pending_approval_students = []
    approved_students = []

    for grade_obj, enrollment_obj in students_for_director:
        item_tuple = (grade_obj, enrollment_obj)
        if grade_obj.remediation_status == 'Pending Director Approval':
            pending_approval_students.append(item_tuple)
        else: # 'Approved'
            approved_students.append(item_tuple)
            
    # Prepare stats for the UI
    stats = {
        'pending': len(pending_approval_students),
        'approved': len(approved_students),
        'total': len(students_for_director)
    }

    return render_template('director/remediation_approval.html',
                           title="อนุมัติผลการเรียน (ฉบับซ่อม)",
                           semester=semester,
                           stats=stats,
                           pending_approval_students=pending_approval_students,
                           approved_students=approved_students)

@bp.route('/api/remediation/approve-all', methods=['POST'])
@login_required
def approve_all_remediation():
    if not current_user.has_role('ผู้อำนวยการ'):
        return jsonify({'status': 'error', 'message': 'Permission Denied'}), 403

    current_semester = Semester.query.filter_by(is_current=True).first_or_404()
    course_ids_in_semester = db.session.query(Course.id).filter(
        Course.semester_id == current_semester.id
    ).scalar_subquery()

    records_to_approve_q = CourseGrade.query.filter(
        CourseGrade.course_id.in_(course_ids_in_semester),
        CourseGrade.remediation_status == 'Pending Director Approval'
    )
    records_to_approve = records_to_approve_q.options(db.load_only(CourseGrade.id)).all()
    record_ids = [r.id for r in records_to_approve]
    count = len(records_to_approve)
    new_status = 'Approved'
    old_status = 'Pending Director Approval'

    if not records_to_approve:
         return jsonify({'status': 'info', 'message': 'ไม่พบผลการซ่อมที่รออนุมัติ'}), 200

    try:
        # Bulk Update
        records_to_approve_q.update({'remediation_status': new_status}, synchronize_session=False)

        # --- Log Bulk Action ---
        log_action(
            "Approve All Remediation (Director)", model=CourseGrade,
            new_value={'count': count, 'new_status': new_status, 'semester_id': current_semester.id},
            old_value={'old_status': old_status}
        )
        db.session.commit()
        try:
            academic_role = db.session.query(Role).filter_by(name='Academic Affairs').first()
            if academic_role:
                title = "ผลการซ่อมได้รับการอนุมัติ (ทั้งหมด)"
                message = f"ผอ. ({current_user.full_name}) ได้อนุมัติผลการซ่อมของนักเรียน {count} คนเรียบร้อยแล้ว"
                url_for_academic = url_for('academic.remediation_approval', _external=True)
                for user in academic_role.users:
                    db.session.add(Notification(user_id=user.id, title=title, message=message, url=url_for_academic, notification_type='REMEDIATION_APPROVED_ALL'))
                db.session.commit()
        except Exception as e:
            current_app.logger.error(f"Failed to send remediation approval (all) notification: {e}", exc_info=True)
            pass
        return jsonify({
            'status': 'success',
            'message': f'อนุมัติผลการซ่อมของนักเรียน {count} คนเรียบร้อยแล้ว'
        })
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Error approving all remediation: {e}", exc_info=True)
        # --- Log Failure ---
        log_action(f"Approve All Remediation Failed (Director): {type(e).__name__}", model=CourseGrade)
        try: db.session.commit()
        except: db.session.rollback()
        return jsonify({'status': 'error', 'message': f'เกิดข้อผิดพลาด: {e}'}), 500

# ==========================================================
# [1] VIEW: หน้าหลัก (ใช้ Logic ของ Academic ที่คุณส่งมาเป็นตัวอย่าง)
# ==========================================================
@bp.route('/assessment-approval')
@login_required
def assessment_approval():
    if not current_user.has_role('ผู้อำนวยการ'): abort(403)
        
    current_semester = Semester.query.filter_by(is_current=True).first_or_404()

    # --- [จุดแก้ไขสำคัญ] ---
    # เราจะใช้ Logic เดียวกับ Academic แต่เปลี่ยนเงื่อนไขการค้นหา (Filter)
    # จาก 'Submitted to Academic Affairs'
    # เป็น 'Pending Director Approval' (รอ ผอ. อนุมัติ) และ 'Approved' (ผอ. อนุมัติแล้ว)
    
    records_in_process = db.session.query(AdvisorAssessmentRecord, Enrollment).join(
        Enrollment, AdvisorAssessmentRecord.student_id == Enrollment.student_id
    ).join(
        Classroom, Enrollment.classroom_id == Classroom.id 
    ).filter(
        AdvisorAssessmentRecord.semester_id == current_semester.id,
        Classroom.academic_year_id == current_semester.academic_year_id, 
        AdvisorAssessmentRecord.status.in_(['Pending Director Approval', 'Approved']) # <--- แก้ไขเงื่อนไขที่นี่
    ).options(
        joinedload(AdvisorAssessmentRecord.student),
        joinedload(Enrollment.classroom).joinedload(Classroom.grade_level), 
        joinedload(Enrollment.classroom).joinedload(Classroom.advisors), 
        joinedload(AdvisorAssessmentRecord.scores).joinedload(AdvisorAssessmentScore.topic) 
    ).order_by(Classroom.grade_level_id, Enrollment.classroom_id, Enrollment.roll_number).all()

    # --- ส่วนนี้คือ Logic การสร้างข้อมูลที่ Theme ของคุณต้องการ (เหมือนไฟล์ตัวอย่าง) ---
    
    records_by_grade_level = defaultdict(lambda: defaultdict(lambda: {'records': [], 'advisors': []}))
    processed_classrooms = set()
    
    templates = AssessmentTemplate.query.options(joinedload(AssessmentTemplate.rubric_levels), joinedload(AssessmentTemplate.topics)).all()
    first_template = next((t for t in templates if t.rubric_levels), None) 
    rubric_map = {r.value: r.label for r in first_template.rubric_levels} if first_template else {}

    total_pending_director = 0
    total_approved_by_director = 0

    for record, enrollment in records_in_process:
        classroom = enrollment.classroom
        classroom_name = classroom.name 
        grade_level = classroom.grade_level 
        grade_level_name = grade_level.name 

        if classroom.id not in processed_classrooms:
            records_by_grade_level[grade_level_name][classroom_name]['advisors'] = [adv.first_name for adv in classroom.advisors]
            processed_classrooms.add(classroom.id)
        
        # สร้าง Mini Bar Chart Summary
        summary_dist = defaultdict(int) 
        for score in record.scores:
            if score.topic and score.topic.parent_id is None: 
                label = rubric_map.get(score.score_value, 'N/A')
                summary_dist[label] += 1
        item_tuple = (record, enrollment, dict(summary_dist)) 

        records_by_grade_level[grade_level_name][classroom_name]['records'].append(item_tuple) 
        
        # [จุดแก้ไขสำคัญ] นับจำนวนให้ถูกช่อง
        if record.status == 'Pending Director Approval': 
            total_pending_director += 1
        elif record.status == 'Approved':
            total_approved_by_director += 1
            
    # สร้างตัวแปร 'stats' ที่ Theme ของคุณต้องการ
    stats = { 
        'pending': total_pending_director, 
        'approved': total_approved_by_director
    }

    # สร้างตัวแปร 'assessment_stats' (กราฟใหญ่) ที่ Theme ของคุณต้องการ
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

    return render_template('director/assessment_approval.html', 
                           title='อนุมัติผลการประเมิน (ผอ.)',
                           semester=current_semester,
                           stats=stats,
                           records_by_grade_level=dict(records_by_grade_level),
                           assessment_stats=assessment_stats_by_template,
                           overall_mode_distribution={}) # ส่งค่าว่างไปก่อนได้ถ้าไม่ใช้

# ==========================================================
# [2] API: สำหรับปุ่ม "อนุมัติทั้งหมด"
# ==========================================================
@bp.route('/api/approve-all-assessments', methods=['POST'])
@login_required
def approve_all_assessments():
    if not current_user.has_role('ผู้อำนวยการ'): abort(403)
    current_semester = Semester.query.filter_by(is_current=True).first_or_404()

    records_to_approve_q = AdvisorAssessmentRecord.query.filter(
        AdvisorAssessmentRecord.semester_id == current_semester.id,
        AdvisorAssessmentRecord.status == 'Pending Director Approval' # Approve only those pending director
    )
    records_to_approve = records_to_approve_q.options(db.load_only(AdvisorAssessmentRecord.id)).all()
    record_ids = [r.id for r in records_to_approve]
    count = len(records_to_approve)
    new_status = 'Approved'
    old_status = 'Pending Director Approval'

    if not records_to_approve:
        return jsonify({'status': 'info', 'message': 'ไม่พบรายการประเมินที่รออนุมัติ'}), 200

    try:
        updated_count = records_to_approve_q.update(
            {'status': new_status, 'approved_at': datetime.utcnow()},
            synchronize_session=False
        )

        # --- Log Bulk Action ---
        log_action(
            "Approve All Assessments (Director)", model=AdvisorAssessmentRecord,
            new_value={'count': updated_count, 'new_status': new_status, 'semester_id': current_semester.id},
            old_value={'old_status': old_status}
        )
        db.session.commit()
        try:
            academic_role = db.session.query(Role).filter_by(name='Academic Affairs').first()
            if academic_role:
                title = "ผลประเมินคุณลักษณะได้รับการอนุมัติ (ทั้งหมด)"
                message = f"ผอ. ({current_user.full_name}) ได้อนุมัติผลการประเมินคุณลักษณะ {updated_count} รายการ"
                url_for_academic = url_for('academic.review_advisor_assessments', _external=True)
                for user in academic_role.users:
                    db.session.add(Notification(user_id=user.id, title=title, message=message, url=url_for_academic, notification_type='ASSESSMENT_APPROVED_ALL'))
                db.session.commit()
        except Exception as e:
            current_app.logger.error(f"Failed to send assessment approval (all) notification: {e}", exc_info=True)
            pass
        return jsonify({'status': 'success', 'message': f'อนุมัติผลการประเมิน {updated_count} รายการเรียบร้อยแล้ว'})
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Error approving all assessments: {e}", exc_info=True)
        # --- Log Failure ---
        log_action(f"Approve All Assessments Failed (Director): {type(e).__name__}", model=AdvisorAssessmentRecord)
        try: db.session.commit()
        except: db.session.rollback()
        return jsonify({'status': 'error', 'message': f'เกิดข้อผิดพลาด: {e}'}), 500

# ==========================================================
# [3] API: สำหรับ Modal ตรวจสอบ (เวอร์ชันแก้ไขที่เพิ่ม "หลักฐาน")
# ==========================================================
@bp.route('/api/assessment-record/<int:record_id>/details')
@login_required
def get_director_review_details(record_id):
    if not current_user.has_role('ผู้อำนวยการ'): abort(403)
    record = db.session.get(AdvisorAssessmentRecord, record_id)
    if not record: abort(404)

    # 1. ดึงข้อมูลสรุปของครูที่ปรึกษา
    advisor_scores = {score.topic_id: score.score_value for score in record.scores}

    # 2. ดึงข้อมูล "หลักฐาน" จากครูผู้สอน (ส่วนที่ขาดไป)
    enrollment = Enrollment.query.join(Classroom).filter(
        Enrollment.student_id == record.student_id,
        Classroom.academic_year_id == record.semester.academic_year_id
    ).first()
    
    student_courses = Course.query.filter_by(
        classroom_id=enrollment.classroom_id, 
        semester_id=record.semester_id
    ).options(joinedload(Course.subject)).all() if enrollment else []
    
    course_ids = [c.id for c in student_courses]
    course_subject_map = {c.id: c.subject.name for c in student_courses if c.subject}

    all_qualitative_scores = QualitativeScore.query.filter(
        QualitativeScore.student_id == record.student_id,
        QualitativeScore.course_id.in_(course_ids)
    ).all()

    scores_by_topic = defaultdict(list)
    for score in all_qualitative_scores:
        scores_by_topic[score.assessment_topic_id].append({
            'subject': course_subject_map.get(score.course_id, 'N/A'), 
            'score': score.score_value
        })

    # 3. ดึง Template และสร้างข้อมูล Response ที่ "เป็นหนึ่งเดียว"
    templates = AssessmentTemplate.query.options(
        joinedload(AssessmentTemplate.topics).joinedload(AssessmentTopic.children),
        joinedload(AssessmentTemplate.rubric_levels)
    ).order_by(AssessmentTemplate.display_order).all()
    
    response_data = []
    for template in templates:
        rubric_map = {r.value: r.label for r in template.rubric_levels}
        # [แก้ไข] เพิ่ม 'id' เข้าไปใน template_data
        template_data = {'id': template.id, 'name': template.name, 'table_data': [], 'labels': [], 'data': []}
        main_topics = sorted([t for t in template.topics if not t.parent_id], key=lambda t: t.id)
        
        for topic in main_topics:
            advisor_score_value = advisor_scores.get(topic.id)
            
            # [FIX 2] รวบรวมหลักฐานสำหรับหัวข้อนี้
            all_evidence = scores_by_topic.get(topic.id, [])
            if topic.children:
                for sub in topic.children:
                    all_evidence.extend(scores_by_topic.get(sub.id, []))
            
            evidence_list_for_json = sorted([
                {'subject': ev['subject'], 'score_label': rubric_map.get(ev['score'], 'N/A')}
                for ev in all_evidence
            ], key=lambda x: x['subject'])
            
            # เพิ่มข้อมูลสำหรับ Radar Chart
            template_data['labels'].append(topic.name)
            template_data['data'].append(advisor_score_value if advisor_score_value is not None else 0)
            
            # เพิ่มข้อมูลสำหรับตาราง (พร้อมหลักฐาน)
            template_data['table_data'].append({
                'name': topic.name,
                'label': rubric_map.get(advisor_score_value, '-'),
                'evidence_scores': evidence_list_for_json  # <--- [FIX 2] เพิ่มข้อมูลหลักฐานเข้าไป
            })
            
        response_data.append(template_data)

    return jsonify(response_data)

@bp.route('/review-repeat-candidates')
@login_required
# @director_required
def review_repeat_candidates_director():
    """Displays candidates pending Director approval."""
    form = FlaskForm() # For CSRF

    # Find candidates whose status is pending Director approval
    candidates = db.session.query(RepeatCandidate).filter(
        RepeatCandidate.status.like('Pending Director Approval%') # Match both 'Repeat' and 'Promote' pending
    ).options(
        joinedload(RepeatCandidate.student),
        joinedload(RepeatCandidate.previous_enrollment).joinedload(Enrollment.classroom).joinedload(Classroom.grade_level),
        joinedload(RepeatCandidate.academic_year) # Year failed
    ).order_by(RepeatCandidate.updated_at.asc()).all()

    return render_template('director/review_repeat_candidates_director.html',
                           title='อนุมัตินักเรียนซ้ำชั้น/เลื่อนชั้นพิเศษ (ผอ.)',
                           candidates=candidates,
                           form=form)

@bp.route('/review-repeat-candidates/submit/<int:candidate_id>', methods=['POST'])
@login_required
# @director_required
def submit_director_decision(candidate_id):
    if not current_user.has_role('ผู้อำนวยการ'): abort(403) # Role check
    candidate = db.session.get(RepeatCandidate, candidate_id)

    # Security Check
    if (not candidate or not candidate.status.startswith('Pending Director Approval')):
        flash('ไม่พบข้อมูลหรือสถานะไม่ถูกต้อง', 'danger')
        return redirect(url_for('director.review_repeat_candidates_director'))

    decision = request.form.get('decision') # 'approve' or 'reject'
    notes = request.form.get('notes', '')
    original_status = candidate.status
    new_status = None

    if decision == 'approve':
        if candidate.status.endswith('(Repeat)'): new_status = 'Approved (Repeat)'
        elif candidate.status.endswith('(Promote)'): new_status = 'Approved (Promote)'
        else: new_status = 'Approved'
        # final_decision is already set tentatively
    elif decision == 'reject':
        new_status = 'Rejected by Director'
        # Keep tentative final_decision for record? Or override? Let's keep it.
    else:
        flash('กรุณาเลือกการดำเนินการ (อนุมัติ/ไม่อนุมัติ)', 'warning')
        return redirect(url_for('director.review_repeat_candidates_director'))

    try:
        candidate.status = new_status
        candidate.director_notes = notes

        # --- Log Action ---
        log_action(
            f"Director Review Repeat Candidate ({decision})", model=RepeatCandidate, record_id=candidate.id,
            old_value=original_status,
            new_value={'status': new_status, 'final_decision': candidate.final_decision, 'notes': notes}
        )
        db.session.commit()
        try:
            academic_role = db.session.query(Role).filter_by(name='Academic Affairs').first()
            if academic_role:
                title = f"ผลการพิจารณา นร. ซ้ำชั้น/เลื่อนชั้น ({decision})"
                message = f"ผอ. ได้ {decision} เรื่องของ {candidate.student.full_name} (สถานะ: {new_status})"
                url_for_academic = url_for('academic.review_repeat_candidates', _external=True)

                for user in academic_role.users:
                    new_notif = Notification(
                        user_id=user.id,
                        title=title,
                        message=message,
                        url=url_for_academic,
                        notification_type='REPEAT_CANDIDATE_FINALIZED'
                    )
                    db.session.add(new_notif)
                db.session.commit()
        except Exception as e:
            current_app.logger.error(f"Failed to send repeat candidate finalization notification: {e}", exc_info=True)
            pass
        flash(f'บันทึกการอนุมัติสำหรับ {candidate.student.full_name} เรียบร้อยแล้ว', 'success')

    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Error submitting director decision for candidate {candidate_id}: {e}", exc_info=True)
        # --- Log Failure ---
        log_action(f"Director Review Repeat Candidate Failed: {type(e).__name__}", model=RepeatCandidate, record_id=candidate.id)
        try: db.session.commit()
        except: db.session.rollback()
        flash(f'เกิดข้อผิดพลาด: {e}', 'danger')

    return redirect(url_for('director.review_repeat_candidates_director'))