
import os
import re
from pathlib import Path

import mysql.connector
from dotenv import load_dotenv
from flask import (
    Flask,
    render_template,
    request,
    redirect,
    url_for,
    flash,
    session
)
from werkzeug.security import generate_password_hash, check_password_hash

app = Flask(__name__)

load_dotenv(Path(__file__).resolve().parent / ".env")
app.secret_key = os.getenv("SECRET_KEY", "library-dev-key")


# Connect to MySQL
def get_db_connection():
    return mysql.connector.connect(
        host=os.getenv("DB_HOST", "localhost"),
        user=os.getenv("DB_USER"),
        password=os.getenv("DB_PASSWORD"),
        database=os.getenv("DB_NAME", "library_auth_db")
    )


# Validate email format
def is_valid_email(email):
    pattern = r"^[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}$"
    return re.fullmatch(pattern, email) is not None


# Home page redirects to login
@app.route("/")
def home():
    if "user_id" in session:
        return redirect(url_for("library"))
    return redirect(url_for("login"))


# Login page and login processing
@app.route("/login", methods=["GET", "POST"])
def login():
    if "user_id" in session:
        return redirect(url_for("library"))

    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")

        if not username:
            flash("Please enter your username.", "error")
            return render_template("login.html")

        if not password:
            flash("Please enter your password.", "error")
            return render_template("login.html")

        connection = None
        cursor = None

        try:
            connection = get_db_connection()
            cursor = connection.cursor(dictionary=True)

            cursor.execute(
                """
                SELECT user_id, username, password_hash
                FROM USERS
                WHERE username = %s
                """,
                (username,)
            )

            user = cursor.fetchone()

            if user and check_password_hash(
                user["password_hash"], password
            ):
                session["user_id"] = user["user_id"]
                session["username"] = user["username"]
                flash("Login successful!", "success")
                return redirect(url_for("library"))

            flash("Invalid username or password.", "error")

        except mysql.connector.Error:
            app.logger.exception("Login database error")
            flash(
                "Database connection failed. Please check your settings.",
                "error"
            )

        finally:
            if cursor:
                cursor.close()
            if connection and connection.is_connected():
                connection.close()

    return render_template("login.html")


# Registration page and account creation
@app.route("/register", methods=["GET", "POST"])
def register():
    if "user_id" in session:
        return redirect(url_for("library"))

    if request.method == "POST":
        username = request.form.get("username", "").strip()
        email = request.form.get("email", "").strip()
        password = request.form.get("password", "")

        if not username:
            flash("Please enter your username.", "error")
            return render_template("register.html")

        if not email:
            flash("Please enter your email address.", "error")
            return render_template("register.html")

        if not password:
            flash("Please enter your password.", "error")
            return render_template("register.html")

        if not is_valid_email(email):
            flash(
                "Please enter a valid email address, "
                "for example name@example.com.",
                "error"
            )
            return render_template("register.html")

        if len(password) < 8:
            flash(
                "Your password must contain at least 8 characters.",
                "error"
            )
            return render_template("register.html")

        connection = None
        cursor = None

        try:
            connection = get_db_connection()
            cursor = connection.cursor()

            cursor.execute(
                """
                SELECT user_id
                FROM USERS
                WHERE username = %s OR email = %s
                """,
                (username, email)
            )

            if cursor.fetchone():
                flash(
                    "This username or email is already registered.",
                    "error"
                )
                return render_template("register.html")

            password_hash = generate_password_hash(password)

            cursor.execute(
                """
                INSERT INTO USERS (username, email, password_hash)
                VALUES (%s, %s, %s)
                """,
                (username, email, password_hash)
            )

            connection.commit()

            flash(
                "Account created successfully! Please log in.",
                "success"
            )
            return redirect(url_for("login"))

        except mysql.connector.Error:
            if connection and connection.is_connected():
                connection.rollback()

            app.logger.exception("Registration database error")
            flash(
                "Registration failed. Please check your database settings.",
                "error"
            )

        finally:
            if cursor:
                cursor.close()
            if connection and connection.is_connected():
                connection.close()

    return render_template("register.html")


# Temporary page after successful login
@app.route("/library")
def library():
    if "user_id" not in session:
        flash("Please log in to continue.", "error")
        return redirect(url_for("login"))

    return f"""
        <h1>Welcome, {session['username']}!</h1>
        <p>You have logged in successfully.</p>
        <a href="{url_for('logout')}">Log out</a>
    """


# Logout
@app.route("/logout")
def logout():
    session.clear()
    flash("You have logged out successfully.", "success")
    return redirect(url_for("login"))


if __name__ == "__main__":
    app.run(debug=True)
