import os
import json

from datetime import date
from cs50 import SQL
from flask import Flask, flash, jsonify, redirect, render_template, request, session
from flask_session import Session
from tempfile import mkdtemp
from werkzeug.exceptions import default_exceptions, HTTPException, InternalServerError
from werkzeug.security import check_password_hash, generate_password_hash

from helpers import apology, login_required

# Configure application
app = Flask(__name__)

# Ensure templates are auto-reloaded
app.config["TEMPLATES_AUTO_RELOAD"] = True

# Ensure responses aren't cached
@app.after_request
def after_request(response):
    response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    response.headers["Expires"] = 0
    response.headers["Pragma"] = "no-cache"
    return response


# Configure session to use filesystem (instead of signed cookies)
app.config["SESSION_FILE_DIR"] = mkdtemp()
app.config["SESSION_PERMANENT"] = False
app.config["SESSION_TYPE"] = "filesystem"
Session(app)

# Configure CS50 Library to use SQLite database
db = SQL("sqlite:///insulin.db")


@app.route("/", methods=["GET", "POST"])
def index():
    if request.method == "GET":
        return render_template("homepage.html")


@app.route("/enter_foods", methods=["GET", "POST"])
@login_required
def enter_foods():
    if request.method == "POST":
        # initialize i and create food items
        i = 0
        food_items = []

        # if food item exists, add food items and servings into a list of lists
        while(request.form.get("food_item_"+str(i)) != None):
            food_items.append([request.form.get("food_item_"+str(i)), request.form.get("serving_"+str(i))])
            i += 1

        # get the target blood sugar level, current blood sugar level, and meal from user input
        target_bsl = float(request.form.get("target_bl"))
        current_bsl = float(request.form.get("current_bl"))
        meal = request.form.get("meal")

        total_carbs = 0

        # iterates through the user inputs to find the carbohydrate contents for each food
        for food in food_items:
            carbs_db = db.execute("SELECT Carbs FROM nutrition WHERE LOWER(Short_Name) LIKE LOWER(:name)", name='%'+food[0]+'%')

            # check to see if food item exists
            if not carbs_db:
                return apology("Food does not exist in our database, sorry!", 403)
            else:
                carbs = float(carbs_db[0]['Carbs'])
                servings = float(food[1])
                total_carbs += carbs*servings

        weight = db.execute("SELECT weight FROM users WHERE id = :id", id=session["user_id"])[0]['weight']

        # get the total dosage of insulin needed for meal with the calculate function
        total_dosage = calculate(weight, total_carbs, current_bsl, target_bsl)

        # input foods eaten into history table
        for food in food_items:
            db.execute("INSERT INTO history (user_id, date, food, servings, meal, dosage) VALUES (:user_id, :date, :food, :servings, :meal, :dosage)",
                       user_id=session["user_id"], date=date.today(), food=food[0], servings=food[1], meal=meal, dosage=total_dosage)

        # Redirect user to home
        return render_template("entered_foods.html", dosage=total_dosage)

    if request.method == "GET":
        return render_template("enter_foods.html")

# takes the weight, total_carbs of meal, actual blood sugar level, and target blood sugar level to calculate the total dose of insulin needed


def calculate(weight, total_carbs, actual_bsl, target_bsl):

    # calculate the total daily dose of insulin (TDD)
    TDD = float(0.55 * float(weight))

    # calculate insulin required to cover carbohydrate in meal
    BD = float(TDD / 450) * total_carbs

    # calculate the insulin sensitivity factor (correction factor)
    ISF = float(1700 / TDD)

    # calculate the correction dose insulin
    CD = (actual_bsl - target_bsl) / ISF

    # calculate total dosage
    TD = BD + CD

    # return insulin dosage value
    return round(TD, 2)


@app.route("/foodsearch", methods=["GET", "POST"])
def foodsearch():
    if request.method == "POST":
        # check if user inputted food
        if not request.form.get("food"):
            return apology("must provide food", 403)

        foodname = request.form.get("food")
        # query database for food items containing some form of the user input
        food = db.execute("SELECT Short_Name, Carbs FROM nutrition WHERE Short_Name LIKE LOWER(:foodname)",
                          foodname='%'+foodname+'%')

        # check if food actually exists
        if not food:
            return apology("Food does not exist in our database, sorry!", 403)

        # given all of these things are correct, return the list of appropriate foods
        return render_template("foodresult.html", food=food)

    if request.method == "GET":
        return render_template("foodsearch.html")


@app.route("/addfoods", methods=["GET", "POST"])
def addfoods():
    if request.method == "POST":
        # check if user inputted food
        if not request.form.get("food"):
            return apology("must provide food", 403)

        foodname = request.form.get("food")
        carbs = request.form.get("carbs")

        # get foods from database
        is_food = db.execute("SELECT Short_Name FROM nutrition WHERE Short_Name = :foodname", foodname=foodname)

        # check to see if food is already in database
        if (len(is_food) > 0):
            return render_template("addfoods.html", food_item=json.dumps(foodname), food_exists=json.dumps('True'))
        else:
            # insert into the nutrition table the user inputted food and carb content
            food = db.execute("INSERT INTO nutrition (Short_Name, Carbs) VALUES (:foodname, :carbs)",
                              foodname=foodname, carbs=carbs)

            # after adding the food, go back to the addfoods template
            return render_template("addfoods.html", food_item=json.dumps(foodname), food_exists=json.dumps('False'))

    if request.method == "GET":
        return render_template("addfoods.html")


@app.route("/history")
@login_required
def history():
    # get entries from each user that represent the food inputs per meal, then sorts then by date and meal
    histories = db.execute(
        "SELECT meal, food, servings, dosage, date FROM history WHERE user_id = :user_id ORDER BY date, meal='Dinner',meal='Lunch',meal='Breakfast',food", user_id=session["user_id"])
    return render_template("history.html", histories=histories)


@app.route("/login", methods=["GET", "POST"])
def login():
    """Log user in"""

    # Forget any user_id
    session.clear()

    # User reached route via POST (as by submitting a form via POST)
    if request.method == "POST":

        # Ensure username was submitted
        if not request.form.get("username"):
            return apology("must provide username", 403)

        # Ensure password was submitted
        elif not request.form.get("password"):
            return apology("must provide password", 403)

        # Query database for username
        rows = db.execute("SELECT * FROM users WHERE username = :username",
                          username=request.form.get("username"))

        # Ensure username exists and password is correct
        if len(rows) != 1 or not check_password_hash(rows[0]["hash"], request.form.get("password")):
            return apology("invalid username and/or password", 403)

        # Remember which user has logged in
        session["user_id"] = rows[0]["id"]

        # Redirect user to home page
        return render_template("homepage.html", msg=json.dumps('login'))

    # User reached route via GET (as by clicking a link or via redirect)
    else:
        return render_template("login.html")


@app.route("/logout")
def logout():
    """Log user out"""

    # Forget any user_id
    session.clear()

    # Redirect user to login form
    return redirect("/")


@app.route("/info", methods=["GET", "POST"])
def info():
    if request.method == "GET":
        return render_template("info.html")


@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "GET":
        return render_template("register.html")

    if request.method == "POST":
        username = request.form.get("username")

        # check if username is actually inputted
        if not username:
            return apology("must provide username", 403)
        password = request.form.get("password")

        # check if password is actually inputted
        if not password:
            return apology("must provide password", 403)

        # check password length to make sure that it is at least 8 characters
        if len(password) < 8:
            return apology("password must be at least 8 characters", 403)

        # check password to make sure there is at least one uppercase letter
        if not any(char.isupper() for char in password):
            return apology("password must have at least one uppercase character", 403)

        # check password to make sure there is at least one digit
        if not any(char.isdigit() for char in password):
            return apology("password must have at least one digit", 403)

        # check password to see if passwords match
        if request.form.get("confirmation") != request.form.get("password"):
            return apology("passwords must match", 403)

        # check if weight is integer value larger than 0
        if int(request.form.get("weight")) < 0:
            return apology("weight must be larger than 0", 403)

        # if all is well, generate hashed password and upload into users database
        hash = generate_password_hash(request.form.get("password"))
        newuser = db.execute("INSERT INTO users (username, hash, weight) VALUES (:username, :hash, :weight)",
                             username=request.form.get("username"), hash=hash, weight=request.form.get("weight"))

        # check if username has already been used
        if not newuser:
            return apology("username is taken", 403)

        # update session to be new user's login page
        session["user_id"] = newuser
        return redirect("/")


@app.route("/resources", methods=["GET", "POST"])
def resources():
    if request.method == "GET":
        return render_template("resources.html")


def errorhandler(e):
    """Handle error"""
    if not isinstance(e, HTTPException):
        e = InternalServerError()
    return apology(e.name, e.code)


# Listen for errors
for code in default_exceptions:
    app.errorhandler(code)(errorhandler)
