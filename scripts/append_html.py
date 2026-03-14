import sys

html_code = """
# ───────────────────────────────────────────────
#  4. HTML Dashboard (Interactive)
# ───────────────────────────────────────────────

def generate_html(deal: Dict, analyst_data: Dict, agent_results: List[Dict]) -> bytes:
    \"\"\"
    Generate an interactive HTML dashboard with deal details and agent findings.
    \"\"\"
    html = [
        "<html><head><title>DealForge Dashboard</title>",
        "<style>",
        "body { font-family: 'Helvetica Neue', Helvetica, Arial, sans-serif; background-color: #f4f7f6; color: #333; margin: 0; padding: 20px; }",
        ".container { max-width: 1200px; margin: auto; background: #fff; padding: 30px; border-radius: 8px; box-shadow: 0 4px 6px rgba(0,0,0,0.1); }",
        "h1 { color: #003366; border-bottom: 2px solid #0072ce; padding-bottom: 10px; }",
        "h2 { color: #0072ce; margin-top: 30px; }",
        ".card { background: #fafafa; border: 1px solid #e0e0e0; padding: 15px; border-radius: 5px; margin-bottom: 15px; }",
        ".badge { display: inline-block; padding: 5px 10px; border-radius: 12px; background: #003366; color: #fff; font-size: 12px; font-weight: bold; }",
        "</style></head><body><div class='container'>"
    ]
    
    html.append(f"<h1>{deal.get('name', 'Deal Analysis Dashboard')}</h1>")
    html.append(f"<p><strong>Target:</strong> {deal.get('target_company', 'N/A')}</p>")
    html.append(f"<p><strong>Industry:</strong> {deal.get('industry', 'N/A')}</p>")
    
    score = deal.get("final_score")
    score_text = f"{round(score * 100)}%" if score is not None else "Pending"
    html.append(f"<p><strong>Score:</strong> <span class='badge'>{score_text}</span></p>")
    
    exec_sum = analyst_data.get("executive_summary", {})
    if exec_sum:
        html.append("<h2>Executive Summary</h2>")
        html.append(f"<div class='card'><p><b>Situation:</b> {exec_sum.get('situation', '')}</p>")
        html.append(f"<p><b>Complication:</b> {exec_sum.get('complication', '')}</p>")
        html.append(f"<p><b>Question:</b> {exec_sum.get('question', '')}</p>")
        html.append(f"<p><b>Recommendation:</b> {exec_sum.get('answer', deal.get('final_recommendation', ''))}</p></div>")
    
    html.append("<h2>Agent Findings</h2>")
    for r in agent_results:
        agent_type = r.get("agent_type", "Agent").replace('_', ' ').title()
        reasoning = r.get("reasoning", "").replace("\\n", "<br/>")
        conf = round(r.get("confidence", 0) * 100)
        html.append(f"<div class='card'><h3>{agent_type} <span class='badge'>{conf}% Confidence</span></h3>")
        html.append(f"<p>{reasoning}</p></div>")
        
    html.append("</div></body></html>")
    return "".join(html).encode("utf-8")
"""

with open(
    r"f:\code project\Kimi_Agent_DealForge AI PRD\dealforge-ai\backend\app\core\reports\report_generator.py",
    "a",
    encoding="utf-8",
) as f:
    f.write(html_code)

print("HTML added")
