import os
import unittest
from pathlib import Path

# Set test environment
os.environ["DOWNLOAD_DIR"] = "./test_downloads"
os.environ["DATA_DIR"] = "./test_data"

from app import database as db
from app.converter import html_to_markdown
from app.tasks import extract_tasks_from_announcement_text
from app import calendar as cal
from fastapi.testclient import TestClient
from app.server import app

class TestBlackboardAutomate(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        Path("./test_data").mkdir(exist_ok=True)
        Path("./test_downloads").mkdir(exist_ok=True)
        db.init_db()

    @classmethod
    def tearDownClass(cls):
        import shutil
        shutil.rmtree("./test_data", ignore_errors=True)
        shutil.rmtree("./test_downloads", ignore_errors=True)

    def test_01_database_and_courses(self):
        db.upsert_course("test_c1", "CS2001", "Systems Programming I", "./test_downloads/Systems")
        courses = db.get_courses()
        self.assertTrue(any(c["id"] == "test_c1" for c in courses))

        # Toggle course
        db.toggle_course_active("test_c1", False)
        active_courses = db.get_courses(only_active=True)
        self.assertFalse(any(c["id"] == "test_c1" for c in active_courses))

        db.toggle_course_active("test_c1", True)

    def test_02_task_management(self):
        db.upsert_task(
            tid="task_1",
            cid="test_c1",
            title="Lab 1 Submission",
            description="Complete exercise 1 to 4",
            due_date="2026-10-25T23:59:00Z",
            source_type="assignment",
            source_id="item_123"
        )
        tasks = db.get_tasks(completed=False)
        self.assertTrue(any(t["id"] == "task_1" for t in tasks))

        # Complete task
        db.toggle_task_completed("task_1", True)
        completed_tasks = db.get_tasks(completed=True)
        self.assertTrue(any(t["id"] == "task_1" for t in completed_tasks))

    def test_03_html_to_markdown_converter(self):
        sample_html = """
        <h3>Assignment 2 Instructions</h3>
        <p>Please <strong>submit your lab report</strong> by Friday 5pm on Blackboard.</p>
        <ul>
            <li>Task A: Setup</li>
            <li>Task B: Implementation</li>
        </ul>
        """
        md = html_to_markdown(sample_html)
        self.assertIn("### Assignment 2 Instructions", md)
        self.assertIn("submit your lab report", md)
        self.assertIn("Task A: Setup", md)

        # Test Ultra dictionary payload format
        dict_payload = {"rawText": "<p>Ultra Announcement <strong>content</strong></p>"}
        md_dict = html_to_markdown(dict_payload)
        self.assertIn("Ultra Announcement **content**", md_dict)

        # Test empty / None handling
        self.assertEqual(html_to_markdown(None), "")
        self.assertEqual(html_to_markdown({}), "")

    def test_04_announcement_task_extraction(self):
        announcement = {
            "id": "ann_99",
            "course_id": "test_c1",
            "title": "Important: Project Deliverable Due Date",
            "markdown_body": "Hello class,\n\nPlease remember you must submit the final project proposal by Friday 24th October at 5pm.\nPenalties will apply for late submissions."
        }
        extracted = extract_tasks_from_announcement_text(announcement, "Systems Programming I")
        self.assertGreaterEqual(len(extracted), 1)
        self.assertIn("Systems Programming I", extracted[0]["title"])

    def test_05_calendar_generation(self):
        db.upsert_task(
            tid="cal_task_1",
            cid="test_c1",
            title="Project Milestone 1",
            description="Submit code via git",
            due_date="2026-11-01T17:00:00Z",
            source_type="assignment",
            source_id="assign_1"
        )
        ics_text = cal.generate_deadlines_ics()
        self.assertIn("BEGIN:VCALENDAR", ics_text)
        self.assertIn("SUMMARY:🎯 Project Milestone 1", ics_text)
        self.assertIn("END:VCALENDAR", ics_text)

    def test_06_fastapi_endpoints(self):
        client = TestClient(app)

        # Stats
        res_stats = client.get("/api/stats")
        self.assertEqual(res_stats.status_code, 200)
        self.assertIn("active_courses", res_stats.json())

        # Courses
        res_courses = client.get("/api/courses")
        self.assertEqual(res_courses.status_code, 200)
        self.assertIsInstance(res_courses.json(), list)

        # Tasks
        res_tasks = client.get("/api/tasks")
        self.assertEqual(res_tasks.status_code, 200)

        # Calendar feed
        res_cal = client.get("/calendar/deadlines.ics")
        self.assertEqual(res_cal.status_code, 200)
        self.assertIn("text/calendar", res_cal.headers["content-type"])
        self.assertIn("BEGIN:VCALENDAR", res_cal.text)

if __name__ == "__main__":
    unittest.main()
