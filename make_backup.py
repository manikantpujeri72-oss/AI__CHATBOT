import shutil
import os
import datetime

ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
backup_name = f"backup_{ts}"
backup_path = os.path.join(r"D:\MINI Project", backup_name)
os.makedirs(backup_path, exist_ok=True)

files_to_copy = [
    "app.py",
    "hybrid_rag.py",
    "faculty_lookup.py",
    "ui_cards.py",
    "hod_manager.py",
    "hod_verified.json",
    "faculty_profiles_new.json",
    "department_overviews.json",
    "rag.py",
    "source_config.py",
]

for f in files_to_copy:
    if os.path.exists(f):
        shutil.copy2(f, os.path.join(backup_path, f))

print(f"Backup created at: {backup_path}")

