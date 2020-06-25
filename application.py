import os
import requests

from flask import Flask, flash, session, url_for, redirect, render_template, request, jsonify
from flask_session import Session
from sqlalchemy import create_engine
from sqlalchemy.orm import scoped_session, sessionmaker

app = Flask(__name__)

# INFO #

# host = ec2-34-193-117-204.compute-1.amazonaws.com
# database = d3re1hp0s2l9ed
# URI = postgres://skldzcighsbyzo:879d26f8bef16ae5cb18fe8e036d161737d5ec74dc14
# c2c824518b4b30a1bce9@ec2-34-193-117-204.compute-1.amazonaws.com:5432/d3re1hp0s2l9ed

# good reads key
key = "R8EG81qbuducjoKKdEbA"

# Check for environment variable
if not os.getenv("DATABASE_URL"):
    raise RuntimeError("DATABASE_URL is not set")

# Configure session to use filesystem
app.config["SESSION_PERMANENT"] = False
app.config["SESSION_TYPE"] = "filesystem"
Session(app)

# Set up database
engine = create_engine(os.getenv("DATABASE_URL"))
db = scoped_session(sessionmaker(bind=engine))

@app.route("/", methods=["GET", "POST"])
def index():
    if request.method == 'POST':
        # get information from form
        attribute = request.form.get("attributes")
        book_info = "%" + request.form.get("book_info").lower() + "%"
        
        # select results
        results = db.execute(f"SELECT * FROM books WHERE {attribute} LIKE :book_info", 
                            {"book_info": book_info}).fetchall()
        db.commit()

        if results:
            return render_template("index.html", results = results)

        else:
            return render_template("error.html", message = "There were no matches for your search")

    else:
        return render_template("index.html")

@app.route("/register", methods=["GET", "POST"])
def register():

    if request.method == 'POST':
        
        # get information from register.html
        username = request.form.get("username").lower()
        password = request.form.get("password")
        password_confirmation = request.form.get("password_confirmation")

        # check input
        if not username or not password or not password_confirmation:
            return render_template("error.html", message = "Fill all the blanks")

        if password != password_confirmation:
            return render_template("error.html", message = "Passwords do not match, retry")
        
        # check if username already exists
        username_check = db.execute("SELECT username FROM users WHERE username = :username", 
                                    {"username": username}).fetchone()
        db.commit()

        if username_check:
            return render_template("error.html", message = "Username already in use, try another one")

        # register user
        db.execute("INSERT INTO users (username, password) VALUES (:username, :password)", 
                    {"username": username, "password": password})
        db.commit()

        # login user
        user_id = db.execute("SELECT id FROM users WHERE username=:username",
                            {"username": username}).fetchone()
        db.commit()

        session["user_id"] = user_id.id

        return render_template("index.html")
    
    else:
        return render_template("register.html")

@app.route("/login", methods=["GET", "POST"])
def login():

    if request.method == 'POST':
        # get information from form
        username = request.form.get("username").lower()
        password = request.form.get("password")

        # check if matches database
        user_info = db.execute("SELECT * FROM users WHERE username = :username AND password = :password",
                    {"username": username, "password": password}).fetchone()
        db.commit()

        if not user_info:
            return render_template("error.html", message="Username and password do not match")
        
        else:
            # login user
            session["user_id"] = user_info.id

            return render_template("index.html")

    else:
        return render_template("login.html")

@app.route("/logout", methods=["POST"])
def logout():
    if 'user_id' in session:  
        session.pop('user_id',None)  
    return render_template("index.html")

@app.route("/book/<string:isbn>", methods=["GET", "POST"])
def book(isbn):

    if request.method == 'POST':
        if not "user_id" in session:
            return render_template("error.html", message="You need to log in to leave a review")
        
        # Check if iuser left a previous review
        previous = db.execute("SELECT user_id FROM reviews WHERE user_id = :user_id and book_isbn = :isbn", 
                                {"user_id": session["user_id"], "isbn": isbn}).fetchone()
        db.commit()

        if previous:
            return render_template("error.html", message="Sorry, you can only review a book once")

        # if not previous
        rating = request.form.get("rating")
        review = request.form.get("review")

        db.execute("""INSERT INTO reviews (user_id, review, book_isbn, rating)
                    VALUES(:user_id, :review, :isbn, :rating)""", {"user_id": session["user_id"], 
                    "review": review, "isbn": isbn, "rating": rating})
        db.commit()

        return redirect(url_for("book", isbn=isbn))




    else:
        book = db.execute("SELECT * FROM books WHERE isbn = :isbn",
                            {"isbn": isbn}).fetchone()
        db.commit()
        reviews = db.execute("""SELECT username, review, rating FROM 
                            reviews JOIN users ON users.id = reviews.user_id 
                            WHERE book_isbn = :isbn""", {"isbn": isbn}).fetchall()
        db.commit()

        # Get information from Goodreads API
        ratings = goodreads(isbn)

        return render_template("book.html", reviews=reviews, book=book, rating_count=ratings[0], average_rating=ratings[1])


@app.route("/api/<isbn>")
def api(isbn):
    ratings = goodreads(isbn)

    if ratings == 404:
        ratings = [None, None]
    
    book = db.execute("SELECT * FROM books WHERE isbn = :isbn", 
                        {"isbn": isbn}).fetchone()
    db.commit()

    if book is None:
        return jsonify({"error": "Book not in database"}), 404
    
    return jsonify({
                        "title": book.title,
                        "author": book.author,
                        "year": book.year,
                        "isbn": isbn,
                        "review_count": ratings[0],
                        "average_score": ratings[1]
                    })

# Get information from Goodreads API
def goodreads(isbn):
    res = requests.get("https://www.goodreads.com/book/review_counts.json", 
                    params={"key": key, "isbns": isbn})

    if res.status_code != 200:
      return 404
    
    goodreads_info = res.json()

    goodreads_info = [goodreads_info["books"][0]["work_ratings_count"], 
                        goodreads_info["books"][0]["average_rating"]]

    return goodreads_info