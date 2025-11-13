"""Fix: Set existing users to initial_setup_complete=true

Revision ID: 4cd3ee4b95a5
Revises: 1d9d63a4c2da
Create Date: 2025-11-13 16:59:36.483412

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '4cd3ee4b95a5'
down_revision = '1d9d63a4c2da'
branch_labels = None
depends_on = None


def upgrade():
    # --- [FIX] ---
    # เราจะตั้งค่าให้ผู้ใช้ "ทุกคน" ที่มีอยู่ในปัจจุบัน
    # มีสถานะ initial_setup_complete = true (เพราะถือเป็นผู้ใช้เก่า)
    # (ใช้ 'true' สำหรับ PostgreSQL)
    op.execute('UPDATE "user" SET initial_setup_complete = true')
    # --- [END FIX] ---


def downgrade():
    # --- [FIX] ---
    # (คำสั่งย้อนกลับ คือตั้งค่าให้เป็น false เหมือนเดิม)
    op.execute('UPDATE "user" SET initial_setup_complete = false')
    # --- [END FIX] ---