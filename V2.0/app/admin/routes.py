from flask import render_template, Blueprint, abort, redirect, request, url_for, flash, jsonify
from flask_login import login_required, current_user
from app import db
from app.models import (AssessmentTool, CharacteristicSubItem, Competency, DesirableCharacteristic,
                        MethodSubItem, User, CourseSection, AcademicYear, LearningUnit,
                        GradeComponent, AssessmentAspect, AssessmentMethod, TeacherAssignment,
                        CompetencySubItem, CharacteristicSubItem, MethodSubItem, HomeroomEnrollment,
                        Student, Classroom)
from app.decorators import teacher_required, admin_required
from app.teacher.forms import LearningUnitForm, GradeComponentForm, AssessmentAspectForm

teacher_bp = Blueprint('teacher', __name__, template_folder='templates')

@teacher_bp.route('/dashboard')
@login_required
@teacher_required
def dashboard():
    active_year = AcademicYear.query.filter_by(is_active=True).first()
    assigned_sections = []
    if active_year:
        assigned_sections = db.session.query(CourseSection).distinct().join(
            TeacherAssignment, CourseSection.id == TeacherAssignment.course_section_id
        ).filter(
            TeacherAssignment.teacher_id == current_user.id,
            CourseSection.academic_year_id == active_year.id
        ).all()

    return render_template('teacher/dashboard.html', title='Teacher Dashboard', sections=assigned_sections)


@teacher_bp.route('/plan/<int:section_id>')
@login_required
@teacher_required
def manage_learning_plan(section_id):
    section = CourseSection.query.get_or_404(section_id)

    if not TeacherAssignment.query.filter_by(teacher_id=current_user.id, course_section_id=section.id).first():
        abort(403)

    learning_units = section.learning_units.order_by(LearningUnit.start_period).all()

    all_components = GradeComponent.query.join(LearningUnit).filter(
        LearningUnit.course_section_id == section.id
    ).all()
    total_midterm_score = sum(c.total_max_score for c in all_components if c.is_midterm_exam)
    total_final_score = sum(c.total_max_score for c in all_components if c.is_final_exam)
    total_assignment_score = sum(c.total_max_score for c in all_components if not c.is_midterm_exam and not c.is_final_exam)
    score_during_semester = total_assignment_score + total_midterm_score
    course_total_score = score_during_semester + total_final_score

    ratio = "0:0"
    if course_total_score > 0 and total_final_score > 0:
        score_during_semester_percent = round((score_during_semester / course_total_score) * 100)
        final_score_percent = 100 - score_during_semester_percent
        ratio = f"{score_during_semester_percent}:{final_score_percent}"
    elif course_total_score > 0:
        ratio = "100:0"

    component_scores = { c.id: {'current': sum(a.max_score for a in c.assessment_aspects), 'total': c.total_max_score} for c in all_components }

    return render_template('teacher/plan.html', title="แผนการสอน", section=section, learning_units=learning_units,
        component_scores=component_scores, total_scores={ 'assignment': total_assignment_score, 'midterm': total_midterm_score,
            'final': total_final_score, 'course_total': course_total_score, 'ratio': ratio })


@teacher_bp.route('/plan/unit/manage/<int:section_id>', methods=['GET', 'POST'], defaults={'unit_id': None})
@teacher_bp.route('/plan/unit/manage/<int:section_id>/<int:unit_id>', methods=['GET', 'POST'])
@login_required
@teacher_required
def manage_learning_unit(section_id, unit_id):
    section = CourseSection.query.get_or_404(section_id)
    if not TeacherAssignment.query.filter_by(teacher_id=current_user.id, course_section_id=section.id).first():
        abort(403)

    unit = LearningUnit.query.get(unit_id) if unit_id else None

    if request.method == 'POST':
        data = request.get_json()

        if not unit:
            unit = LearningUnit(course_section_id=section.id)
            db.session.add(unit)

        unit.title = data.get('title')
        unit.start_period = data.get('start_period')
        unit.end_period = data.get('end_period')
        unit.learning_standard = data.get('learning_standard')
        unit.learning_objectives = data.get('learning_objectives')
        unit.core_concepts = data.get('core_concepts')
        unit.learning_content = data.get('learning_content')
        unit.activities = data.get('activities')
        unit.media_sources = data.get('media_sources')

        # จัดการความสัมพันธ์ Many-to-Many
        unit.competencies = CompetencySubItem.query.filter(CompetencySubItem.id.in_(data.get('competencies', []))).all()
        unit.desirable_characteristics = CharacteristicSubItem.query.filter(CharacteristicSubItem.id.in_(data.get('characteristics', []))).all()
        unit.assessment_methods = MethodSubItem.query.filter(MethodSubItem.id.in_(data.get('assessment_methods', []))).all()

        try:
            db.session.commit()
            return jsonify({'status': 'success', 'message': 'บันทึกหน่วยการเรียนรู้เรียบร้อยแล้ว'})
        except Exception as e:
            db.session.rollback()
            return jsonify({'status': 'error', 'message': str(e)}), 500

    form = LearningUnitForm(obj=unit)

    # เพิ่ม logic เพื่อดึงข้อมูลความสัมพันธ์ทั้งหมดเพื่อส่งไปยังหน้าเว็บ
    selected_competency_ids = [c.id for c in unit.competencies] if unit else []
    selected_characteristic_ids = [c.id for c in unit.desirable_characteristics] if unit else []
    selected_method_ids = [m.id for m in unit.assessment_methods] if unit else []

    return render_template('teacher/manage_unit.html', form=form, section=section, unit=unit,
                           selected_competency_ids=selected_competency_ids,
                           selected_characteristic_ids=selected_characteristic_ids,
                           selected_method_ids=selected_method_ids)

@teacher_bp.route('/unit/<int:unit_id>/delete', methods=['POST'])
@login_required
@teacher_required
def delete_unit(unit_id):
    unit = LearningUnit.query.get_or_404(unit_id)
    if not TeacherAssignment.query.filter_by(teacher_id=current_user.id, course_section_id=unit.course_section_id).first():
        abort(403)
    db.session.delete(unit)
    db.session.commit()
    return jsonify({'status': 'success', 'message': 'ลบหน่วยการเรียนรู้สำเร็จ'})

@teacher_bp.route('/api/learning_units/<int:section_id>')
@login_required
@teacher_required
def get_learning_units(section_id):
    section = CourseSection.query.get_or_404(section_id)
    if not TeacherAssignment.query.filter_by(teacher_id=current_user.id, course_section_id=section.id).first():
        abort(403)

    units = LearningUnit.query.filter_by(course_section_id=section_id).order_by(LearningUnit.start_period).all()
    units_data = []
    for unit in units:
        units_data.append({
            'id': unit.id,
            'title': unit.title,
            'start_period': unit.start_period,
            'end_period': unit.end_period,
            'learning_objectives': unit.learning_objectives,
            'competencies': [c.name for c in unit.competencies],
            'characteristics': [c.name for c in unit.desirable_characteristics],
            'assessment_methods': [m.name for m in unit.assessment_methods],
            'component_count': len(unit.grade_components)
        })
    return jsonify(units_data)

@teacher_bp.route('/api/competencies')
@login_required
@teacher_required
def get_all_competencies():
    competencies = Competency.query.order_by('id').all()
    data = [{'id': c.id, 'name': c.name, 'sub_items': [{'id': sub.id, 'name': sub.name} for sub in c.sub_items]} for c in competencies]
    return jsonify(data)

@teacher_bp.route('/api/characteristics')
@login_required
@teacher_required
def get_all_characteristics():
    characteristics = DesirableCharacteristic.query.order_by('id').all()
    data = [{'id': c.id, 'name': c.name, 'sub_items': [{'id': sub.id, 'name': sub.name} for sub in c.sub_items]} for c in characteristics]
    return jsonify(data)

@teacher_bp.route('/api/assessment_methods')
@login_required
@teacher_required
def get_all_assessment_methods():
    methods = AssessmentMethod.query.order_by('id').all()
    data = [{'id': m.id, 'name': m.name, 'sub_items': [{'id': sub.id, 'name': sub.name} for sub in m.sub_items]} for m in methods]
    return jsonify(data)

# (โค้ดส่วน API ที่เหลือทั้งหมดให้คงไว้เหมือนเดิม)
@teacher_bp.route('/plan/<int:section_id>/api')
@login_required
@teacher_required
def plan_course_api(section_id):
    section = CourseSection.query.get_or_404(section_id)
    if not TeacherAssignment.query.filter_by(teacher_id=current_user.id, course_section_id=section.id).first():
        abort(403)

    all_components = GradeComponent.query.join(LearningUnit).filter(LearningUnit.course_section_id == section.id).all()

    total_midterm_score = sum(c.total_max_score for c in all_components if c.is_midterm_exam)
    total_final_score = sum(c.total_max_score for c in all_components if c.is_final_exam)
    total_assignment_score = sum(c.total_max_score for c in all_components if not c.is_midterm_exam and not c.is_final_exam)

    score_during_semester = total_assignment_score + total_midterm_score
    course_total_score = score_during_semester + total_final_score

    ratio = "N/A"
    if course_total_score > 0:
        score_during_semester_percent = round((score_during_semester / course_total_score) * 100)
        final_score_percent = 100 - score_during_semester_percent
        ratio = f"{score_during_semester_percent}:{final_score_percent}"
    else:
        ratio = "0:0"

    return jsonify({
        'total_scores': {
            'assignment': total_assignment_score,
            'midterm': total_midterm_score,
            'final': total_final_score,
            'course_total': course_total_score,
            'ratio': ratio
        }
    })

# ... (ส่วนที่เหลือทั้งหมดเหมือนเดิม)
@teacher_bp.route('/unit/<int:unit_id>/add_component', methods=['POST'])
@login_required
@teacher_required
def add_grade_component(unit_id):
    unit = LearningUnit.query.get_or_404(unit_id)
    if not TeacherAssignment.query.filter_by(teacher_id=current_user.id, course_section_id=unit.course_section_id).first():
        abort(403)

    form = GradeComponentForm(request.form)
    if form.validate_on_submit():
        new_component = GradeComponent(
            learning_unit_id=unit.id,
            name=form.name.data,
            total_max_score=form.total_max_score.data
        )

        is_exam = form.is_midterm_exam.data or form.is_final_exam.data
        if is_exam:
            new_component.is_midterm_exam = form.is_midterm_exam.data
            new_component.is_final_exam = form.is_final_exam.data
            new_component.is_critical_indicator = True
            new_component.is_midway_indicator = False
        else:
            new_component.is_midterm_exam = False
            new_component.is_final_exam = False
            is_midway = form.is_midway_indicator.data
            is_critical = form.is_critical_indicator.data
            if not is_midway and not is_critical: is_midway = True
            elif is_midway and is_critical: is_critical = False
            new_component.is_midway_indicator = is_midway
            new_component.is_critical_indicator = is_critical

        db.session.add(new_component)
        db.session.commit()
        return jsonify({
            'status': 'success',
            'component': { 'id': new_component.id, 'name': new_component.name, 'total_max_score': new_component.total_max_score,
                           'is_critical_indicator': new_component.is_critical_indicator, 'is_midway_indicator': new_component.is_midway_indicator }
        })
    return jsonify({'status': 'error', 'errors': form.errors})

@teacher_bp.route('/component/<int:component_id>/data')
@login_required
@teacher_required
def get_component_data(component_id):
    comp = GradeComponent.query.get_or_404(component_id)
    if not TeacherAssignment.query.filter_by(teacher_id=current_user.id, course_section_id=comp.learning_unit.course_section_id).first():
        abort(403)
    is_exam = comp.is_midterm_exam or comp.is_final_exam
    return jsonify({ 'id': comp.id, 'name': comp.name, 'total_max_score': comp.total_max_score,
                     'is_midway_indicator': comp.is_midway_indicator, 'is_critical_indicator': comp.is_critical_indicator, 'is_exam': is_exam })

@teacher_bp.route('/component/<int:component_id>/edit', methods=['POST'])
@login_required
@teacher_required
def edit_component(component_id):
    comp = GradeComponent.query.get_or_404(component_id)
    if not TeacherAssignment.query.filter_by(teacher_id=current_user.id, course_section_id=comp.learning_unit.course_section_id).first():
        abort(403)

    form = GradeComponentForm(request.form)
    if form.validate_on_submit():
        if not (comp.is_midterm_exam or comp.is_final_exam):
            is_midway = form.is_midway_indicator.data
            is_critical = form.is_critical_indicator.data
            if not is_midway and not is_critical: is_midway = True
            elif is_midway and is_critical: is_critical = False
            comp.is_midway_indicator = is_midway
            comp.is_critical_indicator = is_critical

        comp.name = form.name.data
        comp.total_max_score = form.total_max_score.data
        db.session.commit()
        return jsonify({'status': 'success', 'message': 'อัปเดตรายการคะแนนสำเร็จ', 'component': {
             'id': comp.id, 'name': comp.name, 'total_max_score': comp.total_max_score,
             'is_critical_indicator': comp.is_critical_indicator, 'is_midway_indicator': comp.is_midway_indicator }})
    return jsonify({'status': 'error', 'errors': form.errors})

@teacher_bp.route('/component/<int:component_id>/delete', methods=['POST'])
@login_required
@teacher_required
def delete_component(component_id):
    comp = GradeComponent.query.get_or_404(component_id)
    if not TeacherAssignment.query.filter_by(teacher_id=current_user.id, course_section_id=comp.learning_unit.course_section_id).first():
        abort(403)
    db.session.delete(comp)
    db.session.commit()
    return jsonify({'status': 'success', 'message': 'ลบรายการคะแนนสำเร็จ'})

@teacher_bp.route('/unit/<int:unit_id>/add_exam_score', methods=['POST'])
@login_required
@teacher_required
def add_exam_score_from_unit(unit_id):
    unit = LearningUnit.query.get_or_404(unit_id)
    if not TeacherAssignment.query.filter_by(teacher_id=current_user.id, course_section_id=unit.course_section_id).first():
        abort(403)

    data = request.get_json()
    exam_type = data.get('exam_type')
    score = float(data.get('score', 0))

    if not exam_type or score <= 0:
        return jsonify({'status': 'error', 'message': 'ข้อมูลไม่ถูกต้อง'}), 400

    is_midterm = exam_type == 'midterm'
    exam_name = "สอบกลางภาค" if is_midterm else "สอบปลายภาค"

    existing_component = GradeComponent.query.filter_by(learning_unit_id=unit.id, is_midterm_exam=is_midterm, is_final_exam=not is_midterm).first()

    if existing_component:
        existing_component.total_max_score = score
        message = 'อัปเดตคะแนนสอบสำเร็จ'
    else:
        new_component = GradeComponent(name=exam_name, total_max_score=score, learning_unit_id=unit.id,
                                       is_midterm_exam=is_midterm, is_final_exam=not is_midterm, is_critical_indicator=True)
        db.session.add(new_component)
        message = 'เพิ่มคะแนนสอบสำเร็จ'

    db.session.commit()
    return jsonify({'status': 'success', 'message': message})

@teacher_bp.route('/component/<int:component_id>/details')
@login_required
@teacher_required
def get_component_details(component_id):
    comp = GradeComponent.query.get_or_404(component_id)
    if not TeacherAssignment.query.filter_by(teacher_id=current_user.id, course_section_id=comp.learning_unit.course_section_id).first():
        abort(403)
    aspects_data = [{'id': aspect.id, 'dimension_name': aspect.dimension.name, 'dimension_code': aspect.dimension.code,
                     'description': aspect.description, 'max_score': aspect.max_score}
                    for aspect in comp.assessment_aspects]
    current_score = sum(aspect['max_score'] for aspect in aspects_data)
    return jsonify({ 'id': comp.id, 'name': comp.name, 'total_max_score': comp.total_max_score,
                   'current_score': current_score, 'aspects': aspects_data })

@teacher_bp.route('/component/<int:component_id>/add_aspect', methods=['POST'])
@login_required
@teacher_required
def add_assessment_aspect(component_id):
    comp = GradeComponent.query.get_or_404(component_id)
    if not TeacherAssignment.query.filter_by(teacher_id=current_user.id, course_section_id=comp.learning_unit.course_section_id).first():
        abort(403)
    form = AssessmentAspectForm()
    if form.validate_on_submit():
        new_aspect = AssessmentAspect(grade_component_id=comp.id, dimension=form.dimension.data,
                                      description=form.description.data, max_score=form.max_score.data)
        db.session.add(new_aspect)
        db.session.commit()
        return jsonify({ 'status': 'success',
            'aspect': { 'id': new_aspect.id, 'dimension_name': new_aspect.dimension.name, 'dimension_code': new_aspect.dimension.code,
                        'description': new_aspect.description, 'max_score': new_aspect.max_score }
        })
    return jsonify({'status': 'error', 'errors': form.errors})

@teacher_bp.route('/aspect/<int:aspect_id>/delete', methods=['POST'])
@login_required
@teacher_required
def delete_assessment_aspect(aspect_id):
    aspect = AssessmentAspect.query.get_or_404(aspect_id)
    if not TeacherAssignment.query.filter_by(teacher_id=current_user.id, course_section_id=aspect.grade_component.learning_unit.course_section_id).first():
        abort(403)

    score_to_remove = aspect.max_score
    db.session.delete(aspect)
    db.session.commit()

    return jsonify({ 'status': 'success', 'message': 'ลบองค์ประกอบสำเร็จ', 'removed_score': score_to_remove })

@teacher_bp.route('/analyze-objectives', methods=['POST'])
@login_required
@teacher_required
def analyze_objectives():
    data = request.get_json()
    objectives_text = data.get('objectives', '')
    characteristics_text = data.get('characteristics', '')
    competencies_text = data.get('competencies', '')

    suggestions = []
    if any(keyword in objectives_text for keyword in ['อธิบาย', 'บอก', 'ระบุ', 'เปรียบเทียบ']):
        suggestions.append({'type': 'Test', 'dimension': 'K', 'name': 'แบบทดสอบวัดความรู้'})
    if any(keyword in objectives_text + competencies_text for keyword in ['แสดงออก', 'ปฏิบัติ', 'สาธิต', 'นำเสนอ', 'สื่อสาร']):
        suggestions.append({'type': 'Performance-based Assessment', 'dimension': 'S', 'name': 'ประเมินการปฏิบัติ'})
    if any(keyword in objectives_text + characteristics_text for keyword in ['เห็นคุณค่า', 'มีวินัย', 'รับผิดชอบ', 'ร่วมมือ']):
        suggestions.append({'type': 'Observation Checklist', 'dimension': 'A', 'name': 'สังเกตพฤติกรรม'})

    return jsonify({'suggestions': suggestions})

@teacher_bp.route('/api/assessment-tools')
@login_required
@teacher_required
def get_assessment_tools():
    tools = AssessmentTool.query.order_by(AssessmentTool.name).all()
    tools_data = [{'id': tool.id, 'name': tool.name, 'type': tool.tool_type} for tool in tools]
    return jsonify(tools_data)

@teacher_bp.route('/component/<int:component_id>/link_tool', methods=['POST'])
@login_required
@teacher_required
def link_tool_to_component(component_id):
    comp = GradeComponent.query.get_or_404(component_id)
    if not TeacherAssignment.query.filter_by(teacher_id=current_user.id, course_section_id=comp.learning_unit.course_section_id).first():
        abort(403)

    tool_id = request.json.get('tool_id')
    if tool_id:
        comp.assessment_tool_id = tool_id
        tool_name = AssessmentTool.query.get(tool_id).name
    else:
        comp.assessment_tool_id = None
        tool_name = None

    db.session.commit()
    return jsonify({'status': 'success', 'tool_name': tool_name})

@teacher_bp.route('/homeroom_enrollment', methods=['GET', 'POST'])
@login_required
@admin_required
def homeroom_enrollment():
    if request.method == 'POST':
        student_id = request.json.get('student_id')
        classroom_id = request.json.get('classroom_id')
        academic_year_id = request.json.get('academic_year_id')

        # Check if enrollment already exists
        existing_enrollment = HomeroomEnrollment.query.filter_by(
            student_id=student_id,
            classroom_id=classroom_id,
            academic_year_id=academic_year_id
        ).first()

        if existing_enrollment:
            return jsonify({'status': 'fail', 'message': 'Student is already enrolled in this homeroom for the selected academic year.'})

        try:
            new_enrollment = HomeroomEnrollment(
                student_id=student_id,
                classroom_id=classroom_id,
                academic_year_id=academic_year_id
            )
            db.session.add(new_enrollment)
            db.session.commit()
            return jsonify({'status': 'success', 'message': 'Student enrolled successfully.'})
        except Exception as e:
            db.session.rollback()
            return jsonify({'status': 'fail', 'message': str(e)})

    # GET request
    academic_years = AcademicYear.query.order_by(AcademicYear.year.desc()).all()
    classrooms = Classroom.query.order_by(Classroom.name).all()
    students = Student.query.order_by(Student.id_code).all()
    enrollments = HomeroomEnrollment.query.join(Student).join(Classroom).join(AcademicYear).order_by(AcademicYear.year.desc(), Classroom.name).all()

    return render_template('teacher/homeroom_enrollment.html',
                           academic_years=academic_years,
                           classrooms=classrooms,
                           students=students,
                           enrollments=enrollments)

@teacher_bp.route('/auto_enroll_students', methods=['POST'])
@login_required
@admin_required
def auto_enroll_students():
    data = request.json
    academic_year_id = data.get('academic_year_id')
    classroom_id = data.get('classroom_id')

    if not academic_year_id or not classroom_id:
        return jsonify({'status': 'error', 'message': 'Academic year and classroom must be selected.'}), 400

    try:
        # Find all students in the specified homeroom for the academic year
        students_to_enroll = [
            enrollment.student for enrollment in HomeroomEnrollment.query.filter_by(
                academic_year_id=academic_year_id,
                classroom_id=classroom_id
            ).all()
        ]

        # Find all course sections for the specified classroom in the academic year
        course_sections = CourseSection.query.filter_by(
            academic_year_id=academic_year_id,
            classroom_id=classroom_id
        ).all()

        enrollment_count = 0
        section_count = len(course_sections)

        for student in students_to_enroll:
            for section in course_sections:
                # Check if the student is not already enrolled in the section
                if student not in section.students:
                    section.students.append(student)
                    enrollment_count += 1

        db.session.commit()
        
        return jsonify({
            'status': 'success',
            'message': f"Successfully enrolled {len(students_to_enroll)} students into {section_count} courses.",
            'new_enrollments_count': enrollment_count
        })

    except Exception as e:
        db.session.rollback()
        return jsonify({'status': 'error', 'message': str(e)}), 500