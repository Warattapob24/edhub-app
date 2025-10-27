# path: app/models.py

from datetime import datetime
from app import db, login_manager
from werkzeug.security import generate_password_hash, check_password_hash
from flask_login import UserMixin

# ==============================================================================
# == 1. ASSOCIATION TABLES (ตารางเชื่อม)
# ==============================================================================
# --- ย้ายตารางเชื่อมทั้งหมดมาไว้ข้างบนสุด ---

# Association table for User and Role (Many-to-Many)
user_roles = db.Table('user_roles',
    db.Column('user_id', db.Integer, db.ForeignKey('user.id'), primary_key=True),
    db.Column('role_id', db.Integer, db.ForeignKey('role.id'), primary_key=True)
)

# ตารางเชื่อมโยงระหว่าง CourseSection และ User (นักเรียน)
section_enrollments = db.Table('section_enrollments',
    db.Column('user_id', db.Integer, db.ForeignKey('user.id'), primary_key=True),
    db.Column('section_id', db.Integer, db.ForeignKey('course_section.id'), primary_key=True)
)

# ตารางเชื่อมโยงระหว่าง ห้องเรียน และ ครูที่ปรึกษา (Many-to-Many)
classroom_advisors = db.Table('classroom_advisors',
    db.Column('classroom_id', db.Integer, db.ForeignKey('classroom.id'), primary_key=True),
    db.Column('user_id', db.Integer, db.ForeignKey('user.id'), primary_key=True)
)

# ตารางเชื่อมโยงระหว่าง CourseSection และ Teachers (Many-to-Many)
section_teachers = db.Table('section_teachers',
    db.Column('section_id', db.Integer, db.ForeignKey('course_section.id'), primary_key=True),
    db.Column('user_id', db.Integer, db.ForeignKey('user.id'), primary_key=True)
)

# ตารางเชื่อมโยงระหว่าง CourseSection และ Classrooms (Many-to-Many)
section_classrooms = db.Table('section_classrooms',
    db.Column('section_id', db.Integer, db.ForeignKey('course_section.id'), primary_key=True),
    db.Column('classroom_id', db.Integer, db.ForeignKey('classroom.id'), primary_key=True)
)

# ตารางเชื่อมสำหรับ LearningUnit และ SubItems
unit_competency_sub_items = db.Table('unit_competency_sub_items',
    db.Column('learning_unit_id', db.Integer, db.ForeignKey('learning_unit.id'), primary_key=True),
    db.Column('sub_item_id', db.Integer, db.ForeignKey('competency_sub_item.id'), primary_key=True)
)

unit_characteristic_sub_items = db.Table('unit_characteristic_sub_items',
    db.Column('learning_unit_id', db.Integer, db.ForeignKey('learning_unit.id'), primary_key=True),
    db.Column('sub_item_id', db.Integer, db.ForeignKey('characteristic_sub_item.id'), primary_key=True)
)

unit_assessment_methods_sub_items = db.Table('unit_assessment_methods_sub_items',
    db.Column('learning_unit_id', db.Integer, db.ForeignKey('learning_unit.id'), primary_key=True),
    db.Column('sub_item_id', db.Integer, db.ForeignKey('method_sub_item.id'), primary_key=True)
)

unit_competencies = db.Table('unit_competencies',
    db.Column('learning_unit_id', db.Integer, db.ForeignKey('learning_unit.id'), primary_key=True),
    db.Column('competency_id', db.Integer, db.ForeignKey('competency.id'), primary_key=True)
)

unit_characteristics = db.Table('unit_characteristics',
    db.Column('learning_unit_id', db.Integer, db.ForeignKey('learning_unit.id'), primary_key=True),
    db.Column('characteristic_id', db.Integer, db.ForeignKey('desirable_characteristic.id'), primary_key=True)
)

unit_assessment_methods = db.Table('unit_assessment_methods',
    db.Column('learning_unit_id', db.Integer, db.ForeignKey('learning_unit.id'), primary_key=True),
    db.Column('method_id', db.Integer, db.ForeignKey('assessment_method.id'), primary_key=True)
)


# ==============================================================================
# == 2. MODEL CLASSES
# ==============================================================================

class Competency(db.Model):
    __tablename__ = 'competency'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(255), unique=True, nullable=False)
    sub_items = db.relationship('CompetencySubItem', backref='parent', lazy='dynamic', cascade="all, delete-orphan")
    indicators = db.Column(db.JSON, default=list)
    created_at = db.Column(db.DateTime, default=datetime.now)

    learning_units = db.relationship(
        'LearningUnit',
        secondary=unit_competencies,
        back_populates='competencies'
    )    

class CompetencySubItem(db.Model):
    __tablename__ = 'competency_sub_item'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(255), nullable=False)
    parent_id = db.Column(db.Integer, db.ForeignKey('competency.id'), nullable=False)
    learning_units = db.relationship(
        'LearningUnit',
        secondary=unit_competency_sub_items,
        back_populates='competency_sub_items'   # ✅ ตรงกับ LearningUnit.competency_sub_items
    )

class DesirableCharacteristic(db.Model):
    __tablename__ = 'desirable_characteristic'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False, unique=True)
    indicators = db.Column(db.JSON, default=list)
    created_at = db.Column(db.DateTime, default=datetime.now)
    sub_items = db.relationship('CharacteristicSubItem', backref='parent', lazy='dynamic', cascade="all, delete-orphan")

    learning_units = db.relationship(
        'LearningUnit',
        secondary=unit_characteristics,
        back_populates='desirable_characteristics'
    )

class CharacteristicSubItem(db.Model):
    __tablename__ = 'characteristic_sub_item'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(255), nullable=False)
    parent_id = db.Column(db.Integer, db.ForeignKey('desirable_characteristic.id'), nullable=False)
    learning_units = db.relationship(
        'LearningUnit',
        secondary=unit_characteristic_sub_items,
        back_populates='characteristic_sub_items'
    )

class AssessmentMethod(db.Model):
    __tablename__ = 'assessment_method'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(255), unique=True, nullable=False)
    description = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.now)
    sub_items = db.relationship('MethodSubItem', backref='parent', lazy='dynamic', cascade="all, delete-orphan")

    learning_units = db.relationship(
        'LearningUnit',
        secondary=unit_assessment_methods,
        back_populates='assessment_methods'
    )
    
class MethodSubItem(db.Model):
    __tablename__ = 'method_sub_item'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(255), nullable=False)
    parent_id = db.Column(db.Integer, db.ForeignKey('assessment_method.id'), nullable=False)
    learning_units = db.relationship('LearningUnit', secondary=unit_assessment_methods_sub_items,
                                     back_populates='method_sub_items')



class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(64), index=True, unique=True, nullable=False)
    full_name = db.Column(db.String(120), nullable=False)
    password_hash = db.Column(db.String(256))
    active = db.Column(db.Boolean, default=True)
    learning_area_id = db.Column(db.Integer, db.ForeignKey('learning_area.id'), nullable=True)
    learning_area = db.relationship('LearningArea', foreign_keys=[learning_area_id], backref='teachers')
    roles = db.relationship('Role', secondary='user_roles', backref=db.backref('users', lazy='dynamic'))

    # [เพิ่มใหม่] ความสัมพันธ์สำหรับนักเรียนที่ลงทะเบียนใน CourseSection
    enrolled_sections = db.relationship('CourseSection', secondary=section_enrollments, lazy='subquery',
                                        backref=db.backref('students', lazy=True))

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

    def has_role(self, role_name):
        return any(role.name == role_name for role in self.roles)
    
    def is_active(self):
        return self.active

class Role(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(64), unique=True, nullable=False)

    def __repr__(self):
        return f'<Role {self.name}>'

class AcademicYear(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    year = db.Column(db.Integer, nullable=False) # เช่น 2568
    semester = db.Column(db.Integer, nullable=False) # เช่น 1, 2
    is_active = db.Column(db.Boolean, default=False, nullable=False)

    def __repr__(self):
        return f'ปีการศึกษา {self.year}/{self.semester}'

class GradeLevel(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), unique=True, nullable=False) # เช่น "มัธยมศึกษาปีที่ 1"
    classrooms = db.relationship('Classroom', backref='grade_level', lazy='dynamic')
    courses = db.relationship('Course', backref='grade_level', lazy='dynamic')

    def __repr__(self):
        return self.name

class Classroom(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False) # เช่น "ห้อง 1/1"
    grade_level_id = db.Column(db.Integer, db.ForeignKey('grade_level.id'), nullable=False)
    
    # ความสัมพันธ์กับครูที่ปรึกษา
    advisors = db.relationship('User', secondary=classroom_advisors, lazy='subquery',
                               backref=db.backref('advised_classrooms', lazy=True))

    def __repr__(self):
        return f'{self.grade_level.name} - {self.name}'
    
class HomeroomEnrollment(db.Model):
    __tablename__ = 'homeroom_enrollment'
    id = db.Column(db.Integer, primary_key=True)
    student_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    classroom_id = db.Column(db.Integer, db.ForeignKey('classroom.id'), nullable=False)
    academic_year_id = db.Column(db.Integer, db.ForeignKey('academic_year.id'), nullable=False)

    student = db.relationship('User', backref=db.backref('homeroom_enrollments', lazy='dynamic'))
    classroom = db.relationship('Classroom', backref=db.backref('homeroom_enrollments', lazy='dynamic'))
    academic_year = db.relationship('AcademicYear', backref=db.backref('homeroom_enrollments', lazy='dynamic'))

    def __repr__(self):
        return f'<Homeroom: {self.student.full_name} in {self.classroom.name} for {self.academic_year.year}>'

class LearningArea(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(150), unique=True, nullable=False) # เช่น "วิทยาศาสตร์และเทคโนโลยี"
    courses = db.relationship('Course', backref='learning_area', lazy='dynamic')

    head_id = db.Column(db.Integer, db.ForeignKey('user.id', use_alter=True, name='fk_learning_area_head_id'))
    head = db.relationship('User', backref='headed_area', foreign_keys=[head_id])
    
    def __repr__(self):
        return self.name

class Course(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    course_code = db.Column(db.String(20), unique=True, nullable=False)
    name_thai = db.Column(db.String(200), nullable=False)
    credits = db.Column(db.Float, nullable=False)

    # --- Fields ที่เพิ่มเข้ามา ---
    semester = db.Column(db.Integer, nullable=False) # ภาคเรียนที่เปิดสอนตามหลักสูตร (1, 2, or 0 for both)

    # ความสัมพันธ์กับกลุ่มสาระฯ (One-to-Many)
    learning_area_id = db.Column(db.Integer, db.ForeignKey('learning_area.id'), nullable=False)

    # ความสัมพันธ์กับระดับชั้น (One-to-Many)
    grade_level_id = db.Column(db.Integer, db.ForeignKey('grade_level.id'), nullable=False)
    periods_per_week = db.Column(db.Integer)
    
    def __repr__(self):
        # แสดงข้อมูลให้ครบถ้วนมากขึ้น
        grade_level = GradeLevel.query.get(self.grade_level_id)
        return f'{self.course_code} {self.name_thai} ({grade_level.name})'
    
class CourseSection(db.Model):
    __tablename__ = 'course_section'
    id = db.Column(db.Integer, primary_key=True)

    # เชื่อมโยงกับข้อมูลหลัก
    academic_year_id = db.Column(db.Integer, db.ForeignKey('academic_year.id'), nullable=False)
    course_id = db.Column(db.Integer, db.ForeignKey('course.id'), nullable=False)

    # ความสัมพันธ์
    academic_year = db.relationship('AcademicYear')
    course = db.relationship('Course')

    # ครูผู้สอน (รองรับหลายคน)
    teachers = db.relationship('User',
                               secondary=section_teachers,
                               lazy='subquery',
                               backref=db.backref('assigned_sections', lazy=True))

    teacher_assignments = db.relationship('TeacherAssignment', 
                                          backref='course_section', 
                                          lazy='dynamic', 
                                          cascade="all, delete-orphan")

    # [แก้ไข] ความสัมพันธ์ students ถูกย้ายไปที่ Model User ผ่าน backref แล้ว
    # students = db.relationship('User', secondary=section_enrollments, lazy='subquery',
    #                            backref=db.backref('enrolled_sections', lazy=True))

    # ห้องเรียนที่สอน (รองรับหลายห้อง)
    classrooms = db.relationship('Classroom', secondary=section_classrooms, lazy='subquery',
                                 backref=db.backref('course_sections', lazy=True))
    
    periods_per_week = db.Column(db.Integer, default=2) # เช่น 2 คาบ/สัปดาห์
    prefer_consecutive = db.Column(db.Boolean, default=True) # ชอบสอนคาบติดกันหรือไม่
    prefer_time = db.Column(db.String(20)) # เช่น 'morning', 'afternoon', 'any'

    main_physical_room_id = db.Column(db.Integer, db.ForeignKey('physical_room.id'))
    main_physical_room = db.relationship('PhysicalRoom')    

    learning_units = db.relationship('LearningUnit', back_populates='course_section', lazy='dynamic', cascade="all, delete-orphan")

    def __repr__(self):
        return f'Section: {self.course.course_code} ({self.academic_year})'
    
class LearningUnit(db.Model):
    __tablename__ = 'learning_unit'
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(255), nullable=False)
    description = db.Column(db.Text)
    start_period = db.Column(db.Integer)
    end_period = db.Column(db.Integer)
    learning_standard = db.Column(db.Text)
    indicators = db.Column(db.Text)
    learning_objectives = db.Column(db.Text)
    core_concepts = db.Column(db.Text)
    learning_content = db.Column(db.Text)
    activities = db.Column(db.Text)
    media_sources = db.Column(db.Text)
    
    # --- CORRECTED RELATIONSHIPS START HERE ---
    competencies = db.relationship(
        'Competency',
        secondary=unit_competencies,
        back_populates='learning_units'
    )
    desirable_characteristics = db.relationship(
        'DesirableCharacteristic',
        secondary=unit_characteristics,
        back_populates='learning_units'
    )
    assessment_methods = db.relationship(
        'AssessmentMethod',
        secondary=unit_assessment_methods,
        back_populates='learning_units'
    )

    # ความสัมพันธ์กับ SubItem (คุณมีแล้ว เก็บไว้ก็ได้ ถ้าใช้จริง)
    competency_sub_items = db.relationship('CompetencySubItem', secondary=unit_competency_sub_items, lazy='subquery',
                                           back_populates='learning_units')
    characteristic_sub_items = db.relationship('CharacteristicSubItem', secondary=unit_characteristic_sub_items, lazy='subquery',
                                               back_populates='learning_units')
    method_sub_items = db.relationship('MethodSubItem', secondary=unit_assessment_methods_sub_items, lazy='subquery',
                                       back_populates='learning_units')

    course_section_id = db.Column(db.Integer, db.ForeignKey('course_section.id'), nullable=False)
    course_section = db.relationship('CourseSection', back_populates='learning_units')
    # --- CORRECTED RELATIONSHIPS END HERE ---

# [ใหม่] Model สำหรับเก็บ "คลังมิติการประเมิน"
class AssessmentDimension(db.Model):
    __tablename__ = 'assessment_dimension'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), unique=True, nullable=False) # เช่น "Knowledge", "ทักษะการปฏิบัติ"
    code = db.Column(db.String(10), unique=True, nullable=False) # รหัสย่อ เช่น "K", "S"
    description = db.Column(db.Text) # คำอธิบายความหมายของมิตินี้
    
    def __repr__(self):
        return f'<Dimension: {self.name}>'

class ToolCriterion(db.Model):
    """โมเดลสำหรับเก็บ 'เกณฑ์' ย่อยๆ ในเครื่องมือ"""
    id = db.Column(db.Integer, primary_key=True)
    description = db.Column(db.String(500), nullable=False) # เช่น "ความถูกต้องของเนื้อหา", "ความคล่องแคล่วในการนำเสนอ"
    max_score = db.Column(db.Float, nullable=False, default=5) # คะแนนเต็มของเกณฑ์นี้
    tool_id = db.Column(db.Integer, db.ForeignKey('assessment_tool.id'), nullable=False)

class GradeComponent(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(255), nullable=False) # ชื่องาน เช่น "โครงงานวิทยาศาสตร์"
    total_max_score = db.Column(db.Float, nullable=False) # คะแนนเต็มของงานชิ้นนี้

    # เชื่อมกลับไปยังหน่วยการเรียนรู้
    learning_unit_id = db.Column(db.Integer, db.ForeignKey('learning_unit.id'), nullable=False)
    learning_unit = db.relationship('LearningUnit', backref=db.backref('grade_components', lazy='dynamic', cascade="all, delete-orphan"))

    # เชื่อมกลับไปยังมิติการประเมิน
    assessment_aspects = db.relationship('AssessmentAspect', backref='grade_component', lazy='dynamic', cascade="all, delete-orphan")

    # [เพิ่มใหม่] กลไกพิเศษสำหรับการวัดผล
    is_midway_indicator = db.Column(db.Boolean, default=False, nullable=False) # ตัวชี้วัดระหว่างทาง
    is_critical_indicator = db.Column(db.Boolean, default=False, nullable=False) # ตัวชี้วัดปลายทาง (ขาดส่งติด 'ร')
    is_midterm_exam = db.Column(db.Boolean, default=False, nullable=False) # สอบกลางภาค
    is_final_exam = db.Column(db.Boolean, default=False, nullable=False) # สอบปลายภาค
    assessment_tool_id = db.Column(db.Integer, db.ForeignKey('assessment_tool.id'), nullable=True)
    assessment_tool = db.relationship('AssessmentTool', backref='grade_components')

class AssessmentAspect(db.Model):
    __tablename__ = 'assessment_aspect'
    id = db.Column(db.Integer, primary_key=True)
    description = db.Column(db.String(255), nullable=False) # สิ่งที่วัดในช่องนี้ เช่น "ความเข้าใจเรื่องหลักการ"
    max_score = db.Column(db.Float, nullable=False) # คะแนนเต็มของช่องนี้

    grade_component_id = db.Column(db.Integer, db.ForeignKey('grade_component.id'), nullable=False)

    # [ปรับปรุง] เปลี่ยนมาอ้างอิงกับ "คลังมิติการประเมิน"
    dimension_id = db.Column(db.Integer, db.ForeignKey('assessment_dimension.id'), nullable=False)
    dimension = db.relationship('AssessmentDimension')

class StudentGrade(db.Model):
    __tablename__ = 'student_grade'
    id = db.Column(db.Integer, primary_key=True)
    score = db.Column(db.Float)
    
    student_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    assessment_aspect_id = db.Column(db.Integer, db.ForeignKey('assessment_aspect.id'), nullable=False)

    # ความสัมพันธ์
    student = db.relationship('User', backref=db.backref('grades', lazy='dynamic'))
    assessment_aspect = db.relationship('AssessmentAspect', backref=db.backref('grades', lazy='dynamic'))

    def __repr__(self):
        return f'<Grade {self.student.username} gets {self.score}>'

class PhysicalRoom(db.Model):
    __tablename__ = 'physical_room'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), unique=True, nullable=False) # เช่น "123", "LAB-SCI-1"
    description = db.Column(db.String(255)) # เช่น "ห้องเรียนชั้น 2 อาคาร 1", "ห้องปฏิบัติการวิทยาศาสตร์ 1"
    capacity = db.Column(db.Integer)

    def __repr__(self):
        return self.name

class TeacherAssignment(db.Model):
    __tablename__ = 'teacher_assignment'
    id = db.Column(db.Integer, primary_key=True)
    
    # Foreign Keys ที่เชื่อมโยงข้อมูลสำคัญ
    course_section_id = db.Column(db.Integer, db.ForeignKey('course_section.id'), nullable=False)
    teacher_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    classroom_id = db.Column(db.Integer, db.ForeignKey('classroom.id'), nullable=False)

    # Relationships เพื่อให้เรียกใช้งานได้ง่าย
    teacher = db.relationship('User')
    classroom = db.relationship('Classroom')

    def __repr__(self):
        return f'<Assignment: {self.teacher.full_name} teaches {self.classroom.name}>'
    
class AssessmentTool(db.Model):
    """
    โมเดลหลักสำหรับเก็บ 'แม่แบบ' ของเครื่องมือวัดผลแต่ละชนิด
    เช่น Rubric การนำเสนอ, Checklist สังเกตพฤติกรรม
    """
    __tablename__ = 'assessment_tool'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(200), nullable=False)
    tool_type = db.Column(db.String(50), nullable=False) # 'rubric', 'checklist', 'rating_scale'
    creator_id = db.Column(db.Integer, db.ForeignKey('user.id'))
    
    criteria = db.relationship('ToolCriterion', backref='tool', lazy='dynamic', cascade="all, delete-orphan")

class RubricCriterion(db.Model):
    """โมเดลสำหรับเก็บ 'เกณฑ์' ย่อยๆ ใน Rubric หนึ่งๆ"""
    __tablename__ = 'rubric_criterion'
    id = db.Column(db.Integer, primary_key=True)
    description = db.Column(db.String(500), nullable=False) # เช่น "การนำเสนอเนื้อหา"
    tool_id = db.Column(db.Integer, db.ForeignKey('assessment_tool.id'), nullable=False)
    # อาจเพิ่มคอลัมน์สำหรับเก็บ level descriptions ได้ในอนาคต

class ChecklistItem(db.Model):
    """โมเดลสำหรับเก็บ 'รายการ' ย่อยๆ ใน Checklist หนึ่งๆ"""
    __tablename__ = 'checklist_item'
    id = db.Column(db.Integer, primary_key=True)
    description = db.Column(db.String(500), nullable=False) # เช่น "มีการทำงานร่วมกับเพื่อน"
    tool_id = db.Column(db.Integer, db.ForeignKey('assessment_tool.id'), nullable=False)

class ReadingAnalysisWriting(db.Model):
    __tablename__ = 'reading_analysis_writing'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False, unique=True)
    sub_categories = db.Column(db.JSON, default=dict)
    created_at = db.Column(db.DateTime, default=datetime.now)

class Enrollment(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    student_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    classroom_id = db.Column(db.Integer, db.ForeignKey('classroom.id'), nullable=False)
    academic_year_id = db.Column(db.Integer, db.ForeignKey('academic_year.id'), nullable=False)

    student = db.relationship('User')
    classroom = db.relationship('Classroom')
    academic_year = db.relationship('AcademicYear')

# ADD THIS FUNCTION
@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))