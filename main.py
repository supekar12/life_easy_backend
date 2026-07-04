import os
import json
from datetime import datetime
from typing import Optional, List, Dict, Any

from fastapi import FastAPI, Depends, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session
from pydantic import BaseModel, Field
from dotenv import load_dotenv

# Database imports
from database import engine, Base, get_db
import models

# Load environment variables
load_dotenv()

# Initialize Database tables
Base.metadata.create_all(bind=engine)

app = FastAPI(title="Life Easy AI Agent API", version="1.0.0")

# Enable CORS — allows any origin (required for Vercel & Railway cross-domain requests)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Initialize Google Gemini SDK
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
gemini_available = True
client = None

if not GEMINI_API_KEY:
    print("WARNING: GEMINI_API_KEY is not set in environment or .env. Running in MOCK mode.")
    gemini_available = False
else:
    try:
        from google import genai
        from google.genai import types
        # Initialize the client
        client = genai.Client(api_key=GEMINI_API_KEY)
    except ImportError:
        print("WARNING: google-genai library not installed or import failed. Running in MOCK mode.")
        gemini_available = False
    except Exception as e:
        print(f"WARNING: Failed to initialize Gemini Client: {e}. Running in MOCK mode.")
        gemini_available = False

# --- Pydantic Schemas for Requests and Responses ---

class ChatRequest(BaseModel):
    message: str

class ExtractedEntities(BaseModel):
    # B.Tech Assignments
    title: Optional[str] = None
    course: Optional[str] = None
    deadline: Optional[str] = None
    description: Optional[str] = None

    # Program Schedules (Gemini / McKinsey)
    program_name: Optional[str] = None
    event_title: Optional[str] = None
    event_date: Optional[str] = None
    event_description: Optional[str] = None

    # Workouts
    exercise: Optional[str] = None
    sets: Optional[int] = None
    reps: Optional[int] = None
    weight: Optional[float] = None
    personal_record: Optional[bool] = None

    # Story Drafts
    chapter_number: Optional[int] = None
    title_draft: Optional[str] = None
    content: Optional[str] = None
    brainstorm_notes: Optional[str] = None
    status: Optional[str] = None

    # Custom categories
    session_name: Optional[str] = None
    custom_title: Optional[str] = None
    custom_description: Optional[str] = None

class IntentClassification(BaseModel):
    category: str
    action: str
    entities: ExtractedEntities = Field(default_factory=ExtractedEntities)
    suggested_response: str

class ChatResponse(BaseModel):
    response: str
    category: str
    action: str
    entities: ExtractedEntities
    database_updated: bool
    data: Optional[Any] = None

# --- B.Tech Assignments Schemas ---
class AssignmentCreate(BaseModel):
    title: str
    description: Optional[str] = None
    course: str
    deadline: datetime
    status: str = "Pending"

class AssignmentUpdate(BaseModel):
    status: Optional[str] = None
    deadline: Optional[datetime] = None

class AssignmentResponse(AssignmentCreate):
    id: int
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True

# --- Program Schedule Schemas ---
class ProgramScheduleCreate(BaseModel):
    program_name: str  # 'Gemini Student Ambassador' or 'McKinsey Forward'
    event_title: str
    event_description: Optional[str] = None
    event_date: datetime
    status: str = "Scheduled"

class ScheduleUpdate(BaseModel):
    status: Optional[str] = None
    event_date: Optional[datetime] = None

class ProgramScheduleResponse(ProgramScheduleCreate):
    id: int
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True

# --- Workout Log Schemas ---
class WorkoutLogCreate(BaseModel):
    exercise: str
    sets: int
    reps: int
    weight: float
    personal_record: bool = False

class WorkoutLogResponse(WorkoutLogCreate):
    id: int
    logged_at: datetime

    class Config:
        from_attributes = True

# --- Story Draft Schemas ---
class StoryDraftCreate(BaseModel):
    chapter_number: Optional[int] = None
    title: str
    content: Optional[str] = None
    brainstorm_notes: Optional[str] = None
    status: str = "Draft"

class StoryDraftResponse(StoryDraftCreate):
    id: int
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


# --- User & Profile Schemas ---
class UserRegister(BaseModel):
    username: str
    email: str
    password: str

class UserLogin(BaseModel):
    email_or_username: str
    password: str

class ProfileUpdate(BaseModel):
    age: Optional[int] = None
    gender: Optional[str] = None
    birthdate: Optional[str] = None
    profile_image: Optional[str] = None

class ProfileResponse(BaseModel):
    username: str
    email: str
    age: Optional[int] = None
    gender: Optional[str] = None
    birthdate: Optional[str] = None
    profile_image: Optional[str] = None

    class Config:
        from_attributes = True


# --- Session Category Schemas ---
class SessionCategoryCreate(BaseModel):
    name: str
    type: str  # "Professional" or "Personal"

class SessionCategoryResponse(BaseModel):
    id: int
    name: str
    type: str
    created_at: datetime

    class Config:
        from_attributes = True

# --- Custom Record Schemas ---
class CustomRecordCreate(BaseModel):
    title: str
    description: Optional[str] = None
    status: str = "Pending"

class CustomRecordResponse(BaseModel):
    id: int
    category_id: int
    title: str
    description: Optional[str] = None
    status: str
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True

class CustomRecordUpdate(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    status: Optional[str] = None



# --- Gemini Helper Functions ---

SYSTEM_PROMPT = """You are the backend Agentic Router for a 'Life Concierge' AI. Your task is to analyze the user's chat input and determine:
1. Category: 'Professional' (B.Tech assignments, presentation deadlines, Gemini Student Ambassador, McKinsey Forward, or any user-created professional categories), 'Personal' (strength training logs, exercises, reps, weight, chapters/brainstorming notes for the story "The Unstoppable", or any user-created personal categories), or 'General' (general chit-chat, greetings, questions that do not specify professional/personal logging).
2. Action: Identify what they want to do. Options:
   - 'create_assignment' (adding a B.Tech assignment/deadline)
   - 'view_assignments' (viewing or asking about current B.Tech assignments)
   - 'create_schedule' (scheduling a Gemini Student Ambassador or McKinsey Forward event)
   - 'view_schedule' (asking for ambassador/McKinsey schedules)
   - 'log_workout' (recording a strength training session)
   - 'view_workouts' (checking workout history or personal records)
   - 'create_story_draft' (creating or saving story drafts/brainstorms for "The Unstoppable")
   - 'view_story_drafts' (reading drafts/notes of the story)
   - 'create_custom_record' (adding an item/task/record to a custom category created by the user, e.g. "Volunteering", "Reading", etc.)
   - 'view_custom_records' (viewing or listing items/tasks/records in a custom category)
   - 'chitchat' (general conversations like greetings, simple questions, or AI status checks)
   - 'other' (none of the above)
3. Entities: Extract relevant parameters from the input:
   - For B.Tech assignments: 'title', 'description', 'course', 'deadline' (format as YYYY-MM-DD HH:MM:SS or ISO if mentioned, otherwise infer a future date/time if relative like 'tomorrow' or 'next Monday').
   - For ambassador/McKinsey schedules: 'program_name' (strictly 'Gemini Student Ambassador' or 'McKinsey Forward'), 'event_title', 'event_description', 'event_date'.
   - For workouts: 'exercise', 'sets' (integer), 'reps' (integer), 'weight' (float), 'personal_record' (boolean).
   - For story drafts: 'chapter_number' (integer), 'title_draft' (title of draft), 'content', 'brainstorm_notes', 'status'.
   - For custom categories: 'session_name' (name of the custom category, e.g. "Volunteering" or "Reading"), 'custom_title' (title of the task/record), 'custom_description' (details of the task/record).
4. Suggested Response: Create a short, supportive response confirming the action you are about to take on their behalf.
"""

def get_gemini_schema(types):
    """
    Explicitly define the schema using the google-genai SDK's types.Schema 
    to completely avoid additionalProperties bugs.
    """
    return types.Schema(
        type=types.Type.OBJECT,
        properties={
            "category": types.Schema(
                type=types.Type.STRING,
                description="Must be 'Professional', 'Personal', or 'General'"
            ),
            "action": types.Schema(
                type=types.Type.STRING,
                description="What action the user wants to perform. Options: 'create_assignment', 'view_assignments', 'create_schedule', 'view_schedule', 'log_workout', 'view_workouts', 'create_story_draft', 'view_story_drafts', 'create_custom_record', 'view_custom_records', 'chitchat', 'other'"
            ),
            "entities": types.Schema(
                type=types.Type.OBJECT,
                properties={
                    "title": types.Schema(type=types.Type.STRING, description="The title of the B.Tech assignment."),
                    "course": types.Schema(type=types.Type.STRING, description="The B.Tech course name, e.g., Physics, Calculus, Chemistry."),
                    "deadline": types.Schema(type=types.Type.STRING, description="The deadline date and time for the assignment."),
                    "description": types.Schema(type=types.Type.STRING, description="Additional description of the assignment or task."),
                    "program_name": types.Schema(type=types.Type.STRING, description="Strictly 'Gemini Student Ambassador' or 'McKinsey Forward'."),
                    "event_title": types.Schema(type=types.Type.STRING, description="The name/title of the program event or meeting."),
                    "event_date": types.Schema(type=types.Type.STRING, description="The scheduled date/time of the event."),
                    "event_description": types.Schema(type=types.Type.STRING, description="Details about the event."),
                    "exercise": types.Schema(type=types.Type.STRING, description="The strength training exercise name, e.g., Bench Press, Squat."),
                    "sets": types.Schema(type=types.Type.INTEGER, description="Number of sets performed."),
                    "reps": types.Schema(type=types.Type.INTEGER, description="Number of reps per set."),
                    "weight": types.Schema(type=types.Type.NUMBER, description="Weight used in kg or lbs."),
                    "personal_record": types.Schema(type=types.Type.BOOLEAN, description="Whether this is a personal record."),
                    "chapter_number": types.Schema(type=types.Type.INTEGER, description="The chapter number for the story 'The Unstoppable'."),
                    "title_draft": types.Schema(type=types.Type.STRING, description="Title of the story draft or brainstorm concept."),
                    "content": types.Schema(type=types.Type.STRING, description="Story draft content or details."),
                    "brainstorm_notes": types.Schema(type=types.Type.STRING, description="Brainstorming notes or ideas."),
                    "status": types.Schema(type=types.Type.STRING, description="Draft status, e.g., Draft, Completed."),
                    "session_name": types.Schema(type=types.Type.STRING, description="The name of the custom session category, if the user specifies logging/viewing in a custom category."),
                    "custom_title": types.Schema(type=types.Type.STRING, description="The title of the item being added to the custom category."),
                    "custom_description": types.Schema(type=types.Type.STRING, description="The description of the item being added to the custom category.")
                }
            ),
            "suggested_response": types.Schema(
                type=types.Type.STRING,
                description="A friendly, brief conversational answer explaining what you are doing."
            )
        },
        required=["category", "action", "suggested_response"]
    )

def classify_intent_with_gemini(message: str) -> IntentClassification:
    if not gemini_available or client is None:
        return mock_intent_classification(message)

    try:
        from google.genai import types
        schema = get_gemini_schema(types)
        
        # Request a structured output adhering to our custom schema
        response = client.models.generate_content(
            model='gemini-2.5-flash',
            contents=f"Classify the following user message: '{message}'",
            config=types.GenerateContentConfig(
                system_instruction=SYSTEM_PROMPT,
                response_mime_type="application/json",
                response_schema=schema,
                temperature=0.1,
            )
        )
        # Parse the JSON response
        result_dict = json.loads(response.text)
        return IntentClassification(**result_dict)
    except Exception as e:
        print(f"Gemini API error during classification: {e}")
        return mock_intent_classification(message)

def mock_intent_classification(message: str) -> IntentClassification:
    """
    Fallback classifier that uses regex/keywords when Gemini is unavailable.
    """
    msg = message.lower()
    
    # Check if this matches any custom category in database
    from database import SessionLocal
    db = SessionLocal()
    try:
        cats = db.query(models.SessionCategory).all()
        for cat in cats:
            if cat.name.lower() in msg:
                # Custom category match!
                is_view = any(k in msg for k in ["view", "show", "list", "get", "read", "what is", "what are"])
                action = "view_custom_records" if is_view else "create_custom_record"
                
                title = message
                # Try to clean up the title from verbs/prepositions if adding
                if action == "create_custom_record":
                    import re
                    clean_title = re.sub(r'^(add|log|record|put|insert)\s+(a\s+|an\s+)?(task\s+|entry\s+|item\s+)?(to|in|for)\s+' + re.escape(cat.name.lower()) + r'\s+(called|named|with\s+title)?\s*', '', msg, flags=re.IGNORECASE)
                    clean_title = clean_title.strip()
                    if clean_title:
                        title = clean_title.capitalize()
                
                return IntentClassification(
                    category=cat.type,
                    action=action,
                    entities=ExtractedEntities(
                        session_name=cat.name,
                        custom_title=title,
                        custom_description="Logged via mock agentic router."
                    ),
                    suggested_response=f"[MOCK] Detected custom category '{cat.name}' logging."
                )
    except Exception as e:
        print(f"Error querying custom categories in mock intent: {e}")
    finally:
        db.close()
    
    # 1. Workout detection
    if any(k in msg for k in ["workout", "bench press", "squat", "deadlift", "sets", "reps", "kg", "lbs", "lift", "training"]):
        exercise = "Bench Press"
        if "squat" in msg: exercise = "Squat"
        elif "deadlift" in msg: exercise = "Deadlift"
        
        # Simple extraction heuristics
        sets = 3
        reps = 10
        weight = 60.0
        
        # Try to find integers
        import re
        nums = re.findall(r'\d+', msg)
        if len(nums) >= 2:
            sets = int(nums[0])
            reps = int(nums[1])
            if len(nums) >= 3:
                weight = float(nums[2])
                
        return IntentClassification(
            category="Personal",
            action="log_workout",
            entities=ExtractedEntities(exercise=exercise, sets=sets, reps=reps, weight=weight, personal_record="pr" in msg or "record" in msg),
            suggested_response=f"[MOCK] I detected this is a workout log. Logging {sets} sets of {reps} reps of {exercise} at {weight}kg."
        )
        
    # 2. B.Tech Assignment detection
    elif any(k in msg for k in ["assignment", "deadline", "b.tech", "btech", "calculus", "physics", "chemistry", "due"]):
        course = "B.Tech General"
        for c in ["calculus", "physics", "chemistry", "programming", "english"]:
            if c in msg:
                course = c.capitalize()
                
        return IntentClassification(
            category="Professional",
            action="create_assignment",
            entities=ExtractedEntities(
                title="B.Tech Assignment",
                course=course,
                deadline=datetime.now().replace(hour=23, minute=59).strftime("%Y-%m-%d %H:%M:%S"),
                description="Added via mock classification"
            ),
            suggested_response=f"[MOCK] Detected B.Tech assignment details. Adding assignment for {course} due soon."
        )
        
    # 3. Ambassador / McKinsey detection
    elif any(k in msg for k in ["ambassador", "mckinsey", "forward", "student ambassador"]):
        prog = "Gemini Student Ambassador" if "gemini" in msg else "McKinsey Forward"
        return IntentClassification(
            category="Professional",
            action="create_schedule",
            entities=ExtractedEntities(
                program_name=prog,
                event_title="Program Event",
                event_date=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                event_description="Added via mock classification"
            ),
            suggested_response=f"[MOCK] Logging event for {prog} program."
        )
        
    # 4. Story drafts / brainstorm
    elif any(k in msg for k in ["story", "unstoppable", "chapter", "draft", "brainstorm", "novel", "book"]):
        chapter = None
        import re
        chap_nums = re.findall(r'chapter\s+(\d+)', msg)
        if chap_nums:
            chapter = int(chap_nums[0])
            
        return IntentClassification(
            category="Personal",
            action="create_story_draft",
            entities=ExtractedEntities(
                chapter_number=chapter,
                title_draft=f"Chapter {chapter} Idea" if chapter else "Story Idea",
                content="Story details: " + message,
                brainstorm_notes="Brainstorming for 'The Unstoppable'"
            ),
            suggested_response="[MOCK] Writing down your ideas for 'The Unstoppable' in your story drafts."
        )
        
    # Default: Chitchat
    return IntentClassification(
        category="General",
        action="chitchat",
        entities=ExtractedEntities(),
        suggested_response=f"[MOCK] Hello! I'm your Life Concierge. How can I help you manage your assignments, McKinsey/Gemini schedules, workouts, or story drafts today?"
    )

# --- Core Router API Endpoint ---

@app.post("/api/chat", response_model=ChatResponse)
def handle_chat(payload: ChatRequest, db: Session = Depends(get_db)):
    user_message = payload.message
    
    # 1. Classify the user intent using Gemini (or fallback mock)
    intent = classify_intent_with_gemini(user_message)
    
    database_updated = False
    action_data = None
    final_response = intent.suggested_response

    try:
        # 2. Perform DB operations depending on the action
        if intent.action == "create_assignment":
            # Extract entities
            title = intent.entities.title or "New Assignment"
            course = intent.entities.course or "B.Tech Course"
            desc = intent.entities.description or ""
            
            # Deadline date parsing
            deadline_str = intent.entities.deadline
            if deadline_str:
                try:
                    deadline_dt = datetime.fromisoformat(deadline_str.replace("Z", "+00:00"))
                except ValueError:
                    try:
                        deadline_dt = datetime.strptime(deadline_str, "%Y-%m-%d %H:%M:%S")
                    except ValueError:
                        deadline_dt = datetime.now() # Fallback
            else:
                deadline_dt = datetime.now()
                
            db_assignment = models.Assignment(
                title=title,
                description=desc,
                course=course,
                deadline=deadline_dt,
                status="Pending"
            )
            db.add(db_assignment)
            db.commit()
            db.refresh(db_assignment)
            database_updated = True
            action_data = {
                "id": db_assignment.id,
                "title": db_assignment.title,
                "course": db_assignment.course,
                "deadline": db_assignment.deadline.isoformat(),
                "status": db_assignment.status
            }
            final_response = f"I've added the B.Tech assignment '{title}' for {course} due on {db_assignment.deadline.strftime('%Y-%m-%d %H:%M')}. Good luck!"

        elif intent.action == "view_assignments":
            assignments = db.query(models.Assignment).order_by(models.Assignment.deadline.asc()).all()
            action_data = [
                {
                    "id": a.id,
                    "title": a.title,
                    "course": a.course,
                    "deadline": a.deadline.isoformat(),
                    "status": a.status
                }
                for a in assignments
            ]
            if assignments:
                items_str = ", ".join([f"'{a.title}' ({a.course})" for a in assignments[:3]])
                final_response = f"You have {len(assignments)} assignment(s) scheduled. Here are the upcoming ones: {items_str}."
            else:
                final_response = "You don't have any assignments logged in the system currently."

        elif intent.action == "create_schedule":
            prog_name = intent.entities.program_name or "Gemini Student Ambassador"
            event_title = intent.entities.event_title or "Event / Task"
            desc = intent.entities.event_description or ""
            
            date_str = intent.entities.event_date
            if date_str:
                try:
                    event_dt = datetime.fromisoformat(date_str.replace("Z", "+00:00"))
                except ValueError:
                    try:
                        event_dt = datetime.strptime(date_str, "%Y-%m-%d %H:%M:%S")
                    except ValueError:
                        event_dt = datetime.now()
            else:
                event_dt = datetime.now()
                
            db_schedule = models.ProgramSchedule(
                program_name=prog_name,
                event_title=event_title,
                event_description=desc,
                event_date=event_dt,
                status="Scheduled"
            )
            db.add(db_schedule)
            db.commit()
            db.refresh(db_schedule)
            database_updated = True
            action_data = {
                "id": db_schedule.id,
                "program_name": db_schedule.program_name,
                "event_title": db_schedule.event_title,
                "event_date": db_schedule.event_date.isoformat(),
                "status": db_schedule.status
            }
            final_response = f"I've added the event '{event_title}' for the {prog_name} program on {db_schedule.event_date.strftime('%Y-%m-%d %H:%M')}."

        elif intent.action == "view_schedule":
            schedules = db.query(models.ProgramSchedule).order_by(models.ProgramSchedule.event_date.asc()).all()
            action_data = [
                {
                    "id": s.id,
                    "program_name": s.program_name,
                    "event_title": s.event_title,
                    "event_date": s.event_date.isoformat(),
                    "status": s.status
                }
                for s in schedules
            ]
            if schedules:
                items_str = ", ".join([f"'{s.event_title}' ({s.program_name})" for s in schedules[:3]])
                final_response = f"You have {len(schedules)} event(s) scheduled. Upcoming: {items_str}."
            else:
                final_response = "You don't have any program schedule events logged."

        elif intent.action == "log_workout":
            exercise = intent.entities.exercise or "Strength Exercise"
            sets = intent.entities.sets if intent.entities.sets is not None else 3
            reps = intent.entities.reps if intent.entities.reps is not None else 10
            weight = intent.entities.weight if intent.entities.weight is not None else 0.0
            is_pr = bool(intent.entities.personal_record)
            
            db_workout = models.WorkoutLog(
                exercise=exercise,
                sets=sets,
                reps=reps,
                weight=weight,
                personal_record=is_pr
            )
            db.add(db_workout)
            db.commit()
            db.refresh(db_workout)
            database_updated = True
            action_data = {
                "id": db_workout.id,
                "exercise": db_workout.exercise,
                "sets": db_workout.sets,
                "reps": db_workout.reps,
                "weight": db_workout.weight,
                "personal_record": db_workout.personal_record,
                "logged_at": db_workout.logged_at.isoformat()
            }
            pr_suffix = " (New Personal Record! 🎉)" if is_pr else ""
            final_response = f"Logged: {sets} sets of {reps} reps of {exercise} at {weight}kg{pr_suffix}."

        elif intent.action == "view_workouts":
            workouts = db.query(models.WorkoutLog).order_by(models.WorkoutLog.logged_at.desc()).limit(10).all()
            action_data = [
                {
                    "id": w.id,
                    "exercise": w.exercise,
                    "sets": w.sets,
                    "reps": w.reps,
                    "weight": w.weight,
                    "personal_record": w.personal_record,
                    "logged_at": w.logged_at.isoformat()
                }
                for w in workouts
            ]
            if workouts:
                last_w = workouts[0]
                final_response = f"Your last logged workout was {last_w.sets}x{last_w.reps} of {last_w.exercise} at {last_w.weight}kg. I retrieved your recent strength logs."
            else:
                final_response = "You haven't logged any strength training workouts yet. Let's record one!"

        elif intent.action == "create_story_draft":
            title = intent.entities.title_draft or "New Brainstorm Note"
            chapter = intent.entities.chapter_number
            content = intent.entities.content or ""
            notes = intent.entities.brainstorm_notes or ""
            
            db_draft = models.StoryDraft(
                chapter_number=chapter,
                title=title,
                content=content,
                brainstorm_notes=notes,
                status="Draft"
            )
            db.add(db_draft)
            db.commit()
            db.refresh(db_draft)
            database_updated = True
            action_data = {
                "id": db_draft.id,
                "chapter_number": db_draft.chapter_number,
                "title": db_draft.title,
                "status": db_draft.status
            }
            chap_prefix = f"Chapter {chapter} - " if chapter else ""
            final_response = f"Saved draft: '{chap_prefix}{title}' to the story 'The Unstoppable'."

        elif intent.action == "view_story_drafts":
            drafts = db.query(models.StoryDraft).order_by(models.StoryDraft.chapter_number.asc().nullsfirst()).all()
            action_data = [
                {
                    "id": d.id,
                    "chapter_number": d.chapter_number,
                    "title": d.title,
                    "status": d.status
                }
                for d in drafts
            ]
            if drafts:
                drafts_str = ", ".join([f"'{d.title}'" for d in drafts[:3]])
                final_response = f"You have {len(drafts)} drafts saved for 'The Unstoppable'. Recent notes: {drafts_str}."
            else:
                final_response = "No brainstorming drafts found for 'The Unstoppable'."

        elif intent.action == "create_custom_record":
            session_name = intent.entities.session_name
            title = intent.entities.custom_title or "New Entry"
            desc = intent.entities.custom_description or ""
            if not session_name:
                session_name = "General"
            db_cat = db.query(models.SessionCategory).filter(
                models.SessionCategory.name.like(session_name)
            ).first()
            if not db_cat:
                cat_type = intent.category if intent.category in ["Professional", "Personal"] else "Professional"
                db_cat = models.SessionCategory(name=session_name, type=cat_type)
                db.add(db_cat)
                db.commit()
                db.refresh(db_cat)
            db_record = models.CustomRecord(
                category_id=db_cat.id,
                title=title,
                description=desc,
                status="Pending"
            )
            db.add(db_record)
            db.commit()
            db.refresh(db_record)
            database_updated = True
            action_data = {
                "id": db_record.id,
                "category_id": db_record.category_id,
                "category_name": db_cat.name,
                "title": db_record.title,
                "description": db_record.description,
                "status": db_record.status
            }
            final_response = f"Added '{title}' to your custom session '{db_cat.name}'."

        elif intent.action == "view_custom_records":
            session_name = intent.entities.session_name
            db_cat = None
            if session_name:
                db_cat = db.query(models.SessionCategory).filter(
                    models.SessionCategory.name.like(session_name)
                ).first()
            if db_cat:
                records = db.query(models.CustomRecord).filter(
                    models.CustomRecord.category_id == db_cat.id
                ).order_by(models.CustomRecord.created_at.desc()).all()
                action_data = [
                    {
                        "id": r.id,
                        "category_id": r.category_id,
                        "title": r.title,
                        "description": r.description,
                        "status": r.status
                    }
                    for r in records
                ]
                if records:
                    records_str = ", ".join([f"'{r.title}'" for r in records[:3]])
                    final_response = f"Here are the latest entries in your '{db_cat.name}' session: {records_str}."
                else:
                    final_response = f"Your custom session '{db_cat.name}' has no entries yet."
            else:
                final_response = f"I couldn't find a custom session named '{session_name or 'unspecified'}'. You can create one from the Sessions panel!"

        elif intent.action == "chitchat":
            action_data = None

    except Exception as db_err:
        db.rollback()
        print(f"Database error: {db_err}")
        final_response = f"I classified your intent as '{intent.action}', but ran into an error database-side: {str(db_err)}"

    return ChatResponse(
        response=final_response,
        category=intent.category,
        action=intent.action,
        entities=intent.entities,
        database_updated=database_updated,
        data=action_data
    )

# --- Standard REST Endpoints for Data Inspection ---

@app.get("/api/assignments", response_model=List[AssignmentResponse])
def read_assignments(db: Session = Depends(get_db)):
    return db.query(models.Assignment).order_by(models.Assignment.deadline.asc()).all()

@app.get("/api/schedules", response_model=List[ProgramScheduleResponse])
def read_schedules(db: Session = Depends(get_db)):
    return db.query(models.ProgramSchedule).order_by(models.ProgramSchedule.event_date.asc()).all()

@app.get("/api/workouts", response_model=List[WorkoutLogResponse])
def read_workouts(db: Session = Depends(get_db)):
    return db.query(models.WorkoutLog).order_by(models.WorkoutLog.logged_at.desc()).all()

@app.get("/api/story-drafts", response_model=List[StoryDraftResponse])
def read_story_drafts(db: Session = Depends(get_db)):
    return db.query(models.StoryDraft).order_by(models.StoryDraft.chapter_number.asc().nullsfirst()).all()


# --- Session Category & Record Endpoints ---

@app.get("/api/categories", response_model=List[SessionCategoryResponse])
def read_categories(db: Session = Depends(get_db)):
    return db.query(models.SessionCategory).all()

@app.post("/api/categories", response_model=SessionCategoryResponse)
def create_category(payload: SessionCategoryCreate, db: Session = Depends(get_db)):
    existing = db.query(models.SessionCategory).filter(models.SessionCategory.name == payload.name).first()
    if existing:
        raise HTTPException(status_code=400, detail="Category already exists")
    db_cat = models.SessionCategory(name=payload.name, type=payload.type)
    db.add(db_cat)
    db.commit()
    db.refresh(db_cat)
    return db_cat

@app.delete("/api/categories/{category_id}")
def delete_category(category_id: int, db: Session = Depends(get_db)):
    db_cat = db.query(models.SessionCategory).filter(models.SessionCategory.id == category_id).first()
    if not db_cat:
        raise HTTPException(status_code=404, detail="Category not found")
    db.delete(db_cat)
    db.commit()
    return {"message": "Category deleted successfully"}

@app.get("/api/categories/{category_id}/records", response_model=List[CustomRecordResponse])
def read_category_records(category_id: int, db: Session = Depends(get_db)):
    db_cat = db.query(models.SessionCategory).filter(models.SessionCategory.id == category_id).first()
    if not db_cat:
        raise HTTPException(status_code=404, detail="Category not found")
    return db.query(models.CustomRecord).filter(models.CustomRecord.category_id == category_id).all()

@app.post("/api/categories/{category_id}/records", response_model=CustomRecordResponse)
def create_category_record(category_id: int, payload: CustomRecordCreate, db: Session = Depends(get_db)):
    db_cat = db.query(models.SessionCategory).filter(models.SessionCategory.id == category_id).first()
    if not db_cat:
        raise HTTPException(status_code=404, detail="Category not found")
    db_rec = models.CustomRecord(
        category_id=category_id,
        title=payload.title,
        description=payload.description,
        status=payload.status
    )
    db.add(db_rec)
    db.commit()
    db.refresh(db_rec)
    return db_rec

@app.put("/api/records/{record_id}", response_model=CustomRecordResponse)
def update_custom_record(record_id: int, payload: CustomRecordUpdate, db: Session = Depends(get_db)):
    db_rec = db.query(models.CustomRecord).filter(models.CustomRecord.id == record_id).first()
    if not db_rec:
        raise HTTPException(status_code=404, detail="Record not found")
    if payload.title is not None:
        db_rec.title = payload.title
    if payload.description is not None:
        db_rec.description = payload.description
    if payload.status is not None:
        db_rec.status = payload.status
    db.commit()
    db.refresh(db_rec)
    return db_rec

@app.delete("/api/records/{record_id}")
def delete_custom_record(record_id: int, db: Session = Depends(get_db)):
    db_rec = db.query(models.CustomRecord).filter(models.CustomRecord.id == record_id).first()
    if not db_rec:
        raise HTTPException(status_code=404, detail="Record not found")
    db.delete(db_rec)
    db.commit()
    return {"message": "Record deleted successfully"}


# --- User Authentication & Profile Endpoints ---

@app.post("/api/register")
def register_user(payload: UserRegister, db: Session = Depends(get_db)):
    # Check if username or email already exists
    existing_username = db.query(models.User).filter(models.User.username == payload.username).first()
    if existing_username:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Username already registered"
        )
    existing_email = db.query(models.User).filter(models.User.email == payload.email).first()
    if existing_email:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Email address already registered"
        )
    
    # Store SHA256 hashed password
    import hashlib
    hashed_password = hashlib.sha256(payload.password.encode()).hexdigest()

    db_user = models.User(
        username=payload.username,
        email=payload.email,
        password=hashed_password
    )
    db.add(db_user)
    db.commit()
    db.refresh(db_user)
    
    return {"message": "Registration successful", "username": db_user.username}

@app.post("/api/login")
def login_user(payload: UserLogin, db: Session = Depends(get_db)):
    import hashlib
    hashed_password = hashlib.sha256(payload.password.encode()).hexdigest()
    
    # Check by email or username
    user = db.query(models.User).filter(
        (models.User.email == payload.email_or_username) | 
        (models.User.username == payload.email_or_username)
    ).first()
    
    if not user or user.password != hashed_password:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid username/email or password"
        )
    
    return {
        "message": "Login successful",
        "username": user.username,
        "email": user.email,
        "age": user.age,
        "gender": user.gender,
        "birthdate": user.birthdate,
        "profile_image": user.profile_image
    }

@app.get("/api/profile/{username}", response_model=ProfileResponse)
def get_profile(username: str, db: Session = Depends(get_db)):
    user = db.query(models.User).filter(models.User.username == username).first()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found"
        )
    return user

@app.put("/api/profile/{username}")
def update_profile(username: str, payload: ProfileUpdate, db: Session = Depends(get_db)):
    user = db.query(models.User).filter(models.User.username == username).first()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found"
        )
    
    if payload.age is not None:
        user.age = payload.age
    if payload.gender is not None:
        user.gender = payload.gender
    if payload.birthdate is not None:
        user.birthdate = payload.birthdate
    if payload.profile_image is not None:
        user.profile_image = payload.profile_image
        
    db.commit()
    db.refresh(user)
    return {
        "message": "Profile updated successfully",
        "username": user.username,
        "age": user.age,
        "gender": user.gender,
        "birthdate": user.birthdate,
        "profile_image": user.profile_image
    }


@app.put("/api/assignments/{assignment_id}", response_model=AssignmentResponse)
def update_assignment(assignment_id: int, payload: AssignmentUpdate, db: Session = Depends(get_db)):
    db_assign = db.query(models.Assignment).filter(models.Assignment.id == assignment_id).first()
    if not db_assign:
        raise HTTPException(status_code=404, detail="Assignment not found")
    if payload.status is not None:
        db_assign.status = payload.status
    if payload.deadline is not None:
        db_assign.deadline = payload.deadline
    db.commit()
    db.refresh(db_assign)
    return db_assign


@app.put("/api/schedules/{schedule_id}", response_model=ProgramScheduleResponse)
def update_schedule(schedule_id: int, payload: ScheduleUpdate, db: Session = Depends(get_db)):
    db_sched = db.query(models.ProgramSchedule).filter(models.ProgramSchedule.id == schedule_id).first()
    if not db_sched:
        raise HTTPException(status_code=404, detail="Schedule not found")
    if payload.status is not None:
        db_sched.status = payload.status
    if payload.event_date is not None:
        db_sched.event_date = payload.event_date
    db.commit()
    db.refresh(db_sched)
    return db_sched



if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="127.0.0.1", port=8000, reload=True)
