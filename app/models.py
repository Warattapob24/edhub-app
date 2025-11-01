# FILE: app/models.py
from datetime import datetime
from app import login
from app import db
from werkzeug.security import generate_password_hash, check_password_hash
from flask_login import UserMixin
from sqlalchemy import UniqueConstraint, event
from datetime import datetime
from sqlalchemy import func

# --- Association tables ---
user_roles = db.Table('user_roles',
    db.Column('user_id', db.Integer, db.ForeignKey('user.id'), primary_key=True),
    db.Column('role_id', db.Integer, db.ForeignKey('role.id'), primary_key=True)
)
subject_grade_levels = db.Table('subject_grade_levels',
    db.Column('subject_id', db.Integer, db.ForeignKey('subject.id'), primary_key=True),
    db.Column('grade_level_id', db.Integer, db.ForeignKey('grade_level.id'), primary_key=True)
)
subject_group_members = db.Table('subject_group_members',
    db.Column('user_id', db.Integer, db.ForeignKey('user.id'), primary_key=True),
    db.Column('subject_group_id', db.Integer, db.ForeignKey('subject_group.id'), primary_key=True)
)
classroom_advisors = db.Table('classroom_advisors',
    db.Column('user_id', db.Integer, db.ForeignKey('user.id'), primary_key=True),
    db.Column('classroom_id', db.Integer, db.ForeignKey('classroom.id'), primary_key=True)
)
course_teachers = db.Table('course_teachers',
    db.Column('course_id', db.Integer, db.ForeignKey('course.id'), primary_key=True),
    db.Column('user_id', db.Integer, db.ForeignKey('user.id'), primary_key=True)
)
learning_unit_indicators = db.Table('learning_unit_indicators',
    db.Column('learning_unit_id', db.Integer, db.ForeignKey('learning_unit.id'), primary_key=True),
    db.Column('indicator_id', db.Integer, db.ForeignKey('indicator.id'), primary_key=True)
)
unit_indicators = db.Table('unit_indicators',
    db.Column('learning_unit_id', db.Integer, db.ForeignKey('learning_unit.id'), primary_key=True),
    db.Column('indicator_id', db.Integer, db.ForeignKey('indicator.id'), primary_key=True)
)
sub_unit_indicators = db.Table('sub_unit_indicators',
    db.Column('sub_unit_id', db.Integer, db.ForeignKey('sub_unit.id'), primary_key=True),
    db.Column('indicator_id', db.Integer, db.ForeignKey('indicator.id'), primary_key=True)
)
sub_unit_graded_items = db.Table('sub_unit_graded_items',
    db.Column('sub_unit_id', db.Integer, db.ForeignKey('sub_unit.id'), primary_key=True),
    db.Column('graded_item_id', db.Integer, db.ForeignKey('graded_item.id'), primary_key=True)
)
sub_unit_assessment_items = db.Table('sub_unit_assessment_items',
    db.Column('sub_unit_id', db.Integer, db.ForeignKey('sub_unit.id'), primary_key=True),
    db.Column('assessment_item_id', db.Integer, db.ForeignKey('assessment_item.id'), primary_key=True)
)
subunit_topics = db.Table('subunit_topics',
    db.Column('subunit_id', db.Integer, db.ForeignKey('sub_unit.id', name='fk_subunit_topics_subunit'), primary_key=True),
    db.Column('topic_id', db.Integer, db.ForeignKey('assessment_topic.id', name='fk_subunit_topics_topic'), primary_key=True)
)
student_group_members = db.Table('student_group_members',
    db.Column('enrollment_id', db.Integer, db.ForeignKey('enrollment.id'), primary_key=True),
    db.Column('student_group_id', db.Integer, db.ForeignKey('student_group.id'), primary_key=True)
)
admin_department_members = db.Table('admin_department_members',
    db.Column('user_id', db.Integer, db.ForeignKey('user.id'), primary_key=True),
    db.Column('department_id', db.Integer, db.ForeignKey('administrative_department.id'), primary_key=True)
)
weekly_schedule_slot_grades = db.Table('weekly_schedule_slot_grades',
    db.Column('slot_id', db.Integer, db.ForeignKey('weekly_schedule_slot.id'), primary_key=True),
    db.Column('grade_level_id', db.Integer, db.ForeignKey('grade_level.id'), primary_key=True)
)
school_event_grades = db.Table('school_event_grades',
    db.Column('event_id', db.Integer, db.ForeignKey('school_event.id'), primary_key=True),
    db.Column('grade_level_id', db.Integer, db.ForeignKey('grade_level.id'), primary_key=True)
)

class Setting(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    key = db.Column(db.String(50), unique=True, nullable=False)
    value = db.Column(db.Text, nullable=True)

class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(64), index=True, unique=True, nullable=False)
    email = db.Column(db.String(120), index=True, unique=True, nullable=True)
    password_hash = db.Column(db.String(256))
    name_prefix = db.Column(db.String(20), nullable=True)
    first_name = db.Column(db.String(64), nullable=False)
    last_name = db.Column(db.String(64), nullable=False)
    job_title = db.Column(db.String(100), nullable=True)
    must_change_username = db.Column(db.Boolean, default=True, nullable=False)
    must_change_password = db.Column(db.Boolean, default=True, nullable=False)

    roles = db.relationship('Role', secondary=user_roles, back_populates='users')
    advised_classrooms = db.relationship('Classroom', secondary=classroom_advisors, back_populates='advisors')
    member_of_groups = db.relationship('SubjectGroup', secondary=subject_group_members, back_populates='members')
    courses = db.relationship('Course', secondary=course_teachers, back_populates='teachers', lazy='select')
    logs = db.relationship('AuditLog', back_populates='user', lazy='dynamic')
    member_of_admin_depts = db.relationship('AdministrativeDepartment', secondary=admin_department_members, back_populates='members')

    # --- ADDED THIS LINE ---
    created_indicators = db.relationship('Indicator', back_populates='creator', lazy='dynamic')

    @property
    def full_name(self):
        """Returns the user's full name."""
        return f"{self.name_prefix or ''}{self.first_name} {self.last_name}".strip()

    def set_password(self, password):
        self.password_hash = generate_password_hash(password, method='pbkdf2:sha256:260000')

    def check_password(self, password):
        if self.password_hash:
            return check_password_hash(self.password_hash, password)
        return False
    
    def check_student_password(self, password_input):
        """Checks if the provided password matches the student ID (for student login)."""
        # Check if this User is linked to a Student profile
        if self.student_profile:
            # For students, the password is their student ID
            return self.student_profile.student_id == password_input
        # If not linked to a student, this method should not be used for validation
        return False
        
    def has_role(self, role_name):
        """Helper function to check if a user has a specific role."""
        return any(role.name == role_name for role in self.roles)

    def __repr__(self):
        return f'<User {self.username}>'

class Role(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(64), unique=True, nullable=False)
    description = db.Column(db.String(255))
    users = db.relationship('User', secondary=user_roles, back_populates='roles')
    def __repr__(self): return self.name

class GradeLevel(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(50), nullable=False, unique=True)
    short_name = db.Column(db.String(10))
    level_group = db.Column(db.String(10), nullable=True, index=True) # เช่น 'm-ton', 'm-plai'
    head_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True)
    head = db.relationship('User', backref=db.backref('led_grade_level', uselist=False))
    weekly_schedule_slots = db.relationship('WeeklyScheduleSlot', backref='grade_level', lazy='dynamic')
    school_events = db.relationship('SchoolEvent', secondary=school_event_grades, back_populates='grade_levels')
    classrooms = db.relationship('Classroom', back_populates='grade_level')
    
    def __repr__(self): return self.name

class SubjectGroup(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False, unique=True)
    head_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True)
    head = db.relationship('User', backref=db.backref('led_subject_group', uselist=False))
    members = db.relationship('User', secondary=subject_group_members, back_populates='member_of_groups')
    learning_strands = db.relationship('LearningStrand', back_populates='subject_group', cascade="all, delete-orphan")
    def __repr__(self): return self.name

class Program(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False, unique=True, index=True)
    description = db.Column(db.String(255), nullable=True)
    
    # Relationship back to Classrooms
    classrooms = db.relationship('Classroom', back_populates='program', lazy='dynamic')
    # Relationship back to Curriculum entries (optional, if needed)
    # curriculum_entries = db.relationship('Curriculum', backref='program', lazy='dynamic')

    def __repr__(self):
        return f'<Program {self.name}>'
    
class SubjectType(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False, unique=True)
    def __repr__(self): return self.name

class AcademicYear(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    year = db.Column(db.Integer, unique=True, nullable=False)
    semesters = db.relationship('Semester', back_populates='academic_year', lazy='dynamic', cascade="all, delete-orphan")
    classrooms = db.relationship('Classroom', back_populates='academic_year', lazy='dynamic')
    def __repr__(self): return str(self.year)

class Semester(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    term = db.Column(db.Integer, nullable=False)
    start_date = db.Column(db.Date)
    end_date = db.Column(db.Date)
    is_current = db.Column(db.Boolean, default=False, index=True)
    academic_year_id = db.Column(db.Integer, db.ForeignKey('academic_year.id'), nullable=False)
    academic_year = db.relationship('AcademicYear', back_populates='semesters')
    curriculums = db.relationship('Curriculum', back_populates='semester', cascade="all, delete-orphan")
    weekly_schedule_slots = db.relationship('WeeklyScheduleSlot', backref='semester', lazy='dynamic', cascade="all, delete-orphan")
    time_slots = db.relationship('TimeSlot', backref='semester', lazy='dynamic', cascade="all, delete-orphan")
    def __repr__(self): return f'{self.academic_year.year}/{self.term}'

class Subject(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    subject_code = db.Column(db.String(20), unique=True, nullable=False, index=True)
    name = db.Column(db.String(100), nullable=False)
    credit = db.Column(db.Float, nullable=False)
    subject_group_id = db.Column(db.Integer, db.ForeignKey('subject_group.id'), nullable=False)
    subject_type_id = db.Column(db.Integer, db.ForeignKey('subject_type.id'), nullable=False)
    subject_group = db.relationship('SubjectGroup', backref=db.backref('subjects', lazy=True))
    subject_type = db.relationship('SubjectType', backref=db.backref('subjects', lazy=True))
    grade_levels = db.relationship('GradeLevel', secondary=subject_grade_levels, backref=db.backref('subjects', lazy='dynamic'))
    lesson_plans = db.relationship('LessonPlan', back_populates='subject', cascade="all, delete-orphan")

    def __repr__(self): return f'{self.subject_code} - {self.name}'

class Curriculum(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    semester_id = db.Column(db.Integer, db.ForeignKey('semester.id', name='fk_curriculum_semester'), nullable=False)
    grade_level_id = db.Column(db.Integer, db.ForeignKey('grade_level.id', name='fk_curriculum_grade_level'), nullable=False)
    subject_id = db.Column(db.Integer, db.ForeignKey('subject.id', name='fk_curriculum_subject'), nullable=False)
    program_id = db.Column(db.Integer, db.ForeignKey('program.id', name='fk_curriculum_program'), nullable=False, index=True)
    semester = db.relationship('Semester', back_populates='curriculums')
    grade_level = db.relationship('GradeLevel', backref=db.backref('curriculum_items'))
    subject = db.relationship('Subject', backref=db.backref('curriculum_items'))
    program = db.relationship('Program')
    __table_args__ = (UniqueConstraint('semester_id', 'grade_level_id', 'program_id', 'subject_id', name='_semester_grade_program_subject_uc'),)

    def __repr__(self):
        # Optional: Update repr if needed
        return f'<Curriculum Sem:{self.semester_id} Grade:{self.grade_level_id} Prog:{self.program_id} Subj:{self.subject_id}>'
    
class Classroom(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(50), nullable=False)
    grade_level_id = db.Column(db.Integer, db.ForeignKey('grade_level.id', name='fk_classroom_grade_level'), nullable=False)
    academic_year_id = db.Column(db.Integer, db.ForeignKey('academic_year.id', name='fk_classroom_academic_year'), nullable=False)
    program_id = db.Column(db.Integer, db.ForeignKey('program.id', name='fk_classroom_program'), nullable=True, index=True)
    room_id = db.Column(db.Integer, db.ForeignKey('room.id', name='fk_classroom_room'), nullable=True)
    grade_level = db.relationship('GradeLevel', back_populates='classrooms')
    academic_year = db.relationship('AcademicYear', back_populates='classrooms')
    enrollments = db.relationship('Enrollment', back_populates='classroom', lazy='dynamic', cascade="all, delete-orphan")
    advisors = db.relationship('User', secondary=classroom_advisors, back_populates='advised_classrooms')
    room = db.relationship('Room',
                           back_populates='classrooms',
                           primaryjoin="Classroom.room_id == Room.id")
    program = db.relationship('Program', back_populates='classrooms')
    courses = db.relationship('Course', back_populates='classroom', lazy='dynamic', cascade="all, delete-orphan")

    def __repr__(self): return f'{self.name} ({self.academic_year.year})'

class Student(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    student_id = db.Column(db.String(20), unique=True, nullable=False, index=True)
    name_prefix = db.Column(db.String(20), nullable=False)
    first_name = db.Column(db.String(64), nullable=False)
    last_name = db.Column(db.String(64), nullable=False)
    status = db.Column(db.String(50), default='กำลังศึกษา')
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), unique=True, nullable=True)
    user = db.relationship('User', backref=db.backref('student_profile', uselist=False))
    enrollments = db.relationship('Enrollment', back_populates='student', lazy='dynamic', cascade="all, delete-orphan")
    scores = db.relationship('Score', back_populates='student', lazy=True, cascade="all, delete-orphan")

    def __repr__(self): return f'{self.student_id} - {self.name_prefix}{self.first_name} {self.last_name}'

class Enrollment(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    student_id = db.Column(db.Integer, db.ForeignKey('student.id'), nullable=False)
    classroom_id = db.Column(db.Integer, db.ForeignKey('classroom.id'), nullable=False)
    roll_number = db.Column(db.Integer)
    alerts = db.Column(db.JSON, nullable=True) # สำหรับเก็บสถานะ ร, 0, มส
    student_group_id = db.Column(db.Integer, db.ForeignKey('student_group.id'), nullable=True)
    student = db.relationship('Student', back_populates='enrollments')
    classroom = db.relationship('Classroom', back_populates='enrollments')
    student_group = db.relationship('StudentGroup', back_populates='enrollments')

class Course(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    subject_id = db.Column(db.Integer, db.ForeignKey('subject.id'), nullable=False)
    classroom_id = db.Column(db.Integer, db.ForeignKey('classroom.id'), nullable=False)
    semester_id = db.Column(db.Integer, db.ForeignKey('semester.id'), nullable=False)
    lesson_plan_id = db.Column(db.Integer, db.ForeignKey('lesson_plan.id'), nullable=True)
    room_id = db.Column(db.Integer, db.ForeignKey('room.id'), nullable=True) # <-- ADD THIS LINE

    grade_submission_status = db.Column(db.String(50), nullable=False, default='ยังไม่ส่ง', index=True)
    grade_submission_notes = db.Column(db.Text, nullable=True) # สำหรับหมายเหตุการส่งกลับ
    submitted_by_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True)
    submitted_at = db.Column(db.DateTime, nullable=True)

    # Relationships
    subject = db.relationship('Subject', backref=db.backref('courses', lazy='dynamic'))
    classroom = db.relationship('Classroom', back_populates='courses')
    semester = db.relationship('Semester', backref=db.backref('courses', lazy='dynamic'))
    teachers = db.relationship('User', secondary=course_teachers, back_populates='courses', lazy='select')
    lesson_plan = db.relationship('LessonPlan', back_populates='courses')
    timetable_entries = db.relationship('TimetableEntry', back_populates='course', cascade="all, delete-orphan")
    room = db.relationship('Room', back_populates='courses')
    student_groups = db.relationship('StudentGroup', back_populates='course', lazy='dynamic')
    submitted_by = db.relationship('User', foreign_keys=[submitted_by_id])
    qualitative_scores = db.relationship('QualitativeScore', back_populates='course', cascade="all, delete-orphan")
    
    # Constraints
    __table_args__ = (
        db.UniqueConstraint('subject_id', 'classroom_id', 'semester_id', name='_subject_classroom_semester_uc'),
        db.ForeignKeyConstraint(['submitted_by_id'], ['user.id'], name='fk_course_submitted_by_user')
    )

    def __repr__(self):
        return f'<Course {self.subject.subject_code} for {self.classroom.name} in {self.semester}>'

class LearningStrand(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(255), nullable=False) # e.g., "สาระที่ 1: ทัศนศิลป์"
    
    subject_group_id = db.Column(db.Integer, db.ForeignKey('subject_group.id'), nullable=False)
    subject_group = db.relationship('SubjectGroup', back_populates='learning_strands')
    
    standards = db.relationship('Standard', back_populates='learning_strand', cascade="all, delete-orphan")

    def __repr__(self):
        return f'<LearningStrand {self.name}>'
    
class Standard(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    code = db.Column(db.String(50), nullable=False)
    description = db.Column(db.Text, nullable=False)
    
    # Relationships
    learning_strand_id = db.Column(db.Integer, db.ForeignKey('learning_strand.id'), nullable=False)
    learning_strand = db.relationship('LearningStrand', back_populates='standards')
    indicators = db.relationship('Indicator', back_populates='standard', cascade="all, delete-orphan")

    __table_args__ = (
        db.UniqueConstraint('code', 'learning_strand_id', name='_code_strand_uc'),
        db.Index('ix_standard_code', 'code') # Explicitly define the index here
    )
    def __repr__(self):
        return f'<Standard {self.code}>'

class Indicator(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    code = db.Column(db.String(50), nullable=False)
    description = db.Column(db.Text, nullable=False)
    creator_type = db.Column(db.String(20), nullable=False, default='ADMIN') # ADMIN or TEACHER

    # Foreign Keys
    standard_id = db.Column(db.Integer, db.ForeignKey('standard.id'), nullable=False)
    creator_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True) # Null if ADMIN
    lesson_plan_id = db.Column(db.Integer, db.ForeignKey('lesson_plan.id'), nullable=True) # Null if ADMIN

    # Relationships
    standard = db.relationship('Standard', back_populates='indicators')
    creator = db.relationship('User', back_populates='created_indicators')
    lesson_plan = db.relationship('LessonPlan', back_populates='custom_indicators')

    __table_args__ = (
        db.Index('ix_indicator_code', 'code'),
        db.Index('ix_indicator_creator_type', 'creator_type'),
    )

    def __repr__(self):
        return f'<Indicator {self.code} - {self.description[:30]}>'

class AssessmentDimension(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    code = db.Column(db.String(10), unique=True, nullable=False, index=True)
    name = db.Column(db.String(100), nullable=False)
    description = db.Column(db.Text, nullable=True)

    def __repr__(self):
        return f'<Dimension {self.code}: {self.name}>'

class AssessmentTemplate(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(150), unique=True, nullable=False)
    description = db.Column(db.Text, nullable=True)
    display_order = db.Column(db.Integer, default=0, nullable=False)
    
    # Relationships
    topics = db.relationship('AssessmentTopic', back_populates='template', cascade="all, delete-orphan")
    rubric_levels = db.relationship('RubricLevel', back_populates='template', cascade="all, delete-orphan")

    def __repr__(self):
        return f'<AssessmentTemplate {self.name}>'

class AssessmentTopic(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(255), nullable=False)
    template_id = db.Column(db.Integer, db.ForeignKey('assessment_template.id'), nullable=False)
    parent_id = db.Column(db.Integer, db.ForeignKey('assessment_topic.id'), nullable=True)

    # Relationships
    template = db.relationship('AssessmentTemplate', back_populates='topics')
    children = db.relationship('AssessmentTopic', backref=db.backref('parent', remote_side=[id]), cascade="all, delete-orphan")
    assessment_items = db.relationship('AssessmentItem', back_populates='topic')
    qualitative_scores = db.relationship('QualitativeScore', back_populates='topic')

    def __repr__(self):
        return f'<AssessmentTopic {self.name}>'

class RubricLevel(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    template_id = db.Column(db.Integer, db.ForeignKey('assessment_template.id'), nullable=False)
    label = db.Column(db.String(50), nullable=False)
    value = db.Column(db.Float, nullable=False)
    order = db.Column(db.Integer, default=0)

    # Relationships
    template = db.relationship('AssessmentTemplate', back_populates='rubric_levels')

    def __repr__(self):
        return f'<RubricLevel {self.label} ({self.value})>'
    
class LearningUnit(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    lesson_plan_id = db.Column(db.Integer, db.ForeignKey('lesson_plan.id'), nullable=False)
    title = db.Column(db.String(255), nullable=False)
    sequence = db.Column(db.Integer, default=0)

    midterm_score = db.Column(db.Float, nullable=True)
    final_score = db.Column(db.Float, nullable=True)
        
    topic = db.Column(db.String(255), nullable=True)
    hours = db.Column(db.Integer, nullable=True)
    target_mid_ratio = db.Column(db.Integer, nullable=True)
    target_final_ratio = db.Column(db.Integer, nullable=True)
    learning_objectives = db.Column(db.Text, nullable=True)
    learning_content = db.Column(db.Text, nullable=True) # New Field
    learning_activities = db.Column(db.Text, nullable=True) # Renamed from 'activities'
    core_concepts = db.Column(db.Text, nullable=True)
    activities = db.Column(db.Text, nullable=True)
    media_sources = db.Column(db.Text, nullable=True)

    reflections = db.relationship('LessonReflection', back_populates='unit', cascade="all, delete-orphan")

    lesson_plan = db.relationship('LessonPlan', back_populates='learning_units')

    indicators = db.relationship('Indicator', secondary=learning_unit_indicators,
                                 backref=db.backref('learning_units', lazy='dynamic'),
                                 lazy='select')
    
    graded_items = db.relationship('GradedItem', back_populates='learning_unit', cascade="all, delete-orphan", lazy='select')
    
    sub_units = db.relationship('SubUnit', backref='learning_unit', lazy=True, cascade="all, delete-orphan")

    def __repr__(self):
        return f'<LearningUnit {self.title}>'

class AssessmentItem(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    learning_unit_id = db.Column(db.Integer, db.ForeignKey('learning_unit.id'), nullable=False)
    assessment_topic_id = db.Column(db.Integer, db.ForeignKey('assessment_topic.id'), nullable=False)
    
    # Relationships
    unit = db.relationship('LearningUnit', backref=db.backref('assessment_items', cascade="all, delete-orphan"))
    scores = db.relationship('Score', back_populates='assessment_item', cascade="all, delete-orphan")
    topic = db.relationship('AssessmentTopic', back_populates='assessment_items')
    
    def __repr__(self):
        return f'<AssessmentItem Unit:{self.learning_unit_id} Topic:{self.assessment_topic_id}>'

class Score(db.Model):
    __tablename__ = 'score'
    id = db.Column(db.Integer, primary_key=True)
    student_id = db.Column(db.Integer, db.ForeignKey('student.id'), nullable=False)
    assessment_item_id = db.Column(db.Integer, db.ForeignKey('assessment_item.id'), nullable=True)
    rubric_level_id = db.Column(db.Integer, db.ForeignKey('rubric_level.id'), nullable=True)
    score = db.Column(db.Float, nullable=True)
    details = db.Column(db.JSON, nullable=True)
    graded_item_id = db.Column(db.Integer, db.ForeignKey('graded_item.id'), nullable=True)

    # Relationships
    student = db.relationship('Student', back_populates='scores')
    assessment_item = db.relationship('AssessmentItem', back_populates='scores')
    rubric_level = db.relationship('RubricLevel')
    graded_item = db.relationship('GradedItem', back_populates='scores')

    def __repr__(self):
        return f'<Score Student:{self.student_id} Item:{self.assessment_item_id}>'

class GroupScore(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    score = db.Column(db.Float, nullable=True)
    student_group_id = db.Column(db.Integer, db.ForeignKey('student_group.id'), nullable=False)
    graded_item_id = db.Column(db.Integer, db.ForeignKey('graded_item.id'), nullable=False)
    student_group = db.relationship('StudentGroup', backref=db.backref('group_scores', cascade="all, delete-orphan"))
    graded_item = db.relationship('GradedItem', backref=db.backref('group_scores', cascade="all, delete-orphan"))
    __table_args__ = (db.UniqueConstraint('student_group_id', 'graded_item_id', name='_group_item_uc'),)
    def __repr__(self):
        return f'<GroupScore for Group:{self.student_group_id} on Item:{self.graded_item_id}>'
    
class LessonReflection(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    learning_unit_id = db.Column(db.Integer, db.ForeignKey('learning_unit.id'), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    content = db.Column(db.Text, nullable=False)
    timestamp = db.Column(db.DateTime, server_default=db.func.now())

    # Relationships
    unit = db.relationship('LearningUnit', back_populates='reflections')
    author = db.relationship('User', backref='reflections')

    def __repr__(self):
        return f'<LessonReflection Unit:{self.learning_unit_id} Author:{self.user_id}>'

class AuditLog(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    action = db.Column(db.String(255), nullable=False)
    model_name = db.Column(db.String(50), nullable=True)
    record_id = db.Column(db.String(50), nullable=True) # <-- เปลี่ยนจาก db.Integer
    old_value = db.Column(db.Text, nullable=True)
    new_value = db.Column(db.Text, nullable=True)
    timestamp = db.Column(db.DateTime, server_default=db.func.now())

    # Relationship
    user = db.relationship('User', back_populates='logs')

    def __repr__(self):
        return f'<AuditLog {self.action} by User:{self.user_id}>'

class LessonPlan(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    subject_id = db.Column(db.Integer, db.ForeignKey('subject.id'), nullable=False)
    academic_year_id = db.Column(db.Integer, db.ForeignKey('academic_year.id'), nullable=False)
    target_mid_ratio = db.Column(db.Integer, nullable=True)
    target_final_ratio = db.Column(db.Integer, nullable=True)
    status = db.Column(db.String(50), nullable=False, default='ฉบับร่าง', index=True)
    revision_notes = db.Column(db.Text, nullable=True)
    manual_scheduling_notes = db.Column(db.Text, nullable=True) # บันทึกช่วยจำสำหรับผู้จัดตาราง

    # Relationships
    subject = db.relationship('Subject', back_populates='lesson_plans')
    academic_year = db.relationship('AcademicYear')
    learning_units = db.relationship('LearningUnit', back_populates='lesson_plan', cascade="all, delete-orphan")
    courses = db.relationship('Course', back_populates='lesson_plan')
    custom_indicators = db.relationship('Indicator', back_populates='lesson_plan', lazy='dynamic', cascade="all, delete-orphan")
    constraints = db.relationship('LessonPlanConstraint', backref='lesson_plan', cascade="all, delete-orphan")

    __table_args__ = (db.UniqueConstraint('subject_id', 'academic_year_id', name='_subject_year_uc'),)

    def __repr__(self):
        return f'<LessonPlan for {self.subject.name} ({self.academic_year.year})>'

class GradedItem(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(255), nullable=False)
    max_score = db.Column(db.Float, nullable=False, default=0)
    indicator_type = db.Column(db.String(50), nullable=False, default='FORMATIVE') # FORMATIVE or SUMMATIVE
    assessment_type = db.Column(db.String(50), nullable=False, server_default='ปลายภาค') # e.g., 'กลางภาค', 'ปลายภาค'

    # Foreign Keys
    learning_unit_id = db.Column(db.Integer, db.ForeignKey('learning_unit.id'), nullable=False)
    assessment_dimension_id = db.Column(db.Integer, db.ForeignKey('assessment_dimension.id'), nullable=False)
    is_group_assignment = db.Column(db.Boolean, default=False, nullable=False) # <-- ตรวจสอบว่ามีบรรทัดนี้

    # Relationships
    learning_unit = db.relationship('LearningUnit', back_populates='graded_items') 
    scores = db.relationship('Score', back_populates='graded_item', lazy=True, cascade="all, delete-orphan")
    dimension = db.relationship('AssessmentDimension', backref='graded_items')

    def __repr__(self):
        return f'<GradedItem {self.name}>'
    
class SubUnit(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(255), nullable=False)
    hour_sequence = db.Column(db.Integer, nullable=False) # e.g., 1, 2, 3...
    activities = db.Column(db.Text)
    
    learning_unit_id = db.Column(db.Integer, db.ForeignKey('learning_unit.id'), nullable=False)

    # Many-to-Many relationships
    indicators = db.relationship('Indicator', secondary=sub_unit_indicators, lazy='subquery',
                                 backref=db.backref('sub_units', lazy=True))
    graded_items = db.relationship('GradedItem', secondary=sub_unit_graded_items, lazy='subquery',
                                   backref=db.backref('sub_units', lazy=True))
    assessment_topics = db.relationship('AssessmentTopic', secondary=subunit_topics, lazy='subquery',
                                          backref=db.backref('sub_units', lazy=True))

    def __repr__(self):
        return f'<SubUnit {self.title}>'
    
class QualitativeScore(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    score_value = db.Column(db.Integer, nullable=False)
    student_id = db.Column(db.Integer, db.ForeignKey('student.id'), nullable=False, index=True)
    assessment_topic_id = db.Column(db.Integer, db.ForeignKey('assessment_topic.id'), nullable=False, index=True)
    course_id = db.Column(db.Integer, db.ForeignKey('course.id'), nullable=False, index=True)
    topic = db.relationship('AssessmentTopic', back_populates='qualitative_scores')
    course = db.relationship('Course', back_populates='qualitative_scores')

    # กำหนดให้ (นักเรียน, หัวข้อ, คอร์ส) ต้องไม่ซ้ำกัน
    __table_args__ = (db.UniqueConstraint('student_id', 'assessment_topic_id', 'course_id', name='_student_topic_course_uc'),)

    def __repr__(self):
        return f'<QualitativeScore for Student {self.student_id} on Topic {self.assessment_topic_id}>'
    
class StudentGroup(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    # index=True ช่วยให้ค้นหากลุ่มตาม course ได้เร็วขึ้น
    course_id = db.Column(db.Integer, db.ForeignKey('course.id'), nullable=False, index=True)
    lesson_plan_id = db.Column(db.Integer, db.ForeignKey('lesson_plan.id'), nullable=False, index=True)
    creator_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False, index=True)
    
    # ความสัมพันธ์นี้ช่วยให้เราสามารถหากลุ่มของนักเรียนได้จาก enrollment
    course = db.relationship('Course', back_populates='student_groups')
    # learning_unit = db.relationship('LearningUnit', backref=db.backref('student_groups', lazy='dynamic', cascade="all, delete-orphan"))
    enrollments = db.relationship('Enrollment', back_populates='student_group', lazy='select')
    creator = db.relationship('User', backref='created_student_groups')

    def __repr__(self):
        return f'<StudentGroup {self.name}>'
    
class PostTeachingLog(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    log_content = db.Column(db.Text, nullable=False)
    problems_obstacles = db.Column(db.Text, nullable=True)
    solutions = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    learning_unit_id = db.Column(db.Integer, db.ForeignKey('learning_unit.id'), nullable=False, index=True)
    teacher_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False, index=True)
    classroom_id = db.Column(db.Integer, db.ForeignKey('classroom.id'), nullable=True, index=True) # Set nullable to True

    # กำหนดให้ (หน่วย, ครู, ห้องเรียน) ต้องไม่ซ้ำกัน
    __table_args__ = (
        db.UniqueConstraint('learning_unit_id', 'teacher_id', 'classroom_id', name='_unit_teacher_classroom_uc'),
    )
    
    def __repr__(self):
        return f'<PostTeachingLog for Unit {self.learning_unit_id} by Teacher {self.teacher_id}>'
    
class AdministrativeDepartment(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(150), unique=True, nullable=False)
    
    # เรายังเก็บ ID ของ User ที่ดำรงตำแหน่งไว้เหมือนเดิม
    head_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True)
    vice_director_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True)
    
    # Relationships
    head = db.relationship('User', foreign_keys=[head_id])
    vice_director = db.relationship('User', foreign_keys=[vice_director_id])
    members = db.relationship('User', secondary=admin_department_members, back_populates='member_of_admin_depts')
    
    # --- [ใหม่] เพิ่มคอลัมน์สำหรับ "ผูก" กับ Role ที่มีอยู่ ---
    head_role_id = db.Column(db.Integer, db.ForeignKey('role.id', name='fk_admin_dept_head_role'), nullable=True)
    vice_role_id = db.Column(db.Integer, db.ForeignKey('role.id', name='fk_admin_dept_vice_role'), nullable=True)
    member_role_id = db.Column(db.Integer, db.ForeignKey('role.id', name='fk_admin_dept_member_role'), nullable=True)

    # --- [ใหม่] สร้าง Relationship ไปยัง Role ---
    head_role = db.relationship('Role', foreign_keys=[head_role_id])
    vice_role = db.relationship('Role', foreign_keys=[vice_role_id])
    member_role = db.relationship('Role', foreign_keys=[member_role_id])

    def __repr__(self):
        return f'<AdministrativeDepartment {self.name}>'

@event.listens_for(AdministrativeDepartment, 'after_insert')
def create_department_roles(mapper, connection, target):
    """
    Automatically creates associated roles when a new administrative department is created.
    """
    session = db.session.object_session(target)
    if not session:
        # This can happen in certain test setups, but should have a session in the app context.
        return

    dept_id = target.id
    roles_to_create = [
        (f"DEPT_HEAD_{dept_id}", f"Head of Department ID {dept_id}"),
        (f"DEPT_VICE_{dept_id}", f"Vice Director of Department ID {dept_id}"),
        (f"DEPT_MEMBER_{dept_id}", f"Member of Department ID {dept_id}")
    ]

    for role_name, role_desc in roles_to_create:
        if not session.query(Role).filter_by(name=role_name).first():
            new_role = Role(name=role_name, description=role_desc)
            session.add(new_role)

class WeeklyScheduleSlot(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    semester_id = db.Column(db.Integer, db.ForeignKey('semester.id'), nullable=False, index=True)
    grade_level_id = db.Column(db.Integer, db.ForeignKey('grade_level.id'), nullable=False, index=True)
    day_of_week = db.Column(db.Integer, nullable=False) # 1=Monday, 2=Tuesday, ... 7=Sunday
    period_number = db.Column(db.Integer, nullable=False)
    start_time = db.Column(db.Time, nullable=False)
    end_time = db.Column(db.Time, nullable=False)
    activity_name = db.Column(db.String(100), nullable=True)
    is_teaching_period = db.Column(db.Boolean, nullable=False, default=True)

    __table_args__ = (
        db.UniqueConstraint('semester_id', 'grade_level_id', 'day_of_week', 'period_number', name='_unique_slot_for_grade'),
    )

    def __repr__(self):
        return f'<WeeklySlot Day:{self.day_of_week} Period:{self.period_number}>'

class SchoolEvent(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(255), nullable=False)
    description = db.Column(db.Text)
    start_datetime = db.Column(db.DateTime, nullable=False)
    end_datetime = db.Column(db.DateTime, nullable=False)
    is_all_day = db.Column(db.Boolean, default=False)
    grade_levels = db.relationship('GradeLevel', secondary=school_event_grades, back_populates='school_events')

    def __repr__(self):
        return f'<SchoolEvent {self.name}>'

class TimeSlot(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    semester_id = db.Column(db.Integer, db.ForeignKey('semester.id'), nullable=False, index=True)
    period_number = db.Column(db.Integer, nullable=False)
    start_time = db.Column(db.Time, nullable=False)
    end_time = db.Column(db.Time, nullable=False)
    activity_name = db.Column(db.String(100), nullable=True) # e.g., 'พักกลางวัน'
    is_teaching_period = db.Column(db.Boolean, nullable=False, default=True)

    def __repr__(self):
        return f'<TimeSlot {self.period_number} for Semester {self.semester_id}>'

class Room(db.Model):
    __tablename__ = 'room'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), unique=True, nullable=False)
    capacity = db.Column(db.Integer, nullable=True)
    room_type = db.Column(db.String(100), nullable=True)
    notes = db.Column(db.Text, nullable=True)
    classrooms = db.relationship('Classroom',
                                 back_populates='room', # <-- ต้องตรงกับชื่อใน Classroom
                                 lazy='dynamic',
                                 primaryjoin="Room.id == Classroom.room_id")
    courses = db.relationship('Course', back_populates='room', lazy='dynamic')

    def __repr__(self):
        return f'<Room {self.name}>'

class LessonPlanConstraint(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    lesson_plan_id = db.Column(db.Integer, db.ForeignKey('lesson_plan.id'), nullable=False, index=True)
    constraint_type = db.Column(db.String(50), nullable=False)
    value = db.Column(db.String(100), nullable=False)

    def __repr__(self):
        return f'<LessonPlanConstraint {self.constraint_type}={self.value}>'
                
class TimetableEntry(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    course_id = db.Column(db.Integer, db.ForeignKey('course.id'), nullable=False)
    weekly_schedule_slot_id = db.Column(db.Integer, db.ForeignKey('weekly_schedule_slot.id'), nullable=False)

    # Relationships
    course = db.relationship('Course', back_populates='timetable_entries')
    slot = db.relationship('WeeklyScheduleSlot', backref='timetable_entry')
    attendance_records = db.relationship('AttendanceRecord', back_populates='timetable_entry', cascade="all, delete-orphan")

    __table_args__ = (db.UniqueConstraint('weekly_schedule_slot_id', name='_slot_uc'),)

    def __repr__(self):
        return f'<TimetableEntry Course:{self.course_id} Slot:{self.weekly_schedule_slot_id}>'

class AttendanceWarning(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    student_id = db.Column(db.Integer, db.ForeignKey('student.id'), nullable=False, index=True)
    course_id = db.Column(db.Integer, db.ForeignKey('course.id'), nullable=False, index=True)
    threshold_percent = db.Column(db.Integer, nullable=False)
    triggered_at = db.Column(db.DateTime, default=datetime.utcnow)
    absence_count_at_trigger = db.Column(db.Integer, nullable=False)
    status = db.Column(db.String(50), default='ACTIVE', nullable=False)

    student = db.relationship('Student', backref='attendance_warnings')
    course = db.relationship('Course', backref='attendance_warnings')

    __table_args__ = (db.UniqueConstraint('student_id', 'course_id', 'threshold_percent', name='_student_course_threshold_uc'),)

    def __repr__(self):
        return f'<AttendanceWarning for Student {self.student_id} in Course {self.course_id}>'

class AttendanceRecord(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    status = db.Column(db.String(20), nullable=False, default='PRESENT')
    recorded_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    attendance_date = db.Column(db.Date, nullable=False, index=True, server_default=func.current_date())

    student_id = db.Column(db.Integer, db.ForeignKey('student.id'), nullable=False, index=True)
    timetable_entry_id = db.Column(db.Integer, db.ForeignKey('timetable_entry.id'), nullable=False, index=True)
    recorder_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)

    student = db.relationship('Student', backref='attendance_records')
    timetable_entry = db.relationship('TimetableEntry', back_populates='attendance_records')
    recorder = db.relationship('User', backref='recorded_attendance')

    # --- UPDATE THIS LINE ---
    __table_args__ = (db.UniqueConstraint('student_id', 'timetable_entry_id', 'attendance_date', name='_student_entry_date_uc'),)

    def __repr__(self):
        return f'<AttendanceRecord Student {self.student_id} is {self.status} on {self.attendance_date}>'
    
class Notification(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False, index=True)
    title = db.Column(db.String(255), nullable=False)
    message = db.Column(db.Text, nullable=False)
    url = db.Column(db.String(255), nullable=True) # Link for Action
    is_read = db.Column(db.Boolean, default=False, nullable=False, index=True)
    notification_type = db.Column(db.String(50), index=True) # e.g., 'ATTENDANCE', 'GRADE_ALERT', 'HR'
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    user = db.relationship('User', backref=db.backref('notifications', lazy='dynamic'))

    def __repr__(self):
        return f'<Notification for User {self.user_id}>'
    
class CourseGrade(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    student_id = db.Column(db.Integer, db.ForeignKey('student.id'), nullable=False, index=True)
    course_id = db.Column(db.Integer, db.ForeignKey('course.id'), nullable=False, index=True)
    midterm_score = db.Column(db.Float, nullable=True)
    final_score = db.Column(db.Float, nullable=True)
    midterm_remediated_score = db.Column(db.Float, nullable=True)

    final_grade = db.Column(db.String(10), nullable=True, index=True) # เช่น '4', '3.5', '0', 'ร', 'มส'
    remediation_status = db.Column(db.String(50), default='None', nullable=False) # สถานะ: None, In Progress, Completed
    original_final_grade = db.Column(db.String(10), nullable=True) # เก็บเกรดเดิมก่อนซ่อม
    remediated_at = db.Column(db.DateTime, nullable=True) # วันที่ซ่อมเสร็จ
    remediation_status = db.Column(db.String(50), default='None', nullable=False) # สถานะ: None, In Progress, Completed
    original_final_grade = db.Column(db.String(10), nullable=True) # เก็บเกรดเดิมก่อนซ่อม
    remediated_at = db.Column(db.DateTime, nullable=True) # วันที่ซ่อมเสร็จ
    remediated_at = db.Column(db.DateTime, nullable=True) # วันที่ซ่อมเสร็จ
    ms_remediated_status = db.Column(db.Boolean, server_default='0', nullable=False) # สถานะการซ่อม มส

    student = db.relationship('Student', backref=db.backref('course_grades', cascade="all, delete-orphan"))
    course = db.relationship('Course', backref=db.backref('student_grades', cascade="all, delete-orphan"))

    __table_args__ = (db.UniqueConstraint('student_id', 'course_id', name='_student_course_grade_uc'),)

    def __repr__(self):
        return f'<CourseGrade S:{self.student_id} C:{self.course_id}>'
        
class AdvisorAssessmentRecord(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    student_id = db.Column(db.Integer, db.ForeignKey('student.id'), nullable=False, index=True)
    semester_id = db.Column(db.Integer, db.ForeignKey('semester.id'), nullable=False, index=True)
    advisor_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False, index=True)
    
    status = db.Column(db.String(50), nullable=False, default='Draft', index=True) # e.g., Draft, Submitted to Head, Approved
    submitted_at = db.Column(db.DateTime, nullable=True)
    approved_at = db.Column(db.DateTime, nullable=True)
    
    student = db.relationship('Student', backref='advisor_assessment_records')
    semester = db.relationship('Semester')
    advisor = db.relationship('User')
    scores = db.relationship('AdvisorAssessmentScore', back_populates='record', cascade="all, delete-orphan")

    __table_args__ = (db.UniqueConstraint('student_id', 'semester_id', name='_student_semester_advisor_assessment_uc'),)

    def __repr__(self):
        return f'<AdvisorAssessmentRecord S:{self.student_id} Sem:{self.semester_id}>'

class AdvisorAssessmentScore(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    record_id = db.Column(db.Integer, db.ForeignKey('advisor_assessment_record.id'), nullable=False, index=True)
    topic_id = db.Column(db.Integer, db.ForeignKey('assessment_topic.id'), nullable=False, index=True)
    score_value = db.Column(db.Integer, nullable=False)
    
    record = db.relationship('AdvisorAssessmentRecord', back_populates='scores')
    topic = db.relationship('AssessmentTopic')

    __table_args__ = (db.UniqueConstraint('record_id', 'topic_id', name='_record_topic_advisor_score_uc'),)

    def __repr__(self):
        return f'<AdvisorAssessmentScore Record:{self.record_id} Topic:{self.topic_id}>'
            
@event.listens_for(GradeLevel, 'after_insert')
def create_grade_level_roles(mapper, connection, target):
    """
    Automatically creates an associated role when a new grade level is created.
    """
    session = db.session.object_session(target)
    if not session:
        return

    grade_id = target.id
    role_name = f"GRADE_HEAD_{grade_id}"
    role_desc = f"Head of Grade Level ID {grade_id}"

    if not session.query(Role).filter_by(name=role_name).first():
        new_role = Role(name=role_name, description=role_desc)
        session.add(new_role)

class RepeatCandidate(db.Model):
    """Stores students flagged for potential grade repetition pending review."""
    id = db.Column(db.Integer, primary_key=True)
    student_id = db.Column(db.Integer, db.ForeignKey('student.id'), nullable=False, index=True)
    previous_enrollment_id = db.Column(db.Integer, db.ForeignKey('enrollment.id'), nullable=False, index=True) # Enrollment from the year they failed
    academic_year_id_failed = db.Column(db.Integer, db.ForeignKey('academic_year.id'), nullable=False, index=True) # Academic year they failed in
    status = db.Column(db.String(50), nullable=False, default='Pending Advisor Review', index=True) # Workflow status
    advisor_notes = db.Column(db.Text, nullable=True)
    grade_head_notes = db.Column(db.Text, nullable=True)
    academic_notes = db.Column(db.Text, nullable=True)
    director_notes = db.Column(db.Text, nullable=True)
    final_decision = db.Column(db.String(50), nullable=True, index=True) # e.g., 'Repeat', 'Promote (Special Case)'
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    student = db.relationship('Student', backref='repeat_candidacies')
    previous_enrollment = db.relationship('Enrollment', backref='repeat_candidacy') # Use uselist=False if one-to-one
    academic_year = db.relationship('AcademicYear')

    # Ensure a student isn't flagged multiple times for the same failed year
    __table_args__ = (UniqueConstraint('student_id', 'academic_year_id_failed', name='_student_year_repeat_uc'),)

    def __repr__(self):
        return f'<RepeatCandidate S:{self.student_id} Year:{self.academic_year_id_failed}>'
    
@login.user_loader
def load_user(id):
    return User.query.get(int(id))