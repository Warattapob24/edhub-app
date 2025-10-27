# In app/grade_level_head/routes.py (REPLACE ALL CONTENT)
from flask import current_app, flash, redirect, render_template, abort, jsonify, request, url_for
from flask_login import login_required, current_user
from flask_wtf import FlaskForm
from sqlalchemy import func
from sqlalchemy.orm import joinedload
from collections import defaultdict
from datetime import datetime

from app.services import log_action

from . import bp
from app import db
from app.models import (
    AdvisorAssessmentRecord, AdvisorAssessmentScore, CourseGrade, RepeatCandidate, Student, 
    Semester, Classroom, Enrollment, AssessmentTemplate, AssessmentTopic, 
    Course, QualitativeScore, Subject
)

# ==========================================================
# [1] หน้า DASHBOARD (เวอร์ชันแก้ไขพร้อมแก้ progress bar และ chart)
# ==========================================================
@bp.route('/dashboard')
@login_required
def dashboard():
    grade_level = getattr(current_user, 'led_grade_level', None)
    if not grade_level:
        abort(403)

    current_semester = Semester.query.filter_by(is_current=True).first_or_404()
    
    student_ids_in_level = db.session.query(Student.id).join(Enrollment).join(Classroom).filter(
        Classroom.grade_level_id == grade_level.id,
        Classroom.academic_year_id == current_semester.academic_year_id
    ).scalar_subquery()

    failing_grades = db.session.query(CourseGrade, Enrollment).join(
        Enrollment, CourseGrade.student_id == Enrollment.student_id
    ).join(
        Course, CourseGrade.course_id == Course.id
    ).filter(
        CourseGrade.student_id.in_(student_ids_in_level),
        Course.semester_id == current_semester.id,
        CourseGrade.final_grade.in_(['0', 'ร', 'มส'])
    ).options(
        joinedload(CourseGrade.student),
        joinedload(CourseGrade.course).joinedload(Course.subject)
    ).all()

    records_in_process = db.session.query(AdvisorAssessmentRecord, Enrollment).join(
        Enrollment, AdvisorAssessmentRecord.student_id == Enrollment.student_id
    ).filter(
        Enrollment.classroom.has(grade_level_id=grade_level.id),
        AdvisorAssessmentRecord.semester_id == current_semester.id,
        AdvisorAssessmentRecord.status.notin_(['Draft']) 
    ).options(
        joinedload(AdvisorAssessmentRecord.student),
        joinedload(AdvisorAssessmentRecord.advisor), 
        joinedload(Enrollment.classroom).joinedload(Classroom.advisors),
        joinedload(AdvisorAssessmentRecord.scores).joinedload(AdvisorAssessmentScore.topic)
    ).order_by(Enrollment.classroom_id, Enrollment.roll_number).all()

    records_by_classroom = defaultdict(lambda: {'pending': [], 'forwarded': [], 'advisors': []}) 
    processed_classrooms = set()
    all_pending_records = [] 
    
    stats = { 'attention_students': len(failing_grades) }
    
    templates = AssessmentTemplate.query.options(joinedload(AssessmentTemplate.rubric_levels), joinedload(AssessmentTemplate.topics)).all()
    first_template = next((t for t in templates if t.rubric_levels), None) 
    rubric_map = {r.value: r.label for r in first_template.rubric_levels} if first_template else {}

    for record, enrollment in records_in_process:
        classroom = enrollment.classroom
        classroom_name = classroom.name
        
        if classroom.id not in processed_classrooms:
            records_by_classroom[classroom_name]['advisors'] = [adv.first_name for adv in classroom.advisors]
            processed_classrooms.add(classroom.id)
        
        summary_dist = defaultdict(int)
        for score in record.scores:
            if score.topic and score.topic.parent_id is None: 
                label = rubric_map.get(score.score_value, 'N/A')
                summary_dist[label] += 1
        
        # --- FIX: แปลงค่าเป็น int ทุกตัว ---
        summary_dist_int = {k: int(v) for k, v in summary_dist.items()}
        item_tuple = (record, enrollment, summary_dist_int)

        if record.status == 'Submitted to Head':
            records_by_classroom[classroom_name]['pending'].append(item_tuple)
            all_pending_records.append(record)
        else:
            records_by_classroom[classroom_name]['forwarded'].append(item_tuple)

    total_pending = len(all_pending_records)
    stats['pending_approvals'] = total_pending

    # --- Prepare Stacked Bar Chart ---
    assessment_stats_by_template = {}

    templates = AssessmentTemplate.query.options(
        joinedload(AssessmentTemplate.rubric_levels),
        joinedload(AssessmentTemplate.topics)
    ).all()

    for template in templates:
        assessment_stats_by_template[template.id] = {
            'id': template.id,
            'name': template.name,
            'topic_labels': [],
            'datasets': []
        }

    if records_in_process:
        all_record_ids = [r.id for r, e in records_in_process]
        all_scores = db.session.query(AdvisorAssessmentScore).options(
            joinedload(AdvisorAssessmentScore.topic)
        ).filter(
            AdvisorAssessmentScore.record_id.in_(all_record_ids)
        ).all()

        scores_by_template = defaultdict(lambda: defaultdict(lambda: defaultdict(int)))

        for score in all_scores:
            if score.topic and score.topic.template_id and score.topic.parent_id is None:
                scores_by_template[score.topic.template_id][score.topic.name][score.score_value] += 1
        for template_obj in templates:
            if not template_obj.rubric_levels:
                continue
            rubric_map_local = {r.value: r.label for r in template_obj.rubric_levels}
            topic_labels = sorted(scores_by_template[template_obj.id].keys())
            rubric_values_sorted = sorted(rubric_map_local.keys(), reverse=True)
            datasets = []

            colors = {
                'ดีเยี่ยม': 'rgba(40, 167, 69, 0.7)',
                'ดี': 'rgba(0, 123, 255, 0.7)',
                'ผ่าน': 'rgba(255, 193, 7, 0.7)',
                'ไม่ผ่าน': 'rgba(220, 53, 69, 0.7)'
            }

            for rubric_value in rubric_values_sorted:
                label = rubric_map_local[rubric_value]
                data = [
                    int(scores_by_template[template_obj.id][topic].get(rubric_value, 0))
                    for topic in topic_labels
                ]
                datasets.append({
                    'label': label,
                    'data': data,
                    'backgroundColor': colors.get(label, 'rgba(108, 117, 125, 0.7)')
                })

            assessment_stats_by_template[template_obj.id]['topic_labels'] = topic_labels
            assessment_stats_by_template[template_obj.id]['datasets'] = datasets
    # --- Prepare Chart Data for Template ---
    chart_labels = []
    chart_datasets = []

    if assessment_stats_by_template:
        # ใช้ template แรกเป็นค่าเริ่มต้น
        first_template = next(iter(assessment_stats_by_template.values()))
        chart_labels = first_template['topic_labels']
        chart_datasets = first_template['datasets']

    return render_template('grade_level_head/dashboard.html',
                           title=f'แดชบอร์ดหัวหน้าสายชั้น {grade_level.name}',
                           chart_labels=chart_labels,
                           chart_datasets=chart_datasets,                           
                           total_pending=total_pending,
                           stats=stats,
                           failing_students=failing_grades,
                           records_by_classroom=dict(records_by_classroom),
                           assessment_stats=assessment_stats_by_template)

# ==========================================================
# [2] หน้า ASSESSMENT APPROVAL (โค้ดที่ถูกต้อง)
# ==========================================================
@bp.route('/assessment-approval')
@login_required
def assessment_approval():
    # (โค้ดส่วนนี้จากครั้งที่แล้ว ถูกต้อง 100% ครับ)
    grade_level = getattr(current_user, 'led_grade_level', None)
    if not grade_level:
        abort(403)

    current_semester = Semester.query.filter_by(is_current=True).first_or_404()

    records_in_process = db.session.query(AdvisorAssessmentRecord, Enrollment).join(
        Enrollment, AdvisorAssessmentRecord.student_id == Enrollment.student_id
    ).join(
        Classroom, Enrollment.classroom_id == Classroom.id
    ).filter(
        Classroom.grade_level_id == grade_level.id,
        AdvisorAssessmentRecord.semester_id == current_semester.id,
        AdvisorAssessmentRecord.status.in_(['Submitted to Head', 'Submitted to Academic Affairs']) 
    ).options(
        joinedload(AdvisorAssessmentRecord.student),
        joinedload(AdvisorAssessmentRecord.advisor), 
        joinedload(Enrollment.classroom)
    ).order_by(Enrollment.classroom_id, Enrollment.roll_number).all()

    records_by_classroom = defaultdict(lambda: {'pending': [], 'forwarded': []})
    all_pending_records = []
    
    for record, enrollment in records_in_process:
        classroom_name = enrollment.classroom.name
        item_tuple = (record, enrollment) 
        
        if record.status == 'Submitted to Head':
            records_by_classroom[classroom_name]['pending'].append(item_tuple)
            all_pending_records.append(record) 
        elif record.status == 'Submitted to Academic Affairs':
            records_by_classroom[classroom_name]['forwarded'].append(item_tuple)

    total_pending = len(all_pending_records)
    chart_labels = []
    chart_datasets = []
    stats_data = defaultdict(lambda: defaultdict(int)) 
    templates = AssessmentTemplate.query.options(joinedload(AssessmentTemplate.rubric_levels)).all()
    rubric_map = {}
    
    if templates and templates[0].rubric_levels:
        first_template_rubrics = templates[0].rubric_levels
        rubric_map = {r.value: r.label for r in first_template_rubrics}
        chart_labels = sorted(list(rubric_map.values()), key=lambda x: [k for k,v in rubric_map.items() if v==x][0], reverse=True)

    if all_pending_records:
        pending_record_ids = [r.id for r in all_pending_records]
        all_pending_scores = db.session.query(AdvisorAssessmentScore).options(joinedload(AdvisorAssessmentScore.topic)).filter(
            AdvisorAssessmentScore.record_id.in_(pending_record_ids)
        ).all()
        topic_scores = defaultdict(list)
        for score in all_pending_scores:
            if score.topic and score.topic.parent_id is None: 
                topic_scores[score.topic.name].append(score.score_value)
        for topic_name, scores in topic_scores.items():
            for s in scores:
                stats_data[topic_name][rubric_map.get(s, 'N/A')] += 1
        dataset_data = []
        colors = {'ดีเยี่ยม': 'rgba(40, 167, 69, 0.7)', 'ดี': 'rgba(0, 123, 255, 0.7)', 'ผ่าน': 'rgba(255, 193, 7, 0.7)', 'ไม่ผ่าน': 'rgba(220, 53, 69, 0.7)'}
        for label in chart_labels:
            count = 0
            for topic_data in stats_data.values():
                count += topic_data.get(label, 0)
            dataset_data.append(count)
        chart_datasets = [{'label': 'จำนวนนักเรียน', 'data': dataset_data, 'backgroundColor': [colors.get(label, 'rgba(108, 117, 125, 0.7)') for label in chart_labels]}]
    
    return render_template('grade_level_head/assessment_approval.html',
                           title=f'ตรวจสอบผลประเมิน (สายชั้น {grade_level.name})',
                           total_pending=total_pending,
                           records_by_classroom=dict(records_by_classroom),
                           stats_data=stats_data, 
                           chart_labels=chart_labels, 
                           chart_datasets=chart_datasets) 

# ==========================================================
# [3] API สำหรับ MODAL (เวอร์ชันอัปเกรด)
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

    # 2. ตรวจสอบสิทธิ์
    if not record or not enrollment or enrollment.classroom.grade_level_id != current_user.led_grade_level.id:
        abort(404)

    # 3. ดึง "หลักฐาน" (Evidence Pool) ทั้งหมดของนักเรียนในเทอมนั้น
    # นี่คือคะแนนจากครูผู้สอนรายวิชา
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

    # 4. สร้าง Map ของ Rubric Levels ทั้งหมด (เพื่อใช้แปลง score_value เป็น label)
    all_templates = AssessmentTemplate.query.options(joinedload(AssessmentTemplate.rubric_levels)).all()
    global_rubric_map = {}
    for t in all_templates:
        for r in t.rubric_levels:
            # สร้าง Map ที่ครอบคลุม เช่น { (template_id, 3): 'ดีเยี่ยม', (template_id, 2): 'ดี' }
            global_rubric_map[(t.id, r.value)] = r.label

    # 5. จัดกลุ่มหลักฐานตาม Topic ID เพื่อให้ดึงใช้ง่าย
    evidence_by_topic_id = defaultdict(list)
    for q_score, subject_name in evidence_scores_query:
        # หา template_id ของ topic นี้ (อาจจะต้อง query เพิ่ม แต่เพื่อ performance เราจะลองหาจาก q_score)
        # หมายเหตุ: เราจะใช้ rubric map จาก template ของ Advisor ก่อน
        # (หากต้องการความแม่นยำสูง อาจต้อง join AssessmentTopic ใน query ด้านบนเพื่อหา template_id)
        
        evidence_by_topic_id[q_score.assessment_topic_id].append({
            'subject': subject_name,
            'score_value': q_score.score_value
            # 'score_label' จะถูกเพิ่มใน loop ถัดไปโดยใช้ rubric_map ของ template นั้นๆ
        })

    # 6. ดึงข้อมูลคะแนนสรุป (Advisor's Score)
    scores_by_topic_id = {s.topic_id: s.score_value for s in record.scores}
    
    # 7. สร้างข้อมูล JSON ที่จะส่งกลับ
    response_data = []
    templates = AssessmentTemplate.query.options(joinedload(AssessmentTemplate.topics), joinedload(AssessmentTemplate.rubric_levels)).all()

    for template in templates:
        # Rubric map สำหรับ template นี้โดยเฉพาะ
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
                
                # ประกอบร่าง "หลักฐาน" สำหรับ Topic นี้
                evidence_list_for_topic = []
                for ev in evidence_by_topic_id.get(topic.id, []):
                    evidence_list_for_topic.append({
                        'subject': ev['subject'],
                        'score_label': local_rubric_map.get(ev['score_value'], 'N/A')
                    })

                template_data['topics'].append({
                    'name': topic.name,
                    'score': score_value,
                    'evidence_scores': evidence_list_for_topic # <--- ส่งหลักฐานไปด้วย
                })

        if has_data: 
            response_data.append(template_data)
            
    return jsonify(response_data)

# ==========================================================
# [4] API สำหรับปุ่ม "ส่งต่อ" (โค้ดเดิม)
# ==========================================================
@bp.route('/api/forward-assessments', methods=['POST'])
@login_required
def forward_to_academic():
    grade_level = getattr(current_user, 'led_grade_level', None)
    if not grade_level: abort(403)

    student_ids_in_level = db.session.query(Student.id).join(Enrollment).join(Classroom).filter(Classroom.grade_level_id == grade_level.id).scalar_subquery()

    records_to_forward_q = AdvisorAssessmentRecord.query.filter(
        AdvisorAssessmentRecord.student_id.in_(student_ids_in_level),
        AdvisorAssessmentRecord.status == 'Submitted to Head'
    )
    records_to_forward = records_to_forward_q.options(db.load_only(AdvisorAssessmentRecord.id)).all()
    count = len(records_to_forward)
    new_status = 'Submitted to Academic Affairs'
    old_status = 'Submitted to Head'

    if not records_to_forward:
        return jsonify({'status': 'info', 'message': 'ไม่พบรายการที่รอการส่งต่อ'}), 200

    try:
        # Bulk update
        records_to_forward_q.update(
            {'status': new_status, 'submitted_at': datetime.utcnow()}, # Update submitted_at on forwarding
            synchronize_session=False
        )
        # --- Log Bulk Action ---
        log_action(
            "Forward Assessments to Academic (Grade Head Bulk)", model=AdvisorAssessmentRecord,
            new_value={'count': count, 'grade_level_id': grade_level.id, 'new_status': new_status},
            old_value={'old_status': old_status}
        )
        db.session.commit()
        # TODO: Add Notification for Academic Affairs
        return jsonify({'status': 'success', 'message': f'ส่งต่อผลการประเมิน {count} รายการเรียบร้อยแล้ว'})
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Error forwarding assessments (Grade Head): {e}", exc_info=True)
        # --- Log Failure ---
        log_action(f"Forward Assessments Failed (Grade Head): {type(e).__name__}", model=AdvisorAssessmentRecord, new_value={'grade_level_id': grade_level.id})
        try: db.session.commit()
        except: db.session.rollback()
        return jsonify({'status': 'error', 'message': f'เกิดข้อผิดพลาด: {e}'}), 500

@bp.route('/review-repeat-candidates')
@login_required
# @grade_level_head_required
def review_repeat_candidates():
    """แสดงรายชื่อนักเรียนที่รอการพิจารณาจากหัวหน้าสายชั้น"""
    form = FlaskForm() # สำหรับ CSRF
    grade_level_led = current_user.led_grade_level
    if not grade_level_led:
        flash('ไม่พบข้อมูลสายชั้นที่ท่านดูแล', 'danger')
        return redirect(url_for('grade_level_head.dashboard')) # Redirect ไป dashboard ของตนเอง

    # ค้นหา Candidates ที่ห้องเรียน *เดิม* อยู่ในสายชั้นที่ดูแล
    # และมีสถานะรอการพิจารณาจากหัวหน้าสายชั้น
    candidates = db.session.query(RepeatCandidate).join(
        Enrollment, RepeatCandidate.previous_enrollment_id == Enrollment.id
    ).join(
        Classroom, Enrollment.classroom_id == Classroom.id
    ).filter(
        Classroom.grade_level_id == grade_level_led.id,
        RepeatCandidate.status.like('Pending Grade Head Review%') # ดึงทั้งเคส Repeat และ Promote
    ).options(
        joinedload(RepeatCandidate.student),
        joinedload(RepeatCandidate.previous_enrollment).joinedload(Enrollment.classroom),
        joinedload(RepeatCandidate.academic_year) # ปีที่ซ้ำชั้น
    ).order_by(RepeatCandidate.updated_at.asc()).all() # แสดงรายการที่ส่งมาก่อน

    return render_template('grade_level_head/review_repeat_candidates.html',
                           title='พิจารณานักเรียนซ้ำชั้น/เลื่อนชั้นพิเศษ',
                           candidates=candidates,
                           grade_level_name=grade_level_led.name,
                           form=form)


@bp.route('/review-repeat-candidates/submit/<int:candidate_id>', methods=['POST'])
@login_required
# @grade_level_head_required
def submit_grade_head_decision(candidate_id):
    candidate = db.session.get(RepeatCandidate, candidate_id)
    grade_level_led = current_user.led_grade_level

    # Security check (unchanged)
    if (not candidate or not grade_level_led or
            candidate.previous_enrollment.classroom.grade_level_id != grade_level_led.id or
            not candidate.status.startswith('Pending Grade Head Review')):
        flash('ไม่พบข้อมูลหรือไม่มีสิทธิ์ดำเนินการ', 'danger')
        return redirect(url_for('grade_level_head.review_repeat_candidates'))

    decision = request.form.get('decision') # 'approve' or 'reject'
    notes = request.form.get('notes', '')
    original_status = candidate.status
    new_status = None

    if decision == 'approve':
        if candidate.status.endswith('(Repeat)'): new_status = 'Pending Academic Review (Repeat)'
        elif candidate.status.endswith('(Promote)'): new_status = 'Pending Academic Review (Promote)'
        else: new_status = 'Pending Academic Review'
        # Keep final_decision
    elif decision == 'reject':
        new_status = 'Rejected by Grade Head'
        # Keep final_decision
    else:
        flash('กรุณาเลือกการดำเนินการ (เห็นด้วย/ไม่เห็นด้วย)', 'warning')
        return redirect(url_for('grade_level_head.review_repeat_candidates'))

    try:
        candidate.status = new_status
        candidate.grade_head_notes = notes

        # --- Log Action ---
        log_action(
            f"Grade Head Review Repeat Candidate ({decision})", model=RepeatCandidate, record_id=candidate.id,
            old_value=original_status,
            new_value={'status': new_status, 'final_decision': candidate.final_decision, 'notes': notes}
        )
        db.session.commit()
        # TODO: Add Notification for Academic Affairs (if approve)
        if decision == 'approve':
            flash(f'ส่งเรื่องของ {candidate.student.first_name} ให้ฝ่ายวิชาการพิจารณาต่อเรียบร้อยแล้ว', 'success')
        else:
            flash(f'บันทึกผลการพิจารณา (ไม่เห็นด้วย) สำหรับ {candidate.student.first_name} เรียบร้อยแล้ว', 'info')
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Error submitting grade head decision for candidate {candidate_id}: {e}", exc_info=True)
        # --- Log Failure ---
        log_action(f"Grade Head Review Repeat Candidate Failed: {type(e).__name__}", model=RepeatCandidate, record_id=candidate.id)
        try: db.session.commit()
        except: db.session.rollback()
        flash(f'เกิดข้อผิดพลาด: {e}', 'danger')

    return redirect(url_for('grade_level_head.review_repeat_candidates'))