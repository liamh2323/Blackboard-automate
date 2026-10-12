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

    def test_07_study_coverage_analyzer(self):
        from app import coverage

        # Create temporary markdown note in test downloads
        course_dir = Path("./test_downloads/Systems")
        course_dir.mkdir(parents=True, exist_ok=True)
        lec_file = course_dir / "week1_virtual_memory.md"
        with open(lec_file, "w", encoding="utf-8") as f:
            f.write("""# Lecture 1: Virtual Memory and Paging

## Learning Objectives
- Understand page tables and TLB
- Learn about page faults and swap space

## Paging Architecture
**Paging** divides virtual memory into fixed-size blocks called pages.
The **TLB** caches recent virtual-to-physical translations.
""")

        parsed = coverage.parse_markdown_note(lec_file)
        self.assertEqual(parsed["title"], "Lecture 1: Virtual Memory and Paging")
        self.assertIn("Paging Architecture", parsed["topics"])
        self.assertIn("Paging", parsed["key_concepts"])
        self.assertGreaterEqual(len(parsed["learning_objectives"]), 1)

        # Test report builder
        report = coverage.build_study_coverage_report("test_c1")
        self.assertGreaterEqual(len(report["courses"]), 1)
        c_report = report["courses"][0]
        self.assertEqual(c_report["course_id"], "test_c1")
        self.assertIn("agy", c_report["antigravity_command"])
        self.assertIn("Review", c_report["antigravity_prompt"])

        # Verify STUDY_PLAN.md was created in course dir
        self.assertTrue((course_dir / "STUDY_PLAN.md").exists())

    def test_08_smart_announcement_task_filtering(self):
        # 1. Non-actionable announcement should NOT create a task
        chatty_announcement = {
            "id": "ann_chatty",
            "course_id": "test_c1",
            "title": "Welcome to week 3!",
            "markdown_body": "Hope you all had a nice weekend. Lecture slides are uploaded. Let me know if you have questions."
        }
        extracted_none = extract_tasks_from_announcement_text(chatty_announcement, "Systems Programming I")
        self.assertEqual(len(extracted_none), 0)

        # 2. Actionable announcement with multiple sentences should only create ONE consolidated task (not 5 spam tasks)
        actionable_announcement = {
            "id": "ann_action",
            "course_id": "test_c1",
            "title": "Mandatory Assignment Submission Deadline",
            "markdown_body": "Important notice.\nPlease submit your assignment by Friday 24th October at 5pm.\nPenalties will apply.\nDo not forget to upload to Blackboard."
        }
        extracted_one = extract_tasks_from_announcement_text(actionable_announcement, "Systems Programming I")
        self.assertEqual(len(extracted_one), 1)
        self.assertEqual(extracted_one[0]["id"], "ann_task_ann_action")
        self.assertEqual(extracted_one[0]["priority"], "high")

    def test_09_scheduler_status_and_config(self):
        from app import scheduler
        client = TestClient(app)

        # GET scheduler info
        res = client.get("/api/sync/status")
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertIn("is_syncing", data)
        self.assertIn("auto_sync_enabled", data)
        self.assertIn("interval_hours", data)

        # POST reconfigure scheduler
        res_cfg = client.post("/api/scheduler/config", json={"enabled": True, "interval_hours": 2.0})
        self.assertEqual(res_cfg.status_code, 200)
        self.assertEqual(res_cfg.json()["interval_hours"], 2.0)
        self.assertEqual(db.get_setting("auto_sync_interval_hours"), "2.0")

    def test_10_task_filtering_and_update(self):
        # Create different task types
        db.upsert_task("t_assign", "test_c1", "HW 1", "desc", "2026-10-30", "assignment", "s1", "high")
        db.upsert_task("t_study", "test_c1", "Review Slides", "desc", None, "study", "s2", "low")

        # Filter by source_type
        assignments = db.get_tasks(source_type="assignment")
        self.assertTrue(any(t["id"] == "t_assign" for t in assignments))
        self.assertFalse(any(t["id"] == "t_study" for t in assignments))

        studies = db.get_tasks(source_type="study")
        self.assertTrue(any(t["id"] == "t_study" for t in studies))

        # Update task
        db.update_task("t_study", title="Review Slides Week 1", priority="medium")
        updated = [t for t in db.get_tasks() if t["id"] == "t_study"][0]
        self.assertEqual(updated["title"], "Review Slides Week 1")
        self.assertEqual(updated["priority"], "medium")

    def test_11_coverage_endpoint(self):
        client = TestClient(app)
        res = client.get("/api/coverage")
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertIn("courses", data)
        self.assertIn("total_courses", data)

if __name__ == "__main__":
    unittest.main()
