
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
def get_library_connection():
    return mysql.connector.connect(
        host=os.getenv("DB_HOST", "localhost"),
        user=os.getenv("DB_USER", "root"),
        password=os.getenv("DB_PASSWORD"),
        database="library_db"
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



# Library dashboard - F2.1
@app.route("/library")
def library():
    if "user_id" not in session:
        flash("Please log in to continue.", "error")
        return redirect(url_for("login"))

    connection = None
    cursor = None

    try:
        connection = get_library_connection()
        cursor = connection.cursor(dictionary=True)

        cursor.execute(
            "SELECT author_id, name, country FROM AUTHOR"
        )
        authors = cursor.fetchall()

        cursor.execute(
            "SELECT book_id, title, price, author_id FROM BOOK"
        )
        books = cursor.fetchall()

        return render_template(
            "library.html",
            authors=authors,
            books=books
        )

    except mysql.connector.Error:
        app.logger.exception("Library database error")
        flash(
            "Could not load the library. Please check your database.",
            "error"
        )
        return redirect(url_for("logout"))

    finally:
        if cursor:
            cursor.close()
        if connection and connection.is_connected():
            connection.close()

# Add a new book - F2.2
@app.route("/books/add", methods=["POST"])
def add_book():
    if "user_id" not in session:
        flash("Please log in to continue.", "error")
        return redirect(url_for("login"))

    title = request.form.get("title", "").strip()
    price_text = request.form.get("price", "").strip()
    author_id = request.form.get("author_id", "").strip()

    if not title or not price_text or not author_id:
        flash("Please fill in all book fields.", "error")
        return redirect(url_for("library"))

    try:
        price = float(price_text)
        author_id = int(author_id)

        if price < 0:
            raise ValueError

        connection = get_library_connection()
        cursor = connection.cursor()

        cursor.execute(
            "SELECT author_id FROM AUTHOR WHERE author_id = %s",
            (author_id,)
        )
        if not cursor.fetchone():
            flash("Please select a valid author.", "error")
            return redirect(url_for("library"))

        cursor.execute(
            """
            INSERT INTO BOOK (title, price, author_id)
            VALUES (%s, %s, %s)
            """,
            (title, price, author_id)
        )
        connection.commit()
        flash("Book added successfully!", "success")

    except ValueError:
        flash("Enter a valid non-negative price and author ID.", "error")
    except mysql.connector.Error:
        app.logger.exception("Could not add book")
        flash("Could not add the book. Please try again.", "error")
    finally:
        if "cursor" in locals():
            cursor.close()
        if "connection" in locals() and connection.is_connected():
            connection.close()

    return redirect(url_for("library"))


# Add a new author - F2.2
@app.route("/authors/add", methods=["POST"])
def add_author():
    if "user_id" not in session:
        flash("Please log in to continue.", "error")
        return redirect(url_for("login"))

    name = request.form.get("name", "").strip()
    country = request.form.get("country", "").strip()

    if not name:
        flash("Please enter the author's name.", "error")
        return redirect(url_for("library"))

    connection = None
    cursor = None

    try:
        connection = get_library_connection()
        cursor = connection.cursor()

        cursor.execute(
            "INSERT INTO AUTHOR (name, country) VALUES (%s, %s)",
            (name, country or None)
        )
        connection.commit()
        flash("Author added successfully!", "success")

    except mysql.connector.Error:
        if connection and connection.is_connected():
            connection.rollback()
        app.logger.exception("Could not add author")
        flash("Could not add the author. Please try again.", "error")

    finally:
        if cursor:
            cursor.close()
        if connection and connection.is_connected():
            connection.close()

    return redirect(url_for("library"))


# Edit a book - F2.3
@app.route("/books/edit/<int:book_id>", methods=["POST"])
def edit_book(book_id):
    if "user_id" not in session:
        flash("Please log in to continue.", "error")
        return redirect(url_for("login"))

    title = request.form.get("title", "").strip()
    price_text = request.form.get("price", "").strip()
    author_id_text = request.form.get("author_id", "").strip()

    connection = None
    cursor = None

    try:
        if not title or not price_text or not author_id_text:
            flash("Please fill in all book fields.", "error")
            return redirect(url_for("library"))

        price = float(price_text)
        author_id = int(author_id_text)

        if price < 0:
            raise ValueError

        connection = get_library_connection()
        cursor = connection.cursor()

        cursor.execute(
            "SELECT author_id FROM AUTHOR WHERE author_id = %s",
            (author_id,)
        )
        if not cursor.fetchone():
            flash("Please choose a valid author.", "error")
            return redirect(url_for("library"))

        cursor.execute(
            """
            UPDATE BOOK
            SET title = %s, price = %s, author_id = %s
            WHERE book_id = %s
            """,
            (title, price, author_id, book_id)
        )

        if cursor.rowcount == 0:
            flash("Book not found or no changes were made.", "error")
        else:
            connection.commit()
            flash("Book updated successfully!", "success")

    except ValueError:
        flash("Enter a valid price and author ID.", "error")
    except mysql.connector.Error:
        if connection and connection.is_connected():
            connection.rollback()
        app.logger.exception("Could not edit book")
        flash("Could not update the book.", "error")
    finally:
        if cursor:
            cursor.close()
        if connection and connection.is_connected():
            connection.close()

    return redirect(url_for("library"))


# Edit an author - F2.3
@app.route("/authors/edit/<int:author_id>", methods=["POST"])
def edit_author(author_id):
    if "user_id" not in session:
        flash("Please log in to continue.", "error")
        return redirect(url_for("login"))

    name = request.form.get("name", "").strip()
    country = request.form.get("country", "").strip()

    if not name:
        flash("Please enter the author's name.", "error")
        return redirect(url_for("library"))

    connection = None
    cursor = None

    try:
        connection = get_library_connection()
        cursor = connection.cursor()

        cursor.execute(
            """
            UPDATE AUTHOR
            SET name = %s, country = %s
            WHERE author_id = %s
            """,
            (name, country or None, author_id)
        )

        if cursor.rowcount == 0:
            flash("Author not found or no changes were made.", "error")
        else:
            connection.commit()
            flash("Author updated successfully!", "success")

    except mysql.connector.Error:
        if connection and connection.is_connected():
            connection.rollback()
        app.logger.exception("Could not edit author")
        flash("Could not update the author.", "error")
    finally:
        if cursor:
            cursor.close()
        if connection and connection.is_connected():
            connection.close()

    return redirect(url_for("library"))

# Delete a book - F2.4
@app.route("/books/delete/<int:book_id>", methods=["POST"])
def delete_book(book_id):
    if "user_id" not in session:
        flash("Please log in to continue.", "error")
        return redirect(url_for("login"))

    connection = None
    cursor = None

    try:
        connection = get_library_connection()
        cursor = connection.cursor()

        cursor.execute(
            "DELETE FROM BOOK WHERE book_id = %s",
            (book_id,)
        )

        if cursor.rowcount == 0:
            flash("Book not found.", "error")
        else:
            connection.commit()
            flash("Book deleted successfully!", "success")

    except mysql.connector.Error:
        if connection and connection.is_connected():
            connection.rollback()

        app.logger.exception("Could not delete book")
        flash("Could not delete the book. Please try again.", "error")

    finally:
        if cursor:
            cursor.close()
        if connection and connection.is_connected():
            connection.close()

    return redirect(url_for("library"))

# Delete an author - F2.5
@app.route("/authors/delete/<int:author_id>", methods=["POST"])
def delete_author(author_id):
    if "user_id" not in session:
        flash("Please log in to continue.", "error")
        return redirect(url_for("login"))

    connection = None
    cursor = None

    try:
        connection = get_library_connection()
        cursor = connection.cursor()

        # Find out how many books belong to this author
        cursor.execute(
            "SELECT COUNT(*) FROM BOOK WHERE author_id = %s",
            (author_id,)
        )
        book_count = cursor.fetchone()[0]

        # Delete the author (the database cascades to their books)
        cursor.execute(
            "DELETE FROM AUTHOR WHERE author_id = %s",
            (author_id,)
        )

        if cursor.rowcount == 0:
            flash("Author not found.", "error")
        else:
            connection.commit()
            flash(
                f"Author deleted successfully. "
                f"{book_count} associated book(s) were also deleted.",
                "success"
            )

    except mysql.connector.Error:
        if connection and connection.is_connected():
            connection.rollback()

        app.logger.exception("Could not delete author")
        flash("Could not delete the author. Please try again.", "error")

    finally:
        if cursor:
            cursor.close()
        if connection and connection.is_connected():
            connection.close()

    return redirect(url_for("library"))


# Logout
@app.route("/logout")
def logout():
    session.clear()
    flash("You have logged out successfully.", "success")
    return redirect(url_for("login"))


if __name__ == "__main__":
    app.run(debug=True)
