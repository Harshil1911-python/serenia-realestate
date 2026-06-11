// ── SIDEBAR TOGGLE ──
const sidebar = document.getElementById('sidebar');
const sidebarToggle = document.getElementById('sidebarToggle');
const sidebarClose = document.getElementById('sidebarClose');
const sidebarOverlay = document.getElementById('sidebarOverlay');

function openSidebar() {
  sidebar && sidebar.classList.add('open');
  sidebarOverlay && sidebarOverlay.classList.add('active');
  document.body.style.overflow = 'hidden';
}
function closeSidebar() {
  sidebar && sidebar.classList.remove('open');
  sidebarOverlay && sidebarOverlay.classList.remove('active');
  document.body.style.overflow = '';
}

sidebarToggle && sidebarToggle.addEventListener('click', openSidebar);
sidebarClose && sidebarClose.addEventListener('click', closeSidebar);
sidebarOverlay && sidebarOverlay.addEventListener('click', closeSidebar);

// ── AUTO-DISMISS ALERTS ──
setTimeout(() => {
  document.querySelectorAll('.alert').forEach(a => {
    a.style.opacity = '0';
    a.style.transition = 'opacity 0.4s';
    setTimeout(() => a.remove(), 400);
  });
}, 5000);

// ── CONFIRM DELETE ──
document.querySelectorAll('[data-confirm]').forEach(btn => {
  btn.addEventListener('click', e => {
    if (!confirm(btn.dataset.confirm)) e.preventDefault();
  });
});

// ── TABLE ROW CLICK ──
document.querySelectorAll('tr[data-href]').forEach(row => {
  row.style.cursor = 'pointer';
  row.addEventListener('click', () => window.location = row.dataset.href);
});

// ── ACTIVE NAV HIGHLIGHT ──
const currentPath = window.location.pathname;
document.querySelectorAll('.nav-item').forEach(item => {
  if (item.getAttribute('href') === currentPath) {
    item.classList.add('active');
  }
});
