"""CareerOS AI Application Strategy Generator & Tailoring Suite.

Grounded in Arsema Doji Wordofa's verified background:
- 3+ years PM experience across B2B SaaS, ERP, CRM, eCommerce, Healthcare EHR.
- Software Engineering degree from Addis Ababa University of Technology.
- Real projects: Bravura EHR, Composity ERP, Ethiojobs Scrum/QA, Halwot Ops, PM/QA Copilot.
- Generates:
  1. Strategic positioning (Lead with, Strongest evidence, Secondary evidence, Gaps, Resume tweaks, Angle).
  2. 1-click tailored Cover Letter drafting.
  3. Pre-filled high-signal answers for application questions.
"""
from __future__ import annotations

import json
import os
import re
from typing import Any, Dict, List, Optional

PROFILE_PATH = os.path.join("config", "candidate_profile.json")


def load_candidate_profile() -> dict:
    try:
        with open(PROFILE_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def generate_application_strategy(
    title: str,
    company: str,
    description: str,
    candidate_profile: Optional[dict] = None,
) -> Dict[str, Any]:
    """Generates application strategy using Gemini/Claude or intelligent heuristic fallback."""
    profile = candidate_profile or load_candidate_profile()
    desc_lower = description.lower()
    title_lower = title.lower()

    # Domain & keyword detection from Job Description
    is_technical = any(k in desc_lower or k in title_lower for k in [
        "technical", "tpm", "api", "engineering", "developer", "sql", "architecture", "system"
    ])
    is_ai = any(k in desc_lower or k in title_lower for k in [
        "ai", "llm", "machine learning", "ml", "genai", "prompt", "evaluation", "nlp"
    ])
    is_healthcare = any(k in desc_lower for k in ["health", "ehr", "medical", "clinic", "patient", "hipaa"])
    is_b2b_saas = any(k in desc_lower for k in ["b2b", "saas", "enterprise", "crm", "erp", "subscription", "arr"])
    is_qa_delivery = any(k in desc_lower or k in title_lower for k in [
        "qa", "quality", "test", "scrum", "agile", "delivery", "sprint", "blocker"
    ])

    # Try Gemini first if key available
    gemini_key = os.environ.get("GEMINI_API_KEY")
    if gemini_key:
        try:
            from google import genai
            client = genai.Client(api_key=gemini_key)
            prompt = f"""You are an elite career strategist for Arsema Doji Wordofa, a Product Manager with 3+ years experience and a Software Engineering degree from Addis Ababa University.
Target Role: {title} at {company}

CANDIDATE BACKGROUND:
- Software Engineering Degree (AAU): Technical fluency, API testing (Postman, Swagger), reads React/Laravel/PHP/MySQL, SQL.
- Bravura Healthcare EHR (Remote PM): Took concept with no PRD/Jira into 7-phase dependency-sequenced roadmap, closed gap between business & engineering.
- Composity ERP & eCommerce Platform (Remote PM): Owned 5 modules (ERP, CRM, eCommerce, invoicing, inventory), shipped 5 AI features (predictive lead scoring, smart POs, OCR), drove feature adoption 40% -> 80%+.
- Ethiojobs ATS (Scrum Master / QA): Coordinated team of 8, cut blocker resolution time from 3 days to <1 day, led QA to 40% defect reduction.
- Built AI Job Matcher, PM/QA Copilot, and Halwot Community Management Platform.

JOB DESCRIPTION:
{description[:3500]}

Return pure JSON matching this exact schema:
{{
  "lead_with": "Short punchy angle (e.g. Technical PM + Software Engineering foundation + Delivery Ownership)",
  "strongest_evidence": "Specific project proof point from candidate's real work that best answers the job requirements",
  "secondary_evidence": "Secondary proof point backing it up",
  "potential_gaps": [
    {{"gap": "Specific requirement candidate may lack direct years in", "mitigation": "How to address and reframe it"}}
  ],
  "resume_changes": [
    "Specific bullet tweak 1",
    "Specific bullet tweak 2"
  ],
  "cover_letter_angle": "The narrative thread for the cover letter",
  "recommended_portfolio_projects": ["List of 2-3 specific portfolio items"],
  "draft_cover_letter": "A high-impact, authentic 3-paragraph tailored cover letter written in first person (no generic fluff)",
  "sample_qa_answers": [
    {{"question": "Why are you interested in this role?", "answer": "Authentic tailored response"}},
    {{"question": "Tell us about your experience with SaaS / complex workflows.", "answer": "Authentic tailored response"}},
    {{"question": "What is your salary expectation?", "answer": "Salary is negotiable depending on the overall compensation package and remote setup."}}
  ]
}}"""
            model_name = os.environ.get("GEMINI_MODEL", "gemini-2.5-flash")
            resp = client.models.generate_content(model=model_name, contents=prompt)
            raw = resp.text.strip()
            # Clean markdown code blocks if present
            raw = re.sub(r"^```(?:json)?\s*", "", raw)
            raw = re.sub(r"\s*```$", "", raw)
            return json.loads(raw)
        except Exception:
            pass  # Fall through to deterministic heuristic generator

    # Deterministic Heuristic Generator (grounded in Arsema's verified profile)
    lead_with = "Technical PM with Software Engineering Foundation + End-to-End Delivery Ownership"
    if is_ai:
        lead_with = "AI-Fluent Product Manager: Real Experience Shipping AI Features & Evaluation into Production"
    elif is_healthcare:
        lead_with = "Healthcare & Complex B2B SaaS Product Manager: Proven EHR Roadmap & Jira Execution"
    elif is_technical:
        lead_with = "Technical PM with Software Engineering Degree: Closing the Gap Between Business and Engineering"

    strongest_evidence = (
        "Bravura Healthcare EHR: Took an early orthodontic EHR concept from raw mocks into a 7-phase buildable roadmap, "
        "defining MVP across Practice Settings, Patient Overview, and Scheduling while authoring buildable Jira stories."
    )
    if is_ai:
        strongest_evidence = (
            "Composity ERP: Led 5 production AI-powered features from brief through QA and release (predictive lead scoring, "
            "AI product search, smart purchase-order generation, OCR processing, and campaign automation)."
        )
    elif is_technical:
        strongest_evidence = (
            "Software Engineering Degree (AAU) + Composity: Validated APIs and data models using Postman, Swagger, JSON, and "
            "DevTools alongside developers; prototyped requirements with Claude & Cursor before engineering handoff."
        )

    secondary_evidence = (
        "Composity ERP & eCommerce: Managed 5 product modules across ERP, CRM, and eCommerce, translating client operations "
        "into clear requirements and increasing feature adoption from 40% to 80%+ within 3 months."
    )

    gaps = []
    if "fintech" in desc_lower or "payments" in desc_lower:
        gaps.append({
            "gap": "No dedicated long-term fintech background stated",
            "mitigation": "Highlight ERP invoicing, payments integration (MyPOS for Elimex.bg), and complex accounting approval workflows."
        })
    elif "b2c" in desc_lower and not is_b2b_saas:
        gaps.append({
            "gap": "Profile is predominantly B2B SaaS and ERP",
            "mitigation": "Emphasize responsive eCommerce storefront discovery, cart, checkout flows, and user onboarding adoption (40% to 80%+)."
        })
    else:
        gaps.append({
            "gap": "Direct domain specifics for " + company,
            "mitigation": "Emphasize rapid domain mastery demonstrated when taking Orthodontic EHR from scratch without prior clinical training."
        })

    resume_changes = [
        f"Promote technical specs and API integration testing bullets to the top of Composity experience.",
        f"Highlight Jira story acceptance criteria and dependency mapping in Bravura EHR section.",
    ]

    cover_letter_angle = (
        "Requirements clarity -> developer-ready Jira user stories -> API validation -> release readiness and adoption"
    )

    recommended_projects = ["Bravura Healthcare EHR", "Composity ERP & eCommerce Platform"]
    if is_ai:
        recommended_projects.append("PM/QA Copilot & AI Job Matcher")
    else:
        recommended_projects.append("Halwot Community Operations Platform")

    draft_cover_letter = (
        f"Hi {company} Team,\n\n"
        f"I am applying for the {title} role because my background bridges technical software engineering and "
        f"pragmatic, end-to-end product delivery. Across B2B SaaS, ERP, and healthcare EHR platforms over the past 3+ years, "
        f"my focus has always been resolving ambiguity before it reaches developers and ensuring shipped features achieve measurable adoption.\n\n"
        f"At Bravura, I took an orthodontic EHR concept with no existing PRD or Jira structure and established a 7-phase roadmap, "
        f"defining buildable user stories with explicit acceptance criteria that allowed engineering to execute smoothly. At Composity, "
        f"I managed product delivery across ERP, CRM, and eCommerce, shipping production AI features (predictive lead scoring, smart PO generation, OCR) "
        f"and boosting feature adoption from 40% to 80%+ within three months by overhauling onboarding workflows. Having earned a B.Sc. in "
        f"Software Engineering, I comfortably read code, test API integrations in Postman, and collaborate directly with engineers without translation overhead.\n\n"
        f"I am looking for a remote role where I can take complete ownership of requirements, streamline delivery, and help {company} build "
        f"impactful, reliable products. I would welcome the opportunity to discuss how my experience aligns with your team's goals.\n\n"
        f"Best regards,\nArsema Doji Wordofa\nhttps://arsemadoji.netlify.app | arsemadoji7@gmail.com"
    )

    sample_qa_answers = [
        {
            "question": "Why are you interested in this role?",
            "answer": (
                f"I am drawn to {company}'s mission and the opportunity to own the full product lifecycle for {title}. "
                f"My experience taking complex workflows (like orthodontic EHR and multi-module ERP) from concept to buildable, "
                f"developer-ready execution aligns directly with what you are looking for."
            ),
        },
        {
            "question": "Tell us about your experience with SaaS / complex product delivery.",
            "answer": (
                "Over the past 3+ years, I have owned product delivery across ERP, CRM, eCommerce, and healthcare platforms. "
                "I specialize in breaking complex business processes into clear Jira stories with edge-case acceptance criteria, "
                "validating APIs using Postman and Swagger, and running QA end to end to ensure release readiness."
            ),
        },
        {
            "question": "What is your salary expectation?",
            "answer": "Salary is negotiable depending on the overall compensation structure, remote setup, and role responsibilities.",
        },
    ]

    return {
        "lead_with": lead_with,
        "strongest_evidence": strongest_evidence,
        "secondary_evidence": secondary_evidence,
        "potential_gaps": gaps,
        "resume_changes": resume_changes,
        "cover_letter_angle": cover_letter_angle,
        "recommended_portfolio_projects": recommended_projects,
        "draft_cover_letter": draft_cover_letter,
        "sample_qa_answers": sample_qa_answers,
    }
