// ── NAVBAR SCROLL ──
const navbar = document.getElementById('navbar');
if (navbar) {
  window.addEventListener('scroll', () => {
    navbar.classList.toggle('scrolled', window.scrollY > 50);
  });
}

// ── MOBILE NAV TOGGLE ──
const navToggle = document.getElementById('navToggle');
const navMenu = document.getElementById('navMenu');
if (navToggle && navMenu) {
  navToggle.addEventListener('click', () => {
    navMenu.classList.toggle('open');
    navToggle.classList.toggle('active');
    document.body.style.overflow = navMenu.classList.contains('open') ? 'hidden' : '';
  });
  // Close on outside click
  document.addEventListener('click', (e) => {
    if (!navToggle.contains(e.target) && !navMenu.contains(e.target)) {
      navMenu.classList.remove('open');
      navToggle.classList.remove('active');
      document.body.style.overflow = '';
    }
  });
  // Close on nav link click
  navMenu.querySelectorAll('.nav-link').forEach(link => {
    link.addEventListener('click', () => {
      navMenu.classList.remove('open');
      navToggle.classList.remove('active');
      document.body.style.overflow = '';
    });
  });
}

// ── SEARCH TABS ──
document.querySelectorAll('.search-tab').forEach(tab => {
  tab.addEventListener('click', () => {
    document.querySelectorAll('.search-tab').forEach(t => t.classList.remove('active'));
    tab.classList.add('active');
    const listingInput = document.getElementById('listingType');
    if (listingInput) listingInput.value = tab.dataset.listing;
  });
});

// ── FAQ TOGGLE ──
function toggleFaq(btn) {
  const item = btn.closest('.faq-item');
  const isOpen = item.classList.contains('open');
  // Close all
  document.querySelectorAll('.faq-item.open').forEach(i => {
    i.classList.remove('open');
    i.querySelector('.faq-answer').style.maxHeight = null;
  });
  // Open clicked if it was closed
  if (!isOpen) {
    item.classList.add('open');
    const answer = item.querySelector('.faq-answer');
    answer.style.maxHeight = answer.scrollHeight + 'px';
  }
}

// ── SECTION REVEAL (simple IntersectionObserver) ──
const revealEls = document.querySelectorAll('[data-aos]');
if (revealEls.length && 'IntersectionObserver' in window) {
  const observer = new IntersectionObserver((entries) => {
    entries.forEach(entry => {
      if (entry.isIntersecting) {
        entry.target.classList.add('aos-animate');
        observer.unobserve(entry.target);
      }
    });
  }, { threshold: 0.1, rootMargin: '0px 0px -40px 0px' });
  revealEls.forEach(el => {
    el.style.opacity = '0';
    el.style.transform = 'translateY(24px)';
    el.style.transition = `opacity 0.55s ease ${el.dataset.aosDelay || 0}ms, transform 0.55s ease ${el.dataset.aosDelay || 0}ms`;
    observer.observe(el);
  });
}
document.addEventListener('DOMContentLoaded', () => {
  document.querySelectorAll('[data-aos].aos-animate').forEach(el => {
    el.style.opacity = '1';
    el.style.transform = 'none';
  });
});
// Fallback: add class when visible
window.addEventListener('scroll', () => {
  document.querySelectorAll('[data-aos]:not(.aos-animate)').forEach(el => {
    const rect = el.getBoundingClientRect();
    if (rect.top < window.innerHeight - 40) {
      el.classList.add('aos-animate');
      el.style.opacity = '1';
      el.style.transform = 'none';
    }
  });
}, { passive: true });
// Trigger on load
setTimeout(() => {
  document.querySelectorAll('[data-aos]').forEach(el => {
    const rect = el.getBoundingClientRect();
    if (rect.top < window.innerHeight) {
      el.classList.add('aos-animate');
      el.style.opacity = '1';
      el.style.transform = 'none';
    }
  });
}, 100);

// ── AUTO-DISMISS FLASH MESSAGES ──
setTimeout(() => {
  document.querySelectorAll('.flash').forEach(f => {
    f.style.opacity = '0';
    f.style.transform = 'translateX(100%)';
    f.style.transition = 'all 0.4s ease';
    setTimeout(() => f.remove(), 400);
  });
}, 4000);

// ── SMOOTH SCROLL FOR ANCHOR LINKS ──
document.querySelectorAll('a[href^="#"]').forEach(a => {
  a.addEventListener('click', e => {
    const target = document.querySelector(a.getAttribute('href'));
    if (target) {
      e.preventDefault();
      target.scrollIntoView({ behavior: 'smooth', block: 'start' });
    }
  });
});

// ── PROPERTY COMPARISON ──
const COMPARE_KEY = 'luxe_compare_ids';
const COMPARE_MAX = 4;

function getCompareList() {
  try {
    return JSON.parse(localStorage.getItem(COMPARE_KEY)) || [];
  } catch (e) {
    return [];
  }
}

function saveCompareList(list) {
  localStorage.setItem(COMPARE_KEY, JSON.stringify(list));
}

function toggleCompare(checkbox) {
  let list = getCompareList();
  const id = checkbox.dataset.id;
  const title = checkbox.dataset.title;

  if (checkbox.checked) {
    if (list.length >= COMPARE_MAX) {
      checkbox.checked = false;
      alert(`You can compare up to ${COMPARE_MAX} properties at a time. Remove one first.`);
      return;
    }
    if (!list.find(item => item.id === id)) {
      list.push({ id, title });
    }
  } else {
    list = list.filter(item => item.id !== id);
  }
  saveCompareList(list);
  renderCompareBar();
}

function clearCompare() {
  saveCompareList([]);
  document.querySelectorAll('.compare-checkbox').forEach(cb => cb.checked = false);
  renderCompareBar();
}

function removeFromCompare(id) {
  let list = getCompareList().filter(item => item.id !== id);
  saveCompareList(list);
  document.querySelectorAll(`.compare-checkbox[data-id="${id}"]`).forEach(cb => cb.checked = false);
  renderCompareBar();
}

function renderCompareBar() {
  const bar = document.getElementById('compareBar');
  if (!bar) return;
  const list = getCompareList();

  document.getElementById('compareCount').textContent = list.length;

  const itemsEl = document.getElementById('compareBarItems');
  itemsEl.innerHTML = list.map(item =>
    `<span class="compare-bar-chip">${item.title.length > 22 ? item.title.slice(0,22)+'…' : item.title}<button onclick="removeFromCompare('${item.id}')" aria-label="Remove">&times;</button></span>`
  ).join('');

  const btn = document.getElementById('compareBarBtn');
  if (list.length >= 2) {
    bar.classList.add('active');
    btn.classList.remove('disabled');
    btn.href = '/compare?ids=' + list.map(i => i.id).join(',');
  } else if (list.length === 1) {
    bar.classList.add('active');
    btn.classList.add('disabled');
    btn.removeAttribute('href');
  } else {
    bar.classList.remove('active');
  }
}

// Restore checkbox state on page load + render bar
document.addEventListener('DOMContentLoaded', () => {
  const list = getCompareList();
  const ids = new Set(list.map(i => i.id));
  document.querySelectorAll('.compare-checkbox').forEach(cb => {
    if (ids.has(cb.dataset.id)) cb.checked = true;
  });
  renderCompareBar();
});

// ── LANGUAGE DROPDOWN CLOSE ON OUTSIDE CLICK ──
document.addEventListener('click', (e) => {
  const dropdown = document.getElementById('langDropdown');
  if (dropdown && !e.target.closest('.lang-switcher')) {
    dropdown.classList.remove('open');
  }
});
