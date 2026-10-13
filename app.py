import random
from io import BytesIO

import pandas as pd
import streamlit as st
from reportlab.lib import colors
from reportlab.lib.pagesizes import landscape, letter
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer


# ------------------------------------------------------
# PAGE CONFIGURATION
# ------------------------------------------------------
st.set_page_config(page_title="Smart Timetable Generator", layout="wide")


# ------------------------------------------------------
# LOGIN SYSTEM (DEMO ONLY)
# ------------------------------------------------------
def login_page():
    st.title("Login")
    st.caption("Demo credentials: admin / 1234")

    with st.form("login_form"):
        username = st.text_input("Username")
        password = st.text_input("Password", type="password")
        submitted = st.form_submit_button("Login")

    if submitted:
        if username == "admin" and password == "1234":
            st.session_state["logged_in"] = True
            st.rerun()
        else:
            st.error("Invalid username or password.")


if "logged_in" not in st.session_state:
    st.session_state["logged_in"] = False

if not st.session_state["logged_in"]:
    login_page()
    st.stop()


with st.sidebar:
    st.success("Logged in as Admin")
    if st.button("Logout"):
        st.session_state["logged_in"] = False
        st.rerun()


# ------------------------------------------------------
# TIMETABLE GENERATION
# ------------------------------------------------------
def generate_timetable(days, hours_per_day, subjects, weekly_hours, teachers, availability):
    """Generate one class timetable using backtracking.

    Ensures exact weekly subject-hour counts, respects each subject's
    teacher availability, and avoids assigning one teacher to two subjects
    in the same period of this class.
    """
    if not days:
        raise ValueError("Please select at least one working day.")
    if not subjects:
        raise ValueError("Please enter at least one valid subject.")
    if len(subjects) != len(weekly_hours):
        raise ValueError("Subject names and weekly hours do not match.")
    if len(set(subjects)) != len(subjects):
        raise ValueError("Subject names must be unique.")
    if any(not teachers.get(subject, "").strip() for subject in subjects):
        raise ValueError("Please assign a teacher to every subject.")
    if any(not isinstance(hours, int) or hours < 0 for hours in weekly_hours):
        raise ValueError("Weekly hours must be non-negative whole numbers.")

    total_slots = len(days) * hours_per_day
    total_required = sum(weekly_hours)

    if total_required > total_slots:
        raise ValueError(
            f"Weekly subject hours ({total_required}) exceed available slots "
            f"({total_slots}). Reduce subject hours or add days/hours."
        )

    remaining = dict(zip(subjects, weekly_hours))
    timetable = {day: [None] * hours_per_day for day in days}
    slots = [(day, hour) for day in days for hour in range(hours_per_day)]

    # Track teachers already scheduled during each day/hour in this class.
    teacher_at_slot = {
        (day, hour): set()
        for day, hour in slots
    }

    # Precompute availability sets for faster checks.
    availability_sets = {
        subject: {
            day: set(availability.get(subject, {}).get(day, []))
            for day in days
        }
        for subject in subjects
    }

    # Try the most constrained slots first while retaining slot order for output.
    # A recursive search assigns the next unfilled slot with the fewest candidates.
    def solve(unfilled_slots):
        if not unfilled_slots:
            return all(count == 0 for count in remaining.values())

        best_slot = None
        best_candidates = None

        for day, hour in unfilled_slots:
            slot_name = f"Hour {hour + 1}"
            used_teachers = teacher_at_slot[(day, hour)]
            candidates = [
                subject for subject in subjects
                if remaining[subject] > 0
                and slot_name in availability_sets[subject][day]
                and teachers[subject] not in used_teachers
            ]

            # Prefer subjects with fewer remaining possible placements.
            random.shuffle(candidates)
            if best_candidates is None or len(candidates) < len(best_candidates):
                best_slot = (day, hour)
                best_candidates = candidates

            if not best_candidates:
                break

        if best_slot is None:
            return True

        day, hour = best_slot
        slot_name = f"Hour {hour + 1}"
        remaining_slots = [slot for slot in unfilled_slots if slot != best_slot]

        for subject in best_candidates:
            teacher = teachers[subject]
            timetable[day][hour] = subject
            remaining[subject] -= 1
            teacher_at_slot[(day, hour)].add(teacher)

            if solve(remaining_slots):
                return True

            teacher_at_slot[(day, hour)].remove(teacher)
            remaining[subject] += 1
            timetable[day][hour] = None

        # Free period is allowed only if all remaining required hours can fit.
        if sum(remaining.values()) <= len(remaining_slots):
            timetable[day][hour] = "Free Period"
            if solve(remaining_slots):
                return True
            timetable[day][hour] = None

        return False

    if not solve(slots):
        raise ValueError(
            "No valid timetable could be generated with the current subject "
            "hours, teacher assignments, and availability. Try increasing "
            "teacher availability or adjusting weekly hours."
        )

    df = pd.DataFrame.from_dict(timetable, orient="index")
    df.columns = [f"Hour {i + 1}" for i in range(hours_per_day)]
    df.index.name = "Day"

    teacher_df = df.copy()
    for column in teacher_df.columns:
        teacher_df[column] = teacher_df[column].map(
            lambda subject: teachers.get(subject, subject)
        )

    return df, teacher_df


# ------------------------------------------------------
# PDF EXPORT
# ------------------------------------------------------
def create_pdf(df, title="Smart Timetable Report"):
    """Return a timetable PDF as bytes for Streamlit download."""
    buffer = BytesIO()
    pdf = SimpleDocTemplate(
        buffer,
        pagesize=landscape(letter),
        rightMargin=30,
        leftMargin=30,
        topMargin=30,
        bottomMargin=30,
    )

    styles = getSampleStyleSheet()
    elements = [
        Paragraph(f"<b>{title}</b>", styles["Title"]),
        Spacer(1, 14),
    ]

    table_data = [["Day"] + list(df.columns)]
    for day in df.index:
        table_data.append([str(day)] + [str(value) for value in df.loc[day].tolist()])

    table = Table(table_data, repeatRows=1)
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#2E86C1")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("BACKGROUND", (0, 1), (0, -1), colors.HexColor("#D6EAF8")),
        ("ALIGN", (0, 0), (-1, -1), "CENTER"),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("FONTSIZE", (0, 0), (-1, -1), 9),
        ("GRID", (0, 0), (-1, -1), 0.6, colors.black),
        ("ROWBACKGROUNDS", (1, 1), (-1, -1), [colors.whitesmoke, colors.lightgrey]),
        ("LEFTPADDING", (0, 0), (-1, -1), 6),
        ("RIGHTPADDING", (0, 0), (-1, -1), 6),
        ("TOPPADDING", (0, 0), (-1, -1), 7),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
    ]))
    elements.append(table)
    pdf.build(elements)
    buffer.seek(0)
    return buffer.getvalue()


# ------------------------------------------------------
# MAIN APP INTERFACE
# ------------------------------------------------------
st.title("Advanced Smart Timetable Generator")
st.write(
    "Configure classes, subjects, teachers, and availability, then generate "
    "timetables and export them as PDFs."
)

st.header("Timetable Configuration")

classes = st.multiselect(
    "Select Classes",
    ["Class A", "Class B", "Class C"],
    default=["Class A"],
)
hours_per_day = st.number_input("Hours per day", min_value=1, max_value=10, value=6, step=1)
days = st.multiselect(
    "Select Working Days",
    ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday"],
    default=["Monday", "Tuesday", "Wednesday", "Thursday", "Friday"],
)

st.subheader("Enter Subjects and Weekly Hours")
subject_count = st.number_input(
    "How many subjects?",
    min_value=1,
    max_value=20,
    value=5,
    step=1,
)

subjects = []
weekly_hours = []
subject_errors = []

for i in range(int(subject_count)):
    col1, col2 = st.columns([2, 1])
    with col1:
        subject_name = st.text_input(f"Subject {i + 1} name", key=f"subject_{i}").strip()
    with col2:
        weekly_hour_count = st.number_input(
            f"Weekly hours for subject {i + 1}",
            min_value=0,
            max_value=60,
            value=4,
            step=1,
            key=f"weekly_hours_{i}",
        )

    if subject_name:
        subjects.append(subject_name)
        weekly_hours.append(int(weekly_hour_count))

if len(set(subjects)) != len(subjects):
    st.warning("Subject names must be unique. Please remove duplicate names.")

st.subheader("Assign Teachers")
teachers = {}
for subject in subjects:
    teachers[subject] = st.text_input(
        f"Teacher for {subject}",
        key=f"teacher_{subject}",
    ).strip()

st.subheader("Teacher Availability")
st.caption(
    "Select the periods each subject's teacher can teach. By default, all periods "
    "are available. Availability is configured per subject, so use the same teacher "
    "name consistently for subjects taught by that person."
)

teacher_availability = {}
for subject in subjects:
    with st.expander(f"{subject} — {teachers.get(subject) or 'Teacher not assigned'}", expanded=False):
        subject_availability = {}
        for day in days:
            subject_availability[day] = st.multiselect(
                f"Available periods for {subject} on {day}",
                [f"Hour {i + 1}" for i in range(int(hours_per_day))],
                default=[f"Hour {i + 1}" for i in range(int(hours_per_day))],
                key=f"availability_{subject}_{day}",
            )
        teacher_availability[subject] = subject_availability


# ------------------------------------------------------
# GENERATE TIMETABLES
# ------------------------------------------------------
if st.button("Generate Timetables", type="primary"):
    if not classes:
        st.error("Please select at least one class.")
    elif not days:
        st.error("Please select at least one working day.")
    elif not subjects:
        st.error("Please enter at least one subject name.")
    elif len(set(subjects)) != len(subjects):
        st.error("Subject names must be unique.")
    elif any(not teachers.get(subject) for subject in subjects):
        st.error("Please assign a teacher to every subject.")
    elif sum(weekly_hours) > len(days) * int(hours_per_day):
        st.error(
            f"Weekly subject hours ({sum(weekly_hours)}) exceed available slots "
            f"({len(days) * int(hours_per_day)})."
        )
    else:
        try:
            for class_name in classes:
                st.header(f"Timetable for {class_name}")

                subject_df, teacher_df = generate_timetable(
                    days=days,
                    hours_per_day=int(hours_per_day),
                    subjects=subjects,
                    weekly_hours=weekly_hours,
                    teachers=teachers,
                    availability=teacher_availability,
                )

                st.subheader("Subject Timetable")
                st.dataframe(subject_df, use_container_width=True)

                st.subheader("Teacher Timetable")
                st.dataframe(teacher_df, use_container_width=True)

                subject_pdf = create_pdf(subject_df, f"{class_name} — Subject Timetable")
                teacher_pdf = create_pdf(teacher_df, f"{class_name} — Teacher Timetable")

                download_col1, download_col2 = st.columns(2)
                safe_class_name = class_name.replace(" ", "_")

                with download_col1:
                    st.download_button(
                        "Download Subject Timetable PDF",
                        data=subject_pdf,
                        file_name=f"{safe_class_name}_subject_timetable.pdf",
                        mime="application/pdf",
                        key=f"subject_pdf_{safe_class_name}",
                    )

                with download_col2:
                    st.download_button(
                        "Download Teacher Timetable PDF",
                        data=teacher_pdf,
                        file_name=f"{safe_class_name}_teacher_timetable.pdf",
                        mime="application/pdf",
                        key=f"teacher_pdf_{safe_class_name}",
                    )

                # Verify that scheduled subject counts match the requested hours.
                scheduled_counts = (
                    subject_df.stack()
                    .loc[lambda values: values != "Free Period"]
                    .value_counts()
                    .to_dict()
                )
                with st.expander(f"Validate weekly hours for {class_name}"):
                    validation_rows = []
                    for subject, required_hours in zip(subjects, weekly_hours):
                        actual_hours = int(scheduled_counts.get(subject, 0))
                        validation_rows.append({
                            "Subject": subject,
                            "Required hours": required_hours,
                            "Scheduled hours": actual_hours,
                            "Status": "OK" if actual_hours == required_hours else "Mismatch",
                        })
                    st.dataframe(pd.DataFrame(validation_rows), use_container_width=True)

        except ValueError as error:
            st.error(str(error))
        except Exception as error:
            st.error(f"Unexpected error: {error}")
            st.exception(error)
