from sqlalchemy import Column, Integer, String, Boolean, DateTime, Text, Float, ForeignKey
from sqlalchemy.orm import relationship
from datetime import datetime
from database import Base


class Assignment(Base):
    """
    Professional Module: Tracks B.Tech assignments, homework, and presentation deadlines.
    """
    __tablename__ = "assignments"

    id = Column(Integer, primary_key=True, index=True)
    title = Column(String, nullable=False, index=True)
    description = Column(Text, nullable=True)
    course = Column(String, nullable=False, index=True)  # e.g., Physics, Calculus, Chemistry
    deadline = Column(DateTime, nullable=False)
    status = Column(String, default="Pending")  # e.g., Pending, In Progress, Completed
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class ProgramSchedule(Base):
    """
    Professional Module: Schedules and logs tasks/events for the 
    Gemini Student Ambassador & McKinsey Forward programs.
    """
    __tablename__ = "program_schedules"

    id = Column(Integer, primary_key=True, index=True)
    program_name = Column(String, nullable=False, index=True)  # 'Gemini Student Ambassador' or 'McKinsey Forward'
    event_title = Column(String, nullable=False)
    event_description = Column(Text, nullable=True)
    event_date = Column(DateTime, nullable=False)
    status = Column(String, default="Scheduled")  # e.g., Scheduled, Completed, Cancelled
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class WorkoutLog(Base):
    """
    Personal Module: Logs strength training routines and exercises.
    """
    __tablename__ = "workout_logs"

    id = Column(Integer, primary_key=True, index=True)
    exercise = Column(String, nullable=False, index=True)  # e.g., Bench Press, Squat, Deadlift
    sets = Column(Integer, nullable=False)
    reps = Column(Integer, nullable=False)
    weight = Column(Float, nullable=False)  # in kg or lbs
    personal_record = Column(Boolean, default=False)
    logged_at = Column(DateTime, default=datetime.utcnow)


class StoryDraft(Base):
    """
    Personal Module: Brainstorming notes and chapter drafts for the story "The Unstoppable".
    """
    __tablename__ = "story_drafts"

    id = Column(Integer, primary_key=True, index=True)
    chapter_number = Column(Integer, nullable=True)
    title = Column(String, nullable=False, index=True)
    content = Column(Text, nullable=True)
    brainstorm_notes = Column(Text, nullable=True)
    status = Column(String, default="Draft")  # e.g., Brainstorm, Draft, Completed, Polished
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class User(Base):
    """
    User Account & Profile: Stores authentication credentials and profile details.
    """
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    username = Column(String, unique=True, index=True, nullable=False)
    email = Column(String, unique=True, index=True, nullable=False)
    password = Column(String, nullable=False)  # Stored password hash/raw (local app)
    age = Column(Integer, nullable=True)
    gender = Column(String, nullable=True)
    birthdate = Column(String, nullable=True)
    profile_image = Column(Text, nullable=True)  # Stored Base64 encoded image
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class SessionCategory(Base):
    """
    Dynamic Sessions/Categories created by the user (B.Tech, Workouts, etc.).
    """
    __tablename__ = "session_categories"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, unique=True, index=True, nullable=False)
    type = Column(String, nullable=False)  # "Professional" or "Personal"
    created_at = Column(DateTime, default=datetime.utcnow)

    records = relationship("CustomRecord", back_populates="category", cascade="all, delete-orphan")


class CustomRecord(Base):
    """
    Generic task/item entries logged in user-created custom sessions.
    """
    __tablename__ = "custom_records"

    id = Column(Integer, primary_key=True, index=True)
    category_id = Column(Integer, ForeignKey("session_categories.id", ondelete="CASCADE"), nullable=False)
    title = Column(String, nullable=False, index=True)
    description = Column(Text, nullable=True)
    status = Column(String, default="Pending")  # e.g., Pending, In Progress, Completed
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    category = relationship("SessionCategory", back_populates="records")


