import os
from io import BytesIO
from urllib.parse import quote_plus

import requests
import streamlit as st
from docx import Document
from fpdf import FPDF

BACKEND_URL = os.environ.get("BACKEND_URL", "http://localhost:8000")

st.set_page_config(page_title="AI Job Seeker Agent", layout="wide")


def _init_state() -> None:
    defaults = {
        "user_id": None,
        "profile_id": None,
        "parsed_resume": None,
        "jobs": [],
        "gap_results": {},
        "job_query": "",
        "job_query_source_profile": None,
        "chat_history": [],
    }
    for key, value in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = value


def _resume_derived_query(resume: dict) -> str:
    """Best-effort search query from the parsed resume: most recent job title,
    falling back to top skills, so search reflects what the candidate actually
    is/has rather than a generic default."""
    experience = resume.get("experience") or []
    if experience and experience[0].get("title"):
        return experience[0]["title"]
    skills = resume.get("skills") or []
    if skills:
        return " ".join(skills[:3])
    return ""


def _bridge_link(gap: str) -> str:
    return "https://www.google.com/search?q=" + quote_plus(f"how to learn {gap} for free")


def _contact_line(resume: dict) -> str:
    contact = resume.get("contact_info") or {}
    bits = [contact.get(k) for k in ("email", "phone", "linkedin_url", "github_url", "portfolio_url")]
    return " | ".join(b for b in bits if b)


def _pdf_safe(text: str) -> str:
    # Core PDF fonts only support latin-1; swap anything else for a safe lookalike
    # so an unusual character in a name/skill can't crash the whole download.
    return text.encode("latin-1", "replace").decode("latin-1")


def _build_resume_pdf(resume: dict) -> bytes:
    contact = resume.get("contact_info") or {}
    pdf = FPDF()
    pdf.set_auto_page_break(auto=True, margin=15)
    pdf.add_page()

    def line(text: str, height: float = 6) -> None:
        # multi_cell leaves the cursor at the right edge of the last line by
        # default, which starves the next call of horizontal space — force it
        # back to the left margin, next line, every time.
        pdf.multi_cell(0, height, _pdf_safe(text), new_x="LMARGIN", new_y="NEXT")

    if contact.get("full_name"):
        pdf.set_font("Helvetica", "B", 16)
        pdf.cell(0, 10, _pdf_safe(contact["full_name"]), new_x="LMARGIN", new_y="NEXT")

    contact_line = _contact_line(resume)
    if contact_line:
        pdf.set_font("Helvetica", "", 10)
        pdf.cell(0, 6, _pdf_safe(contact_line), new_x="LMARGIN", new_y="NEXT")
    pdf.ln(4)

    def heading(title: str) -> None:
        pdf.set_font("Helvetica", "B", 12)
        pdf.cell(0, 8, title, new_x="LMARGIN", new_y="NEXT")
        pdf.set_font("Helvetica", "", 10)

    if resume.get("summary"):
        heading("Summary")
        line(resume["summary"])
        pdf.ln(2)

    if resume.get("skills"):
        heading("Skills")
        line(", ".join(resume["skills"]))
        pdf.ln(2)

    if resume.get("experience"):
        heading("Experience")
        for exp in resume["experience"]:
            pdf.set_font("Helvetica", "B", 10)
            line(f"{exp.get('title', '')} - {exp.get('company', '')} ({exp.get('duration', '')})")
            pdf.set_font("Helvetica", "", 10)
            for hl in exp.get("highlights", []):
                line(f"  - {hl}")
        pdf.ln(2)

    if resume.get("education"):
        heading("Education")
        for edu in resume["education"]:
            degree = f"{edu.get('degree', '')} {edu.get('field_of_study') or ''}".strip()
            line(f"{degree} - {edu.get('institution', '')} ({edu.get('graduation_year') or ''})")
        pdf.ln(2)

    if resume.get("certifications"):
        heading("Certifications")
        line(", ".join(resume["certifications"]))

    return bytes(pdf.output())


def _build_resume_docx(resume: dict) -> bytes:
    contact = resume.get("contact_info") or {}
    doc = Document()

    if contact.get("full_name"):
        doc.add_heading(contact["full_name"], level=1)

    contact_line = _contact_line(resume)
    if contact_line:
        doc.add_paragraph(contact_line)

    if resume.get("summary"):
        doc.add_heading("Summary", level=2)
        doc.add_paragraph(resume["summary"])

    if resume.get("skills"):
        doc.add_heading("Skills", level=2)
        doc.add_paragraph(", ".join(resume["skills"]))

    if resume.get("experience"):
        doc.add_heading("Experience", level=2)
        for exp in resume["experience"]:
            p = doc.add_paragraph()
            run = p.add_run(f"{exp.get('title', '')} — {exp.get('company', '')} ({exp.get('duration', '')})")
            run.bold = True
            for hl in exp.get("highlights", []):
                doc.add_paragraph(hl, style="List Bullet")

    if resume.get("education"):
        doc.add_heading("Education", level=2)
        for edu in resume["education"]:
            degree = f"{edu.get('degree', '')} {edu.get('field_of_study') or ''}".strip()
            doc.add_paragraph(f"{degree} — {edu.get('institution', '')} ({edu.get('graduation_year') or ''})")

    if resume.get("certifications"):
        doc.add_heading("Certifications", level=2)
        doc.add_paragraph(", ".join(resume["certifications"]))

    buf = BytesIO()
    doc.save(buf)
    return buf.getvalue()


_init_state()

with st.sidebar:
    st.header("Account")
    email = st.text_input("Email", key="email_input")
    if st.button("Sign in / Register"):
        try:
            resp = requests.post(f"{BACKEND_URL}/users", params={"email": email}, timeout=10)
            resp.raise_for_status()
            st.session_state.user_id = resp.json()["id"]
            st.success(f"Signed in as {email}")
        except requests.RequestException as exc:
            st.error(f"Could not sign in: {exc}")

    if st.session_state.user_id:
        st.caption(f"user_id: {st.session_state.user_id}")

st.title("AI Job Seeker Agent")

if not st.session_state.user_id:
    st.info("Sign in with an email in the sidebar to get started.")
    st.stop()

tab_profile, tab_search, tab_apps, tab_chat = st.tabs(["Profile", "Job Search", "Applications", "Chat Assistant"])

# ---------------------------------------------------------------------------
# Profile tab
# ---------------------------------------------------------------------------
with tab_profile:
    st.subheader("Upload your resume (PDF)")
    uploaded_file = st.file_uploader("Resume", type=["pdf"])

    if uploaded_file and st.button("Parse resume"):
        with st.spinner("Extracting structured data from your resume..."):
            try:
                files = {"file": (uploaded_file.name, uploaded_file.getvalue(), "application/pdf")}
                resp = requests.post(
                    f"{BACKEND_URL}/profiles/upload-resume",
                    params={"user_id": st.session_state.user_id},
                    files=files,
                    timeout=60,
                )
                resp.raise_for_status()
                data = resp.json()
                st.session_state.profile_id = data["profile_id"]
                st.session_state.parsed_resume = data["parsed_resume"]
                st.success("Resume parsed successfully.")
            except requests.RequestException as exc:
                st.error(f"Failed to parse resume: {exc}")

    if st.session_state.parsed_resume:
        st.subheader("Parsed resume")
        st.json(st.session_state.parsed_resume)
        dl_col1, dl_col2 = st.columns(2)
        with dl_col1:
            st.download_button(
                "Download resume (.pdf)",
                data=_build_resume_pdf(st.session_state.parsed_resume),
                file_name="resume.pdf",
                mime="application/pdf",
            )
        with dl_col2:
            st.download_button(
                "Download resume (.docx)",
                data=_build_resume_docx(st.session_state.parsed_resume),
                file_name="resume.docx",
                mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            )

        if st.button("Improve my profile"):
            with st.spinner("Analyzing your resume for missing keywords and formatting issues..."):
                try:
                    resp = requests.get(
                        f"{BACKEND_URL}/profiles/{st.session_state.profile_id}/improve", timeout=60
                    )
                    resp.raise_for_status()
                    improvement = resp.json()
                    st.subheader("Overall assessment")
                    st.write(improvement["overall_assessment"])
                    col1, col2 = st.columns(2)
                    with col1:
                        st.markdown("**Missing keywords**")
                        for kw in improvement["missing_keywords"]:
                            st.write(f"- {kw}")
                    with col2:
                        st.markdown("**Formatting issues**")
                        for issue in improvement["formatting_issues"]:
                            st.write(f"- {issue}")
                    st.markdown("**Suggestions**")
                    for suggestion in improvement["suggestions"]:
                        st.write(f"- {suggestion}")
                except requests.RequestException as exc:
                    st.error(f"Failed to improve profile: {exc}")

# ---------------------------------------------------------------------------
# Job Search tab
# ---------------------------------------------------------------------------
with tab_search:
    st.subheader("Search internships & jobs (MNCs + startups)")

    with st.expander("Found a job link yourself? Analyze it directly"):
        job_url = st.text_input("Paste the job posting / apply link", key="external_job_url")
        if st.button("Fetch & analyze this job"):
            if not job_url.strip():
                st.warning("Paste a URL first.")
            else:
                with st.spinner("Fetching the job posting..."):
                    try:
                        resp = requests.post(
                            f"{BACKEND_URL}/jobs/from-url",
                            json={"url": job_url.strip(), "profile_id": st.session_state.profile_id},
                            timeout=30,
                        )
                        resp.raise_for_status()
                        fetched_job = resp.json()
                        st.session_state.jobs = [fetched_job] + [
                            j for j in st.session_state.jobs if j["id"] != fetched_job["id"]
                        ]
                        st.success(f"Added \"{fetched_job['title']}\" — see it below to run gap analysis.")
                    except requests.RequestException as exc:
                        st.error(f"Could not fetch that job: {exc}")

    if st.session_state.parsed_resume and st.session_state.job_query_source_profile != st.session_state.profile_id:
        st.session_state.job_query = _resume_derived_query(st.session_state.parsed_resume)
        st.session_state.job_query_source_profile = st.session_state.profile_id

    if not st.session_state.parsed_resume:
        st.caption(
            "Upload & parse a resume in the Profile tab for a query tailored to you, "
            "or just type the specific role you're targeting below."
        )
    else:
        st.caption("Pre-filled from your resume — edit it to target a specific role instead.")

    col1, col2, col3 = st.columns([2, 2, 1])
    with col1:
        query = st.text_input("Role / keywords", key="job_query")
    with col2:
        location = st.text_input("Location (optional)")
    with col3:
        num_results = st.number_input("Results", min_value=5, max_value=50, value=20, step=5)

    if st.button("Search jobs"):
        if not query.strip():
            st.warning("Enter a role/keywords to search for, or parse a resume first.")
            st.stop()
        with st.spinner("Searching..."):
            try:
                resp = requests.post(
                    f"{BACKEND_URL}/jobs/search",
                    json={
                        "query": query,
                        "location": location or None,
                        "num_results": int(num_results),
                        "profile_id": st.session_state.profile_id,
                    },
                    timeout=60,
                )
                resp.raise_for_status()
                st.session_state.jobs = resp.json()
            except requests.RequestException as exc:
                st.error(f"Search failed: {exc}")

    if st.session_state.jobs and st.session_state.jobs[0].get("match_score") is not None:
        st.caption("Sorted by fit to your resume.")

    for job in st.session_state.jobs:
        match_score = job.get("match_score")
        match_label = f" — Match: {round(match_score * 100)}%" if match_score is not None else ""
        with st.expander(f"{job['title']} — {job['company']} ({job.get('location') or 'N/A'}){match_label}"):
            st.write(job.get("description") or "No description available.")
            st.markdown(f"[Actual apply link]({job['apply_url']})")
            col_a, col_b = st.columns(2)
            with col_a:
                run_gap = st.button("Analyze skill gap", key=f"gap_{job['id']}")
            with col_b:
                if st.button("Save to applications", key=f"save_{job['id']}"):
                    try:
                        resp = requests.post(
                            f"{BACKEND_URL}/applications",
                            json={"user_id": st.session_state.user_id, "job_id": job["id"]},
                            timeout=15,
                        )
                        resp.raise_for_status()
                        st.success("Saved.")
                    except requests.RequestException as exc:
                        st.error(f"Could not save: {exc}")

            if run_gap:
                if not st.session_state.profile_id:
                    st.warning("Upload and parse a resume first (Profile tab).")
                else:
                    with st.spinner("Comparing your resume against this job description..."):
                        try:
                            resp = requests.post(
                                f"{BACKEND_URL}/gap-analysis",
                                json={"profile_id": st.session_state.profile_id, "job_id": job["id"]},
                                timeout=60,
                            )
                            resp.raise_for_status()
                            st.session_state.gap_results[job["id"]] = resp.json()
                        except requests.RequestException as exc:
                            st.error(f"Gap analysis failed: {exc}")

            analysis = st.session_state.gap_results.get(job["id"])
            if analysis:
                st.divider()
                st.metric("Match", f"{analysis['match_percentage']}%")
                col1, col2 = st.columns(2)
                with col1:
                    st.markdown("**Matching skills**")
                    for skill in analysis["matching_skills"]:
                        st.write(f"✅ {skill}")
                with col2:
                    st.markdown("**Missing requirements**")
                    for req in analysis["missing_requirements"]:
                        st.write(f"❌ {req}")

                st.markdown("**Close the gap** — check any you want added to your resume")
                checked_gaps = []
                for i, rec in enumerate(analysis["recommendations"]):
                    gap, action = rec["gap"], rec["action"]
                    check_col, text_col = st.columns([1, 6])
                    with check_col:
                        checked = st.checkbox("Add", key=f"addgap_{job['id']}_{i}")
                    with text_col:
                        st.write(f"**{gap}** — {action}")
                        st.markdown(f"[Bridge this gap →]({_bridge_link(gap)})")
                    if checked:
                        checked_gaps.append(gap)

                if st.button("Add checked skills to my resume", key=f"apply_gaps_{job['id']}"):
                    if not checked_gaps:
                        st.warning("Check at least one gap first.")
                    else:
                        try:
                            resp = requests.post(
                                f"{BACKEND_URL}/profiles/{st.session_state.profile_id}/add-skills",
                                json={"skills": checked_gaps},
                                timeout=15,
                            )
                            resp.raise_for_status()
                            st.session_state.parsed_resume = resp.json()["parsed_resume"]
                            st.success(f"Added {len(checked_gaps)} skill(s) to your resume.")
                        except requests.RequestException as exc:
                            st.error(f"Could not update resume: {exc}")

                if st.session_state.parsed_resume:
                    dl_col1, dl_col2 = st.columns(2)
                    with dl_col1:
                        st.download_button(
                            "Download updated resume (.pdf)",
                            data=_build_resume_pdf(st.session_state.parsed_resume),
                            file_name="resume.pdf",
                            mime="application/pdf",
                            key=f"download_pdf_{job['id']}",
                        )
                    with dl_col2:
                        st.download_button(
                            "Download updated resume (.docx)",
                            data=_build_resume_docx(st.session_state.parsed_resume),
                            file_name="resume.docx",
                            mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                            key=f"download_docx_{job['id']}",
                        )

# ---------------------------------------------------------------------------
# Applications tab
# ---------------------------------------------------------------------------
with tab_apps:
    st.subheader("Your saved applications")
    try:
        resp = requests.get(
            f"{BACKEND_URL}/applications", params={"user_id": st.session_state.user_id}, timeout=15
        )
        resp.raise_for_status()
        applications = resp.json()
    except requests.RequestException as exc:
        st.error(f"Could not load applications: {exc}")
        applications = []

    if not applications:
        st.info("No saved applications yet — save one from the Job Search tab.")

    for application in applications:
        with st.container(border=True):
            st.write(f"Job ID: {application['job_id']}  ·  Status: **{application['status']}**")
            st.warning(
                "The pre-fill assistant opens a real, visible browser window and fills what it can "
                "(name, email, phone, LinkedIn, GitHub, resume upload). It never submits — review and "
                "click Submit yourself."
            )
            with st.form(key=f"prefill_form_{application['id']}"):
                full_name = st.text_input("Full name", key=f"name_{application['id']}")
                email_field = st.text_input("Email", key=f"email_{application['id']}")
                phone = st.text_input("Phone (optional)", key=f"phone_{application['id']}")
                linkedin_url = st.text_input("LinkedIn URL (optional)", key=f"li_{application['id']}")
                github_url = st.text_input("GitHub URL (optional)", key=f"gh_{application['id']}")
                submitted = st.form_submit_button("Launch pre-fill browser")

            if submitted:
                with st.spinner("Launching browser — check your taskbar for the new window..."):
                    try:
                        resp = requests.post(
                            f"{BACKEND_URL}/applications/{application['id']}/prefill",
                            json={
                                "full_name": full_name,
                                "email": email_field,
                                "phone": phone or None,
                                "linkedin_url": linkedin_url or None,
                                "github_url": github_url or None,
                            },
                            timeout=90,
                        )
                        resp.raise_for_status()
                        result = resp.json()
                        st.success(f"Filled fields: {result['filled_fields'] or 'none'}")
                        if result.get("skipped_reason"):
                            st.warning(result["skipped_reason"])
                    except requests.RequestException as exc:
                        st.error(f"Pre-fill failed: {exc}")

# ---------------------------------------------------------------------------
# Chat Assistant tab
# ---------------------------------------------------------------------------
with tab_chat:
    st.subheader("Ask about your resume, gaps, or job search")
    if not st.session_state.parsed_resume:
        st.caption("Upload & parse a resume in the Profile tab so answers can reference it directly.")

    for turn in st.session_state.chat_history:
        with st.chat_message(turn["role"]):
            st.write(turn["content"])

    user_message = st.chat_input("Ask something, e.g. 'What's missing from my resume for a backend role?'")
    if user_message:
        st.session_state.chat_history.append({"role": "user", "content": user_message})
        with st.chat_message("user"):
            st.write(user_message)

        with st.chat_message("assistant"):
            with st.spinner("Thinking..."):
                try:
                    resp = requests.post(
                        f"{BACKEND_URL}/chat",
                        json={
                            "message": user_message,
                            "history": st.session_state.chat_history[:-1],
                            "profile_id": st.session_state.profile_id,
                        },
                        timeout=60,
                    )
                    resp.raise_for_status()
                    reply = resp.json()["reply"]
                    st.write(reply)
                    st.session_state.chat_history.append({"role": "assistant", "content": reply})
                except requests.RequestException as exc:
                    st.error(f"Chat failed: {exc}")
