# path: restore.py
import json
from app import create_app
from app import db
from app.models import User, Role, LearningArea, GradeLevel # Import ทุก Model ที่เกี่ยวข้อง

def restore_data(filename):
    """
    Clears the database and restores data from a JSON backup file.
    """
    app = create_app()
    with app.app_context():
        print(f"--- Starting database restore from '{filename}' ---")

        try:
            # 1. Read the JSON backup file
            with open(filename, 'r', encoding='utf-8') as f:
                data = json.load(f)
            print("SUCCESS: Backup file read successfully.")

            # 2. Clear existing data in the correct order (from child to parent)
            print("[STEP 1] Clearing existing data...")
            # This is a simplified clearing order. For complex schemas,
            # you might need to disable foreign key checks temporarily.
            db.session.execute('DELETE FROM user_roles') # Clear association table
            User.query.delete()
            Role.query.delete()
            LearningArea.query.delete()
            GradeLevel.query.delete()
            db.session.commit()
            print("  - All old data cleared.")

            # 3. Restore data, starting with tables that others depend on
            print("[STEP 2] Restoring data...")
            
            # Restore Roles first
            if 'roles' in data:
                for role_name in data['roles']:
                    db.session.add(Role(name=role_name))
                db.session.commit()
                print(f"  - {len(data['roles'])} Roles restored.")

            # Restore Learning Areas
            if 'learning_areas' in data:
                for area_name in data['learning_areas']:
                    db.session.add(LearningArea(name=area_name))
                print(f"  - {len(data['learning_areas'])} Learning Areas restored.")
                
            # Restore Grade Levels
            if 'grade_levels' in data:
                for grade_name in data['grade_levels']:
                    db.session.add(GradeLevel(name=grade_name))
                print(f"  - {len(data['grade_levels'])} Grade Levels restored.")
            
            db.session.commit()

            # Restore Users and their relationships
            if 'users' in data:
                for user_data in data['users']:
                    new_user = User(
                        username=user_data['username'],
                        full_name=user_data['full_name']
                    )
                    # IMPORTANT: We set a default password as hashes are not backed up
                    new_user.set_password('123456') 
                    
                    # Link roles
                    if 'roles' in user_data:
                        for role_name in user_data['roles']:
                            role_obj = Role.query.filter_by(name=role_name).first()
                            if role_obj:
                                new_user.roles.append(role_obj)
                    
                    db.session.add(new_user)
                print(f"  - {len(data['users'])} Users restored.")

            # 4. Final commit
            db.session.commit()
            print("\n--- Database restore finished successfully! ---")

        except FileNotFoundError:
            print(f"ERROR: Backup file '{filename}' not found.")
        except Exception as e:
            db.session.rollback()
            print(f"AN ERROR OCCURRED: {e}")
            print("INFO: Database transaction has been rolled back.")
