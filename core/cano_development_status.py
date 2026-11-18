"""Owner-visible status for existing CANO code jobs (test-first placeholder)."""

def summarize_recent_code_jobs(jobs):
    return {"total": 0, "deployed": 0, "active": 0, "blocked": 0,
            "last_pr_url": None}

def render_owner_code_status(st, jobs):
    result = summarize_recent_code_jobs(jobs)
    st.info("CANO kod işleri: henüz gösterilemiyor.")
    return result
