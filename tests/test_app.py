import os
import unittest
import tempfile
from pathlib import Path

# Set test environment: probe if current directory is writable, otherwise use /tmp
try:
    _probe = Path("./test_probe.tmp")
    _probe.touch()
    _probe.unlink()
    TEST_DIR_BASE = Path(".")
except OSError:
    TEST_DIR_BASE = Path(tempfile.gettempdir()) / "bb_test"

TEST_DATA_DIR = (TEST_DIR_BASE / "test_data").resolve()
TEST_DOWNLOAD_DIR = (TEST_DIR_BASE / "test_downloads").resolve()

os.environ["DOWNLOAD_DIR"] = str(TEST_DOWNLOAD_DIR)
os.environ["DATA_DIR"] = str(TEST_DATA_DIR)

from app import database as db
from app.converter import html_to_markdown
from app.tasks import extract_tasks_from_announcement_text
from app import calendar as cal
from fastapi.testclient import TestClient
from app.server import app

class TestBlackboardAutomate(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        TEST_DATA_DIR.mkdir(parents=True, exist_ok=True)
        TEST_DOWNLOAD_DIR.mkdir(parents=True, exist_ok=True)
        db.init_db()

    @classmethod
    def tearDownClass(cls):
        import shutil
        shutil.rmtree(TEST_DATA_DIR, ignore_errors=True)
        shutil.rmtree(TEST_DOWNLOAD_DIR, ignore_errors=True)

    def test_01_database_and_courses(self):
        db.upsert_course("test_c1", "CS2001", "Systems Programming I", str(TEST_DOWNLOAD_DIR / "Systems"))
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
        course_dir = TEST_DOWNLOAD_DIR / "Systems"
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

    def test_12_skip_mp4_downloads(self):
        from app.downloader import is_mp4_file, download_and_process_file

        # Check MP4 detection
        self.assertTrue(is_mp4_file("lecture_recording.mp4"))
        self.assertTrue(is_mp4_file("video.MP4"))
        self.assertTrue(is_mp4_file("screencast.m4v"))
        self.assertTrue(is_mp4_file("some_file", mime_type="video/mp4"))
        self.assertTrue(is_mp4_file("some_file", mime_type="video/x-m4v"))
        self.assertTrue(is_mp4_file("stream", url="https://example.com/video.mp4?token=123"))

        # Non-MP4 files
        self.assertFalse(is_mp4_file("slides.pdf"))
        self.assertFalse(is_mp4_file("lab.docx"))
        self.assertFalse(is_mp4_file("notes.txt", mime_type="text/plain"))

        # Mock page to verify it is NOT contacted when skipping
        class MockPage:
            def __init__(self):
                self.called = False
            @property
            def request(self):
                self.called = True
                return self
            def get(self, url):
                self.called = True
                raise RuntimeError("Network should not be contacted for skipped MP4s")

        mock_page = MockPage()
        item = {
            "fileName": "lecture_01.mp4",
            "permanentUrl": "/webapps/lecture_01.mp4",
            "fileSize": 1024 * 1024 * 50,
            "mimeType": "video/mp4"
        }
        course_folder = TEST_DOWNLOAD_DIR / "Systems"

        # When skip_mp4=True, verify it skips immediately without network requests
        downloaded, status = download_and_process_file(
            page=mock_page,
            base_url="https://example.com",
            course_id="test_c1",
            course_folder=course_folder,
            item=item,
            existing_index={"by_name": {}, "by_size": {}, "by_hash": {}},
            skip_mp4=True
        )
        self.assertFalse(downloaded)
        self.assertEqual(status, "skipped_mp4")
        self.assertFalse(mock_page.called)

    def test_13_app_settings_api(self):
        from app import config
        client = TestClient(app)

        # GET settings
        res_get = client.get("/api/settings")
        self.assertEqual(res_get.status_code, 200)
        initial = res_get.json()
        self.assertIn("download_dir", initial)
        self.assertIn("skip_mp4_downloads", initial)

        # POST updated settings
        custom_dl = TEST_DOWNLOAD_DIR / "custom_folder"
        res_post = client.post("/api/settings", json={
            "download_dir": str(custom_dl),
            "skip_mp4_downloads": False,
            "term_filter": "202627",
            "blackboard_url": "https://tcd.blackboard.com/",
            "auto_sync_enabled": True,
            "interval_hours": 4.0,
        })
        self.assertEqual(res_post.status_code, 200)
        updated = res_post.json()
        self.assertEqual(updated["download_dir"], str(custom_dl.resolve()))
        self.assertFalse(updated["skip_mp4_downloads"])
        self.assertEqual(updated["term_filter"], "202627")
        self.assertEqual(updated["blackboard_url"], "https://tcd.blackboard.com")
        self.assertTrue(custom_dl.exists())

        # Restore TEST_DOWNLOAD_DIR for subsequent tests
        config.update_runtime_settings(download_dir=str(TEST_DOWNLOAD_DIR), skip_mp4_downloads=True, term_filter="")

    def test_14_windows_browser_channels_and_icon(self):
        from app import auth, config
        import build_windows

        # Test Windows channel ordering
        orig_win = config.IS_WINDOWS
        orig_ch = config.BROWSER_CHANNEL
        try:
            config.IS_WINDOWS = True
            config.BROWSER_CHANNEL = "auto"
            candidates = auth.get_browser_channel_candidates()
            self.assertEqual(candidates[0], "msedge")
            self.assertIn("chrome", candidates)
        finally:
            config.IS_WINDOWS = orig_win
            config.BROWSER_CHANNEL = orig_ch

        # Test ICO generator
        ico_file = TEST_DATA_DIR / "test_icon.ico"
        build_windows.generate_app_icon(ico_file)
        self.assertTrue(ico_file.exists())
        self.assertGreater(ico_file.stat().st_size, 1000)

if __name__ == "__main__":
    unittest.main()
