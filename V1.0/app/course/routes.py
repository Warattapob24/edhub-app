# app/course/routes.py
from flask import render_template, flash, redirect, url_for, request, abort, jsonify # <-- เพิ่ม jsonify
from flask_login import login_required, current_user
from app import db
from app.course import bp
from app.models import (Course, Student, CourseComponent, Score, Subject, ClassGroup, 
                       GradeLevel, AttendanceRecord, Setting, EvaluationTopic, AdditionalAssessment, 
                       ApprovalLog, TimetableSlot, SchedulingRule, CourseAssignment, Curriculum, Room)
from app.forms import CreateCourseForm, AddComponentForm, EnrollStudentForm, TimetableSlotForm, SchedulingRuleForm, ClassGroupForm
from app.utils import log_activity
from datetime import date
import json
from collections import Counter, defaultdict
from datetime import date, timedelta
import datetime

# ฟังก์ชันสำหรับแปลงเลขเป็นเลขไทย (เจ้าน่าจะมีอยู่แล้ว หากไม่มีสามารถใช้ตัวนี้ได้)
def to_thai_numerals(number_input):
    try:
        if number_input is None or number_input == '':
            return ''
        
        # แปลงเป็น string ก่อน
        number_str = str(number_input)
        
        thai_digits = '๐๑๒๓๔๕๖๗๘๙'
        english_digits = '0123456789'
        translation_table = str.maketrans(english_digits, thai_digits)
        return number_str.translate(translation_table)
    except (ValueError, TypeError):
        return number_input # ถ้าแปลงไม่ได้ ให้คืนค่าเดิม
    
@bp.route('/course/<int:course_id>/report')
@login_required
def course_report(course_id):
    course = Course.query.get_or_404(course_id)
    if course.teacher_id != current_user.id:
        abort(403)

    selected_class_group_id = request.args.get('class_group_id', type=int)
    class_groups = [course.class_group] if course.class_group else []
    students = []
    
    # --- ประกาศตัวแปรเปล่าไว้ก่อน ---
    attendance_grid = {}
    attendance_summary = {}
    all_components = []
    scores_dict = {}
    student_summary = {}

    if selected_class_group_id:
        class_group = ClassGroup.query.get(selected_class_group_id)
        if class_group and course.class_group_id == class_group.id:
            students = class_group.students.order_by('class_number').all()
            student_ids = [s.id for s in students]

            # ===== 1. คาถาคำนวณเวลาเรียน =====
            attendances = Attendance.query.filter(
                Attendance.course_id == course_id,
                Attendance.student_id.in_(student_ids)
            ).all()
            
            attendance_grid = {sid: {} for sid in student_ids}
            attendance_summary = {sid: Counter() for sid in student_ids}

            start_date = course.start_date or datetime.date(course.academic_year, 5, 15)

            for att in attendances:
                week_number = (att.date - start_date).days // 7 + 1
                if 1 <= week_number <= 20:
                    attendance_grid[att.student_id][week_number] = att.status
                
                attendance_summary[att.student_id][att.status] += 1
            
            for sid in student_ids:
                attendance_summary[sid] = dict(attendance_summary[sid])

            # ===== 2. คาถารวบรวมคะแนนหน่วย =====
            all_components = course.components.order_by('component_order').all()
            scores = Score.query.filter(
                Score.course_id == course_id,
                Score.student_id.in_(student_ids)
            ).all()
            scores_dict = {f"{s.student_id}-{s.component_id}": s for s in scores}

            # ===== 3. คาถาคำนวณสรุปผลการเรียน (ปถ.๐๕) =====
            final_evals = FinalEvaluation.query.filter(FinalEvaluation.student_id.in_(student_ids)).all()
            final_evals_by_student = {sid: {} for sid in student_ids}
            for fe in final_evals:
                if fe.topic:
                    final_evals_by_student[fe.student_id][fe.topic.assessment_type] = fe.result

            for student in students:
                total_coursework_score = 0
                total_coursework_max = 0
                total_final_score = 0
                total_final_max = 0

                for comp in all_components:
                    score = scores_dict.get(f"{student.id}-{comp.id}")
                    if score and score.total_score is not None:
                        if comp.component_type == 'coursework':
                            total_coursework_score += score.total_score
                            total_coursework_max += comp.max_score
                        elif comp.component_type == 'final':
                            total_final_score += score.total_score
                            total_final_max += comp.max_score
                
                coursework_weighted = (total_coursework_score / total_coursework_max * course.coursework_ratio) if total_coursework_max > 0 else 0
                final_weighted = (total_final_score / total_final_max * course.final_exam_ratio) if total_final_max > 0 else 0
                total_score_100 = coursework_weighted + final_weighted

                grade = calculate_grade(total_score_100, 100)

                total_hours = course.total_hours or 40
                absent_count = attendance_summary.get(student.id, {}).get('ขาด', 0)
                attendance_status = "ปกติ"
                # สมมติว่า 1 ครั้ง = 1 ชั่วโมง หากไม่ใช่ต้องปรับ logic
                if absent_count > total_hours * 0.2:
                    attendance_status = "มส."
                    grade = "มส."

                student_summary[student.id] = {
                    'coursework_weighted': coursework_weighted,
                    'final_weighted': final_weighted,
                    'total_score_100': total_score_100,
                    'grade': grade,
                    'attendance_status': attendance_status,
                    'attributes_grade': final_evals_by_student.get(student.id, {}).get('คุณลักษณะอันพึงประสงค์', ''),
                    'reading_grade': final_evals_by_student.get(student.id, {}).get('การอ่าน คิดวิเคราะห์ และเขียน', ''),
                    'competency_grade': final_evals_by_student.get(student.id, {}).get('สมรรถนะสำคัญของผู้เรียน', '')
                }

    return render_template(
        'course/course_report.html', # << แก้ไขเป็นชื่อไฟล์ที่ถูกต้องของเจ้า
        title="พิมพ์รายงาน",
        course=course,
        class_groups=class_groups,
        selected_class_group_id=selected_class_group_id,
        students=students,
        attendance_grid=attendance_grid,
        attendance_summary=attendance_summary,
        all_components=all_components,
        scores_dict=scores_dict,
        student_summary=student_summary,
        school_name=current_app.config.get('SCHOOL_NAME', 'โรงเรียนของฉัน'), # ตัวอย่างการดึงชื่อโรงเรียน
        to_thai_numerals=to_thai_numerals
    )

@bp.route('/create', methods=['GET', 'POST'])
@login_required
def create_course():
    form = CreateCourseForm()
    rule_form = SchedulingRuleForm()

    # 1. เตรียม Choices สำหรับ Dropdowns
    assignments = CourseAssignment.query.filter_by(teacher_id=current_user.id).all()
    form.subject.choices = [
        (a.curriculum.subject.id, f"{a.curriculum.subject.subject_code} - {a.curriculum.subject.name} ({a.curriculum.grade_level.name})") 
        for a in assignments
    ]
    form.class_group.choices = [
        (cg.id, f"{cg.grade_level.name} / {cg.room_number} ({cg.academic_year})") 
        for cg in ClassGroup.query.join(GradeLevel).order_by(GradeLevel.id, ClassGroup.room_number)
    ]
    form.room.choices = [('0', '- ไม่ระบุห้องประจำ -')] + [(r.id, r.name) for r in Room.query.order_by('name').all()]

    if form.validate_on_submit() and form.submit_course.data:
        room_id = None
        room_name = form.room.data.strip()
        if room_name:
            # ค้นหาห้องที่ชื่อตรงกันก่อน
            room = Room.query.filter_by(name=room_name).first()
            if not room:
                # ถ้าไม่เจอ ให้สร้างใหม่โดยใช้ประเภท 'ห้องเรียนปกติ' เป็นค่าเริ่มต้น
                room = Room(name=room_name, room_type='ห้องเรียนปกติ')
                db.session.add(room)
                db.session.flush() # เพื่อให้ room.id พร้อมใช้งาน
            room_id = room.id
        # 2. สร้าง Course ใหม่ตามโครงสร้าง
        new_course = Course(
            subject_id=form.subject.data,
            teacher_id=current_user.id,
            class_group_id=form.class_group.data,
            room_id=room_id,
            academic_year=form.academic_year.data,
            semester=form.semester.data,
            coursework_ratio=form.coursework_ratio.data,
            final_exam_ratio=100 - form.coursework_ratio.data
        )
        db.session.add(new_course)
        db.session.commit()

        # 3. สร้าง Rule (ถ้ามี)
        if rule_form.validate() and rule_form.rule_type.data:
            new_rule = SchedulingRule(
                rule_type=rule_form.rule_type.data,
                value=rule_form.value.data,
                course_id=new_course.id
            )
            db.session.add(new_rule)
            db.session.commit()

        flash('สร้างคลาสเรียนใหม่เรียบร้อยแล้ว')
        return redirect(url_for('course.my_courses'))

    return render_template('course/create_course.html', 
                           title='สร้างคลาสเรียนใหม่', 
                           form=form, 
                           rule_form=rule_form)

@bp.route('/api/subject/<int:subject_id>/details')
@login_required
def get_subject_details(subject_id):
    subject = Subject.query.get_or_404(subject_id)
    return jsonify({
        'success': True,
        'credits': subject.default_credits,
        'hours_per_week': subject.default_credits * 2 # ใช้คาถาคำนวณของเรา
    })

@bp.route('/manage/<int:course_id>', methods=['GET', 'POST'])
@login_required
def manage_course(course_id):
    course = Course.query.get_or_404(course_id)
    if course.teacher_id != current_user.id:
        abort(403)

    rule = course.scheduling_rules.first()
    rule_form = SchedulingRuleForm(obj=rule)

    if rule_form.validate_on_submit() and 'submit_rule' in request.form:
        # โค้ดทั้งหมดในบล็อก if นี้ต้องย่อหน้าเข้ามา
        if not rule:
            rule = SchedulingRule(course_id=course.id)
            db.session.add(rule)
        
        rule.rule_type = rule_form.rule_type.data
        rule.value = rule_form.value.data
        
        if not rule.rule_type:
            db.session.delete(rule)
            flash('ยกเลิกเงื่อนไขพิเศษแล้ว')
        else:
            flash('บันทึกเงื่อนไขการจัดตารางสอนเรียบร้อยแล้ว')
            
        db.session.commit()
        # บรรทัด return นี้ต้องอยู่ใน if block
        return redirect(url_for('course.manage_course', course_id=course.id))

    if course.final_exam_ratio > 0:
        # ตรวจสอบว่ามี component ที่เป็น final exam หรือยัง
        has_final_component = course.components.filter_by(exam_type='final').first()
        if not has_final_component:
            flash(f'คำเตือน: คุณตั้งสัดส่วนคะแนนปลายภาคไว้ที่ {course.final_exam_ratio}% แต่ยังไม่ได้กำหนดหน่วยใดเป็นการสอบปลายภาค', 'warning')

    component_form = AddComponentForm()
    enrollment_form = EnrollStudentForm()

    # --- ส่วนที่เพิ่มเข้ามาสำหรับตารางสอน ---
    timetable_form = TimetableSlotForm()
    
    # ทำให้ใน dropdown มีแค่ห้องเรียนที่สอนในคอร์สนี้เท่านั้น
    timetable_form.class_group.choices = [
        (c.id, f"{c.grade_level.name}/{c.room_number}") for c in course.class_groups
    ]
        
    # ดึงรายการคาบสอนที่มีอยู่แล้วของวิชานี้
    existing_slots = course.timetable_slots.order_by('day_of_week', 'start_time').all()
    # ------------------------------------
    
    enrolled_student_ids = [s.id for s in course.students]
    available_students = Student.query.filter(Student.id.notin_(enrolled_student_ids)).all()
    enrollment_form.students.choices = [(s.id, f"{s.student_id} - {s.first_name} {s.last_name}") for s in available_students]

    if component_form.submit_component.data and component_form.validate():
        # --- แก้ไขการเพิ่ม Component ---
        # หา order ล่าสุดเพื่อกำหนดให้รายการใหม่
        last_component = course.components.order_by(CourseComponent.display_order.desc()).first()
        new_order = (last_component.display_order + 1) if last_component else 1
        
        new_component = CourseComponent(
            name=component_form.name.data,
            indicator=component_form.indicator.data,
            component_type=component_form.component_type.data,
            max_score_k=component_form.max_score_k.data,
            max_score_p=component_form.max_score_p.data,
            max_score_a=component_form.max_score_a.data,
            exam_type=component_form.exam_type.data,
            total_max_score=component_form.total_max_score.data,
            course_id=course.id,
            display_order=new_order # <-- กำหนด order
        )
        db.session.add(new_component)
        db.session.commit()
        flash('เพิ่มองค์ประกอบคะแนนเรียบร้อยแล้ว', 'success')
        return redirect(url_for('course.manage_course', course_id=course.id))
    
    if enrollment_form.submit_enrollment.data and enrollment_form.validate():
        students_to_enroll = Student.query.filter(Student.id.in_(enrollment_form.students.data)).all()
        for student in students_to_enroll:
            course.students.append(student)
        db.session.commit()
        flash('ลงทะเบียนนักเรียนเรียบร้อยแล้ว', 'success')
        return redirect(url_for('course.manage_course', course_id=course.id))
        
    components = course.components.order_by(CourseComponent.display_order).all()

    return render_template('course/manage_course.html',
                           title=f'จัดการวิชา: {course.subject.name}',
                           course=course,
                           components=components, # <-- ส่ง components ที่เรียงแล้ว
                           component_form=component_form,
                           enrollment_form=enrollment_form,
                           timetable_form=timetable_form, # <-- ส่งฟอร์มไป
                           existing_slots=existing_slots, # <-- ส่งรายการคาบสอนไป
                           rule_form=rule_form)

@bp.route('/rule/delete/<int:rule_id>', methods=['POST'])
@login_required
def delete_rule(rule_id):
    rule = SchedulingRule.query.get_or_404(rule_id)
    course_id = rule.course_id
    # ตรวจสอบสิทธิ์ความเป็นเจ้าของ
    if rule.course.teacher_id != current_user.id:
        flash('ไม่ได้รับอนุญาต', 'danger')
        return redirect(url_for('course.my_courses'))
    
    db.session.delete(rule)
    db.session.commit()
    flash('ลบเงื่อนไขเรียบร้อยแล้ว')
    return redirect(url_for('course.manage_course', course_id=course_id))

@bp.route('/component/edit/<int:component_id>', methods=['GET', 'POST'])
@login_required
def edit_component(component_id):
    """หน้าสำหรับแก้ไของค์ประกอบคะแนน"""
    component = CourseComponent.query.get_or_404(component_id)
    course = component.course
    # ตรวจสอบสิทธิ์ความเป็นเจ้าของ
    if course.teacher_id != current_user.id:
        abort(403)
    
    form = AddComponentForm(obj=component)
    if form.validate_on_submit():
        component.name = form.name.data
        component.indicator = form.indicator.data
        component.component_type = form.component_type.data
        component.max_score_k = form.max_score_k.data
        component.max_score_p = form.max_score_p.data
        component.max_score_a = form.max_score_a.data
        component.exam_type = form.exam_type.data
        component.total_max_score = form.total_max_score.data
        db.session.commit()
        flash('แก้ไของค์ประกอบคะแนนเรียบร้อยแล้ว')
        return redirect(url_for('course.manage_course', course_id=course.id))

    return render_template('course/edit_component.html', title='แก้ไของค์ประกอบคะแนน', form=form, course=course)


@bp.route('/component/delete/<int:component_id>', methods=['POST'])
@login_required
def delete_component(component_id):
    """เส้นทางสำหรับลบองค์ประกอบคะแนน"""
    component = CourseComponent.query.get_or_404(component_id)
    course = component.course
    # ตรวจสอบสิทธิ์ความเป็นเจ้าของ
    if course.teacher_id != current_user.id:
        abort(403)
    
    # อาจต้องเพิ่มการลบคะแนนที่เกี่ยวข้องทั้งหมดก่อน
    Score.query.filter_by(component_id=component.id).delete()

    db.session.delete(component)
    db.session.commit()
    flash('ลบองค์ประกอบคะแนนเรียบร้อยแล้ว')
    return redirect(url_for('course.manage_course', course_id=course.id))

@bp.route('/scores/<int:course_id>', methods=['GET'])
@login_required
def score_entry(course_id):
    course = Course.query.get_or_404(course_id)
    if course.teacher_id != current_user.id:
        abort(403)
    
    selected_class_group_id = request.args.get('class_group_id', type=int)
    students = []
    if selected_class_group_id:
        class_group = ClassGroup.query.get(selected_class_group_id)
        if class_group in course.class_groups:
            students = class_group.students.order_by('class_number').all()

    components = course.components.order_by(CourseComponent.display_order).all()

    # --- เพิ่มโค้ดส่วนที่ขาดหายไปตรงนี้ ---
    scores_query = Score.query.filter(Score.component_id.in_([c.id for c in components])).all()
    scores_dict = {}
    for score in scores_query:
        key = f"{score.student_id}-{score.component_id}"
        display_value = score.total_points
        if score.status == 'Incomplete':
            display_value = 'ร'
        elif score.status == 'Absent':
            display_value = 'มส'
        scores_dict[key] = {
            "k": score.points_k, "p": score.points_p, "a": score.points_a,
            "total": display_value
        }

    max_total_score = sum([(c.max_score_k or 0) + (c.max_score_p or 0) + (c.max_score_a or 0) for c in components])

    student_summary = {}
    for student in students:
        student_total_score = 0
        has_incomplete = False
        for component in components:
            key = f"{student.id}-{component.id}"
            score_info = scores_dict.get(key, {})
            if score_info.get('total') in ['ร', 'มส']:
                has_incomplete = True
            student_total_score += float(score_info.get('total', 0)) if isinstance(score_info.get('total'), (int, float)) else 0
        
        grade = "ร" if has_incomplete else calculate_grade(student_total_score, max_total_score)
        student_summary[student.id] = { "total": student_total_score, "grade": grade }
    # ------------------------------------

    return render_template('course/score_entry.html',
                           title='กรอกคะแนน',
                           course=course,
                           students=students,
                           components=components,
                           scores_dict=scores_dict,
                           student_summary=student_summary,
                           max_total_score=max_total_score,
                           class_groups=course.class_groups,
                           selected_class_group_id=selected_class_group_id)

@bp.route('/api/save-score', methods=['POST'])
@login_required
def save_score():
    """API สำหรับบันทึกคะแนน และคำนวณสรุปผลทั้งหมดส่งกลับไป"""
    data = request.json
    student_id = data.get('student_id')
    component_id = data.get('component_id')
    
    component = CourseComponent.query.get_or_404(component_id)
    if component.course.teacher_id != current_user.id:
        return jsonify({"success": False, "error": "Unauthorized"}), 403

    score = Score.query.filter_by(student_id=student_id, component_id=component_id).first()
    if not score:
        score = Score(student_id=student_id, component_id=component_id)
        db.session.add(score)

    # --- ส่วนบันทึกคะแนนของหน่วยนั้นๆ (เหมือนเดิม) ---
    status = data.get('status')
    if status in ['Incomplete', 'Absent']:
        score.points_k = None
        score.points_p = None
        score.points_a = None
        score.total_points = None
        score.status = status
    else:
        k = data.get('k')
        p = data.get('p')
        a = data.get('a')
        score.points_k = float(k) if k not in [None, ''] else None
        score.points_p = float(p) if p not in [None, ''] else None
        score.points_a = float(a) if a not in [None, ''] else None
        score.total_points = (score.points_k or 0) + (score.points_p or 0) + (score.points_a or 0)
        score.status = 'Graded'
    
    db.session.commit()
    
    # --- ✨ คาถาคำนวณสรุปผลทั้งหมดที่ร่ายเพิ่มเข้ามา ✨ ---
    course = component.course
    all_components = course.components.all()
    student_scores = Score.query.filter_by(student_id=student_id, course_id=course.id).all()
    student_scores_dict = {s.component_id: s for s in student_scores}

    # ตรวจสอบเงื่อนไขการติด 'ร'
    has_incomplete_critical = False
    critical_components = [c for c in all_components if c.component_type in ['summative', 'midterm', 'final']]
    
    for comp in critical_components:
        comp_score = student_scores_dict.get(comp.id)
        if not comp_score or comp_score.total_points == 0:
            has_incomplete_critical = True
            break
    
    # คำนวณคะแนนรวมและเกรด
    if has_incomplete_critical:
        final_grade = 'ร'
        total_score_weighted = sum(s.total_points for s in student_scores if s.total_points is not None)
    else:
        # คำนวณคะแนนรวมตามสัดส่วน (อาจจะต้องปรับตาม logic ของเจ้า)
        max_total_score = sum((c.max_score_k or 0) + (c.max_score_p or 0) + (c.max_score_a or 0) for c in all_components)
        current_total_score = sum(s.total_points for s in student_scores if s.total_points is not None)
        final_grade = calculate_grade(current_total_score, max_total_score)
        total_score_weighted = current_total_score # หรือคะแนนที่ปรับสัดส่วนแล้ว

    # เตรียมข้อมูลสรุปเพื่อส่งกลับ
    student_summary_data = {
        "total_score": round(total_score_weighted, 2),
        "grade": final_grade
    }

    return jsonify({
        "success": True, 
        "new_total_display": score.total_points if score.status == 'Graded' else ('ร' if score.status == 'Incomplete' else 'มส'),
        "summary": student_summary_data # ส่งข้อมูลสรุปทั้งหมดกลับไปด้วย
    })

@bp.route('/api/calculate-kpa', methods=['POST'])
@login_required
def calculate_kpa_from_total():
    data = request.json
    # --- แก้ไขชื่อตัวแปรตรงนี้ ---
    total_score_val = data.get('total_score')
    component_id = data.get('component_id')

    if total_score_val is None or component_id is None:
        return jsonify({"success": False, "error": "Missing data"}), 400

    try:
        total_score = float(total_score_val)
    except (ValueError, TypeError):
        status_map = {'ร': 'Incomplete', 'มส': 'Absent'}
        status = status_map.get(str(total_score_val).strip().lower(), None)
        if status:
            return jsonify({"success": True, "status": status})
        else:
            return jsonify({"success": False, "error": "Invalid input"})

    component = CourseComponent.query.get_or_404(component_id)
    
    max_k = component.max_score_k or 0
    max_p = component.max_score_p or 0
    max_a = component.max_score_a or 0
    total_max = max_k + max_p + max_a

    if total_max == 0:
        return jsonify({"success": True, "k": 0, "p": 0, "a": 0})

    k = round(total_score * (max_k / total_max))
    p = round(total_score * (max_p / total_max))
    a = round(total_score * (max_a / total_max))
    
    current_total = k + p + a
    diff = int(total_score) - current_total
    k += diff

    return jsonify({"success": True, "k": k, "p": p, "a": a})

@bp.route('/api/reorder-components', methods=['POST'])
@login_required
def reorder_components():
    data = request.json
    component_ids = data.get('order')
    
    # ตรวจสอบสิทธิ์คร่าวๆ (อาจต้องทำให้รัดกุมกว่านี้)
    if component_ids:
        first_component = CourseComponent.query.get(component_ids[0])
        if not first_component or first_component.course.teacher_id != current_user.id:
            return jsonify({'success': False, 'error': 'Unauthorized'}), 403

    for index, comp_id in enumerate(component_ids):
        component = CourseComponent.query.get(comp_id)
        if component:
            component.display_order = index + 1
    
    db.session.commit()
    return jsonify({'success': True})

@bp.route('/my-courses')
@login_required
def my_courses():
    """แดชบอร์ดแสดงรายวิชาของครู และตารางสอนประจำวัน"""
    
    # --- ส่วนที่ 1: ดึงข้อมูลตารางสอนสำหรับวันนี้ (ฉบับอัปเกรด) ---
    today_weekday = date.today().weekday()

    # 1.1 ดึงข้อมูลทั้งหมดเหมือนเดิม
    todays_slots_query = TimetableSlot.query.join(Course).filter(
        Course.teacher_id == current_user.id,
        TimetableSlot.day_of_week == today_weekday
    ).order_by(TimetableSlot.start_time).all()

    # 1.2 ร่ายมนตร์ "รวมมิติ"
    grouped_schedule = defaultdict(lambda: {'course': None, 'period': None, 'class_groups': []})
    for slot in todays_slots_query:
        # ใช้ (เวลาเริ่ม, ชื่อวิชา) เป็น key ในการจัดกลุ่ม
        key = (slot.start_time, slot.course.subject.name)
        if not grouped_schedule[key]['course']:
            grouped_schedule[key]['course'] = slot.course
            grouped_schedule[key]['period'] = slot
        grouped_schedule[key]['class_groups'].append(slot.class_group)

    # แปลง dict ให้เป็น list ที่เรียงตามเวลาเพื่อส่งไปแสดงผล
    todays_schedule_grouped = sorted(grouped_schedule.values(), key=lambda x: x['period'].start_time)

    # --- ส่วนที่ 2: ดึงข้อมูลรายวิชาทั้งหมด (เหมือนเดิม) ---
    # เรายังเก็บส่วนนี้ไว้ เพื่อแสดงในแท็บ "รายวิชาทั้งหมด"
    courses_query = Course.query.filter_by(teacher_id=current_user.id).order_by(Course.academic_year.desc(), Course.semester.desc()).all()
    
    courses_summary = []
    for course in courses_query:
        total_max_score = sum([(c.max_score_k or 0) + (c.max_score_p or 0) + (c.max_score_a or 0) for c in course.components])
        # แก้ไข: เปลี่ยน course.students เป็นการ query จาก relationship ที่ถูกต้อง
        student_count = sum(len(class_group.students.all()) for class_group in course.class_groups)
        courses_summary.append({
            "course": course,
            "student_count": student_count,
            "total_max_score": total_max_score
        })

    # ส่งข้อมูลทั้ง 2 ส่วนไปที่ Template
    return render_template('course/my_courses.html', 
                           title='แดชบอร์ดของฉัน', 
                           todays_schedule=todays_schedule_grouped, # <-- ข้อมูลใหม่
                           courses_summary=courses_summary) # <-- ข้อมูลเดิม

@bp.route('/course/<int:course_id>/submit', methods=['POST'])
@login_required
def submit_course(course_id):
    course = Course.query.get_or_404(course_id)
    if course.teacher_id != current_user.id:
        abort(403)
    
    # 1. เปลี่ยนสถานะหลักของ Course
    course.status = 'pending_approval' # ใช้สถานะกลางๆ ว่า "กำลังรออนุมัติ"

    # 2. สร้าง Log การอนุมัติขั้นตอนแรก
    new_log = ApprovalLog(
        status='Submitted',
        comments='ครูผู้สอนส่งผลการเรียน',
        step=1, # ระบุว่าเป็นขั้นตอนที่ 1
        course_id=course.id,
        user_id=current_user.id # บันทึกว่าใครเป็นคนส่ง
    )
    db.session.add(new_log)
    
    # 3. Commit ทีเดียว
    db.session.commit()

    log_activity('Submit Course', f'User {current_user.username} submitted course {course.id}')
    flash(f'ส่งผลการเรียนวิชา "{course.subject.name}" เพื่อขออนุมัติเรียบร้อยแล้ว')
    return redirect(url_for('course.my_courses'))

@bp.route('/<int:course_id>/attendance', methods=['GET', 'POST'])
@login_required
def attendance(course_id):
    course = Course.query.get_or_404(course_id)
    if course.teacher_id != current_user.id:
        abort(403)
    
    # รับค่า class_group_id และ date จาก URL
    selected_class_group_id = request.args.get('class_group_id', type=int)
    day_str = request.args.get('date', date.today().isoformat())
    selected_date = date.fromisoformat(day_str)
    
    students = []
    if selected_class_group_id:
        class_group = ClassGroup.query.get(selected_class_group_id)
        students = class_group.students.order_by('class_number').all()

    if request.method == 'POST' and students:
        for student in students:
            status = request.form.get(f'attendance-{student.id}')
            if status:
                record = AttendanceRecord.query.filter_by(
                    student_id=student.id, course_id=course.id, date=selected_date
                ).first()
                if record:
                    record.status = status
                else:
                    record = AttendanceRecord(
                        student_id=student.id, course_id=course.id,
                        date=selected_date, status=status
                    )
                    db.session.add(record)
        db.session.commit()
        flash(f'บันทึกการเข้าเรียนวันที่ {selected_date.strftime("%d-%m-%Y")} เรียบร้อยแล้ว')
        return redirect(url_for('course.attendance', course_id=course.id, date=day_str, class_group_id=selected_class_group_id))

    records_query = AttendanceRecord.query.filter_by(course_id=course.id, date=selected_date).all()
    attendance_dict = {r.student_id: r.status for r in records_query}

    return render_template('course/attendance.html', 
                           title='บันทึกเวลาเรียน', 
                           course=course,
                           students=students,
                           class_groups=course.class_groups, # ส่งรายชื่อห้องไปให้ template
                           selected_class_group_id=selected_class_group_id,
                           selected_date_str=day_str,
                           attendance_dict=attendance_dict)

def calculate_grade(total_score, max_total_score):
    """ฟังก์ชันช่วยคำนวณเกรดจากเกณฑ์ในฐานข้อมูล"""
    if max_total_score == 0:
        return "N/A"
    
    # ดึงเกณฑ์เกรดจากฐานข้อมูล
    scale_setting = Setting.query.filter_by(key='grading_scale').first()
    if not (scale_setting and scale_setting.value):
        return "ไม่มีเกณฑ์" # Fallback
        
    grading_scale = json.loads(scale_setting.value)
    percentage = (total_score / max_total_score) * 100
    
    # หาเกรดตามเกณฑ์ (เกณฑ์ถูกเรียงจากมากไปน้อยแล้ว)
    for rule in grading_scale:
        if percentage >= rule['min_score']:
            return rule['grade']
            
    return "0" # ถ้าไม่เข้าเกณฑ์ไหนเลย

@bp.route('/<int:course_id>/additional-assessment')
@login_required
def additional_assessment(course_id):
    course = Course.query.get_or_404(course_id)
    if course.teacher_id != current_user.id:
        abort(403)

    selected_class_group_id = request.args.get('class_group_id', type=int)
    students = []
    
    # ประกาศตัวแปรทั้งหมดไว้ก่อน
    topics_by_type_serializable = {}
    assessments_dict = {}
    summary_results = {}

    # --- ส่วนที่เจ้าทำไว้ดีแล้ว: การแปลง Object เป็น Dictionary ---
    all_topics = EvaluationTopic.query.filter_by(parent_id=None).order_by(EvaluationTopic.assessment_type, EvaluationTopic.display_order).all()
    for topic in all_topics:
        if topic.assessment_type not in topics_by_type_serializable:
            topics_by_type_serializable[topic.assessment_type] = []
        
        sub_topics_list = [
            {'id': sub.id, 'name': sub.name}
            for sub in sorted(topic.sub_topics, key=lambda x: x.display_order)
        ]
        
        topics_by_type_serializable[topic.assessment_type].append({
            'id': topic.id,
            'name': topic.name,
            'sub_topics': sub_topics_list
        })
    # ----------------------------------------------------

    if selected_class_group_id:
        class_group = ClassGroup.query.get(selected_class_group_id)
        if class_group and class_group in course.class_groups:
            students = class_group.students.order_by('class_number').all()

            # ดึงข้อมูลการประเมินทั้งหมดของวิชานี้
            assessments_query = AdditionalAssessment.query.filter_by(course_id=course_id).all()
            assessments_dict = {f"{a.student_id}-{a.topic_id}": a.result for a in assessments_query}

            # ===== ✨ คาถาคำนวณ summary_results ที่เพิ่มเข้ามา! ✨ =====
            result_options_reversed = {'ดีเยี่ยม': 3, 'ดี': 2, 'ผ่าน': 1, 'ไม่ผ่าน': 0}

            for student in students:
                for assessment_type, topics in topics_by_type_serializable.items():
                    for topic in topics:
                        # ตรวจสอบว่ามี sub_topics ที่เป็น list และไม่ว่าง
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
            # =======================================================
    
    # --- ส่วนที่แก้ไข: เพิ่ม summary_results เข้าไปในการ return ---
    return render_template('course/additional_assessment.html',
                           title='ประเมินเพิ่มเติม',
                           course=course,
                           topics_by_type=topics_by_type_serializable,
                           students=students,
                           assessments_dict=assessments_dict,
                           class_groups=course.class_groups,
                           selected_class_group_id=selected_class_group_id,
                           summary_results=summary_results)

# API สำหรับบันทึกผลการประเมิน
@bp.route('/api/save-bulk-assessments', methods=['POST'])
@login_required
def save_bulk_assessments():
    data = request.json
    course_id = data.get('course_id')
    student_id = data.get('student_id')
    results = data.get('results') # {topic_id: result, ...}

    course = Course.query.get_or_404(course_id)
    if course.teacher_id != current_user.id:
        return jsonify({'success': False, 'error': 'Unauthorized'}), 403

    for topic_id, result in results.items():
        assessment = AdditionalAssessment.query.filter_by(
            student_id=student_id, topic_id=topic_id, course_id=course_id
        ).first()

        if result:
            if not assessment:
                assessment = AdditionalAssessment(student_id=student_id, topic_id=topic_id, course_id=course_id)
                db.session.add(assessment)
            assessment.result = result
        elif assessment:
            db.session.delete(assessment)
    
    db.session.commit()
    return jsonify({'success': True})

@bp.route('/api/save-assessment', methods=['POST'])
@login_required
def save_assessment():
    data = request.json
    student_id = data.get('student_id')
    topic_id = data.get('topic_id')
    result = data.get('result')
    course_id = data.get('course_id')
    
    course = Course.query.get_or_404(course_id)
    if course.teacher_id != current_user.id:
        return jsonify({'success': False, 'error': 'Unauthorized'}), 403

    # หาหรือสร้าง Assessment object
    assessment = AdditionalAssessment.query.filter_by(
        student_id=student_id, topic_id=topic_id, course_id=course_id
    ).first()

    if result: # ถ้ามีค่า (เช่น 'ผ่าน')
        if not assessment:
            assessment = AdditionalAssessment(
                student_id=student_id, topic_id=topic_id, course_id=course_id
            )
            db.session.add(assessment)
        assessment.result = result
    elif assessment: # ถ้าส่งค่าว่างมา (ล้างค่า)
        db.session.delete(assessment)

    db.session.commit()
    return jsonify({'success': True})

@bp.route('/<int:course_id>/report/poh05')
@login_required
def poh05_report(course_id):
    course = Course.query.get_or_404(course_id)
    if course.teacher_id != current_user.id:
        abort(403)

    school_name_setting = Setting.query.filter_by(key='school_name').first()
    school_name = school_name_setting.value if school_name_setting else "ชื่อโรงเรียน"
    
    selected_class_group_id = request.args.get('class_group_id', type=int)
    students = []
    class_group = None
    
    # ประกาศตัวแปรเปล่าไว้ก่อน
    all_components = []
    scores_dict = {}
    attendance_grid = {}
    attendance_summary = {}
    student_summary = {}
    max_final = 0

    if selected_class_group_id:
        class_group = ClassGroup.query.get(selected_class_group_id)
        if class_group and class_group in course.class_groups:
            students = class_group.students.order_by('class_number').all()
            student_ids = [s.id for s in students]

            all_components = course.components.order_by(CourseComponent.display_order).all()
            
            # ดึงข้อมูลคะแนนและเวลาเรียนทั้งหมดในครั้งเดียวเพื่อประสิทธิภาพ
            scores_query = Score.query.filter(Score.student_id.in_(student_ids), Score.component_id.in_([c.id for c in all_components])).all()
            scores_dict = {f"{s.student_id}-{s.component_id}": s for s in scores_query}

            attendance_query = AttendanceRecord.query.filter(AttendanceRecord.student_id.in_(student_ids), AttendanceRecord.course_id == course_id).all()

            # สร้าง Grid ข้อมูลเวลาเรียน
            first_day = db.session.query(db.func.min(AttendanceRecord.date)).filter_by(course_id=course_id).scalar() or date.today()
            
            # จัดกลุ่มข้อมูลเวลาเรียนตามนักเรียนและสัปดาห์
            attendance_by_student_week = {}
            for record in attendance_query:
                week_number = (record.date - first_day).days // 7 + 1
                if record.student_id not in attendance_by_student_week:
                    attendance_by_student_week[record.student_id] = {}
                # เก็บเฉพาะ record ล่าสุดของสัปดาห์นั้น
                if week_number not in attendance_by_student_week[record.student_id] or record.date > attendance_by_student_week[record.student_id][week_number].date:
                    attendance_by_student_week[record.student_id][week_number] = record
            
            attendance_grid = {sid: {} for sid in student_ids}
            for sid, weeks_data in attendance_by_student_week.items():
                for week_num, record in weeks_data.items():
                    if 1 <= week_num <= 20:
                        attendance_grid[sid][week_num] = record.status[0] if record.status else ''

            # คำนวณ attendance_summary
            attendance_summary = {sid: Counter() for sid in student_ids}
            for record in attendance_query:
                attendance_summary[record.student_id][record.status] += 1
            for sid in student_ids:
                attendance_summary[sid] = dict(attendance_summary[sid])

            coursework_comps = [c for c in all_components if c.exam_type not in ['final']]
            final_comps = [c for c in all_components if c.exam_type == 'final']
            
            max_coursework = sum((c.max_score_k or 0) + (c.max_score_p or 0) + (c.max_score_a or 0) for c in coursework_comps)
            final_exam_comps = [c for c in all_components if c.exam_type == 'final']
            max_final = sum((c.max_score_k or 0) + (c.max_score_p or 0) + (c.max_score_a or 0) for c in final_comps)

    # --- วางโค้ดนี้แทนที่ส่วนคำนวณ student_summary เดิมทั้งหมด ---
    student_summary = {}
    for student in students:
        summary = {}
        has_incomplete = False
        was_remediated = False

        # 1. ตรวจสอบ "ร" อัตโนมัติจากงานสำคัญที่ขาดส่ง
        summative_comps = [c for c in all_components if c.component_type == 'Summative' or c.exam_type in ['midterm', 'final']]
        for comp in summative_comps:
            score = scores_dict.get(f"{student.id}-{comp.id}")
            if not score or score.total_points is None:
                has_incomplete = True
                break
        
        # 2. ตรวจสอบ "ร่องรอย" การซ่อม
        for comp in all_components:
            score = scores_dict.get(f"{student.id}-{comp.id}")
            if score and score.remedial_score is not None:
                was_remediated = True
                break
        summary['was_remediated'] = was_remediated

        # 3. คำนวณคะแนนตามสัดส่วน (อัปเกรดแล้ว!)
        raw_coursework_score = 0
        for c in coursework_comps:
            score = scores_dict.get(f"{student.id}-{c.id}")
            if score:
                # ถ้ามีคะแนนซ่อม (ไม่ใช่ None) ให้ใช้คะแนนซ่อม
                # แต่ถ้าไม่มี ให้ใช้คะแนนปกติ (total_points)
                points_to_use = score.remedial_score if score.remedial_score is not None else score.total_points
                raw_coursework_score += (points_to_use or 0)

        raw_final_score = 0
        for c in final_comps:
            score = scores_dict.get(f"{student.id}-{c.id}")
            if score:
                # ใช้ Logic เดียวกันกับคะแนนปลายภาค
                points_to_use = score.remedial_score if score.remedial_score is not None else score.total_points
                raw_final_score += (points_to_use or 0)
        
        # ส่วนที่เหลือของขั้นตอนที่ 3 เหมือนเดิมทุกประการ
        coursework_weighted = (raw_coursework_score / max_coursework * course.coursework_ratio) if max_coursework > 0 else 0
        final_weighted = (raw_final_score / max_final * course.final_exam_ratio) if max_final > 0 else 0
        
        summary['total_score_100'] = coursework_weighted + final_weighted

        # 4. ตัดสินเกรดตามเงื่อนไขใหม่
        summary['grade'] = "ร" if has_incomplete else calculate_grade(summary['total_score_100'], 100)

        # 5. คำนวณสถานะเวลาเรียน (เหมือนเดิม)
        absent_count = attendance_summary.get(student.id, {}).get('ขาด', 0)
        total_sessions = 20 # สมมติ
        
        attendance_status = "ปกติ"
        if total_sessions > 0 and (absent_count / total_sessions) * 100 > 20:
            attendance_status = "มส."
        summary['attendance_status'] = attendance_status
        
        student_summary[student.id] = summary

    return render_template('course/poh05_report.html',
                           title=f"ปถ.05 - {course.subject.name}",
                           course=course,
                           class_group=class_group,
                           students=students,
                           all_components=all_components,
                           scores_dict=scores_dict,
                           attendance_summary=attendance_summary,
                           student_summary=student_summary,
                           school_name=school_name,
                           class_groups=course.class_groups,
                           selected_class_group_id=selected_class_group_id,
                           to_thai_numerals=to_thai_numerals,
                           attendance_grid=attendance_grid,
                           coursework_ratio=course.coursework_ratio,
                           final_exam_ratio=course.final_exam_ratio,
                           max_final=max_final)

@bp.route('/<int:course_id>/remedial')
@login_required
def remedial_management(course_id):
    course = Course.query.get_or_404(course_id)
    if course.teacher_id != current_user.id:
        abort(403)

    # --- 1. ดึงข้อมูลพื้นฐานทั้งหมด ---
    students_in_course = []
    for class_group in course.class_groups:
        students_in_course.extend(class_group.students.all())
    
    students = sorted(students_in_course, key=lambda s: (s.class_group.grade_level.name, s.class_group.room_number, s.class_number))
    student_ids = [s.id for s in students]

    all_components = course.components.order_by(CourseComponent.display_order).all()
    scores_query = Score.query.filter(Score.student_id.in_(student_ids), Score.component_id.in_([c.id for c in all_components])).all()
    
    # สร้าง scores_dict เป็น dict ของ dicts (ถูกต้องแล้วสำหรับส่งไปหน้าบ้าน)
    scores_dict = {}
    for s in scores_query:
        key = f"{s.student_id}-{s.component_id}"
        scores_dict[key] = {
            "id": s.id,
            "total_points": s.total_points,
            "status": s.status,
            "remedial_score": s.remedial_score # เพิ่มคะแนนซ่อมเข้าไปด้วย
        }

    students_with_issues = []
    critical_components = [c for c in all_components if c.component_type in ['summative', 'midterm', 'final']]
    
    for student in students:
        issues = []
        has_incomplete_critical = False
        
        for component in critical_components:
            score = scores_dict.get(f"{student.id}-{component.id}")
            # ✨ แก้ไข: เรียกใช้แบบ dict['key'] ✨
            if not score or score['total_points'] == 0:
                has_incomplete_critical = True
                issues.append({
                    'component': { 'id': component.id, 'name': component.name, 'max_score_k': component.max_score_k or 0, 'max_score_p': component.max_score_p or 0, 'max_score_a': component.max_score_a or 0 },
                    'score': { 'id': score['id'] if score else 0, 'status': 'ไม่มีคะแนน' if not score else 'ได้ 0 คะแนน', 'remedial_score': score['remedial_score'] if score else '' }
                })
        
        if has_incomplete_critical:
            students_with_issues.append({
                'student': student,
                'grade': 'ร',
                'issues': issues
            })
            continue

        max_total_score = sum((c.max_score_k or 0) + (c.max_score_p or 0) + (c.max_score_a or 0) for c in all_components)
        
        # ✨ แก้ไข: สร้าง list ของคะแนนสำหรับนักเรียนคนนี้โดยเฉพาะ ✨
        student_scores = [s for key, s in scores_dict.items() if key.startswith(f"{student.id}-")]
        current_total_score = sum(s['total_points'] for s in student_scores if s['total_points'] is not None)
        
        current_grade = calculate_grade(current_total_score, max_total_score)

        if current_grade == '0':
            for component in all_components:
                score = scores_dict.get(f"{student.id}-{component.id}")
                # ✨ แก้ไข: เรียกใช้แบบ dict['key'] ✨
                if score and score['total_points'] is not None:
                    max_score_comp = (component.max_score_k or 0) + (component.max_score_p or 0) + (component.max_score_a or 0)
                    if max_score_comp > 0 and (score['total_points'] / max_score_comp) < 0.5:
                        issues.append({
                            'component': { 'id': component.id, 'name': component.name, 'max_score_k': component.max_score_k or 0, 'max_score_p': component.max_score_p or 0, 'max_score_a': component.max_score_a or 0 },
                            'score': { 'id': score['id'], 'status': f"ได้ {score['total_points']}/{max_score_comp}", 'remedial_score': score['remedial_score'] }
                        })
            
            students_with_issues.append({
                'student': student,
                'grade': '0',
                'issues': issues if issues else [{'component': {'name': 'คะแนนรวมไม่ถึงเกณฑ์'}, 'score': {'status': '', 'id': 0}}]
            })

    return render_template('course/remedial_management.html',
                           title='จัดการผลการเรียนที่ต้องแก้ไข',
                           course=course,
                           students_with_issues=students_with_issues,
                           all_components=all_components,
                           scores_dict=scores_dict
                          )

@bp.route('/api/save-remedial', methods=['POST'])
@login_required
def save_remedial():
    data = request.json
    score_id = data.get('score_id')
    remedial_points_str = data.get('points')
    
    score = Score.query.get_or_404(score_id)
    course = score.component.course
    student_id = score.student_id

    # ตรวจสอบสิทธิ์
    if course.teacher_id != current_user.id:
        return jsonify({'success': False, 'error': 'Unauthorized'}), 403
    
    # 1. บันทึกคะแนนซ่อม (เหมือนเดิม)
    score.remedial_score = float(remedial_points_str) if remedial_points_str and remedial_points_str.strip() != '' else None
    if score.remedial_score is not None:
        score.status = 'Remedied'
        # --- เพิ่ม Logic: ถ้าคะแนนซ่อมสูงกว่าคะแนนเดิม ให้ใช้คะแนนซ่อมเป็นคะแนนหลัก ---
        if score.total_points is None or score.remedial_score > score.total_points:
            score.total_points = score.remedial_score
    else:
        score.status = 'Incomplete'
    
    db.session.flush() # ส่งการเปลี่ยนแปลงไปที่ session ก่อน commit

    # --- ✨ 2. คาถาร่ายใหม่: คำนวณคะแนนรวมและเกรดสุดท้ายของนักเรียนทั้งคอร์ส! ✨ ---
    all_student_scores = Score.query.filter_by(student_id=student_id, course_id=course.id).all()
    all_components = course.components.all()

    # คำนวณคะแนนรวม
    max_total_score = sum((c.max_score_k or 0) + (c.max_score_p or 0) + (c.max_score_a or 0) for c in all_components)
    current_total_score = sum(s.total_points for s in all_student_scores if s.total_points is not None)
    
    # ตัดเกรดใหม่
    new_final_grade = calculate_grade(current_total_score, max_total_score)
    
    # Commit การเปลี่ยนแปลงทั้งหมดทีเดียว
    db.session.commit()
    
    # 3. ส่งข้อมูลสรุปกลับไปหน้าเว็บ
    return jsonify({
        'success': True,
        'new_final_grade': new_final_grade,
        'new_total_score': round(current_total_score, 2)
    })

@bp.route('/course/<int:course_id>/add_slot', methods=['POST'])
@login_required
def add_timetable_slot(course_id):
    course = Course.query.get_or_404(course_id)
    if course.teacher_id != current_user.id:
        abort(403)
    
    form = TimetableSlotForm()
    form.class_group.choices = [
        (c.id, f"{c.grade_level.name}/{c.room_number}") 
        for c in Course.query.get(course_id).class_groups
    ]

    if form.validate_on_submit():
        new_slot = TimetableSlot(
            course_id=course.id,
            class_group_id=form.class_group.data, 
            day_of_week=form.day_of_week.data,
            start_time=form.start_time.data,
            end_time=form.end_time.data
        )
        db.session.add(new_slot)
        db.session.commit()
        flash('เพิ่มคาบสอนเรียบร้อยแล้ว', 'success')
    else:
        flash('ข้อมูลไม่ถูกต้อง กรุณาตรวจสอบอีกครั้ง', 'danger')

    return redirect(url_for('course.manage_course', course_id=course.id))

@bp.route('/course/delete_slot/<int:slot_id>', methods=['POST'])
@login_required
def delete_timetable_slot(slot_id):
    slot = TimetableSlot.query.get_or_404(slot_id)
    course_id = slot.course.id # เก็บ course_id ไว้ก่อนลบ
    if slot.course.teacher_id != current_user.id:
        abort(403)
    
    db.session.delete(slot)
    db.session.commit()
    flash('ลบคาบสอนเรียบร้อยแล้ว', 'success')
    return redirect(url_for('course.manage_course', course_id=course_id))