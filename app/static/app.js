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
    const setBadge = (state, text) => {
      badge.classList.remove('is-on', 'is-off', 'is-syncing');
      if (state) badge.classList.add(state);
      badge.textContent = text;
    };

    if (schedulerInfo.is_syncing) {
      setBadge('is-syncing', 'Syncing…');
      return;
    }

    if (!schedulerInfo.auto_sync_enabled) {
      setBadge('is-off', 'Auto-sync off');
      return;
    }

    if (schedulerInfo.next_sync_time) {
      const diffMs = new Date(schedulerInfo.next_sync_time) - new Date();

      if (diffMs <= 0) {
        setBadge('is-on', 'Next sync imminent');
      } else {
        const diffMins = Math.floor(diffMs / 60000);
        if (diffMins < 60) {
          setBadge('is-on', `Next sync in ${diffMins}m`);
        } else {
          const hours = Math.floor(diffMins / 60);
          const mins = diffMins % 60;
          setBadge('is-on', `Next sync in ${hours}h ${mins}m`);
        }
      }
    } else {
      setBadge('is-on', `Auto-sync every ${schedulerInfo.interval_hours}h`);
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

    const populate = (select, defaultLabel) => {
      const previous = select.value;
      select.innerHTML = '';
      select.appendChild(new Option(defaultLabel, ''));
      activeCourses.forEach(c => select.appendChild(new Option(c.name, c.id)));
      select.value = previous;
      if (select.selectedIndex === -1) select.value = '';
    };

    populate(todoSelect, 'All courses');
    populate(taskFormSelect, 'General');
    populate(coverageSelect, 'All active modules');

    // Populate Courses Grid
    const container = document.getElementById('courses-grid-container');
    if (activeCourses.length === 0) {
      container.innerHTML = emptyState('No modules indexed yet', 'Click “Sync now” to discover your enrolled modules.');
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
            <label class="switch" title="Toggle sync for this module">
              <input type="checkbox" ${c.is_active ? 'checked' : ''} onchange="toggleCourseSync(${jsArg(c.id)}, this.checked)">
              <span class="slider"></span>
            </label>
          </div>
          <p class="course-folder"><code>${escapeHtml(c.folder || '')}</code></p>
        </div>
        <div class="card-footer">
          <span>Last synced: ${c.last_synced_at ? new Date(c.last_synced_at).toLocaleString() : 'Never'}</span>
          <button class="btn btn-outline btn-sm" onclick="viewCourseFiles(${jsArg(c.id)}, ${jsArg(c.name)})">View files</button>
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
      container.innerHTML = emptyState('Nothing here', 'No to-do items match the selected filters.');
      return;
    }

    const typeTags = {
      assignment: ['Assignment', 'tag-assignment'],
      announcement: ['Action item', 'tag-announcement'],
      manual: ['Custom', 'tag-manual'],
      study: ['Study review', 'tag-study'],
    };

    container.innerHTML = tasks.map(t => {
      const isOverdue = t.due_date && new Date(t.due_date) < new Date() && !t.completed;
      const formattedDue = t.due_date
        ? new Date(t.due_date).toLocaleString(undefined, { dateStyle: 'medium', timeStyle: 'short' })
        : null;

      const [tagLabel, tagClass] = typeTags[t.source_type] || typeTags.assignment;
      const priority = ['high', 'medium', 'low'].includes(t.priority) ? t.priority : 'medium';
      const priorityLabel = priority.charAt(0).toUpperCase() + priority.slice(1);

      return `
        <div class="task-card ${t.completed ? 'completed' : ''}">
          <div class="task-left">
            <input type="checkbox" class="task-checkbox" ${t.completed ? 'checked' : ''} onchange="toggleTask(${jsArg(t.id)}, this.checked)" aria-label="Mark complete">
            <div class="task-info">
              <h4>${escapeHtml(t.title)}</h4>
              <div class="task-meta">
                <span class="tag ${tagClass}">${tagLabel}</span>
                <span class="tag tag-priority-${priority}">${priorityLabel}</span>
                ${formattedDue ? `<span class="tag-due ${isOverdue ? 'is-overdue' : ''}">${isOverdue ? 'Overdue · ' : 'Due '}${formattedDue}</span>` : ''}
                ${t.course_name ? `<span class="meta-sep">${escapeHtml(t.course_name)}</span>` : ''}
              </div>
              ${t.description ? `<p class="task-desc">${escapeHtml(t.description)}</p>` : ''}
            </div>
          </div>
          <div class="task-actions">
            <button class="btn-icon" title="Delete task" aria-label="Delete task" onclick="deleteTask(${jsArg(t.id)})">${ICON_TRASH}</button>
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
  container.innerHTML = '<p class="empty-state">Analysing lecture slides and lab notes…</p>';

  try {
    const res = await fetch('/api/coverage');
    coverageData = await res.json();
    renderCoverageUI();
  } catch (err) {
    container.innerHTML = `<p class="empty-state is-error">Error analysing study coverage: ${escapeHtml(String(err))}</p>`;
  }
}

function renderCoverageUI() {
  const container = document.getElementById('coverage-container');
  if (!coverageData || !coverageData.courses || coverageData.courses.length === 0) {
    container.innerHTML = emptyState(
      'No converted notes yet',
      'Click “Sync now” to discover modules and convert lecture notes to Markdown.'
    );
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
      <h3>Study roadmap</h3>
      <p>
        ${totalNotes} notes across ${courses.length} module${courses.length === 1 ? '' : 's'} ·
        estimated revision time <strong>${totalHours} hours</strong>
      </p>
      ${uniqueConcepts.length > 0 ? `
        <div class="coverage-concepts">
          <span class="section-label">Key concepts</span>
          <div>${uniqueConcepts.map(c => `<span class="concept-pill">${escapeHtml(c)}</span>`).join('')}</div>
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
        <span class="tag tag-study">${notes.length} notes · ~${course.estimated_review_minutes}m</span>
      </div>

      ${course.top_concepts && course.top_concepts.length > 0 ? `
        <div>
          <span class="section-label">Core topics</span>
          <div>${course.top_concepts.slice(0, 8).map(c => `<span class="concept-pill">${escapeHtml(c)}</span>`).join('')}</div>
        </div>
      ` : ''}

      <div class="coverage-section">
        <span class="section-label">Checklist</span>
        <ul class="topic-checklist">
          ${notes.length === 0 ? '<li class="topic-sub">No notes converted in this module yet.</li>' : ''}
          ${notes.slice(0, 8).map(note => {
            const checkKey = `study_done_${note.filename}`;
            const isChecked = localStorage.getItem(checkKey) === 'true';
            return `
              <li class="topic-check-item ${isChecked ? 'is-done' : ''}">
                <input type="checkbox" id="${escapeHtml(checkKey)}" ${isChecked ? 'checked' : ''} onchange="toggleTopicChecked(${jsArg(checkKey)}, this.checked, this)">
                <div class="topic-body">
                  <label for="${escapeHtml(checkKey)}">
                    ${escapeHtml(note.title)}<span class="topic-minutes">${escapeHtml(note.category || '')}${note.category ? ' · ' : ''}${note.estimated_minutes}m</span>
                  </label>
                  ${note.topics && note.topics.length > 0 ? `
                    <div class="topic-sub">${escapeHtml(note.topics.slice(0, 2).join(' · '))}</div>
                  ` : ''}
                </div>
                <button class="btn btn-outline btn-xs" onclick="previewMarkdownFile(${jsArg(encodeURIComponent(note.path))}, ${jsArg(note.filename)})">Read</button>
              </li>
            `;
          }).join('')}
        </ul>
        ${notes.length > 8 ? `
          <div class="topic-more">+ ${notes.length - 8} more documents indexed in STUDY_PLAN.md</div>
        ` : ''}
      </div>
    </div>
  `;
}

function toggleTopicChecked(key, isChecked, el) {
  localStorage.setItem(key, isChecked ? 'true' : 'false');
  const item = el ? el.closest('.topic-check-item') : null;
  if (item) item.classList.toggle('is-done', isChecked);
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
    btn.textContent = 'Copied!';
    setTimeout(() => {
      btn.textContent = 'Copy to clipboard';
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
      container.innerHTML = emptyState('No announcements yet', 'Run a sync to fetch updates from Blackboard.');
      return;
    }

    container.innerHTML = anns.map(a => `
      <div class="announcement-card">
        <div class="announcement-header">
          <div>
            <h3>${escapeHtml(a.title)}</h3>
            <span class="announcement-course">${escapeHtml(a.course_name || 'Course')}</span>
          </div>
          <span class="announcement-date">
            ${a.created_at ? new Date(a.created_at).toLocaleDateString(undefined, { dateStyle: 'medium' }) : ''}
          </span>
        </div>
        <div class="announcement-body">
          <pre>${escapeHtml(a.markdown_body || '')}</pre>
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
  btn.textContent = 'Syncing…';
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
      btn.textContent = 'Sync now';
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
  if (/^\[(error|fatal)\]/i.test(text) || /\b(error|failed|exception)\b/i.test(text)) {
    entry.classList.add('is-error');
  } else if (/^\[system\]/i.test(text)) {
    entry.classList.add('is-system');
  }
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
    modalTitle.textContent = `Files · ${courseName}`;
    modalBody.classList.add('is-list');

    if (files.length === 0) {
      modalBody.innerHTML = '<p class="empty-state">No local files recorded for this module yet.</p>';
    } else {
      modalBody.innerHTML = files.map(f => `
        <div class="file-row">
          <div>
            <div class="file-name">${escapeHtml(f.filename)}</div>
            <div class="file-path">${escapeHtml(f.remote_path || '')}</div>
          </div>
          ${f.markdown_path ? `<button class="btn btn-outline btn-sm" onclick="previewMarkdownFile(${jsArg(encodeURIComponent(f.markdown_path))}, ${jsArg(f.filename)})">View markdown</button>` : ''}
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
    const body = document.getElementById('markdown-modal-body');
    document.getElementById('markdown-modal-title').textContent = filename;
    body.classList.remove('is-list');
    body.textContent = data.content || '(Empty document)';
    body.scrollTop = 0;
    document.getElementById('modal-markdown').classList.add('active');
  } catch (err) {
    alert('Failed to load markdown content: ' + err);
  }
}

function closeModal(modalId) {
  document.getElementById(modalId).classList.remove('active');
}

// Close modals on backdrop click or Escape
document.addEventListener('click', (e) => {
  if (e.target.classList && e.target.classList.contains('modal-overlay')) {
    e.target.classList.remove('active');
  }
});
document.addEventListener('keydown', (e) => {
  if (e.key === 'Escape') {
    document.querySelectorAll('.modal-overlay.active').forEach(m => m.classList.remove('active'));
  }
});

// --- Helpers ---
const ICON_TRASH = '<svg class="icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M3 6h18"/><path d="M8 6V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"/><path d="M19 6l-1 14a2 2 0 0 1-2 2H8a2 2 0 0 1-2-2L5 6"/></svg>';

function emptyState(title, message) {
  return `<div class="empty-state"><h3>${escapeHtml(title)}</h3><p>${escapeHtml(message)}</p></div>`;
}

function escapeHtml(str) {
  if (!str) return '';
  return String(str).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;').replace(/'/g, '&#39;');
}

// Safely embed a value as a JS string literal inside an inline HTML event attribute
function jsArg(value) {
  return escapeHtml(JSON.stringify(value == null ? '' : String(value)));
}
