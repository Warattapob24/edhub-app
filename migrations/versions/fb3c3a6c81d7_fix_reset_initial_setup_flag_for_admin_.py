"""Fix: Reset initial_setup flag for Admin-created users

Revision ID: fb3c3a6c81d7
Revises: 4cd3ee4b95a5
Create Date: 2025-11-13 17:17:44.211683

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'fb3c3a6c81d7'
down_revision = '4cd3ee4b95a5'
branch_labels = None
depends_on = None


def upgrade():
    # --- [FIX] ---
    # ค้นหาผู้ใช้ทุกคนที่ "ต้องเปลี่ยนรหัสผ่าน" (Admin สร้างไว้)
    # และ "รีเซ็ต" สถานะ initial_setup_complete ให้เป็น false
    # เพื่อบังคับให้พวกเขาไปหน้า setup (แก้บั๊กจาก Migration ก่อนหน้า)
    op.execute('UPDATE "user" SET initial_setup_complete = false WHERE must_change_password = true')
    # --- [END FIX] ---


def downgrade():
    # --- [FIX] ---
    # (คำสั่งย้อนกลับ คือตั้งค่าให้เป็น true ตามบั๊กเดิม)
    op.execute('UPDATE "user" SET initial_setup_complete = true WHERE must_change_password = true')
    # --- [END FIX] ---