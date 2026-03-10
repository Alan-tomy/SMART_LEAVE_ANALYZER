// ====== SIDEBAR TOGGLE ======
function toggleSidebar() {
  document.getElementById('sidebar').classList.toggle('open');
}

// ====== DATE IN TOPBAR ======
function updateDate() {
  const el = document.getElementById('topbarDate');
  if (!el) return;
  const now = new Date();
  el.textContent = now.toLocaleDateString('en-IN', {
    weekday: 'long', year: 'numeric', month: 'long', day: 'numeric'
  });
}
updateDate();

// ====== AUTO-DISMISS ALERTS ======
setTimeout(() => {
  document.querySelectorAll('.alert').forEach(a => a.remove());
}, 4000);

// ====== CLOSE MODAL ON OVERLAY CLICK ======
document.addEventListener('click', (e) => {
  if (e.target.classList.contains('modal-overlay')) {
    e.target.style.display = 'none';
  }
});

// ====== ACTIVE NAV HIGHLIGHT (redundant safety) ======
document.querySelectorAll('.nav-item').forEach(item => {
  item.addEventListener('click', () => {
    document.querySelectorAll('.nav-item').forEach(i => i.classList.remove('active'));
    item.classList.add('active');
  });
});
