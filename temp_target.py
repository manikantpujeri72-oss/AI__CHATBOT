def get_admission_contact_response() -> dict[str, Any]:
    """Retrieve verified admission contact details from overview of mce.pdf (Page 48)."""
    lines = [
        "## MCE Admission Contact Details\n",
        "Official admission and institutional contact details for Malnad College of Engineering (MCE), Hassan:\n",
        "- **MTES Office:** `08172-268371`",
        "- **Principal's Office:** `08172-245317`",
        "- **Dean – Student Affairs:** `9449689093`",
        "- **Admission Enquiry / PRO:** `9141305843`",
        "- **Official Email:** [office@mcehassan.ac.in](mailto:office@mcehassan.ac.in)",
        "- **College Address:** No. 21, Salagame Road, Rangoli Halla, Hassan, Karnataka – 573202\n",
        "### Official Admission Portals & Links",
        "- [MCE Admission Process 2026–27](https://www.mcehassan.ac.in)",
        "- [MCE Management Admission Portal](https://www.mcehassan.ac.in)",
        "- [MCE Admission Enquiry](https://www.mcehassan.ac.in)",
        "- [Karnataka Examinations Authority (KEA)](https://cetonline.karnataka.gov.in/kea/)",
        "- [COMEDK Official Website](https://www.comedk.org)\n",
        "*[Source: overview of mce.pdf, Page 48]*"
    ]
    msg = "\n".join(lines)
    return {
        "handled": True,
        "status": "admission_contact",
        "type": "faculty_admission_contact",
        "message": msg,
    }


def get_eligibility_criteria_response() -> dict[str, Any]:
    """Retrieve verified admission eligibility criteria from overview of mce.pdf (Pages 50-51)."""
    lines = [
        "## Eligibility Criteria for Admission to MCE Hassan (2026–27)\n",
        "According to official admission records, eligibility requirements depend on the programme and entry route:\n",
        "### 1. Undergraduate (B.E.) Programmes",
        "- **Educational Qualification:** Pass 2nd PUC, Class 12, or an equivalent qualifying examination.",
        "- **Compulsory Subjects:** Physics and Mathematics, along with Chemistry / Bio-Technology / Biology / Computer Science / Electronics.",
        "- **Minimum Marks:** Minimum of **45% aggregate** in compulsory subjects for General Category candidates, and **40% aggregate** for Karnataka SC/ST/OBC category candidates.",
        "- **Admission Routes:** KCET (KEA quota), COMEDK UGET, or Management Quota.\n",
        "### 2. Diploma Lateral Entry (Direct 2nd Year B.E.)",
        "- **Qualification:** 3-year diploma in a relevant engineering discipline recognized by the state board.",
        "- **Minimum Marks:** Minimum **45% marks** for General Merit (40% for eligible reserved categories).",
        "- **Admission Route:** D-CET counselling through KEA.\n",
        "### 3. Postgraduate M.Tech Programmes",
        "- **Qualification:** Relevant B.E./B.Tech degree or equivalent qualification.",
        "- **Minimum Marks:** Prescribed qualifying aggregate/CGPA by VTU/Government.",
        "- **Admission Route:** Valid Karnataka PGCET or GATE score followed by counselling.\n",
        "### 4. Master of Computer Applications (MCA)",
        "- **Qualification:** Recognized Bachelor's degree with Mathematics at 10+2 level or degree level.",
        "- **Minimum Marks:** Prescribed qualifying aggregate (50% for GM, 45% for reserved categories).",
        "- **Admission Route:** Valid PGCET score or MCE MCA selection test.\n",
        "### 5. Management Quota Admissions",
        "- Candidates must satisfy academic eligibility requirements. Applications are processed directly through the **MTES Office** in Hassan.\n",
        "*[Source: overview of mce.pdf, Pages 50–51]*"
    ]
    msg = "\n".join(lines)
    return {
        "handled": True,
        "status": "eligibility",
        "type": "faculty_eligibility",
        "message": msg,
    }


def get_fee_structure_response() -> dict[str, Any]:
    """Retrieve official 2026-27 fee structure from overview of mce.pdf."""
    lines = [
        "## Malnad College of Engineering (MCE) — Fee Structure (2026–27)\n",
        "According to the official 2026–27 management quota fee notice and admission documents published by Malnad College of Engineering (MCE), Hassan:\n",
        "### 1. Management Quota Annual Tuition Fees (First-Year B.E. & MCA)",
        "| No. | Course / Branch | Listed Annual Fee (₹) |",
        "| :--- | :--- | :--- |",
        "| 1 | Civil Engineering | ₹1,25,000 |",
        "| 2 | Mechanical Engineering | ₹1,25,000 |",
        "| 3 | Electrical & Electronics Engineering (EEE) | ₹1,25,000 |",
        "| 4 | Electronics & Instrumentation Engineering (EIE) | ₹1,25,000 |",
        "| 5 | Electronics & Communication Engineering (ECE) | ₹2,25,000 |",
        "| 6 | Computer Science & Engineering (CSE) | ₹2,50,000 |",
        "| 7 | Information Science & Engineering (ISE) | ₹2,50,000 |",
        "| 8 | Artificial Intelligence & Machine Learning (AIML) | ₹2,50,000 |",
        "| 9 | Computer Science & Business Systems (CSBS) | ₹2,25,000 |",
        "| 10 | Master of Computer Applications (MCA) | ₹1,25,000 |\n",
        "### 2. Government & Entrance Quota Fees (KCET & COMEDK)",
        "- **KCET / KEA Quota:** Prescribed by the Government of Karnataka / KEA at the time of counselling (Aided: ₹44,200, Unaided: ₹1,12,410 first-year).",
        "- **COMEDK Quota:** Prescribed by the COMEDK authority under the private engineering college consortium notification.\n",
        "### 3. Scholarships & Fee Concessions",
        "- **State Scholarship Portal (SSP):** Post-matric scholarships for SC/ST/OBC/Minority students.",
        "- **National Scholarship Portal (NSP):** Central government merit-cum-means scholarships.",
        "- **Alumni & Merit Scholarships:** Offered through MTES for deserving students.\n",
        "### 4. Admission Office & MTES Contact",
        "- **MTES Office:** `08172-268371`",
        "- **Principal's Office:** `08172-245317`",
        "- **Dean – Student Affairs:** `9449689093`",
        "- **Admission Enquiry / PRO:** `9141305843` | **Email:** [office@mcehassan.ac.in](mailto:office@mcehassan.ac.in)\n",
        "*[Source: overview of mce.pdf, Pages 48, 52]*"
    ]
    msg = "\n".join(lines)
    return {
        "handled": True,
        "status": "fee_structure",
        "type": "faculty_fee_structure",
        "message": msg,
    }


