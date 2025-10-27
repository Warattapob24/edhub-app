from flask import Flask, session
from config import Config
from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate
from flask_login import LoginManager

db = SQLAlchemy()
migrate = Migrate()
login = LoginManager()
login.login_view = 'auth.login'
login.login_message = 'กรุณาเข้าสู่ระบบเพื่อเข้าถึงหน้านี้'

def create_app(config_class=Config):
    """
    สร้างและกำหนดค่า Flask Application (Application Factory)
    """
    app = Flask(__name__)
    app.config.from_object(config_class)

    db.init_app(app)
    migrate.init_app(app, db)
    login.init_app(app)

    # --- ลงทะเบียน Blueprints ---
    from app.main import bp as main_bp
    app.register_blueprint(main_bp)

    from app.auth import bp as auth_bp
    app.register_blueprint(auth_bp, url_prefix='/auth')

    from app.admin import bp as admin_bp
    app.register_blueprint(admin_bp, url_prefix='/admin')
    
    from app.course import bp as course_bp
    app.register_blueprint(course_bp, url_prefix='/course')

    from app.advisor import bp as advisor_bp
    app.register_blueprint(advisor_bp, url_prefix='/advisor')
    
    from app.manager import bp as manager_bp
    app.register_blueprint(manager_bp, url_prefix='/manager')
    
    from app.executive import bp as executive_bp
    app.register_blueprint(executive_bp, url_prefix='/executive')

    from app.student import bp as student_bp
    app.register_blueprint(student_bp, url_prefix='/student')

    # --- ย้ายโค้ดทั้งหมดเข้ามาไว้ในฟังก์ชัน ---
    from app.models import User, Student

    @login.user_loader
    def load_user(user_id):
        user_type = session.get('user_type', 'user') # ให้ 'user' เป็นค่า default
        if user_type == 'student':
            return Student.query.get(int(user_id))
        else: # user, admin, manager, etc.
            return User.query.get(int(user_id))

    from app.course.routes import to_thai_numerals
    app.jinja_env.globals.update(to_thai_numerals=to_thai_numerals)

    # บรรทัดนี้ต้องอยู่สุดท้ายของฟังก์ชันเสมอ
    return app