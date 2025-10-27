# app/admin/forms.py

from flask_wtf import FlaskForm
from wtforms.widgets import CheckboxInput, ListWidget
from wtforms import (BooleanField, DateField, FloatField, IntegerField, PasswordField, 
                     SelectField, StringField, SubmitField, TextAreaField, ValidationError)
from wtforms.validators import DataRequired, Length, Email, EqualTo, Optional
from wtforms_sqlalchemy.fields import QuerySelectMultipleField, QuerySelectField
from app.models import AcademicYear, Classroom, GradeLevel, Role, Semester, Student, Subject, SubjectGroup, SubjectType, User, AssessmentDimension, AssessmentTemplate

# --- Helper Functions for Forms ---

def get_roles():
    return Role.query.order_by(Role.id).all()

def get_all_academic_years():
    return AcademicYear.query.order_by(AcademicYear.year.desc()).all()

def get_all_grade_levels():
    return GradeLevel.query.order_by(GradeLevel.id).all()

def get_subject_groups():
    return SubjectGroup.query.order_by(SubjectGroup.name).all()

def get_subject_types():
    return SubjectType.query.order_by(SubjectType.name).all()

def get_classrooms_for_advisors():
    # ในอนาคตอาจจะต้องกรองตามปีการศึกษาปัจจุบัน
    return Classroom.query.order_by(Classroom.name).all()

def get_all_semesters():
    return Semester.query.join(AcademicYear).order_by(AcademicYear.year.desc(), Semester.term.asc()).all()
    
def get_teachers():
    # ในอนาคตสามารถกรองจาก Role 'Teacher' ได้
    return User.query.order_by(User.first_name).all()

def get_all_students():
    return Student.query.order_by(Student.student_id).all()

# --- Form Classes (ฉบับปรับปรุง) ---

class SettingsForm(FlaskForm):
    school_name = StringField('ชื่อโรงเรียน', validators=[DataRequired()])
    school_address = TextAreaField('ที่อยู่โรงเรียน')
    director_name = StringField('ชื่อผู้อำนวยการ')
    deputy_director_name = StringField('ชื่อรองผู้อำนวยการ')
    submit = SubmitField('บันทึกการตั้งค่า')
    
class AddUserForm(FlaskForm):
    username = StringField('ชื่อผู้ใช้ (Username)', validators=[DataRequired(), Length(min=4, max=64)])
    email = StringField('อีเมล', validators=[Optional(), Email()]) # แก้ไข: ไม่บังคับกรอก
    name_prefix = StringField('คำนำหน้าชื่อ', validators=[Optional(), Length(max=20)]) # แก้ไข: ไม่บังคับกรอก
    first_name = StringField('ชื่อจริง', validators=[DataRequired()])
    last_name = StringField('นามสกุล', validators=[DataRequired()])
    job_title = StringField('ตำแหน่ง', validators=[Optional(), Length(max=100)])
    password = PasswordField('รหัสผ่าน', validators=[DataRequired()])
    password2 = PasswordField('ยืนยันรหัสผ่าน', validators=[DataRequired(), EqualTo('password', message='รหัสผ่านต้องตรงกัน')])
    roles = QuerySelectMultipleField('บทบาท', query_factory=get_roles, get_label='name', widget=ListWidget(prefix_label=False), option_widget=CheckboxInput())
    submit = SubmitField('เพิ่มผู้ใช้งาน')

class EditUserForm(FlaskForm):
    username = StringField('ชื่อผู้ใช้ (Username)', validators=[DataRequired(), Length(min=4, max=64)])
    email = StringField('อีเมล', validators=[Optional(), Email()]) # แก้ไข: ไม่บังคับกรอก
    name_prefix = StringField('คำนำหน้าชื่อ', validators=[Optional(), Length(max=20)]) # แก้ไข: ไม่บังคับกรอก
    first_name = StringField('ชื่อจริง', validators=[DataRequired()])
    last_name = StringField('นามสกุล', validators=[DataRequired()])
    job_title = StringField('ตำแหน่ง', validators=[Optional(), Length(max=100)])
    password = PasswordField('รหัสผ่านใหม่ (กรอกหากต้องการเปลี่ยน)', validators=[Optional()])
    password2 = PasswordField('ยืนยันรหัสผ่านใหม่', validators=[EqualTo('password', message='รหัสผ่านต้องตรงกัน')])
    roles = QuerySelectMultipleField('บทบาท', query_factory=get_roles, get_label='name', widget=ListWidget(prefix_label=False), option_widget=CheckboxInput())
    submit = SubmitField('บันทึกการเปลี่ยนแปลง')
    
class GradeLevelForm(FlaskForm):
    name = StringField('ชื่อระดับชั้น (เช่น มัธยมศึกษาปีที่ 1)', validators=[DataRequired(), Length(min=2, max=50)])
    short_name = StringField('ชื่อย่อ (เช่น ม.1)', validators=[DataRequired(), Length(min=1, max=10)])
    submit = SubmitField('บันทึกข้อมูล')

class SubjectGroupForm(FlaskForm):
    # แก้ไข: ทำให้ฟอร์มนี้เรียบง่ายสำหรับหน้า Add โดยเฉพาะ
    name = StringField('ชื่อกลุ่มสาระการเรียนรู้', validators=[DataRequired(), Length(min=3, max=100)])
    submit = SubmitField('สร้างกลุ่มสาระฯ')

class SubjectTypeForm(FlaskForm):
    name = StringField('ชื่อประเภทวิชา (เช่น รายวิชาพื้นฐาน)', validators=[DataRequired(), Length(min=3, max=100)])
    submit = SubmitField('บันทึกข้อมูล')

class RoleForm(FlaskForm):
    name = StringField('ชื่อบทบาท (ภาษาอังกฤษเท่านั้น)', validators=[DataRequired(), Length(min=2, max=64)])
    description = TextAreaField('คำอธิบายบทบาท')
    submit = SubmitField('บันทึกข้อมูล')

class AcademicYearForm(FlaskForm):
    year = IntegerField('ปีการศึกษา (พ.ศ.)', validators=[DataRequired()])
    submit = SubmitField('บันทึกข้อมูล')

class SemesterForm(FlaskForm):
    term = SelectField('ภาคเรียนที่', choices=[(1, '1'), (2, '2'), (3, 'ภาคฤดูร้อน')], coerce=int, validators=[DataRequired()])
    academic_year = QuerySelectField('ของปีการศึกษา', query_factory=get_all_academic_years, get_label='year', allow_blank=False, validators=[DataRequired()])
    start_date = DateField('วันเปิดภาคเรียน (YYYY-MM-DD)', format='%Y-%m-%d', validators=[Optional()])
    end_date = DateField('วันปิดภาคเรียน (YYYY-MM-DD)', format='%Y-%m-%d', validators=[Optional()])
    is_current = BooleanField('กำหนดให้เป็นภาคเรียนปัจจุบัน')
    submit = SubmitField('บันทึกข้อมูล')

class SubjectForm(FlaskForm):
    subject_code = StringField('รหัสวิชา', validators=[DataRequired(), Length(max=20)])
    name = StringField('ชื่อรายวิชา', validators=[DataRequired(), Length(max=100)])
    credit = FloatField('หน่วยกิต', validators=[DataRequired()], render_kw={'type': 'number', 'step': '0.5', 'min': '0.5'})
    subject_group = QuerySelectField('กลุ่มสาระการเรียนรู้', query_factory=get_subject_groups, get_label='name', allow_blank=False, validators=[DataRequired()])
    subject_type = QuerySelectField('ประเภทวิชา', query_factory=get_subject_types, get_label='name', allow_blank=False, validators=[DataRequired()])
    grade_levels = QuerySelectMultipleField('รายวิชานี้สำหรับระดับชั้น', query_factory=get_all_grade_levels, get_label='name', widget=ListWidget(prefix_label=False), option_widget=CheckboxInput())
    submit = SubmitField('บันทึกข้อมูล')

class CurriculumForm(FlaskForm):
    semester = SelectField('ภาคเรียน', coerce=int)
    grade_level = SelectField('ระดับชั้น', coerce=int)

class ClassroomForm(FlaskForm):
    name = StringField('ชื่อห้องเรียน (เช่น ม.1/1)', validators=[DataRequired(), Length(max=50)])
    academic_year = QuerySelectField('ปีการศึกษา', query_factory=get_all_academic_years, get_label='year', allow_blank=False)
    grade_level = QuerySelectField('ระดับชั้น', query_factory=get_all_grade_levels, get_label='name', allow_blank=False)
    submit = SubmitField('บันทึกข้อมูล')

class StudentForm(FlaskForm):
    student_id = StringField('รหัสนักเรียน', validators=[DataRequired(), Length(max=20)])
    name_prefix = StringField('คำนำหน้าชื่อ', validators=[DataRequired(), Length(max=20)])
    first_name = StringField('ชื่อจริง', validators=[DataRequired(), Length(max=64)])
    last_name = StringField('นามสกุล', validators=[DataRequired(), Length(max=64)])
    submit = SubmitField('บันทึกข้อมูล')

class EnrollmentForm(FlaskForm):
    students = QuerySelectMultipleField(
        'เลือกนักเรียนเข้าห้องเรียน (ติ๊กเลือกนักเรียนที่ต้องการให้อยู่ในห้องนี้)',
        query_factory=get_all_students,
        get_label=lambda student: f"{student.student_id} - {student.name_prefix}{student.first_name} {student.last_name}",
        widget=ListWidget(prefix_label=False),
        option_widget=CheckboxInput()
    )
    submit = SubmitField('บันทึกการลงทะเบียน')

class AssignHeadsForm(FlaskForm):
    heads = QuerySelectMultipleField(
        'เลือกผู้ใช้งานเพื่อแต่งตั้งเป็นหัวหน้ากลุ่มสาระฯ',
        query_factory=get_teachers, # เรามีฟังก์ชันนี้อยู่แล้ว
        get_label=lambda user: f"{user.name_prefix}{user.first_name} {user.last_name}",
        widget=ListWidget(prefix_label=False),
        option_widget=CheckboxInput()
    )
    submit = SubmitField('บันทึกข้อมูล')

class AssignAdvisorsForm(FlaskForm):
    advisors = QuerySelectMultipleField(
        'เลือกผู้ใช้งานเพื่อแต่งตั้งเป็นครูที่ปรึกษา',
        query_factory=get_teachers,
        get_label=lambda user: f"{user.name_prefix or ''}{user.first_name} {user.last_name}",
        widget=ListWidget(prefix_label=False),
        option_widget=CheckboxInput()
    )
    submit = SubmitField('บันทึกข้อมูล')

class AssessmentDimensionForm(FlaskForm):
    code = StringField('รหัสย่อ (เช่น K, P, A)', validators=[DataRequired(), Length(max=10)])
    name = StringField('ชื่อเต็ม (เช่น ความรู้)', validators=[DataRequired(), Length(max=100)])
    description = TextAreaField('คำอธิบาย (ไม่บังคับ)')
    submit = SubmitField('บันทึกข้อมูล')
    
class AssessmentTemplateForm(FlaskForm):
    name = StringField('ชื่อแม่แบบการประเมิน', validators=[DataRequired(), Length(max=150)])
    description = TextAreaField('คำอธิบาย (ไม่บังคับ)')
    submit = SubmitField('บันทึกแม่แบบ')

class RubricLevelForm(FlaskForm):
    label = StringField('ชื่อระดับคะแนน (เช่น ดีเยี่ยม)', validators=[DataRequired(), Length(max=50)])
    value = FloatField('ค่าคะแนน', validators=[DataRequired()])
    submit = SubmitField('บันทึก')

class AssessmentTopicForm(FlaskForm):
    name = StringField('ชื่อหัวข้อ', validators=[DataRequired(), Length(max=255)])
    submit = SubmitField('บันทึก')