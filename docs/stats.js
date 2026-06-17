// ValueHunt Dashboard — статистика
// Данные обновляются через GitHub Actions

async function loadStats() {
  try {
    const res = await fetch('stats.json');
    return await res.json();
  } catch {
    return getDefaultData();
  }
}

function getDefaultData() {
  return {
    funnel: { просмотрено: 0, откликнуто: 0, приглашения: 0, собеседования: 0, офферы: 0 },
    vacancies_by_day: [],
    statuses: { new: 0, responded: 0, invited: 0, interview: 0, offer: 0, rejected: 0, archived: 0 },
  };
}

function renderFunnelChart(ctx, data) {
  new Chart(ctx, {
    type: 'bar',
    data: {
      labels: Object.keys(data.funnel),
      datasets: [{
        label: 'Количество',
        data: Object.values(data.funnel),
        backgroundColor: ['#4CAF50', '#FF9800', '#2196F3', '#9C27B0', '#F44336'],
      }],
    },
  });
}

function renderVacanciesChart(ctx, data) {
  const days = data.vacancies_by_day.map(d => d.date);
  const counts = data.vacancies_by_day.map(d => d.count);
  new Chart(ctx, {
    type: 'line',
    data: {
      labels: days,
      datasets: [{ label: 'Новые вакансии', data: counts, borderColor: '#2196F3', fill: false }],
    },
  });
}

function renderStatusChart(ctx, data) {
  new Chart(ctx, {
    type: 'doughnut',
    data: {
      labels: Object.keys(data.statuses),
      datasets: [{
        data: Object.values(data.statuses),
        backgroundColor: ['#9E9E9E', '#FF9800', '#2196F3', '#9C27B0', '#4CAF50', '#F44336', '#607D8B'],
      }],
    },
  });
}

document.addEventListener('DOMContentLoaded', async () => {
  const data = await loadStats();
  renderFunnelChart(document.getElementById('funnelChart'), data);
  renderVacanciesChart(document.getElementById('vacanciesChart'), data);
  renderStatusChart(document.getElementById('statusChart'), data);
});
