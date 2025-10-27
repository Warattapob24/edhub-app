from wtforms_sqlalchemy.fields import QuerySelectMultipleField

class PatchedQuerySelectMultipleField(QuerySelectMultipleField):
    """
    ฟิลด์แก้ไขปัญหาการ render multiple select ของ WTForms-SQLAlchemy
    """
    def pre_validate(self, form):
        # ข้ามการ validate ค่า ถ้าเป็น empty
        if self.data:
            super().pre_validate(form)
