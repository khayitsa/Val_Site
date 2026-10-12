/* Forms: stop double submits (a second click on "Place order" could create a
   duplicate order) and clear a field's server error as soon as it is edited. */
(function () {
  document.addEventListener('submit', function (e) {
    var form = e.target;
    if (!(form instanceof HTMLFormElement) || e.defaultPrevented) return;
    if (form.dataset.submitting === '1') { e.preventDefault(); return; }
    form.dataset.submitting = '1';
    form.querySelectorAll('button[type=submit], input[type=submit]').forEach(function (b) {
      b.setAttribute('disabled', 'disabled');
      b.setAttribute('aria-busy', 'true');
    });
  });
  /* Restore buttons if the visitor comes back with the browser's Back button. */
  window.addEventListener('pageshow', function (e) {
    if (!e.persisted) return;
    document.querySelectorAll('form[data-submitting]').forEach(function (f) {
      delete f.dataset.submitting;
      f.querySelectorAll('[disabled]').forEach(function (b) { b.removeAttribute('disabled'); b.removeAttribute('aria-busy'); });
    });
  });
  document.addEventListener('input', function (e) {
    var field = e.target.closest && e.target.closest('.field');
    if (field) field.querySelectorAll('.field-error').forEach(function (x) { x.remove(); });
  });
})();

/* Shared header behaviour: scroll shadow + mobile menu. */
(function () {
  var header = document.getElementById('siteHeader');
  var burger = document.getElementById('burger');
  var menu = document.getElementById('navlinks');
  if (!header) return;

  window.addEventListener('scroll', function () {
    header.classList.toggle('scrolled', window.scrollY > 20);
  }, { passive: true });

  if (!burger || !menu) return;

  function setOpen(open) {
    menu.classList.toggle('open', open);
    burger.classList.toggle('open', open);
    burger.setAttribute('aria-expanded', open ? 'true' : 'false');
    burger.setAttribute('aria-label', open ? 'Close menu' : 'Open menu');
    document.body.classList.toggle('nav-open', open);
  }

  burger.addEventListener('click', function () {
    setOpen(!menu.classList.contains('open'));
  });
  menu.addEventListener('click', function (e) {
    if (e.target.closest('a')) setOpen(false);
  });
  document.addEventListener('keydown', function (e) {
    if (e.key === 'Escape') setOpen(false);
  });
  window.addEventListener('resize', function () {
    if (window.innerWidth > 768) setOpen(false);
  });
})();
