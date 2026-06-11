import os, uuid, csv, io, json, zipfile, shutil
from datetime import datetime, timedelta
from functools import wraps
from flask import (Flask, render_template, redirect, url_for, flash,
                   request, jsonify, send_file, abort, session, Response)
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

from models import db, User, Property, PropertyImage, PropertyAmenity, Inquiry, Testimonial, BlogPost, ActivityLog, PageVisit, SiteSettings, FAQ, ExternalLink

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

ALLOWED_IMG = {'jpg','jpeg','png','webp','gif'}
ALLOWED_ALL = {'jpg','jpeg','png','webp','gif','mp4','mov','pdf','docx'}

# ── EXTENSIONS ──────────────────────────────────────────────────────
db.init_app(app)
migrate = Migrate(app, db)
csrf = CSRFProtect(app)
login_manager = LoginManager(app)
login_manager.login_view = 'login_redirect'
login_manager.login_message_category = 'info'
login_manager.login_message = 'Please log in to access this page.'
limiter = Limiter(key_func=get_remote_address, app=app,
                  default_limits=["500 per day", "100 per hour"],
                  storage_uri="memory://")

for folder in ['properties','profiles','documents','blog','backups']:
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

def log_activity(action, details=None):
    try:
        db.session.add(ActivityLog(
            user_id=current_user.id if current_user.is_authenticated else None,
            action=action, details=details, ip_address=request.remote_addr))
        db.session.commit()
    except Exception: pass

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
    s = get_settings()
    ext = ExternalLink.query.filter_by(is_active=True).order_by(ExternalLink.sort_order).all()
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
    except Exception: pass

def clean(s, tags=None):
    allowed = tags or []
    return bleach.clean(s or '', tags=allowed, strip=True)

# ── PUBLIC ROUTES ────────────────────────────────────────────────────

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
                 'price':p.price,'type':p.property_type,'status':p.status,
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
    return render_template('owner/dashboard.html',total_props=total_props,total_inqs=total_inqs,
                           unread=unread,today_v=today_v,month_v=month_v,
                           top_props=top_props,recent_inqs=recent_inqs)

@app.route('/owner/properties')
@login_required
@owner_required
def owner_properties():
    page=request.args.get('page',1,type=int)
    props=Property.query.order_by(Property.created_at.desc()).paginate(page=page,per_page=20,error_out=False)
    return render_template('owner/properties.html',props=props)

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
        db.session.commit()
        log_activity('Add Property',title)
        flash('Property added!','success')
        return redirect(url_for('owner_properties'))
    prop_types=['Apartment','Villa','Office','Shop','Land','Warehouse','Residential','Commercial','Industrial','Agricultural','Luxury']
    return render_template('owner/property_form.html',prop=None,prop_types=prop_types,action='Add')

def _unique_slug(base, model):
    slug=base; n=1
    while model.query.filter_by(slug=slug).first(): slug=f"{base}-{n}"; n+=1
    return slug

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
        db.session.commit()
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
    return render_template('developer/dashboard.html',users=users,total_v=total_v,
                           total_p=total_p,total_i=total_i,logs=logs)

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
def init_db():
    with app.app_context():
        db.create_all()
        if not User.query.filter_by(role='developer').first():
            u=User(username='developer',email='dev@luxerealty.com',role='developer'); u.set_password('Dev@123456'); db.session.add(u)
        if not User.query.filter_by(role='owner').first():
            u=User(username='owner',email='owner@luxerealty.com',role='owner'); u.set_password('Owner@123456'); db.session.add(u)
        for k,v in SETTING_DEFAULTS.items():
            if not SiteSettings.query.filter_by(key=k).first():
                db.session.add(SiteSettings(key=k,value=v))
        db.session.commit()

if __name__=='__main__':
    init_db()
    app.run(debug=True)

# Compatibility redirect for flask-login's redirect
@app.route('/login')
def login_redirect():
    s = get_settings()
    return redirect(url_for('login', login_path=s.get('admin_path','admin')))
