import os
from functools import wraps
from flask import Flask, render_template, request, url_for, redirect, abort, make_response
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy.sql import func
import jwt
from flask_bcrypt import generate_password_hash, check_password_hash
from flask_jwt_extended import JWTManager, create_access_token, set_access_cookies

from config import JWT_SECRET_KEY, JWT_TOKEN_LOCATION, Config
from forms import LoginForm, RegisterForm, UploadPhotoForm

app = Flask(__name__)
basedir = os.path.abspath(os.path.dirname(__file__))
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///' + os.path.join(basedir, 'database.db')
# app.config['SQLALCHEMY_DATABASE_URI'] = Config.SQLALCHEMY_DATABASE_URI
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = Config.SQLALCHEMY_TRACK_MODIFICATIONS
app.config['SECRET_KEY'] = Config.SECRET_KEY
app.config['JWT_SECRET_KEY'] = JWT_SECRET_KEY
app.config['JWT_TOKEN_LOCATION'] = JWT_TOKEN_LOCATION
app.config['JWT_COOKIE_SECURE'] = not app.debug
app.config['WTF_CSRF_CHECK_DEFAULT'] = False  # turn off flask_wtf csrf check, use flask_jwt_extended csrf check instead
db = SQLAlchemy(app)
jwt_manager = JWTManager(app)


# Database models

class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    email = db.Column(db.String(80), unique=True, nullable=False)
    password = db.Column(db.String(100), nullable=False)
    contact = db.Column(db.String(30), nullable=False)

    def __init__(self, name, email, password, contact):
        self.name = name
        self.email = email
        self.password = generate_password_hash(password).decode('utf8')  # bcrypt adds salt automatically
        self.contact = contact
    def __repr__(self):
        return f'<User {self.email}, {self.name}>'

class Photo(db.Model):
    id = db.Column(db.Integer, primary_key=True)  # id for photo
    friend_name = db.Column(db.String(100), nullable=False)
    friend_contact = db.Column(db.String(100), nullable=False)
    upload_date = db.Column(db.DateTime(timezone=True), server_default=func.now())
    photo_path = db.Column(db.String(100), nullable=False)
    contact = db.Column(db.String(100), nullable=False)
    activity = db.Column(db.String(100), nullable=True)
    uploader_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)  # id of the uploader
    def __repr__(self):
        return f'<Photo {self.friend_name}, {self.friend_contact}, {self.photo_path}>'


def create_new_db():
    db.drop_all()  # clear database
    db.create_all()
    
def db_add_user(name, email, password, contact):
    user = User(name=name,
                email=email,
                password=password,
                contact=contact)
    db.session.add(user)
    db.session.commit()
    return user

def db_upload_photos(friend_name, friend_contact, photo_path, contact, uploader_id):
    photo = Photo(friend_name='John',
                  friend_contact='0987654321',
                  photo_path='photo.jpg',
                  contact='0987654321',
                  uploader_id=1)
    db.session.add(photo)
    db.session.commit()

def populating_example_data():
    db_add_user('John',
                'johndoe@example.com',
                'password',
                '0987654321')
    db_upload_photos('John',
                    '0987654321',
                    'photo.jpg',
                    '0987654321',
                    1)

with app.app_context():
    create_new_db()
    populating_example_data()


def redirect_to_upload_if_token_valid(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        access_token = request.cookies.get('access_token_cookie')
        print('decorator run')
        if access_token:
            print('access token exists')
            try:
                jwt.decode(access_token, JWT_SECRET_KEY, algorithms=['HS256'])  # type: ignore
                return redirect(url_for('upload'))
            except jwt.ExpiredSignatureError as e:
                print(e)
            except jwt.InvalidSignatureError as e:
                print(e)
            except jwt.InvalidTokenError as e:
                print(e)
        return f(*args, **kwargs)
    return decorated


@app.route("/")
@redirect_to_upload_if_token_valid
def main():
    return render_template('index.html')


@app.route("/upload")
def upload():
    upload_form = UploadPhotoForm()
    return render_template('upload.html', title='Upload', form=upload_form)


@app.route('/login', methods=['GET', 'POST'])  # type: ignore
@redirect_to_upload_if_token_valid
def login():
    if request.method == 'POST':
        email = request.form['email']
        password = request.form['password']
        user = User.query.filter_by(email=email).first()
        if not user or not check_password_hash(user.password, password):
            abort(401, description='Incorrect email or password.')
        else:
            access_token = create_access_token(identity=user.id)
            resp = make_response(redirect(url_for('upload')))
            set_access_cookies(resp, access_token)
            return resp
    if request.method == 'GET':
        login_form = LoginForm()
        return render_template('login.html', title='Sign In', form=login_form)


@app.route('/register', methods=['GET', 'POST'])  # type: ignore
@redirect_to_upload_if_token_valid
def register():
    if request.method == 'GET':
        register_form = RegisterForm()
        return render_template('register.html', title='Register', form=register_form)
    if request.method == 'POST':
        name = request.form['name']
        email = request.form['email']
        password = request.form['password']
        contact = request.form['contact']
        existing_user = User.query.filter_by(email=email).first()
        if existing_user:
            abort(409, description='Email already exists.')
        user = db_add_user(name, email, password, contact)

        access_token = create_access_token(user.id)
        resp = make_response(redirect(url_for('upload')))
        set_access_cookies(resp, access_token)
        return resp
