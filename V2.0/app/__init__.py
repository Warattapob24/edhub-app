# path: app/__init__.py

from flask import Flask
from config import Config
from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate
from flask_login import LoginManager
from flask_wtf.csrf import CSRFProtect

# 1. สร้าง Instance ของ Extension ไว้ก่อน
db = SQLAlchemy()
migrate = Migrate()
login_manager = LoginManager()
csrf = CSRFProtect()
login_manager.login_view = 'main.login' # หรือ 'auth.login' ตามที่คุณตั้งชื่อ Blueprint

# 2. สร้างฟังก์ชัน create_app
def create_app(config_class=Config):
    app = Flask(__name__)
    app.config.from_object(config_class)

    app.jinja_env.add_extension('jinja2.ext.do')

    # 3. ผูก Extension เข้ากับ app ภายในฟังก์ชัน
    db.init_app(app)
    migrate.init_app(app, db)
    login_manager.init_app(app)
    csrf.init_app(app)

    # 4. Import และ Register Blueprints ภายในฟังก์ชัน
    from app.admin.routes import admin_bp
    app.register_blueprint(admin_bp, url_prefix='/admin')

    from app.main.routes import main_bp
    app.register_blueprint(main_bp)

    from app.department.routes import department_bp
    app.register_blueprint(department_bp, url_prefix='/department')   

    from app.teacher.routes import teacher_bp
    app.register_blueprint(teacher_bp, url_prefix='/teacher') 

    return app

# 5. [สำคัญที่สุด] Import models ไว้ล่างสุดของไฟล์
# เพื่อให้แน่ใจว่า db ถูกสร้างและตั้งค่าเรียบร้อยแล้วก่อนที่ models.py จะถูกอ่าน
from app import models