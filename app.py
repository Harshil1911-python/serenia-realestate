import os, uuid, csv, io, json, zipfile, shutil, re, hashlib
from datetime import datetime, timedelta, date
from functools import wraps
from flask import (Flask, render_template, redirect, url_for, flash,
                   request, jsonify, send_file, abort, session, Response, send_from_directory)
from flask_login import LoginManager, login_user, logout_user, login_required, current_user
from flask_migrate import Migrate
from flask_wtf.csrf import CSRFProtect, generate_csrf
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from werkzeug.utils import secure_filename
from slugify import slugify
from PIL import Image
from dotenv import load_dotenv
import bleach

load_dotenv()

from models import (db, User, Property, PropertyImage, PropertyVideo, PropertyAmenity,
                     Inquiry, Testimonial, BlogPost, ActivityLog, PageVisit, SiteSettings,
                     FAQ, ExternalLink, Task, Note, PropertyNote)

app = Flask(__name__)

# ── CONFIG ──────────────────────────────────────────────────────────
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'luxerealty-secret-key-change-in-prod-2025')
db_url = os.environ.get('DATABASE_URL', 'sqlite:///realestate.db')
if db_url.startswith('postgres://'):
    db_url = db_url.replace('postgres://', 'postgresql://', 1)
app.config['SQLALCHEMY_DATABASE_URI'] = db_url
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['UPLOAD_FOLDER'] = os.path.join('static', 'uploads')
app.config['MAX_CONTENT_LENGTH'] = 52 * 1024 * 1024
app.config['WTF_CSRF_ENABLED'] = True
app.config['WTF_CSRF_TIME_LIMIT'] = None  # no expiry

IS_SQLITE = db_url.startswith('sqlite')
if IS_SQLITE:
    # Increase busy timeout so concurrent gunicorn workers wait instead of
    # immediately raising "database is locked" errors.
    app.config['SQLALCHEMY_ENGINE_OPTIONS'] = {
        'connect_args': {'timeout': 30}
    }

ALLOWED_IMG = {'jpg','jpeg','png','webp','gif'}
ALLOWED_VIDEO = {'mp4','mov','webm'}
ALLOWED_ALL = {'jpg','jpeg','png','webp','gif','mp4','mov','webm','pdf','docx'}

def youtube_embed_url(url):
    """Convert a YouTube/Vimeo URL to an embeddable URL"""
    if not url: return ''
    url = url.strip()
    yt = re.search(r'(?:youtube\.com/watch\?v=|youtu\.be/|youtube\.com/embed/|youtube\.com/shorts/)([A-Za-z0-9_-]{6,})', url)
    if yt:
        return f"https://www.youtube.com/embed/{yt.group(1)}"
    vm = re.search(r'vimeo\.com/(\d+)', url)
    if vm:
        return f"https://player.vimeo.com/video/{vm.group(1)}"
    if 'embed' in url:
        return url
    return url

# ── EXTENSIONS ──────────────────────────────────────────────────────
db.init_app(app)
migrate = Migrate(app, db)
csrf = CSRFProtect(app)
login_manager = LoginManager(app)
login_manager.login_view = 'login_redirect'
login_manager.login_message_category = 'info'
login_manager.login_message = 'Please log in to access this page.'

if IS_SQLITE:
    from sqlalchemy import event
    from sqlalchemy.engine import Engine

    @event.listens_for(Engine, "connect")
    def _set_sqlite_pragma(dbapi_connection, connection_record):
        """Enable WAL mode + busy timeout so multiple gunicorn workers can
        read/write the SQLite file concurrently without 'database is locked'
        errors causing broken sessions and intermittent 500/404/CSS issues."""
        cursor = dbapi_connection.cursor()
        try:
            cursor.execute("PRAGMA journal_mode=WAL")
            cursor.execute("PRAGMA busy_timeout=30000")
            cursor.execute("PRAGMA synchronous=NORMAL")
        finally:
            cursor.close()

@app.teardown_request
def _cleanup_session(exception=None):
    """Ensure any failed transaction is rolled back at the end of every
    request so the next request on this worker starts with a clean session."""
    if exception is not None:
        try:
            db.session.rollback()
        except Exception:
            pass
    db.session.remove()

limiter = Limiter(key_func=get_remote_address, app=app,
                  default_limits=["500 per day", "100 per hour"],
                  storage_uri="memory://")

for folder in ['properties','profiles','documents','blog','backups','videos']:
    os.makedirs(os.path.join(app.config['UPLOAD_FOLDER'], folder), exist_ok=True)

# ── HELPERS ─────────────────────────────────────────────────────────
@login_manager.user_loader
def load_user(uid): return User.query.get(int(uid))

def save_image(file, folder='properties', max_size=(1200,900)):
    if not file or not file.filename: return None
    ext = file.filename.rsplit('.',1)[-1].lower()
    if ext not in ALLOWED_IMG: return None
    fname = f"{uuid.uuid4().hex}.webp"
    path = os.path.join(app.config['UPLOAD_FOLDER'], folder, fname)
    try:
        img = Image.open(file).convert('RGB')
        img.thumbnail(max_size, Image.LANCZOS)
        img.save(path, 'WEBP', quality=85, optimize=True)
    except Exception:
        ext2 = secure_filename(file.filename).rsplit('.',1)[-1].lower()
        fname = f"{uuid.uuid4().hex}.{ext2}"
        path = os.path.join(app.config['UPLOAD_FOLDER'], folder, fname)
        file.seek(0); file.save(path)
    return fname

def save_video(file, folder='videos'):
    if not file or not file.filename: return None
    ext = file.filename.rsplit('.',1)[-1].lower()
    if ext not in ALLOWED_VIDEO: return None
    fname = f"{uuid.uuid4().hex}.{ext}"
    path = os.path.join(app.config['UPLOAD_FOLDER'], folder, fname)
    file.save(path)
    return fname

def log_activity(action, details=None):
    try:
        db.session.add(ActivityLog(
            user_id=current_user.id if current_user.is_authenticated else None,
            action=action, details=details, ip_address=request.remote_addr))
        db.session.commit()
    except Exception:
        db.session.rollback()

def owner_required(f):
    @wraps(f)
    def dec(*a,**k):
        if not current_user.is_authenticated or not current_user.is_owner(): abort(403)
        return f(*a,**k)
    return dec

def developer_required(f):
    @wraps(f)
    def dec(*a,**k):
        if not current_user.is_authenticated or not current_user.is_developer(): abort(403)
        return f(*a,**k)
    return dec

SETTING_DEFAULTS = {
    'site_name':'LuxeRealty','tagline':'Find Your Dream Property',
    'phone':'+91 98765 43210','whatsapp':'919876543210',
    'email':'info@luxerealty.com','address':'123 Business Hub, Mumbai, Maharashtra 400001',
    'facebook':'','instagram':'','twitter':'','linkedin':'','youtube':'',
    'hero_title':'Find Your Perfect Property',
    'hero_subtitle':'Discover luxury homes, commercial spaces and investment properties',
    'google_maps_embed':'','meta_title':'LuxeRealty - Premium Real Estate',
    'meta_description':'Find your dream property with LuxeRealty. Browse residential, commercial and luxury properties.',
    'favicon':'','logo':'','maintenance_mode':'false',
    'primary_color':'#1a56db','accent_color':'#f59e0b',
    'custom_css':'','custom_js':'',
    'smtp_host':'','smtp_port':'587','smtp_user':'','smtp_pass':'',
    'agent_name':'Your Name','agent_title':'Senior Real Estate Consultant',
    'agent_bio':'With over 10 years of experience in real estate, I help clients find their perfect property.',
    'agent_experience':'10+ Years','agent_certifications':'RERA Certified',
    'agent_languages':'English, Hindi, Gujarati','agent_whatsapp':'919876543210',
    'agent_photo':'',
    'map_lat':'19.0760','map_lng':'72.8777','map_zoom':'12',
    'admin_path':'admin','dev_path':'devcontrol',
}

def get_settings():
    rows = SiteSettings.query.all()
    s = dict(SETTING_DEFAULTS)
    for r in rows: s[r.key] = r.value
    return s

def set_settings(data: dict):
    for key, val in data.items():
        row = SiteSettings.query.filter_by(key=key).first()
        if row: row.value = val; row.updated_at = datetime.utcnow()
        else: db.session.add(SiteSettings(key=key, value=val))
    db.session.commit()

@app.context_processor
def inject_globals():
    try:
        s = get_settings()
        ext = ExternalLink.query.filter_by(is_active=True).order_by(ExternalLink.sort_order).all()
    except Exception:
        db.session.rollback()
        try:
            s = get_settings()
            ext = ExternalLink.query.filter_by(is_active=True).order_by(ExternalLink.sort_order).all()
        except Exception:
            db.session.rollback()
            s = dict(SETTING_DEFAULTS)
            ext = []
    return dict(
        settings=s, now=datetime.utcnow(),
        header_links=[l for l in ext if l.link_type=='header_nav'],
        footer_links=[l for l in ext if l.link_type=='footer'],
        social_links=[l for l in ext if l.link_type=='social'],
        csrf_token=generate_csrf,
    )

def track(page):
    try:
        db.session.add(PageVisit(page=page, ip_address=request.remote_addr,
                                  user_agent=(request.user_agent.string or '')[:300]))
        db.session.commit()
    except Exception:
        db.session.rollback()

def clean(s, tags=None):
    allowed = tags or []
    return bleach.clean(s or '', tags=allowed, strip=True)

# ── CURRENCY HELPERS ───────────────────────────────────────────────────

CURRENCY_SYMBOLS = {
    'INR': '₹', 'AED': 'AED', 'USD': '$', 'GBP': '£', 'EUR': '€',
    'SAR': 'SAR', 'QAR': 'QAR',
}

# Currencies that use the Indian lakh/crore short-form display.
# All others (AED, USD, etc.) display the full grouped number.
LAKH_CRORE_CURRENCIES = {'INR'}

def format_price_str(price, unit='total', currency='INR'):
    """Format a raw numeric price for display with the correct currency
    symbol/code. INR uses Lakh/Crore short-forms; other currencies (AED,
    USD, SAR, etc.) show the full grouped amount with their symbol/code."""
    if price is None:
        price = 0
    currency = (currency or 'INR').upper()
    symbol = CURRENCY_SYMBOLS.get(currency, currency)

    if currency in LAKH_CRORE_CURRENCIES:
        if price >= 10000000:
            txt = f"{symbol} {price/10000000:.2f} Cr"
        elif price >= 100000:
            txt = f"{symbol} {price/100000:.2f} Lakh"
        else:
            txt = f"{symbol} {price:,.0f}"
    else:
        # AED / USD / SAR / etc: show full amount with symbol/code prefix
        if symbol in ('$', '£', '€'):
            txt = f"{symbol}{price:,.0f}"
        else:
            txt = f"{symbol} {price:,.0f}"

    if unit == 'per_month': txt += " / month"
    elif unit == 'per_sqft': txt += " / sqft"
    return txt


def format_price_compact(price, currency='INR'):
    """Shorter form used on cards/markers — e.g. '₹1.2 Cr', 'AED 1.25M'."""
    if price is None:
        price = 0
    currency = (currency or 'INR').upper()
    symbol = CURRENCY_SYMBOLS.get(currency, currency)

    if currency in LAKH_CRORE_CURRENCIES:
        if price >= 10000000:
            return f"{symbol}{price/10000000:.1f}Cr"
        elif price >= 100000:
            return f"{symbol}{price/100000:.1f}L"
        return f"{symbol}{price:,.0f}"
    else:
        if price >= 1_000_000:
            val = f"{symbol}{price/1_000_000:.1f}M" if symbol in ('$','£','€') else f"{symbol} {price/1_000_000:.1f}M"
        else:
            val = f"{symbol}{price:,.0f}" if symbol in ('$','£','€') else f"{symbol} {price:,.0f}"
        return val


@app.template_filter('price')
def jinja_format_price(price, unit='total', currency='INR'):
    return format_price_str(price, unit, currency)


@app.template_filter('price_compact')
def jinja_format_price_compact(price, currency='INR'):
    return format_price_compact(price, currency)


@app.template_filter('currency_symbol')
def jinja_currency_symbol(currency):
    return CURRENCY_SYMBOLS.get((currency or 'INR').upper(), currency)

def generate_brochure_pdf(prop):
    """Auto-generate a professional PDF brochure for a property using reportlab"""
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.units import mm
    from reportlab.lib.colors import HexColor
    from reportlab.platypus import (SimpleDocTemplate, Paragraph, Spacer, Image as RLImage,
                                     Table, TableStyle, HRFlowable)
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.enums import TA_CENTER, TA_LEFT

    s = get_settings()
    primary = HexColor(s.get('primary_color','#1a56db'))

    fname = f"brochure_{prop.property_id}.pdf"
    path = os.path.join(app.config['UPLOAD_FOLDER'],'documents', fname)

    doc = SimpleDocTemplate(path, pagesize=A4,
                             topMargin=18*mm, bottomMargin=18*mm,
                             leftMargin=18*mm, rightMargin=18*mm)
    styles = getSampleStyleSheet()
    title_style = ParagraphStyle('TitleX', parent=styles['Title'], textColor=primary, fontSize=22, spaceAfter=4)
    h2 = ParagraphStyle('H2', parent=styles['Heading2'], textColor=primary, spaceBefore=14, spaceAfter=6)
    normal = styles['Normal']
    small = ParagraphStyle('Small', parent=styles['Normal'], fontSize=9, textColor=HexColor('#64748b'))
    price_style = ParagraphStyle('Price', parent=styles['Title'], textColor=primary, fontSize=20, alignment=TA_LEFT, spaceAfter=2)

    elements = []

    # Header - business name
    elements.append(Paragraph(s.get('site_name','Real Estate'), ParagraphStyle('Brand', parent=styles['Heading1'], textColor=primary, fontSize=16)))
    elements.append(Paragraph(s.get('tagline',''), small))
    elements.append(HRFlowable(width="100%", thickness=1, color=primary, spaceAfter=10, spaceBefore=6))

    # Title
    elements.append(Paragraph(prop.title, title_style))
    elements.append(Paragraph(f"Property ID: {prop.property_id}  |  {prop.property_type} · For {prop.listing_type.title()}", small))
    elements.append(Spacer(1, 8))

    # Main image
    if prop.images:
        try:
            img_path = os.path.join(app.config['UPLOAD_FOLDER'],'properties', prop.images[0].filename)
            if os.path.exists(img_path):
                img = RLImage(img_path, width=170*mm, height=95*mm)
                elements.append(img)
                elements.append(Spacer(1, 10))
        except Exception: pass

    # Price
    elements.append(Paragraph(format_price_str(prop.price, prop.price_unit, prop.currency), price_style))
    elements.append(Spacer(1, 8))

    # Key details table
    rows = []
    rows.append(['Location', f"{prop.city or ''}{', ' + prop.state if prop.state else ''}"])
    if prop.area: rows.append(['Area', f"{prop.area:.0f} {prop.area_unit}"])
    if prop.bedrooms: rows.append(['Bedrooms', str(prop.bedrooms)])
    if prop.bathrooms: rows.append(['Bathrooms', str(prop.bathrooms)])
    if prop.parking: rows.append(['Parking', str(prop.parking)])
    if prop.furnishing: rows.append(['Furnishing', prop.furnishing.title()])
    if prop.property_age: rows.append(['Property Age', prop.property_age])
    rows.append(['Status', prop.status.replace('_',' ').title()])

    table = Table(rows, colWidths=[45*mm, 120*mm])
    table.setStyle(TableStyle([
        ('FONTSIZE',(0,0),(-1,-1),10),
        ('TEXTCOLOR',(0,0),(0,-1), HexColor('#64748b')),
        ('FONTNAME',(0,0),(0,-1),'Helvetica-Bold'),
        ('BOTTOMPADDING',(0,0),(-1,-1),5),
        ('TOPPADDING',(0,0),(-1,-1),5),
        ('LINEBELOW',(0,0),(-1,-1),0.5,HexColor('#e2e8f0')),
    ]))
    elements.append(table)
    elements.append(Spacer(1, 10))

    # Description
    if prop.description:
        elements.append(Paragraph('About this Property', h2))
        desc_text = bleach.clean(prop.description, tags=[], strip=True)
        elements.append(Paragraph(desc_text[:1200], normal))

    # Amenities
    if prop.amenities:
        elements.append(Paragraph('Amenities', h2))
        amenity_text = '  •  '.join([a.name for a in prop.amenities])
        elements.append(Paragraph(amenity_text, normal))

    # Address
    if prop.address:
        elements.append(Paragraph('Address', h2))
        elements.append(Paragraph(prop.address, normal))

    # Map snapshot link
    if prop.latitude and prop.longitude:
        elements.append(Spacer(1, 6))
        elements.append(Paragraph(f"Location Coordinates: {prop.latitude}, {prop.longitude}", small))
        elements.append(Paragraph(f"View on map: https://www.openstreetmap.org/?mlat={prop.latitude}&mlon={prop.longitude}#map=16/{prop.latitude}/{prop.longitude}", small))

    elements.append(Spacer(1, 16))
    elements.append(HRFlowable(width="100%", thickness=1, color=HexColor('#e2e8f0'), spaceAfter=8))

    # Contact footer
    elements.append(Paragraph('Contact Us', h2))
    contact_rows = [
        ['Agent', s.get('agent_name','')],
        ['Phone', s.get('phone','')],
        ['WhatsApp', '+' + s.get('whatsapp','')],
        ['Email', s.get('email','')],
        ['Address', s.get('address','')],
    ]
    ctable = Table(contact_rows, colWidths=[35*mm, 130*mm])
    ctable.setStyle(TableStyle([
        ('FONTSIZE',(0,0),(-1,-1),10),
        ('TEXTCOLOR',(0,0),(0,-1), HexColor('#64748b')),
        ('FONTNAME',(0,0),(0,-1),'Helvetica-Bold'),
        ('BOTTOMPADDING',(0,0),(-1,-1),4),
    ]))
    elements.append(ctable)

    doc.build(elements)
    return fname


# ── BROCHURE AUTO-FILL EXTRACTION ─────────────────────────────────────

# Fields tracked for the green/red "extraction status" dots in the UI
BROCHURE_TRACKED_FIELDS = [
    'title', 'bedrooms', 'price', 'currency', 'area', 'area_unit', 'address', 'city',
    'pincode', 'property_age', 'amenities', 'rera_number', 'developer',
    'contact', 'email', 'website', 'description',
]

# Limits applied when processing large brochure PDFs so a huge file
# (50+ pages, lots of embedded images) cannot hang or crash a worker.
BROCHURE_MAX_PAGES_TEXT = 25       # max pages to run text extraction on
BROCHURE_MAX_PAGES_IMAGES = 30     # max pages to scan for images
BROCHURE_MAX_TIME_SECONDS = 45     # hard wall-clock budget for the whole extraction
BROCHURE_MAX_TEXT_CHARS = 400_000  # cap collected text to avoid huge regex scans

INDIAN_CITIES = [
    'Mumbai','Navi Mumbai','Thane','Pune','Bengaluru','Bangalore','Delhi','New Delhi',
    'Gurugram','Gurgaon','Noida','Greater Noida','Hyderabad','Chennai','Kolkata',
    'Ahmedabad','Surat','Vadodara','Rajkot','Jaipur','Lucknow','Kanpur','Nagpur',
    'Indore','Bhopal','Coimbatore','Kochi','Cochin','Visakhapatnam','Chandigarh',
    'Faridabad','Ghaziabad','Patna','Vapi','Vasai','Mira Road','Kalyan',
]

UAE_CITIES = [
    'Dubai','Abu Dhabi','Sharjah','Ajman','Ras Al Khaimah','Ras Al-Khaimah',
    'Fujairah','Umm Al Quwain','Umm Al-Quwain', 'Al Ain',
]

OTHER_CITIES = [
    'Doha','Riyadh','Jeddah','Manama','Muscat','Kuwait City','London',
    'New York','Singapore','Toronto','Dubai Marina','Business Bay',
    'Downtown Dubai','Jumeirah','JVC','JLT','Palm Jumeirah',
]

ALL_CITIES = INDIAN_CITIES + UAE_CITIES + OTHER_CITIES

# Currency symbol/keyword -> ISO code, and the "lakh/crore" style multiplier
# words that apply to each currency (Indian-style units only apply to INR;
# AED/USD/etc. brochures normally state the full number directly).
CURRENCY_PATTERNS = [
    # (regex for symbol/code, ISO code, supports lakh/crore words)
    (r'AED|Dhs?\.?|د\.إ', 'AED', False),
    (r'USD|US\$|\$', 'USD', False),
    (r'SAR|SR\b', 'SAR', False),
    (r'QAR', 'QAR', False),
    (r'GBP|£', 'GBP', False),
    (r'EUR|€', 'EUR', False),
    (r'₹|Rs\.?|INR', 'INR', True),
]

# Multiplier words for "lakh/crore" style numbers (used for INR, and also
# harmlessly checked for other currencies in case a brochure mixes styles)
MULTIPLIER_WORDS = r'(Crores?|Cr\.?|Lakhs?|Lacs?|L\.?|Million|Mn|M\b|Thousand|K\b)'


def _apply_multiplier(num, word):
    word = (word or '').strip().lower()
    if word.startswith('cr'):
        return num * 10_000_000
    if word.startswith('l'):
        return num * 100_000
    if word.startswith('m'):
        return num * 1_000_000
    if word.startswith('k') or word.startswith('th'):
        return num * 1_000
    return num


def _price_to_number(value, unit):
    """Convert a price string + optional multiplier word to a raw number."""
    try:
        num = float(value.replace(',', '').strip())
    except (ValueError, AttributeError):
        return None
    return _apply_multiplier(num, unit)


def extract_brochure_text_data(text):
    """Run smart regex extraction over raw brochure text and return a dict
    of auto-filled property fields. Missing fields are simply absent."""
    data = {}
    if not text:
        return data

    # Cap text length so regex scans on huge brochures stay fast.
    if len(text) > BROCHURE_MAX_TEXT_CHARS:
        text = text[:BROCHURE_MAX_TEXT_CHARS]

    clean_text = text.replace('\r', '\n')
    # Collapse excessive blank lines (common in PDF text dumps) but keep
    # paragraph breaks for the description/amenities heuristics below.
    clean_text = re.sub(r'\n{3,}', '\n\n', clean_text)

    # ── BHK / Bedrooms ──
    m = re.search(r'(\d+(?:\.\d+)?)\s*[- ]?\s*BHK', clean_text, re.I)
    if m:
        try:
            data['bedrooms'] = int(float(m.group(1)))
        except ValueError:
            pass
    else:
        # "Studio" / "1 Bedroom" / "2 Bedrooms" style (common in AED/Gulf brochures)
        m = re.search(r'\bStudio\b', clean_text, re.I)
        if m:
            data['bedrooms'] = 0
        else:
            m = re.search(r'(\d+)\s*[- ]?\s*Bed(?:room)?s?\b', clean_text, re.I)
            if m:
                try:
                    data['bedrooms'] = int(m.group(1))
                except ValueError:
                    pass

    # ── Price (multi-currency: ₹/Rs/INR, AED/Dhs, USD/$, SAR, QAR, GBP, EUR) ──
    price_found = False
    for sym_pattern, code, supports_multiplier in CURRENCY_PATTERNS:
        if supports_multiplier:
            # e.g. "₹ 85 Lakhs", "Rs. 1.25 Cr", "INR 45 Lacs"
            m = re.search(
                rf'(?:{sym_pattern})\s*([\d,]+(?:\.\d+)?)\s*{MULTIPLIER_WORDS}\b',
                clean_text, re.I)
            if m:
                price = _price_to_number(m.group(1), m.group(2))
                if price:
                    data['price'] = price
                    data['price_unit'] = 'total'
                    data['currency'] = code
                    price_found = True
                    break
        # Plain "AED 1,250,000" / "USD 350,000" / "$ 1,200,000" style
        m = re.search(
            rf'(?:{sym_pattern})\s*([\d,]{{4,}}(?:\.\d+)?)\b',
            clean_text)
        if m:
            try:
                price = float(m.group(1).replace(',', ''))
            except ValueError:
                price = None
            if price and price >= 1000:
                data['price'] = price
                data['price_unit'] = 'total'
                data['currency'] = code
                price_found = True
                break

    if not price_found:
        # Fallback: bare lakh/crore figure with no visible currency symbol
        # (assume INR, the most common case for these terms)
        m = re.search(rf'([\d,]+(?:\.\d+)?)\s*{MULTIPLIER_WORDS}\b', clean_text, re.I)
        if m:
            price = _price_to_number(m.group(1), m.group(2))
            if price:
                data['price'] = price
                data['price_unit'] = 'total'
                data['currency'] = 'INR'

    # ── RERA Number (India) or DLD/Permit Number (UAE) ──
    m = re.search(
        r'RERA\s*(?:Reg(?:istration)?\.?\s*)?(?:No\.?|Number|ID)?\s*[:\-]?\s*'
        r'([A-Z0-9][A-Z0-9\/\-]{5,30})',
        clean_text, re.I)
    if m:
        data['rera_number'] = m.group(1).strip()
    else:
        m = re.search(
            r'(?:DLD|Permit|Trakheesi)\s*(?:No\.?|Number)?\s*[:\-]?\s*'
            r'([A-Z0-9][A-Z0-9\/\-]{5,30})',
            clean_text, re.I)
        if m:
            data['rera_number'] = m.group(1).strip()

    # ── Carpet / Built-up / Super Built-up / Saleable Area ──
    m = re.search(
        r'(Carpet|Built[\s\-]?up|Super\s*Built[\s\-]?up|Saleable|Plot|Gross|Net)\s*Area\s*'
        r'(?:\(.*?\))?\s*[:\-]?\s*'
        r'([\d,]+(?:\.\d+)?)\s*(sq\.?\s?ft\.?|sqft|sft|ft²|sq\.?\s?m(?:t|tr|eter)?s?\.?|sqm|m²)',
        clean_text, re.I)
    if m:
        try:
            data['area'] = float(m.group(2).replace(',', ''))
            unit_str = m.group(3).lower()
            data['area_unit'] = 'sqm' if ('m' in unit_str and 'sq' in unit_str) or '²' in unit_str and 'f' not in unit_str else ('sqm' if 'm' in unit_str else 'sqft')
        except ValueError:
            pass
    else:
        # Generic "Area: 1,200 sq ft" / "Size: 85 sqm" without a Carpet/Built-up prefix
        m = re.search(
            r'(?:Area|Size)\s*[:\-]?\s*([\d,]+(?:\.\d+)?)\s*'
            r'(sq\.?\s?ft\.?|sqft|sft|ft²|sq\.?\s?m(?:t|tr|eter)?s?\.?|sqm|m²)',
            clean_text, re.I)
        if m:
            try:
                data['area'] = float(m.group(1).replace(',', ''))
                unit_str = m.group(2).lower()
                data['area_unit'] = 'sqm' if 'm' in unit_str else 'sqft'
            except ValueError:
                pass

    # ── Possession / Handover Date ──
    m = re.search(
        r'(?:Possession|Handover)\s*(?:Date|By|in|On|:)*\s*[:\-]?\s*'
        r'((?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\.?\s*[\'’]?\s*\d{2,4}'
        r'|\d{1,2}[\/\-]\d{1,2}[\/\-]\d{2,4}|Q[1-4]\s*\d{4}|\d{4})',
        clean_text, re.I)
    if m:
        data['property_age'] = 'Possession: ' + m.group(1).strip()

    # ── Developer / Builder Name ──
    m = re.search(
        r'(?:Developed\s*By|Developer|Builder|Promoter|A\s*Project\s*[Bb]y)\s*[:\-]?\s*'
        r'([A-Za-z0-9&.,\'\-\s]{3,60})',
        clean_text, re.I)
    if m:
        dev = m.group(1).strip().split('\n')[0].strip(' .,-')
        if len(dev) > 2:
            data['developer'] = dev

    # ── Email ──
    m = re.search(r'[\w.\-]+@[\w\-]+\.[\w.\-]+', clean_text)
    if m:
        data['email'] = m.group(0).rstrip('.')

    # ── Website ──
    m = re.search(r'(?:https?://)?(?:www\.)[\w\-]+\.[a-z]{2,}(?:/[^\s,]*)?', clean_text, re.I)
    if m:
        data['website'] = m.group(0).rstrip('.,')

    # ── Contact Phone (India +91, UAE +971, generic international) ──
    m = re.search(r'(?:\+?91[\-\s]?)?[6-9]\d{9}\b', clean_text)
    if m:
        data['contact'] = m.group(0)
    else:
        m = re.search(r'(?:\+?971[\-\s]?)?(?:0)?5\d[\-\s]?\d{3}[\-\s]?\d{4}\b', clean_text)
        if m:
            data['contact'] = m.group(0)
        else:
            # Generic international number with country code, 8-15 digits
            m = re.search(r'\+\d{1,3}[\-\s]?\d[\d\-\s]{6,13}\d', clean_text)
            if m:
                data['contact'] = m.group(0).strip()

    # ── Pincode / Postal Code (India 6-digit; skipped for UAE - no postal codes) ──
    m = re.search(r'\b(\d{6})\b', clean_text)
    if m:
        data['pincode'] = m.group(1)

    # ── City (match known city list across India / UAE / GCC / global hubs) ──
    for c in ALL_CITIES:
        if re.search(r'\b' + re.escape(c) + r'\b', clean_text, re.I):
            data['city'] = c
            break

    # ── Address / Location ──
    m = re.search(r'(?:Location|Address|Site\s*Address)\s*[:\-]\s*(.+)', clean_text, re.I)
    if m:
        addr = m.group(1).strip().split('\n')[0].strip()
        if len(addr) > 4:
            data['address'] = addr

    # ── Amenities (look for "Amenities"/"Facilities"/"Features" section header) ──
    m = re.search(
        r'(?:Amenities|Facilities|Features|Specifications)\s*[:\-]?\s*\n(.*?)(?:\n\s*\n|\Z)',
        clean_text, re.I | re.S)
    if m:
        block = m.group(1)
        items = re.split(r'[•▪●○\-\*\u2022\n,]', block)
        amenities = []
        for item in items:
            item = item.strip(' .')
            if 2 < len(item) < 40 and not re.search(r'\d{4,}', item):
                amenities.append(item)
        if amenities:
            data['amenities'] = amenities[:15]

    # ── Title (first reasonable standalone line, skip headers/contacts) ──
    skip_words = ('rera', 'amenities', 'facilities', 'possession', 'handover',
                   'location', 'address', 'price', 'carpet', 'built', 'developer',
                   'contact', 'email', 'dld', 'permit')
    for line in clean_text.split('\n'):
        line = line.strip()
        if (10 < len(line) < 80
                and not re.search(r'@|http|www|\d{10}|\d{6}', line)
                and not any(w in line.lower() for w in skip_words)):
            data['title'] = line
            break

    # ── Description: use first dense paragraph as fallback description ──
    paragraphs = [p.strip() for p in clean_text.split('\n\n') if len(p.strip()) > 80]
    if paragraphs:
        data['description'] = paragraphs[0][:1000]

    return data


def extract_brochure_images(pdf_path, dest_folder, max_images=12, min_dim=200,
                             max_pages=None, deadline=None):
    """Extract embedded images from a PDF using PyMuPDF, dedupe, filter out
    tiny icons/logos, convert to WEBP and save into dest_folder.

    Safe for large PDFs:
    - Only scans up to `max_pages` pages (default BROCHURE_MAX_PAGES_IMAGES)
    - Stops early once `deadline` (a time.monotonic() value) is passed
    - Skips absurdly large embedded images that could blow up memory

    Returns a list of saved filenames.
    """
    import fitz  # PyMuPDF
    import time

    if max_pages is None:
        max_pages = BROCHURE_MAX_PAGES_IMAGES

    MAX_RAW_IMAGE_BYTES = 15 * 1024 * 1024  # skip individual images >15MB raw

    saved = []
    seen_hashes = set()
    try:
        doc = fitz.open(pdf_path)
    except Exception:
        return saved

    try:
        page_count = min(len(doc), max_pages)
        for page_index in range(page_count):
            if len(saved) >= max_images:
                break
            if deadline is not None and time.monotonic() > deadline:
                break

            try:
                page_images = doc.get_page_images(page_index)
            except Exception:
                continue

            for img in page_images:
                if len(saved) >= max_images:
                    break
                if deadline is not None and time.monotonic() > deadline:
                    break

                xref = img[0]
                try:
                    base = doc.extract_image(xref)
                except Exception:
                    continue

                image_bytes = base.get('image')
                width, height = base.get('width', 0), base.get('height', 0)
                if not image_bytes:
                    continue
                if width < min_dim or height < min_dim:
                    continue
                if len(image_bytes) > MAX_RAW_IMAGE_BYTES:
                    continue

                h = hashlib.md5(image_bytes).hexdigest()
                if h in seen_hashes:
                    continue
                seen_hashes.add(h)

                fname = f"brochure_{uuid.uuid4().hex}.webp"
                path = os.path.join(dest_folder, fname)
                try:
                    img_pil = Image.open(io.BytesIO(image_bytes)).convert('RGB')
                    img_pil.thumbnail((1200, 900), Image.LANCZOS)
                    img_pil.save(path, 'WEBP', quality=85, optimize=True)
                except Exception:
                    ext = base.get('ext', 'png')
                    fname = f"brochure_{uuid.uuid4().hex}.{ext}"
                    path = os.path.join(dest_folder, fname)
                    try:
                        with open(path, 'wb') as f:
                            f.write(image_bytes)
                    except Exception:
                        continue
                saved.append(fname)
    finally:
        doc.close()

    return saved


def extract_brochure_tables_text(pdf_path, max_pages=None, deadline=None):
    """Extract text from tables in a PDF (common in larger/denser brochures
    for specification sheets, amenities lists, payment plans, etc.) and
    flatten it into plain text lines so the regex extractor can pick up
    fields that live inside tables rather than free-flowing text.

    Safe for large PDFs via max_pages / deadline limits.
    """
    import time
    if max_pages is None:
        max_pages = BROCHURE_MAX_PAGES_TEXT

    lines = []
    try:
        import pdfplumber
        with pdfplumber.open(pdf_path) as pdf:
            page_count = min(len(pdf.pages), max_pages)
            for page in pdf.pages[:page_count]:
                if deadline is not None and time.monotonic() > deadline:
                    break
                try:
                    tables = page.extract_tables()
                except Exception:
                    tables = []
                for table in tables:
                    for row in table:
                        cells = [str(c).strip() for c in row if c]
                        if cells:
                            lines.append('  '.join(cells))
    except Exception:
        pass

    return '\n'.join(lines)



# ── PUBLIC ROUTES ────────────────────────────────────────────────────

@app.route('/favicon.ico')
def favicon():
    s = get_settings()
    if s.get('favicon'):
        return redirect(url_for('static', filename='uploads/profiles/' + s['favicon']))
    return ('', 204)

@app.route('/')
def index():
    track('home')
    s = get_settings()
    if s.get('maintenance_mode')=='true' and not (current_user.is_authenticated and current_user.is_developer()):
        return render_template('public/maintenance.html')
    featured = Property.query.filter_by(is_featured=True).order_by(Property.created_at.desc()).limit(6).all()
    latest = Property.query.order_by(Property.created_at.desc()).limit(8).all()
    testimonials = Testimonial.query.filter_by(is_active=True).order_by(Testimonial.created_at.desc()).limit(6).all()
    faqs = FAQ.query.filter_by(is_active=True).order_by(FAQ.sort_order).limit(6).all()
    return render_template('public/index.html', featured=featured, latest=latest,
                           testimonials=testimonials, faqs=faqs,
                           prop_types=['Apartment','Villa','Office','Shop','Land','Warehouse'])

@app.route('/properties')
def properties():
    track('properties')
    page = request.args.get('page',1,type=int)
    q = Property.query
    for arg,col in [('type',Property.property_type),('listing',Property.listing_type),
                    ('city',Property.city),('furnishing',Property.furnishing)]:
        v = request.args.get(arg,'')
        if v: q = q.filter(col.ilike(f'%{v}%') if arg in ('type','city') else col==v)
    if request.args.get('bedrooms',type=int): q=q.filter(Property.bedrooms>=request.args.get('bedrooms',type=int))
    if request.args.get('min_price',type=float): q=q.filter(Property.price>=request.args.get('min_price',type=float))
    if request.args.get('max_price',type=float): q=q.filter(Property.price<=request.args.get('max_price',type=float))
    search = request.args.get('q','')
    if search:
        q = q.filter((Property.title.ilike(f'%{search}%'))|(Property.city.ilike(f'%{search}%'))|(Property.address.ilike(f'%{search}%')))
    status = request.args.get('status','')
    if status: q = q.filter(Property.status==status)
    props = q.order_by(Property.created_at.desc()).paginate(page=page,per_page=12,error_out=False)
    cities = [c[0] for c in db.session.query(Property.city).distinct().filter(Property.city.isnot(None)).all() if c[0]]
    all_props_geo = q.filter(Property.latitude.isnot(None), Property.longitude.isnot(None)).limit(200).all()
    geo_data = [{'id':p.id,'title':p.title,'lat':p.latitude,'lng':p.longitude,
                 'price':p.price,'currency':p.currency or 'INR',
                 'price_label': format_price_compact(p.price, p.currency),
                 'type':p.property_type,'status':p.status,
                 'img': (url_for('static',filename='uploads/properties/'+p.images[0].filename) if p.images else ''),
                 'url': url_for('property_detail',slug=p.slug)} for p in all_props_geo]
    return render_template('public/properties.html', props=props, cities=cities,
                           geo_data=json.dumps(geo_data),
                           prop_types=['Apartment','Villa','Office','Shop','Land','Warehouse','Residential','Commercial','Industrial','Agricultural'])

@app.route('/property/<slug>')
def property_detail(slug):
    prop = Property.query.filter_by(slug=slug).first_or_404()
    prop.views += 1; db.session.commit()
    track(f'property/{slug}')
    similar = Property.query.filter(Property.property_type==prop.property_type,
                                    Property.id!=prop.id,Property.status=='available').limit(4).all()
    return render_template('public/property_detail.html', prop=prop, similar=similar)

@app.route('/about')
def about():
    track('about')
    return render_template('public/about.html')

@app.route('/contact', methods=['GET','POST'])
@limiter.limit("15 per hour")
def contact():
    if request.method=='POST':
        name=clean(request.form.get('name',''))
        email=clean(request.form.get('email',''))
        phone=clean(request.form.get('phone',''))
        subject=clean(request.form.get('subject','General Inquiry'))
        message=clean(request.form.get('message',''))
        if name and email and message:
            db.session.add(Inquiry(name=name,email=email,phone=phone,
                                   message=message,source=subject,ip_address=request.remote_addr))
            db.session.commit()
            flash('✅ Message sent! We\'ll get back to you soon.','success')
        else:
            flash('Please fill all required fields.','danger')
        return redirect(url_for('contact'))
    track('contact')
    return render_template('public/contact.html')

@app.route('/inquiry', methods=['POST'])
@limiter.limit("10 per hour")
def submit_inquiry():
    name=clean(request.form.get('name',''))
    email=clean(request.form.get('email',''))
    phone=clean(request.form.get('phone',''))
    message=clean(request.form.get('message',''))
    property_id=request.form.get('property_id',type=int)
    if name and email and message:
        db.session.add(Inquiry(name=name,email=email,phone=phone,message=message,
                               property_id=property_id,ip_address=request.remote_addr))
        db.session.commit()
        return jsonify({'success':True,'message':'Inquiry submitted! We will contact you soon.'})
    return jsonify({'success':False,'message':'Please fill all required fields.'})

@app.route('/blog')
def blog():
    page=request.args.get('page',1,type=int)
    posts=BlogPost.query.filter_by(is_published=True).order_by(BlogPost.created_at.desc()).paginate(page=page,per_page=9,error_out=False)
    return render_template('public/blog.html',posts=posts)

@app.route('/blog/<slug>')
def blog_detail(slug):
    post=BlogPost.query.filter_by(slug=slug,is_published=True).first_or_404()
    post.views+=1; db.session.commit()
    return render_template('public/blog_detail.html',post=post)

@app.route('/page/<name>')
def custom_page(name):
    link=ExternalLink.query.filter_by(is_active=True).filter(ExternalLink.name.ilike(name)).first()
    if not link: abort(404)
    return render_template('public/iframe_page.html',link=link)

# ── AUTH ─────────────────────────────────────────────────────────────

def get_login_paths():
    s = get_settings()
    return s.get('admin_path','admin'), s.get('dev_path','devcontrol')

@app.route('/<path:login_path>/login', methods=['GET','POST'])
@limiter.limit("10 per 15minute")
def login(login_path):
    admin_p, dev_p = get_login_paths()
    if login_path not in (admin_p, dev_p): abort(404)
    is_dev_path = (login_path == dev_p)
    if current_user.is_authenticated:
        return redirect(url_for('developer_dashboard') if current_user.is_developer() else url_for('owner_dashboard'))
    if request.method=='POST':
        username=request.form.get('username','').strip()
        password=request.form.get('password','')
        user=User.query.filter((User.username==username)|(User.email==username)).first()
        if user and user.locked_until and user.locked_until > datetime.utcnow():
            flash(f'Account locked until {user.locked_until.strftime("%H:%M")}','danger')
            return render_template('public/login.html', login_path=login_path)
        if user and user.check_password(password) and user.is_active:
            if is_dev_path and not user.is_developer():
                flash('Access denied for this login portal.','danger')
                return render_template('public/login.html', login_path=login_path)
            user.failed_logins=0; user.last_login=datetime.utcnow(); db.session.commit()
            login_user(user)
            log_activity('Login', f'{user.username} via /{login_path}/login')
            return redirect(url_for('developer_dashboard') if user.is_developer() else url_for('owner_dashboard'))
        else:
            if user:
                user.failed_logins=(user.failed_logins or 0)+1
                if user.failed_logins>=5:
                    user.locked_until=datetime.utcnow()+timedelta(minutes=30)
                    flash('Account locked for 30 minutes.','danger')
                else:
                    flash(f'Invalid credentials. {5-user.failed_logins} attempts left.','danger')
                db.session.commit()
            else:
                flash('Invalid credentials.','danger')
    return render_template('public/login.html', login_path=login_path)

@app.route('/logout')
@login_required
def logout():
    log_activity('Logout')
    logout_user()
    flash('Logged out.','info')
    return redirect(url_for('index'))

# ── OWNER DASHBOARD ──────────────────────────────────────────────────

@app.route('/owner')
@login_required
@owner_required
def owner_dashboard():
    total_props=Property.query.count()
    total_inqs=Inquiry.query.count()
    unread=Inquiry.query.filter_by(is_read=False).count()
    today=datetime.utcnow().date()
    today_v=PageVisit.query.filter(db.func.date(PageVisit.created_at)==today).count()
    month_v=PageVisit.query.filter(PageVisit.created_at>=today.replace(day=1)).count()
    top_props=Property.query.order_by(Property.views.desc()).limit(5).all()
    recent_inqs=Inquiry.query.order_by(Inquiry.created_at.desc()).limit(5).all()
    available_count=Property.query.filter_by(status='available').count()
    sold_count=Property.query.filter_by(status='sold').count()
    rented_count=Property.query.filter_by(status='rented').count()
    negotiation_count=Property.query.filter_by(status='under_negotiation').count()
    tasks=Task.query.order_by(Task.is_done, Task.due_date.asc().nullslast(), Task.created_at.desc()).limit(8).all()
    notes=Note.query.order_by(Note.created_at.desc()).limit(6).all()
    pending_tasks=Task.query.filter_by(is_done=False).count()
    return render_template('owner/dashboard.html',total_props=total_props,total_inqs=total_inqs,
                           unread=unread,today_v=today_v,month_v=month_v,
                           top_props=top_props,recent_inqs=recent_inqs,
                           available_count=available_count,sold_count=sold_count,
                           rented_count=rented_count,negotiation_count=negotiation_count,
                           tasks=tasks,notes=notes,pending_tasks=pending_tasks)

@app.route('/owner/tasks', methods=['POST'])
@login_required
@owner_required
def manage_tasks():
    action=request.form.get('action')
    if action=='add':
        title=clean(request.form.get('title',''))
        due=request.form.get('due_date','')
        due_date=None
        if due:
            try: due_date=datetime.strptime(due,'%Y-%m-%d').date()
            except Exception: pass
        if title:
            db.session.add(Task(title=title,priority=request.form.get('priority','normal'),due_date=due_date))
            db.session.commit()
    elif action=='toggle':
        t=Task.query.get(request.form.get('id',type=int))
        if t: t.is_done=not t.is_done; db.session.commit()
    elif action=='delete':
        t=Task.query.get(request.form.get('id',type=int))
        if t: db.session.delete(t); db.session.commit()
    return redirect(url_for('owner_dashboard'))

@app.route('/owner/notes', methods=['POST'])
@login_required
@owner_required
def manage_notes():
    action=request.form.get('action')
    if action=='add':
        content=clean(request.form.get('content',''))
        if content:
            db.session.add(Note(content=content,color=request.form.get('color','yellow')))
            db.session.commit()
    elif action=='delete':
        n=Note.query.get(request.form.get('id',type=int))
        if n: db.session.delete(n); db.session.commit()
    return redirect(url_for('owner_dashboard'))

@app.route('/owner/properties')
@login_required
@owner_required
def owner_properties():
    page=request.args.get('page',1,type=int)
    props=Property.query.order_by(Property.created_at.desc()).paginate(page=page,per_page=20,error_out=False)
    return render_template('owner/properties.html',props=props)

@app.route('/owner/upload-brochure', methods=['POST'])
@login_required
@owner_required
def upload_brochure_extract():
    """Accept a brochure PDF, extract text + embedded images, and return
    auto-fill data as JSON for the property form to consume via fetch().

    Designed to handle large brochure PDFs (many pages / high-res images)
    without hanging a worker: page counts are capped, a wall-clock deadline
    is enforced across the whole extraction, and oversized embedded images
    are skipped rather than loaded fully into memory.
    """
    import time

    file = request.files.get('brochure_pdf')
    if not file or not file.filename:
        return jsonify({'success': False, 'message': 'No file uploaded.'})
    if not file.filename.lower().endswith('.pdf'):
        return jsonify({'success': False, 'message': 'Please upload a PDF file.'})

    tmp_name = f"{uuid.uuid4().hex}.pdf"
    tmp_path = os.path.join(app.config['UPLOAD_FOLDER'], 'documents', tmp_name)
    file.save(tmp_path)

    # Reject absurdly large files outright (also bounded by MAX_CONTENT_LENGTH,
    # but give a friendlier message for brochure-specific limits)
    try:
        size_mb = os.path.getsize(tmp_path) / (1024 * 1024)
    except OSError:
        size_mb = 0
    if size_mb > 45:
        try: os.remove(tmp_path)
        except Exception: pass
        return jsonify({'success': False,
                         'message': f'This PDF is {size_mb:.1f}MB, which is too large to '
                                     f'process (max ~45MB). Please compress the brochure '
                                     f'or split it into smaller files.'})

    # Overall wall-clock budget for this request (text + tables + images)
    deadline = time.monotonic() + BROCHURE_MAX_TIME_SECONDS

    try:
        file_size_mb = round(os.path.getsize(tmp_path) / (1024 * 1024), 2)

        # ── Determine page count up front so we can scale limits ──
        total_pages = None
        try:
            import fitz
            with fitz.open(tmp_path) as _doc:
                total_pages = len(_doc)
        except Exception:
            pass

        # ── Extract text with pdfplumber (page-capped) ──
        text = ''
        pages_read = 0
        try:
            import pdfplumber
            with pdfplumber.open(tmp_path) as pdf:
                page_count = min(len(pdf.pages), BROCHURE_MAX_PAGES_TEXT)
                for page in pdf.pages[:page_count]:
                    if time.monotonic() > deadline:
                        break
                    try:
                        page_text = page.extract_text() or ''
                    except Exception:
                        page_text = ''
                    text += page_text + '\n'
                    pages_read += 1
                    if len(text) > BROCHURE_MAX_TEXT_CHARS:
                        break
        except Exception as e:
            log_activity('Brochure Extract - Text Failed', str(e))

        # ── Also pull text out of tables (specs/amenities often live here) ──
        if time.monotonic() < deadline:
            try:
                table_text = extract_brochure_tables_text(tmp_path, deadline=deadline)
                if table_text:
                    text += '\n' + table_text
            except Exception as e:
                log_activity('Brochure Extract - Table Text Failed', str(e))

        fields = extract_brochure_text_data(text)

        # ── Extract images with PyMuPDF (page-capped + time-capped) ──
        images = []
        try:
            images = extract_brochure_images(
                tmp_path, os.path.join(app.config['UPLOAD_FOLDER'], 'properties'),
                deadline=deadline)
        except Exception as e:
            log_activity('Brochure Extract - Images Failed', str(e))

        # Build green/red extraction status map for the UI dots
        status = {f: bool(fields.get(f)) for f in BROCHURE_TRACKED_FIELDS}

        timed_out = time.monotonic() > deadline
        truncated = (total_pages is not None and total_pages > BROCHURE_MAX_PAGES_TEXT)

        log_activity('Brochure Auto-Fill',
                      f"{file.filename} ({file_size_mb}MB, {total_pages} pages) - "
                      f"{len(fields)} fields, {len(images)} images"
                      f"{' [partial: large file]' if (timed_out or truncated) else ''}")

        message = None
        if timed_out:
            message = ('This brochure is large, so extraction stopped early to avoid timing out. '
                        'Results below are from the portion that was processed — '
                        'please review and complete any remaining fields manually.')
        elif truncated:
            message = (f'This brochure has {total_pages} pages — only the first '
                        f'{BROCHURE_MAX_PAGES_TEXT} were scanned for text/data and the first '
                        f'{BROCHURE_MAX_PAGES_IMAGES} for images. Please review extracted '
                        f'fields and add anything from later pages manually.')

        return jsonify({
            'success': True,
            'fields': fields,
            'status': status,
            'images': images,
            'image_urls': [url_for('static', filename='uploads/properties/' + f) for f in images],
            'partial': bool(timed_out or truncated),
            'message': message,
            'pages_total': total_pages,
            'pages_scanned': pages_read,
            'file_size_mb': file_size_mb,
        })
    except Exception as e:
        return jsonify({'success': False, 'message': f'Extraction failed: {str(e)}'})

    finally:
        try: os.remove(tmp_path)
        except Exception: pass


@app.route('/owner/property/add', methods=['GET','POST'])
@login_required
@owner_required
def add_property():
    if request.method=='POST':
        title=clean(request.form.get('title',''))
        slug=_unique_slug(slugify(title), Property)
        prop=Property(
            title=title, property_id=f"LR{datetime.utcnow().strftime('%Y%m%d%H%M%S')}",
            slug=slug,
            description=bleach.clean(request.form.get('description',''),
                tags=['p','br','strong','em','ul','li','ol','h2','h3','h4','a'],strip=True),
            property_type=request.form.get('property_type',''),
            listing_type=request.form.get('listing_type','sale'),
            status=request.form.get('status','available'),
            price=float(request.form.get('price',0) or 0),
            price_unit=request.form.get('price_unit','total'),
            currency=request.form.get('currency','INR'),
            area=float(request.form.get('area',0) or 0),
            area_unit=request.form.get('area_unit','sqft'),
            bedrooms=int(request.form.get('bedrooms',0) or 0) or None,
            bathrooms=int(request.form.get('bathrooms',0) or 0) or None,
            parking=int(request.form.get('parking',0) or 0) or None,
            furnishing=request.form.get('furnishing',''),
            property_age=clean(request.form.get('property_age','')),
            address=clean(request.form.get('address','')),
            city=clean(request.form.get('city','')),
            state=clean(request.form.get('state','')),
            pincode=clean(request.form.get('pincode','')),
            latitude=float(request.form.get('latitude',0) or 0) or None,
            longitude=float(request.form.get('longitude',0) or 0) or None,
            google_map_link=clean(request.form.get('google_map_link','')),
            video_url=clean(request.form.get('video_url','')),
            is_featured='is_featured' in request.form,
            meta_title=clean(request.form.get('meta_title','')),
            meta_description=clean(request.form.get('meta_description','')),
        )
        db.session.add(prop); db.session.flush()
        for a in request.form.getlist('amenities[]'):
            if a.strip(): db.session.add(PropertyAmenity(property_id=prop.id,name=a.strip()))
        brochure=request.files.get('brochure')
        if brochure and brochure.filename:
            ext=secure_filename(brochure.filename).rsplit('.',1)[-1].lower()
            if ext in {'pdf','docx'}:
                fn=f"{uuid.uuid4().hex}.{ext}"
                brochure.save(os.path.join(app.config['UPLOAD_FOLDER'],'documents',fn))
                prop.brochure_path=fn
        first=True
        for img in request.files.getlist('images[]'):
            fn=save_image(img,'properties')
            if fn: db.session.add(PropertyImage(property_id=prop.id,filename=fn,is_primary=first)); first=False

        # Attach images that were extracted from an uploaded brochure PDF
        _save_extracted_images(prop, has_existing_images=not first)

        _save_property_videos(prop)

        db.session.commit()

        # Auto-generate brochure if requested and none uploaded
        if request.form.get('auto_brochure')=='1' and not prop.brochure_path:
            try:
                fn=generate_brochure_pdf(prop)
                prop.brochure_path=fn
                prop.brochure_auto=True
                db.session.commit()
            except Exception as e:
                log_activity('Brochure Generation Failed', str(e))

        log_activity('Add Property',title)
        flash('Property added!','success')
        return redirect(url_for('owner_properties'))
    prop_types=['Apartment','Villa','Office','Shop','Land','Warehouse','Residential','Commercial','Industrial','Agricultural','Luxury']
    return render_template('owner/property_form.html',prop=None,prop_types=prop_types,action='Add')

def _unique_slug(base, model):
    slug=base; n=1
    while model.query.filter_by(slug=slug).first(): slug=f"{base}-{n}"; n+=1
    return slug

def _save_extracted_images(prop, has_existing_images=False):
    """Attach images that were already extracted from a brochure PDF (and
    saved to disk by /owner/upload-brochure) to this property as
    PropertyImage records. The first selected image becomes primary if the
    property has no images yet."""
    filenames = request.form.getlist('extracted_images[]')
    if not filenames:
        return
    upload_dir = os.path.join(app.config['UPLOAD_FOLDER'], 'properties')
    first = not has_existing_images
    for fn in filenames:
        safe_fn = secure_filename(fn)
        if not safe_fn or not os.path.exists(os.path.join(upload_dir, safe_fn)):
            continue
        db.session.add(PropertyImage(property_id=prop.id, filename=safe_fn, is_primary=first))
        first = False


def _save_property_videos(prop):
    """Save YouTube/Vimeo links and uploaded video files for a property"""
    # YouTube/Vimeo links (multiple, one per line or repeated field)
    for link in request.form.getlist('youtube_links[]'):
        link = link.strip()
        if link:
            embed = youtube_embed_url(link)
            title = clean(request.form.get('youtube_title_' + str(hash(link)) , ''))
            db.session.add(PropertyVideo(property_id=prop.id, video_type='youtube',
                                          url=embed, title=title or 'Property Video'))
    # Set primary video_url field for backward compatibility (first youtube link)
    yt_links = [l.strip() for l in request.form.getlist('youtube_links[]') if l.strip()]
    if yt_links and not prop.video_url:
        prop.video_url = youtube_embed_url(yt_links[0])

    # Uploaded video files
    for vid in request.files.getlist('video_files[]'):
        if vid and vid.filename:
            fn = save_video(vid)
            if fn:
                db.session.add(PropertyVideo(property_id=prop.id, video_type='upload',
                                              filename=fn, title='Property Video'))

@app.route('/owner/property/<int:pid>/edit', methods=['GET','POST'])
@login_required
@owner_required
def edit_property(pid):
    prop=Property.query.get_or_404(pid)
    if request.method=='POST':
        prop.title=clean(request.form.get('title',''))
        prop.description=bleach.clean(request.form.get('description',''),
            tags=['p','br','strong','em','ul','li','ol','h2','h3','h4','a'],strip=True)
        prop.property_type=request.form.get('property_type','')
        prop.listing_type=request.form.get('listing_type','sale')
        prop.status=request.form.get('status','available')
        prop.price=float(request.form.get('price',0) or 0)
        prop.price_unit=request.form.get('price_unit','total')
        prop.currency=request.form.get('currency','INR')
        prop.area=float(request.form.get('area',0) or 0)
        prop.area_unit=request.form.get('area_unit','sqft')
        prop.bedrooms=int(request.form.get('bedrooms',0) or 0) or None
        prop.bathrooms=int(request.form.get('bathrooms',0) or 0) or None
        prop.parking=int(request.form.get('parking',0) or 0) or None
        prop.furnishing=request.form.get('furnishing','')
        prop.property_age=clean(request.form.get('property_age',''))
        prop.address=clean(request.form.get('address',''))
        prop.city=clean(request.form.get('city',''))
        prop.state=clean(request.form.get('state',''))
        prop.pincode=clean(request.form.get('pincode',''))
        prop.latitude=float(request.form.get('latitude',0) or 0) or None
        prop.longitude=float(request.form.get('longitude',0) or 0) or None
        prop.google_map_link=clean(request.form.get('google_map_link',''))
        prop.video_url=clean(request.form.get('video_url',''))
        prop.is_featured='is_featured' in request.form
        prop.meta_title=clean(request.form.get('meta_title',''))
        prop.meta_description=clean(request.form.get('meta_description',''))
        prop.updated_at=datetime.utcnow()
        PropertyAmenity.query.filter_by(property_id=prop.id).delete()
        for a in request.form.getlist('amenities[]'):
            if a.strip(): db.session.add(PropertyAmenity(property_id=prop.id,name=a.strip()))
        for img in request.files.getlist('images[]'):
            fn=save_image(img,'properties')
            if fn: db.session.add(PropertyImage(property_id=prop.id,filename=fn))

        # Attach images that were extracted from an uploaded brochure PDF
        _save_extracted_images(prop, has_existing_images=bool(prop.images))

        # Brochure upload (manual overrides auto)
        brochure=request.files.get('brochure')
        if brochure and brochure.filename:
            ext=secure_filename(brochure.filename).rsplit('.',1)[-1].lower()
            if ext in {'pdf','docx'}:
                fn=f"{uuid.uuid4().hex}.{ext}"
                brochure.save(os.path.join(app.config['UPLOAD_FOLDER'],'documents',fn))
                prop.brochure_path=fn
                prop.brochure_auto=False

        _save_property_videos(prop)

        db.session.commit()

        # Auto-generate / regenerate brochure
        if request.form.get('auto_brochure')=='1':
            try:
                fn=generate_brochure_pdf(prop)
                prop.brochure_path=fn
                prop.brochure_auto=True
                db.session.commit()
            except Exception as e:
                log_activity('Brochure Generation Failed', str(e))

        log_activity('Edit Property',prop.title)
        flash('Property updated!','success')
        return redirect(url_for('owner_properties'))
    prop_types=['Apartment','Villa','Office','Shop','Land','Warehouse','Residential','Commercial','Industrial','Agricultural','Luxury']
    return render_template('owner/property_form.html',prop=prop,prop_types=prop_types,action='Edit')

@app.route('/owner/property/<int:pid>/delete', methods=['POST'])
@login_required
@owner_required
def delete_property(pid):
    prop=Property.query.get_or_404(pid)
    log_activity('Delete Property',prop.title)
    db.session.delete(prop); db.session.commit()
    flash('Property deleted.','info')
    return redirect(url_for('owner_properties'))

@app.route('/owner/property/image/<int:iid>/delete', methods=['POST'])
@login_required
@owner_required
def delete_property_image(iid):
    img=PropertyImage.query.get_or_404(iid)
    try: os.remove(os.path.join(app.config['UPLOAD_FOLDER'],'properties',img.filename))
    except Exception: pass
    db.session.delete(img); db.session.commit()
    return jsonify({'success':True})

@app.route('/owner/property/video/<int:vid>/delete', methods=['POST'])
@login_required
@owner_required
def delete_property_video(vid):
    video=PropertyVideo.query.get_or_404(vid)
    if video.video_type=='upload' and video.filename:
        try: os.remove(os.path.join(app.config['UPLOAD_FOLDER'],'videos',video.filename))
        except Exception: pass
    db.session.delete(video); db.session.commit()
    return jsonify({'success':True})

@app.route('/owner/property/<int:pid>/generate-brochure', methods=['POST'])
@login_required
@owner_required
def generate_brochure(pid):
    prop=Property.query.get_or_404(pid)
    try:
        # remove old auto-generated brochure
        if prop.brochure_path and prop.brochure_auto:
            try: os.remove(os.path.join(app.config['UPLOAD_FOLDER'],'documents',prop.brochure_path))
            except Exception: pass
        fn=generate_brochure_pdf(prop)
        prop.brochure_path=fn
        prop.brochure_auto=True
        db.session.commit()
        log_activity('Generate Brochure', prop.title)
        flash('✅ PDF brochure generated successfully!','success')
    except Exception as e:
        flash(f'Brochure generation failed: {str(e)}','danger')
    return redirect(request.referrer or url_for('owner_properties'))

@app.route('/owner/property/<int:pid>/notes', methods=['POST'])
@login_required
@owner_required
def add_property_note(pid):
    prop=Property.query.get_or_404(pid)
    content=clean(request.form.get('content',''))
    if content:
        db.session.add(PropertyNote(property_id=prop.id, content=content))
        db.session.commit()
        flash('Note added.','success')
    return redirect(url_for('edit_property', pid=pid))

@app.route('/owner/property/note/<int:nid>/delete', methods=['POST'])
@login_required
@owner_required
def delete_property_note(nid):
    note=PropertyNote.query.get_or_404(nid)
    pid=note.property_id
    db.session.delete(note); db.session.commit()
    return redirect(url_for('edit_property', pid=pid))

@app.route('/owner/property/<int:pid>/toggle-public-link', methods=['POST'])
@login_required
@owner_required
def toggle_public_link(pid):
    prop=Property.query.get_or_404(pid)
    prop.public_link_enabled = not prop.public_link_enabled
    db.session.commit()
    return jsonify({'success':True,'enabled':prop.public_link_enabled})

@app.route('/owner/inquiries')
@login_required
@owner_required
def owner_inquiries():
    page=request.args.get('page',1,type=int)
    filter_read=request.args.get('filter','')
    q=Inquiry.query
    if filter_read=='unread': q=q.filter_by(is_read=False)
    elif filter_read=='read': q=q.filter_by(is_read=True)
    inqs=q.order_by(Inquiry.created_at.desc()).paginate(page=page,per_page=20,error_out=False)
    return render_template('owner/inquiries.html',inqs=inqs)

@app.route('/owner/inquiry/<int:iid>', methods=['GET','POST'])
@login_required
@owner_required
def view_inquiry(iid):
    inq=Inquiry.query.get_or_404(iid)
    inq.is_read=True; db.session.commit()
    if request.method=='POST':
        inq.reply=clean(request.form.get('reply',''))
        inq.replied_at=datetime.utcnow(); db.session.commit()
        flash('Reply saved.','success')
    return render_template('owner/inquiry_detail.html',inq=inq)

@app.route('/owner/inquiries/export')
@login_required
@owner_required
def export_inquiries():
    inqs=Inquiry.query.order_by(Inquiry.created_at.desc()).all()
    out=io.StringIO()
    w=csv.writer(out)
    w.writerow(['ID','Name','Email','Phone','Subject','Message','Property','Date','Read'])
    for i in inqs:
        w.writerow([i.id,i.name,i.email,i.phone or '',i.source or '',
                    i.message,i.property.title if i.property else 'General',
                    i.created_at.strftime('%Y-%m-%d %H:%M'),'Yes' if i.is_read else 'No'])
    out.seek(0)
    return send_file(io.BytesIO(out.getvalue().encode()),mimetype='text/csv',
                     as_attachment=True,download_name=f'inquiries_{datetime.utcnow().strftime("%Y%m%d")}.csv')

@app.route('/owner/testimonials', methods=['GET','POST'])
@login_required
@owner_required
def owner_testimonials():
    if request.method=='POST':
        action=request.form.get('action')
        if action=='add':
            photo=save_image(request.files.get('photo'),'profiles',(300,300))
            db.session.add(Testimonial(name=clean(request.form.get('name','')),
                designation=clean(request.form.get('designation','')),
                content=clean(request.form.get('content','')),
                rating=int(request.form.get('rating',5)),photo=photo))
            db.session.commit(); flash('Testimonial added!','success')
        elif action=='delete':
            t=Testimonial.query.get(request.form.get('id',type=int))
            if t: db.session.delete(t); db.session.commit()
    return render_template('owner/testimonials.html',testimonials=Testimonial.query.order_by(Testimonial.created_at.desc()).all())

@app.route('/owner/blog')
@login_required
@owner_required
def owner_blog():
    return render_template('owner/blog.html',posts=BlogPost.query.order_by(BlogPost.created_at.desc()).all())

@app.route('/owner/blog/add', methods=['GET','POST'])
@login_required
@owner_required
def add_blog():
    if request.method=='POST':
        title=clean(request.form.get('title',''))
        slug=_unique_slug(slugify(title),BlogPost)
        img=save_image(request.files.get('featured_image'),'blog')
        db.session.add(BlogPost(title=title,slug=slug,content=request.form.get('content',''),
            excerpt=clean(request.form.get('excerpt','')),featured_image=img,
            is_published='is_published' in request.form,
            meta_title=clean(request.form.get('meta_title','')),
            meta_description=clean(request.form.get('meta_description',''))))
        db.session.commit(); flash('Post created!','success')
        return redirect(url_for('owner_blog'))
    return render_template('owner/blog_form.html',post=None)

@app.route('/owner/blog/<int:bid>/edit', methods=['GET','POST'])
@login_required
@owner_required
def edit_blog(bid):
    post=BlogPost.query.get_or_404(bid)
    if request.method=='POST':
        post.title=clean(request.form.get('title',''))
        post.content=request.form.get('content','')
        post.excerpt=clean(request.form.get('excerpt',''))
        post.is_published='is_published' in request.form
        post.meta_title=clean(request.form.get('meta_title',''))
        post.meta_description=clean(request.form.get('meta_description',''))
        img=save_image(request.files.get('featured_image'),'blog')
        if img: post.featured_image=img
        db.session.commit(); flash('Post updated!','success')
        return redirect(url_for('owner_blog'))
    return render_template('owner/blog_form.html',post=post)

@app.route('/owner/settings', methods=['GET','POST'])
@login_required
@owner_required
def owner_settings():
    if request.method=='POST':
        keys=['site_name','tagline','phone','whatsapp','email','address',
              'facebook','instagram','twitter','linkedin','youtube',
              'hero_title','hero_subtitle','meta_title','meta_description',
              'agent_name','agent_title','agent_bio','agent_experience',
              'agent_certifications','agent_languages','agent_whatsapp',
              'google_maps_embed','map_lat','map_lng','map_zoom']
        data={k: clean(request.form.get(k,'')) for k in keys}
        logo=save_image(request.files.get('logo'),'profiles',(400,200))
        if logo: data['logo']=logo
        ap=save_image(request.files.get('agent_photo'),'profiles',(400,400))
        if ap: data['agent_photo']=ap
        fav=request.files.get('favicon')
        if fav and fav.filename:
            fn=f"{uuid.uuid4().hex}.ico"
            fav.save(os.path.join(app.config['UPLOAD_FOLDER'],'profiles',fn))
            data['favicon']=fn
        set_settings(data)
        log_activity('Settings Updated')
        flash('✅ Settings saved successfully!','success')
        return redirect(url_for('owner_settings'))
    return render_template('owner/settings.html')

@app.route('/owner/faqs', methods=['GET','POST'])
@login_required
@owner_required
def owner_faqs():
    if request.method=='POST':
        action=request.form.get('action')
        if action=='add':
            db.session.add(FAQ(question=clean(request.form.get('question','')),
                answer=clean(request.form.get('answer','')),
                sort_order=int(request.form.get('sort_order',0) or 0)))
            db.session.commit(); flash('FAQ added!','success')
        elif action=='delete':
            f=FAQ.query.get(request.form.get('id',type=int))
            if f: db.session.delete(f); db.session.commit()
    return render_template('owner/faqs.html',faqs=FAQ.query.order_by(FAQ.sort_order).all())

# ── DEVELOPER DASHBOARD ──────────────────────────────────────────────

@app.route('/developer')
@login_required
@developer_required
def developer_dashboard():
    users=User.query.all()
    total_v=PageVisit.query.count()
    total_p=Property.query.count()
    total_i=Inquiry.query.count()
    logs=ActivityLog.query.order_by(ActivityLog.created_at.desc()).limit(20).all()

    # System / storage info
    upload_dir = app.config['UPLOAD_FOLDER']
    total_size = 0
    file_count = 0
    for root, dirs, files in os.walk(upload_dir):
        for f in files:
            if f == '.gitkeep': continue
            try:
                total_size += os.path.getsize(os.path.join(root, f))
                file_count += 1
            except Exception: pass
    storage_mb = round(total_size / (1024*1024), 2)

    today = datetime.utcnow().date()
    today_v = PageVisit.query.filter(db.func.date(PageVisit.created_at)==today).count()
    unread_msgs = Inquiry.query.filter_by(is_read=False).count()
    total_videos = PropertyVideo.query.count()
    auto_brochures = Property.query.filter_by(brochure_auto=True).count()

    return render_template('developer/dashboard.html',users=users,total_v=total_v,
                           total_p=total_p,total_i=total_i,logs=logs,
                           storage_mb=storage_mb, file_count=file_count,
                           today_v=today_v, unread_msgs=unread_msgs,
                           total_videos=total_videos, auto_brochures=auto_brochures)

@app.route('/developer/users', methods=['GET','POST'])
@login_required
@developer_required
def manage_users():
    if request.method=='POST':
        action=request.form.get('action')
        if action=='create':
            u_name=request.form.get('username','').strip()
            email=request.form.get('email','').strip()
            pw=request.form.get('password','')
            role=request.form.get('role','owner')
            if u_name and email and pw:
                if not User.query.filter((User.username==u_name)|(User.email==email)).first():
                    u=User(username=u_name,email=email,role=role); u.set_password(pw)
                    db.session.add(u); db.session.commit()
                    log_activity('Create User',f'{u_name} ({role})')
                    flash(f'User {u_name} created!','success')
                else: flash('Username/email already exists.','danger')
        elif action=='delete':
            uid=request.form.get('user_id',type=int)
            if uid!=current_user.id:
                u=User.query.get(uid)
                if u: db.session.delete(u); db.session.commit(); flash('User deleted.','info')
        elif action=='toggle':
            u=User.query.get(request.form.get('user_id',type=int))
            if u and u.id!=current_user.id: u.is_active=not u.is_active; db.session.commit()
        elif action=='reset_password':
            u=User.query.get(request.form.get('user_id',type=int))
            pw=request.form.get('new_password','')
            if u and pw: u.set_password(pw); u.failed_logins=0; u.locked_until=None; db.session.commit(); flash('Password reset.','success')
    return render_template('developer/users.html',users=User.query.all())

@app.route('/developer/settings', methods=['GET','POST'])
@login_required
@developer_required
def developer_settings():
    if request.method=='POST':
        keys=['site_name','tagline','phone','whatsapp','email','address',
              'hero_title','hero_subtitle','meta_title','meta_description',
              'primary_color','accent_color','custom_css','custom_js',
              'google_maps_embed','map_lat','map_lng','map_zoom',
              'maintenance_mode','smtp_host','smtp_port','smtp_user','smtp_pass',
              'admin_path','dev_path']
        data={}
        for k in keys:
            v=request.form.get(k,'')
            data[k] = v if k in ('custom_css','custom_js') else clean(v)
        logo=save_image(request.files.get('logo'),'profiles',(400,200))
        if logo: data['logo']=logo
        fav=request.files.get('favicon')
        if fav and fav.filename:
            fn=f"{uuid.uuid4().hex}.ico"
            fav.save(os.path.join(app.config['UPLOAD_FOLDER'],'profiles',fn)); data['favicon']=fn
        set_settings(data)
        log_activity('Dev Settings Updated')
        flash('✅ Settings saved!','success')
        return redirect(url_for('developer_settings'))
    return render_template('developer/settings.html')

@app.route('/developer/external-links', methods=['GET','POST'])
@login_required
@developer_required
def manage_external_links():
    if request.method=='POST':
        action=request.form.get('action')
        if action=='add':
            db.session.add(ExternalLink(
                name=clean(request.form.get('name','')),
                url=request.form.get('url','').strip(),
                link_type=request.form.get('link_type','header_nav'),
                description=clean(request.form.get('description','')),
                open_in=request.form.get('open_in','_blank'),
                sort_order=int(request.form.get('sort_order',0) or 0),
                is_active='is_active' in request.form))
            db.session.commit(); flash('Link added!','success')
        elif action=='toggle':
            l=ExternalLink.query.get(request.form.get('link_id',type=int))
            if l: l.is_active=not l.is_active; db.session.commit()
        elif action=='delete':
            l=ExternalLink.query.get(request.form.get('link_id',type=int))
            if l: db.session.delete(l); db.session.commit(); flash('Link removed.','info')
        elif action=='edit':
            l=ExternalLink.query.get(request.form.get('link_id',type=int))
            if l:
                l.name=clean(request.form.get('name',''))
                l.url=request.form.get('url','').strip()
                l.link_type=request.form.get('link_type','header_nav')
                l.description=clean(request.form.get('description',''))
                l.open_in=request.form.get('open_in','_blank')
                l.sort_order=int(request.form.get('sort_order',0) or 0)
                l.is_active='is_active' in request.form
                db.session.commit(); flash('Link updated!','success')
    links=ExternalLink.query.order_by(ExternalLink.link_type,ExternalLink.sort_order).all()
    return render_template('developer/external_links.html',links=links,
                           link_types=['header_nav','footer','social','iframe','redirect','custom_page'])

@app.route('/developer/analytics')
@login_required
@developer_required
def analytics():
    from sqlalchemy import func
    today=datetime.utcnow().date()
    daily=db.session.query(func.date(PageVisit.created_at).label('d'),func.count().label('c'))\
        .filter(PageVisit.created_at>=today-timedelta(days=30))\
        .group_by(func.date(PageVisit.created_at)).order_by('d').all()
    top_pages=db.session.query(PageVisit.page,func.count().label('c'))\
        .filter(PageVisit.created_at>=today-timedelta(days=30))\
        .group_by(PageVisit.page).order_by(func.count().desc()).limit(10).all()
    top_props=Property.query.order_by(Property.views.desc()).limit(10).all()
    return render_template('developer/analytics.html',daily=daily,top_pages=top_pages,top_props=top_props)

@app.route('/developer/logs')
@login_required
@developer_required
def activity_logs():
    page=request.args.get('page',1,type=int)
    logs=ActivityLog.query.order_by(ActivityLog.created_at.desc()).paginate(page=page,per_page=50,error_out=False)
    return render_template('developer/logs.html',logs=logs)

@app.route('/developer/database')
@login_required
@developer_required
def database_overview():
    stats={'users':User.query.count(),'properties':Property.query.count(),
           'images':PropertyImage.query.count(),'inquiries':Inquiry.query.count(),
           'testimonials':Testimonial.query.count(),'blog_posts':BlogPost.query.count(),
           'activity_logs':ActivityLog.query.count(),'page_visits':PageVisit.query.count(),
           'faqs':FAQ.query.count(),'external_links':ExternalLink.query.count(),
           'settings':SiteSettings.query.count()}
    return render_template('developer/database.html',stats=stats)

@app.route('/developer/database/clear-logs', methods=['POST'])
@login_required
@developer_required
def clear_logs():
    ActivityLog.query.delete(); PageVisit.query.delete(); db.session.commit()
    flash('Logs cleared.','info')
    return redirect(url_for('database_overview'))

# ── BACKUP / RESTORE ─────────────────────────────────────────────────

@app.route('/developer/backup/create')
@login_required
@developer_required
def create_backup():
    ts=datetime.utcnow().strftime('%Y%m%d_%H%M%S')
    fname=f"backup_{ts}.zip"
    fpath=os.path.join(app.config['UPLOAD_FOLDER'],'backups',fname)
    try:
        with zipfile.ZipFile(fpath,'w',zipfile.ZIP_DEFLATED) as zf:
            # Export all DB tables as JSON
            data={
                'users':[{'id':u.id,'username':u.username,'email':u.email,
                          'password_hash':u.password_hash,'role':u.role,'is_active':u.is_active} for u in User.query.all()],
                'settings':[{'key':s.key,'value':s.value} for s in SiteSettings.query.all()],
                'properties':[{'id':p.id,'property_id':p.property_id,'title':p.title,'slug':p.slug,
                                'description':p.description,'property_type':p.property_type,
                                'listing_type':p.listing_type,'status':p.status,'price':p.price,
                                'price_unit':p.price_unit,'area':p.area,'area_unit':p.area_unit,
                                'bedrooms':p.bedrooms,'bathrooms':p.bathrooms,'parking':p.parking,
                                'furnishing':p.furnishing,'property_age':p.property_age,
                                'address':p.address,'city':p.city,'state':p.state,'pincode':p.pincode,
                                'latitude':p.latitude,'longitude':p.longitude,
                                'google_map_link':p.google_map_link,'video_url':p.video_url,
                                'is_featured':p.is_featured,'views':p.views,'created_at':str(p.created_at)} for p in Property.query.all()],
                'inquiries':[{'id':i.id,'name':i.name,'email':i.email,'phone':i.phone,
                               'message':i.message,'source':i.source,'is_read':i.is_read,
                               'reply':i.reply,'property_id':i.property_id,
                               'created_at':str(i.created_at)} for i in Inquiry.query.all()],
                'testimonials':[{'id':t.id,'name':t.name,'designation':t.designation,
                                  'content':t.content,'rating':t.rating,'photo':t.photo,
                                  'is_active':t.is_active} for t in Testimonial.query.all()],
                'faqs':[{'id':f.id,'question':f.question,'answer':f.answer,
                          'sort_order':f.sort_order,'is_active':f.is_active} for f in FAQ.query.all()],
                'blog_posts':[{'id':b.id,'title':b.title,'slug':b.slug,'content':b.content,
                                'excerpt':b.excerpt,'featured_image':b.featured_image,
                                'is_published':b.is_published,'views':b.views} for b in BlogPost.query.all()],
                'external_links':[{'id':l.id,'name':l.name,'url':l.url,'link_type':l.link_type,
                                    'description':l.description,'open_in':l.open_in,
                                    'sort_order':l.sort_order,'is_active':l.is_active} for l in ExternalLink.query.all()],
                'backup_info':{'created_at':ts,'version':'2.0'}
            }
            zf.writestr('database.json', json.dumps(data, indent=2, default=str))
            # Include uploaded media
            uploads_dir=app.config['UPLOAD_FOLDER']
            for root,dirs,files in os.walk(uploads_dir):
                for file in files:
                    if file=='.gitkeep': continue
                    fp=os.path.join(root,file)
                    arcname=os.path.relpath(fp, os.path.dirname(uploads_dir))
                    zf.write(fp, arcname)
        log_activity('Backup Created',fname)
        return send_file(fpath, as_attachment=True, download_name=fname)
    except Exception as e:
        flash(f'Backup failed: {str(e)}','danger')
        return redirect(url_for('database_overview'))

@app.route('/developer/backup/restore', methods=['POST'])
@login_required
@developer_required
def restore_backup():
    f=request.files.get('backup_file')
    if not f or not f.filename.endswith('.zip'):
        flash('Please upload a valid .zip backup file.','danger')
        return redirect(url_for('database_overview'))
    try:
        content=f.read()
        with zipfile.ZipFile(io.BytesIO(content),'r') as zf:
            if 'database.json' not in zf.namelist():
                flash('Invalid backup: missing database.json','danger')
                return redirect(url_for('database_overview'))
            data=json.loads(zf.read('database.json'))
            # Restore settings only (safe restore)
            if 'settings' in data:
                for row in data['settings']:
                    existing=SiteSettings.query.filter_by(key=row['key']).first()
                    if existing: existing.value=row['value']
                    else: db.session.add(SiteSettings(key=row['key'],value=row['value']))
            # Restore testimonials
            if 'testimonials' in data:
                Testimonial.query.delete()
                for t in data['testimonials']:
                    db.session.add(Testimonial(name=t['name'],designation=t.get('designation',''),
                        content=t['content'],rating=t.get('rating',5),photo=t.get('photo'),is_active=t.get('is_active',True)))
            # Restore FAQs
            if 'faqs' in data:
                FAQ.query.delete()
                for fq in data['faqs']:
                    db.session.add(FAQ(question=fq['question'],answer=fq['answer'],
                        sort_order=fq.get('sort_order',0),is_active=fq.get('is_active',True)))
            # Restore media files
            for name in zf.namelist():
                if name.startswith('static/uploads/') and not name.endswith('/'):
                    dest=os.path.join(os.path.dirname(app.root_path) if False else '', name)
                    os.makedirs(os.path.dirname(name),exist_ok=True)
                    with open(name,'wb') as out: out.write(zf.read(name))
            db.session.commit()
        log_activity('Backup Restored',f.filename)
        flash('✅ Backup restored successfully! Settings, testimonials, and FAQs have been restored.','success')
    except Exception as e:
        db.session.rollback()
        flash(f'Restore failed: {str(e)}','danger')
    return redirect(url_for('database_overview'))

@app.route('/developer/messages')
@login_required
@developer_required
def all_messages():
    page=request.args.get('page',1,type=int)
    inqs=Inquiry.query.order_by(Inquiry.created_at.desc()).paginate(page=page,per_page=30,error_out=False)
    return render_template('developer/messages.html',inqs=inqs)

# ── LIVE PREVIEW API ─────────────────────────────────────────────────

@app.route('/api/settings/preview', methods=['POST'])
@login_required
@owner_required
def settings_preview():
    """Return HTML snippet showing how settings look"""
    site_name=clean(request.json.get('site_name',''))
    primary_color=request.json.get('primary_color','#1a56db')
    return jsonify({'site_name':site_name,'primary_color':primary_color,'success':True})

# ── ERROR HANDLERS ────────────────────────────────────────────────────
@app.errorhandler(404)
def e404(e): return render_template('public/404.html'),404
@app.errorhandler(403)
def e403(e): return render_template('public/403.html'),403
@app.errorhandler(500)
def e500(e): return render_template('public/500.html'),500

# ── INIT DB ──────────────────────────────────────────────────────────

def run_auto_migrations():
    """Safely add any missing columns to existing tables (lightweight migration
    for deployments where db.create_all() doesn't alter existing tables)."""
    from sqlalchemy import inspect, text

    inspector = inspect(db.engine)
    existing_tables = inspector.get_table_names()

    # Map of table -> {column_name: SQL column definition}
    column_specs = {
        'properties': {
            'brochure_auto': 'BOOLEAN DEFAULT 0',
            'public_link_enabled': 'BOOLEAN DEFAULT 1',
            'currency': "VARCHAR(10) DEFAULT 'INR'",
        },
        'users': {
            'totp_secret': 'VARCHAR(32)',
            'two_fa_enabled': 'BOOLEAN DEFAULT 0',
        },
    }

    with db.engine.connect() as conn:
        for table, columns in column_specs.items():
            if table not in existing_tables:
                continue
            existing_cols = {c['name'] for c in inspector.get_columns(table)}
            for col_name, col_def in columns.items():
                if col_name not in existing_cols:
                    try:
                        conn.execute(text(f'ALTER TABLE {table} ADD COLUMN {col_name} {col_def}'))
                        conn.commit()
                    except Exception as e:
                        print(f"Migration warning: could not add {table}.{col_name}: {e}")

def init_db():
    with app.app_context():
        db.create_all()
        run_auto_migrations()
        if not User.query.filter_by(role='developer').first():
            u=User(username='developer',email='dev@luxerealty.com',role='developer'); u.set_password('Dev@123456'); db.session.add(u)
        if not User.query.filter_by(role='owner').first():
            u=User(username='owner',email='owner@luxerealty.com',role='owner'); u.set_password('Owner@123456'); db.session.add(u)
        for k,v in SETTING_DEFAULTS.items():
            if not SiteSettings.query.filter_by(key=k).first():
                db.session.add(SiteSettings(key=k,value=v))
        db.session.commit()

# Compatibility redirect for flask-login's redirect
@app.route('/login')
def login_redirect():
    s = get_settings()
    return redirect(url_for('login', login_path=s.get('admin_path','admin')))

# Run DB setup/migrations at import time so gunicorn workers also initialize the DB
try:
    init_db()
except Exception as e:
    print(f"DB init warning: {e}")

if __name__=='__main__':
    app.run(debug=True)
