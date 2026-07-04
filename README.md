# Life Concierge AI Agent

A unified, intelligent chat interface and dashboard to manage daily professional tasks (B.Tech assignments, McKinsey Forward schedules, Gemini Ambassador events) and personal logs (weekly strength training, story drafts for "The Unstoppable").

Built using a modern stack: Next.js 16 (App Router), Tailwind CSS v4, FastAPI, SQLite, and Google Gemini API.

---

## Tech Stack Summary
- **Frontend**: Next.js (App Router), Tailwind CSS v4, TypeScript, Lucide Icons.
- **Backend**: FastAPI (Python 3.13), Uvicorn.
- **Database**: SQLite (SQLAlchemy ORM).
- **AI Core**: Google Gemini API via the official `google-genai` SDK.

---

## Setup & Running Instructions

### 1. Backend Server Setup (FastAPI)
1. Navigate to the backend directory:
   ```bash
   cd backend
   ```
2. Create and configure your environment file:
   - Copy `.env.example` to `.env`
   - Paste your **Gemini API Key** from [Google AI Studio](https://aistudio.google.com/):
     ```env
     GEMINI_API_KEY=AIzaSy...
     ```
3. Run the development server:
   ```bash
   py -m uvicorn main:app --reload
   ```
   *Note: On backend startup, the SQLite database `life_concierge.db` will be initialized automatically and print `Application startup complete`.*

---

### 2. Frontend Dashboard Setup (Next.js)
1. Navigate to the frontend directory:
   ```bash
   cd frontend
   ```
2. Start the hot-reload development server:
   ```bash
   npm run dev
   ```
   *(or `npm.cmd run dev` on Windows PowerShell)*
3. Open your browser and navigate to **[http://localhost:3000](http://localhost:3000)**.

---

## Quick-Start Queries to Try in Chat
- **Log workout**: `"Log workout: Bench press 3 sets of 10 reps at 80kg"`
- **B.Tech Assignment**: `"Add a Physics assignment on Quantum Mechanics due next Friday"`
- **Ambassador Program**: `"Schedule a presentation workshop for Gemini Student Ambassador next Wednesday"`
- **Story Brainstorming**: `"Save Chapter 2 brainstorm notes: The protagonist discovers an ancient artifact"`
- **Inspection**: Click on the **Database Center** tab in the sidebar to review all SQLite records dynamically synced from your chat actions.
