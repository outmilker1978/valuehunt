// ValueHunt Web UI — frontend logic

// ─── HH справочники ──────────────────────────────────────────

const HH_PROF_ROLES = [
  [107, 'Руководитель проектов (Project Manager)'],
  [73, 'Менеджер продукта (Product Manager)'],
  [104, 'Руководитель группы разработки (Engineering Manager / Delivery Manager)'],
  [157, 'Руководитель отдела аналитики (Head of Analytics)'],
  [125, 'Технический директор (CTO)'],
  [36, 'Директор по информационным технологиям (CIO)'],
];

function safeParse(val, fallback = []) {
  if (val === null || val === undefined) return fallback;
  if (typeof val !== 'string') return val;
  try { return JSON.parse(val); } catch { return fallback; }
}

// ─── Helpers ──────────────────────────────────────────────────

async function api(path, options = {}) {
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), 10000);
  try {
    const res = await fetch(path, {
      headers: { 'Content-Type': 'application/json' },
      cache: 'no-store',
      signal: controller.signal,
      ...options,
    });
    const ct = res.headers.get('content-type') || '';
    if (!ct.includes('application/json')) {
      const text = await res.text();
      throw new Error('Ответ не JSON (' + res.status + '): ' + text.slice(0, 200));
    }
    return res.json();
  } finally {
    clearTimeout(timeout);
  }
}

function showStatus(el, msg, ok = true) {
  el.textContent = msg;
  el.style.color = ok ? '#28a745' : '#dc3545';
  setTimeout(() => el.textContent = '', 3000);
}

// ─── Dashboard ───────────────────────────────────────────────

async function runScan() {
  const el = document.querySelector('#scan-result');
  const progress = document.getElementById('scan-progress');
  el.textContent = 'Сканирование всех профилей... это может занять 1-2 мин';
  el.style.color = '#666';
  try {
    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), 300000);
    const res = await fetch('/api/scan-all', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      signal: controller.signal,
    });
    clearTimeout(timeout);
    const data = await res.json();
    if (data.ok) {
      if (progress) {
        const parts = (data.per_profile || []).map(p =>
          `${p.profile_name}: ${p.error ? '❌ '+p.error : p.skipped ? '—' : p.found + ' вакансий, +' + (p.new_count || 0) + ' новых'}`
        );
        progress.textContent = parts.join(' | ');
      }
      el.textContent = data.message || 'Готово';
      el.style.color = '#28a745';
      setTimeout(() => {
        if (typeof fetchAndRender === 'function') fetchAndRender();
        else if (typeof loadDashboard === 'function') loadDashboard();
      }, 1000);
    } else {
      el.textContent = data.error || 'Ошибка при сканировании';
      el.style.color = '#dc3545';
    }
  } catch (e) {
    if (e.name === 'AbortError') {
      el.textContent = 'Сканирование прервано по таймауту (3 мин).';
    } else {
      el.textContent = 'Ошибка соединения с сервером';
    }
    el.style.color = '#dc3545';
  }
}

async function importRetro() {
  const el = document.getElementById('scan-result');
  const progress = document.getElementById('scan-progress');
  el.textContent = 'Импорт из Excel...';
  el.style.color = '#666';
  try {
    const resp = await fetch('/api/import-retro', { method: 'POST', headers: {'Content-Type': 'application/json'} });
    const data = await resp.json();
    if (!data.ok) { el.textContent = 'Ошибка: ' + (data.error || data.report?.error || '?'); el.style.color = '#dc3545'; return; }
    const r = data.report;
    el.innerHTML =
      `Импорт: лист <b>${r.sheet}</b> | создано <b>${r.created}</b> | обновлено <b>${r.updated}</b> | контактов <b>${r.contacts_created}</b> | ошибок <b>${r.errors?.length || 0}</b>`;
    el.style.color = '#28a745';
    if (r.errors?.length) console.warn('Import errors:', r.errors);
    setTimeout(() => location.reload(), 1500); // refresh dashboard
  } catch(e) {
    el.textContent = 'Ошибка: ' + e.message;
    el.style.color = '#dc3545';
  }
}

async function cleanAndRescan() {
  if (!confirm('Удалить ВСЕ вакансии из БД и запустить сканирование заново?\nКонтакты и компании НЕ пострадают.')) return;
  const el = document.querySelector('#scan-result');
  const progress = document.getElementById('scan-progress');
  el.textContent = 'Удаление вакансий...';
  el.style.color = '#666';
  try {
    const r1 = await fetch('/api/vacancies/clean', { method: 'POST' });
    const d1 = await r1.json();
    if (!d1.ok) { el.textContent = d1.error || 'Ошибка очистки'; el.style.color = '#dc3545'; return; }
    el.textContent = 'Вакансии удалены. Запуск сканирования...';
    setTimeout(() => runScan(), 300);
  } catch (e) {
    el.textContent = 'Ошибка соединения: ' + e.message;
    el.style.color = '#dc3545';
  }
}
// ─── Profile ──────────────────────────────────────────────────

async function loadProfile() {
  const profile = await api('/api/profile');
  if (!profile) return;

  setVal('field-name', profile.name);
  setVal('field-location', profile.location);
  setVal('field-salary', profile.salary_expectation);
  setVal('field-hh_token', profile.hh_access_token);
  setVal('field-hh_resume_id', profile.hh_resume_id || 'ff6f2e8eff1065d7ea0039ed1f314c5a767845');
  setVal('field-telegram_chat_id', profile.telegram_chat_id);
  setVal('field-search-period', (profile.search_filters || {}).search_period || '7');

  // Fields moved to top level for HH-like structure
  const pf = profile;
  setVal('field-titles', (pf.titles || (pf.search_filters || {}).titles || []).join(', '));
  setVal('field-keywords', (pf.keywords || (pf.search_filters || {}).keywords || []).join(', '));
  setCheckboxGroup('field-experience', pf.experience || (pf.search_filters || {}).experience || []);
  setCheckboxGroup('field-employment', pf.employment || (pf.search_filters || {}).employment || []);
  setCheckboxGroup('field-schedule', pf.schedule || (pf.search_filters || {}).schedule || []);
  setCheckboxGroup('field-work_formats', pf.work_formats || []);
  renderProfRoles(pf.professional_roles || (pf.search_filters || {}).professional_roles || [107, 73]);
  updateFilterPreview();
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
  const titles = val('field-titles').split(',').map(s => s.trim()).filter(Boolean);
  const keywords = val('field-keywords').split(',').map(s => s.trim()).filter(Boolean);

  const profRoleCbs = document.querySelectorAll('#field-prof-roles input[type="checkbox"]:checked');
  const professional_roles = Array.from(profRoleCbs).map(cb => parseInt(cb.value)).filter(n => !isNaN(n));

  const experience = getCheckboxValues('field-experience');
  const employment = getCheckboxValues('field-employment');
  const schedule = getCheckboxValues('field-schedule');
  const searchPeriod = val('field-search-period') || '7';
  const workFormats = getCheckboxValues('field-work_formats');

  const regions = val('field-location').split(',').map(s => s.trim()).filter(Boolean);

  const body = {
    name: val('field-name'),
    location: val('field-location'),
    work_format: workFormats.length ? workFormats[0] : 'remote',
    work_formats: workFormats.length ? workFormats : ['remote'],
    salary_expectation: salary,
    titles,
    keywords,
    experience,
    employment,
    schedule,
    professional_roles: professional_roles.length ? professional_roles : [107, 73],
    search_filters: {
      regions,
      titles,
      keywords,
      professional_roles: professional_roles.length ? professional_roles : [107, 73],
      experience,
      employment,
      schedule,
      salary_from: salary,
      search_period: searchPeriod,
    },
  };
  const res = await api('/api/profile', {
    method: 'POST',
    body: JSON.stringify(body),
  });
  showStatus(document.getElementById('profile-status'), 'Профиль сохранён');
  updateFilterPreview();
}

function updateFilterPreview() {
  const labels = { noExperience: 'Без опыта', between1And3: '1-3 года', between3And6: '3-6 лет', moreThan6: 'Более 6 лет' };
  const empLabels = { full: 'Полная', part: 'Частичная', project: 'Проектная', volunteer: 'Волонтёрство', probation: 'Стажировка' };
  const schLabels = { fullDay: 'Полный день', shift: 'Сменный', flexible: 'Гибкий', remote: 'Удалёнка', flyInFlyOut: 'Вахта' };
  const roleNames = Object.fromEntries(HH_PROF_ROLES);

  document.getElementById('filter-text').textContent = val('field-titles') || '—';
  document.getElementById('filter-regions').textContent = val('field-location') || '—';
  document.getElementById('filter-proles').textContent = getCheckboxValues('field-prof-roles').map(v => roleNames[parseInt(v)] || v).join(', ') || '—';
  document.getElementById('filter-exp').textContent = getCheckboxValues('field-experience').map(v => labels[v] || v).join(', ') || '—';
  document.getElementById('filter-emp').textContent = getCheckboxValues('field-employment').map(v => empLabels[v] || v).join(', ') || '—';
  document.getElementById('filter-sch').textContent = getCheckboxValues('field-schedule').map(v => schLabels[v] || v).join(', ') || '—';
  const wfLabels = { remote: 'Удалёнка', hybrid: 'Гибрид', office: 'Офис' };
  document.getElementById('filter-work-format').textContent = getCheckboxValues('field-work_formats').map(v => wfLabels[v] || v).join(', ') || '—';
  document.getElementById('filter-salary').textContent = val('field-salary') ? val('field-salary') + ' ₽' : '—';
  document.getElementById('filter-period').textContent = val('field-search-period') ? val('field-search-period') + ' дн.' : 'всё время';
}

async function uploadResume() {
  const fileInput = document.getElementById('resume-file-input');
  const statusEl = document.getElementById('upload-status');
  const file = fileInput.files[0];
  if (!file) {
    statusEl.textContent = 'Выбери файл .txt';
    statusEl.style.color = '#dc3545';
    return;
  }
  const formData = new FormData();
  formData.append('file', file);
  statusEl.textContent = 'Загрузка...';
  statusEl.style.color = '#666';
  try {
    const res = await fetch('/api/profile/upload-resume', { method: 'POST', body: formData });
    const data = await res.json();
    if (data.ok) {
      statusEl.textContent = 'Готово! Профиль заполнен.';
      statusEl.style.color = '#28a745';
      loadProfile();
    } else {
      statusEl.textContent = data.error || 'Ошибка';
      statusEl.style.color = '#dc3545';
    }
  } catch (e) {
    statusEl.textContent = 'Ошибка соединения';
    statusEl.style.color = '#dc3545';
  }
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

  root.innerHTML = groups.map((g, gi) => {
    const allCriteria = g.criteria || [];
    const critMap = {};
    allCriteria.forEach(c => { critMap[c.id] = c; });
    return `
    <div class="matrix-group" data-group-id="${g.id}">
      <h3>
        <span>${gi + 1}. ${g.name}</span>
        <span class="weight-control">
          Вес группы:
          <input type="number" class="input criterion-weight" value="${g.weight}" min="1" max="10"
                 onchange="updateGroupWeight('${g.id}', this.value)" />
        </span>
      </h3>
      ${allCriteria.map(c => {
        const altIds = c.alternatives || [];
        const altOptions = altIds
          .filter(aId => critMap[aId])
          .map(aId => `<option value="${aId}">${critMap[aId].name}</option>`).join('');
        return `
        <div class="criterion-row">
          <span class="criterion-name">
            <select class="input criterion-alternative" style="font-weight:600;"
                    onchange="swapCriterion('${g.id}', '${c.id}', this.value)">
              <option value="${c.id}" selected>${c.name}</option>
              ${altOptions}
            </select>
          </span>
          <span class="criterion-desc" style="font-size:12px;">${c.description || ''}</span>
          <span class="weight-control">
            Вес: <input type="number" class="input criterion-weight" value="${c.weight}" min="1" max="10"
                        onchange="updateCriterionWeight('${g.id}', '${c.id}', this.value)" />
          </span>
        </div>`;
      }).join('')}
    </div>`;
  }).join('');
}

async function swapCriterion(groupId, oldId, newId) {
  if (oldId === newId) return;
  const matrix = await api('/api/matrix');
  const group = matrix.groups.find(g => g.id === groupId);
  if (!group) return;
  const oldIdx = group.criteria.findIndex(c => c.id === oldId);
  const newC = group.criteria.find(c => c.id === newId);
  const oldC = group.criteria[oldIdx];
  if (oldIdx === -1 || !newC || !oldC) return;
  // Swap the two criteria
  const newIdx = group.criteria.findIndex(c => c.id === newId);
  group.criteria[oldIdx] = newC;
  group.criteria[newIdx] = oldC;
  await api('/api/matrix/save', {
    method: 'POST',
    body: JSON.stringify(matrix),
  });
  loadMatrix();
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
// Vacancies page now has its own inline JS — nothing needed here.

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
  loadMatrix();
});
