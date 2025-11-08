# app/advisor/routes.py

from collections import defaultdict
from datetime import datetime
from statistics import StatisticsError, mode
from flask import Blueprint, abort, current_app, flash, jsonify, redirect, render_template, request, url_for
from flask_login import login_required, current_user
from flask_wtf import FlaskForm
from sqlalchemy import func
from app import db
from sqlalchemy.orm import joinedload, contains_eager
from app.advisor import bp
from app.models import AdvisorAssessmentRecord, AdvisorAssessmentScore, AssessmentTemplate, AssessmentTopic, AttendanceRecord, Classroom, Course, CourseGrade, GradedItem, LearningUnit, LessonPlan, QualitativeScore, RepeatCandidate, Score, Student, Enrollment, AttendanceWarning, Semester, Subject, classroom_advisors, Notification, User
from app.services import log_action

@bp.route('/dashboard')
@login_required
def dashboard():
    if not current_user.advised_classrooms:
        return render_template('advisor/dashboard.html', title="แดชบอร์ดครูที่ปรึกษา", classrooms=[], all_enrollments=[], attention_students=[])

    advised_classrooms = current_user.advised_classrooms
    primary_classroom = advised_classrooms[0]

    enrollments = Enrollment.query.filter_by(
        classroom_id=primary_classroom.id
    ).options(
        joinedload(Enrollment.student)
    ).order_by(
        Enrollment.roll_number
    ).all()

    student_ids = [en.student.id for en in enrollments]

    warning_student_ids = {s_id for s_id, in db.session.query(AttendanceWarning.student_id).filter(
        AttendanceWarning.student_id.in_(student_ids),
        AttendanceWarning.status == 'ACTIVE'
    ).distinct()}

    non_active_student_ids = {s.id for s in Student.query.filter(
        Student.id.in_(student_ids),
        Student.status != 'กำลังศึกษา'
    )}

    attention_student_ids = warning_student_ids.union(non_active_student_ids)
    
    attention_students = [en.student for en in enrollments if en.student.id in attention_student_ids]
    attention_students.sort(key=lambda s: next((en.roll_number for en in enrollments if en.student_id == s.id), 999))


    return render_template(
        'advisor/dashboard.html',
        title="แดชบอร์ดครูที่ปรึกษา",
        classrooms=advised_classrooms,
        all_enrollments=enrollments,
        attention_students=attention_students)

@bp.route('/student/<int:student_id>')
@login_required
def student_profile(student_id):
    # This function can remain as is, it's not affected by the Command Center changes.
    student = db.session.get(Student, student_id)
    if not student: abort(404)

    is_advisor_of_student = any(student in [e.student for e in classroom.enrollments] for classroom in current_user.advised_classrooms)
    if not is_advisor_of_student: abort(403)

    active_warnings = AttendanceWarning.query.filter_by(student_id=student.id, status='ACTIVE').options(joinedload(AttendanceWarning.course).joinedload(Course.subject)).all()
    current_semester = Semester.query.filter_by(is_current=True).first()
    
    academic_summary = []
    assessment_summary = []
    enrolled_courses = []

    if current_semester:
        enrolled_courses = Course.query.join(
            CourseGrade, Course.id == CourseGrade.course_id
        ).filter(
            CourseGrade.student_id == student.id,
            Course.semester_id == current_semester.id
        ).options(
            joinedload(Course.subject), 
            joinedload(Course.teachers), 
            joinedload(Course.lesson_plan).joinedload(LessonPlan.learning_units)
        ).all()
        
        course_ids = [c.id for c in enrolled_courses]
        student_course_grades = [cg for cg in student.course_grades if cg.course_id in course_ids]
        grades_map = {cg.course_id: cg for cg in student_course_grades}
        
        def map_to_grade(p):
            if p >= 80: return '4'
            if p >= 75: return '3.5'
            if p >= 70: return '3'
            if p >= 65: return '2.5'
            if p >= 60: return '2'
            if p >= 55: return '1.5'
            if p >= 50: return '1'
            return '0'

        for course in enrolled_courses:
            grade_obj = grades_map.get(course.id)
            course_summary = {'course': course,'collected_score': 0,'max_collected_score': 0,'midterm_score': None,'final_score': None,'attendance': {'PRESENT': 0, 'LATE': 0, 'ABSENT': 0, 'LEAVE': 0}}
            if grade_obj:
                course_summary['midterm_score'] = grade_obj.midterm_score
                course_summary['final_score'] = grade_obj.final_score
            
            total_midterm_max, total_final_max = 0, 0
            if course.lesson_plan:
                graded_items = GradedItem.query.join(LearningUnit).filter(LearningUnit.lesson_plan_id == course.lesson_plan.id).all()
                if graded_items:
                    item_ids = [i.id for i in graded_items]
                    scores = Score.query.filter(Score.student_id == student.id, Score.graded_item_id.in_(item_ids)).all()
                    course_summary['collected_score'] = sum(s.score for s in scores if s.score is not None)
                    course_summary['max_collected_score'] = sum(i.max_score for i in graded_items if i.max_score is not None)
                
                total_midterm_max = sum(unit.midterm_score for unit in course.lesson_plan.learning_units if unit.midterm_score)
                total_final_max = sum(unit.final_score for unit in course.lesson_plan.learning_units if unit.final_score)

            student_total_score = (course_summary['collected_score'] or 0) + (course_summary['midterm_score'] or 0) + (course_summary['final_score'] or 0)
            grand_max_score = (course_summary['max_collected_score'] or 0) + total_midterm_max + total_final_max
            percentage = (student_total_score / grand_max_score * 100) if grand_max_score > 0 else 0
            
            course_summary.update({'total_score': student_total_score, 'grand_max_score': grand_max_score, 'grade': map_to_grade(percentage), 'max_midterm_score': total_midterm_max, 'max_final_score': total_final_max})
            
            entry_ids = [e.id for e in course.timetable_entries]
            if entry_ids:
                attendance_counts = db.session.query(AttendanceRecord.status, func.count(AttendanceRecord.id)).filter(AttendanceRecord.student_id == student.id, AttendanceRecord.timetable_entry_id.in_(entry_ids)).group_by(AttendanceRecord.status).all()
                for status, count in attendance_counts:
                    if status in course_summary['attendance']: course_summary['attendance'][status] = count
            
            academic_summary.append(course_summary)

        templates = AssessmentTemplate.query.options(joinedload(AssessmentTemplate.topics).joinedload(AssessmentTopic.children), joinedload(AssessmentTemplate.rubric_levels)).order_by(AssessmentTemplate.display_order).all()
        advisor_record = AdvisorAssessmentRecord.query.filter_by(student_id=student.id, semester_id=current_semester.id).first()
        advisor_scores = {score.topic_id: score.score_value for score in advisor_record.scores} if advisor_record else {}
        
        all_qualitative_scores = QualitativeScore.query.filter(
            QualitativeScore.student_id == student.id, 
            QualitativeScore.course_id.in_(course_ids)
        ).options(joinedload(QualitativeScore.course).joinedload(Course.subject)).all()
        
        scores_by_topic = defaultdict(list)
        for score in all_qualitative_scores:
            scores_by_topic[score.assessment_topic_id].append({'subject': score.course.subject.name, 'score': score.score_value})

        for template in templates:
            template_data = {'name': template.name, 'rubric_map': {r.value: r.label for r in template.rubric_levels}, 'topics': []}
            for main_topic in sorted([t for t in template.topics if not t.parent_id], key=lambda t: t.id):
                template_data['topics'].append({
                    'name': main_topic.name, 
                    'advisor_score': advisor_scores.get(main_topic.id), 
                    'detailed_scores': scores_by_topic.get(main_topic.id, [])
                })
            assessment_summary.append(template_data)

    current_enrollment = student.enrollments.filter(Enrollment.classroom.has(academic_year_id=current_semester.academic_year_id)).first() if current_semester else None
    
    return render_template('advisor/student_profile.html',
                           title=f"ข้อมูลนักเรียน: {student.first_name}",
                           student=student,
                           warnings=active_warnings,
                           academic_summary=academic_summary,
                           assessment_summary=assessment_summary,
                           current_enrollment=current_enrollment)

@bp.route('/remediation-overview')
@login_required
def remediation_overview():
    if not current_user.advised_classrooms:
        abort(403)

    primary_classroom = current_user.advised_classrooms[0]
    current_semester = Semester.query.filter_by(is_current=True).first_or_404()

    # Query for students in the advised classroom with failing grades
    failing_grades = db.session.query(CourseGrade, Enrollment).join(
        Enrollment, CourseGrade.student_id == Enrollment.student_id
    ).join(
        Course, CourseGrade.course_id == Course.id
    ).filter(
        Enrollment.classroom_id == primary_classroom.id,
        Course.semester_id == current_semester.id,
        CourseGrade.final_grade.in_(['0', 'ร', 'มส'])
    ).options(
        joinedload(CourseGrade.student),
        joinedload(CourseGrade.course).joinedload(Course.subject)
    ).all()
    
    stats = {
        'total_failing': len(failing_grades)
    }

    return render_template('advisor/remediation_overview.html',
                           title="ภาพรวมผลการเรียนไม่ผ่านเกณฑ์",
                           semester=current_semester,
                           stats=stats,
                           failing_students=failing_grades,
                           classroom=primary_classroom)

@bp.route('/central-assessment')
@login_required
def central_assessment():
    if not current_user.advised_classrooms: abort(403)
    primary_classroom = current_user.advised_classrooms[0]
    current_semester = Semester.query.filter_by(is_current=True).first_or_404()

    enrollments = Enrollment.query.filter_by(classroom_id=primary_classroom.id).options(joinedload(Enrollment.student)).order_by(Enrollment.roll_number).all()
    templates = AssessmentTemplate.query.order_by(AssessmentTemplate.display_order).all()
    main_topic_ids = {topic.id for template in templates for topic in template.topics if not topic.parent_id}
    total_main_topics = len(main_topic_ids)

    students_data = []
    all_students_complete = True # Assume true initially

    for en in enrollments:
        record = AdvisorAssessmentRecord.query.filter_by(student_id=en.student_id, semester_id=current_semester.id).first()
        
        completed_topics_count = 0
        if record:
            completed_topics_count = AdvisorAssessmentScore.query.with_parent(record).filter(AdvisorAssessmentScore.topic_id.in_(main_topic_ids)).count()
        
        is_complete = (completed_topics_count >= total_main_topics)
        if not is_complete:
            all_students_complete = False # If one is incomplete, the whole class is

        students_data.append({
            'student_id': en.student.id,
            'full_name': f"{(en.student.name_prefix or '')}{en.student.first_name} {en.student.last_name}".strip(),
            'student_code': en.student.student_id,
            'roll_number': en.roll_number,
            'is_complete': is_complete
        })

    return render_template(
        'advisor/central_assessment.html',
        title="ศูนย์บัญชาการประเมินผล",
        classroom=primary_classroom,
        students_data=students_data,
        templates=templates
    )

@bp.route('/api/advisor/sub-topic-details/student/<int:student_id>/topic/<int:main_topic_id>')
@login_required
def get_sub_topic_details_for_advisor(student_id, main_topic_id):
    if not current_user.advised_classrooms:
        abort(403)

    current_semester = Semester.query.filter_by(is_current=True).first_or_404()
    primary_classroom = current_user.advised_classrooms[0]

    main_topic = db.session.get(AssessmentTopic, main_topic_id)
    if not main_topic or not main_topic.children:
        return jsonify({'error': 'Main topic or sub-topics not found'}), 404
    
    sub_topics = main_topic.children
    sub_topic_ids = [st.id for st in sub_topics]
    
    student_courses = Course.query.filter_by(
        classroom_id=primary_classroom.id, 
        semester_id=current_semester.id
    ).options(joinedload(Course.subject)).all()
    course_ids = [c.id for c in student_courses]
    course_map = {c.id: c.subject.name for c in student_courses}

    scores = QualitativeScore.query.filter(
        QualitativeScore.student_id == student_id,
        QualitativeScore.assessment_topic_id.in_(sub_topic_ids),
        QualitativeScore.course_id.in_(course_ids)
    ).all()

    detailed_scores_by_subtopic = defaultdict(list)
    recommended_scores_by_subtopic = {}
    
    scores_grouped_by_subtopic = defaultdict(list)
    for score in scores:
        scores_grouped_by_subtopic[score.assessment_topic_id].append(score)

    for sub_topic in sub_topics:
        score_list = scores_grouped_by_subtopic.get(sub_topic.id, [])
        
        for score in score_list:
            detailed_scores_by_subtopic[sub_topic.id].append({
                'subject': course_map.get(score.course_id, 'N/A'),
                'score': score.score_value
            })
            
        raw_scores = [s.score_value for s in score_list]
        if raw_scores:
            try:
                recommended_scores_by_subtopic[sub_topic.id] = mode(raw_scores)
            except StatisticsError:
                recommended_scores_by_subtopic[sub_topic.id] = raw_scores[0]

    # --- START: THE FIX IS HERE ---
    # Query for the advisor's already saved scores for these sub-topics
    advisor_record = AdvisorAssessmentRecord.query.filter_by(student_id=student_id, semester_id=current_semester.id).first()
    advisor_scores = {}
    if advisor_record:
        advisor_scores = {
            score.topic_id: score.score_value 
            for score in advisor_record.scores 
            if score.topic_id in sub_topic_ids
        }
    # --- END: THE FIX IS HERE ---

    template = main_topic.template
    rubric_map = {r.value: r.label for r in template.rubric_levels}

    response_data = {
        'sub_topics': [{'id': st.id, 'name': st.name} for st in sorted(sub_topics, key=lambda x: x.id)],
        'recommended_scores': recommended_scores_by_subtopic,
        'detailed_scores': detailed_scores_by_subtopic,
        'rubric_map': rubric_map,
        'rubrics': [{'value': r.value, 'label': r.label} for r in sorted(template.rubric_levels, key=lambda x: x.value, reverse=True)],
        'advisor_scores': advisor_scores # <-- Send the saved scores to the frontend
    }
    
    return jsonify(response_data)

@bp.route('/api/advisor/submit-assessment', methods=['POST'])
@login_required
def submit_advisor_assessment():
    if not current_user.advised_classrooms: abort(403)
    data = request.get_json()
    record_ids = data.get('record_ids', [])

    if not record_ids:
        return jsonify({'status': 'error', 'message': 'No records to submit'}), 400

    # Security check: ensure the advisor is only submitting records they own
    updated_count = AdvisorAssessmentRecord.query.filter(
        AdvisorAssessmentRecord.id.in_(record_ids),
        AdvisorAssessmentRecord.advisor_id == current_user.id
    ).update({'status': 'Submitted to Head'}, synchronize_session=False)

    if updated_count > 0:
        db.session.commit()
    
    return jsonify({'status': 'success', 'message': f'ส่งผลการประเมิน {updated_count} รายการเรียบร้อยแล้ว'})

@bp.route('/api/assessment-workspace/student/<int:student_id>')
@login_required
def get_assessment_workspace_data(student_id):
    if not current_user.advised_classrooms: abort(403)
    student = db.session.get(Student, student_id)
    if not student: return jsonify({'error': 'Student not found'}), 404
    
    current_semester = Semester.query.filter_by(is_current=True).first_or_404()
    enrollment = Enrollment.query.join(Classroom).filter(
        Enrollment.student_id == student_id,
        Classroom.academic_year_id == current_semester.academic_year_id
    ).first()
    if not enrollment: return jsonify({'error': 'Enrollment not found'}), 404

    templates = AssessmentTemplate.query.options(
        joinedload(AssessmentTemplate.topics).joinedload(AssessmentTopic.children),
        joinedload(AssessmentTemplate.rubric_levels)
    ).order_by(AssessmentTemplate.display_order).all()
    
    student_courses = Course.query.filter_by(classroom_id=enrollment.classroom_id, semester_id=current_semester.id).all()
    course_ids = [c.id for c in student_courses]

    all_qualitative_scores = QualitativeScore.query.filter(
        QualitativeScore.student_id == student_id,
        QualitativeScore.course_id.in_(course_ids)
    ).options(joinedload(QualitativeScore.course).joinedload(Course.subject)).all()
    
    scores_by_topic = defaultdict(list)
    for score in all_qualitative_scores:
        scores_by_topic[score.assessment_topic_id].append({'subject': score.course.subject.name, 'score': score.score_value})

    advisor_record = AdvisorAssessmentRecord.query.filter_by(student_id=student_id, semester_id=current_semester.id).first()
    advisor_scores = {score.topic_id: score.score_value for score in advisor_record.scores} if advisor_record else {}

    overall_summary_mode = "ยังไม่มีข้อมูล"
    if advisor_scores:
        # Get only scores from main topics for the calculation
        main_topic_ids = {t.id for tmpl in templates for t in tmpl.topics if not t.parent_id}
        main_scores = [score for topic_id, score in advisor_scores.items() if topic_id in main_topic_ids]

        if main_scores:
            try:
                calculated_mode = mode(main_scores)
            except StatisticsError: # Handle cases with ties
                calculated_mode = max(main_scores)
            
            # Find the label for the mode value (assuming rubrics are consistent)
            if templates and templates[0].rubric_levels:
                rubric_map = {r.value: r.label for r in templates[0].rubric_levels}
                overall_summary_mode = rubric_map.get(calculated_mode, "N/A")

    response_data = {'templates': [], 'overall_summary_mode': overall_summary_mode} # Add new key to response
    for template in templates:
        rubric_map = {r.value: r.label for r in template.rubric_levels}
        template_data = {
            'id': template.id,
            'name': template.name,
            'rubrics': sorted([{'value': r.value, 'label': r.label} for r in template.rubric_levels], key=lambda x: x['value'], reverse=True),
            'topics': []
        }
        main_topics = sorted([t for t in template.topics if not t.parent_id], key=lambda t: t.id)
        for topic in main_topics:
            topic_info = {
                'id': topic.id,
                'name': topic.name,
                'has_sub_topics': bool(topic.children),
                'advisor_score': advisor_scores.get(topic.id),
                'evidence_scores': scores_by_topic.get(topic.id, []),
                'sub_topics': []
            }
            if topic.children:
                for sub_topic in sorted(topic.children, key=lambda x: x.id):
                    topic_info['sub_topics'].append({
                        'id': sub_topic.id,
                        'name': sub_topic.name,
                        'advisor_score': advisor_scores.get(sub_topic.id),
                        'evidence_scores': scores_by_topic.get(sub_topic.id, [])
                    })
            template_data['topics'].append(topic_info)
        response_data['templates'].append(template_data)
        
    return jsonify(response_data)

@bp.route('/api/advisor/save-assessment', methods=['POST'])
@login_required
def save_advisor_assessment():
    if not current_user.advised_classrooms: abort(403)
    data = request.get_json()
    student_id = data.get('student_id')
    scores_to_save = data.get('scores') # List of {'topic_id': X, 'score_value': Y}
    current_semester = Semester.query.filter_by(is_current=True).first_or_404()

    if not student_id or not scores_to_save:
         return jsonify({'status': 'error', 'message': 'Missing data'}), 400

    try:
        record = AdvisorAssessmentRecord.query.filter_by(student_id=student_id, semester_id=current_semester.id).first()
        is_new_record = False
        if not record:
            record = AdvisorAssessmentRecord(student_id=student_id, semester_id=current_semester.id, advisor_id=current_user.id)
            db.session.add(record)
            db.session.flush() # Get record ID
            is_new_record = True

        existing_scores = {s.topic_id: s for s in record.scores}
        changes_old = {}
        changes_new = {}

        for item in scores_to_save:
            topic_id = item.get('topic_id')
            score_value = item.get('score_value')
            if topic_id is None or score_value is None: continue # Skip invalid items

            # Ensure score_value is integer if needed by model
            try: score_value = int(score_value)
            except (ValueError, TypeError): continue # Skip if not convertible to int

            if topic_id in existing_scores:
                if existing_scores[topic_id].score_value != score_value:
                    changes_old[topic_id] = existing_scores[topic_id].score_value
                    changes_new[topic_id] = score_value
                    existing_scores[topic_id].score_value = score_value
            else:
                changes_old[topic_id] = None
                changes_new[topic_id] = score_value
                new_score = AdvisorAssessmentScore(record_id=record.id, topic_id=topic_id, score_value=score_value)
                db.session.add(new_score)

        # --- [START LOG] Log changes before commit ---
        log_msg_prefix = "Create Advisor Assessment Record" if is_new_record else "Update Advisor Assessment Scores"
        if changes_old or changes_new: # Only log if there were changes or it's a new record
            log_action(
                log_msg_prefix, model=AdvisorAssessmentRecord, record_id=record.id,
                old_value=changes_old if not is_new_record else None,
                new_value=changes_new
            )
        # --- [END LOG] ---

        db.session.commit()
        return jsonify({'status': 'success', 'message': 'บันทึกผลการประเมินเรียบร้อยแล้ว'})

    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Error saving advisor assessment for student {student_id}: {e}", exc_info=True)
        # --- [START LOG] Log failure ---
        log_action(f"Save Advisor Assessment Failed: {type(e).__name__}", model=AdvisorAssessmentRecord, record_id=record.id if 'record' in locals() and not is_new_record else None)
        try: db.session.commit()
        except: db.session.rollback()
        # --- [END LOG] ---
        return jsonify({'status': 'error', 'message': f'Database error: {e}'}), 500

@bp.route('/api/advisor/bulk-assess', methods=['POST'])
@login_required
def bulk_assess_students():
    if not current_user.advised_classrooms: abort(403)
    data = request.get_json()
    main_topic_id = data.get('topic_id')
    score_value = data.get('score_value')
    classroom_id = data.get('classroom_id')

    if not all([main_topic_id, score_value is not None, classroom_id]):
        return jsonify({'status': 'error', 'message': 'Missing required data'}), 400

    if int(classroom_id) not in [c.id for c in current_user.advised_classrooms]:
        abort(403)

    main_topic = db.session.get(AssessmentTopic, main_topic_id)
    if not main_topic:
        return jsonify({'status': 'error', 'message': 'Topic not found'}), 404
        
    topic_ids_to_update = [main_topic.id]
    if main_topic.children:
        topic_ids_to_update.extend([child.id for child in main_topic.children])

    current_semester = Semester.query.filter_by(is_current=True).first_or_404()
    enrollments = Enrollment.query.filter_by(classroom_id=classroom_id).all()
    student_ids = [en.student_id for en in enrollments]

    for student_id in student_ids:
        record = AdvisorAssessmentRecord.query.filter_by(student_id=student_id, semester_id=current_semester.id).first()
        if not record:
            record = AdvisorAssessmentRecord(student_id=student_id, semester_id=current_semester.id, advisor_id=current_user.id)
            db.session.add(record)
            db.session.flush()
        
        for topic_id in topic_ids_to_update:
            score_obj = AdvisorAssessmentScore.query.filter_by(record_id=record.id, topic_id=topic_id).first()
            if score_obj:
                score_obj.score_value = score_value
            else:
                new_score = AdvisorAssessmentScore(record_id=record.id, topic_id=topic_id, score_value=score_value)
                db.session.add(new_score)

    db.session.commit()
    return jsonify({'status': 'success', 'message': f'ประเมินนักเรียน {len(student_ids)} คนเรียบร้อยแล้ว'})

@bp.route('/api/advisor/submit-class-assessment', methods=['POST'])
@login_required
def submit_class_assessment():
    if not current_user.advised_classrooms: abort(403)
    data = request.get_json()
    classroom_id = data.get('classroom_id')
    if not classroom_id: return jsonify({'status': 'error', 'message': 'Classroom ID is required.'}), 400
    if int(classroom_id) not in [c.id for c in current_user.advised_classrooms]: abort(403)

    current_semester = Semester.query.filter_by(is_current=True).first_or_404()

    records_to_submit = db.session.query(AdvisorAssessmentRecord).join(
        Enrollment, AdvisorAssessmentRecord.student_id == Enrollment.student_id
    ).filter(
        Enrollment.classroom_id == classroom_id,
        AdvisorAssessmentRecord.semester_id == current_semester.id,
        AdvisorAssessmentRecord.status == 'Draft' # Only submit drafts
    ).options(db.load_only(AdvisorAssessmentRecord.id)).all()

    if not records_to_submit:
        return jsonify({'status': 'info', 'message': 'ไม่พบรายการที่ต้องส่ง หรืออาจส่งไปแล้ว'}), 200

    record_ids = [r.id for r in records_to_submit]
    new_status = 'Submitted to Head' # Assuming this is the next step
    old_status = 'Draft'

    try:
        updated_count = AdvisorAssessmentRecord.query.filter(
             AdvisorAssessmentRecord.id.in_(record_ids)
        ).update({'status': new_status, 'submitted_at': datetime.utcnow()}, synchronize_session=False)

        # --- [START LOG] Log bulk submission ---
        log_action(
            "Submit Class Assessment (Advisor)", model=AdvisorAssessmentRecord,
            new_value={'count': updated_count, 'new_status': new_status, 'classroom_id': classroom_id},
            old_value={'old_status': old_status}
        )
        # --- [END LOG] ---

        db.session.commit()
        try:
            # ค้นหา Classroom และ Grade Head
            classroom = db.session.get(Classroom, int(classroom_id))
            if classroom and classroom.grade_level and classroom.grade_level.head:
                grade_head = classroom.grade_level.head
                title = "แจ้งเตือนการส่งผลประเมินคุณลักษณะ"
                message = f"ครูที่ปรึกษา {current_user.full_name} ได้ส่งผลการประเมินของห้อง {classroom.name} จำนวน {len(records_to_submit)} คน เพื่อรอการตรวจสอบ"
                url_for_head = url_for('grade_level_head.review_assessments', grade_level_id=classroom.grade_level_id, _external=True)

                new_notif = Notification(
                    user_id=grade_head.id,
                    title=title,
                    message=message,
                    url=url_for_head,
                    notification_type='ASSESSMENT_SUBMITTED'
                )
                db.session.add(new_notif)
                db.session.commit()
        except Exception as e:
            current_app.logger.error(f"Failed to send submit assessment notification: {e}", exc_info=True)
            pass
        return jsonify({'status': 'success', 'message': f'ส่งผลการประเมินจำนวน {len(records_to_submit)} คนเรียบร้อยแล้ว'})

    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Error submitting class assessment for classroom {classroom_id}: {e}", exc_info=True)
        # --- [START LOG] Log failure ---
        log_action(f"Submit Class Assessment Failed (Advisor): {type(e).__name__}", model=AdvisorAssessmentRecord, new_value={'classroom_id': classroom_id})
        try: db.session.commit()
        except: db.session.rollback()
        # --- [END LOG] ---
        return jsonify({'status': 'error', 'message': f'Database error: {e}'}), 500

@bp.route('/repeat-candidates')
@login_required
# @advisor_required # Add role check
def repeat_candidates():
    """Displays students flagged for potential repetition for the advisor to review."""
    form = FlaskForm() # For CSRF
    # Find students advised by the current user who are flagged
    # We need the academic year they failed in to display context
    candidates = db.session.query(RepeatCandidate).join(
        RepeatCandidate.student
    ).join(
        Enrollment, RepeatCandidate.previous_enrollment_id == Enrollment.id
    ).join(
        Classroom, Enrollment.classroom_id == Classroom.id
    ).join(
        classroom_advisors
    ).filter(
        # Filter by advisor ID association with the classroom of the *previous* enrollment
        classroom_advisors.c.user_id == current_user.id,
        # Only show candidates pending advisor review
        RepeatCandidate.status == 'Pending Advisor Review'
    ).options(
        joinedload(RepeatCandidate.student),
        joinedload(RepeatCandidate.previous_enrollment).joinedload(Enrollment.classroom).joinedload(Classroom.academic_year),
        joinedload(RepeatCandidate.academic_year) # Year failed
    ).order_by(RepeatCandidate.created_at.desc()).all()

    return render_template('advisor/repeat_candidates.html',
                           title='นักเรียนรอพิจารณาซ้ำชั้น',
                           candidates=candidates,
                           form=form)

@bp.route('/repeat-candidates/submit/<int:candidate_id>', methods=['POST'])
@login_required
# @advisor_required
def submit_repeat_decision(candidate_id):
    candidate = db.session.get(RepeatCandidate, candidate_id)
    # ... (Security check - unchanged) ...
    is_advisor = db.session.query(classroom_advisors).filter(
        classroom_advisors.c.user_id == current_user.id,
        classroom_advisors.c.classroom_id == candidate.previous_enrollment.classroom_id
    ).count() > 0
    if not candidate or not is_advisor or candidate.status != 'Pending Advisor Review':
        flash('ไม่พบข้อมูลหรือไม่มีสิทธิ์ดำเนินการ', 'danger')
        return redirect(url_for('advisor.repeat_candidates'))

    decision = request.form.get('decision') # 'repeat' or 'promote'
    notes = request.form.get('notes', '')
    original_status = candidate.status
    new_status = None
    final_decision_tentative = None

    if decision == 'repeat':
        new_status = 'Pending Grade Head Review (Repeat)'
        final_decision_tentative = 'Repeat'
    elif decision == 'promote':
        new_status = 'Pending Grade Head Review (Promote)'
        final_decision_tentative = 'Promote (Special Case)'
    else:
        flash('กรุณาเลือกการดำเนินการ', 'warning')
        return redirect(url_for('advisor.repeat_candidates'))

    try:
        candidate.status = new_status
        candidate.final_decision = final_decision_tentative
        candidate.advisor_notes = notes

        # --- [START LOG] Log advisor decision ---
        log_action(
            f"Advisor Review Repeat Candidate ({decision})", model=RepeatCandidate, record_id=candidate.id,
            old_value=original_status,
            new_value={'status': new_status, 'decision': final_decision_tentative, 'notes': notes}
        )
        # --- [END LOG] ---

        db.session.commit()
        try:
            # ค้นหา Grade Head จาก Classroom ของนักเรียน
            grade_level = candidate.previous_enrollment.classroom.grade_level
            if grade_level and grade_level.head:
                grade_head = grade_level.head
                title = "แจ้งเตือนการพิจารณาเลื่อนชั้น/ซ้ำชั้น"
                message = f"ครูที่ปรึกษา {current_user.full_name} ได้ส่งเรื่องของ {candidate.student.full_name} ({final_decision_tentative}) เพื่อรอการพิจารณาต่อ"
                url_for_head = url_for('grade_level_head.review_repeat_candidates', _external=True)

                new_notif = Notification(
                    user_id=grade_head.id,
                    title=title,
                    message=message,
                    url=url_for_head,
                    notification_type='REPEAT_CANDIDATE_SUBMITTED'
                )
                db.session.add(new_notif)
                db.session.commit()
        except Exception as e:
            current_app.logger.error(f"Failed to send repeat candidate submission notification: {e}", exc_info=True)
            pass
        flash(f'ส่งเรื่องของ {candidate.student.first_name} ให้หัวหน้าสายชั้นพิจารณาเรียบร้อยแล้ว', 'success')
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Error submitting advisor decision for candidate {candidate_id}: {e}", exc_info=True)
        # --- [START LOG] Log failure ---
        log_action(f"Advisor Review Repeat Candidate Failed: {type(e).__name__}", model=RepeatCandidate, record_id=candidate.id)
        try: db.session.commit()
        except: db.session.rollback()
        # --- [END LOG] ---
        flash(f'เกิดข้อผิดพลาด: {e}', 'danger')

    return redirect(url_for('advisor.repeat_candidates'))

def _calculate_student_summary(student, semester):
    """
    คำนวณข้อมูลเกรดสรุปของนักเรียนสำหรับทุกวิชาในภาคเรียนที่กำหนด
    """
    academic_summary = []
    
    # 1. ค้นหา Enrollment ของนักเรียนในเทอม/ปี นี้
    enrollment = student.enrollments.filter(
        Enrollment.classroom.has(academic_year_id=semester.academic_year_id)
    ).first()
    
    if not enrollment:
        return [] # นักเรียนไม่ได้ลงทะเบียนในเทอมนี้

    # 2. ค้นหาทุก Course ที่ห้องเรียนนี้ลงทะเบียนในเทอมนี้
    enrolled_courses = Course.query.filter_by(
        classroom_id=enrollment.classroom_id, 
        semester_id=semester.id
    ).options(
        joinedload(Course.subject), 
        joinedload(Course.lesson_plan).selectinload(LessonPlan.learning_units)
    ).all()
    
    if not enrolled_courses:
        return []

    course_ids = {c.id for c in enrolled_courses}
    
    # 3. ดึงเกรดกลางภาค/ปลายภาค (ถ้ามี)
    student_course_grades = [cg for cg in student.course_grades if cg.course_id in course_ids]
    grades_map = {cg.course_id: cg for cg in student_course_grades}
    
    # 4. ดึงคะแนนเก็บ (Scores) ทั้งหมดของนักเรียนสำหรับคอร์สเหล่านี้
    item_ids_query = db.session.query(GradedItem.id).join(LearningUnit).join(LessonPlan).filter(
        LessonPlan.id.in_([c.lesson_plan_id for c in enrolled_courses if c.lesson_plan_id])
    )
    scores_list = Score.query.filter(
        Score.student_id == student.id,
        Score.graded_item_id.in_(item_ids_query)
    ).all()
    scores_map = defaultdict(float)
    for s in scores_list:
        scores_map[s.graded_item.learning_unit.lesson_plan_id] += (s.score or 0)

    # 5. ดึงคะแนนเต็มของ GradedItem
    graded_items_list = GradedItem.query.filter(GradedItem.id.in_(item_ids_query)).all()
    max_scores_map = defaultdict(float)
    for i in graded_items_list:
        max_scores_map[i.learning_unit.lesson_plan_id] += (i.max_score or 0)
    
    # 6. ดึงสถานะการขาดเรียน (สำหรับ มส.)
    active_warnings = set(w.course_id for w in AttendanceWarning.query.filter_by(student_id=student.id, status='ACTIVE'))
    
    # ฟังก์ชันแปลงเกรด
    def map_to_grade(p):
        if p >= 80: return '4'
        if p >= 75: return '3.5'
        if p >= 70: return '3'
        if p >= 65: return '2.5'
        if p >= 60: return '2'
        if p >= 55: return '1.5'
        if p >= 50: return '1'
        return '0'

    # 7. วนลูปสร้างสรุปผล
    for course in enrolled_courses:
        grade_obj = grades_map.get(course.id)
        lesson_plan = course.lesson_plan
        
        collected_score = scores_map[course.lesson_plan_id]
        max_collected_score = max_scores_map[course.lesson_plan_id]
        
        midterm_score = grade_obj.midterm_score if grade_obj else None
        final_score = grade_obj.final_score if grade_obj else None
        
        total_midterm_max = 0
        total_final_max = 0
        has_summative_items = False # (ตรรกะสำหรับ 'ร' - ยังไม่ได้อิมพลีเมนต์)

        if lesson_plan:
            total_midterm_max = sum(unit.midterm_score for unit in lesson_plan.learning_units if unit.midterm_score)
            total_final_max = sum(unit.final_score for unit in lesson_plan.learning_units if unit.final_score)

        student_total_score = (collected_score or 0) + (midterm_score or 0) + (final_score or 0)
        grand_max_score = (max_collected_score or 0) + total_midterm_max + total_final_max
        
        percentage = (student_total_score / grand_max_score * 100) if grand_max_score > 0 else 0
        
        final_grade = map_to_grade(percentage)
        
        # 8. ตรวจสอบ 'มส' (ต้องมีตรรกะการเช็ค 'ร' เพิ่มเติมถ้าต้องการ)
        if course.id in active_warnings:
            final_grade = 'มส'
        # (เพิ่มตรรกะเช็ค 'ร' ที่นี่ ถ้าจำเป็น)

        academic_summary.append({
            'course': course,
            'grade': final_grade,
            'credit': course.subject.credit,
            'percentage': percentage
        })
        
    return academic_summary

@bp.route('/gradebook-summary')
@login_required
def gradebook_summary():
    # 1. ตรวจสอบสิทธิ์ (เหมือนเดิม)
    if not current_user.has_role('Advisor'):
        abort(403)

    # 2. ดึงภาคเรียนทั้งหมด (เหมือนเดิม)
    all_semesters = Semester.query.options(
        joinedload(Semester.academic_year)
    ).order_by(Semester.id.desc()).all()
    
    current_semester_obj = next((s for s in all_semesters if s.is_current), None)
    
    # 4. หาภาคเรียนที่จะแสดง (เหมือนเดิม)
    selected_semester_id = request.args.get('semester_id', type=int)
    semester_to_show = None

    if selected_semester_id:
        semester_to_show = next((s for s in all_semesters if s.id == selected_semester_id), None)
    
    if not semester_to_show:
        semester_to_show = current_semester_obj

    if not semester_to_show:
        flash('ไม่พบข้อมูลภาคเรียน (กรุณาติดต่อ Admin เพื่อตั้งค่าภาคเรียนในระบบ)', 'danger')
        return render_template('advisor/gradebook_summary.html', title='สรุปผลการเรียน', advised_classrooms=[], all_semesters=[])

    # --- [START] 🔽 [ตรรกะใหม่ที่แก้ไขแล้ว] 🔽 ---
    
    # 6. ดึง ID ปีการศึกษาจากภาคเรียนที่เลือก (เหมือนเดิม)
    selected_academic_year_id = semester_to_show.academic_year_id

    # 7. [แก้ไข] Query หาห้องเรียนที่ user นี้เป็นที่ปรึกษา "โดยตรง"
    # โดยกรองจาก "ปีการศึกษาที่เลือก" ทันที
    # (เราจะไม่ใช้ current_user.advised_classrooms อีกต่อไป)
    advised_classrooms_in_year = Classroom.query.join(
        classroom_advisors
    ).filter(
        classroom_advisors.c.user_id == current_user.id,
        Classroom.academic_year_id == selected_academic_year_id
    ).order_by(Classroom.name).all()
    
    # 9. ตรวจสอบว่ามีห้องเรียนในปีนั้นหรือไม่ (เหมือนเดิม)
    if not advised_classrooms_in_year:
        flash(f'คุณไม่ได้เป็นที่ปรึกษาห้องเรียนใดๆ ในปีการศึกษา {semester_to_show.academic_year.year}', 'info')
        return render_template('advisor/gradebook_summary.html',
                               title='สรุปผลการเรียน',
                               advised_classrooms=[], # ส่งลิสต์ว่างไป
                               all_semesters=all_semesters,
                               selected_semester_id=semester_to_show.id,
                               selected_classroom_id=None,
                               enrollments=None,
                               courses=None,
                               gpa_map={},
                               grade_matrix={})

    # --- [END] 🔼 [ตรรกะใหม่ที่แก้ไขแล้ว] 🔼 ---

    # 10. หาห้องเรียนที่จะแสดง (จากลิสต์ที่กรองแล้ว) (เหมือนเดิม)
    selected_classroom_id = request.args.get('classroom_id', type=int)
    classroom_to_show = None

    if selected_classroom_id:
        classroom_to_show = next((c for c in advised_classrooms_in_year if c.id == selected_classroom_id), None)
    
    if not classroom_to_show:
        classroom_to_show = advised_classrooms_in_year[0]


    # 11. ดึงข้อมูลนักเรียนและวิชา (เหมือนเดิม)
    enrollments = Enrollment.query.filter_by(
        classroom_id=classroom_to_show.id
    ).join(Student).options(
        contains_eager(Enrollment.student)
    ).order_by(Enrollment.roll_number, Student.student_id).all()
    
    courses = Course.query.filter_by(
        classroom_id=classroom_to_show.id,
        semester_id=semester_to_show.id
    ).join(Subject).options(
        joinedload(Course.subject)
    ).order_by(Subject.subject_code).all()

    # 12. สร้าง Matrix เกรด (เหมือนเดิม)
    grade_matrix = {}
    gpa_map = {}
    grade_point_map = {
        '4': 4.0, '3.5': 3.5, '3': 3.0, '2.5': 2.5,
        '2': 2.0, '1.5': 1.5, '1': 1.0, '0': 0.0
    }

    for enrollment in enrollments:
        student = enrollment.student
        summary_list = _calculate_student_summary(student, semester_to_show)
        
        student_grades = {}
        total_credits = 0.0
        total_grade_points = 0.0
        
        for summary in summary_list:
            subject_id = summary['course'].subject_id
            grade_val = summary['grade']
            credit = summary['credit'] or 0.0
            
            student_grades[subject_id] = grade_val
            
            grade_point = grade_point_map.get(grade_val)
            
            if grade_point is not None:
                total_credits += credit
                total_grade_points += (grade_point * credit)

        grade_matrix[student.id] = student_grades
        gpa_map[student.id] = (total_grade_points / total_credits) if total_credits > 0 else 0.0

    # 13. ส่งตัวแปรที่กรองแล้ว (advised_classrooms_in_year) ไปยัง Template (เหมือนเดิม)
    return render_template('advisor/gradebook_summary.html',
                           title=f"สรุปผลการเรียนห้อง {classroom_to_show.name}",
                           advised_classrooms=advised_classrooms_in_year,
                           selected_classroom_id=classroom_to_show.id,
                           all_semesters=all_semesters,
                           selected_semester_id=semester_to_show.id,
                           enrollments=enrollments,
                           courses=courses,
                           grade_matrix=grade_matrix,
                           gpa_map=gpa_map
                           )