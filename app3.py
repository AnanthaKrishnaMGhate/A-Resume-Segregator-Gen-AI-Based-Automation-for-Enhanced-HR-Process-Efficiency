# HR Hiring Process Automation Agent System
import streamlit as st
import pandas as pd
import sqlite3
import json
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime, timedelta
import uuid
import re
import os
import tempfile
from typing import Dict, List, Optional, Tuple, Any
import requests
from dataclasses import dataclass
import asyncio
from groq import Groq
import logging
import io
import PyPDF2
import docx
import time
import hashlib

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Configure Streamlit page
st.set_page_config(
    page_title="HR Automation Agent",
    page_icon="🤖",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Custom CSS for better UI
st.markdown("""
<style>
    .main-header {
        background: linear-gradient(90deg, #667eea 0%, #764ba2 100%);
        padding: 1rem;
        border-radius: 10px;
        color: white;
        text-align: center;
        margin-bottom: 2rem;
    }
    .agent-card {
        background: #f8f9fa;
        padding: 1rem;
        border-radius: 8px;
        border-left: 4px solid #667eea;
        margin: 0.5rem 0;
    }
    .status-active { color: #28a745; }
    .status-pending { color: #ffc107; }
    .status-completed { color: #17a2b8; }
    .candidate-card {
        background: white;
        padding: 1rem;
        border-radius: 8px;
        box-shadow: 0 2px 4px rgba(0,0,0,0.1);
        margin: 0.5rem 0;
    }
    .stButton>button {
        width: 100%;
    }
    .danger-zone {
        background-color: #fff5f5;
        border-left: 4px solid #dc3545;
        padding: 1rem;
        border-radius: 5px;
    }
    .info-box {
        background-color: #f0f7ff;
        border-left: 4px solid #0d6efd;
        padding: 1rem;
        border-radius: 5px;
        margin-bottom: 1rem;
    }
    .success-box {
        background-color: #f0fff0;
        border-left: 4px solid #28a745;
        padding: 1rem;
        border-radius: 5px;
        margin-bottom: 1rem;
    }
    .warning-box {
        background-color: #fffaf0;
        border-left: 4px solid #ffc107;
        padding: 1rem;
        border-radius: 5px;
        margin-bottom: 1rem;
    }
    .dashboard-metric {
        background: white;
        padding: 1.5rem;
        border-radius: 10px;
        box-shadow: 0 2px 10px rgba(0,0,0,0.05);
        text-align: center;
    }
    .dashboard-metric h1 {
        font-size: 2.5rem;
        margin: 0;
        color: #764ba2;
    }
    .dashboard-metric p {
        margin: 0;
        color: #666;
    }
</style>
""", unsafe_allow_html=True)

@dataclass
class Candidate:
    id: str
    name: str
    email: str
    country: str
    current_job: str
    total_experience: float
    relevant_experience: float
    application_reason: str
    notice_period: str
    rating: float
    status: str
    created_at: str
    job_id: Optional[str] = None
    resume_text: Optional[str] = None
    interview_notes: Optional[str] = None
    skills: Optional[List[str]] = None

@dataclass
class Job:
    id: str
    title: str
    description: str
    keywords: List[str]
    status: str
    created_at: str
    posted_at: Optional[str] = None
    department: Optional[str] = None
    location: Optional[str] = None
    employment_type: Optional[str] = None
    salary_range: Optional[str] = None
    application_count: int = 0

class DatabaseManager:
    def __init__(self, db_path="hr_automation.db"):
        self.db_path = os.path.abspath(db_path)
        logger.info(f"Using database at: {self.db_path}")
        self.init_database()

    def get_connection(self) -> sqlite3.Connection:
        """Get a database connection with retry logic"""
        max_retries = 3
        retry_delay = 0.5

        for attempt in range(max_retries):
            try:
                conn = sqlite3.connect(self.db_path, timeout=10)
                conn.row_factory = sqlite3.Row  # Return rows as dictionaries
                return conn
            except sqlite3.Error as e:
                logger.error(f"Database connection error (attempt {attempt+1}/{max_retries}): {e}")
                if attempt < max_retries - 1:
                    time.sleep(retry_delay)
                    retry_delay *= 2  # Exponential backoff
                else:
                    raise

    def init_database(self):
        try:
            conn = self.get_connection()
            cursor = conn.cursor()

            # Jobs table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS jobs (
                    id TEXT PRIMARY KEY,
                    title TEXT NOT NULL,
                    description TEXT NOT NULL,
                    keywords TEXT NOT NULL,
                    status TEXT DEFAULT 'draft',
                    created_at TEXT NOT NULL,
                    posted_at TEXT,
                    department TEXT,
                    location TEXT,
                    employment_type TEXT,
                    salary_range TEXT
                )
            """)

            # Candidates table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS candidates (
                    id TEXT PRIMARY KEY,
                    job_id TEXT,
                    name TEXT NOT NULL,
                    email TEXT NOT NULL,
                    country TEXT,
                    current_job TEXT,
                    total_experience REAL,
                    relevant_experience REAL,
                    application_reason TEXT,
                    notice_period TEXT,
                    rating REAL,
                    status TEXT DEFAULT 'applied',
                    created_at TEXT NOT NULL,
                    resume_text TEXT,
                    interview_notes TEXT,
                    skills TEXT,
                    FOREIGN KEY (job_id) REFERENCES jobs (id)
                )
            """)

            # Process tracking table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS process_tracking (
                    id TEXT PRIMARY KEY,
                    candidate_id TEXT,
                    job_id TEXT,
                    step TEXT NOT NULL,
                    status TEXT NOT NULL,
                    timestamp TEXT NOT NULL,
                    notes TEXT,
                    FOREIGN KEY (candidate_id) REFERENCES candidates (id),
                    FOREIGN KEY (job_id) REFERENCES jobs (id)
                )
            """)

            # Email templates table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS email_templates (
                    id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    subject TEXT NOT NULL,
                    body TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
            """)

            # Settings table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS settings (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
            """)

            conn.commit()
            conn.close()
            logger.info("Database initialized successfully")
        except Exception as e:
            logger.error(f"Error initializing database: {e}")
            raise

    def save_job(self, job: Job) -> bool:
        try:
            logger.info(f"Saving job: {job.title} ({job.id})")
            conn = self.get_connection()
            cursor = conn.cursor()
            cursor.execute("""
                INSERT OR REPLACE INTO jobs
                (id, title, description, keywords, status, created_at, posted_at,
                department, location, employment_type, salary_range)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (job.id, job.title, job.description, json.dumps(job.keywords),
                  job.status, job.created_at, job.posted_at, job.department,
                  job.location, job.employment_type, job.salary_range))
            conn.commit()
            conn.close()
            return True
        except Exception as e:
            logger.error(f"Error saving job: {e}")
            return False

    def save_candidate(self, candidate: Candidate, job_id: str) -> bool:
        try:
            logger.info(f"Saving candidate: {candidate.name} ({candidate.id}) for job {job_id}")
            conn = self.get_connection()
            cursor = conn.cursor()

            # Convert skills list to JSON string if it exists
            skills_json = json.dumps(candidate.skills) if candidate.skills else None

            cursor.execute("""
                INSERT OR REPLACE INTO candidates
                (id, job_id, name, email, country, current_job, total_experience,
                 relevant_experience, application_reason, notice_period, rating, status,
                 created_at, resume_text, interview_notes, skills)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (candidate.id, job_id, candidate.name, candidate.email, candidate.country,
                  candidate.current_job, candidate.total_experience, candidate.relevant_experience,
                  candidate.application_reason, candidate.notice_period, candidate.rating,
                  candidate.status, candidate.created_at, candidate.resume_text,
                  candidate.interview_notes, skills_json))

            # Update application count for the job
            cursor.execute("""
                SELECT COUNT(*) FROM candidates WHERE job_id = ?
            """, (job_id,))
            count = cursor.fetchone()[0]

            conn.commit()
            conn.close()
            return True
        except Exception as e:
            logger.error(f"Error saving candidate: {e}")
            return False

    def update_candidate_status(self, candidate_id: str, new_status: str) -> bool:
        try:
            conn = self.get_connection()
            cursor = conn.cursor()
            cursor.execute("""
                UPDATE candidates SET status = ? WHERE id = ?
            """, (new_status, candidate_id))

            # Add to process tracking
            tracking_id = str(uuid.uuid4())
            timestamp = datetime.now().isoformat()

            # Get job_id for this candidate
            cursor.execute("SELECT job_id FROM candidates WHERE id = ?", (candidate_id,))
            job_id = cursor.fetchone()[0]

            cursor.execute("""
                INSERT INTO process_tracking
                (id, candidate_id, job_id, step, status, timestamp, notes)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (tracking_id, candidate_id, job_id, "status_change", new_status, timestamp,
                  f"Status changed to {new_status}"))

            conn.commit()
            conn.close()
            return True
        except Exception as e:
            logger.error(f"Error updating candidate status: {e}")
            return False

    def add_interview_notes(self, candidate_id: str, notes: str) -> bool:
        try:
            conn = self.get_connection()
            cursor = conn.cursor()
            cursor.execute("""
                UPDATE candidates SET interview_notes = ? WHERE id = ?
            """, (notes, candidate_id))
            conn.commit()
            conn.close()
            return True
        except Exception as e:
            logger.error(f"Error adding interview notes: {e}")
            return False

    def get_jobs(self, status: str = None) -> List[Job]:
        try:
            logger.info("Fetching jobs from database")
            conn = self.get_connection()
            cursor = conn.cursor()

            if status:
                cursor.execute("SELECT * FROM jobs WHERE status = ? ORDER BY created_at DESC", (status,))
            else:
                cursor.execute("SELECT * FROM jobs ORDER BY created_at DESC")

            rows = cursor.fetchall()

            jobs = []
            for row in rows:
                # Get application count for each job
                cursor.execute("SELECT COUNT(*) FROM candidates WHERE job_id = ?", (row['id'],))
                application_count = cursor.fetchone()[0]

                jobs.append(Job(
                    id=row['id'],
                    title=row['title'],
                    description=row['description'],
                    keywords=json.loads(row['keywords']),
                    status=row['status'],
                    created_at=row['created_at'],
                    posted_at=row['posted_at'],
                    department=row['department'],
                    location=row['location'],
                    employment_type=row['employment_type'],
                    salary_range=row['salary_range'],
                    application_count=application_count
                ))

            conn.close()
            return jobs
        except Exception as e:
            logger.error(f"Error getting jobs: {e}")
            return []

    def get_job_by_id(self, job_id: str) -> Optional[Job]:
        try:
            conn = self.get_connection()
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM jobs WHERE id = ?", (job_id,))
            row = cursor.fetchone()

            if not row:
                conn.close()
                return None

            # Get application count
            cursor.execute("SELECT COUNT(*) FROM candidates WHERE job_id = ?", (job_id,))
            application_count = cursor.fetchone()[0]

            job = Job(
                id=row['id'],
                title=row['title'],
                description=row['description'],
                keywords=json.loads(row['keywords']),
                status=row['status'],
                created_at=row['created_at'],
                posted_at=row['posted_at'],
                department=row['department'],
                location=row['location'],
                employment_type=row['employment_type'],
                salary_range=row['salary_range'],
                application_count=application_count
            )

            conn.close()
            return job
        except Exception as e:
            logger.error(f"Error getting job by ID: {e}")
            return None

    def get_candidates(self, job_id: str = None, status: str = None) -> List[Candidate]:
        try:
            conn = self.get_connection()
            cursor = conn.cursor()

            query = "SELECT * FROM candidates"
            params = []

            if job_id and status:
                query += " WHERE job_id = ? AND status = ?"
                params = [job_id, status]
            elif job_id:
                query += " WHERE job_id = ?"
                params = [job_id]
            elif status:
                query += " WHERE status = ?"
                params = [status]

            query += " ORDER BY rating DESC, created_at DESC"

            cursor.execute(query, params)
            rows = cursor.fetchall()

            candidates = []
            for row in rows:
                # Parse skills from JSON if available
                skills = json.loads(row['skills']) if row['skills'] else None

                candidates.append(Candidate(
                    id=row['id'],
                    name=row['name'],
                    email=row['email'],
                    country=row['country'],
                    current_job=row['current_job'],
                    total_experience=row['total_experience'],
                    relevant_experience=row['relevant_experience'],
                    application_reason=row['application_reason'],
                    notice_period=row['notice_period'],
                    rating=row['rating'],
                    status=row['status'],
                    created_at=row['created_at'],
                    job_id=row['job_id'],
                    resume_text=row['resume_text'],
                    interview_notes=row['interview_notes'],
                    skills=skills
                ))

            conn.close()
            return candidates
        except Exception as e:
            logger.error(f"Error getting candidates: {e}")
            return []

    def get_candidate_by_id(self, candidate_id: str) -> Optional[Candidate]:
        try:
            conn = self.get_connection()
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM candidates WHERE id = ?", (candidate_id,))
            row = cursor.fetchone()

            if not row:
                conn.close()
                return None

            # Parse skills from JSON if available
            skills = json.loads(row['skills']) if row['skills'] else None

            candidate = Candidate(
                id=row['id'],
                name=row['name'],
                email=row['email'],
                country=row['country'],
                current_job=row['current_job'],
                total_experience=row['total_experience'],
                relevant_experience=row['relevant_experience'],
                application_reason=row['application_reason'],
                notice_period=row['notice_period'],
                rating=row['rating'],
                status=row['status'],
                created_at=row['created_at'],
                job_id=row['job_id'],
                resume_text=row['resume_text'],
                interview_notes=row['interview_notes'],
                skills=skills
            )

            conn.close()
            return candidate
        except Exception as e:
            logger.error(f"Error getting candidate by ID: {e}")
            return None

    def get_process_history(self, candidate_id: str) -> List[Dict]:
        try:
            conn = self.get_connection()
            cursor = conn.cursor()
            cursor.execute("""
                SELECT * FROM process_tracking
                WHERE candidate_id = ?
                ORDER BY timestamp DESC
            """, (candidate_id,))

            rows = cursor.fetchall()
            history = [dict(row) for row in rows]

            conn.close()
            return history
        except Exception as e:
            logger.error(f"Error getting process history: {e}")
            return []

    def save_email_template(self, template_id: str, name: str, subject: str, body: str) -> bool:
        try:
            conn = self.get_connection()
            cursor = conn.cursor()

            now = datetime.now().isoformat()

            cursor.execute("""
                INSERT OR REPLACE INTO email_templates
                (id, name, subject, body, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (template_id, name, subject, body, now, now))

            conn.commit()
            conn.close()
            return True
        except Exception as e:
            logger.error(f"Error saving email template: {e}")
            return False

    def get_email_templates(self) -> List[Dict]:
        try:
            conn = self.get_connection()
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM email_templates ORDER BY name")

            rows = cursor.fetchall()
            templates = [dict(row) for row in rows]

            conn.close()
            return templates
        except Exception as e:
            logger.error(f"Error getting email templates: {e}")
            return []

    def save_setting(self, key: str, value: str) -> bool:
        try:
            conn = self.get_connection()
            cursor = conn.cursor()

            now = datetime.now().isoformat()

            cursor.execute("""
                INSERT OR REPLACE INTO settings
                (key, value, updated_at)
                VALUES (?, ?, ?)
            """, (key, value, now))

            conn.commit()
            conn.close()
            return True
        except Exception as e:
            logger.error(f"Error saving setting: {e}")
            return False

    def get_setting(self, key: str, default: str = None) -> str:
        try:
            conn = self.get_connection()
            cursor = conn.cursor()
            cursor.execute("SELECT value FROM settings WHERE key = ?", (key,))

            row = cursor.fetchone()
            conn.close()

            if row:
                return row[0]
            return default
        except Exception as e:
            logger.error(f"Error getting setting: {e}")
            return default

    def clear_all_data(self) -> bool:
        """Clear all data from the database"""
        try:
            conn = self.get_connection()
            cursor = conn.cursor()

            # Delete data from all tables
            cursor.execute("DELETE FROM process_tracking")
            cursor.execute("DELETE FROM candidates")
            cursor.execute("DELETE FROM jobs")

            # Don't delete settings and email templates

            conn.commit()
            conn.close()
            logger.info("All data cleared successfully")
            return True
        except Exception as e:
            logger.error(f"Error clearing data: {e}")
            return False

    def get_analytics_data(self) -> Dict[str, Any]:
        """Get analytics data from the database"""
        try:
            conn = self.get_connection()
            cursor = conn.cursor()

            # Jobs by status
            cursor.execute("""
                SELECT status, COUNT(*) as count
                FROM jobs
                GROUP BY status
            """)
            jobs_by_status = {row['status']: row['count'] for row in cursor.fetchall()}

            # Candidates by status
            cursor.execute("""
                SELECT status, COUNT(*) as count
                FROM candidates
                GROUP BY status
            """)
            candidates_by_status = {row['status']: row['count'] for row in cursor.fetchall()}

            # Average rating by job
            cursor.execute("""
                SELECT j.title, AVG(c.rating) as avg_rating, COUNT(c.id) as count
                FROM candidates c
                JOIN jobs j ON c.job_id = j.id
                GROUP BY j.id
                ORDER BY avg_rating DESC
            """)
            avg_ratings = [dict(row) for row in cursor.fetchall()]

            # Candidates by country
            cursor.execute("""
                SELECT country, COUNT(*) as count
                FROM candidates
                WHERE country IS NOT NULL AND country != ''
                GROUP BY country
                ORDER BY count DESC
                LIMIT 10
            """)
            candidates_by_country = {row['country']: row['count'] for row in cursor.fetchall()}

            # Experience distribution
            cursor.execute("""
                SELECT
                    CASE
                        WHEN total_experience < 2 THEN '0-2 years'
                        WHEN total_experience < 5 THEN '2-5 years'
                        WHEN total_experience < 10 THEN '5-10 years'
                        ELSE '10+ years'
                    END as exp_range,
                    COUNT(*) as count
                FROM candidates
                GROUP BY exp_range
                ORDER BY
                    CASE exp_range
                        WHEN '0-2 years' THEN 1
                        WHEN '2-5 years' THEN 2
                        WHEN '5-10 years' THEN 3
                        WHEN '10+ years' THEN 4
                    END
            """)
            experience_distribution = {row['exp_range']: row['count'] for row in cursor.fetchall()}

            # Recent activity
            cursor.execute("""
                SELECT 'candidate' as type, id, name as title, status, created_at
                FROM candidates
                UNION ALL
                SELECT 'job' as type, id, title, status, created_at
                FROM jobs
                ORDER BY created_at DESC
                LIMIT 20
            """)
            recent_activity = [dict(row) for row in cursor.fetchall()]

            conn.close()

            return {
                "jobs_by_status": jobs_by_status,
                "candidates_by_status": candidates_by_status,
                "avg_ratings": avg_ratings,
                "candidates_by_country": candidates_by_country,
                "experience_distribution": experience_distribution,
                "recent_activity": recent_activity
            }
        except Exception as e:
            logger.error(f"Error getting analytics data: {e}")
            return {}

class AIAgentManager:
    def __init__(self, groq_api_key: str = None):
        self.groq_client = Groq(api_key=groq_api_key) if groq_api_key else None
        self.db_manager = DatabaseManager()
        self.model = "mixtral-8x7b-32768"  # Default model

    def set_model(self, model_name: str):
        """Set the AI model to use"""
        self.model = model_name

    def generate_job_description(self, role_name: str, keywords: List[str],
                               department: str = None, location: str = None,
                               employment_type: str = None) -> str:
        """Agent 1: Job Description Generator"""
        if not self.groq_client:
            return self._fallback_job_description(role_name, keywords)

        prompt = f"""
        Create a comprehensive job description for the role: {role_name}

        Keywords/Skills: {', '.join(keywords)}
        Department: {department or 'Not specified'}
        Location: {location or 'Not specified'}
        Employment Type: {employment_type or 'Not specified'}

        Structure the job description with:
        1. Role Overview
        2. Key Responsibilities
        3. Required Skills & Qualifications
        4. Preferred Experience
        5. What We Offer

        Make it professional, engaging, and detailed for LinkedIn posting.
        """

        try:
            response = self.groq_client.chat.completions.create(
                messages=[{"role": "user", "content": prompt}],
                model=self.model,
                temperature=0.7,
                max_tokens=1500
            )
            return response.choices[0].message.content
        except Exception as e:
            logger.error(f"Error generating job description: {e}")
            return self._fallback_job_description(role_name, keywords)

    def _fallback_job_description(self, role_name: str, keywords: List[str]) -> str:
        """Fallback method when AI generation fails"""
        return f"""
        # {role_name}

        ## Role Overview
        We are seeking a talented {role_name} to join our dynamic team. This role offers an exciting opportunity to work with cutting-edge technologies and contribute to innovative projects.

        ## Key Responsibilities
        • Lead and execute projects related to {', '.join(keywords[:3])}
        • Collaborate with cross-functional teams to deliver high-quality solutions
        • Drive innovation and implement best practices
        • Stay updated with industry trends and technologies

        ## Required Skills & Qualifications
        • Proficiency in {', '.join(keywords)}
        • Strong problem-solving abilities and attention to detail
        • Excellent communication and teamwork skills
        • Bachelor's degree in a relevant field or equivalent experience

        ## Preferred Experience
        • 3+ years of experience in a similar role
        • Previous experience with {', '.join(keywords[:2])}
        • Knowledge of industry best practices

        ## What We Offer
        • Competitive salary and benefits package
        • Professional development opportunities
        • Flexible work environment
        • Collaborative and innovative team culture
        """

    def extract_text_from_file(self, uploaded_file) -> str:
        """Extract text from uploaded resume file"""
        try:
            # Get file extension
            file_extension = os.path.splitext(uploaded_file.name)[1].lower()

            # Create a temporary file
            with tempfile.NamedTemporaryFile(delete=False, suffix=file_extension) as temp_file:
                temp_file.write(uploaded_file.getvalue())
                temp_file_path = temp_file.name

            text = ""

            # Extract text based on file type
            if file_extension == '.pdf':
                with open(temp_file_path, 'rb') as file:
                    pdf_reader = PyPDF2.PdfReader(file)
                    for page_num in range(len(pdf_reader.pages)):
                        text += pdf_reader.pages[page_num].extract_text()

            elif file_extension in ['.docx', '.doc']:
                doc = docx.Document(temp_file_path)
                for para in doc.paragraphs:
                    text += para.text + "\n"

            elif file_extension == '.txt':
                with open(temp_file_path, 'r', encoding='utf-8', errors='ignore') as file:
                    text = file.read()

            # Clean up the temporary file
            os.unlink(temp_file_path)

            return text
        except Exception as e:
            logger.error(f"Error extracting text from file: {e}")
            return f"Error extracting text: {str(e)}\n\nPlease try a different file format."

    def analyze_cv(self, cv_text: str, job_description: str, job_keywords: List[str]) -> Dict:
        """Agent 3: CV Screening & Analysis"""
        if not self.groq_client or not cv_text:
            return self._fallback_cv_analysis(cv_text)

        prompt = f"""
        Analyze this CV against the job description and extract the following information:

        1. Name
        2. Email
        3. Country/Location
        4. Current Job Title
        5. Total Years of Experience (numeric value)
        6. Relevant Experience for this role (numeric value)
        7. Reason for applying (if mentioned)
        8. Notice Period (if mentioned)
        9. Rating out of 5 based on job fit (numeric value with one decimal place)
        10. Skills (list of technical and soft skills found in the CV)
        11. Education (highest degree and institution)
        12. Strengths (3 key strengths based on the CV)
        13. Weaknesses (areas that might need improvement based on job requirements)

        Job Keywords: {', '.join(job_keywords)}

        Job Description: {job_description[:1000]}...

        CV Text: {cv_text[:3000]}...

        Return as JSON format with these exact keys: name, email, country, current_job, total_experience, relevant_experience, application_reason, notice_period, rating, skills, education, strengths, weaknesses
        """

        try:
            response = self.groq_client.chat.completions.create(
                messages=[{"role": "user", "content": prompt}],
                model=self.model,
                temperature=0.3,
                max_tokens=1000
            )

            # Parse JSON response
            content = response.choices[0].message.content
            # Extract JSON from response
            json_match = re.search(r'\{.*\}', content, re.DOTALL)
            if json_match:
                result = json.loads(json_match.group())
                # Ensure rating is a float
                if 'rating' in result:
                    try:
                        result['rating'] = float(result['rating'])
                    except:
                        result['rating'] = 3.0
                return result
            else:
                return self._fallback_cv_analysis(cv_text)
        except Exception as e:
            logger.error(f"Error analyzing CV: {e}")
            return self._fallback_cv_analysis(cv_text)

    def _fallback_cv_analysis(self, cv_text: str) -> Dict:
        """Fallback method when AI analysis fails"""
        # Simple regex-based extraction as fallback
        email_match = re.search(r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b', cv_text)
        name_match = re.search(r'^([A-Z][a-z]+ [A-Z][a-z]+)', cv_text)

        return {
            "name": name_match.group() if name_match else "Candidate Name",
            "email": email_match.group() if email_match else "candidate@example.com",
            "country": "Unknown",
            "current_job": "Current Position",
            "total_experience": 3.0,
            "relevant_experience": 2.0,
            "application_reason": "Interested in the role",
            "notice_period": "30 days",
            "rating": 3.5,
            "skills": ["Communication", "Teamwork", "Problem Solving"],
            "education": "Bachelor's Degree",
            "strengths": ["Adaptability", "Technical Knowledge", "Communication"],
            "weaknesses": ["May need additional training in specific areas"]
        }

    def generate_interview_questions(self, job_title: str, job_description: str,
                                   candidate_skills: List[str], experience: float) -> List[str]:
        """Generate tailored interview questions based on job and candidate"""
        if not self.groq_client:
            return self._fallback_interview_questions(job_title)

        prompt = f"""
        Generate 10 tailored interview questions for a {job_title} position.

        Job Description: {job_description[:500]}...

        Candidate Skills: {', '.join(candidate_skills)}
        Candidate Experience: {experience} years

        Include:
        - 3 technical questions specific to the required skills
        - 3 behavioral questions relevant to the role
        - 2 questions about past experience and achievements
        - 1 question about career goals
        - 1 question about why they want this specific role

        Format each question as a separate item in a JSON array.
        """

        try:
            response = self.groq_client.chat.completions.create(
                messages=[{"role": "user", "content": prompt}],
                model=self.model,
                temperature=0.7,
                max_tokens=1000
            )

            content = response.choices[0].message.content
            # Extract JSON array from response
            json_match = re.search(r'\[.*\]', content, re.DOTALL)
            if json_match:
                questions = json.loads(json_match.group())
                return questions
            else:
                return self._fallback_interview_questions(job_title)
        except Exception as e:
            logger.error(f"Error generating interview questions: {e}")
            return self._fallback_interview_questions(job_title)

    def _fallback_interview_questions(self, job_title: str) -> List[str]:
        """Fallback interview questions when AI generation fails"""
        return [
            f"Can you tell us about your experience relevant to this {job_title} position?",
            "Describe a challenging project you worked on and how you overcame obstacles.",
            "How do you stay updated with the latest industry trends and technologies?",
            "Tell us about a time when you had to work under pressure to meet a deadline.",
            "How do you approach collaboration with team members from different backgrounds?",
            "What are your greatest professional strengths and weaknesses?",
            "Where do you see yourself professionally in 5 years?",
            "Why are you interested in joining our company specifically?",
            "How do you handle feedback and criticism?",
            "Do you have any questions for us about the role or company?"
        ]

    def evaluate_candidate_fit(self, job_description: str, candidate_resume: str,
                             interview_notes: str = None) -> Dict:
        """Evaluate candidate fit for the position based on resume and interview notes"""
        if not self.groq_client:
            return self._fallback_candidate_evaluation()

        prompt = f"""
        Evaluate this candidate's fit for the position based on their resume and interview notes.

        Job Description: {job_description[:500]}...

        Candidate Resume: {candidate_resume[:1000]}...

        Interview Notes: {interview_notes[:500] if interview_notes else "No interview conducted yet."}

        Provide an evaluation with:
        1. Overall fit score (1-5, with one decimal place)
        2. Key strengths (3-5 points)
        3. Areas of concern (if any)
        4. Recommendation (Hire, Consider, Reject)
        5. Justification for recommendation (2-3 sentences)

        Return as JSON format.
        """

        try:
            response = self.groq_client.chat.completions.create(
                messages=[{"role": "user", "content": prompt}],
                model=self.model,
                temperature=0.4,
                max_tokens=800
            )

            content = response.choices[0].message.content
            json_match = re.search(r'\{.*\}', content, re.DOTALL)
            if json_match:
                return json.loads(json_match.group())
            else:
                return self._fallback_candidate_evaluation()
        except Exception as e:
            logger.error(f"Error evaluating candidate: {e}")
            return self._fallback_candidate_evaluation()

    def _fallback_candidate_evaluation(self) -> Dict:
        """Fallback evaluation when AI evaluation fails"""
        return {
            "fit_score": 3.5,
            "strengths": [
                "Relevant technical skills",
                "Good communication",
                "Team player"
            ],
            "concerns": [
                "May need additional training in specific areas"
            ],
            "recommendation": "Consider",
            "justification": "The candidate has relevant skills but may require some additional training. Consider for roles where on-the-job learning is possible."
        }

    def generate_offer_letter(self, candidate_name: str, job_title: str,
                            company_name: str = "Our Company",
                            salary: str = None) -> str:
        """Generate a professional offer letter"""
        if not self.groq_client:
            return self._fallback_offer_letter(candidate_name, job_title, company_name)

        prompt = f"""
        Generate a professional job offer letter with the following details:

        Candidate Name: {candidate_name}
        Job Title: {job_title}
        Company Name: {company_name}
        Salary: {salary if salary else "Competitive compensation package"}

        Include:
        1. Professional greeting
        2. Offer details (position, start date options)
        3. Compensation information
        4. Benefits overview
        5. Next steps
        6. Professional closing

        Make it warm, professional, and excited to welcome the candidate to the team.
        """

        try:
            response = self.groq_client.chat.completions.create(
                messages=[{"role": "user", "content": prompt}],
                model=self.model,
                temperature=0.7,
                max_tokens=1000
            )

            return response.choices[0].message.content
        except Exception as e:
            logger.error(f"Error generating offer letter: {e}")
            return self._fallback_offer_letter(candidate_name, job_title, company_name)

    def _fallback_offer_letter(self, candidate_name: str, job_title: str, company_name: str) -> str:
        """Fallback offer letter when AI generation fails"""
        today = datetime.now().strftime("%B %d, %Y")
        return f"""
        {today}

        Dear {candidate_name},

        We are pleased to offer you the position of {job_title} at {company_name}. We believe your skills and experience will be a valuable asset to our team.

        This offer is contingent upon the successful completion of reference checks and any required background verifications.

        Position Details:
        - Title: {job_title}
        - Status: Full-time
        - Start Date: To be determined (typically two weeks from acceptance)
        - Reporting to: Department Manager

        Compensation & Benefits:
        - Competitive salary package
        - Health, dental, and vision insurance
        - Retirement benefits
        - Paid time off
        - Professional development opportunities

        Please review this offer and let us know your decision within five business days. To accept, simply sign and return the enclosed copy of this letter.

        We are excited about the possibility of you joining our team and look forward to your positive response.

        Sincerely,

        HR Department
        {company_name}
        """

class NotificationManager:
    def __init__(self, smtp_server="smtp.gmail.com", smtp_port=587,
               sender_email=None, sender_password=None):
        self.smtp_server = smtp_server
        self.smtp_port = smtp_port
        self.sender_email = sender_email
        self.sender_password = sender_password
        self.email_enabled = bool(sender_email and sender_password)

    def configure_email(self, smtp_server: str, smtp_port: int,
                      sender_email: str, sender_password: str) -> bool:
        """Configure email settings"""
        self.smtp_server = smtp_server
        self.smtp_port = smtp_port
        self.sender_email = sender_email
        self.sender_password = sender_password
        self.email_enabled = bool(sender_email and sender_password)

        # Test connection
        if self.email_enabled:
            try:
                server = smtplib.SMTP(self.smtp_server, self.smtp_port)
                server.starttls()
                server.login(self.sender_email, self.sender_password)
                server.quit()
                return True
            except Exception as e:
                logger.error(f"Email configuration error: {e}")
                self.email_enabled = False
                return False
        return False

    def send_meeting_invite(self, candidate_email: str, candidate_name: str,
                          meeting_link: str, datetime_str: str, job_title: str) -> bool:
        """Agent 4: Meeting Invite Sender"""
        subject = f"Interview Invitation for {job_title} - {candidate_name}"
        body = f"""
        Dear {candidate_name},

        Thank you for your interest in the {job_title} position at our company. We were impressed with your application and would like to invite you for an interview.

        Meeting Details:
        Date & Time: {datetime_str}
        Meeting Link: {meeting_link}

        Please confirm your attendance by replying to this email. If this time doesn't work for you, please suggest a few alternatives.

        We look forward to speaking with you!

        Best regards,
        HR Team
        """

        return self._send_email(candidate_email, subject, body)

    def send_offer_letter(self, candidate_email: str, candidate_name: str,
                         job_title: str, offer_letter_text: str) -> bool:
        """Agent 6: Offer Letter Generator & Sender"""
        subject = f"Job Offer - {job_title}"
        body = offer_letter_text

        return self._send_email(candidate_email, subject, body)

    def send_status_update(self, candidate_email: str, candidate_name: str,
                         job_title: str, status: str, message: str = None) -> bool:
        """Send status update to candidate"""
        status_messages = {
            "screened": "Your application has been received and is being reviewed.",
            "interviewed": "Thank you for your interview. We'll be in touch soon.",
            "selected": "Congratulations! You've been selected for the next steps.",
            "rejected": "Thank you for your interest, but we've decided to pursue other candidates."
        }

        subject = f"Application Status Update - {job_title}"
        body = f"""
        Dear {candidate_name},

        {message or status_messages.get(status, "We have an update regarding your application.")}

        If you have any questions, please don't hesitate to contact us.

        Best regards,
        HR Team
        """

        return self._send_email(candidate_email, subject, body)

    def _send_email(self, to_email: str, subject: str, body: str) -> bool:
        """Send email with error handling and logging"""
        if self.email_enabled:
            try:
                msg = MIMEMultipart()
                msg['From'] = self.sender_email
                msg['To'] = to_email
                msg['Subject'] = subject

                msg.attach(MIMEText(body, 'plain'))

                server = smtplib.SMTP(self.smtp_server, self.smtp_port)
                server.starttls()
                server.login(self.sender_email, self.sender_password)
                server.send_message(msg)
                server.quit()

                logger.info(f"Email sent to {to_email}: {subject}")
                return True
            except Exception as e:
                logger.error(f"Error sending email: {e}")
                # Fall through to simulation

        # Simulate email sending for demo or when email is not configured
        st.success(f"📧 Email sent to {to_email}: {subject}")
        return True

def init_session_state():
    """Initialize session state variables"""
    if 'db_manager' not in st.session_state:
        st.session_state.db_manager = DatabaseManager()

    # Initialize AI agent manager with API key from session state or empty
    if 'agent_manager' not in st.session_state:
        groq_key = st.session_state.get('groq_api_key', '')
        st.session_state.agent_manager = AIAgentManager(groq_key)

    if 'notification_manager' not in st.session_state:
        st.session_state.notification_manager = NotificationManager()

    if 'chat_history' not in st.session_state:
        st.session_state.chat_history = []

    if 'messages' not in st.session_state:
        st.session_state.messages = [
            {"role": "assistant", "content": "👋 Hi! I'm your HR AI Assistant. I can help you with:\n\n• Check job and candidate status\n• Trigger screening processes\n• Send interview invites\n• Generate reports\n• Answer questions about the hiring pipeline\n\nWhat would you like to do today?"}
        ]

def main():
    # Initialize session state
    init_session_state()

    # Header
    st.markdown("""
    <div class="main-header">
        <h1>🤖 HR Automation Agent System</h1>
        <p>Complete end-to-end hiring process automation with AI agents</p>
    </div>
    """, unsafe_allow_html=True)

    # Sidebar for navigation and configuration
    with st.sidebar:
        # Company Logo Section
        st.markdown("""
        <div style='text-align: center; padding: 1rem; background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); border-radius: 10px; margin-bottom: 1rem;'>
            <div style='font-size: 3rem; margin-bottom: 0.5rem;'>🏢</div>
            <h3 style='color: white; margin: 0;'>Your Company</h3>
            <p style='color: #e8e8e8; margin: 0; font-size: 0.9rem;'>HR Automation Hub</p>
        </div>
        """, unsafe_allow_html=True)

        # API Configuration Section
        st.markdown("### 🔑 API Configuration")
        with st.expander("⚙️ Setup API Keys", expanded=False):
            # Groq API Key input
            groq_key_input = st.text_input(
                "Groq API Key",
                type="password",
                placeholder="Enter your Groq API key...",
                help="Get your API key from console.groq.com",
                key="groq_api_input"
            )

            if st.button("💾 Save Groq API Key", key="save_groq"):
                if groq_key_input:
                    st.session_state.groq_api_key = groq_key_input
                    # Reinitialize agent manager with new key
                    st.session_state.agent_manager = AIAgentManager(groq_key_input)
                    st.success("✅ Groq API key saved successfully!")
                    # Also save to database for persistence
                    st.session_state.db_manager.save_setting("groq_api_key", groq_key_input)
                    st.rerun()
                else:
                    st.error("Please enter a valid API key")

            # Show current status
            if hasattr(st.session_state, 'groq_api_key') and st.session_state.groq_api_key:
                st.success("🟢 Groq API Connected")
            else:
                st.warning("🟡 Groq API Not Connected")

            # LinkedIn API (placeholder for future)
            linkedin_token = st.text_input(
                "LinkedIn API Token (Optional)",
                type="password",
                placeholder="Future LinkedIn integration...",
                disabled=True,
                help="LinkedIn job posting integration - Coming soon!"
            )

        st.divider()

        # Navigation
        st.title("🎯 Navigation")
        page = st.radio("Choose Module:", [
            "🏠 Dashboard",
            "💼 Job Management",
            "👥 Candidate Pipeline",
            "📊 Analytics",
            "💬 AI Chat Assistant",
            "⚙️ Settings"
        ])

        st.divider()

        # System Status
        st.markdown("### 📊 System Status")
        jobs_count = len(st.session_state.db_manager.get_jobs())
        candidates_count = len(st.session_state.db_manager.get_candidates())

        col1, col2 = st.columns(2)
        with col1:
            st.metric("Jobs", jobs_count, delta=None)
        with col2:
            st.metric("Candidates", candidates_count, delta=None)

        # Quick Actions
        st.markdown("### ⚡ Quick Actions")
        if st.button("🆕 Create Job", use_container_width=True):
            st.session_state.quick_action = "create_job"
        if st.button("➕ Add Candidate", use_container_width=True):
            st.session_state.quick_action = "add_candidate"
        if st.button("📊 View Analytics", use_container_width=True):
            st.session_state.quick_action = "analytics"

    # Handle quick actions from sidebar
    if hasattr(st.session_state, 'quick_action'):
        if st.session_state.quick_action == "create_job":
            page = "💼 Job Management"
        elif st.session_state.quick_action == "add_candidate":
            page = "👥 Candidate Pipeline"
        elif st.session_state.quick_action == "analytics":
            page = "📊 Analytics"
        # Clear the quick action
        del st.session_state.quick_action

    # Main content based on selected page
    if "Dashboard" in page:
        show_dashboard()
    elif "Job Management" in page:
        show_job_management()
    elif "Candidate Pipeline" in page:
        show_candidate_pipeline()
    elif "Analytics" in page:
        show_analytics()
    elif "AI Chat Assistant" in page:
        show_chat_interface()
    elif "Settings" in page:
        show_settings()

    # Footer
    st.markdown("""
    ---
    <div style='text-align: center; color: #666; padding: 20px;'>
        <p>🤖 <strong>HR Automation Agent System v1.0</strong></p>
        <p>Powered by CrewAI • Groq Cloud • Streamlit</p>
        <p>End-to-end hiring process automation with AI agents</p>
    </div>
    """, unsafe_allow_html=True)

def show_dashboard():
    st.header("📊 HR Dashboard")

    # Get data for dashboard
    jobs = st.session_state.db_manager.get_jobs()
    candidates = st.session_state.db_manager.get_candidates()

    # Key metrics in cards
    st.markdown("### Key Metrics")
    col1, col2, col3, col4 = st.columns(4)

    with col1:
        st.markdown("""
        <div class="dashboard-metric">
            <h1>{}</h1>
            <p>Total Jobs</p>
        </div>
        """.format(len(jobs)), unsafe_allow_html=True)

    with col2:
        active_jobs = len([j for j in jobs if j.status == 'active'])
        st.markdown("""
        <div class="dashboard-metric">
            <h1>{}</h1>
            <p>Active Jobs</p>
        </div>
        """.format(active_jobs), unsafe_allow_html=True)

    with col3:
        st.markdown("""
        <div class="dashboard-metric">
            <h1>{}</h1>
            <p>Total Candidates</p>
        </div>
        """.format(len(candidates)), unsafe_allow_html=True)

    with col4:
        shortlisted = len([c for c in candidates if c.rating >= 4.0])
        st.markdown("""
        <div class="dashboard-metric">
            <h1>{}</h1>
            <p>Shortlisted</p>
        </div>
        """.format(shortlisted), unsafe_allow_html=True)

    # Recent activity and insights
    col1, col2 = st.columns([3, 2])

    with col1:
        st.markdown("### 📈 Recent Activity")

        # Combine recent jobs and candidates
        recent_items = []

        for job in jobs[:5]:
            recent_items.append({
                "type": "job",
                "title": job.title,
                "status": job.status,
                "date": job.created_at[:10],
                "id": job.id
            })

        for candidate in candidates[:5]:
            recent_items.append({
                "type": "candidate",
                "title": candidate.name,
                "status": candidate.status,
                "date": candidate.created_at[:10],
                "id": candidate.id
            })

        # Sort by date
        recent_items.sort(key=lambda x: x["date"], reverse=True)

        for item in recent_items[:10]:
            icon = "💼" if item["type"] == "job" else "👤"
            status_class = f"status-{item['status']}"

            st.markdown(f"""
            <div class="agent-card">
                {icon} <strong>{item["title"]}</strong><br>
                <span class="{status_class}">● {item["status"].title()}</span> | {item["date"]}
            </div>
            """, unsafe_allow_html=True)

    with col2:
        st.markdown("### 🔍 Quick Insights")

        # Calculate insights
        if candidates:
            avg_rating = sum(c.rating for c in candidates) / len(candidates)
            status_counts = {}
            for c in candidates:
                status_counts[c.status] = status_counts.get(c.status, 0) + 1

            # Display insights
            st.markdown(f"**Average Candidate Rating:** {avg_rating:.1f}/5")

            # Status breakdown
            st.markdown("**Application Status:**")
            for status, count in status_counts.items():
                st.markdown(f"- {status.title()}: {count}")

            # Top candidates
            st.markdown("**Top Candidates:**")
            top_candidates = sorted(candidates, key=lambda x: x.rating, reverse=True)[:3]
            for candidate in top_candidates:
                rating_stars = "⭐" * int(candidate.rating)
                st.markdown(f"- {candidate.name} ({rating_stars})")
        else:
            st.info("No candidate data available yet. Add candidates to see insights.")

    # Job and candidate overview
    st.markdown("### 📋 Job Overview")

    if jobs:
        job_data = []
        for job in jobs:
            job_candidates = [c for c in candidates if c.job_id == job.id]
            job_data.append({
                "Title": job.title,
                "Status": job.status.title(),
                "Applications": len(job_candidates),
                "Avg Rating": f"{sum(c.rating for c in job_candidates) / len(job_candidates):.1f}/5" if job_candidates else "N/A",
                "Created": job.created_at[:10]
            })

        st.dataframe(pd.DataFrame(job_data), use_container_width=True)
    else:
        st.info("No jobs created yet. Create your first job in the Job Management section.")

    # Action items
    st.markdown("### ✅ Action Items")

    action_items = []

    # Check for jobs without candidates
    empty_jobs = [j for j in jobs if j.status == 'active' and j.application_count == 0]
    if empty_jobs:
        action_items.append(f"📢 {len(empty_jobs)} active jobs have no applications yet")

    # Check for candidates needing review
    applied_candidates = len([c for c in candidates if c.status == 'applied'])
    if applied_candidates > 0:
        action_items.append(f"🔍 {applied_candidates} candidates need screening")

    # Check for interviewed candidates
    interviewed_candidates = len([c for c in candidates if c.status == 'interviewed'])
    if interviewed_candidates > 0:
        action_items.append(f"📝 {interviewed_candidates} candidates have completed interviews")

    # Display action items
    if action_items:
        for item in action_items:
            st.markdown(f"- {item}")
    else:
        st.success("✅ No pending action items!")

def show_job_management():
    st.header("💼 Job Management")

    tab1, tab2 = st.tabs(["Create New Job", "Manage Existing Jobs"])

    with tab1:
        st.subheader("🆕 Create Job Description")

        with st.form("job_creation"):
            col1, col2 = st.columns(2)
            with col1:
                role_name = st.text_input("Job Title/Role Name*", placeholder="e.g., Senior Python Developer")
                department = st.selectbox("Department", ["Engineering", "Marketing", "Sales", "HR", "Finance", "Operations", "Product", "Design", "Customer Support", "Other"])

            with col2:
                location = st.text_input("Location", placeholder="e.g., Remote, New York, etc.")
                employment_type = st.selectbox("Employment Type", ["Full-time", "Part-time", "Contract", "Internship", "Freelance"])

            keywords = st.text_area("Keywords/Skills (comma-separated)*",
                                   placeholder="Python, Django, REST APIs, AWS, Docker")

            salary_range = st.text_input("Salary Range (Optional)", placeholder="e.g., $80,000-$100,000")

            col1, col2 = st.columns(2)
            with col1:
                auto_post = st.checkbox("Auto-post to LinkedIn", value=True)
            with col2:
                auto_screen = st.checkbox("Enable auto-screening", value=True)

            if st.form_submit_button("🚀 Generate Job Description", type="primary"):
                if role_name and keywords:
                    # Check if Groq API is configured
                    if not hasattr(st.session_state, 'groq_api_key') or not st.session_state.groq_api_key:
                        st.warning("⚠️ Groq API key not configured. Please add your API key in the sidebar for AI-powered job description generation. Using fallback generation...")

                    with st.spinner("🤖 AI Agent generating job description..."):
                        keywords_list = [k.strip() for k in keywords.split(",")]
                        job_desc = st.session_state.agent_manager.generate_job_description(
                            role_name, keywords_list, department, location, employment_type
                        )

                        # Save job to database
                        job = Job(
                            id=str(uuid.uuid4()),
                            title=role_name,
                            description=job_desc,
                            keywords=keywords_list,
                            status="draft",
                            created_at=datetime.now().isoformat(),
                            department=department,
                            location=location,
                            employment_type=employment_type,
                            salary_range=salary_range
                        )

                        if st.session_state.db_manager.save_job(job):
                            st.success("✅ Job description generated and saved successfully!")

                            st.markdown("### Generated Job Description:")
                            st.markdown(job_desc)

                            if auto_post:
                                # Simulate LinkedIn posting
                                job.status = "active"
                                job.posted_at = datetime.now().isoformat()
                                st.session_state.db_manager.save_job(job)
                                st.success("📱 Job posted to LinkedIn successfully!")
                        else:
                            st.error("❌ Error saving job to database")
                else:
                    st.error("Please fill in required fields (Role Name and Keywords)")

    with tab2:
        st.subheader("📋 Existing Jobs")
        jobs = st.session_state.db_manager.get_jobs()

        # Filter options
        col1, col2 = st.columns(2)
        with col1:
            status_filter = st.selectbox(
                "Filter by Status:",
                ["All", "draft", "active", "paused", "closed"],
                key="job_status_filter"
            )

        with col2:
            sort_by = st.selectbox(
                "Sort by:",
                ["Newest First", "Oldest First", "Title A-Z"],
                key="job_sort_by"
            )

        # Apply filters
        filtered_jobs = jobs
        if status_filter != "All":
            filtered_jobs = [j for j in filtered_jobs if j.status == status_filter]

        # Apply sorting
        if sort_by == "Newest First":
            filtered_jobs.sort(key=lambda x: x.created_at, reverse=True)
        elif sort_by == "Oldest First":
            filtered_jobs.sort(key=lambda x: x.created_at)
        elif sort_by == "Title A-Z":
            filtered_jobs.sort(key=lambda x: x.title)

        if filtered_jobs:
            for job in filtered_jobs:
                with st.expander(f"{job.title} - {job.status.title()}", expanded=False):
                    col1, col2 = st.columns([2, 1])

                    with col1:
                        st.markdown(f"**Department:** {job.department or 'Not specified'}")
                        st.markdown(f"**Location:** {job.location or 'Not specified'}")
                        st.markdown(f"**Type:** {job.employment_type or 'Not specified'}")
                        st.markdown(f"**Created:** {job.created_at[:16].replace('T', ' ')}")
                        if job.posted_at:
                            st.markdown(f"**Posted:** {job.posted_at[:16].replace('T', ' ')}")
                        st.markdown(f"**Keywords:** {', '.join(job.keywords[:5])}")

                        # Show job description
                        with st.expander("View Job Description"):
                            st.markdown(job.description)

                    with col2:
                        # Job metrics
                        candidates = st.session_state.db_manager.get_candidates(job.id)
                        st.metric("Applications", len(candidates))

                        # Status counts
                        status_counts = {}
                        for c in candidates:
                            status_counts[c.status] = status_counts.get(c.status, 0) + 1

                        for status, count in status_counts.items():
                            st.markdown(f"- {status.title()}: {count}")

                        # Job actions
                        new_status = st.selectbox(
                            "Status",
                            ["draft", "active", "paused", "closed"],
                            index=["draft", "active", "paused", "closed"].index(job.status),
                            key=f"status_{job.id}"
                        )

                        if st.button(f"Update Status", key=f"update_{job.id}"):
                            job.status = new_status
                            if st.session_state.db_manager.save_job(job):
                                st.success(f"Job status updated to {new_status}")
                                st.rerun()
                            else:
                                st.error("Error updating job status")

                        if st.button(f"View Candidates", key=f"view_candidates_{job.id}"):
                            st.session_state.selected_job_id = job.id
                            st.rerun()

                        if job.status == "draft" and st.button(f"Post Job", key=f"post_{job.id}"):
                            job.status = "active"
                            job.posted_at = datetime.now().isoformat()
                            if st.session_state.db_manager.save_job(job):
                                st.success("Job posted successfully!")
                                st.rerun()
                            else:
                                st.error("Error posting job")
        else:
            st.info("No jobs found matching the selected filters.")

            if status_filter != "All":
                if st.button("Show All Jobs"):
                    st.session_state.job_status_filter = "All"
                    st.rerun()
            else:
                st.info("Create your first job in the 'Create New Job' tab!")

def show_candidate_pipeline():
    st.header("👥 Candidate Pipeline")

    jobs = st.session_state.db_manager.get_jobs()

    if not jobs:
        st.warning("No jobs available. Please create a job first in Job Management.")
        if st.button("Create Job Now"):
            st.session_state.quick_action = "create_job"
            st.rerun()
        return

    # Job selector
    job_options = {f"{job.title} ({job.status})": job.id for job in jobs if job.status != 'closed'}

    # Use selected job from session state if available
    selected_job_id = None
    if hasattr(st.session_state, 'selected_job_id'):
        selected_job_id = st.session_state.selected_job_id
        # Check if this job is in the options
        job_titles = {job_id: job_title for job_title, job_id in job_options.items()}
        if selected_job_id in job_titles:
            selected_job_key = job_titles[selected_job_id]
        else:
            selected_job_key = list(job_options.keys())[0] if job_options else None
            selected_job_id = job_options.get(selected_job_key)
        # Clear the session state
        del st.session_state.selected_job_id
    else:
        selected_job_key = list(job_options.keys())[0] if job_options else None
        selected_job_id = job_options.get(selected_job_key)

    if selected_job_key:
        selected_job_key = st.selectbox("Select Job:", list(job_options.keys()),
                                      index=list(job_options.keys()).index(selected_job_key))
        selected_job_id = job_options[selected_job_key]
    else:
        st.warning("No active jobs available. Please create or activate a job first.")
        return

    # Get selected job and candidates
    selected_job = st.session_state.db_manager.get_job_by_id(selected_job_id)
    candidates = st.session_state.db_manager.get_candidates(selected_job_id)

    tab1, tab2, tab3 = st.tabs(["Add Candidate", "Screen CVs", "Manage Pipeline"])

    with tab1:
        st.subheader("➕ Add New Candidate")

        with st.form("add_candidate"):
            col1, col2 = st.columns(2)

            with col1:
                name = st.text_input("Full Name*")
                email = st.text_input("Email*")
                country = st.text_input("Country/Location")
                current_job = st.text_input("Current Job Title")

            with col2:
                total_exp = st.number_input("Total Experience (years)", min_value=0.0, step=0.5)
                relevant_exp = st.number_input("Relevant Experience (years)", min_value=0.0, step=0.5)
                notice_period = st.text_input("Notice Period", placeholder="e.g., 30 days")
                rating = st.slider("Initial Rating", 1.0, 5.0, 3.0, step=0.1)

            application_reason = st.text_area("Why applying for this role?")

            if st.form_submit_button("➕ Add Candidate", type="primary"):
                if name and email:
                    # Validate email format
                    if not re.match(r"[^@]+@[^@]+\.[^@]+", email):
                        st.error("Please enter a valid email address")
                    else:
                        candidate = Candidate(
                            id=str(uuid.uuid4()),
                            name=name,
                            email=email,
                            country=country,
                            current_job=current_job,
                            total_experience=total_exp,
                            relevant_experience=relevant_exp,
                            application_reason=application_reason,
                            notice_period=notice_period,
                            rating=rating,
                            status="applied",
                            created_at=datetime.now().isoformat(),
                            job_id=selected_job_id
                        )

                        if st.session_state.db_manager.save_candidate(candidate, selected_job_id):
                            st.success(f"✅ Candidate {name} added successfully!")

                            # Add to process tracking
                            tracking_id = str(uuid.uuid4())
                            timestamp = datetime.now().isoformat()

                            st.rerun()
                        else:
                            st.error("Error saving candidate data")
                else:
                    st.error("Please fill in required fields (Name and Email)")

    with tab2:
        st.subheader("🔍 CV Screening")

        uploaded_file = st.file_uploader("Upload CV (PDF/DOC/TXT)", type=['pdf', 'doc', 'docx', 'txt'])

        if uploaded_file:
            with st.spinner("Extracting text from CV..."):
                cv_text = st.session_state.agent_manager.extract_text_from_file(uploaded_file)

                if cv_text:
                    st.success("✅ CV text extracted successfully!")

                    with st.expander("View Extracted Text", expanded=False):
                        st.text(cv_text[:1000] + ("..." if len(cv_text) > 1000 else ""))

                    if st.button("🤖 Screen CV with AI", type="primary"):
                        # Check if Groq API is configured
                        if not hasattr(st.session_state, 'groq_api_key') or not st.session_state.groq_api_key:
                            st.warning("⚠️ Groq API key not configured. Please add your API key in the sidebar for AI-powered CV analysis. Using fallback analysis...")

                        with st.spinner("🔍 AI Agent analyzing CV..."):
                            analysis = st.session_state.agent_manager.analyze_cv(
                                cv_text, selected_job.description, selected_job.keywords
                            )

                            st.success("✅ CV Analysis Complete!")

                            col1, col2 = st.columns(2)
                            with col1:
                                st.markdown("### Candidate Information")
                                st.markdown(f"**Name:** {analysis.get('name', 'Unknown')}")
                                st.markdown(f"**Email:** {analysis.get('email', 'Unknown')}")
                                st.markdown(f"**Current Job:** {analysis.get('current_job', 'Unknown')}")
                                st.markdown(f"**Location:** {analysis.get('country', 'Unknown')}")
                                st.markdown(f"**Experience:** {analysis.get('total_experience', 0)} years total, {analysis.get('relevant_experience', 0)} years relevant")
                                st.markdown(f"**Notice Period:** {analysis.get('notice_period', 'Unknown')}")

                                # Display skills if available
                                if 'skills' in analysis and analysis['skills']:
                                    st.markdown("**Skills:**")
                                    skills_list = analysis['skills'] if isinstance(analysis['skills'], list) else [s.strip() for s in analysis['skills'].split(',')]
                                    for skill in skills_list[:10]:
                                        st.markdown(f"- {skill}")

                            with col2:
                                st.markdown("### AI Evaluation")
                                rating = analysis.get('rating', 3.0)
                                rating_stars = "⭐" * int(rating)
                                st.markdown(f"**Rating:** {rating_stars} ({rating}/5)")

                                if 'strengths' in analysis:
                                    st.markdown("**Strengths:**")
                                    strengths = analysis['strengths'] if isinstance(analysis['strengths'], list) else [s.strip() for s in analysis['strengths'].split(',')]
                                    for strength in strengths:
                                        st.markdown(f"- {strength}")

                                if 'weaknesses' in analysis:
                                    st.markdown("**Areas for Improvement:**")
                                    weaknesses = analysis['weaknesses'] if isinstance(analysis['weaknesses'], list) else [w.strip() for w in analysis['weaknesses'].split(',')]
                                    for weakness in weaknesses:
                                        st.markdown(f"- {weakness}")

                                if 'education' in analysis:
                                    st.markdown(f"**Education:** {analysis['education']}")

                            if st.button("💾 Save Candidate"):
                                # Convert skills to list if it's a string
                                skills = analysis.get('skills', [])
                                if isinstance(skills, str):
                                    skills = [s.strip() for s in skills.split(',')]

                                candidate = Candidate(
                                    id=str(uuid.uuid4()),
                                    name=analysis.get("name", "Unknown"),
                                    email=analysis.get("email", "unknown@email.com"),
                                    country=analysis.get("country", "Unknown"),
                                    current_job=analysis.get("current_job", "Unknown"),
                                    total_experience=float(analysis.get("total_experience", 0)),
                                    relevant_experience=float(analysis.get("relevant_experience", 0)),
                                    application_reason=analysis.get("application_reason", ""),
                                    notice_period=analysis.get("notice_period", "Unknown"),
                                    rating=float(analysis.get("rating", 3.0)),
                                    status="screened",
                                    created_at=datetime.now().isoformat(),
                                    job_id=selected_job_id,
                                    resume_text=cv_text,
                                    skills=skills
                                )

                                if st.session_state.db_manager.save_candidate(candidate, selected_job_id):
                                    st.success("Candidate saved to pipeline!")
                                    st.rerun()
                                else:
                                    st.error("Error saving candidate data")
                else:
                    st.error("Could not extract text from the uploaded file. Please try a different file format.")

    with tab3:
        st.subheader("🏃‍♂️ Candidate Pipeline")

        if candidates:
            # Filter and sort options
            col1, col2, col3 = st.columns(3)
            with col1:
                status_filter = st.selectbox("Filter by Status:",
                    ["All", "applied", "screened", "interviewed", "selected", "rejected"])
            with col2:
                sort_by = st.selectbox("Sort by:", ["Rating", "Date", "Name"])
            with col3:
                min_rating = st.slider("Minimum Rating:", 1.0, 5.0, 1.0, step=0.5)

            # Filter candidates
            filtered_candidates = candidates
            if status_filter != "All":
                filtered_candidates = [c for c in filtered_candidates if c.status == status_filter]
            filtered_candidates = [c for c in filtered_candidates if c.rating >= min_rating]

            # Sort candidates
            if sort_by == "Rating":
                filtered_candidates.sort(key=lambda x: x.rating, reverse=True)
            elif sort_by == "Date":
                filtered_candidates.sort(key=lambda x: x.created_at, reverse=True)
            else:
                filtered_candidates.sort(key=lambda x: x.name)

            # Display candidates
            if filtered_candidates:
                for candidate in filtered_candidates:
                    with st.expander(f"{candidate.name} - {candidate.status.title()}", expanded=False):
                        col1, col2, col3 = st.columns([2, 2, 1])

                        with col1:
                            st.markdown(f"**Email:** {candidate.email}")
                            st.markdown(f"**Current Job:** {candidate.current_job}")
                            st.markdown(f"**Location:** {candidate.country}")
                            st.markdown(f"**Experience:** {candidate.total_experience}y total, {candidate.relevant_experience}y relevant")
                            st.markdown(f"**Notice Period:** {candidate.notice_period}")

                            if candidate.skills:
                                st.markdown("**Skills:**")
                                skills_text = ", ".join(candidate.skills[:5])
                                if len(candidate.skills) > 5:
                                    skills_text += f" and {len(candidate.skills) - 5} more"
                                st.markdown(skills_text)

                        with col2:
                            rating_stars = "⭐" * int(candidate.rating)
                            st.markdown(f"**Rating:** {rating_stars} ({candidate.rating}/5)")

                            st.markdown(f"**Status:** {candidate.status.title()}")
                            st.markdown(f"**Applied:** {candidate.created_at[:10]}")

                            if candidate.application_reason:
                                st.markdown("**Application Reason:**")
                                st.markdown(f"_{candidate.application_reason[:100]}{'...' if len(candidate.application_reason) > 100 else ''}_")

                            # Interview notes
                            if candidate.interview_notes:
                                with st.expander("Interview Notes", expanded=False):
                                    st.markdown(candidate.interview_notes)

                            # Add interview notes
                            if candidate.status in ['interviewed', 'selected']:
                                new_notes = st.text_area("Add/Update Interview Notes",
                                                      value=candidate.interview_notes or "",
                                                      key=f"notes_{candidate.id}")

                                if st.button("Save Notes", key=f"save_notes_{candidate.id}"):
                                    if st.session_state.db_manager.add_interview_notes(candidate.id, new_notes):
                                        st.success("Notes saved successfully!")
                                        st.rerun()
                                    else:
                                        st.error("Error saving notes")

                        with col3:
                            status_colors = {
                                "applied": "🟡", "screened": "🔵", "interviewed": "🟠",
                                "selected": "🟢", "rejected": "🔴"
                            }

                            new_status = st.selectbox(
                                "Change Status:",
                                ["applied", "screened", "interviewed", "selected", "rejected"],
                                index=["applied", "screened", "interviewed", "selected", "rejected"].index(candidate.status),
                                key=f"candidate_status_{candidate.id}"
                            )

                            if new_status != candidate.status:
                                if st.button(f"Update Status", key=f"update_status_{candidate.id}"):
                                    if st.session_state.db_manager.update_candidate_status(candidate.id, new_status):
                                        # Send notification email for status change
                                        st.session_state.notification_manager.send_status_update(
                                            candidate.email, candidate.name, selected_job.title, new_status
                                        )
                                        st.success(f"Status updated to {new_status}")
                                        st.rerun()
                                    else:
                                        st.error("Error updating status")

                            # Action buttons based on status
                            if candidate.status in ['screened', 'applied']:
                                if st.button(f"📅 Schedule Interview", key=f"interview_{candidate.id}"):
                                    meeting_link = "https://meet.google.com/abc-def-ghi"
                                    datetime_str = (datetime.now() + timedelta(days=2)).strftime("%Y-%m-%d 14:00")

                                    if st.session_state.notification_manager.send_meeting_invite(
                                        candidate.email, candidate.name, meeting_link, datetime_str, selected_job.title
                                    ):
                                        # Update status to interviewed
                                        st.session_state.db_manager.update_candidate_status(candidate.id, "interviewed")
                                        st.success("Interview invitation sent!")
                                        st.rerun()

                            if candidate.status == 'interviewed':
                                if st.button(f"📝 Generate Questions", key=f"questions_{candidate.id}"):
                                    with st.spinner("Generating interview questions..."):
                                        questions = st.session_state.agent_manager.generate_interview_questions(
                                            selected_job.title, selected_job.description,
                                            candidate.skills or selected_job.keywords,
                                            candidate.total_experience
                                        )

                                        st.markdown("### Interview Questions")
                                        for i, question in enumerate(questions[:10], 1):
                                            st.markdown(f"{i}. {question}")

                            if candidate.status in ['interviewed', 'selected']:
                                if st.button(f"📄 Send Offer", key=f"offer_{candidate.id}"):
                                    with st.spinner("Generating offer letter..."):
                                        offer_letter = st.session_state.agent_manager.generate_offer_letter(
                                            candidate.name, selected_job.title,
                                            "Your Company", selected_job.salary_range
                                        )

                                        if st.session_state.notification_manager.send_offer_letter(
                                            candidate.email, candidate.name, selected_job.title, offer_letter
                                        ):
                                            # Update status to selected
                                            st.session_state.db_manager.update_candidate_status(candidate.id, "selected")
                                            st.success("Offer letter sent!")
                                            st.rerun()
            else:
                st.info(f"No candidates found matching the selected filters.")
        else:
            st.info("No candidates found for this job. Add candidates using the tabs above!")

def show_analytics():
    st.header("📊 Analytics & Insights")

    # Get analytics data
    analytics_data = st.session_state.db_manager.get_analytics_data()

    if not analytics_data:
        st.warning("No data available for analytics.")
        return

    # Job metrics
    st.subheader("Job Metrics")
    col1, col2 = st.columns(2)

    with col1:
        # Jobs by status
        jobs_by_status = analytics_data.get('jobs_by_status', {})
        if jobs_by_status:
            st.markdown("#### Jobs by Status")
            jobs_df = pd.DataFrame({
                'Status': list(jobs_by_status.keys()),
                'Count': list(jobs_by_status.values())
            })
            st.bar_chart(jobs_df.set_index('Status'))
        else:
            st.info("No job data available")

    with col2:
        # Average ratings by job
        avg_ratings = analytics_data.get('avg_ratings', [])
        if avg_ratings:
            st.markdown("#### Average Candidate Rating by Job")
            ratings_df = pd.DataFrame(avg_ratings)
            ratings_df = ratings_df.sort_values('avg_rating', ascending=False)

            # Format for display
            ratings_df['avg_rating'] = ratings_df['avg_rating'].round(2)
            ratings_df.columns = ['Job Title', 'Avg Rating', 'Candidates']

            st.dataframe(ratings_df, use_container_width=True)
        else:
            st.info("No rating data available")

    # Candidate metrics
    st.subheader("Candidate Metrics")
    col1, col2 = st.columns(2)

    with col1:
        # Candidates by status
        candidates_by_status = analytics_data.get('candidates_by_status', {})
        if candidates_by_status:
            st.markdown("#### Candidates by Status")
            status_df = pd.DataFrame({
                'Status': list(candidates_by_status.keys()),
                'Count': list(candidates_by_status.values())
            })
            st.bar_chart(status_df.set_index('Status'))
        else:
            st.info("No candidate status data available")

    with col2:
        # Experience distribution
        experience_distribution = analytics_data.get('experience_distribution', {})
        if experience_distribution:
            st.markdown("#### Experience Distribution")
            exp_df = pd.DataFrame({
                'Experience Range': list(experience_distribution.keys()),
                'Count': list(experience_distribution.values())
            })
            st.bar_chart(exp_df.set_index('Experience Range'))
        else:
            st.info("No experience data available")

    # Geographic distribution
    st.subheader("Geographic Distribution")
    candidates_by_country = analytics_data.get('candidates_by_country', {})
    if candidates_by_country:
        country_df = pd.DataFrame({
            'Country': list(candidates_by_country.keys()),
            'Count': list(candidates_by_country.values())
        }).sort_values('Count', ascending=False)

        st.bar_chart(country_df.set_index('Country'))
    else:
        st.info("No geographic data available")

    # Recent activity
    st.subheader("Recent Activity")
    recent_activity = analytics_data.get('recent_activity', [])
    if recent_activity:
        activity_df = pd.DataFrame(recent_activity)

        # Format for display
        activity_df['created_at'] = activity_df['created_at'].apply(lambda x: x[:16].replace('T', ' '))
        activity_df['type'] = activity_df['type'].apply(lambda x: '💼 Job' if x == 'job' else '👤 Candidate')
        activity_df = activity_df[['type', 'title', 'status', 'created_at']]
        activity_df.columns = ['Type', 'Title', 'Status', 'Timestamp']

        st.dataframe(activity_df, use_container_width=True)
    else:
        st.info("No recent activity data available")

    # Download analytics data
    st.subheader("Export Analytics")

    col1, col2 = st.columns(2)

    with col1:
        if st.button("📊 Export Analytics Data", use_container_width=True):
            # Create export data
            export_data = {
                "jobs_by_status": pd.DataFrame({
                    'Status': list(analytics_data.get('jobs_by_status', {}).keys()),
                    'Count': list(analytics_data.get('jobs_by_status', {}).values())
                }),
                "candidates_by_status": pd.DataFrame({
                    'Status': list(analytics_data.get('candidates_by_status', {}).keys()),
                    'Count': list(analytics_data.get('candidates_by_status', {}).values())
                }),
                "candidates_by_country": pd.DataFrame({
                    'Country': list(analytics_data.get('candidates_by_country', {}).keys()),
                    'Count': list(analytics_data.get('candidates_by_country', {}).values())
                }),
                "experience_distribution": pd.DataFrame({
                    'Experience Range': list(analytics_data.get('experience_distribution', {}).keys()),
                    'Count': list(analytics_data.get('experience_distribution', {}).values())
                }),
                "avg_ratings": pd.DataFrame(analytics_data.get('avg_ratings', []))
            }

            # Create Excel file in memory
            output = io.BytesIO()
            with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
                for sheet_name, df in export_data.items():
                    if not df.empty:
                        df.to_excel(writer, sheet_name=sheet_name, index=False)

            # Provide download link
            st.download_button(
                label="📥 Download Excel Report",
                data=output.getvalue(),
                file_name="hr_analytics_report.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            )

    with col2:
        if st.button("📊 Generate PDF Report", use_container_width=True):
            st.info("PDF report generation will be available in the next update.")

def show_chat_interface():
    st.header("💬 AI Chat Assistant")
    st.markdown("Chat with your HR AI Agent to get updates, trigger automations, and manage the hiring process.")

    # Display chat messages
    for message in st.session_state.messages:
        with st.chat_message(message["role"]):
            st.markdown(message["content"])

    # Chat input
    if prompt := st.chat_input("Ask me about jobs, candidates, or trigger any automation..."):
        # Add user message
        st.session_state.messages.append({"role": "user", "content": prompt})
        with st.chat_message("user"):
            st.markdown(prompt)

        # Process user input and generate response
        with st.chat_message("assistant"):
            with st.spinner("Thinking..."):
                response = process_chat_command(prompt)
                st.markdown(response)
                st.session_state.messages.append({"role": "assistant", "content": response})

def process_chat_command(user_input: str) -> str:
    """Process user chat commands and return appropriate responses"""
    input_lower = user_input.lower()

    # Get current data
    jobs = st.session_state.db_manager.get_jobs()
    candidates = st.session_state.db_manager.get_candidates()

    # Status inquiries
    if any(word in input_lower for word in ["status", "update", "how many", "count"]):
        if "job" in input_lower:
            active_jobs = len([j for j in jobs if j.status == 'active'])
            return f"""📊 **Job Status Update:**

• Total jobs: {len(jobs)}
• Active jobs: {active_jobs}
• Draft jobs: {len([j for j in jobs if j.status == 'draft'])}
• Paused jobs: {len([j for j in jobs if j.status == 'paused'])}
• Closed jobs: {len([j for j in jobs if j.status == 'closed'])}

**Recent job:** {jobs[0].title if jobs else 'None'}

Would you like to see details about a specific job?"""

        elif "candidate" in input_lower:
            if not candidates:
                return "📊 **Candidate Status:** No candidates in the system yet."

            status_counts = {}
            for candidate in candidates:
                status_counts[candidate.status] = status_counts.get(candidate.status, 0) + 1

            status_text = "\n".join([f"• {status.title()}: {count}" for status, count in status_counts.items()])
            top_candidate = max(candidates, key=lambda x: x.rating)

            return f"""📊 **Candidate Pipeline Status:**
{status_text}

🏆 **Top Candidate:** {top_candidate.name} ({top_candidate.rating}/5 rating)
📧 **Latest Application:** {candidates[-1].name if candidates else 'None'}

Would you like to see candidates for a specific job or status?"""

    # Screening requests
    elif any(word in input_lower for word in ["screen", "analyze", "cv", "resume"]):
        return """🔍 **CV Screening Process:**

To screen candidates, you can:
1. Go to **Candidate Pipeline** → **Screen CVs**
2. Upload CV files (PDF/DOC/TXT)
3. AI will automatically extract and analyze candidate information
4. Review the AI analysis and save qualified candidates

The system supports PDF, DOC, DOCX, and TXT formats for resume parsing.

Would you like me to help you with anything specific about the screening process?"""

    # Interview scheduling
    elif any(word in input_lower for word in ["interview", "meeting", "schedule", "invite"]):
        if not candidates:
            return "📅 No candidates available for interviews yet. Please add candidates first."

        qualified_candidates = [c for c in candidates if c.rating >= 4.0 and c.status in ['screened', 'applied']]

        if qualified_candidates:
            candidate_list = "\n".join([f"• {c.name} ({c.rating}/5)" for c in qualified_candidates[:5]])
            return f"""📅 **Interview Scheduling:**

**Qualified candidates ready for interviews:**
{candidate_list}

To send interview invites:
1. Go to **Candidate Pipeline** → **Manage Pipeline**
2. Click **Schedule Interview** for any candidate
3. System will automatically send meeting links

The system can also generate tailored interview questions based on the job requirements and candidate skills.

Would you like me to trigger invites for all qualified candidates?"""
        else:
            return "📅 No qualified candidates (4+ rating) ready for interviews yet."

    # Offer letter requests
    elif any(word in input_lower for word in ["offer", "hire", "select"]):
        selected_candidates = [c for c in candidates if c.status == 'selected']
        interviewed_candidates = [c for c in candidates if c.status == 'interviewed' and c.rating >= 4.5]

        if selected_candidates:
            candidate_list = "\n".join([f"• {c.name}" for c in selected_candidates])
            return f"""📄 **Offer Letter Management:**

**Candidates ready for offers:**
{candidate_list}

To send offer letters:
1. Go to **Candidate Pipeline** → **Manage Pipeline**
2. Click **Send Offer** button for selected candidates
3. System will generate and email the offer letter

The AI will automatically generate a personalized offer letter based on the job details and candidate information.

Ready to proceed with offers?"""
        elif interviewed_candidates:
            return f"📄 **Potential Offer Candidates:**\nYou have {len(interviewed_candidates)} high-rated interviewed candidates. Consider moving them to 'selected' status first."
        else:
            return "📄 No candidates are currently ready for offer letters. Complete interviews first."

    # Job creation
    elif any(word in input_lower for word in ["create job", "new job", "post job", "job description"]):
        return """💼 **Job Creation Process:**

To create a new job:
1. Go to **Job Management** → **Create New Job**
2. Enter job title and required skills/keywords
3. AI will generate a professional job description
4. Enable auto-posting to LinkedIn
5. Enable auto-screening for incoming applications

The AI will create a comprehensive job description including:
• Role overview
• Key responsibilities
• Required skills & qualifications
• Preferred experience
• Benefits and perks

**Current Jobs:** """ + (f"{len(jobs)} jobs in system" if jobs else "No jobs created yet")

    # Analytics requests
    elif any(word in input_lower for word in ["analytics", "report", "statistics", "insights"]):
        if not candidates:
            return "📊 No data available for analytics yet. Add some candidates first!"

        avg_rating = sum(c.rating for c in candidates) / len(candidates)
        top_countries = {}
        for c in candidates:
            if c.country and c.country != "Unknown":
                top_countries[c.country] = top_countries.get(c.country, 0) + 1

        top_country = max(top_countries.items(), key=lambda x: x[1])[0] if top_countries else "N/A"

        return f"""📊 **HR Analytics Summary:**

• **Total Candidates:** {len(candidates)}
• **Average Rating:** {avg_rating:.1f}/5
• **Top Location:** {top_country}
• **Conversion Rate:** {len([c for c in candidates if c.status == 'selected'])/len(candidates)*100:.1f}%

📈 **Quick Insights:**
• {len([c for c in candidates if c.rating >= 4])} candidates rated 4+ stars
• {len([c for c in candidates if c.status == 'interviewed'])} interviews completed
• {len([c for c in candidates if c.status == 'selected'])} offers pending

Visit the **Analytics** page for detailed charts and insights, including:
• Job metrics
• Candidate pipeline analysis
• Geographic distribution
• Experience distribution
• Export options for reports"""

    # Clear data request
    elif any(word in input_lower for word in ["clear data", "delete all", "reset", "start over"]):
        return """⚠️ **Clear Data Request:**

To clear all data from the system:
1. Go to **Settings** → **Database Management**
2. Scroll down to the "Danger Zone" section
3. Click "Clear All Data" and confirm your choice

This action will delete all jobs and candidates but preserve your settings and email templates.

Would you like me to navigate you to the Settings page?"""

    # Help and general queries
    else:
        # Try to use AI to generate a response if Groq API is configured
        if hasattr(st.session_state, 'groq_api_key') and st.session_state.groq_api_key:
            try:
                # Get context about current system state
                jobs_count = len(jobs)
                candidates_count = len(candidates)
                active_jobs = len([j for j in jobs if j.status == 'active'])

                context = f"""
                Current system state:
                - {jobs_count} total jobs ({active_jobs} active)
                - {candidates_count} total candidates
                - Latest features: CV parsing, interview scheduling, offer letter generation
                """

                client = Groq(api_key=st.session_state.groq_api_key)
                response = client.chat.completions.create(
                    messages=[
                        {"role": "system", "content": "You are an HR Assistant AI helping with the HR Automation Agent System. Be helpful, concise, and informative. Suggest relevant features of the system."},
                        {"role": "user", "content": f"Context: {context}\n\nUser question: {user_input}"}
                    ],
                    model="mixtral-8x7b-32768",
                    temperature=0.7,
                    max_tokens=500
                )

                ai_response = response.choices[0].message.content
                if ai_response and len(ai_response) > 20:
                    return ai_response
            except Exception as e:
                logger.error(f"Error generating AI chat response: {e}")
                # Fall through to default response

        return """🤖 **HR AI Assistant - Available Commands:**

**Status & Updates:**
• "What's the status of candidates?"
• "How many active jobs do we have?"
• "Show me pipeline updates"

**Process Automation:**
• "Screen new CVs"
• "Schedule interviews for qualified candidates"
• "Send offer letters"
• "Create a new job posting"

**Analytics & Reports:**
• "Show me hiring analytics"
• "Generate candidate insights"
• "What's our conversion rate?"

**Quick Actions:**
• "Find top candidates"
• "Check interview pipeline"
• "Review job postings"

What specific task can I help you with?"""

def show_settings():
    st.header("⚙️ System Settings")

    tab1, tab2, tab3 = st.tabs(["API Configuration", "Email Settings", "Database Management"])

    with tab1:
        st.subheader("🔧 API Configuration")

        st.info("💡 **Tip:** You can also configure your Groq API key in the sidebar for quick access!")

        with st.form("api_settings"):
            current_groq_key = getattr(st.session_state, 'groq_api_key', '')
            groq_key = st.text_input("Groq API Key",
                                   value="***CONFIGURED***" if current_groq_key else "",
                                   type="password",
                                   help="Enter your Groq API key for AI processing")

            linkedin_token = st.text_input("LinkedIn API Token", type="password",
                                         help="LinkedIn token for job posting automation (Coming Soon!)",
                                         disabled=True)

            st.markdown("### 🤖 AI Model Settings")
            model_choice = st.selectbox("AI Model",
                ["llama-3.1-8b-instant", "gemma2-9b-it"])
            temperature = st.slider("AI Creativity", 0.0, 1.0, 0.7, step=0.1,
                                  help="Higher values make AI more creative, lower values more focused")

            col1, col2 = st.columns(2)
            with col1:
                if st.form_submit_button("💾 Save API Settings", type="primary"):
                    if groq_key and groq_key != "***CONFIGURED***":
                        st.session_state.groq_api_key = groq_key
                        st.session_state.agent_manager = AIAgentManager(groq_key)
                        st.session_state.agent_manager.set_model(model_choice)
                        st.session_state.db_manager.save_setting("groq_api_key", groq_key)
                        st.session_state.db_manager.save_setting("ai_model", model_choice)
                        st.session_state.db_manager.save_setting("ai_temperature", str(temperature))
                        st.success("✅ API settings saved successfully!")
                    else:
                        st.session_state.agent_manager.set_model(model_choice)
                        st.session_state.db_manager.save_setting("ai_model", model_choice)
                        st.session_state.db_manager.save_setting("ai_temperature", str(temperature))
                        st.success("✅ AI model settings saved!")

            with col2:
                if st.form_submit_button("🧪 Test API Connection"):
                    if hasattr(st.session_state, 'groq_api_key') and st.session_state.groq_api_key:
                        with st.spinner("Testing connection..."):
                            # Test API connection
                            try:
                                test_response = st.session_state.agent_manager.generate_job_description(
                                    "Test Role", ["test", "api"]
                                )
                                if "Test Role" in test_response:
                                    st.success("✅ API connection successful!")
                                else:
                                    st.error("❌ API test failed")
                            except Exception as e:
                                st.error(f"❌ API connection failed: {str(e)}")
                    else:
                        st.error("❌ Please configure API key first")

    with tab2:
        st.subheader("📧 Email Configuration")

        with st.form("email_settings"):
            smtp_server = st.text_input("SMTP Server", value="smtp.gmail.com")
            smtp_port = st.number_input("SMTP Port", value=587)
            sender_email = st.text_input("Sender Email")
            sender_password = st.text_input("Email Password", type="password")

            st.markdown("### Email Templates")

            template_type = st.selectbox(
                "Template Type",
                ["Interview Invite", "Offer Letter", "Rejection", "Application Received"]
            )

            template_subjects = {
                "Interview Invite": "Interview Invitation for {job_title} - {company_name}",
                "Offer Letter": "Job Offer: {job_title} at {company_name}",
                "Rejection": "Update on Your Application for {job_title}",
                "Application Received": "We've Received Your Application for {job_title}"
            }

            template_bodies = {
                "Interview Invite": """Dear {candidate_name},

Thank you for your interest in the {job_title} position at {company_name}. We were impressed with your application and would like to invite you for an interview.

Meeting Details:
Date & Time: {datetime}
Meeting Link: {meeting_link}

Please confirm your attendance by replying to this email. If this time doesn't work for you, please suggest a few alternatives.

We look forward to speaking with you!

Best regards,
HR Team
{company_name}""",
                "Offer Letter": """Dear {candidate_name},

We are pleased to offer you the position of {job_title} at {company_name}. We believe your skills and experience will be a valuable asset to our team.

Position Details:
- Title: {job_title}
- Status: Full-time
- Start Date: To be determined (typically two weeks from acceptance)
- Salary: {salary}

Please review this offer and let us know your decision within five business days.

We are excited about the possibility of you joining our team!

Best regards,
HR Team
{company_name}""",
                "Rejection": """Dear {candidate_name},

Thank you for your interest in the {job_title} position at {company_name} and for taking the time to apply.

After careful consideration, we have decided to move forward with other candidates whose qualifications better match our current needs.

We appreciate your interest in {company_name} and wish you success in your job search.

Best regards,
HR Team
{company_name}""",
                "Application Received": """Dear {candidate_name},

Thank you for applying for the {job_title} position at {company_name}. We have received your application and are currently reviewing it.

We will contact you if your qualifications match our requirements for the position.

Thank you for your interest in joining our team.

Best regards,
HR Team
{company_name}"""
            }

            template_subject = st.text_input(
                "Email Subject",
                value=template_subjects.get(template_type, "")
            )

            template_body = st.text_area(
                "Email Body",
                value=template_bodies.get(template_type, ""),
                height=300
            )

            if st.form_submit_button("💾 Save Email Settings"):
                # Save email configuration
                st.session_state.db_manager.save_setting("smtp_server", smtp_server)
                st.session_state.db_manager.save_setting("smtp_port", str(smtp_port))
                st.session_state.db_manager.save_setting("sender_email", sender_email)

                if sender_password and sender_password != "***CONFIGURED***":
                    # In production, encrypt this password
                    st.session_state.db_manager.save_setting("sender_password", sender_password)

                # Save email template
                template_id = hashlib.md5(template_type.encode()).hexdigest()
                st.session_state.db_manager.save_email_template(
                    template_id, template_type, template_subject, template_body
                )

                # Update notification manager
                st.session_state.notification_manager.configure_email(
                    smtp_server, smtp_port, sender_email,
                    sender_password if sender_password and sender_password != "***CONFIGURED***" else None
                )

                st.success("✅ Email settings saved successfully!")

    with tab3:
        st.subheader("🗄️ Database Management")

        col1, col2 = st.columns(2)

        with col1:
            st.markdown("### Database Stats")
            jobs = st.session_state.db_manager.get_jobs()
            candidates = st.session_state.db_manager.get_candidates()

            st.metric("Total Jobs", len(jobs))
            st.metric("Total Candidates", len(candidates))

            if st.button("🔄 Refresh Database"):
                st.rerun()

        with col2:
            st.markdown("### Database Actions")

            if st.button("📥 Export Data", help="Export all data to CSV"):
                # Create export data
                jobs_df = pd.DataFrame([{
                    "ID": job.id,
                    "Title": job.title,
                    "Status": job.status,
                    "Created": job.created_at,
                    "Keywords": ", ".join(job.keywords),
                    "Department": job.department,
                    "Location": job.location,
                    "Employment Type": job.employment_type,
                    "Salary Range": job.salary_range
                } for job in jobs])

                candidates_df = pd.DataFrame([{
                    "ID": candidate.id,
                    "Job ID": candidate.job_id,
                    "Name": candidate.name,
                    "Email": candidate.email,
                    "Country": candidate.country,
                    "Current Job": candidate.current_job,
                    "Total Experience": candidate.total_experience,
                    "Relevant Experience": candidate.relevant_experience,
                    "Rating": candidate.rating,
                    "Status": candidate.status,
                    "Created": candidate.created_at,
                    "Notice Period": candidate.notice_period,
                    "Skills": ", ".join(candidate.skills) if candidate.skills else ""
                } for candidate in candidates])

                # Create Excel file in memory
                output = io.BytesIO()
                with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
                    jobs_df.to_excel(writer, sheet_name="Jobs", index=False)
                    candidates_df.to_excel(writer, sheet_name="Candidates", index=False)

                # Provide download link
                st.download_button(
                    "📁 Download Excel Export",
                    output.getvalue(),
                    "hr_data_export.xlsx",
                    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                )

            st.markdown("---")
            st.markdown("""
            <div class="danger-zone">
                <h4>⚠️ Danger Zone</h4>
                <p>The following actions cannot be undone. Please proceed with caution.</p>
            </div>
            """, unsafe_allow_html=True)

            with st.expander("🗑️ Clear All Data", expanded=False):
                st.warning("This will delete all jobs and candidates from the database. Settings and email templates will be preserved.")

                confirm_text = st.text_input(
                    "Type 'DELETE ALL DATA' to confirm",
                    key="confirm_delete"
                )

                if st.button("🗑️ Clear All Data", key="clear_data_button"):
                    if confirm_text == "DELETE ALL DATA":
                        if st.session_state.db_manager.clear_all_data():
                            st.success("✅ All data has been cleared successfully!")
                            # Add a button to refresh the page
                            if st.button("Refresh Page"):
                                st.rerun()
                        else:
                            st.error("❌ Error clearing data")
                    else:
                        st.error("Confirmation text doesn't match. Please type 'DELETE ALL DATA' to confirm.")

if __name__ == "__main__":
    main()