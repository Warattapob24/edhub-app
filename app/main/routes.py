# FILE: app/main/routes.py
from flask import abort, current_app, g, jsonify, redirect, url_for
from flask_login import login_required, current_user
from app.main import bp
from app.models import Notification, Setting
from app import db 

@bp.route('/')
@bp.route('/index')
@login_required
def index():
    # สามารถ redirect ไปยัง hub ได้เลย หรือจะสร้างเป็นหน้า index หลักก็ได้
    return redirect(url_for('main.dashboard'))

@bp.route('/dashboard')
@login_required
def dashboard():
    current_app.logger.info(f"Checking user roles: {[role.name for role in current_user.roles]}")

    # ตรวจสอบสิทธิ์ตามลำดับความสำคัญ
    if current_user.has_role('Admin'):
        return redirect(url_for('admin.index')) # หรือ url_for('admin.dashboard')
    elif current_user.has_role('DepartmentHead'):
        return redirect(url_for('department.dashboard'))
    elif current_user.has_role('Teacher'):
        return redirect(url_for('teacher.todays_classroom'))
    elif current_user.has_role('ผู้อำนวยการ'): # Check for Director role first
        return redirect(url_for('director.dashboard'))
    elif current_user.has_role('Academic'):
        return redirect(url_for('academic.dashboard'))    
    
    # หากไม่มีบทบาทพิเศษ ให้กลับไปหน้าแรก
    # ในที่นี้สมมติว่าครูคือบทบาทพื้นฐาน
    return redirect(url_for('teacher.todays_classroom'))

@bp.route('/notifications')
@login_required
def get_notifications():
    notifications = Notification.query.filter_by(user_id=current_user.id, is_read=False).order_by(Notification.created_at.desc()).limit(10).all()

    notif_data = [{
        'id': n.id,
        'title': n.title,
        'message': n.message,
        'url': n.url,
        'timestamp': n.created_at.strftime('%d %b %Y, %H:%M') if n.created_at else ''
    } for n in notifications]

    return jsonify(notif_data)

@bp.route('/api/notifications/<int:notification_id>/mark-read', methods=['POST'])
@login_required
def mark_notification_as_read(notification_id):
    
    notification = db.session.get(Notification, notification_id)
    if not notification or notification.user_id != current_user.id:
        abort(404)
    
    notification.is_read = True
    db.session.commit()
    return jsonify({'status': 'success'})

@bp.before_app_request  # หรือ @main.before_request ขึ้นอยู่กับโครงสร้างของคุณ
def load_global_settings():
    # ดึงค่าเวอร์ชัน favicon จากฐานข้อมูล
    favicon_setting = Setting.query.filter_by(key='favicon_version').first()
    g.favicon_version = favicon_setting.value if favicon_setting else '1' # ถ้าไม่เจอก็ใช้ '1'