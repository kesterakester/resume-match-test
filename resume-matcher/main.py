
from fastapi import FastAPI, File, UploadFile, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pdfminer.high_level import extract_text
import spacy
from sklearn.feature_extraction.text import CountVectorizer
from sklearn.metrics.pairwise import cosine_similarity
import re
import io
import json

app = FastAPI()

# Allow CORS for frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Load NLP model
try:
    nlp = spacy.load("en_core_web_sm")
except:
    import subprocess
    subprocess.run(["python", "-m", "spacy", "download", "en_core_web_sm"])
    nlp = spacy.load("en_core_web_sm")

def extract_contact_info(text):
    email = re.findall(r'[\w\.-]+@[\w\.-]+', text)
    phone = re.findall(r'(\d{3}[-\.\s]??\d{3}[-\.\s]??\d{4}|\(\d{3}\)\s*\d{3}[-\.\s]??\d{4}|\d{3}[-\.\s]??\d{4})', text)
    return {
        "email": email[0] if email else None,
        "phone": phone[0] if phone else None
    }

def calculate_ats_score(text, resume_data):
    score = 0
    feedback = []
    breakdown = {"contact_info": 0, "structure": 0, "content_length": 0, "keywords": 0}

    # 1. Contact Info (20 pts)
    if resume_data["email"]:
        score += 10
        breakdown["contact_info"] += 10
    else:
        feedback.append("Missing email address")
    
    if resume_data["phone"]:
        score += 10
        breakdown["contact_info"] += 10
    else:
        feedback.append("Missing phone number")

    # 2. Content Length (20 pts)
    word_count = len(text.split())
    if 400 <= word_count <= 1000:
        score += 20
        breakdown["content_length"] += 20
    elif word_count < 400:
        score += 10
        breakdown["content_length"] += 10
        feedback.append("Resume is too short. Add more details about your experience.")
    else:
        score += 10
        breakdown["content_length"] += 10
        feedback.append("Resume might be too long. Try to keep it concise.")

    # 3. Structure & Sections (30 pts)
    # Simple check for common headers
    sections = ["experience", "education", "skills", "projects", "summary", "profile"]
    found_sections = [s for s in sections if s in text.lower()]
    
    section_score = min(len(found_sections) * 5, 30)
    score += section_score
    breakdown["structure"] += section_score
    
    missing_sections = [s for s in sections if s not in text.lower()]
    if missing_sections:
        feedback.append(f"Consider adding these sections: {', '.join(missing_sections)}")

    # 4. Action Verbs & Keywords (30 pts)
    # Basic check for action verbs
    action_verbs = ["managed", "developed", "led", "created", "designed", "implemented", "analyzed", "collaborated"]
    found_verbs = [v for v in action_verbs if v in text.lower()]
    
    keyword_score = min(len(found_verbs) * 4, 30)
    score += keyword_score
    breakdown["keywords"] += keyword_score
    
    if len(found_verbs) < 3:
        feedback.append("Use more strong action verbs (e.g., Managed, Developed, Led).")

    return {
        "total_score": score,
        "breakdown": breakdown,
        "feedback": feedback
    }

@app.post("/api/parser")
async def parse_resume(file: UploadFile = File(...)):
    if not file.filename.endswith('.pdf'):
        raise HTTPException(status_code=400, detail="Only PDF files are supported")
    
    content = await file.read()
    
    try:
        # Extract text using pdfminer
        text = extract_text(io.BytesIO(content))
        
        # Extract basic info
        contact = extract_contact_info(text)
        
        # Calculate Score
        scoring = calculate_ats_score(text, contact)
        
        return {
            "resume": {
                "profile": {
                    "email": contact["email"],
                    "phone": contact["phone"]
                },
                "text": text[:500] + "..." # Preview
            },
            "score": {
                "totalScore": scoring["total_score"],
                "breakdown": {
                    "contactInfo": scoring["breakdown"]["contact_info"],
                    "education": scoring["breakdown"]["structure"], # Mapping structure to education category equivalent
                    "experience": scoring["breakdown"]["content_length"],
                    "skills": scoring["breakdown"]["keywords"],
                    "summary": 0
                },
                "feedback": scoring["feedback"]
            }
        }
        
    except Exception as e:
        print(f"Error parsing PDF: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to parse PDF: {str(e)}")

@app.get("/health")
def health_check():
    return {"status": "ok"}
