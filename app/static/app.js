// Blackboard Automate Frontend Logic

let currentTaskFilter = 'pending';
let currentTypeFilter = '';
let currentCourseFilter = '';
let currentCoverageCourse = '';
let activeCourses = [];
let coverageData = null;
let schedulerInfo = null;

document.addEventListener('DOMContentLoaded', () => {
  initTabs();
  initSSELogs();
  loadAllData();
  setupEventListeners();

  // Periodic polling for status & scheduler countdown every 4 seconds
  setInterval(loadSchedulerStatus, 4000);
});

// --- Tab Management ---
function initTabs() {
  const tabs = document.querySelectorAll('.tab-btn');
  tabs.forEach(btn => {
    btn.addEventListener('click', () => {
      tabs.forEach(b => b.classList.remove('active'));
      document.querySelectorAll('.tab-content').forEach(c => c.classList.remove('active'));

      btn.classList.add('active');
      const targetId = btn.getAttribute('data-tab');
      const target = document.getElementById(targetId);
      if (target) target.classList.add('active');

      if (targetId === 'tab-coverage' && !coverageData) {
        loadStudyCoverage();
      }
    });
  });
}

// --- Event Listeners ---
function setupEventListeners() {
  // Sync Now Button
  document.getElementById('btn-sync').addEventListener('click', triggerSync);

  // 2FA Login Button
  document.getElementById('btn-login').addEventListener('click', triggerLogin);

  // Auto-Sync Settings Button
  document.getElementById('btn-autosync-settings').addEventListener('click', openAutoSyncModal);
  document.getElementById('btn-save-autosync').addEventListener('click', saveAutoSyncPreferences);

  // Calendar Modal Button
  document.getElementById('btn-calendar').addEventListener('click', openCalendarModal);

  // Antigravity Prompt Button
  document.getElementById('btn-copy-antigravity-prompt').addEventListener('click', openAntigravityModal);
  document.getElementById('btn-copy-prompt-action').addEventListener('click', copyAntigravityPromptToClipboard);

  // Refresh Coverage Button
  document.getElementById('btn-refresh-coverage').addEventListener('click', () => loadStudyCoverage(true));

  // Clear Logs
  document.getElementById('btn-clear-logs').addEventListener('click', () => {
    document.getElementById('console-logs').innerHTML = '';
  });

  // Task Status Filter Buttons (Pending / All / Completed)
  document.querySelectorAll('.filter-btn').forEach(btn => {
    btn.addEventListener('click', () => {
      document.querySelectorAll('.filter-btn').forEach(b => b.classList.remove('active'));
      btn.classList.add('active');
      currentTaskFilter = btn.getAttribute('data-filter');
      loadTasks();
    });
  });

  // Task Type Filter Buttons (All / Assignment / Action Item / Manual / Study)
  document.querySelectorAll('.type-filter-btn').forEach(btn => {
    btn.addEventListener('click', () => {
      document.querySelectorAll('.type-filter-btn').forEach(b => b.classList.remove('active'));
      btn.classList.add('active');
      currentTypeFilter = btn.getAttribute('data-type');
      loadTasks();
    });
  });

  // Course Filter for Tasks
  document.getElementById('todo-course-filter').addEventListener('change', (e) => {
    currentCourseFilter = e.target.value;
    loadTasks();
  });

  // Course Selector for Study Coverage
  document.getElementById('coverage-course-select').addEventListener('change', (e) => {
    currentCoverageCourse = e.target.value;
    renderCoverageUI();
  });

  // Add Task Form
  document.getElementById('form-add-task').addEventListener('submit', async (e) => {
    e.preventDefault();
    const courseSelect = document.getElementById('new-task-course');
    const prioritySelect = document.getElementById('new-task-priority');
    const titleInput = document.getElementById('new-task-title');
    const dueInput = document.getElementById('new-task-due');

    const title = titleInput.value.trim();
    const course_id = courseSelect.value || null;
    const priority = prioritySelect.value || 'medium';
    const due_date = dueInput.value ? new Date(dueInput.value).toISOString() : null;

    if (!title) return;

    try {
      await fetch('/api/tasks', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ title, due_date, course_id, priority })
      });
      titleInput.value = '';
      dueInput.value = '';
      loadTasks();
      loadStats();
    } catch (err) {
      console.error('Failed to create task:', err);
    }
  });
}

// --- Data Loading ---
async function loadAllData() {
  await Promise.all([
    loadStats(),
    loadCourses(),
    loadTasks(),
    loadAnnouncements(),
    loadSchedulerStatus()
  ]);
}

async function loadStats() {
  try {
    const res = await fetch('/api/stats');
    const data = await res.json();
    document.getElementById('stat-courses').textContent = data.active_courses || 0;
    document.getElementById('stat-tasks').textContent = data.pending_tasks || 0;
    document.getElementById('stat-files').textContent = data.total_files || 0;
    document.getElementById('stat-markdown').textContent = data.converted_files || 0;
  } catch (err) {
    console.error('Error loading stats:', err);
  }
}

async function loadSchedulerStatus() {
  try {
    const res = await fetch('/api/sync/status');
    schedulerInfo = await res.json();
    const badge = document.getElementById('status-badge');

    if (schedulerInfo.is_syncing) {
      badge.textContent = '⚡ Syncing in Progress...';
      badge.style.color = '#38bdf8';
      badge.style.backgroundColor = 'rgba(56, 189, 248, 0.2)';
      badge.style.borderColor = '#38bdf8';
      return;
    }

    if (!schedulerInfo.auto_sync_enabled) {
      badge.textContent = 'Auto-Sync: Disabled';
      badge.style.color = '#94a3b8';
      badge.style.backgroundColor = 'rgba(148, 163, 184, 0.15)';
      return;
    }

    if (schedulerInfo.next_sync_time) {
      const now = new Date();
      const next = new Date(schedulerInfo.next_sync_time);
      const diffMs = next - now;

      if (diffMs <= 0) {
        badge.textContent = 'Auto-Sync: Imminent...';
      } else {
        const diffMins = Math.floor(diffMs / 60000);
        if (diffMins < 60) {
          badge.textContent = `Auto-Sync: in ${diffMins}m`;
        } else {
          const hours = Math.floor(diffMins / 60);
          const mins = diffMins % 60;
          badge.textContent = `Auto-Sync: in ${hours}h ${mins}m`;
        }
      }
      badge.style.color = '#a5b4fc';
      badge.style.backgroundColor = 'rgba(99, 102, 241, 0.15)';
    } else {
      badge.textContent = `Auto-Sync: Every ${schedulerInfo.interval_hours}h`;
    }
  } catch (err) {
    console.error('Error loading scheduler status:', err);
  }
}

async function loadCourses() {
  try {
    const res = await fetch('/api/courses');
    activeCourses = await res.json();

    // Populate Course Filter dropdowns
    const todoSelect = document.getElementById('todo-course-filter');
    const taskFormSelect = document.getElementById('new-task-course');
    const coverageSelect = document.getElementById('coverage-course-select');

    todoSelect.innerHTML = '<option value="">All Courses</option>';
    taskFormSelect.innerHTML = '<option value="">General (No Course)</option>';
    coverageSelect.innerHTML = '<option value="">All Active Modules</option>';

    activeCourses.forEach(c => {
      const opt1 = document.createElement('option');
      opt1.value = c.id;
      opt1.textContent = c.name;
      todoSelect.appendChild(opt1);

      const opt2 = document.createElement('option');
      opt2.value = c.id;
      opt2.textContent = c.name;
      taskFormSelect.appendChild(opt2);

      const opt3 = document.createElement('option');
      opt3.value = c.id;
      opt3.textContent = c.name;
      coverageSelect.appendChild(opt3);
    });

    // Populate Courses Grid
    const container = document.getElementById('courses-grid-container');
    if (activeCourses.length === 0) {
      container.innerHTML = '<p style="color: var(--text-muted); grid-column: 1/-1; text-align: center;">No courses indexed yet. Click "Sync Now" to auto-discover your enrolled modules.</p>';
      return;
    }

    container.innerHTML = activeCourses.map(c => `
      <div class="course-card">
        <div>
          <div class="course-card-header">
            <div>
              <h3>${escapeHtml(c.name)}</h3>
              <span class="course-code">${escapeHtml(c.code || '')}</span>
            </div>
            <label class="switch" title="Toggle Sync for this Module">
              <input type="checkbox" ${c.is_active ? 'checked' : ''} onchange="toggleCourseSync('${c.id}', this.checked)">
              <span class="slider"></span>
            </label>
          </div>
          <p style="font-size: 0.8rem; color: var(--text-muted); margin-bottom: 0.5rem;">
            Folder: <code>${escapeHtml(c.folder || '')}</code>
          </p>
        </div>
        <div style="display: flex; justify-content: space-between; align-items: center; margin-top: 1rem; border-top: 1px solid var(--border-color); padding-top: 0.75rem;">
          <span style="font-size: 0.75rem; color: var(--text-secondary);">
            Last Synced: ${c.last_synced_at ? new Date(c.last_synced_at).toLocaleTimeString() : 'Never'}
          </span>
          <button class="btn btn-outline" style="padding: 0.25rem 0.6rem; font-size: 0.75rem;" onclick="viewCourseFiles('${c.id}', '${escapeHtml(c.name)}')">
            📁 Files
          </button>
        </div>
      </div>
    `).join('');
  } catch (err) {
    console.error('Error loading courses:', err);
  }
}

async function loadTasks() {
  try {
    let url = '/api/tasks?';
    if (currentTaskFilter === 'pending') url += 'completed=false&';
    else if (currentTaskFilter === 'completed') url += 'completed=true&';
    if (currentTypeFilter) url += `source_type=${encodeURIComponent(currentTypeFilter)}&`;
    if (currentCourseFilter) url += `course_id=${encodeURIComponent(currentCourseFilter)}&`;

    const res = await fetch(url);
    const tasks = await res.json();
    const container = document.getElementById('task-list-container');

    if (tasks.length === 0) {
      container.innerHTML = '<p style="color: var(--text-muted); text-align: center; padding: 2rem;">No to-do items matching selected filters.</p>';
      return;
    }

    container.innerHTML = tasks.map(t => {
      const isOverdue = t.due_date && new Date(t.due_date) < new Date() && !t.completed;
      const formattedDue = t.due_date ? new Date(t.due_date).toLocaleString() : null;

      let tagLabel = '🎯 Assignment';
      let tagClass = 'tag-assignment';

      if (t.source_type === 'announcement') {
        tagLabel = '📢 Action Item';
        tagClass = 'tag-announcement';
      } else if (t.source_type === 'manual') {
        tagLabel = '📝 Custom';
        tagClass = 'tag-manual';
      } else if (t.source_type === 'study') {
        tagLabel = '📖 Study Review';
        tagClass = 'tag-study';
      }

      const priorityClass = t.priority === 'high' ? 'tag-priority-high' : (t.priority === 'low' ? 'tag-priority-low' : 'tag-priority-medium');
      const priorityLabel = t.priority ? t.priority.toUpperCase() : 'MEDIUM';

      return `
        <div class="task-card ${t.completed ? 'completed' : ''}">
          <div class="task-left">
            <input type="checkbox" class="task-checkbox" ${t.completed ? 'checked' : ''} onchange="toggleTask('${t.id}', this.checked)">
            <div class="task-info">
              <h4>${escapeHtml(t.title)}</h4>
              <div class="task-meta">
                <span class="tag ${tagClass}">${tagLabel}</span>
                <span class="tag ${priorityClass}">${priorityLabel}</span>
                ${formattedDue ? `<span class="tag-due" style="${isOverdue ? 'color: #ef4444; font-weight: 600;' : ''}">📅 ${formattedDue} ${isOverdue ? '(Overdue)' : ''}</span>` : ''}
                ${t.course_name ? `<span style="color: var(--text-muted);">| ${escapeHtml(t.course_name)}</span>` : ''}
              </div>
              ${t.description ? `<p style="font-size: 0.8rem; color: var(--text-secondary); margin-top: 0.4rem; white-space: pre-wrap;">${escapeHtml(t.description)}</p>` : ''}
            </div>
          </div>
          <div class="task-actions">
            <button class="btn-icon" title="Delete Task" onclick="deleteTask('${t.id}')">🗑️</button>
          </div>
        </div>
      `;
    }).join('');
  } catch (err) {
    console.error('Error loading tasks:', err);
  }
}

// --- Study Coverage Logic ---
async function loadStudyCoverage(forceRefresh = false) {
  const container = document.getElementById('coverage-container');
  container.innerHTML = '<p style="color: var(--text-muted); text-align: center; padding: 2rem;">Analyzing markdown lecture slides and lab notes...</p>';

  try {
    const res = await fetch('/api/coverage');
    coverageData = await res.json();
    renderCoverageUI();
  } catch (err) {
    container.innerHTML = `<p style="color: #ef4444; text-align: center; padding: 2rem;">Error analyzing study coverage: ${err}</p>`;
  }
}

function renderCoverageUI() {
  const container = document.getElementById('coverage-container');
  if (!coverageData || !coverageData.courses || coverageData.courses.length === 0) {
    container.innerHTML = `
      <div style="text-align: center; padding: 3rem; color: var(--text-muted);">
        <h3>No converted markdown notes found yet</h3>
        <p style="margin-top: 0.5rem; font-size: 0.9rem;">
          Click "⚡ Sync Now" to discover modules and convert PDF lecture notes to Markdown.
        </p>
      </div>
    `;
    return;
  }

  let courses = coverageData.courses;
  if (currentCoverageCourse) {
    courses = courses.filter(c => c.course_id === currentCoverageCourse);
  }

  const totalNotes = courses.reduce((acc, c) => acc + c.total_notes, 0);
  const totalMinutes = courses.reduce((acc, c) => acc + c.estimated_review_minutes, 0);
  const totalHours = (totalMinutes / 60).toFixed(1);

  // Collect top concepts across selected courses
  const allConcepts = [];
  courses.forEach(c => allConcepts.push(...(c.top_concepts || [])));
  const uniqueConcepts = [...new Set(allConcepts)].slice(0, 20);

  const html = `
    <div class="coverage-summary-card">
      <div style="display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap; gap: 1rem; margin-bottom: 0.75rem;">
        <div>
          <h3 style="font-size: 1.15rem; color: var(--text-primary); font-weight: 600;">Academic Syllabus & Study Roadmap</h3>
          <p style="font-size: 0.85rem; color: var(--text-secondary); margin-top: 0.2rem;">
            Extracted from ${totalNotes} notes across ${courses.length} module(s). Estimated total revision time: <strong>${totalHours} hours</strong>.
          </p>
        </div>
      </div>
      ${uniqueConcepts.length > 0 ? `
        <div style="margin-top: 0.5rem;">
          <span style="font-size: 0.75rem; color: var(--text-muted); font-weight: 600; display: block; margin-bottom: 0.25rem;">KEY CONCEPTS TO MASTER:</span>
          <div>
            ${uniqueConcepts.map(c => `<span class="concept-pill">${escapeHtml(c)}</span>`).join('')}
          </div>
        </div>
      ` : ''}
    </div>

    <div class="coverage-grid">
      ${courses.map(course => renderCourseCoverageCard(course)).join('')}
    </div>
  `;

  container.innerHTML = html;
}

function renderCourseCoverageCard(course) {
  const notes = course.notes || [];
  return `
    <div class="coverage-card">
      <div class="coverage-card-header">
        <div>
          <h4 class="coverage-card-title">${escapeHtml(course.course_name)}</h4>
          <span class="course-code">${escapeHtml(course.course_code)}</span>
        </div>
        <span class="tag tag-study">${notes.length} notes (~${course.estimated_review_minutes}m)</span>
      </div>

      ${course.top_concepts && course.top_concepts.length > 0 ? `
        <div>
          <span style="font-size: 0.72rem; color: var(--text-muted); font-weight: 600;">CORE MODULE TOPICS:</span>
          <div style="margin-top: 0.25rem;">
            ${course.top_concepts.slice(0, 8).map(c => `<span class="concept-pill">${escapeHtml(c)}</span>`).join('')}
          </div>
        </div>
      ` : ''}

      <div style="border-top: 1px solid var(--border-color); padding-top: 0.75rem; margin-top: 0.25rem;">
        <span style="font-size: 0.75rem; color: var(--text-secondary); font-weight: 600;">TOPIC BREAKDOWN & CHECKLIST:</span>
        <ul class="topic-checklist">
          ${notes.length === 0 ? '<li style="font-size: 0.8rem; color: var(--text-muted);">No notes converted in this module yet.</li>' : ''}
          ${notes.slice(0, 8).map((note, idx) => {
            const checkKey = `study_done_${note.filename}`;
            const isChecked = localStorage.getItem(checkKey) === 'true';
            const icon = note.category === 'Lecture' ? '🎓' : (note.category === 'Lab' ? '💻' : '📖');
            return `
              <li class="topic-check-item">
                <input type="checkbox" id="${checkKey}" ${isChecked ? 'checked' : ''} onchange="toggleTopicChecked('${checkKey}', this.checked)">
                <div style="flex: 1;">
                  <label for="${checkKey}" style="cursor: pointer; ${isChecked ? 'text-decoration: line-through; color: var(--text-muted);' : ''}">
                    <strong>${icon} ${escapeHtml(note.title)}</strong>
                    <span style="font-size: 0.72rem; color: var(--text-muted); margin-left: 0.4rem;">(${note.estimated_minutes}m)</span>
                  </label>
                  ${note.topics && note.topics.length > 0 ? `
                    <div style="font-size: 0.72rem; color: var(--text-muted); margin-top: 0.15rem;">
                      • ${escapeHtml(note.topics.slice(0, 2).join(' • '))}
                    </div>
                  ` : ''}
                </div>
                <button class="btn btn-outline" style="padding: 0.15rem 0.4rem; font-size: 0.7rem;" onclick="previewMarkdownFile('${encodeURIComponent(note.path)}', '${escapeHtml(note.filename)}')">
                  Read
                </button>
              </li>
            `;
          }).join('')}
        </ul>
        ${notes.length > 8 ? `
          <div style="font-size: 0.75rem; color: var(--text-muted); margin-top: 0.5rem; text-align: center;">
            + ${notes.length - 8} more documents indexed in STUDY_PLAN.md
          </div>
        ` : ''}
      </div>
    </div>
  `;
}

function toggleTopicChecked(key, isChecked) {
  localStorage.setItem(key, isChecked ? 'true' : 'false');
  const label = document.querySelector(`label[for="${key}"]`);
  if (label) {
    label.style.textDecoration = isChecked ? 'line-through' : 'none';
    label.style.color = isChecked ? 'var(--text-muted)' : 'inherit';
  }
}

function openAntigravityModal() {
  if (!coverageData || !coverageData.courses || coverageData.courses.length === 0) {
    alert('Please run sync first to index your course materials.');
    return;
  }

  let selectedCourse = coverageData.courses[0];
  if (currentCoverageCourse) {
    selectedCourse = coverageData.courses.find(c => c.course_id === currentCoverageCourse) || selectedCourse;
  }

  const prompt = selectedCourse.antigravity_prompt || `Review the markdown notes in ${selectedCourse.folder} and quiz me.`;
  const box = document.getElementById('antigravity-prompt-box');
  box.textContent = `agy "${prompt}"`;
  document.getElementById('modal-antigravity').classList.add('active');
}

function copyAntigravityPromptToClipboard() {
  const box = document.getElementById('antigravity-prompt-box');
  navigator.clipboard.writeText(box.textContent).then(() => {
    const btn = document.getElementById('btn-copy-prompt-action');
    btn.textContent = '✅ Copied to Clipboard!';
    setTimeout(() => {
      btn.textContent = '📋 Copy to Clipboard';
      closeModal('modal-antigravity');
    }, 1500);
  });
}

// --- Announcements ---
async function loadAnnouncements() {
  try {
    const res = await fetch('/api/announcements');
    const anns = await res.json();
    const container = document.getElementById('announcements-container');

    if (anns.length === 0) {
      container.innerHTML = '<p style="color: var(--text-muted); text-align: center; padding: 2rem;">No announcements discovered yet. Run sync to fetch updates.</p>';
      return;
    }

    container.innerHTML = anns.map(a => `
      <div class="announcement-card">
        <div class="announcement-header">
          <div>
            <h3>${escapeHtml(a.title)}</h3>
            <span style="font-size: 0.75rem; color: #818cf8; font-weight: 600;">${escapeHtml(a.course_name || 'Course')}</span>
          </div>
          <span style="font-size: 0.75rem; color: var(--text-muted);">
            ${a.created_at ? new Date(a.created_at).toLocaleDateString() : ''}
          </span>
        </div>
        <div class="announcement-body">
          <pre style="white-space: pre-wrap; font-family: inherit; font-size: 0.88rem;">${escapeHtml(a.markdown_body || '')}</pre>
        </div>
      </div>
    `).join('');
  } catch (err) {
    console.error('Error loading announcements:', err);
  }
}

// --- Actions ---

async function toggleTask(taskId, completed) {
  try {
    await fetch(`/api/tasks/${taskId}/complete`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ completed })
    });
    loadTasks();
    loadStats();
  } catch (err) {
    console.error('Error updating task:', err);
  }
}

async function deleteTask(taskId) {
  if (!confirm('Are you sure you want to delete this task?')) return;
  try {
    await fetch(`/api/tasks/${taskId}`, { method: 'DELETE' });
    loadTasks();
    loadStats();
  } catch (err) {
    console.error('Error deleting task:', err);
  }
}

async function toggleCourseSync(courseId, isActive) {
  try {
    await fetch(`/api/courses/${courseId}/toggle`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ is_active: isActive })
    });
    loadStats();
  } catch (err) {
    console.error('Error toggling course:', err);
  }
}

async function triggerSync() {
  const btn = document.getElementById('btn-sync');
  btn.disabled = true;
  btn.textContent = '⏳ Syncing...';
  appendConsoleLog('[System] Initiating manual sync job...');

  document.querySelector('[data-tab="tab-logs"]').click();

  try {
    const res = await fetch('/api/sync', { method: 'POST' });
    const data = await res.json();
    appendConsoleLog(`[System] ${data.message}`);
  } catch (err) {
    appendConsoleLog(`[Error] Failed to initiate sync: ${err}`);
  } finally {
    setTimeout(() => {
      btn.disabled = false;
      btn.textContent = '⚡ Sync Now';
      loadAllData();
      loadStudyCoverage(true);
    }, 3000);
  }
}

async function triggerLogin() {
  const btn = document.getElementById('btn-login');
  btn.disabled = true;
  appendConsoleLog('[System] Launching Chromium login window for Microsoft SSO/2FA...');
  document.querySelector('[data-tab="tab-logs"]').click();
  try {
    const res = await fetch('/api/auth/login', { method: 'POST' });
    const data = await res.json();
    appendConsoleLog(`[System] ${data.message}. Complete login in the opened browser window.`);
  } catch (err) {
    appendConsoleLog(`[Error] Failed to launch browser: ${err}`);
  } finally {
    setTimeout(() => {
      btn.disabled = false;
    }, 4000);
  }
}

// --- Auto-Sync Settings Modal ---
function openAutoSyncModal() {
  if (schedulerInfo) {
    document.getElementById('autosync-toggle').checked = !!schedulerInfo.auto_sync_enabled;
    const intervalSelect = document.getElementById('autosync-interval-select');
    const hours = Math.round(schedulerInfo.interval_hours);
    intervalSelect.value = String(hours);
  }
  document.getElementById('modal-autosync').classList.add('active');
}

async function saveAutoSyncPreferences() {
  const enabled = document.getElementById('autosync-toggle').checked;
  const interval = parseFloat(document.getElementById('autosync-interval-select').value);

  try {
    const res = await fetch('/api/scheduler/config', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ enabled, interval_hours: interval })
    });
    schedulerInfo = await res.json();
    closeModal('modal-autosync');
    loadSchedulerStatus();
  } catch (err) {
    alert('Failed to save scheduler preferences: ' + err);
  }
}

// --- SSE Real-time Logs ---
function initSSELogs() {
  const evtSource = new EventSource('/api/sync/logs');
  evtSource.onmessage = (event) => {
    appendConsoleLog(event.data);
  };
}

function appendConsoleLog(text) {
  const box = document.getElementById('console-logs');
  const entry = document.createElement('div');
  entry.className = 'log-entry';
  entry.textContent = text;
  box.appendChild(entry);
  box.scrollTop = box.scrollHeight;
}

// --- Modals ---
function openCalendarModal() {
  const feedUrl = window.location.origin + '/calendar/deadlines.ics';
  document.getElementById('calendar-url-block').textContent = feedUrl;
  document.getElementById('btn-gcal-subscribe').href = `https://calendar.google.com/calendar/render?cid=${encodeURIComponent(feedUrl)}`;
  document.getElementById('modal-calendar').classList.add('active');
}

async function viewCourseFiles(courseId, courseName) {
  try {
    const res = await fetch(`/api/files?course_id=${encodeURIComponent(courseId)}`);
    const files = await res.json();
    const modalBody = document.getElementById('markdown-modal-body');
    const modalTitle = document.getElementById('markdown-modal-title');
    modalTitle.textContent = `📁 Materials for ${courseName}`;

    if (files.length === 0) {
      modalBody.textContent = 'No local files recorded for this module yet.';
    } else {
      modalBody.innerHTML = files.map(f => `
        <div style="display: flex; justify-content: space-between; align-items: center; padding: 0.6rem; border-bottom: 1px solid var(--border-color);">
          <div>
            <div style="font-weight: 600; color: #f8fafc;">${escapeHtml(f.filename)}</div>
            <div style="font-size: 0.75rem; color: var(--text-muted);">${escapeHtml(f.remote_path || '')}</div>
          </div>
          <div style="display: flex; gap: 0.5rem;">
            ${f.markdown_path ? `<button class="btn btn-outline" style="padding: 0.2rem 0.5rem; font-size: 0.75rem;" onclick="previewMarkdownFile('${encodeURIComponent(f.markdown_path)}', '${escapeHtml(f.filename)}')">📄 View Markdown</button>` : ''}
          </div>
        </div>
      `).join('');
    }

    document.getElementById('modal-markdown').classList.add('active');
  } catch (err) {
    console.error('Error fetching files:', err);
  }
}

async function previewMarkdownFile(encodedPath, filename) {
  try {
    const path = decodeURIComponent(encodedPath);
    const res = await fetch(`/api/file-content?path=${encodeURIComponent(path)}`);
    const data = await res.json();
    document.getElementById('markdown-modal-title').textContent = `📄 ${filename} (Markdown)`;
    document.getElementById('markdown-modal-body').textContent = data.content || '(Empty document)';
    document.getElementById('modal-markdown').classList.add('active');
  } catch (err) {
    alert('Failed to load markdown content: ' + err);
  }
}

function closeModal(modalId) {
  document.getElementById(modalId).classList.remove('active');
}

function escapeHtml(str) {
  if (!str) return '';
  return str.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
}
