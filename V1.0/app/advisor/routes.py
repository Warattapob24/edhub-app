# app/advisor/routes.py
from flask import render_template, request, jsonify, abort
from flask_login import login_required, current_user
from app import db
from app.advisor import bp
from app.models import Student, EvaluationTopic, AdditionalAssessment, FinalEvaluation, Setting, ClassGroup, GradeLevel, User, Role
from collections import Counter

@bp.route('/dashboard')
@login_required
def dashboard():
    # ดึงข้อมูลห้องเรียนที่ current_user เป็นที่ปรึกษา
    advised_class_groups = current_user.advised_class_groups
    return render_template('advisor/dashboard.html', 
                           title='แดชบอร์ดครูที่ปรึกษา',
                           class_groups=advised_class_groups)

@bp.route('/student/<int:student_id>/summary')
@login_required
def student_summary(student_id):
    student = Student.query.get_or_404(student_id)
    # ตรวจสอบสิทธิ์
    if current_user not in student.class_group.advisors:
        abort(403)

    # --- Logic ใหม่ทั้งหมดในการรวบรวมและประมวลผลข้อมูล ---
    all_assessments = AdditionalAssessment.query.filter_by(student_id=student_id).all()
    
    summary_data = {}
    main_topics_by_type = {
        'คุณลักษณะอันพึงประสงค์': EvaluationTopic.query.filter_by(assessment_type='คุณลักษณะอันพึงประสงค์', parent_id=None).order_by(EvaluationTopic.display_order).all(),
        'การอ่าน คิดวิเคราะห์ และเขียน': EvaluationTopic.query.filter_by(assessment_type='การอ่าน คิดวิเคราะห์ และเขียน', parent_id=None).order_by(EvaluationTopic.display_order).all(),
        'สมรรถนะ': EvaluationTopic.query.filter_by(assessment_type='สมรรถนะ', parent_id=None).order_by(EvaluationTopic.display_order).all()
    }
    
    result_priority = {'ดีเยี่ยม': 3, 'ดี': 2, 'ผ่าน': 1, 'ไม่ผ่าน': 0}

    for type, main_topics in main_topics_by_type.items():
        summary_data[type] = []
        for main_topic in main_topics:
            sub_topic_summary = []
            for sub_topic in main_topic.sub_topics:
                # 1. รวบรวมผลประเมินของ sub_topic นี้
                results = [a.result for a in all_assessments if a.topic_id == sub_topic.id]
                
                # 2. นับจำนวน
                counts = Counter(results)
                
                # 3. คำนวณหาผลที่แนะนำ
                suggestion = ''
                if results:
                    max_count = 0
                    modes = []
                    for result, count in counts.items():
                        if count > max_count:
                            max_count = count
                            modes = [result]
                        elif count == max_count:
                            modes.append(result)
                    
                    # ถ้ามีฐานนิยมตัวเดียว
                    if len(modes) == 1:
                        suggestion = modes[0]
                    # ถ้ามีฐานนิยมหลายตัว ให้เลือกอันที่ดีที่สุด
                    else:
                        suggestion = max(modes, key=lambda r: result_priority.get(r, -1))

                sub_topic_summary.append({
                    'sub_topic': sub_topic,
                    'counts': dict(counts),
                    'suggestion': suggestion
                })
            
            summary_data[type].append({
                'main_topic': main_topic,
                'sub_topics_summary': sub_topic_summary
            })

    final_evals_query = FinalEvaluation.query.filter_by(student_id=student_id).all()
    final_evals_dict = {fe.topic_id: fe.result for fe in final_evals_query}
    result_options = ['ดีเยี่ยม', 'ดี', 'ผ่าน', 'ไม่ผ่าน']

    return render_template('advisor/student_summary.html',
                           title=f'สรุปผล {student.first_name}',
                           student=student,
                           summary_data_by_type=summary_data,
                           result_options=result_options,
                           final_evals_dict=final_evals_dict)

@bp.route('/api/save-final-evaluation', methods=['POST'])
@login_required
def save_final_evaluation():
    data = request.json
    student_id = data.get('student_id')
    topic_id = data.get('topic_id')
    result = data.get('result')

    # ตรวจสอบสิทธิ์ (อาจต้องเพิ่มความรัดกุม)
    student = Student.query.get_or_404(student_id)
    if current_user not in student.class_group.advisors:
        abort(403)

    # หาหรือสร้าง FinalEvaluation object
    final_eval = FinalEvaluation.query.filter_by(student_id=student_id, topic_id=topic_id).first()
    if not final_eval:
        final_eval = FinalEvaluation(student_id=student_id, topic_id=topic_id, advisor_id=current_user.id)
        db.session.add(final_eval)
    
    final_eval.result = result
    # อาจจะต้องดึงปีการศึกษาและเทอมมาจากที่อื่น
    # final_eval.academic_year = ...
    # final_eval.semester = ...
    
    db.session.commit()
    return jsonify({'success': True})

@bp.route('/class_group/<int:class_group_id>/assessment')
@login_required
def class_assessment(class_group_id):
    # บรรทัดนี้จะไม่มีการย่อหน้าผิดพลาด
    class_group = ClassGroup.query.get_or_404(class_group_id)
    if class_group not in current_user.advised_class_groups:
        abort(403)

    students = class_group.students.order_by('class_number').all()
    
    topics_by_type_serializable = {}
    all_topics = EvaluationTopic.query.filter_by(parent_id=None).order_by(EvaluationTopic.assessment_type, EvaluationTopic.display_order).all()
    for topic in all_topics:
        if topic.assessment_type not in topics_by_type_serializable:
            topics_by_type_serializable[topic.assessment_type] = []
        sub_topics_list = [{'id': sub.id, 'name': sub.name} for sub in sorted(topic.sub_topics, key=lambda x: x.display_order)]
        topics_by_type_serializable[topic.assessment_type].append({
            'id': topic.id, 'name': topic.name, 'sub_topics': sub_topics_list
        })

    student_ids = [s.id for s in students]
    final_evals = FinalEvaluation.query.filter(FinalEvaluation.student_id.in_(student_ids)).all()
    assessments_dict = {f"{a.student_id}-{a.topic_id}": a.result for a in final_evals}

    all_other_assessments = AdditionalAssessment.query.filter(AdditionalAssessment.student_id.in_(student_ids)).all()
    counts_data = {s_id: {} for s_id in student_ids}
    for assessment in all_other_assessments:
        student_id = assessment.student_id
        topic_id = assessment.topic_id
        result = assessment.result
        if topic_id not in counts_data[student_id]:
            counts_data[student_id][topic_id] = Counter()
        counts_data[student_id][topic_id][result] += 1
    for s_id, topics in counts_data.items():
        for t_id, counter in topics.items():
            counts_data[s_id][t_id] = dict(counter)

    suggestions_dict = {}
    for student_id, topics in counts_data.items():
        for topic_id, counts in topics.items():
            if counts:
                most_common_result = max(counts, key=counts.get)
                suggestions_dict[f"{student_id}-{topic_id}"] = most_common_result

    summary_results = {}
    result_options_reversed = {'ดีเยี่ยม': 3, 'ดี': 2, 'ผ่าน': 1, 'ไม่ผ่าน': 0}
    for student in students:
        for assessment_type, topics in topics_by_type_serializable.items():
            for topic in topics:
                if topic.get('sub_topics') and isinstance(topic['sub_topics'], list) and topic['sub_topics']:
                    total_score = 0
                    all_assessed = True
                    num_sub_topics = len(topic['sub_topics'])
                    for sub_topic in topic['sub_topics']:
                        result = assessments_dict.get(f"{student.id}-{sub_topic['id']}")
                        if not result:
                            all_assessed = False
                            break
                        total_score += result_options_reversed.get(result, 0)
                    if all_assessed:
                        average_score = round(total_score / num_sub_topics)
                        options_to_text = {3: 'ดีเยี่ยม', 2: 'ดี', 1: 'ผ่าน', 0: 'ไม่ผ่าน'}
                        final_result = options_to_text.get(average_score, 'ไม่ผ่าน')
                        summary_results[f"{student.id}-{topic['id']}"] = final_result
                    else:
                        summary_results[f"{student.id}-{topic['id']}"] = None

    # บรรทัด return นี้จะถูกจัดวางอย่างถูกต้อง
    return render_template('advisor/class_assessment.html',
                           title=f"ประเมินนักเรียนห้อง {class_group.grade_level.name}/{class_group.room_number}",
                           students=students,
                           topics_by_type=topics_by_type_serializable,
                           assessments_dict=assessments_dict,
                           summary_results=summary_results,
                           counts_data=counts_data,
                           suggestions_dict=suggestions_dict,
                           class_group=class_group
                          )