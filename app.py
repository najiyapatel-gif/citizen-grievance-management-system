from flask import Flask, render_template, request, redirect, url_for, flash
from db import get_connection

app = Flask(__name__)
app.secret_key = "change-this-development-key"


@app.route("/")
def home():
    return render_template("complaint.html")


@app.route("/submit", methods=["POST"])
def submit_complaint():
    name = request.form.get("full_name", "").strip()
    email = request.form.get("email", "").strip()
    phone = request.form.get("phone", "").strip()
    category = request.form.get("category", "").strip()
    title = request.form.get("title", "").strip()
    description = request.form.get("description", "").strip()

    if not name or not email or not category or not title:
        flash("Please fill all required fields.")
        return redirect(url_for("home"))

    conn = None
    cursor = None

    try:
        conn = get_connection()
        cursor = conn.cursor()

        # 1. Save citizen information
        cursor.execute(
            """
            INSERT INTO citizens (full_name, email, phone)
            VALUES (%s, %s, %s)
            ON DUPLICATE KEY UPDATE
                full_name = VALUES(full_name),
                phone = VALUES(phone)
            """,
            (name, email, phone)
        )

        cursor.execute(
            "SELECT citizen_id FROM citizens WHERE email = %s",
            (email,)
        )
        citizen = cursor.fetchone()

        if not citizen:
            raise Exception("Citizen record could not be found.")

        citizen_id = citizen[0]

        # 2. Find the selected department
        cursor.execute(
            "SELECT department_id FROM departments WHERE department_name = %s",
            (category,)
        )
        department = cursor.fetchone()

        if not department:
            conn.rollback()
            flash("Selected department was not found in the database.")
            return redirect(url_for("home"))

        department_id = department[0]

        # 3. Create the complaint
        cursor.execute(
            """
            INSERT INTO complaints
                (citizen_id, title, description, department_id)
            VALUES (%s, %s, %s, %s)
            """,
            (citizen_id, title, description, department_id)
        )

        complaint_id = cursor.lastrowid

        # 4. Record the initial complaint status
        cursor.execute(
            """
            INSERT INTO complaint_updates
                (complaint_id, status, remarks)
            VALUES (%s, %s, %s)
            """,
            (complaint_id, "Pending", "Complaint submitted successfully")
        )

        conn.commit()
        flash(f"Complaint submitted successfully! Complaint ID: {complaint_id}")

    except Exception:
        if conn:
            conn.rollback()

        app.logger.exception("Complaint submission failed")
        flash("Could not submit complaint. Please check your database tables.")

    finally:
        if cursor:
            cursor.close()

        if conn and conn.is_connected():
            conn.close()

    return redirect(url_for("home"))


if __name__ == "__main__":
    app.run(debug=True)