
import os
import re
import uuid
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
    session,
)
from werkzeug.security import generate_password_hash, check_password_hash


# --------------------------------------------------
# APP CONFIGURATION
# --------------------------------------------------

app = Flask(__name__)

load_dotenv(Path(__file__).resolve().parent / ".env")

app.secret_key = os.getenv("SECRET_KEY", "library-dev-key")

UPLOAD_FOLDER = Path(__file__).resolve().parent / "static" / "uploads"
UPLOAD_FOLDER.mkdir(parents=True, exist_ok=True)

app.config["UPLOAD_FOLDER"] = str(UPLOAD_FOLDER)
app.config["MAX_CONTENT_LENGTH"] = 5 * 1024 * 1024

ALLOWED_EXTENSIONS = {"png", "jpg", "jpeg", "webp"}


# --------------------------------------------------
# IMAGE UPLOAD FUNCTIONS
# --------------------------------------------------

def allowed_image(filename):
    return (
        "." in filename
        and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS
    )


def save_uploaded_image(image):
    if not image or not image.filename:
        return None

    if not allowed_image(image.filename):
        raise ValueError(
            "Invalid image format. Use PNG, JPG, JPEG, or WEBP."
        )

    extension = Path(image.filename).suffix.lower()
    filename = f"{uuid.uuid4().hex}{extension}"

    image.save(UPLOAD_FOLDER / filename)

    # This path is relative to the static folder.
    return f"uploads/{filename}"


def delete_uploaded_image(image_path):
    """Delete an uploaded image if it exists."""
    if not image_path:
        return

    path = (UPLOAD_FOLDER / Path(image_path).name).resolve()

    if path.parent == UPLOAD_FOLDER.resolve() and path.is_file():
        path.unlink()


# --------------------------------------------------
# DATABASE CONNECTIONS
# --------------------------------------------------

def get_db_connection():
    """Connect to the database used for login and registration."""
    return mysql.connector.connect(
        host=os.getenv("DB_HOST", "localhost"),
        user=os.getenv("DB_USER", "root"),
        password=os.getenv("DB_PASSWORD", ""),
        database=os.getenv("DB_NAME", "library_auth_db"),
    )


def get_library_connection():
    """Connect to the library database."""
    return mysql.connector.connect(
        host=os.getenv("DB_HOST", "localhost"),
        user=os.getenv("DB_USER", "root"),
        password=os.getenv("DB_PASSWORD", ""),
        database="library_db",
    )


# --------------------------------------------------
# VALIDATION
# --------------------------------------------------

def is_valid_email(email):
    pattern = r"^[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}$"
    return re.fullmatch(pattern, email) is not None


def is_logged_in():
    return "user_id" in session


# --------------------------------------------------
# HOME PAGE
# --------------------------------------------------

@app.route("/")
def index():
    if is_logged_in():
        return redirect(url_for("library"))

    return redirect(url_for("login"))


# --------------------------------------------------
# LOGIN
# --------------------------------------------------

@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        identifier = (
            request.form.get("email", "").strip()
            or request.form.get("username", "").strip()
            or request.form.get("identifier", "").strip()
        )
        password = request.form.get("password", "")

        if not identifier or not password:
            flash("Please enter your username/email and password.", "error")
            return redirect(url_for("login"))

        connection = None
        cursor = None

        try:
            connection = get_db_connection()
            cursor = connection.cursor(dictionary=True)

            cursor.execute(
                """
                SELECT user_id, username, email, password_hash
                FROM USERS
                WHERE username = %s OR email = %s
                """,
                (identifier, identifier),
            )

            user = cursor.fetchone()

            if user and check_password_hash(
                user["password_hash"], password
            ):
                session.clear()
                session["user_id"] = user["user_id"]
                session["username"] = user["username"]

                flash("Login successful!", "success")
                return redirect(url_for("library"))

            flash("Invalid username/email or password.", "error")

        except mysql.connector.Error as error:
            app.logger.exception("Login database error")
            flash("Could not connect to the database. Check your settings.", "error")

        finally:
            if cursor:
                cursor.close()
            if connection and connection.is_connected():
                connection.close()

    return render_template("login.html")


# --------------------------------------------------
# REGISTRATION
# --------------------------------------------------

@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        email = request.form.get("email", "").strip()
        password = request.form.get("password", "")
        confirm_password = request.form.get(
            "confirm_password",
            request.form.get("confirm-password", ""),
        )

        if not username or not email or not password:
            flash("Please complete all required fields.", "error")
            return redirect(url_for("register"))

        if not is_valid_email(email):
            flash("Please enter a valid email address.", "error")
            return redirect(url_for("register"))

        if len(password) < 8:
            flash("Password must contain at least 8 characters.", "error")
            return redirect(url_for("register"))

        if confirm_password and password != confirm_password:
            flash("Passwords do not match.", "error")
            return redirect(url_for("register"))

        password_hash = generate_password_hash(password)

        connection = None
        cursor = None

        try:
            connection = get_db_connection()
            cursor = connection.cursor()

            cursor.execute(
                """
                INSERT INTO USERS (username, email, password_hash)
                VALUES (%s, %s, %s)
                """,
                (username, email, password_hash),
            )

            connection.commit()

            flash("Registration successful. You can now log in.", "success")
            return redirect(url_for("login"))

        except mysql.connector.IntegrityError:
            if connection:
                connection.rollback()
            flash("That username or email may already be registered.", "error")

        except mysql.connector.Error:
            if connection:
                connection.rollback()
            app.logger.exception("Registration database error")
            flash("Registration failed. Check your database settings.", "error")

        finally:
            if cursor:
                cursor.close()
            if connection and connection.is_connected():
                connection.close()

    return render_template("register.html")


# --------------------------------------------------
# LOG OUT
# --------------------------------------------------

@app.route("/logout")
def logout():
    session.clear()
    flash("You have been logged out.", "success")
    return redirect(url_for("login"))


# --------------------------------------------------
# LIBRARY DASHBOARD
# --------------------------------------------------

@app.route("/library")
def library():
    if not is_logged_in():
        flash("Please log in first.", "error")
        return redirect(url_for("login"))

    connection = None
    cursor = None

    try:
        connection = get_library_connection()
        cursor = connection.cursor(dictionary=True)

        cursor.execute(
            """
            SELECT author_id, name, country, author_image
            FROM AUTHOR
            ORDER BY author_id
            """
        )
        authors = cursor.fetchall()

        cursor.execute(
            """
            SELECT book_id, title, price, author_id, cover_image
            FROM BOOK
            ORDER BY book_id
            """
        )
        books = cursor.fetchall()

        return render_template(
            "library.html",
            books=books,
            authors=authors,
        )

    except mysql.connector.Error:
        app.logger.exception("Library database error")
        flash("Could not load the library. Check the database connection.", "error")
        return redirect(url_for("login"))

    finally:
        if cursor:
            cursor.close()
        if connection and connection.is_connected():
            connection.close()


# --------------------------------------------------
# ADD A BOOK
# --------------------------------------------------

@app.route("/books/add", methods=["POST"])
def add_book():
    if not is_logged_in():
        return redirect(url_for("login"))

    title = request.form.get("title", "").strip()
    price = request.form.get("price", "").strip()
    author_id = request.form.get("author_id", "").strip()
    image = request.files.get("cover_image")

    if not title or not price or not author_id:
        flash("Please complete all required book fields.", "error")
        return redirect(url_for("library"))

    try:
        price = float(price)
        author_id = int(author_id)

        if price < 0:
            raise ValueError

    except ValueError:
        flash("Enter a valid price and select an author.", "error")
        return redirect(url_for("library"))

    connection = None
    cursor = None
    image_path = None

    try:
        if image and image.filename:
            image_path = save_uploaded_image(image)

        connection = get_library_connection()
        cursor = connection.cursor()

        cursor.execute(
            """
            INSERT INTO BOOK (title, price, author_id, cover_image)
            VALUES (%s, %s, %s, %s)
            """,
            (title, price, author_id, image_path),
        )

        connection.commit()
        flash("Book added successfully!", "success")

    except ValueError as error:
        flash(str(error), "error")

    except mysql.connector.Error:
        if connection:
            connection.rollback()

        if image_path:
            delete_uploaded_image(image_path)

        app.logger.exception("Add book database error")
        flash("Could not add the book. Check the selected author and database.", "error")

    finally:
        if cursor:
            cursor.close()
        if connection and connection.is_connected():
            connection.close()

    return redirect(url_for("library"))


# --------------------------------------------------
# ADD AN AUTHOR
# --------------------------------------------------

@app.route("/authors/add", methods=["POST"])
def add_author():
    if not is_logged_in():
        return redirect(url_for("login"))

    name = request.form.get("name", "").strip()
    country = request.form.get("country", "").strip()
    image = request.files.get("author_image")

    if not name:
        flash("Author name is required.", "error")
        return redirect(url_for("library"))

    connection = None
    cursor = None
    image_path = None

    try:
        if image and image.filename:
            image_path = save_uploaded_image(image)

        connection = get_library_connection()
        cursor = connection.cursor()

        cursor.execute(
            """
            INSERT INTO AUTHOR (name, country, author_image)
            VALUES (%s, %s, %s)
            """,
            (name, country or None, image_path),
        )

        connection.commit()
        flash("Author added successfully!", "success")

    except ValueError as error:
        flash(str(error), "error")

    except mysql.connector.Error:
        if connection:
            connection.rollback()

        if image_path:
            delete_uploaded_image(image_path)

        app.logger.exception("Add author database error")
        flash("Could not add the author.", "error")

    finally:
        if cursor:
            cursor.close()
        if connection and connection.is_connected():
            connection.close()

    return redirect(url_for("library"))


# --------------------------------------------------
# EDIT A BOOK
# --------------------------------------------------

@app.route("/books/edit/<int:book_id>", methods=["POST"])
def edit_book(book_id):
    if not is_logged_in():
        return redirect(url_for("login"))

    title = request.form.get("title", "").strip()
    price = request.form.get("price", "").strip()
    author_id = request.form.get("author_id", "").strip()
    image = request.files.get("cover_image")

    if not title or not price or not author_id:
        flash("Please complete all required book fields.", "error")
        return redirect(url_for("library"))

    try:
        price = float(price)
        author_id = int(author_id)

        if price < 0:
            raise ValueError

    except ValueError:
        flash("Enter a valid price and select an author.", "error")
        return redirect(url_for("library"))

    connection = None
    cursor = None
    new_image_path = None
    old_image_path = None

    try:
        connection = get_library_connection()
        cursor = connection.cursor(dictionary=True)

        cursor.execute(
            "SELECT cover_image FROM BOOK WHERE book_id = %s",
            (book_id,),
        )
        book = cursor.fetchone()

        if not book:
            flash("Book not found.", "error")
            return redirect(url_for("library"))

        old_image_path = book["cover_image"]

        if image and image.filename:
            new_image_path = save_uploaded_image(image)

            cursor.execute(
                """
                UPDATE BOOK
                SET title = %s, price = %s, author_id = %s,
                    cover_image = %s
                WHERE book_id = %s
                """,
                (title, price, author_id, new_image_path, book_id),
            )
        else:
            cursor.execute(
                """
                UPDATE BOOK
                SET title = %s, price = %s, author_id = %s
                WHERE book_id = %s
                """,
                (title, price, author_id, book_id),
            )

        connection.commit()

        if new_image_path and old_image_path:
            delete_uploaded_image(old_image_path)

        flash("Book updated successfully!", "success")

    except ValueError as error:
        flash(str(error), "error")

    except mysql.connector.Error:
        if connection:
            connection.rollback()

        if new_image_path:
            delete_uploaded_image(new_image_path)

        app.logger.exception("Edit book database error")
        flash("Could not update the book.", "error")

    finally:
        if cursor:
            cursor.close()
        if connection and connection.is_connected():
            connection.close()

    return redirect(url_for("library"))


# --------------------------------------------------
# EDIT AN AUTHOR
# --------------------------------------------------

@app.route("/authors/edit/<int:author_id>", methods=["POST"])
def edit_author(author_id):
    if not is_logged_in():
        return redirect(url_for("login"))

    name = request.form.get("name", "").strip()
    country = request.form.get("country", "").strip()
    image = request.files.get("author_image")

    if not name:
        flash("Author name is required.", "error")
        return redirect(url_for("library"))

    connection = None
    cursor = None
    new_image_path = None
    old_image_path = None

    try:
        connection = get_library_connection()
        cursor = connection.cursor(dictionary=True)

        cursor.execute(
            "SELECT author_image FROM AUTHOR WHERE author_id = %s",
            (author_id,),
        )
        author = cursor.fetchone()

        if not author:
            flash("Author not found.", "error")
            return redirect(url_for("library"))

        old_image_path = author["author_image"]

        if image and image.filename:
            new_image_path = save_uploaded_image(image)

            cursor.execute(
                """
                UPDATE AUTHOR
                SET name = %s, country = %s, author_image = %s
                WHERE author_id = %s
                """,
                (name, country or None, new_image_path, author_id),
            )
        else:
            cursor.execute(
                """
                UPDATE AUTHOR
                SET name = %s, country = %s
                WHERE author_id = %s
                """,
                (name, country or None, author_id),
            )

        connection.commit()

        if new_image_path and old_image_path:
            delete_uploaded_image(old_image_path)

        flash("Author updated successfully!", "success")

    except ValueError as error:
        flash(str(error), "error")

    except mysql.connector.Error:
        if connection:
            connection.rollback()

        if new_image_path:
            delete_uploaded_image(new_image_path)

        app.logger.exception("Edit author database error")
        flash("Could not update the author.", "error")

    finally:
        if cursor:
            cursor.close()
        if connection and connection.is_connected():
            connection.close()

    return redirect(url_for("library"))


# --------------------------------------------------
# DELETE A BOOK
# --------------------------------------------------

@app.route("/books/delete/<int:book_id>", methods=["POST"])
def delete_book(book_id):
    if not is_logged_in():
        return redirect(url_for("login"))

    connection = None
    cursor = None
    image_path = None

    try:
        connection = get_library_connection()
        cursor = connection.cursor(dictionary=True)

        cursor.execute(
            "SELECT cover_image FROM BOOK WHERE book_id = %s",
            (book_id,),
        )
        book = cursor.fetchone()

        if not book:
            flash("Book not found.", "error")
            return redirect(url_for("library"))

        image_path = book["cover_image"]

        cursor.execute(
            "DELETE FROM BOOK WHERE book_id = %s",
            (book_id,),
        )

        connection.commit()

        if image_path:
            delete_uploaded_image(image_path)

        flash("Book deleted successfully!", "success")

    except mysql.connector.Error:
        if connection:
            connection.rollback()

        app.logger.exception("Delete book database error")
        flash("Could not delete the book.", "error")

    finally:
        if cursor:
            cursor.close()
        if connection and connection.is_connected():
            connection.close()

    return redirect(url_for("library"))


# --------------------------------------------------
# DELETE AN AUTHOR
# --------------------------------------------------

@app.route("/authors/delete/<int:author_id>", methods=["POST"])
def delete_author(author_id):
    if not is_logged_in():
        return redirect(url_for("login"))

    connection = None
    cursor = None
    author_image_path = None
    book_image_paths = []

    try:
        connection = get_library_connection()
        cursor = connection.cursor(dictionary=True)

        cursor.execute(
            "SELECT author_image FROM AUTHOR WHERE author_id = %s",
            (author_id,),
        )
        author = cursor.fetchone()

        if not author:
            flash("Author not found.", "error")
            return redirect(url_for("library"))

        author_image_path = author["author_image"]

        cursor.execute(
            "SELECT cover_image FROM BOOK WHERE author_id = %s",
            (author_id,),
        )
        book_image_paths = [
            row["cover_image"]
            for row in cursor.fetchall()
            if row["cover_image"]
        ]

        cursor.execute(
            "SELECT COUNT(*) AS total FROM BOOK WHERE author_id = %s",
            (author_id,),
        )
        book_count = cursor.fetchone()["total"]

        # The database foreign key should cascade-delete the author's books.
        cursor.execute(
            "DELETE FROM AUTHOR WHERE author_id = %s",
            (author_id,),
        )

        connection.commit()

        if author_image_path:
            delete_uploaded_image(author_image_path)

        for image_path in book_image_paths:
            delete_uploaded_image(image_path)

        flash(
            f"Author deleted successfully. {book_count} associated book(s) deleted.",
            "success",
        )

    except mysql.connector.Error:
        if connection:
            connection.rollback()

        app.logger.exception("Delete author database error")
        flash("Could not delete the author.", "error")

    finally:
        if cursor:
            cursor.close()
        if connection and connection.is_connected():
            connection.close()

    return redirect(url_for("library"))


# --------------------------------------------------
# RUN THE APPLICATION
# --------------------------------------------------

if __name__ == "__main__":
    app.run(debug=True)
