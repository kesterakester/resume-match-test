
from fastapi import FastAPI, File, UploadFile, HTTPException, Form
from fastapi.middleware.cors import CORSMiddleware
import base64
from tasks import parse_resume_task, app as celery_app, get_supabase
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
    if user_id:
        try:
            supabase = get_supabase()
            if supabase:
                # Check user role
                user_res = supabase.table('profiles').select('role').eq('id', user_id).execute()
                is_admin = False
                if user_res.data and len(user_res.data) > 0:
                    role = user_res.data[0].get('role')
                    if role == 'admin':
                        is_admin = True
                
                if not is_admin:
                    # Generic User - Check Limit
                    FREE_LIMIT = 2
                    # Count existing resumes
                    usage_res = supabase.table('resume_scores').select('*', count='exact').eq('user_id', user_id).execute()
                    current_usage = usage_res.count or 0
                    
                    if current_usage >= FREE_LIMIT:
                        raise HTTPException(
                            status_code=403,
                            detail=f"Free limit reached ({FREE_LIMIT} resumes). Upgrade to Admin for unlimited accesses."
                        )
        except HTTPException:
            raise
        except Exception as e:
            print(f"Limit check error: {e}")
            # Proceed if check fails to avoid blocking service on minor DB glitches, or block?
            # Safer to log and proceed for now, or could block. 
            pass

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
    import os
    import redis
    
    status = {
        "api": "ok",
        "supabase_url_set": bool(os.environ.get("SUPABASE_URL")),
        "supabase_key_set": bool(os.environ.get("SUPABASE_KEY")),
        "openai_key_set": bool(os.environ.get("OPENAI_API_KEY")),
    }
    
    # Check Redis
    try:
        r = redis.Redis(host='localhost', port=6379, db=0)
        r.ping()
        status["redis"] = "ok"
    except Exception as e:
        status["redis"] = f"error: {str(e)}"
    
    # Check Supabase connection
    try:
        db = get_supabase()
        if db:
            db.table('profiles').select('id').limit(1).execute()
            status["supabase"] = "ok"
        else:
            status["supabase"] = "credentials_missing"
    except Exception as e:
        status["supabase"] = f"error: {str(e)}"
    
    return status
