// JobMatch Web UI — frontend logic

// ─── Helpers ──────────────────────────────────────────────────

async function api(path, options = {}) {
  const res = await fetch(path, {
    headers: { 'Content-Type': 'application/json' },
    ...options,
  });
  return res.json();
}

function showStatus(el, msg, ok = true) {
  el.textContent = msg;
  el.style.color = ok ? '#28a745' : '#dc3545';
  setTimeout(() => el.textContent = '', 3000);
}

// ─── Dashboard ───────────────────────────────────────────────

async function loadDashboard() {
  const el = (id) => document.getElementById(id);
  if (!el('stat-total')) return;

  try {
    const stats = await api('/api/stats');
    el('stat-total').textContent = stats.total;

    const statusHtml = Object.entries(stats.by_status)
      .map(([k, v]) => `${k}: ${v}`).join('\n');
    el('stat-status').textContent = statusHtml || '—';

    const catHtml = Object.entries(stats.by_category)
      .map(([k, v]) => `${k}: ${v}`).join('\n');
    el('stat-category').textContent = catHtml || '—';
  } catch (e) {
    console.error('Failed to load dashboard', e);
  }
}

async function runScan() {
  const el = document.querySelector('#scan-result');
  el.textContent = 'Сканирование...';
  el.style.color = '#666';
  try {
    const res = await api('/api/scan', { method: 'POST' });
    if (res.ok) {
      el.textContent = res.message || `Готово: ${res.scanned} вакансий`;
      el.style.color = '#28a745';
      setTimeout(loadDashboard, 1000);
      setTimeout(loadVacancies, 1000);
    } else {
      el.textContent = res.error || 'Ошибка';
      el.style.color = '#dc3545';
    }
  } catch (e) {
    el.textContent = 'Ошибка соединения с сервером';
    el.style.color = '#dc3545';
  }
}

// ─── Profile ──────────────────────────────────────────────────

async function loadProfile() {
  const profile = await api('/api/profile');
  if (!profile || !profile.name) return;

  setVal('field-name', profile.name);
  setVal('field-location', profile.location);
  setVal('field-work_format', profile.work_format);
  setVal('field-salary', profile.salary_expectation);
  setVal('field-hh_token', profile.hh_access_token);
  setVal('field-hh_resume_id', profile.hh_resume_id);
  setVal('field-telegram_chat_id', profile.telegram_chat_id);

  const filters = profile.search_filters || {};
  setVal('field-regions', (filters.regions || []).join(', '));
  setVal('field-titles', (filters.titles || []).join(', '));
  setVal('field-keywords', (filters.keywords || []).join(', '));
}

async function saveProfile() {
  const body = {
    name: val('field-name'),
    location: val('field-location'),
    work_format: val('field-work_format'),
    salary_expectation: parseInt(val('field-salary')) || 0,
  };
  const res = await api('/api/profile', {
    method: 'POST',
    body: JSON.stringify(body),
  });
  showStatus(document.getElementById('profile-status'), 'Сохранено');
}

async function saveFilters() {
  const regions = val('field-regions').split(',').map(s => s.trim()).filter(Boolean);
  const titles = val('field-titles').split(',').map(s => s.trim()).filter(Boolean);
  const keywords = val('field-keywords').split(',').map(s => s.trim()).filter(Boolean);

  const res = await api('/api/profile', {
    method: 'POST',
    body: JSON.stringify({
      search_filters: { regions, titles, keywords, professional_roles: [107, 73], industries: ['7.540', '7.539'] },
    }),
  });
  showStatus(document.getElementById('filters-status'), 'Фильтры сохранены');
}

async function saveIntegrations() {
  const res = await api('/api/profile', {
    method: 'POST',
    body: JSON.stringify({
      hh_access_token: val('field-hh_token'),
      hh_resume_id: val('field-hh_resume_id'),
      telegram_chat_id: val('field-telegram_chat_id'),
    }),
  });
  showStatus(document.getElementById('integrations-status'), 'Сохранено');
}

// ─── Matrix ───────────────────────────────────────────────────

async function loadMatrix() {
  const root = document.getElementById('matrix-root');
  if (!root) return;

  const matrix = await api('/api/matrix');
  const groups = matrix.groups || [];

  root.innerHTML = groups.map((g, gi) => `
    <div class="matrix-group" data-group-id="${g.id}">
      <h3>
        <span>${gi + 1}. ${g.name}</span>
        <span class="weight-control">
          Вес группы:
          <input type="number" class="input criterion-weight" value="${g.weight}" min="1" max="10"
                 onchange="updateGroupWeight('${g.id}', this.value)" />
        </span>
      </h3>
      ${(g.criteria || []).map(c => `
        <div class="criterion-row">
          <span class="criterion-name">${c.name}</span>
          <span class="criterion-desc">${c.description || ''}</span>
          <span class="weight-control">
            Вес: <input type="number" class="input criterion-weight" value="${c.weight}" min="1" max="10"
                        onchange="updateCriterionWeight('${g.id}', '${c.id}', this.value)" />
          </span>
        </div>
      `).join('')}
    </div>
  `).join('');
}

async function updateGroupWeight(groupId, weight) {
  await api('/api/matrix/group-weight', {
    method: 'POST',
    body: JSON.stringify({ id: groupId, weight: parseInt(weight) }),
  });
}

async function updateCriterionWeight(groupId, criterionId, weight) {
  await api('/api/matrix/criterion-weight', {
    method: 'POST',
    body: JSON.stringify({ group_id: groupId, criterion_id: criterionId, weight: parseInt(weight) }),
  });
}

// ─── Vacancies ────────────────────────────────────────────────

async function loadVacancies() {
  const tbody = document.getElementById('vacancies-body');
  if (!tbody) return;

  const data = await api('/api/vacancies');
  const items = data.items || [];

  if (items.length === 0) {
    tbody.innerHTML = '<tr><td colspan="6" style="text-align:center;color:#999;">Пока нет вакансий</td></tr>';
    return;
  }

  tbody.innerHTML = items.map(v => `
    <tr class="vacancy-row" data-category="${v.category || ''}">
      <td><a href="${v.url || '#'}" target="_blank">${v.title || '—'}</a></td>
      <td>${v.company || '—'}</td>
      <td><strong>${v.score || '?'}</strong></td>
      <td><span class="badge badge-${(v.category || 'мимо').replace('мимо', 'мимо')}">${v.category || 'мимо'}</span></td>
      <td><span class="badge badge-${v.status || 'new'}">${v.status || 'new'}</span></td>
      <td>${v.created_at ? v.created_at.slice(0, 10) : '—'}</td>
    </tr>
  `).join('');
}

function filterVacancies() {
  const cat = document.getElementById('category-filter').value;
  document.querySelectorAll('.vacancy-row').forEach(row => {
    const rowCat = row.dataset.category;
    row.style.display = (!cat || rowCat === cat) ? '' : 'none';
  });
}

// ─── Helpers ──────────────────────────────────────────────────

function val(id) {
  const el = document.getElementById(id);
  return el ? el.value : '';
}

function setVal(id, v) {
  const el = document.getElementById(id);
  if (el) el.value = v ?? '';
}

// ─── Init ─────────────────────────────────────────────────────

document.addEventListener('DOMContentLoaded', () => {
  loadDashboard();
  loadProfile();
  loadMatrix();
  loadVacancies();
});
