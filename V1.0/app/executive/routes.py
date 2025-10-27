# app/executive/routes.py
from flask import render_template, abort
from flask_login import login_required, current_user
from app.executive import bp
from app.models import Course, Subject, Score, Setting
from collections import defaultdict
import json

# (ฟังก์ชัน calculate_grade ควรจะย้ายไปไว้ที่ app/utils.py เพื่อใช้ร่วมกัน)
def calculate_grade(total_score, max_total_score):
    if max_total_score == 0: return "N/A"
    scale_setting = Setting.query.filter_by(key='grading_scale').first()
    if not (scale_setting and scale_setting.value): return "ไม่มีเกณฑ์"
    grading_scale = json.loads(scale_setting.value)
    percentage = (total_score / max_total_score) * 100
    for rule in grading_scale:
        if percentage >= rule['min_score']:
            return rule['grade']
    return "0"

@bp.route('/dashboard')
@login_required
def dashboard():
    if 'executive' not in [role.key for role in current_user.roles]:
        abort(403)

    all_approved_courses = Course.query.filter(Course.status == 'approved').all()
    all_scores = Score.query.all()
    
    # --- นี่คือ Logic ที่จะมาแทนที่ Placeholder ---
    
    # 1. สร้าง Dictionary เพื่อให้ดึงข้อมูลคะแนนได้เร็วขึ้น
    scores_dict = {f"{s.student_id}-{s.component_id}": s for s in all_scores}
    
    # 2. เตรียม Dictionary สำหรับสรุปผล
    department_summary = defaultdict(lambda: {'total_students': 0, 'grade_points': 0.0})
    grade_point_map = {'4': 4.0, '3.5': 3.5, '3': 3.0, '2.5': 2.5, '2': 2.0, '1.5': 1.5, '1': 1.0, '0': 0.0}

    # 3. วนลูปทุกคอร์สที่อนุมัติแล้วเพื่อคำนวณเกรดของนักเรียนทุกคน
    for course in all_approved_courses:
        all_components = course.components.all()
        coursework_comps = [c for c in all_components if c.exam_type not in ['final']]
        final_comps = [c for c in all_components if c.exam_type == 'final']
        
        max_coursework = sum((c.max_score_k or 0) + (c.max_score_p or 0) + (c.max_score_a or 0) for c in coursework_comps)
        max_final = sum((c.max_score_k or 0) + (c.max_score_p or 0) + (c.max_score_a or 0) for c in final_comps)

        students_in_course = [student for class_group in course.class_groups for student in class_group.students]

        for student in students_in_course:
            raw_coursework_score = sum(score.total_points or 0 for c in coursework_comps if (score := scores_dict.get(f"{student.id}-{c.id}")))
            raw_final_score = sum(score.total_points or 0 for c in final_comps if (score := scores_dict.get(f"{student.id}-{c.id}")))

            coursework_weighted = (raw_coursework_score / max_coursework * course.coursework_ratio) if max_coursework > 0 else 0
            final_weighted = (raw_final_score / max_final * course.final_exam_ratio) if max_final > 0 else 0
            
            total_score_100 = coursework_weighted + final_weighted
            grade = calculate_grade(total_score_100, 100)
            
            # 4. เพิ่มข้อมูลลงในสรุปของกลุ่มสาระฯ
            department_name = course.subject.department
            department_summary[department_name]['total_students'] += 1
            department_summary[department_name]['grade_points'] += grade_point_map.get(grade, 0)

    # 5. คำนวณเกรดเฉลี่ย (GPA) ของแต่ละกลุ่มสาระฯ
    final_summary = {}
    for dept, data in department_summary.items():
        gpa = (data['grade_points'] / data['total_students']) if data['total_students'] > 0 else 0
        final_summary[dept] = {'gpa': round(gpa, 2)}

    # 6. เตรียมข้อมูลสำหรับส่งให้ Chart.js
    chart_labels = list(final_summary.keys())
    chart_data = [data['gpa'] for data in final_summary.values()]
    
    return render_template('executive/dashboard.html',
                           title='แดชบอร์ดผู้บริหาร',
                           chart_labels=json.dumps(chart_labels),
                           chart_data=json.dumps(chart_data))