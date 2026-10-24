from flask import(
    Flask, render_template, request,  redirect,
    url_for, flash,session
)

from functools import wraps
from werkzeug.security import check_password_hash
from db import get_connection


def create_admin():
    full_name = input("Enter admin full name: ").strip()
    email = input("Enter admin email: ").strip().lower()
    password = getpass("Create admin password: ")
    confirm_password = getpass("Confirm admin password: ")

    if not full_name or not email or not password:
        print("All fields are required.")
        return

    if password != confirm_password:
        print("Passwords do not match.")
        return

    if len(password) < 8:
        print("Password must be at least 8 characters.")
        return

    conn = None
    cursor = None

    try:
        conn = get_connection()
        cursor = conn.cursor()

        cursor.execute(
            "SELECT admin_id FROM admins WHERE email = %s",
            (email,)
        )

        if cursor.fetchone():
            print("An admin with this email already exists.")
            return

        password_hash = generate_password_hash(password)

        cursor.execute(
            """
            INSERT INTO admins (full_name, email, password_hash)
            VALUES (%s, %s, %s)
            """,
            (full_name, email, password_hash)
        )

        conn.commit()
        print("Admin account created successfully!")

    except Exception:
        if conn:
            conn.rollback()
        print("Admin creation failed. Check the terminal error.")
        raise

    finally:
        if cursor:
            cursor.close()
        if conn and conn.is_connected():
            conn.close()


if __name__ == "__main__":
    create_admin()