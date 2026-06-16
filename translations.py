# ── TRANSLATIONS ────────────────────────────────────────────────────
# Static UI string translations for English / Hindi / Arabic.
# Used via the `t(key)` template helper. Keys are short identifiers;
# values are dicts of {lang_code: translated_string}.
#
# Only static interface chrome is translated here (nav, buttons, labels,
# section headings). User-entered content (property titles, descriptions,
# blog posts, etc.) is shown as-entered regardless of selected language.

SUPPORTED_LANGUAGES = {
    'en': {'name': 'English', 'native': 'English', 'dir': 'ltr'},
    'hi': {'name': 'Hindi', 'native': 'हिन्दी', 'dir': 'ltr'},
    'ar': {'name': 'Arabic', 'native': 'العربية', 'dir': 'rtl'},
}

DEFAULT_LANGUAGE = 'en'

TRANSLATIONS = {
    # ── Navigation ──
    'nav_home': {'en': 'Home', 'hi': 'होम', 'ar': 'الرئيسية'},
    'nav_properties': {'en': 'Properties', 'hi': 'सम्पत्तियाँ', 'ar': 'العقارات'},
    'nav_about': {'en': 'About', 'hi': 'हमारे बारे में', 'ar': 'من نحن'},
    'nav_blog': {'en': 'Blog', 'hi': 'ब्लॉग', 'ar': 'المدونة'},
    'nav_contact': {'en': 'Contact', 'hi': 'संपर्क करें', 'ar': 'اتصل بنا'},
    'nav_call_now': {'en': 'Call Now', 'hi': 'कॉल करें', 'ar': 'اتصل الآن'},
    'nav_admin': {'en': 'Admin', 'hi': 'एडमिन', 'ar': 'الإدارة'},

    # ── Hero / Search ──
    'search_buy': {'en': 'Buy', 'hi': 'खरीदें', 'ar': 'شراء'},
    'search_rent': {'en': 'Rent', 'hi': 'किराये पर लें', 'ar': 'إيجار'},
    'search_placeholder': {'en': 'Search city, locality, project...', 'hi': 'शहर, इलाका, प्रोजेक्ट खोजें...', 'ar': 'ابحث عن مدينة أو منطقة أو مشروع...'},
    'search_property_type': {'en': 'Property Type', 'hi': 'सम्पत्ति का प्रकार', 'ar': 'نوع العقار'},
    'search_bedrooms': {'en': 'Bedrooms', 'hi': 'बेडरूम', 'ar': 'غرف النوم'},
    'search_btn': {'en': 'Search', 'hi': 'खोजें', 'ar': 'بحث'},

    # ── Sections ──
    'browse_by_type': {'en': 'Browse By Type', 'hi': 'प्रकार के अनुसार देखें', 'ar': 'تصفح حسب النوع'},
    'property_categories': {'en': 'Property Categories', 'hi': 'सम्पत्ति श्रेणियाँ', 'ar': 'فئات العقارات'},
    'hand_picked': {'en': 'Hand-Picked', 'hi': 'चुनी हुई', 'ar': 'مختارة بعناية'},
    'featured_properties': {'en': 'Featured Properties', 'hi': 'विशेष सम्पत्तियाँ', 'ar': 'العقارات المميزة'},
    'new_listings': {'en': 'New Listings', 'hi': 'नई लिस्टिंग', 'ar': 'أحدث العقارات'},
    'latest_properties': {'en': 'Latest Properties', 'hi': 'नवीनतम सम्पत्तियाँ', 'ar': 'أحدث العقارات المضافة'},
    'view_all': {'en': 'View All', 'hi': 'सभी देखें', 'ar': 'عرض الكل'},
    'meet_your_agent': {'en': 'Meet Your Agent', 'hi': 'अपने एजेंट से मिलें', 'ar': 'تعرف على وكيلك'},
    'what_clients_say': {'en': 'What Clients Say', 'hi': 'ग्राहकों की राय', 'ar': 'ماذا يقول عملاؤنا'},
    'testimonials': {'en': 'Testimonials', 'hi': 'प्रशंसापत्र', 'ar': 'الشهادات'},
    'got_questions': {'en': 'Got Questions?', 'hi': 'सवाल है?', 'ar': 'لديك أسئلة؟'},
    'frequently_asked': {'en': 'Frequently Asked', 'hi': 'सामान्य प्रश्न', 'ar': 'الأسئلة الشائعة'},
    'ready_to_find': {'en': 'Ready to Find Your Dream Property?', 'hi': 'अपनी पसंदीदा सम्पत्ति खोजने के लिए तैयार हैं?', 'ar': 'هل أنت مستعد للعثور على عقار أحلامك؟'},
    'cta_subtitle': {'en': 'Our experts are here to guide you every step of the way.', 'hi': 'हमारे विशेषज्ञ हर कदम पर आपका मार्गदर्शन करने के लिए तैयार हैं।', 'ar': 'خبراؤنا هنا لمساعدتك في كل خطوة.'},
    'get_in_touch': {'en': 'Get In Touch', 'hi': 'संपर्क करें', 'ar': 'تواصل معنا'},

    # ── Property card / listing ──
    'view_details': {'en': 'View Details', 'hi': 'विवरण देखें', 'ar': 'عرض التفاصيل'},
    'featured': {'en': 'Featured', 'hi': 'विशेष', 'ar': 'مميز'},
    'builder_project': {'en': 'Builder Project', 'hi': 'बिल्डर प्रोजेक्ट', 'ar': 'مشروع المطور'},
    'compare': {'en': 'Compare', 'hi': 'तुलना करें', 'ar': 'مقارنة'},
    'price_on_request': {'en': 'Price on Request', 'hi': 'मूल्य पूछताछ पर', 'ar': 'السعر عند الطلب'},
    'bed': {'en': 'Bed', 'hi': 'बेड', 'ar': 'غرفة نوم'},
    'bath': {'en': 'Bath', 'hi': 'बाथरूम', 'ar': 'حمام'},
    'park': {'en': 'Park', 'hi': 'पार्किंग', 'ar': 'موقف سيارات'},
    'for_sale': {'en': 'For Sale', 'hi': 'बिक्री के लिए', 'ar': 'للبيع'},
    'for_rent': {'en': 'For Rent', 'hi': 'किराये के लिए', 'ar': 'للإيجار'},

    # ── Properties listing page ──
    'all_properties': {'en': 'All Properties', 'hi': 'सभी सम्पत्तियाँ', 'ar': 'جميع العقارات'},
    'filters': {'en': 'Filters', 'hi': 'फ़िल्टर', 'ar': 'الفلاتر'},
    'min_price': {'en': 'Min Price', 'hi': 'न्यूनतम मूल्य', 'ar': 'أقل سعر'},
    'max_price': {'en': 'Max Price', 'hi': 'अधिकतम मूल्य', 'ar': 'أعلى سعر'},
    'builder_projects_only': {'en': 'Builder Projects Only', 'hi': 'केवल बिल्डर प्रोजेक्ट', 'ar': 'مشاريع المطورين فقط'},
    'map_view': {'en': 'Map View', 'hi': 'मैप व्यू', 'ar': 'عرض الخريطة'},
    'list_view': {'en': 'List View', 'hi': 'लिस्ट व्यू', 'ar': 'عرض القائمة'},
    'no_properties_found': {'en': 'No Properties Found', 'hi': 'कोई सम्पत्ति नहीं मिली', 'ar': 'لم يتم العثور على عقارات'},
    'try_adjusting_filters': {'en': 'Try adjusting your filters or search criteria.', 'hi': 'अपने फ़िल्टर या खोज मानदंड बदलकर देखें।', 'ar': 'حاول تعديل الفلاتر أو معايير البحث.'},

    # ── Property detail page ──
    'about_property': {'en': 'About This Property', 'hi': 'इस सम्पत्ति के बारे में', 'ar': 'عن هذا العقار'},
    'property_details': {'en': 'Property Details', 'hi': 'सम्पत्ति विवरण', 'ar': 'تفاصيل العقار'},
    'amenities_features': {'en': 'Amenities & Features', 'hi': 'सुविधाएँ और विशेषताएँ', 'ar': 'المرافق والمميزات'},
    'location_on_map': {'en': 'Location on Map', 'hi': 'मानचित्र पर स्थान', 'ar': 'الموقع على الخريطة'},
    'get_directions': {'en': 'Get Directions', 'hi': 'दिशा प्राप्त करें', 'ar': 'الحصول على الاتجاهات'},
    'open_in_google_maps': {'en': 'Open in Google Maps', 'hi': 'गूगल मैप्स में खोलें', 'ar': 'افتح في خرائط جوجل'},
    'show_nearby_places': {'en': 'Show Nearby Places', 'hi': 'आस-पास के स्थान दिखाएँ', 'ar': 'إظهار الأماكن القريبة'},
    'similar_properties': {'en': 'Similar Properties', 'hi': 'समान सम्पत्तियाँ', 'ar': 'عقارات مماثلة'},
    'send_inquiry': {'en': 'Send Inquiry', 'hi': 'पूछताछ भेजें', 'ar': 'إرسال استعلام'},
    'your_name': {'en': 'Your Name', 'hi': 'आपका नाम', 'ar': 'اسمك'},
    'email_address': {'en': 'Email Address', 'hi': 'ईमेल पता', 'ar': 'البريد الإلكتروني'},
    'phone_number': {'en': 'Phone Number', 'hi': 'फ़ोन नंबर', 'ar': 'رقم الهاتف'},
    'call_agent': {'en': 'Call Agent', 'hi': 'एजेंट को कॉल करें', 'ar': 'اتصل بالوكيل'},
    'download_brochure': {'en': 'Download Brochure', 'hi': 'ब्रोशर डाउनलोड करें', 'ar': 'تحميل الكتيب'},
    'video_gallery': {'en': 'Video Gallery', 'hi': 'वीडियो गैलरी', 'ar': 'معرض الفيديو'},
    'floor_plans': {'en': 'Floor Plans', 'hi': 'फ्लोर प्लान', 'ar': 'مخططات الطوابق'},
    'project_information': {'en': 'Project Information', 'hi': 'प्रोजेक्ट जानकारी', 'ar': 'معلومات المشروع'},
    'a_project_by': {'en': 'A Project by', 'hi': 'एक प्रोजेक्ट', 'ar': 'مشروع من قبل'},
    'emi_calculator': {'en': 'EMI / Mortgage Calculator', 'hi': 'ईएमआई / मॉर्गेज कैलकुलेटर', 'ar': 'حاسبة التمويل العقاري'},
    'property_price': {'en': 'Property Price', 'hi': 'सम्पत्ति मूल्य', 'ar': 'سعر العقار'},
    'down_payment': {'en': 'Down Payment', 'hi': 'डाउन पेमेंट', 'ar': 'الدفعة الأولى'},
    'loan_amount': {'en': 'Loan Amount', 'hi': 'ऋण राशि', 'ar': 'مبلغ القرض'},
    'interest_rate': {'en': 'Interest Rate (% p.a.)', 'hi': 'ब्याज दर (% प्रति वर्ष)', 'ar': 'معدل الفائدة (% سنوياً)'},
    'loan_tenure': {'en': 'Loan Tenure (years)', 'hi': 'ऋण अवधि (वर्ष)', 'ar': 'مدة القرض (سنوات)'},
    'monthly_emi': {'en': 'Monthly EMI', 'hi': 'मासिक ईएमआई', 'ar': 'الدفعة الشهرية'},
    'principal': {'en': 'Principal', 'hi': 'मूलधन', 'ar': 'رأس المال'},
    'total_interest': {'en': 'Total Interest', 'hi': 'कुल ब्याज', 'ar': 'إجمالي الفائدة'},
    'total_payment': {'en': 'Total Payment', 'hi': 'कुल भुगतान', 'ar': 'إجمالي الدفعات'},

    # ── Compare page ──
    'compare_properties': {'en': 'Compare Properties', 'hi': 'सम्पत्तियों की तुलना करें', 'ar': 'مقارنة العقارات'},
    'compare_now': {'en': 'Compare Now', 'hi': 'अभी तुलना करें', 'ar': 'قارن الآن'},
    'clear': {'en': 'Clear', 'hi': 'साफ़ करें', 'ar': 'مسح'},
    'not_enough_selected': {'en': 'Not Enough Properties Selected', 'hi': 'पर्याप्त सम्पत्तियाँ चयनित नहीं हैं', 'ar': 'لم يتم تحديد عقارات كافية'},
    'select_2_4_properties': {'en': 'Select 2-4 properties using the "Compare" checkbox on listing cards, then click "Compare Now".', 'hi': 'लिस्टिंग कार्ड पर "तुलना करें" चेकबॉक्स का उपयोग करके 2-4 सम्पत्तियाँ चुनें, फिर "अभी तुलना करें" पर क्लिक करें।', 'ar': 'حدد 2-4 عقارات باستخدام مربع "مقارنة" على البطاقات، ثم اضغط على "قارن الآن".'},
    'browse_properties': {'en': 'Browse Properties', 'hi': 'सम्पत्तियाँ देखें', 'ar': 'تصفح العقارات'},

    # ── Footer ──
    'quick_links': {'en': 'Quick Links', 'hi': 'त्वरित लिंक', 'ar': 'روابط سريعة'},
    'property_types': {'en': 'Property Types', 'hi': 'सम्पत्ति प्रकार', 'ar': 'أنواع العقارات'},
    'contact_us': {'en': 'Contact Us', 'hi': 'संपर्क करें', 'ar': 'اتصل بنا'},
    'all_rights_reserved': {'en': 'All Rights Reserved.', 'hi': 'सर्वाधिकार सुरक्षित।', 'ar': 'جميع الحقوق محفوظة.'},
    'whatsapp_us': {'en': 'WhatsApp Us', 'hi': 'व्हाट्सएप करें', 'ar': 'واتساب'},
}


def t(key, lang='en'):
    """Translate a UI string key into the given language. Falls back to
    English, then to the key itself if no translation is found."""
    entry = TRANSLATIONS.get(key)
    if not entry:
        return key
    return entry.get(lang) or entry.get(DEFAULT_LANGUAGE) or key
