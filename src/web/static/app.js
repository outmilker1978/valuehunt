// ValueHunt Web UI — frontend logic

// ─── HH справочники ──────────────────────────────────────────

const HH_PROF_ROLES = [
  [107, 'Руководитель проектов (Project Manager)'],
  [73, 'Менеджер продукта (Product Manager)'],
  [150, 'Владелец продукта (Product Owner)'],
  [151, 'Delivery Manager'],
  [152, 'Program Manager'],
  [156, 'Agile-коуч (Agile Coach)'],
  [157, 'Scrum-мастер (Scrum Master)'],
  [12, 'Директор по информационным технологиям (CIO)'],
  [113, 'Технический директор (CTO)'],
  [114, 'Руководитель группы разработки (EM)'],
  [101, 'Руководитель отдела ИТ'],
  [117, 'Руководитель отдела анализа'],
  [118, 'Руководитель отдела разработки'],
  [125, 'Бизнес-аналитик'],
  [124, 'Системный аналитик'],
  [160, 'Head of Product'],
  [96, 'Руководитель отдела маркетинга'],
  [112, 'Руководитель отдела поддержки'],
  [158, 'Техлид (Tech Lead)'],
  [13, 'Директор департамента ИТ'],
];

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
  setVal('field-salary-filter', profile.salary_expectation);
  setVal('field-hh_token', profile.hh_access_token);
  setVal('field-hh_resume_id', profile.hh_resume_id);
  setVal('field-telegram_chat_id', profile.telegram_chat_id);

  const filters = profile.search_filters || {};
  setVal('field-regions', (filters.regions || []).join(', '));
  setVal('field-titles', (filters.titles || []).join(', '));
  setVal('field-keywords', (filters.keywords || []).join(', '));
  setVal('field-search-period', filters.search_period || '7');

  renderProfRoles(filters.professional_roles || [107, 73]);

  setCheckboxGroup('field-experience', filters.experience || []);
  setCheckboxGroup('field-employment', filters.employment || []);
  setCheckboxGroup('field-schedule', filters.schedule || []);
}

function renderProfRoles(selected) {
  const container = document.getElementById('field-prof-roles');
  if (!container) return;
  const sel = new Set(selected);
  container.innerHTML = HH_PROF_ROLES.map(([code, name]) =>
    `<label class="checkbox-label"><input type="checkbox" name="prof_role" value="${code}" ${sel.has(code) ? 'checked' : ''} /> ${name}</label>`
  ).join('');
}

function setCheckboxGroup(containerId, values) {
  const container = document.getElementById(containerId);
  if (!container) return;
  const valSet = new Set(Array.isArray(values) ? values : [values].filter(Boolean));
  container.querySelectorAll('input[type="checkbox"]').forEach(cb => {
    cb.checked = valSet.has(cb.value);
  });
}

function getCheckboxValues(containerId) {
  const container = document.getElementById(containerId);
  if (!container) return [];
  return Array.from(container.querySelectorAll('input[type="checkbox"]:checked'))
    .map(cb => cb.value);
}

async function saveProfile() {
  const salary = parseInt(val('field-salary')) || 0;
  const body = {
    name: val('field-name'),
    location: val('field-location'),
    work_format: val('field-work_format'),
    salary_expectation: salary,
    search_filters: { salary_from: salary },
  };
  const res = await api('/api/profile', {
    method: 'POST',
    body: JSON.stringify(body),
  });
  setVal('field-salary-filter', salary);
  showStatus(document.getElementById('profile-status'), 'Сохранено');
}

async function saveFilters() {
  const regions = val('field-regions').split(',').map(s => s.trim()).filter(Boolean);
  const titles = val('field-titles').split(',').map(s => s.trim()).filter(Boolean);
  const keywords = val('field-keywords').split(',').map(s => s.trim()).filter(Boolean);

  const profRoleCbs = document.querySelectorAll('#field-prof-roles input[type="checkbox"]:checked');
  const professional_roles = Array.from(profRoleCbs).map(cb => parseInt(cb.value)).filter(n => !isNaN(n));

  const search_filters = {
    regions,
    titles,
    keywords,
    professional_roles: professional_roles.length ? professional_roles : [107, 73],
    experience: getCheckboxValues('field-experience'),
    employment: getCheckboxValues('field-employment'),
    schedule: getCheckboxValues('field-schedule'),
    salary_from: parseInt(val('field-salary')) || 0,
    search_period: val('field-search-period'),
  };

  const res = await api('/api/profile', {
    method: 'POST',
    body: JSON.stringify({ search_filters }),
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
