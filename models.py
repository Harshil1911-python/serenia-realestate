from flask_sqlalchemy import SQLAlchemy
from flask_login import UserMixin
from datetime import datetime
from werkzeug.security import generate_password_hash, check_password_hash

db = SQLAlchemy()

class User(UserMixin, db.Model):
    __tablename__ = 'users'
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(256), nullable=False)
    role = db.Column(db.String(20), default='owner')  # owner, developer
    is_active = db.Column(db.Boolean, default=True)
    failed_logins = db.Column(db.Integer, default=0)
    locked_until = db.Column(db.DateTime, nullable=True)
    totp_secret = db.Column(db.String(32), nullable=True)
    two_fa_enabled = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    last_login = db.Column(db.DateTime, nullable=True)

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

    def is_developer(self):
        return self.role == 'developer'

    def is_owner(self):
        return self.role in ['owner', 'developer']


class SiteSettings(db.Model):
    __tablename__ = 'site_settings'
    id = db.Column(db.Integer, primary_key=True)
    key = db.Column(db.String(100), unique=True, nullable=False)
    value = db.Column(db.Text, nullable=True)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    @staticmethod
    def get(key, default=''):
        s = SiteSettings.query.filter_by(key=key).first()
        return s.value if s else default

    @staticmethod
    def set(key, value):
        s = SiteSettings.query.filter_by(key=key).first()
        if s:
            s.value = value
            s.updated_at = datetime.utcnow()
        else:
            s = SiteSettings(key=key, value=value)
            db.session.add(s)
        db.session.commit()


class Property(db.Model):
    __tablename__ = 'properties'
    id = db.Column(db.Integer, primary_key=True)
    property_id = db.Column(db.String(20), unique=True, nullable=False)
    title = db.Column(db.String(200), nullable=False)
    slug = db.Column(db.String(220), unique=True, nullable=False)
    description = db.Column(db.Text, nullable=True)
    property_type = db.Column(db.String(50), nullable=False)  # residential, commercial, etc.
    listing_type = db.Column(db.String(20), nullable=False)  # sale, rent
    status = db.Column(db.String(30), default='available')  # available, sold, rented, negotiation
    price = db.Column(db.Float, nullable=False)
    price_unit = db.Column(db.String(20), default='total')  # total, per_sqft, per_month
    currency = db.Column(db.String(10), default='INR')  # INR, AED, USD, GBP, SAR, etc.
    area = db.Column(db.Float, nullable=True)
    area_unit = db.Column(db.String(10), default='sqft')
    bedrooms = db.Column(db.Integer, nullable=True)
    bathrooms = db.Column(db.Integer, nullable=True)
    parking = db.Column(db.Integer, nullable=True)
    furnishing = db.Column(db.String(30), nullable=True)  # furnished, semi, unfurnished
    property_age = db.Column(db.String(30), nullable=True)
    address = db.Column(db.String(300), nullable=True)
    city = db.Column(db.String(100), nullable=True)
    state = db.Column(db.String(100), nullable=True)
    pincode = db.Column(db.String(10), nullable=True)
    latitude = db.Column(db.Float, nullable=True)
    longitude = db.Column(db.Float, nullable=True)
    google_map_link = db.Column(db.String(500), nullable=True)
    is_featured = db.Column(db.Boolean, default=False)
    is_latest = db.Column(db.Boolean, default=True)
    views = db.Column(db.Integer, default=0)
    brochure_path = db.Column(db.String(300), nullable=True)
    brochure_auto = db.Column(db.Boolean, default=False)  # whether brochure was auto-generated
    video_url = db.Column(db.String(300), nullable=True)  # YouTube/Vimeo embed link
    meta_title = db.Column(db.String(200), nullable=True)
    meta_description = db.Column(db.String(400), nullable=True)
    public_link_enabled = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    images = db.relationship('PropertyImage', backref='property', lazy=True, cascade='all, delete-orphan')
    videos = db.relationship('PropertyVideo', backref='property', lazy=True, cascade='all, delete-orphan')
    amenities = db.relationship('PropertyAmenity', backref='property', lazy=True, cascade='all, delete-orphan')
    inquiries = db.relationship('Inquiry', backref='property', lazy=True)


class PropertyVideo(db.Model):
    __tablename__ = 'property_videos'
    id = db.Column(db.Integer, primary_key=True)
    property_id = db.Column(db.Integer, db.ForeignKey('properties.id'), nullable=False)
    video_type = db.Column(db.String(20), default='youtube')  # youtube, upload
    url = db.Column(db.String(500), nullable=True)       # youtube/vimeo link
    filename = db.Column(db.String(200), nullable=True)  # uploaded video filename
    title = db.Column(db.String(200), nullable=True)
    sort_order = db.Column(db.Integer, default=0)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


class PropertyImage(db.Model):
    __tablename__ = 'property_images'
    id = db.Column(db.Integer, primary_key=True)
    property_id = db.Column(db.Integer, db.ForeignKey('properties.id'), nullable=False)
    filename = db.Column(db.String(200), nullable=False)
    is_primary = db.Column(db.Boolean, default=False)
    sort_order = db.Column(db.Integer, default=0)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


class PropertyAmenity(db.Model):
    __tablename__ = 'property_amenities'
    id = db.Column(db.Integer, primary_key=True)
    property_id = db.Column(db.Integer, db.ForeignKey('properties.id'), nullable=False)
    name = db.Column(db.String(100), nullable=False)
    icon = db.Column(db.String(50), nullable=True)


class Inquiry(db.Model):
    __tablename__ = 'inquiries'
    id = db.Column(db.Integer, primary_key=True)
    property_id = db.Column(db.Integer, db.ForeignKey('properties.id'), nullable=True)
    name = db.Column(db.String(100), nullable=False)
    email = db.Column(db.String(120), nullable=False)
    phone = db.Column(db.String(20), nullable=True)
    message = db.Column(db.Text, nullable=False)
    source = db.Column(db.String(50), default='website')  # website, whatsapp, call
    is_read = db.Column(db.Boolean, default=False)
    reply = db.Column(db.Text, nullable=True)
    replied_at = db.Column(db.DateTime, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    ip_address = db.Column(db.String(45), nullable=True)


class Testimonial(db.Model):
    __tablename__ = 'testimonials'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    designation = db.Column(db.String(100), nullable=True)
    content = db.Column(db.Text, nullable=False)
    rating = db.Column(db.Integer, default=5)
    photo = db.Column(db.String(200), nullable=True)
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


class BlogPost(db.Model):
    __tablename__ = 'blog_posts'
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(200), nullable=False)
    slug = db.Column(db.String(220), unique=True, nullable=False)
    content = db.Column(db.Text, nullable=False)
    excerpt = db.Column(db.String(400), nullable=True)
    featured_image = db.Column(db.String(200), nullable=True)
    is_published = db.Column(db.Boolean, default=False)
    meta_title = db.Column(db.String(200), nullable=True)
    meta_description = db.Column(db.String(400), nullable=True)
    views = db.Column(db.Integer, default=0)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class ActivityLog(db.Model):
    __tablename__ = 'activity_logs'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    action = db.Column(db.String(200), nullable=False)
    details = db.Column(db.Text, nullable=True)
    ip_address = db.Column(db.String(45), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    user = db.relationship('User', backref='activity_logs')


class PageVisit(db.Model):
    __tablename__ = 'page_visits'
    id = db.Column(db.Integer, primary_key=True)
    page = db.Column(db.String(200), nullable=False)
    ip_address = db.Column(db.String(45), nullable=True)
    user_agent = db.Column(db.String(300), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


class FAQ(db.Model):
    __tablename__ = 'faqs'
    id = db.Column(db.Integer, primary_key=True)
    question = db.Column(db.String(300), nullable=False)
    answer = db.Column(db.Text, nullable=False)
    sort_order = db.Column(db.Integer, default=0)
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


class ExternalLink(db.Model):
    """Developer-managed external links integrated into the site"""
    __tablename__ = 'external_links'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    url = db.Column(db.String(500), nullable=False)
    link_type = db.Column(db.String(50), nullable=False)  # header_nav, footer, social, iframe, redirect, custom_page
    description = db.Column(db.String(300), nullable=True)
    open_in = db.Column(db.String(20), default='_blank')  # _blank, _self, iframe
    sort_order = db.Column(db.Integer, default=0)
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


class Task(db.Model):
    """Owner to-do / task list widget"""
    __tablename__ = 'tasks'
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(300), nullable=False)
    is_done = db.Column(db.Boolean, default=False)
    priority = db.Column(db.String(10), default='normal')  # low, normal, high
    due_date = db.Column(db.Date, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


class Note(db.Model):
    """Quick sticky notes for owner dashboard"""
    __tablename__ = 'notes'
    id = db.Column(db.Integer, primary_key=True)
    content = db.Column(db.Text, nullable=False)
    color = db.Column(db.String(20), default='yellow')
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


class PropertyNote(db.Model):
    """Private owner notes attached to a property (not shown publicly)"""
    __tablename__ = 'property_notes'
    id = db.Column(db.Integer, primary_key=True)
    property_id = db.Column(db.Integer, db.ForeignKey('properties.id'), nullable=False)
    content = db.Column(db.Text, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    property = db.relationship('Property', backref='notes')
