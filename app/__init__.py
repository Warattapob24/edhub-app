# FILE: app/__init__.py
import re
from markupsafe import Markup
from flask import Flask, redirect, url_for
from config import Config
from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate
from flask_login import LoginManager, current_user
from flask_wtf.csrf import CSRFProtect
from flask_moment import Moment

# 1. ประกาศ Extensions โดยยังไม่ผูกกับ app
db = SQLAlchemy()
migrate = Migrate()
login = LoginManager()
moment = Moment()
login.login_view = 'auth.login' # We will create the auth blueprint in the future
login.login_message = 'กรุณาเข้าสู่ระบบเพื่อใช้งาน'

csrf = CSRFProtect()

def create_app(config_class=Config):
    app = Flask(__name__)
    app.config.from_object(config_class)
    app.config['JSON_AS_ASCII'] = False

    # 2. ผูก Extensions กับ app ที่สร้างขึ้น
    db.init_app(app)
    migrate.init_app(app, db)
    login.init_app(app)
    csrf.init_app(app)
    moment.init_app(app)

    @app.template_filter('nl2br')
    def nl2br_filter(text_to_convert):
        """
        A custom Jinja2 filter to convert newline characters to <br> tags.
        """
        if text_to_convert:
            # Use Markup to ensure the output is treated as safe HTML
            return Markup(re.sub(r'(\r\n|\n|\r)', '<br>', str(text_to_convert)))
        return ''
    
    # เปิดใช้งาน 'do' extension เพื่อให้สามารถใช้ {% do ... %} ใน template ได้
    app.jinja_env.add_extension('jinja2.ext.do')    

    # เพิ่มการลงทะเบียน Error Handlers Blueprint
    from app.errors import bp as errors_bp
    app.register_blueprint(errors_bp)

    # เพิ่มการลงทะเบียน Admin Blueprint
    from app.admin import bp as admin_bp
    app.register_blueprint(admin_bp, url_prefix='/admin')

    # เพิ่มการลงทะเบียน Teacher Blueprint
    from app.teacher import bp as teacher_bp
    app.register_blueprint(teacher_bp, url_prefix='/teacher')

    # เพิ่มการลงทะเบียน Auth Blueprint
    from app.auth import bp as auth_bp
    app.register_blueprint(auth_bp, url_prefix='/auth')

    # เปลี่ยนจาก department_head เป็น department
    from app.department import bp as department_bp
    app.register_blueprint(department_bp, url_prefix='/department')

    # เพิ่มการลงทะเบียน Academic Blueprint
    from app.academic import bp as academic_bp
    app.register_blueprint(academic_bp, url_prefix='/academic')

    # เพิ่มการลงทะเบียน director
    from app.director import bp as director_bp
    app.register_blueprint(director_bp, url_prefix='/director')  

    # เพิ่มการลงทะเบียน Advisor Blueprint
    from app.advisor import bp as advisor_bp
    app.register_blueprint(advisor_bp, url_prefix='/advisor')      

    # เพิ่มการลงทะเบียน grade_level_head Blueprint
    from app.grade_level_head import bp as grade_level_head_bp
    app.register_blueprint(grade_level_head_bp, url_prefix='/grade_level_head')      
    
    # เพิ่มการลงทะเบียน Student Blueprint
    from app.student import bp as student_bp
    app.register_blueprint(student_bp, url_prefix='/student')

    # Register other blueprints in the future
    from app.main import bp as main_bp
    app.register_blueprint(main_bp)

    # 4. กำหนด Route และ Context Processors
    @app.route('/')
    def index():
        return redirect(url_for('auth.login'))

    @app.context_processor
    def inject_current_semester():
        from app.models import Semester # Import inside the function
        current_semester = Semester.query.filter_by(is_current=True).first()
        return dict(g_current_semester=current_semester)
        
    @app.context_processor
    def inject_notifications():
        if current_user.is_authenticated:
            # Note: We need to import the Notification model within the function
            # to avoid circular import issues during app initialization.
            from app.models import Notification
            count = Notification.query.filter_by(user_id=current_user.id, is_read=False).count()
            return dict(g_unread_notifications_count=count)
        return dict(g_unread_notifications_count=0)
    
    # --- [THE FIX] ---
    # นี่คือการแก้ปัญหาสำหรับ Render Free Tier
    # เราจะสั่งให้ SQLAlchemy สร้างตารางที่ยังไม่มี (ถ้ามีอยู่แล้วมันจะข้ามไป)
    # โดยไม่สนใจประวัติ Migration (Alembic) ที่พังไปแล้ว
    with app.app_context():
        # เราต้อง import models ที่นี่เพื่อให้ SQLAlchemy รู้จักตารางทั้งหมด
        # (แม้ว่า blueprints ต่างๆ จะ import ไปแล้วก็ตาม นี่คือการการันตี)
        from app import models 
        db.create_all()
    # --- [END FIX] ---

    return app