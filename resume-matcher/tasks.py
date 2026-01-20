
import os
import re
import io
import json
import base64
import spacy
from typing import Dict, Any, List
from pdfminer.high_level import extract_text
from sklearn.feature_extraction.text import CountVectorizer
from openai import OpenAI
from supabase import create_client, Client
from celery_app import app

# Load NLP model globally to reuse across tasks
try:
    nlp = spacy.load("en_core_web_sm")
except:
    import subprocess
    subprocess.run(["python", "-m", "spacy", "download", "en_core_web_sm"])
    nlp = spacy.load("en_core_web_sm")

# Supabase Client
supabase_url = os.environ.get("SUPABASE_URL")
supabase_key = os.environ.get("SUPABASE_KEY")

def get_supabase() -> Client:
    if not supabase_url or not supabase_key:
        print("Warning: Supabase credentials not found.")
        return None
    return create_client(supabase_url, supabase_key)

def extract_profile_info(text, nlp_doc):
    email = re.findall(r'[\w\.-]+@[\w\.-]+', text)
    phone = re.findall(r'(\d{3}[-\.\s]??\d{3}[-\.\s]??\d{4}|\(\d{3}\)\s*\d{3}[-\.\s]??\d{4}|\d{3}[-\.\s]??\d{4})', text)
    
    person_name = None
    location = None
    
    for ent in nlp_doc.ents:
        if ent.label_ == "PERSON" and not person_name:
            person_name = ent.text
        if ent.label_ == "GPE" and not location:
            location = ent.text
            
    return {
        "email": email[0] if email else None,
        "phone": phone[0] if phone else None,
        "name": person_name,
        "location": location
    }

def extract_keywords_basic(text, n=15):
    try:
        vectorizer = CountVectorizer(stop_words='english', max_features=n, ngram_range=(1, 2))
        X = vectorizer.fit_transform([text])
        keywords = vectorizer.get_feature_names_out()
        return list(keywords)
    except:
        return []

def calculate_rule_based_score(text, resume_data):
    score = 0
    feedback = []
    breakdown = {"contact_info": 0, "structure": 0, "content_length": 0, "keywords": 0, "impact": 0}

    # 1. Contact Info
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

    # 2. Content Length
    word_count = len(text.split())
    if 400 <= word_count <= 1000:
        score += 20
        breakdown["content_length"] += 20
    elif word_count < 400:
        score += 10
        breakdown["content_length"] += 10
        feedback.append("Resume is too short.")
    else:
        score += 10
        breakdown["content_length"] += 10
        feedback.append("Resume might be too long.")

    # 3. Structure
    sections = ["experience", "education", "skills", "projects", "summary", "profile"]
    found_sections = [s for s in sections if s in text.lower()]
    section_score = min(len(found_sections) * 4, 20)
    score += section_score
    breakdown["structure"] += section_score
    
    missing_sections = [s for s in sections if s not in text.lower()]
    if missing_sections:
        feedback.append(f"Consider adding: {', '.join(missing_sections)}")

    # 4. Keywords
    action_verbs = ["managed", "developed", "led", "created", "designed", "implemented", "analyzed"]
    found_verbs = [v for v in action_verbs if v in text.lower()]
    keyword_score = min(len(found_verbs) * 2, 20)
    score += keyword_score
    breakdown["keywords"] += keyword_score
    
    if len(found_verbs) < 5:
        feedback.append("Use more strong action verbs.")

    # 5. Impact
    metrics = re.findall(r'(\d+%|\$\d+|\d+\s\+)', text)
    impact_words = ["increased", "decreased", "reduced", "improved", "grew"]
    found_impact_words = [w for w in impact_words if w in text.lower()]
    
    if len(metrics) >= 3 or (len(metrics) > 0 and len(found_impact_words) > 0):
        score += 20
        breakdown["impact"] += 20
    elif len(metrics) > 0:
        score += 10
        breakdown["impact"] += 10
        feedback.append("Quantify more results.")
    else:
        feedback.append("Add quantifiable results!")

    return {
        "total_score": score,
        "breakdown": breakdown,
        "feedback": feedback
    }

def get_ai_analysis(text):
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        return None

    client = OpenAI(api_key=api_key)
    prompt = f"""
    You are an expert ATS. Analyze:
    {text[:4000]}
    Provide JSON:
    {{
        "total_score": <0-100>,
        "breakdown": {{ "contact_info": <0-20>, "structure": <0-20>, "content_length": <0-20>, "keywords": <0-20>, "impact": <0-20> }},
        "feedback": [<strings>],
        "extracted_keywords": [<strings>],
        "soft_skills": [<strings>],
        "missing_skills": [<strings>],
        "predicted_roles": [<strings>]
    }}
    """
    try:
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": prompt}],
            response_format={"type": "json_object"}
        )
        return json.loads(response.choices[0].message.content)
    except Exception as e:
        print(f"AI Error: {e}")
        return None

@app.task
def parse_resume_task(file_content_base64: str, filename: str, user_id: str = None):
    try:
        content = base64.b64decode(file_content_base64)
        text = extract_text(io.BytesIO(content))
        
        doc = nlp(text)
        profile = extract_profile_info(text, doc)
        rule_score = calculate_rule_based_score(text, profile)
        ai_score = get_ai_analysis(text)
        
        final_scoring = rule_score
        keywords = extract_keywords_basic(text)
        soft_skills = []
        predicted_roles = []

        if ai_score:
            final_scoring = {
                "total_score": ai_score.get("total_score", rule_score["total_score"]),
                "breakdown": ai_score.get("breakdown", rule_score["breakdown"]),
                "feedback": ai_score.get("feedback", rule_score["feedback"])
            }
            if "missing_skills" in ai_score:
                final_scoring["feedback"].append(f"Recommended Skills: {', '.join(ai_score['missing_skills'][:5])}")
            if "extracted_keywords" in ai_score:
                keywords = ai_score["extracted_keywords"]
            if "soft_skills" in ai_score:
                soft_skills = ai_score["soft_skills"]
            if "predicted_roles" in ai_score:
                predicted_roles = ai_score["predicted_roles"]

        result = {
            "resume": {
                "profile": profile,
                "text": text[:500] + "..."
            },
            "score": {
                "totalScore": final_scoring["total_score"],
                "breakdown": {
                    "contactInfo": final_scoring["breakdown"].get("contact_info", 0),
                    "structure": final_scoring["breakdown"].get("structure", 0),
                    "experience": final_scoring["breakdown"].get("content_length", 0),
                    "keywords": final_scoring["breakdown"].get("keywords", 0),
                    "impact": final_scoring["breakdown"].get("impact", 0)
                },
                "feedback": final_scoring["feedback"]
            },
            "keywords": keywords,
            "softSkills": soft_skills,
            "predictedRoles": predicted_roles
        }

        # Save to Supabase if user_id is provided
        if user_id:
            db = get_supabase()
            if db:
                db.table('resume_scores').insert({
                    'user_id': user_id,
                    'resume_name': filename,
                    'total_score': final_scoring["total_score"],
                    'score_details': result
                }).execute()
                
                # Also update profile last upload time
                db.table('profiles').update({
                    'last_resume_upload_at': 'now()'
                }).eq('id', user_id).execute()

        return result

    except Exception as e:
        print(f"Task Failed: {e}")
        return {"error": str(e)}
