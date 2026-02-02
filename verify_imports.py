
import sys
import traceback

try:
    print("Importing smartflow.io.db...")
    from smartflow.io import db
    print("Successfully imported db.")
    if hasattr(db, 'insert_run'):
        print("db.insert_run exists.")
    else:
        print("ERROR: db.insert_run does NOT exist.")
        print("db contents:", dir(db))

    print("\nImporting smartflow.ui.views.results_view...")
    from smartflow.ui.views import results_view
    print("Successfully imported results_view.")
    
except Exception:
    traceback.print_exc()
