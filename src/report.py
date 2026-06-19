import json
import sys
from pathlib import Path

# Ensure project root is on path
_project_root = Path(__file__).resolve().parent.parent
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))

from src.models import init_db, DB_PATH
from data.demo_data import generate as generate_demo
from src.analytics import (
    total_stats,
    funnel,
    conversion_rates,
    applications_by_day,
    applications_by_week,
    score_distribution,
    top_companies,
    top_industries,
    avg_response_time,
)

OUTPUT_DIR = Path(__file__).resolve().parent.parent / "output"
TEMPLATE = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>ValueHunt — Job Search Dashboard</title>
<script src="https://cdn.jsdelivr.net/npm/chart.js@4"></script>
<style>
  * {{ margin:0; padding:0; box-sizing:border-box; }}
  body {{ font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif; background:#f5f7fa; color:#1a1a2e; }}
  .header {{ background:linear-gradient(135deg,#1a1a2e,#16213e); color:#fff; padding:32px 24px; }}
  .header h1 {{ font-size:28px; margin-bottom:4px; }}
  .header p {{ color:#8899b4; font-size:14px; }}
  .container {{ max-width:1200px; margin:0 auto; padding:24px; }}
  .stats-grid {{ display:grid; grid-template-columns:repeat(auto-fit,minmax(180px,1fr)); gap:16px; margin-bottom:24px; }}
  .stat-card {{ background:#fff; border-radius:12px; padding:20px; text-align:center; box-shadow:0 1px 4px rgba(0,0,0,0.06); }}
  .stat-card .value {{ font-size:32px; font-weight:700; }}
  .stat-card .label {{ font-size:12px; color:#889; margin-top:4px; text-transform:uppercase; letter-spacing:0.5px; }}
  .card {{ background:#fff; border-radius:12px; padding:20px; margin-bottom:20px; box-shadow:0 1px 4px rgba(0,0,0,0.06); }}
  .card h2 {{ font-size:16px; margin-bottom:16px; color:#1a1a2e; }}
  .chart-row {{ display:grid; grid-template-columns:1fr 1fr; gap:20px; }}
  @media (max-width:768px) {{ .chart-row {{ grid-template-columns:1fr; }} }}
  .conversion-grid {{ display:grid; grid-template-columns:repeat(auto-fit,minmax(120px,1fr)); gap:12px; }}
  .conversion-item {{ text-align:center; padding:12px; background:#f8f9fa; border-radius:8px; }}
  .conversion-item .pct {{ font-size:24px; font-weight:700; }}
  .conversion-item .pct.positive {{ color:#28a745; }}
  .conversion-item .pct.neutral {{ color:#ffc107; }}
  .conversion-item .pct.negative {{ color:#dc3545; }}
  .conversion-item .desc {{ font-size:11px; color:#889; margin-top:4px; }}
  .funnel-bar {{ display:flex; align-items:center; margin:8px 0; gap:12px; }}
  .funnel-bar .label {{ width:100px; font-size:13px; text-align:right; }}
  .funnel-bar .bar {{ flex:1; height:32px; border-radius:6px; display:flex; align-items:center; padding:0 12px; color:#fff; font-weight:600; font-size:13px; transition:width 0.6s; }}
  .company-list {{ display:grid; grid-template-columns:repeat(auto-fill,minmax(200px,1fr)); gap:8px; }}
  .company-item {{ display:flex; justify-content:space-between; padding:8px 12px; background:#f8f9fa; border-radius:6px; font-size:13px; }}
  .company-item .name {{ color:#1a1a2e; }}
  .company-item .cnt {{ font-weight:600; color:#007bff; }}
  .footer {{ text-align:center; padding:24px; font-size:12px; color:#889; }}
  .generated {{ font-size:11px; color:#aaa; text-align:right; margin-top:8px; }}
</style>
</head>
<body>
<div class="header">
  <div class="container">
    <h1>ValueHunt</h1>
    <p>Job Search Analytics Dashboard — Track, score, and optimize your IT job applications</p>
  </div>
</div>

<div class="container">

  <!-- Stats Row -->
  <div class="stats-grid">
    <div class="stat-card">
      <div class="value" style="color:#007bff;">{TOTAL_APPS}</div>
      <div class="label">Applications</div>
    </div>
    <div class="stat-card">
      <div class="value" style="color:#28a745;">{TOTAL_COMPANIES}</div>
      <div class="label">Companies</div>
    </div>
    <div class="stat-card">
      <div class="value" style="color:{AVG_SCORE_COLOR};">{AVG_SCORE}</div>
      <div class="label">Avg UES Score</div>
    </div>
    <div class="stat-card">
      <div class="value" style="color:#17a2b8;">{AVG_REPLY}d</div>
      <div class="label">Avg Reply Time</div>
    </div>
    <div class="stat-card">
      <div class="value" style="color:{OFFER_RATE_COLOR};">{OFFER_RATE}%</div>
      <div class="label">Offer Rate</div>
    </div>
  </div>

  <!-- Funnel + Conversion -->
  <div class="chart-row">
    <div class="card">
      <h2>Application Funnel</h2>
      <div id="funnel-bars">{FUNNEL_BARS}</div>
    </div>
    <div class="card">
      <h2>Conversion Rates</h2>
      <div class="conversion-grid">{CONVERSION}</div>
    </div>
  </div>

  <!-- Charts Row -->
  <div class="chart-row">
    <div class="card">
      <h2>Applications by Day (30 days)</h2>
      <canvas id="chart-day" height="200"></canvas>
    </div>
    <div class="card">
      <h2>Applications by Week</h2>
      <canvas id="chart-week" height="200"></canvas>
    </div>
  </div>

  <div class="chart-row">
    <div class="card">
      <h2>UES Score Distribution</h2>
      <canvas id="chart-score" height="200"></canvas>
    </div>
    <div class="card">
      <h2>Top Industries</h2>
      <canvas id="chart-industry" height="200"></canvas>
    </div>
  </div>

  <!-- Top Companies -->
  <div class="card">
    <h2>Top Companies by Applications</h2>
    <div class="company-list">{COMPANIES}</div>
  </div>

  <div class="generated">Generated: {TIMESTAMP}</div>
</div>

<script>
new Chart(document.getElementById('chart-day'), {{
  type:'bar',
  data:{{
    labels:{DAY_LABELS},
    datasets:[{{
      label:'Applications',
      data:{DAY_DATA},
      backgroundColor:'#007bff',
      borderRadius:4,
    }}]
  }},
  options:{{
    responsive:true,
    plugins:{{ legend:{{ display:false }} }},
    scales:{{ y:{{ beginAtZero:true, ticks:{{ stepSize:1 }} }} }}
  }}
}});

new Chart(document.getElementById('chart-week'), {{
  type:'line',
  data:{{
    labels:{WEEK_LABELS},
    datasets:[{{
      label:'Applications per week',
      data:{WEEK_DATA},
      borderColor:'#28a745',
      backgroundColor:'rgba(40,167,69,0.1)',
      fill:true,
      tension:0.3,
      pointRadius:4,
    }}]
  }},
  options:{{
    responsive:true,
    plugins:{{ legend:{{ display:false }} }},
    scales:{{ y:{{ beginAtZero:true, ticks:{{ stepSize:1 }} }} }}
  }}
}});

new Chart(document.getElementById('chart-score'), {{
  type:'pie',
  data:{{
    labels:{SCORE_LABELS},
    datasets:[{{
      data:{SCORE_DATA},
      backgroundColor:['#28a745','#007bff','#ffc107','#fd7e14','#dc3545'],
      borderWidth:2,
      borderColor:'#fff',
    }}]
  }},
  options:{{
    responsive:true,
    plugins:{{ legend:{{ position:'bottom' }} }}
  }}
}});

new Chart(document.getElementById('chart-industry'), {{
  type:'doughnut',
  data:{{
    labels:{INDUSTRY_LABELS},
    datasets:[{{
      data:{INDUSTRY_DATA},
      backgroundColor:['#007bff','#28a745','#ffc107','#dc3545','#17a2b8','#6f42c1','#fd7e14','#20c997','#e83e8c','#6610f2'],
      borderWidth:2,
      borderColor:'#fff',
    }}]
  }},
  options:{{
    responsive:true,
    plugins:{{ legend:{{ position:'bottom' }} }}
  }}
}});
</script>

<div class="footer">
  ValueHunt — Open Source Job Search Tracker &middot; Built with Python &middot; Charts by Chart.js
</div>
</body>
</html>"""


def build_dashboard():
    init_db()

    # Check if DB has data; if not, generate demo
    from src.models import get_connection
    conn = get_connection()
    count = conn.execute("SELECT COUNT(*) as c FROM applications").fetchone()["c"]
    conn.close()
    if count == 0:
        print("No data found. Generating demo data...")
        generate_demo()

    stats = total_stats()
    f = funnel()
    conv = conversion_rates()
    days = applications_by_day(30)
    weeks = applications_by_week(90)
    scores = score_distribution(5)
    companies = top_companies(12)
    industries = top_industries(8)
    avg_reply = avg_response_time()

    offer_rate = round(f["offer"] / (f["viewed"] or 1) * 100, 1)

    # Funnel bar HTML
    funnel_steps = [
        ("Viewed", f["viewed"], "#007bff"),
        ("Invited", f["invited"], "#17a2b8"),
        ("Interviewed", f["interview"], "#28a745"),
        ("Offer", f["offer"], "#ffc107"),
        ("Accepted", f["accepted"], "#1a1a2e"),
        ("Rejected", f["rejected"], "#dc3545"),
    ]
    max_funnel = max((v for _, v, _ in funnel_steps), default=1)
    funnel_bars = "".join(
        f'<div class="funnel-bar">'
        f'<span class="label">{name}</span>'
        f'<div class="bar" style="width:{max(5, v/max_funnel*100):.0f}%;background:{color};">{v}</div>'
        f'</div>'
        for name, v, color in funnel_steps
    )

    # Conversion HTML
    conv_items = [
        ("View → Invite", conv["view_to_invite"], "positive" if conv["view_to_invite"] > 20 else "neutral"),
        ("Invite → Interview", conv["invite_to_interview"], "positive" if conv["invite_to_interview"] > 50 else "neutral"),
        ("Interview → Offer", conv["interview_to_offer"], "positive" if conv["interview_to_offer"] > 30 else "neutral"),
        ("Offer → Accept", conv["offer_to_accept"], "positive" if conv["offer_to_accept"] > 50 else "neutral"),
        ("Overall", conv["overall"], "positive" if conv["overall"] > 5 else "negative"),
    ]
    conversion_html = "".join(
        f'<div class="conversion-item"><div class="pct {cls}">{v}%</div><div class="desc">{name}</div></div>'
        for name, v, cls in conv_items
    )

    # Company list
    companies_html = "".join(
        f'<div class="company-item"><span class="name">{c["name"]}</span><span class="cnt">{c["count"]}</span></div>'
        for c in companies
    )

    # Chart data
    day_labels = json.dumps([d["date"][-5:] for d in days])
    day_data = json.dumps([d["count"] for d in days])
    week_labels = json.dumps([w["week"] for w in weeks])
    week_data = json.dumps([w["count"] for w in weeks])

    score_labels = json.dumps([s["bucket"] for s in scores])
    score_data = json.dumps([s["count"] for s in scores])

    industry_labels = json.dumps([i["name"] for i in industries])
    industry_data = json.dumps([i["count"] for i in industries])

    avg_score_color = "#28a745" if stats["avg_score"] >= 7 else ("#ffc107" if stats["avg_score"] >= 5 else "#dc3545")
    offer_rate_color = "#28a745" if offer_rate >= 10 else ("#ffc107" if offer_rate >= 5 else "#dc3545")

    html = TEMPLATE.format(
        TOTAL_APPS=stats["total_applications"],
        TOTAL_COMPANIES=stats["total_companies"],
        AVG_SCORE=stats["avg_score"],
        AVG_SCORE_COLOR=avg_score_color,
        AVG_REPLY=avg_reply,
        OFFER_RATE=offer_rate,
        OFFER_RATE_COLOR=offer_rate_color,
        FUNNEL_BARS=funnel_bars,
        CONVERSION=conversion_html,
        COMPANIES=companies_html,
        DAY_LABELS=day_labels,
        DAY_DATA=day_data,
        WEEK_LABELS=week_labels,
        WEEK_DATA=week_data,
        SCORE_LABELS=score_labels,
        SCORE_DATA=score_data,
        INDUSTRY_LABELS=industry_labels,
        INDUSTRY_DATA=industry_data,
        TIMESTAMP=__import__("datetime").datetime.now().strftime("%Y-%m-%d %H:%M"),
    )

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    out_path = OUTPUT_DIR / "index.html"
    out_path.write_text(html, encoding="utf-8")
    print(f"Dashboard generated: {out_path.resolve()}")
    return out_path


if __name__ == "__main__":
    build_dashboard()
