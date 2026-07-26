from db import get_connection


def calculate_health_score(user_row, latest_report=None):
    """Return a deterministic MVP wellness score, not a diagnostic score."""
    (
        name,
        age,
        gender,
        weight,
        height,
        bmi,
        diabetes_status,
        hypertension,
        previous_liver_disease,
        family_history,
        activity_level,
        exercise_frequency,
        alcohol_consumption,
        smoking_status
    ) = user_row

    profile_penalty = 0
    if diabetes_status:
        profile_penalty += 6

    if hypertension:
        profile_penalty += 4

    if previous_liver_disease:
        profile_penalty += 10

    if family_history:
        profile_penalty += 4

    if smoking_status == "current":
        profile_penalty += 8
    elif smoking_status == "former":
        profile_penalty += 3

    if alcohol_consumption == "heavy":
        profile_penalty += 10
    elif alcohol_consumption == "moderate":
        profile_penalty += 5
    elif alcohol_consumption == "occasional":
        profile_penalty += 2

    if bmi is not None:
        if bmi >= 30:
            profile_penalty += 8
        elif bmi >= 25:
            profile_penalty += 4

    if activity_level == "sedentary":
        profile_penalty += 4
    elif activity_level == "lightly active":
        profile_penalty += 2

    if exercise_frequency == "never":
        profile_penalty += 4
    elif exercise_frequency == "1-2 times per week":
        profile_penalty += 2

    report_penalty = 0
    if latest_report:
        (
            ast,
            alt,
            bilirubin,
            albumin,
            platelets,
            inr,
            pt,
            afp,
            hbsag,
            anti_hcv,
            apri,
            fib4,
            ultrasound_prediction,
            date_added
        ) = latest_report

        fibrosis_penalties = []
        if fib4 is not None:
            if fib4 >= 2.67:
                fibrosis_penalties.append(18)
            elif fib4 >= 1.3:
                fibrosis_penalties.append(8)
            else:
                fibrosis_penalties.append(0)

        if apri is not None:
            if apri > 1.5:
                fibrosis_penalties.append(15)
            elif apri > 0.5:
                fibrosis_penalties.append(7)
            else:
                fibrosis_penalties.append(0)

        if fibrosis_penalties:
            # FIB-4 and APRI share AST and platelet inputs. Use the higher
            # penalty instead of counting the same abnormality multiple times.
            report_penalty += max(fibrosis_penalties)
        else:
            enzyme_ratio = max(
                (ast or 0) / 40,
                (alt or 0) / 40,
            )
            if enzyme_ratio > 3:
                report_penalty += 12
            elif enzyme_ratio > 2:
                report_penalty += 8
            elif enzyme_ratio > 1:
                report_penalty += 4

            if platelets is not None:
                if platelets < 100:
                    report_penalty += 8
                elif platelets < 150:
                    report_penalty += 4

        if bilirubin is not None:
            if bilirubin > 3:
                report_penalty += 10
            elif bilirubin > 1.2:
                report_penalty += 6

        if albumin is not None:
            if albumin < 3:
                report_penalty += 10
            elif albumin < 3.5:
                report_penalty += 6

        if inr is not None:
            if inr > 1.5:
                report_penalty += 10
            elif inr > 1.2:
                report_penalty += 5
        elif pt is not None:
            if pt > 15:
                report_penalty += 8
            elif pt > 13.5:
                report_penalty += 4

        if afp is not None:
            if afp >= 400:
                report_penalty += 12
            elif afp >= 20:
                report_penalty += 6

        if hbsag or anti_hcv:
            report_penalty += 10

        if ultrasound_prediction:
            prediction = str(ultrasound_prediction).lower()

            if "hcc" in prediction:
                report_penalty += 25
            elif "hemangioma" in prediction:
                report_penalty += 2
            elif prediction != "normal":
                report_penalty += 12

    # Caps keep profile-only risk from overwhelming measured results and
    # prevent a collection of correlated abnormal values from driving the
    # score below zero.
    score = 100 - min(profile_penalty, 35) - min(report_penalty, 65)
    score = max(0, min(100, round(score)))

    return score

def build_llm_prompt(user_id):
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT
                    name,
                    age,
                    gender,
                    weight,
                    height,
                    bmi,
                    diabetes_status,
                    hypertension,
                    previous_liver_disease,
                    family_history,
                    activity_level,
                    exercise_frequency,
                    alcohol_consumption,
                    smoking_status
                FROM users
                WHERE id=%s
                """,
                (user_id,)
            )
            user_row = cur.fetchone()

            cur.execute(
                """SELECT ast, alt, bilirubin, albumin, platelets, inr, pt,
                    afp, hbsag, anti_hcv, apri, fib4, ultrasound_prediction, date_added
                FROM reports WHERE user_id=%s ORDER BY date_added ASC, id ASC""",
                (user_id,)
            )
            report_rows = cur.fetchall()
    finally:
        conn.close()

    if user_row is None:
        return None

    (
        name,
        user_age,
        gender,
        weight,
        height,
        bmi,
        diabetes_status,
        hypertension,
        previous_liver_disease,
        family_history,
        activity_level,
        exercise_frequency,
        alcohol_consumption,
        smoking_status
    ) = user_row

    latest_report = report_rows[-1] if report_rows else None

    health_score = calculate_health_score(
        user_row,
        latest_report
    )

    def fmt(v):
        return v if v is not None else "N/A"

    prompt = (
        f"Patient Profile:\n"
        f"Name: {name}\n"
        f"Age: {fmt(user_age)}\n"
        f"Gender: {fmt(gender)}\n"
        f"Weight: {fmt(weight)} kg\n"
        f"Height: {fmt(height)} cm\n"
        f"BMI: {fmt(bmi)}\n"
        f"Diabetes: {fmt(diabetes_status)}\n"
        f"Hypertension: {fmt(hypertension)}\n"
        f"Previous Liver Disease: {fmt(previous_liver_disease)}\n"
        f"Family History: {fmt(family_history)}\n"
        f"Activity Level: {fmt(activity_level)}\n"
        f"Exercise Frequency: {fmt(exercise_frequency)}\n"
        f"Alcohol Consumption: {fmt(alcohol_consumption)}\n"
        f"Smoking Status: {fmt(smoking_status)}\n\n"
        f"Precalculated Health Score: {health_score}\n\n"
        f"Liver Panel History (chronological order):\n"
    )

    if not report_rows: 
        prompt += (
            "BIOMARKER_DATA_AVAILABLE: NO\n"
            "No previous reports on record.\n"
        )
    else:
        prompt += "BIOMARKER_DATA_AVAILABLE: YES\n\n"

        for row in report_rows:
            (ast, alt, bilirubin, albumin, platelets, inr, pt,
            afp, hbsag, anti_hcv, apri, fib4, ultrasound_prediction, date_added) = row

            line = (
                f"- {date_added} | AST: {fmt(ast)} U/L, ALT: {fmt(alt)} U/L, "
                f"Bilirubin: {fmt(bilirubin)} mg/dL, Albumin: {fmt(albumin)} g/dL, "
                f"Platelets: {fmt(platelets)}, INR: {fmt(inr)}, PT: {fmt(pt)}, "
                f"AFP: {fmt(afp)}, HBsAg: {fmt(hbsag)}, Anti-HCV: {fmt(anti_hcv)}, "
                f"APRI: {apri if apri is not None else 'insufficient data'}, "
                f"FIB-4: {fib4 if fib4 is not None else 'insufficient data'}, "
                f"Liver Imaging Result: {fmt(ultrasound_prediction)}"
            )

            prompt += line + "\n"

    return prompt


def build_full_llm_request(user_id):
    base_prompt = build_llm_prompt(user_id)
    if base_prompt is None:
        return None

    instructions = """
You are a liver health assessment engine.

IMPORTANT:
The response must be deterministic and consistent.
Given the same input data, always produce approximately the same health score.
Do not randomly adjust scores between requests.

A precalculated health score is provided in the patient profile.

You MUST use that exact score as the value of
"overall_health_score".

Do not recalculate it.
Do not modify it.
Do not increase or decrease it.

ASSESSMENT RULES

STEP 1: Determine whether biomarker data is available.

If the patient has NO laboratory report data:
- Use ONLY onboarding/profile information.
- Do NOT assume any laboratory values.
- Do NOT invent biomarker results.
- Generate a PRELIMINARY BASELINE HEALTH SCORE.

Use the following risk factors:
- Age
- BMI
- Diabetes status
- Hypertension
- Previous liver disease
- Family history
- Activity level
- Exercise frequency
- Alcohol consumption
- Smoking status

When no biomarker data exists:
- AST status must be ""
- ALT status must be ""
- Bilirubin status must be ""
- Albumin status must be ""
- AST value must be "N/A"
- ALT value must be "N/A"
- Bilirubin value must be "N/A"
- Albumin value must be "N/A"

Set:
"apri_fib4_interpretation": "Upload a liver report to calculate APRI and FIB-4 scores."

The AI insights should:
1. Explain the onboarding-based score.
2. Summarize major risk factors.
3. Recommend uploading reports for a more accurate assessment.


STEP 2: If laboratory report data IS available:

Use BOTH:
- Onboarding/profile information
AND
- Biomarker information

Consider:
- AST
- ALT
- Bilirubin
- Albumin
- INR
- PT
- Platelets
- AFP
- HBsAg
- Anti-HCV
- APRI
- FIB-4
- Ultrasound findings

Use the MOST RECENT report values when populating biomarker flags.

Interpretation Rules:
- Higher AST, ALT, Bilirubin, INR and PT decrease the score.
- Lower Albumin decreases the score.
- Higher APRI and FIB-4 decrease the score.
- Abnormal ultrasound findings decrease the score.
- Diabetes, hypertension, smoking, obesity and heavy alcohol use decrease the score.

If multiple reports exist:
- Compare latest report against previous reports.
- Mention whether liver health appears improving, worsening or stable.

IMPORTANT:
For identical patient data, keep the score consistent.
Do not make large score changes unless biomarker values justify them.

Respond with ONLY a raw JSON object.

{
  "overall_health_score": <integer 0-100>,
  "flags": {
    "ast": {
      "status": "<Normal/High/Low or empty string>",
      "value": "<latest value or N/A>"
    },
    "alt": {
      "status": "<Normal/High/Low or empty string>",
      "value": "<latest value or N/A>"
    },
    "bilirubin": {
      "status": "<Normal/High/Low or empty string>",
      "value": "<latest value or N/A>"
    },
    "albumin": {
      "status": "<Normal/High/Low or empty string>",
      "value": "<latest value or N/A>"
    }
  },
  "apri_fib4_interpretation": "<one sentence>",
  "ai_insights": [
    "<insight 1>",
    "<insight 2>",
    "<insight 3>"
  ]
}
"""
    return base_prompt + instructions
