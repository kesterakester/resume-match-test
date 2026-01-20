
from fastapi import FastAPI, File, UploadFile, HTTPException, Form
from fastapi.middleware.cors import CORSMiddleware
import base64
from tasks import parse_resume_task, app as celery_app
from celery.result import AsyncResult

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.post("/api/parser")
async def parse_resume(
    file: UploadFile = File(...),
    user_id: str = Form(None)
):
    if not file.filename.endswith('.pdf'):
        raise HTTPException(status_code=400, detail="Only PDF files are supported")
    
    content = await file.read()
    content_b64 = base64.b64encode(content).decode('utf-8')
    
    # Offload to Celery
    task = parse_resume_task.delay(content_b64, file.filename, user_id)
    
    return {
        "task_id": task.id,
        "status": "processing",
        "message": "Resume queued for analysis. Results will be saved automatically."
    }

@app.get("/api/tasks/{task_id}")
async def get_task_result(task_id: str):
    task_result = AsyncResult(task_id, app=celery_app)
    
    if task_result.state == 'PENDING':
        return {"status": "pending"}
    elif task_result.state == 'SUCCESS':
        return {"status": "completed", "result": task_result.result}
    elif task_result.state == 'FAILURE':
        return {"status": "failed", "error": str(task_result.result)}
    else:
        return {"status": task_result.state}

@app.get("/health")
def health_check():
    return {"status": "ok"}
