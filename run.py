import uvicorn
import os
import sys

# Ensure the project root directory is in the python path
project_root = os.path.dirname(os.path.abspath(__file__))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

if __name__ == "__main__":
    print("Starting Tourism Inquiry Intelligence System...")
    # We specify the app string. Since project_root is in sys.path, 
    # Python/Uvicorn can resolve "src.main:app" correctly.
    uvicorn.run("src.main:app", host="127.0.0.1", port=8000, reload=True)#لو غيرت اي حرف بالكود لحالو بعمل ريستارت
