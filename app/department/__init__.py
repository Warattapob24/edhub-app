# FILE: app/department/__init__.py
from flask import Blueprint

# เปลี่ยนชื่อ Blueprint เป็น 'department'
bp = Blueprint('department', __name__, template_folder='../templates/department')

from app.department import routes