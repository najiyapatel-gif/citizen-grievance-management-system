from functools import wraps

from flask import (
    Flask, render_template, request,
    redirect, url_for, flash, session
)
from werkzeug.security import generate_password_hash, check_password_hash

from db import get_connection

app = Flask(__name__)
app.secret_key = "change-this-development-key"


def login_required(role):
    def decorator(view_function):
        @wraps(view_function)
        def wrapper(*args, **kwargs):
            if role == "citizen" and "citizen_id" not in session:
                flash("Please log in as a citizen.")
                return redirect(url_for("citizen_login"))

            if role == "admin" and "admin_id" not in session:
                flash("Please log in as an administrator.")
                return redirect(url_for("admin_login"))

            return view_function(*args, **kwargs)
        return wrapper
    return decorator


def close_db(cursor, conn):
    if cursor:
        cursor.close()
    if conn and conn.is_connected():
        conn.close()


@app.route("/")
def home():
    if "admin_id" in session:
        return redirect(url_for("admin_dashboard"))

    if "citizen_id" in session:
        return redirect(url_for("citizen_dashboard"))

    return render_template("portal_choice.html")


# ---------------- CITIZEN SIGNUP ----------------

@app.route("/citizen/signup", methods=["GET", "POST"])
def citizen_signup():
    if request.method == "POST":
        name = request.form.get("full_name", "").strip()
        email = request.form.get("email", "").strip().lower()
        phone = request.form.get("phone", "").strip()
        password = request.form.get("password", "")
        confirm_password = request.form.get("confirm_password", "")

        if not name or not email or not password:
            flash("Please fill all required fields.")
            return render_template("citizen_signup.html")

        if len(password) < 8:
            flash("Password must contain at least 8 characters.")
            return render_template("citizen_signup.html")

        if password != confirm_password:
            flash("Passwords do not match.")
            return render_template("citizen_signup.html")

        conn = cursor = None

        try:
            conn = get_connection()
            cursor = conn.cursor(dictionary=True)

            cursor.execute(
                "SELECT citizen_id FROM citizens WHERE email = %s",
                (email,)
            )

            if cursor.fetchone():
                flash("Email already registered. Please log in.")
                return render_template("citizen_signup.html")

            cursor.execute(
                """
                INSERT INTO citizens
                (full_name, email, phone, password_hash)
                VALUES (%s, %s, %s, %s)
                """,
                (
                    name,
                    email,
                    phone,
                    generate_password_hash(password)
                )
            )

            conn.commit()
            flash("Account created successfully. Please log in.")
            return redirect(url_for("citizen_login"))

        except Exception:
            if conn:
                conn.rollback()

            app.logger.exception("Citizen signup failed")
            flash("Signup failed. Check the database setup.")

        finally:
            close_db(cursor, conn)

    return render_template("citizen_signup.html")


# ---------------- CITIZEN LOGIN ----------------

@app.route("/citizen/login", methods=["GET", "POST"])
def citizen_login():
    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")

        conn = cursor = None

        try:
            conn = get_connection()
            cursor = conn.cursor(dictionary=True)

            cursor.execute(
                """
                SELECT citizen_id, full_name, password_hash
                FROM citizens
                WHERE email = %s
                """,
                (email,)
            )

            citizen = cursor.fetchone()

            if (
                citizen
                and citizen["password_hash"]
                and check_password_hash(
                    citizen["password_hash"], password
                )
            ):
                session.clear()
                session["citizen_id"] = citizen["citizen_id"]
                session["citizen_name"] = citizen["full_name"]

                return redirect(url_for("citizen_dashboard"))

            flash("Invalid email or password.")

        except Exception:
            app.logger.exception("Citizen login failed")
            flash("Login failed. Check the database setup.")

        finally:
            close_db(cursor, conn)

    return render_template("citizen_login.html")


@app.route("/citizen/logout", methods=["GET","POST"])
@login_required("citizen")
def citizen_logout():
    session.clear()
    flash("You have been logged out.")
    return redirect(url_for("home"))


# ---------------- CITIZEN DASHBOARD ----------------

@app.route("/citizen/dashboard")
@login_required("citizen")
def citizen_dashboard():
    conn = cursor = None

    try:
        conn = get_connection()
        cursor = conn.cursor(dictionary=True)

        cursor.execute(
            """
            SELECT complaint_id, title, description,
                   status, complaint_date
            FROM complaints
            WHERE citizen_id = %s
            ORDER BY complaint_id DESC
            """,
            (session["citizen_id"],)
        )

        complaints = cursor.fetchall()

        return render_template(
            "citizen_dashboard.html",
            complaints=complaints,
            citizen={"full_name":session.get("citizen_name","citizen")}
        )

    except Exception:
        app.logger.exception("Citizen dashboard failed")
        return "Dashboard failed to load. Check the VS Code terminal.", 500

    finally:
        close_db(cursor, conn)


# ---------------- SUBMIT COMPLAINT ----------------

@app.route("/submit", methods=["POST"])
@login_required("citizen")
def submit_complaint():
    title = request.form.get("title", "").strip()
    description = request.form.get("description", "").strip()
    category = request.form.get("category", "").strip()

    allowed_categories = [
        "Water Supply", "Roads", "Electricity",
        "Sanitation", "Public Safety"
    ]

    if not title or not description or category not in allowed_categories:
        flash("Please complete all complaint fields.")
        return redirect(url_for("citizen_dashboard"))

    conn = cursor = None

    try:
        conn = get_connection()
        cursor = conn.cursor()

        cursor.execute(
            """
            SELECT department_id
            FROM departments
            WHERE department_name = %s
            """,
            (category,)
        )

        department = cursor.fetchone()

        if not department:
            flash("Department not found in the database.")
            return redirect(url_for("citizen_dashboard"))

        cursor.execute(
            """
            INSERT INTO complaints
            (citizen_id, title, description, status, department_id)
            VALUES (%s, %s, %s, 'Pending', %s)
            """,
            (
                session["citizen_id"],
                title,
                description,
                department[0]
            )
        )

        complaint_id = cursor.lastrowid

        cursor.execute(
            """
            INSERT INTO complaint_updates
            (complaint_id, status, remarks)
            VALUES (%s, 'Pending', %s)
            """,
            (complaint_id, "Complaint submitted by citizen")
        )

        conn.commit()

        flash(
            f"Complaint submitted successfully. "
            f"Your Complaint ID is #{complaint_id}."
        )

    except Exception:
        if conn:
            conn.rollback()

        app.logger.exception("Complaint submission failed")
        flash("Complaint submission failed. Check the terminal.")

    finally:
        close_db(cursor, conn)

    return redirect(url_for("citizen_dashboard"))


# ---------------- ADMIN LOGIN ----------------

@app.route("/admin/login", methods=["GET", "POST"])
def admin_login():
    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")

        conn = cursor = None

        try:
            conn = get_connection()
            cursor = conn.cursor(dictionary=True)

            cursor.execute(
                """
                SELECT admin_id, full_name, password_hash
                FROM admins
                WHERE email = %s
                """,
                (email,)
            )

            admin = cursor.fetchone()

            if admin and check_password_hash(
                admin["password_hash"], password
            ):
                session.clear()
                session["admin_id"] = admin["admin_id"]
                session["admin_name"] = admin["full_name"]

                return redirect(url_for("admin_dashboard"))

            flash("Invalid admin email or password.")

        except Exception:
            app.logger.exception("Admin login failed")
            flash("Admin login failed. Check the terminal.")

        finally:
            close_db(cursor, conn)

    return render_template("admin_login.html")


@app.route("/admin/logout", methods=["POST"])
@login_required("admin")
def admin_logout():
    session.clear()
    flash("Admin logged out successfully.")
    return redirect(url_for("home"))


# ---------------- ADMIN DASHBOARD ----------------

@app.route("/admin")
@login_required("admin")
def admin_dashboard():
    conn = cursor = None

    try:
        conn = get_connection()
        cursor = conn.cursor(dictionary=True)

        cursor.execute(
            """
            SELECT
                COUNT(*) AS total,
                COALESCE(SUM(status = 'Pending'), 0) AS pending,
                COALESCE(SUM(status = 'In Progress'), 0) AS in_progress,
                COALESCE(SUM(status = 'Resolved'), 0) AS resolved
            FROM complaints
            """
        )

        stats = cursor.fetchone()

        cursor.execute(
            """
            SELECT
                c.complaint_id,
                c.title,
                c.description,
                c.status,
                c.complaint_date,
                ci.full_name,
                ci.email,
                ci.phone,
                d.department_name
            FROM complaints c
            JOIN citizens ci
                ON c.citizen_id = ci.citizen_id
            LEFT JOIN departments d
                ON c.department_id = d.department_id
            ORDER BY c.complaint_id DESC
            """
        )

        complaints = cursor.fetchall()

        return render_template(
            "admin_dashboard.html",
            stats=stats,
            complaints=complaints
        )

    except Exception:
        app.logger.exception("Admin dashboard failed")
        return "Admin dashboard failed. Check the VS Code terminal.", 500

    finally:
        close_db(cursor, conn)


# ---------------- UPDATE COMPLAINT STATUS ----------------

@app.route(
    "/admin/update-status/<int:complaint_id>",
    methods=["POST"]
)
@login_required("admin")
def update_complaint_status(complaint_id):
    new_status = request.form.get("status", "").strip()

    allowed_statuses = ["Pending", "In Progress", "Resolved"]

    if new_status not in allowed_statuses:
        flash("Invalid complaint status.")
        return redirect(url_for("admin_dashboard"))

    conn = cursor = None

    try:
        conn = get_connection()
        cursor = conn.cursor()

        cursor.execute(
            """
            UPDATE complaints
            SET status = %s
            WHERE complaint_id = %s
            """,
            (new_status, complaint_id)
        )

        if cursor.rowcount == 0:
            conn.rollback()
            flash("Complaint not found or status unchanged.")
            return redirect(url_for("admin_dashboard"))

        cursor.execute(
            """
            INSERT INTO complaint_updates
            (complaint_id, status, remarks)
            VALUES (%s, %s, %s)
            """,
            (
                complaint_id,
                new_status,
                "Status updated by admin"
            )
        )

        conn.commit()
        flash(f"Complaint #{complaint_id} status updated to {new_status}.")

    except Exception:
        if conn:
            conn.rollback()

        app.logger.exception("Status update failed")
        flash("Status update failed. Check the VS Code terminal.")

    finally:
        close_db(cursor, conn)

    return redirect(url_for("admin_dashboard"))


if __name__ == "__main__":
    app.run(debug=True)