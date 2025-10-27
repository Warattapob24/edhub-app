# app/forms.py (ฉบับแก้ไข)
from flask_wtf import FlaskForm
from flask_wtf.file import FileField, FileRequired, FileAllowed
from wtforms import (StringField, PasswordField, BooleanField, SubmitField,
                     SelectField, FloatField, TextAreaField, IntegerField, SelectMultipleField,
                     TimeField)
from wtforms.validators import DataRequired, EqualTo, NumberRange, Length, Optional, ValidationError
from datetime import datetime

class LoginForm(FlaskForm):
    username = StringField('ชื่อผู้ใช้ (Username)', validators=[DataRequired()])
    password = PasswordField('รหัสผ่าน (Password)', validators=[DataRequired()])
    remember_me = BooleanField('จดจำฉันไว้ในระบบ')
    submit = SubmitField('เข้าสู่ระบบ')

class EditRoleForm(FlaskForm):
    label = StringField('ชื่อที่แสดงผล (Label)', validators=[DataRequired()])
    submit = SubmitField('บันทึกการเปลี่ยนแปลง')

class CreateUserForm(FlaskForm):
    username = StringField('ชื่อผู้ใช้ (Username)', validators=[DataRequired()])
    full_name = StringField('ชื่อ-นามสกุลเต็ม', validators=[DataRequired()])
    department = SelectField('กลุ่มสาระการเรียนรู้', choices=[], validators=[Optional()])
    roles = SelectMultipleField('บทบาท (กด Ctrl/Cmd เพื่อเลือกหลายรายการ)', coerce=int, validators=[DataRequired()])
    password = PasswordField('รหัสผ่าน', validators=[DataRequired()])
    password2 = PasswordField(
        'ยืนยันรหัสผ่าน', validators=[DataRequired(), EqualTo('password', message='รหัสผ่านต้องตรงกัน')])
    submit = SubmitField('สร้างผู้ใช้')

class SubjectForm(FlaskForm):
    subject_code = StringField('รหัสวิชา', validators=[DataRequired()])
    name = StringField('ชื่อวิชา', validators=[DataRequired()])
    department = StringField('กลุ่มสาระการเรียนรู้', validators=[DataRequired()])
    default_credits = FloatField('หน่วยกิต', validators=[DataRequired(), NumberRange(min=0.5, max=5.0)])
    required_room_type = SelectField('ประเภทห้องที่ต้องการ', choices=[
        ('', '- ไม่จำเป็นต้องใช้ห้องพิเศษ -'),
        ('ห้องปฏิบัติการวิทยาศาสตร์', 'ห้องปฏิบัติการวิทยาศาสตร์'),
        ('ห้องคอมพิวเตอร์', 'ห้องคอมพิวเตอร์'),
        ('ห้องดนตรี', 'ห้องดนตรี'),
        ('ห้องศิลปะ', 'ห้องศิลปะ')
    ], validators=[Optional()])

    submit = SubmitField('บันทึกข้อมูล')
    
class SchoolSettingsForm(FlaskForm):
    school_name = StringField('ชื่อโรงเรียน', validators=[DataRequired()])
    school_director = StringField('ชื่อผู้อำนวยการ', validators=[DataRequired()])
    submit = SubmitField('บันทึกข้อมูล')

class ImportStudentsForm(FlaskForm):
    # แก้ไข FileAllowed ให้รองรับ csv, xlsx, xls
    upload_file = FileField('เลือกไฟล์ CSV หรือ Excel', validators=[
        FileRequired(),
        FileAllowed(['csv', 'xlsx', 'xls'], 'ต้องเป็นไฟล์ CSV หรือ Excel เท่านั้น!')
    ])
    submit = SubmitField('นำเข้าข้อมูล')

class CreateCourseForm(FlaskForm):
    subject = SelectField('เลือกรายวิชาจากคลัง', coerce=int, validators=[DataRequired()])
    class_group = SelectField('สำหรับกลุ่มเรียน (ห้อง/ทับ)', coerce=int, validators=[DataRequired()])
    room = StringField('ระบุสถานที่เรียน (เช่น 521, ห้องสมุด)', validators=[Optional(), Length(max=100)])
    academic_year = IntegerField('ปีการศึกษา', validators=[DataRequired(), NumberRange(min=2500, max=3000)])
    semester = SelectField('ภาคเรียน', choices=[('1', '1'), ('2', '2'), ('3', 'ฤดูร้อน')], validators=[DataRequired()])
    coursework_ratio = IntegerField('สัดส่วนคะแนนระหว่างภาค (เต็ม 100)', default=70, validators=[DataRequired(), NumberRange(min=0, max=100)])
    submit_course = SubmitField('สร้างคลาสเรียน')

class AddComponentForm(FlaskForm):
    name = StringField('ชื่อหน่วยการเรียนรู้/ชื่องาน', validators=[DataRequired()])
    indicator = TextAreaField('ตัวชี้วัด')
    component_type = SelectField('ประเภท', choices=[('Formative', 'ระหว่างทาง (Formative)'), ('Summative', 'ปลายทาง (Summative)')], validators=[DataRequired()])
    exam_type = SelectField('ประเภทการสอบ (ถ้ามี)', choices=[
        ('', 'ไม่มีการสอบกลาง/ปลายภาค'),
        ('midterm', 'ใช้สอบกลางภาค'),
        ('final', 'ใช้สอบปลายภาค')
    ])
    max_score_k = IntegerField('K', default=0, validators=[NumberRange(min=0)])
    max_score_p = IntegerField('P', default=0, validators=[NumberRange(min=0)])
    max_score_a = IntegerField('A', default=0, validators=[NumberRange(min=0)])
    total_max_score = IntegerField('คะแนนเต็ม (การสอบ)', validators=[Optional(), NumberRange(min=0)])
    submit_component = SubmitField('เพิ่มองค์ประกอบ')

class EnrollStudentForm(FlaskForm):
    students = SelectMultipleField('เลือกนักเรียนเพื่อลงทะเบียน', coerce=int, validators=[DataRequired()])
    submit_enrollment = SubmitField('ลงทะเบียนนักเรียน')

class GradeLevelForm(FlaskForm):
    name = StringField('ชื่อสายชั้น (เช่น มัธยมศึกษาปีที่ 1)', validators=[DataRequired()])
    submit_grade = SubmitField('สร้างสายชั้น')

class RoleForm(FlaskForm):
    """ฟอร์มสำหรับสร้างและแก้ไข Role"""
    key = StringField('Key (ภาษาอังกฤษตัวเล็ก, ห้ามซ้ำ)', validators=[DataRequired()])
    label = StringField('ชื่อที่แสดงผล (Label)', validators=[DataRequired()])
    submit = SubmitField('บันทึก')

class EditUserForm(FlaskForm):
    """ฟอร์มสำหรับแก้ไขผู้ใช้งาน"""
    username = StringField('ชื่อผู้ใช้ (Username)', validators=[DataRequired()])
    full_name = StringField('ชื่อ-นามสกุลเต็ม', validators=[DataRequired()])
    department = SelectField('กลุ่มสาระการเรียนรู้', choices=[], validators=[Optional()])
    roles = SelectMultipleField('บทบาท (กด Ctrl/Cmd เพื่อเลือกหลายรายการ)', coerce=int, validators=[DataRequired()])
    status = SelectField('สถานะ', choices=[('Active', 'ปฏิบัติงาน (Active)'), ('Transferred', 'ย้าย'), ('Retired', 'เกษียณอายุ')])
    max_periods_per_day = IntegerField('จำนวนคาบสอนสูงสุดต่อวัน (ถ้ามี)', validators=[Optional(), NumberRange(min=1, max=10)])
    max_periods_per_week = IntegerField('จำนวนคาบสอนสูงสุดต่อสัปดาห์ (ถ้ามี)', validators=[Optional(), NumberRange(min=1, max=50)])
    password = PasswordField('รหัสผ่านใหม่ (เว้นว่างไว้หากไม่ต้องการเปลี่ยน)', validators=[Optional()])
    password2 = PasswordField(
        'ยืนยันรหัสผ่านใหม่', validators=[EqualTo('password', message='รหัสผ่านต้องตรงกัน')])
        
    submit = SubmitField('บันทึกการเปลี่ยนแปลง')

class ClassGroupForm(FlaskForm):
    room_number = StringField('หมายเลขห้อง (เช่น 1, 2, EP1)', validators=[DataRequired()])
    academic_year = IntegerField('ปีการศึกษา', default=datetime.now().year + 543, validators=[DataRequired()])
    advisors = SelectMultipleField('เลือกครูที่ปรึกษา (กด Ctrl/Cmd เพื่อเลือกหลายคน)', coerce=int)
    submit_class = SubmitField('สร้าง/บันทึกห้องเรียน')

class StudentForm(FlaskForm):
    """Form for editing a student."""
    student_id = StringField('รหัสนักเรียน', validators=[DataRequired()])
    prefix = StringField('คำนำหน้าชื่อ', validators=[DataRequired()])
    first_name = StringField('ชื่อจริง', validators=[DataRequired()])
    last_name = StringField('นามสกุล', validators=[DataRequired()])
    class_number = IntegerField('เลขที่')
    class_group = SelectField('ย้ายไปห้องเรียน', coerce=int)
    status = SelectField('สถานะนักเรียน', choices=[
        ('กำลังศึกษา', 'กำลังศึกษา'), 
        ('สำเร็จการศึกษา', 'สำเร็จการศึกษา'), 
        ('ย้ายออก', 'ย้ายออก')
    ])
    submit = SubmitField('บันทึกข้อมูล')

class EvaluationTopicForm(FlaskForm):
    assessment_type = SelectField('ประเภทการประเมิน', choices=[
        ('คุณลักษณะอันพึงประสงค์', 'คุณลักษณะอันพึงประสงค์'),
        ('การอ่าน คิดวิเคราะห์ และเขียน', 'การอ่าน คิดวิเคราะห์ และเขียน'),
        ('สมรรถนะ', 'สมรรถนะ')
    ], validators=[DataRequired()])
    name = StringField('ชื่อหัวข้อ', validators=[DataRequired()])
    display_order = IntegerField('ลำดับการแสดงผล', validators=[DataRequired()])
    submit = SubmitField('บันทึก')

class StudentLoginForm(FlaskForm):
    student_id = StringField('รหัสนักเรียน', validators=[DataRequired()])
    password = PasswordField('รหัสผ่าน', validators=[DataRequired()])
    remember_me = BooleanField('จดจำฉันไว้ในระบบ')
    submit = SubmitField('เข้าสู่ระบบ')

class TimetableSlotForm(FlaskForm):
    class_group = SelectField('สำหรับห้องเรียน', coerce=int, validators=[DataRequired()])
    day_of_week = SelectField('วัน', choices=[
        ('0', 'วันจันทร์'),
        ('1', 'วันอังคาร'),
        ('2', 'วันพุธ'),
        ('3', 'วันพฤหัสบดี'),
        ('4', 'วันศุกร์'),
        ('5', 'วันเสาร์'),
        ('6', 'วันอาทิตย์')
    ], validators=[DataRequired()])
    start_time = TimeField('เวลาเริ่มต้น', validators=[DataRequired()])
    end_time = TimeField('เวลาสิ้นสุด', validators=[DataRequired()])
    submit = SubmitField('บันทึกคาบสอน')

class TimetableBlockForm(FlaskForm):
    name = StringField('ชื่อกิจกรรม/กฎการบล็อก', validators=[DataRequired(), Length(max=100)])
    days_of_week = SelectMultipleField('วันที่จะบล็อก (เลือกได้หลายวัน)', choices=[
        ('0', 'วันจันทร์'), ('1', 'วันอังคาร'), ('2', 'วันพุธ'),
        ('3', 'วันพฤหัสบดี'), ('4', 'วันศุกร์'), ('5', 'วันเสาร์'),
        ('6', 'วันอาทิตย์')
    ], validators=[DataRequired()])
    start_time = TimeField('เวลาเริ่มต้น', validators=[DataRequired()])
    end_time = TimeField('เวลาสิ้นสุด', validators=[DataRequired()])
    academic_year = IntegerField('สำหรับปีการศึกษา', default=datetime.now().year + 543, validators=[DataRequired()])
    
    # --- จุดที่ 1: อัปเกรด field เดิม ---
    # เปลี่ยน DataRequired เป็น Optional เพราะบางกฎอาจใช้กับบทบาทแทน
    applies_to_grade_levels = SelectMultipleField(
        'ใช้กับสายชั้น (ถ้ามี)', 
        coerce=int, 
        validators=[Optional()]
    )
    
    # --- จุดที่ 2: เพิ่ม field ใหม่ ---
    applies_to_roles = SelectMultipleField(
        'ใช้กับบทบาท (ถ้ามี)',
        coerce=int,
        validators=[Optional()]
    )

    submit = SubmitField('บันทึกกฎ')

    # --- จุดที่ 3: เพิ่มคาถาตรวจสอบพิเศษ ---
    # เพื่อป้องกันการสร้างกฎที่ไม่ได้เลือกกลุ่มเป้าหมายเลย
    def validate(self, **kwargs):
        # รัน validator พื้นฐานก่อน
        if not super().validate(**kwargs):
            return False
        
        # ตรวจสอบแบบกำหนดเอง
        if not self.applies_to_grade_levels.data and not self.applies_to_roles.data:
            msg = "กรุณาเลือก 'สายชั้น' หรือ 'บทบาท' อย่างน้อยหนึ่งอย่าง"
            self.applies_to_grade_levels.errors.append(msg)
            self.applies_to_roles.errors.append(msg)
            return False
        
        return True

class SchoolPeriodForm(FlaskForm):
    period_number = IntegerField('ลำดับคาบ', validators=[DataRequired()])
    name = StringField('ชื่อเรียก', validators=[DataRequired(), Length(max=50)]) # เช่น คาบเรียน, คาบพัก
    start_time = TimeField('เวลาเริ่มต้น', validators=[DataRequired()])
    end_time = TimeField('เวลาสิ้นสุด', validators=[DataRequired()])
    submit = SubmitField('บันทึก')
    
class SchedulingRuleForm(FlaskForm):
    rule_type = SelectField('ประเภทของเงื่อนไข', choices=[
        ('', '- ไม่มีเงื่อนไขพิเศษ -'), # <--- เพิ่มตัวเลือกเริ่มต้น
        ('group_together', 'ขอสอนคาบติดกัน'),
        ('spread_out', 'ขอสอนคนละวันกัน'),
        ('prefer_morning', 'ขอคาบเรียนช่วงเช้า (ก่อนพักเที่ยง)'),
        ('prefer_afternoon', 'ขอคาบเรียนช่วงบ่าย (หลังพักเที่ยง)')
    ], validators=[Optional()]) # <--- เปลี่ยนเป็น Optional

    value = StringField('ค่า (ถ้าจำเป็น)',
                        description="เช่น ใส่ '2' สำหรับ 'ขอสอนคาบติดกัน 2 คาบ'",
                        validators=[Optional(), Length(max=50)])

    submit_rule = SubmitField('เพิ่ม/แก้ไขเงื่อนไข')

class CurriculumForm(FlaskForm):
    academic_year = IntegerField('ปีการศึกษา', default=datetime.now().year + 543, validators=[DataRequired()])
    semester = SelectField('ภาคเรียน', choices=[('1', '1'), ('2', '2')], validators=[DataRequired()])
    grade_level = SelectField('สายชั้น', coerce=int, validators=[DataRequired()])
    subjects = SelectMultipleField('เลือกรายวิชา (กด Ctrl/Cmd เพื่อเลือกหลายรายการ)', coerce=int, validators=[DataRequired()])
    submit = SubmitField('บันทึกหลักสูตร')

class RoomForm(FlaskForm):
    name = StringField('ชื่อสถานที่/ห้อง (เช่น "521", "ห้องคอมพิวเตอร์ 1")', validators=[DataRequired()])
    room_type = SelectField('ประเภทห้อง', choices=[
        ('ห้องเรียนปกติ', 'ห้องเรียนปกติ'),
        ('ห้องปฏิบัติการวิทยาศาสตร์', 'ห้องปฏิบัติการวิทยาศาสตร์'),
        ('ห้องคอมพิวเตอร์', 'ห้องคอมพิวเตอร์'),
        ('ห้องดนตรี', 'ห้องดนตรี'),
        ('ห้องศิลปะ', 'ห้องศิลปะ')
    ], validators=[DataRequired()])
    submit = SubmitField('บันทึก')

class RestoreForm(FlaskForm):
    backup_file = FileField('เลือกไฟล์ .zip ที่ต้องการกู้คืน', validators=[
        FileRequired(),
        FileAllowed(['zip'], 'ต้องเป็นไฟล์ .zip เท่านั้น!')
    ])
    submit_restore = SubmitField('เริ่มการกู้คืนข้อมูล (ข้อมูลเก่าจะถูกลบทั้งหมด!)')