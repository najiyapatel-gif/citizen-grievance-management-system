from functools import wraps

from flask import (
    Flask,
    render_template,
    request,
    redirect,
    url_for,
    flash,
    session
)
from werkzeug.security import check_password_hash
from db import get_connection


app = Flask(__name__)

# Development only. Use an environment variable for deployment.
app.secret_key = "change-this-development-key"


# ---------------- ADMIN ACCESS PROTECTION ----------------

def admin_required(view_function):
    @wraps(view_function)
    def wrapped_view(*args, **kwargs):
        if "admin_id" not in session:
            flash("Please log in to access the admin dashboard.")
            return redirect(url_for("admin_login"))

        return view_function(*args, **kwargs)

    return wrapped_view


# ---------------- CITIZEN HOME PAGE ----------------

@app.route("/")
def home():
    return render_template("complaint.html")


# ---------------- ADMIN LOGIN ----------------

@app.route("/admin/login", methods=["GET", "POST"])
def admin_login():
    if "admin_id" in session:
        return redirect(url_for("admin_dashboard"))

    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")

        conn = None
        cursor = None

        try:
            conn = get_connection()
            cursor = conn.cursor(dictionary=True)

            cursor.execute(
                """
                SELECT admin_id, full_name, email, password_hash
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

            flash("Invalid email or password.")

        except Exception:
            app.logger.exception("Admin login failed")
            flash("Login failed. Please check the server terminal.")

        finally:
            if cursor:
                cursor.close()

            if conn and conn.is_connected():
                conn.close()

    return render_template("admin_login.html")


# ---------------- ADMIN LOGOUT ----------------

@app.route("/admin/logout", methods=["POST"])
def admin_logout():
    if "admin_id" not in session:
        return redirect(url_for("admin_login"))

    session.clear()
    flash("You have been logged out.")

    return redirect(url_for("admin_login"))


# ---------------- ADMIN DASHBOARD ----------------

@app.route("/admin")
@admin_required
def admin_dashboard():
    conn = None
    cursor = None

    try:
        conn = get_connection()
        cursor = conn.cursor(dictionary=True)

        # Complaint statistics
        cursor.execute(
            """
            SELECT
                COUNT(*) AS total,
                COALESCE(
                    SUM(CASE WHEN status = 'Pending'
                        THEN 1 ELSE 0 END), 0
                ) AS pending,
                COALESCE(
                    SUM(CASE WHEN status = 'Resolved'
                        THEN 1 ELSE 0 END), 0
                ) AS resolved
            FROM complaints
            """
        )

        stats = cursor.fetchone()

        # Complaint records with citizen and department details
        cursor.execute(
            """
            SELECT
                c.complaint_id,
                c.title,
                c.status,
                c.complaint_date,
                ci.full_name,
                ci.email,
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
            "admin.html",
            stats=stats,
            complaints=complaints
        )

    except Exception:
        app.logger.exception("Admin dashboard failed")
        return (
            "Dashboard load nahi hua. VS Code terminal mein "
            "error check karo.",
            500
        )

    finally:
        if cursor:
            cursor.close()

        if conn and conn.is_connected():
            conn.close()


# ---------------- SUBMIT CITIZEN COMPLAINT ----------------

@app.route("/submit", methods=["POST"])
def submit_complaint():
    name = request.form.get("full_name", "").strip()
    email = request.form.get("email", "").strip().lower()
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

        # Save or update citizen details
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

        # Find department
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
            conn.rollback()
            flash(
                "Selected department was not found in the database."
            )
            return redirect(url_for("home"))

        department_id = department[0]

        # Create complaint
        cursor.execute(
            """
            INSERT INTO complaints
                (citizen_id, title, description, department_id)
            VALUES (%s, %s, %s, %s)
            """,
            (citizen_id, title, description, department_id)
        )

        complaint_id = cursor.lastrowid

        # Save initial status
        cursor.execute(
            """
            INSERT INTO complaint_updates
                (complaint_id, status, remarks)
            VALUES (%s, %s, %s)
            """,
            (
                complaint_id,
                "Pending",
                "Complaint submitted successfully"
            )
        )

        conn.commit()

        flash(
            f"Complaint submitted successfully! "
            f"Complaint ID: {complaint_id}"
        )

    except Exception:
        if conn:
            conn.rollback()

        app.logger.exception("Complaint submission failed")
        flash(
            "Could not submit complaint. "
            "Please check the database tables and terminal."
        )

    finally:
        if cursor:
            cursor.close()

        if conn and conn.is_connected():
            conn.close()

    return redirect(url_for("home"))


# ---------------- RUN APPLICATION ----------------

if __name__ == "__main__":
    app.run(debug=True)