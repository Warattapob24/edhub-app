# app/models.py (ฉบับสมบูรณ์)
from datetime import datetime
from werkzeug.security import generate_password_hash, check_password_hash
from flask_login import UserMixin
from app import db

# --- ตารางเชื่อมความสัมพันธ์ (Association Tables) ---
enrollments = db.Table('enrollments',
    db.Column('student_id', db.Integer, db.ForeignKey('student.id'), primary_key=True),
    db.Column('course_id', db.Integer, db.ForeignKey('course.id'), primary_key=True)
)

class_group_advisors = db.Table('class_group_advisors',
    db.Column('user_id', db.Integer, db.ForeignKey('user.id'), primary_key=True),
    db.Column('class_group_id', db.Integer, db.ForeignKey('class_group.id'), primary_key=True)
)

course_class_groups = db.Table('course_class_groups',
    db.Column('course_id', db.Integer, db.ForeignKey('course.id'), primary_key=True),
    db.Column('class_group_id', db.Integer, db.ForeignKey('class_group.id'), primary_key=True)
)

user_roles = db.Table('user_roles',
    db.Column('user_id', db.Integer, db.ForeignKey('user.id'), primary_key=True),
    db.Column('role_id', db.Integer, db.ForeignKey('role.id'), primary_key=True)
)

timetable_block_grade_levels = db.Table('timetable_block_grade_levels',
    db.Column('block_id', db.Integer, db.ForeignKey('timetable_block.id'), primary_key=True),
    db.Column('grade_level_id', db.Integer, db.ForeignKey('grade_level.id'), primary_key=True)
)

timetable_block_roles = db.Table('timetable_block_roles',
    db.Column('block_id', db.Integer, db.ForeignKey('timetable_block.id'), primary_key=True),
    db.Column('role_id', db.Integer, db.ForeignKey('role.id'), primary_key=True)
)

# --- โมเดลหลัก ---
class Role(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    key = db.Column(db.String(64), unique=True, index=True)
    label = db.Column(db.String(128))

class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(64), index=True, unique=True)
    password_hash = db.Column(db.String(256))
    full_name = db.Column(db.String(120))
    status = db.Column(db.String(50), default='Active')
    department = db.Column(db.String(120), index=True)
    max_periods_per_day = db.Column(db.Integer)
    max_periods_per_week = db.Column(db.Integer)
    roles = db.relationship('Role', secondary=user_roles, lazy='subquery',
                            backref=db.backref('users', lazy=True))
    activity_logs = db.relationship('ActivityLog', backref='user', lazy='dynamic')
    courses_taught = db.relationship('Course', backref='teacher', lazy='dynamic')
    advised_class_groups = db.relationship('ClassGroup', secondary=class_group_advisors, back_populates='advisors')
    def set_password(self, password): self.password_hash = generate_password_hash(password)
    def check_password(self, password): return check_password_hash(self.password_hash, password)

class GradeLevel(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(50), unique=True, nullable=False)
    class_groups = db.relationship('ClassGroup', backref='grade_level', lazy='dynamic')

class ClassGroup(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    room_number = db.Column(db.String(10), nullable=False)
    academic_year = db.Column(db.Integer, index=True, nullable=False)
    grade_level_id = db.Column(db.Integer, db.ForeignKey('grade_level.id'))
    students = db.relationship('Student', backref='class_group', lazy='dynamic')
    advisors = db.relationship('User', secondary=class_group_advisors, back_populates='advised_class_groups')
    courses = db.relationship('Course', secondary=course_class_groups, back_populates='class_groups')

class Room(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), unique=True, nullable=False)
    room_type = db.Column(db.String(50), default='ห้องเรียนปกติ', index=True)
    courses = db.relationship('Course', back_populates='room')
    def __repr__(self):
        return f'<Room {self.name}>'
    
class Student(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    student_id = db.Column(db.String(20), unique=True, index=True)
    password_hash = db.Column(db.String(256))
    prefix = db.Column(db.String(20))
    first_name = db.Column(db.String(64))
    last_name = db.Column(db.String(64))
    class_number = db.Column(db.Integer)
    status = db.Column(db.String(50), default='กำลังศึกษา')
    class_group_id = db.Column(db.Integer, db.ForeignKey('class_group.id'))
    scores = db.relationship('Score', backref='student', lazy='dynamic')
    courses = db.relationship('Course', secondary=enrollments, lazy='subquery', backref=db.backref('students', lazy=True))
    attendance_records = db.relationship('AttendanceRecord', backref='student', lazy='dynamic')
    def set_password(self, password): self.password_hash = generate_password_hash(password)
    def check_password(self, password): return check_password_hash(self.password_hash, password)

class Subject(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    subject_code = db.Column(db.String(20), unique=True, index=True)
    name = db.Column(db.String(120))
    department = db.Column(db.String(120))
    default_credits = db.Column(db.Float, default=1.0)
    subject_type = db.Column(db.String(50)) # เช่น 'คำนวณ', 'บรรยาย', 'ปฏิบัติ', 'กิจกรรม'
    time_preference = db.Column(db.String(50)) # เช่น 'ตอนเช้า', 'ตอนบ่าย', 'ไม่มี'
    required_room_type = db.Column(db.String(50), nullable=True) # เช่น 'ห้องแล็บ', 'ห้องคอมพิวเตอร์'
    courses = db.relationship('Course', back_populates='subject', lazy='dynamic')
    curriculum_entries = db.relationship('Curriculum', back_populates='subject', lazy='dynamic')
    learning_units = db.relationship('LearningUnit', backref='subject', lazy='dynamic', cascade="all, delete-orphan")
    exams = db.relationship('Exam', backref='subject', lazy='dynamic', cascade="all, delete-orphan")

class Course(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    academic_year = db.Column(db.Integer, index=True)
    semester = db.Column(db.Integer, index=True)

    # เพิ่มความสัมพันธ์แบบ One-to-One / Many-to-One
    subject_id = db.Column(db.Integer, db.ForeignKey('subject.id'), nullable=False)
    teacher_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    class_group_id = db.Column(db.Integer, db.ForeignKey('class_group.id'), nullable=True)
    room_id = db.Column(db.Integer, db.ForeignKey('room.id'), nullable=True)
    assignment_id = db.Column(db.Integer, db.ForeignKey('course_assignment.id'), nullable=True) # nullable=True เผื่อกรณีสร้าง Course โดยตรง

    # สร้าง relationship กลับไปหา object
    timetable_slots = db.relationship('TimetableSlot', back_populates='course', lazy='dynamic', cascade="all, delete-orphan")
    subject = db.relationship('Subject', back_populates='courses')
    # teacher = db.relationship('User', backref='courses_taught') 
    class_groups = db.relationship('ClassGroup', secondary=course_class_groups, back_populates='courses')
    room = db.relationship('Room', back_populates='courses')

    coursework_ratio = db.Column(db.Integer, default=70)
    final_exam_ratio = db.Column(db.Integer, default=30)
    status = db.Column(db.String(50), default='draft', index=True) 

    approval_logs = db.relationship('ApprovalLog', backref='course', lazy='dynamic')    
    components = db.relationship('CourseComponent', backref='course', lazy='dynamic', cascade="all, delete-orphan")
    attendance_records = db.relationship('AttendanceRecord', backref='course', lazy='dynamic')
    scheduling_rules = db.relationship('SchedulingRule', back_populates='course', lazy='dynamic', cascade="all, delete-orphan")

class CourseComponent(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120))
    indicator = db.Column(db.Text)
    component_type = db.Column(db.String(50))
    max_score_k = db.Column(db.Integer, default=0)
    max_score_p = db.Column(db.Integer, default=0)
    max_score_a = db.Column(db.Integer, default=0)
    exam_type = db.Column(db.String(20), nullable=True) # e.g., 'midterm', 'final'
    total_max_score = db.Column(db.Integer)
    course_id = db.Column(db.Integer, db.ForeignKey('course.id'))
    display_order = db.Column(db.Integer)
    scores = db.relationship('Score', backref='component', lazy='dynamic')

class Score(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    points_k = db.Column(db.Float)
    points_p = db.Column(db.Float)
    points_a = db.Column(db.Float)
    total_points = db.Column(db.Float)
    status = db.Column(db.String(20), default='Graded')
    remedial_score = db.Column(db.Float)
    exam_points = db.Column(db.Float)
    student_id = db.Column(db.Integer, db.ForeignKey('student.id'))
    component_id = db.Column(db.Integer, db.ForeignKey('course_component.id'))

class AttendanceRecord(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    date = db.Column(db.Date, nullable=False, index=True)
    status = db.Column(db.String(20), nullable=False)
    student_id = db.Column(db.Integer, db.ForeignKey('student.id'))
    course_id = db.Column(db.Integer, db.ForeignKey('course.id'))

class EvaluationTopic(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    assessment_type = db.Column(db.String(100), index=True)
    name = db.Column(db.String(255))
    display_order = db.Column(db.Integer)
    parent_id = db.Column(db.Integer, db.ForeignKey('evaluation_topic.id'))
    sub_topics = db.relationship('EvaluationTopic', backref=db.backref('parent', remote_side=[id]))

class AdditionalAssessment(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    result = db.Column(db.String(50))
    student_id = db.Column(db.Integer, db.ForeignKey('student.id'))
    course_id = db.Column(db.Integer, db.ForeignKey('course.id'))
    topic_id = db.Column(db.Integer, db.ForeignKey('evaluation_topic.id'))
    
class Setting(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    key = db.Column(db.String(64), unique=True, index=True)
    value = db.Column(db.Text)
    
class ActivityLog(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    timestamp = db.Column(db.DateTime, index=True, default=datetime.utcnow)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'))
    action = db.Column(db.String(120))
    details = db.Column(db.String(256))

class FinalEvaluation(db.Model):
    """โมเดลสำหรับเก็บผลการประเมินสรุปโดยครูที่ปรึกษา"""
    id = db.Column(db.Integer, primary_key=True)
    academic_year = db.Column(db.Integer, index=True)
    semester = db.Column(db.Integer, index=True)
    result = db.Column(db.String(50))
    student_id = db.Column(db.Integer, db.ForeignKey('student.id'))
    topic_id = db.Column(db.Integer, db.ForeignKey('evaluation_topic.id'))
    # ครูที่ปรึกษาที่ทำการประเมิน
    advisor_id = db.Column(db.Integer, db.ForeignKey('user.id'))

class ApprovalLog(db.Model):
    """ตารางสำหรับติดตามทุกขั้นตอนการอนุมัติ"""
    id = db.Column(db.Integer, primary_key=True)
    timestamp = db.Column(db.DateTime, index=True, default=datetime.utcnow)
    status = db.Column(db.String(50)) # e.g., 'Submitted', 'Approved', 'Rejected'
    comments = db.Column(db.Text) # สำหรับเหตุผลในการตีกลับ
    
    course_id = db.Column(db.Integer, db.ForeignKey('course.id'))
    user_id = db.Column(db.Integer, db.ForeignKey('user.id')) # ผู้ที่กระทำ
    
    # ลำดับขั้นการอนุมัติ (1=ครูส่ง, 2=วัดผลสาระอนุมัติ, ...)
    step = db.Column(db.Integer)

class TimetableBlock(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    days_of_week = db.Column(db.JSON, nullable=False) # เช่น [0, 2, 4] for Mon, Wed, Fri
    start_time = db.Column(db.Time, nullable=False)
    end_time = db.Column(db.Time, nullable=False)
    academic_year = db.Column(db.Integer, index=True, nullable=False)

    applies_to_grade_levels = db.relationship(
        'GradeLevel', secondary=timetable_block_grade_levels,
        lazy='subquery', backref=db.backref('time_blocks_grade', lazy=True)
    )

    applies_to_roles = db.relationship(
        'Role', secondary=timetable_block_roles,
        lazy='subquery', backref=db.backref('time_blocks_role', lazy=True)
    )

    def __repr__(self):
        # แก้ไข repr ให้แสดงข้อมูลที่เป็นประโยชน์มากขึ้น
        return f'<TimetableBlock "{self.name}" Year {self.academic_year}>'
        
class SchoolPeriod(db.Model):
    """
    โมเดลสำหรับเก็บโครงสร้างคาบเรียนมาตรฐานของโรงเรียน
    เช่น คาบ 1, คาบพัก, คาบ 2
    """
    id = db.Column(db.Integer, primary_key=True)
    period_number = db.Column(db.Integer, nullable=False, index=True) # ลำดับของคาบ เช่น 1, 2, 3
    name = db.Column(db.String(50), nullable=False) # ชื่อเรียก เช่น 'คาบเรียน', 'คาบพัก', 'พักกลางวัน'
    start_time = db.Column(db.Time, nullable=False)
    end_time = db.Column(db.Time, nullable=False)

    def __repr__(self):
        return f'<SchoolPeriod {self.period_number}: {self.name}>'
    
class SchedulingRule(db.Model):
    """
    โมเดลสำหรับเก็บกฎ/คำขอพรในการจัดตารางสอนสำหรับแต่ละคลาสเรียน
    """
    id = db.Column(db.Integer, primary_key=True)
    rule_type = db.Column(db.String(50), nullable=False, index=True) 
    # เช่น 'group_together', 'spread_out', 'prefer_morning'
    
    value = db.Column(db.String(50)) # ค่าเพิ่มเติมสำหรับกฎ เช่น '2' สำหรับ group_together
    
    # ความสัมพันธ์: กฎนี้เป็นของคลาสเรียนไหน
    course_id = db.Column(db.Integer, db.ForeignKey('course.id'), nullable=False)
    course = db.relationship('Course', back_populates='scheduling_rules')

    def __repr__(self):
        return f'<SchedulingRule {self.rule_type} for Course {self.course_id}>'
    
class Curriculum(db.Model):
    """
    โมเดลสำหรับเก็บหลักสูตรแกนกลางของโรงเรียน
    ระบุว่าในแต่ละปี/เทอม แต่ละสายชั้นต้องเรียนวิชาอะไรบ้าง
    """
    id = db.Column(db.Integer, primary_key=True)
    academic_year = db.Column(db.Integer, nullable=False, index=True)
    semester = db.Column(db.Integer, nullable=False, index=True)
    
    # ความสัมพันธ์
    grade_level_id = db.Column(db.Integer, db.ForeignKey('grade_level.id'), nullable=False)
    subject_id = db.Column(db.Integer, db.ForeignKey('subject.id'), nullable=False)

    grade_level = db.relationship('GradeLevel', backref='curriculum_entries')
    subject = db.relationship('Subject', backref='subject_curriculum')

    def __repr__(self):
        return f'<Curriculum for Grade {self.grade_level_id} to learn Subject {self.subject_id}>'
    
class CourseAssignment(db.Model):
    """
    โมเดลสำหรับเก็บการมอบหมายภารกิจ
    ว่าวิชาในหลักสูตรถูกมอบหมายให้ครูคนใด
    """
    id = db.Column(db.Integer, primary_key=True)
    
    # ความสัมพันธ์
    curriculum_id = db.Column(db.Integer, db.ForeignKey('curriculum.id'), nullable=False)
    teacher_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    class_group_id = db.Column(db.Integer, db.ForeignKey('class_group.id'), nullable=True)

    curriculum = db.relationship('Curriculum', backref='assignments')
    teacher = db.relationship('User', backref='course_assignments')
    class_group = db.relationship('ClassGroup', backref='course_assignments')
    
    # สร้าง UniqueConstraint เพื่อป้องกันการมอบหมายซ้ำซ้อน
    __table_args__ = (db.UniqueConstraint('curriculum_id', 'class_group_id', name='_curriculum_class_group_uc'),)

    def __repr__(self):
        return f'<Assignment of Curriculum {self.curriculum_id} to Teacher {self.teacher_id} in Class Group {self.class_group_id}>'
    
class TimetableSlot(db.Model):
    __tablename__ = 'timetable_slot'

    id = db.Column(db.Integer, primary_key=True)
    block_id = db.Column(db.Integer, db.ForeignKey('timetable_block.id'), nullable=False)
    period_id = db.Column(db.Integer, db.ForeignKey('school_period.id'), nullable=False)
    day_of_week = db.Column(db.Integer, nullable=False)  # 0=Monday, 6=Sunday
    room_id = db.Column(db.Integer, db.ForeignKey('room.id'))
    course_id = db.Column(db.Integer, db.ForeignKey('course.id'), nullable=False)
    class_group_id = db.Column(db.Integer, db.ForeignKey('class_group.id'), nullable=True)
    start_time = db.Column(db.Time, nullable=False)
    end_time = db.Column(db.Time, nullable=False)

    # Relationships
    course = db.relationship('Course', back_populates='timetable_slots')
    block = db.relationship('TimetableBlock', backref=db.backref('slots', lazy='dynamic'))
    period = db.relationship('SchoolPeriod', backref=db.backref('slots', lazy='dynamic'))
    room = db.relationship('Room', backref=db.backref('slots', lazy='dynamic'))

    def __repr__(self):
        return f'<TimetableSlot {self.id} - Day {self.day_of_week}>'

class LearningUnit(db.Model):
    __tablename__ = 'learning_unit' # แนะนำให้กำหนดชื่อตารางให้ชัดเจน
    id = db.Column(db.Integer, primary_key=True)
    order = db.Column(db.Integer)
    title = db.Column(db.String(200))
    standards = db.Column(db.Text)
    topics = db.Column(db.Text)
    hours = db.Column(db.Integer)
    k_score = db.Column(db.Integer)
    p_score = db.Column(db.Integer)
    a_score = db.Column(db.Integer)
    
    # Foreign Key เพื่อเชื่อมกับ Subject
    subject_id = db.Column(db.Integer, db.ForeignKey('subject.id'), nullable=False)
    # เราจะเพิ่ม relationship ใน Subject แทน

class Exam(db.Model):
    __tablename__ = 'exam' # แนะนำให้กำหนดชื่อตารางให้ชัดเจน
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100))
    score = db.Column(db.Integer)
    hours = db.Column(db.Integer)
    
    # Foreign Key เพื่อเชื่อมกับ Subject
    subject_id = db.Column(db.Integer, db.ForeignKey('subject.id'), nullable=False)
    # เราจะเพิ่ม relationship ใน Subject แทน