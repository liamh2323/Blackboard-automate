// Blackboard Automate Frontend Logic

let currentTaskFilter = 'pending';
let currentCourseFilter = '';
let activeCourses = [];

document.addEventListener('DOMContentLoaded', () => {
  initTabs();
  initSSELogs();
  loadAllData();
  setupEventListeners();

  // Periodic polling for status & stats
  setInterval(loadStats, 10000);
});

// --- Tab Management ---
function initTabs() {
  const tabs = document.querySelectorAll('.tab-btn');
  tabs.forEach(btn => {
    btn.addEventListener('click', () => {
      tabs.forEach(b => b.classList.remove('active'));
      document.querySelectorAll('.tab-content').forEach(c => c.classList.remove('active'));

      btn.classList.add('active');
      const target = document.getElementById(btn.getAttribute('data-tab'));
      if (target) target.classList.add('active');
    });
  });
}

// --- Event Listeners ---
function setupEventListeners() {
  // Sync Now Button
  document.getElementById('btn-sync').addEventListener('click', triggerSync);

  // 2FA Login Button
  document.getElementById('btn-login').addEventListener('click', triggerLogin);

  // Calendar Modal Button
  document.getElementById('btn-calendar').addEventListener('click', openCalendarModal);

  // Clear Logs
  document.getElementById('btn-clear-logs').addEventListener('click', () => {
    document.getElementById('console-logs').innerHTML = '';
  });

  // Task Filter Buttons
  document.querySelectorAll('.filter-btn').forEach(btn => {
    btn.addEventListener('click', () => {
      document.querySelectorAll('.filter-btn').forEach(b => b.classList.remove('active'));
      btn.classList.add('active');
      currentTaskFilter = btn.getAttribute('data-filter');
      loadTasks();
    });
  });

  // Course Filter for Tasks
  document.getElementById('todo-course-filter').addEventListener('change', (e) => {
    currentCourseFilter = e.target.value;
    loadTasks();
  });

  // Add Task Form
  document.getElementById('form-add-task').addEventListener('submit', async (e) => {
    e.preventDefault();
    const titleInput = document.getElementById('new-task-title');
    const dueInput = document.getElementById('new-task-due');
    const title = titleInput.value.trim();
    const due = dueInput.value ? new Date(dueInput.value).toISOString() : null;

    if (!title) return;

    try {
      await fetch('/api/tasks', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ title, due_date: due, course_id: currentCourseFilter || null })
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
    loadAnnouncements()
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

    // Check sync status
    const statusRes = await fetch('/api/sync/status');
    const statusData = await statusRes.json();
    const badge = document.getElementById('status-badge');
    if (statusData.is_syncing) {
      badge.textContent = 'Syncing...';
      badge.style.color = '#38bdf8';
      badge.style.backgroundColor = 'rgba(56, 189, 248, 0.15)';
    } else {
      badge.textContent = 'Idle';
      badge.style.color = '#a5b4fc';
      badge.style.backgroundColor = 'rgba(99, 102, 241, 0.15)';
    }
  } catch (err) {
    console.error('Error loading stats:', err);
  }
}

async function loadCourses() {
  try {
    const res = await fetch('/api/courses');
    activeCourses = await res.json();

    // Populate Course Filter dropdown
    const select = document.getElementById('todo-course-filter');
    select.innerHTML = '<option value="">All Courses</option>';
    activeCourses.forEach(c => {
      const opt = document.createElement('option');
      opt.value = c.id;
      opt.textContent = c.name;
      select.appendChild(opt);
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
    if (currentCourseFilter) url += `course_id=${encodeURIComponent(currentCourseFilter)}&`;

    const res = await fetch(url);
    const tasks = await res.json();
    const container = document.getElementById('task-list-container');

    if (tasks.length === 0) {
      container.innerHTML = '<p style="color: var(--text-muted); text-align: center; padding: 2rem;">No to-do items matching filter.</p>';
      return;
    }

    container.innerHTML = tasks.map(t => {
      const isOverdue = t.due_date && new Date(t.due_date) < new Date() && !t.completed;
      const formattedDue = t.due_date ? new Date(t.due_date).toLocaleString() : null;
      const tagClass = t.source_type === 'assignment' ? 'tag-assignment' : 'tag-announcement';
      const tagLabel = t.source_type === 'assignment' ? '🎯 Assignment' : (t.source_type === 'manual' ? '📝 Manual' : '📢 Announcement');

      return `
        <div class="task-card ${t.completed ? 'completed' : ''}">
          <div class="task-left">
            <input type="checkbox" class="task-checkbox" ${t.completed ? 'checked' : ''} onchange="toggleTask('${t.id}', this.checked)">
            <div class="task-info">
              <h4>${escapeHtml(t.title)}</h4>
              <div class="task-meta">
                <span class="tag ${tagClass}">${tagLabel}</span>
                ${formattedDue ? `<span class="tag-due" style="${isOverdue ? 'color: #ef4444;' : ''}">📅 ${formattedDue} ${isOverdue ? '(Overdue)' : ''}</span>` : ''}
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

  // Switch to Console Tab so user sees progress
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
    }, 3000);
  }
}

async function triggerLogin() {
  appendConsoleLog('[System] Launching Chromium login window for Microsoft SSO/2FA...');
  document.querySelector('[data-tab="tab-logs"]').click();
  try {
    const res = await fetch('/api/auth/login', { method: 'POST' });
    const data = await res.json();
    appendConsoleLog(`[System] ${data.message}. Complete login in the opened browser window.`);
  } catch (err) {
    appendConsoleLog(`[Error] Failed to launch browser: ${err}`);
  }
}

// --- SSE Real-time Logs ---
function initSSELogs() {
  const evtSource = new EventSource('/api/sync/logs');
  evtSource.onmessage = (event) => {
    appendConsoleLog(event.data);
  };
  evtSource.onerror = () => {
    // Reconnects automatically
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
