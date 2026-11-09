(function () {
  var sidebar = document.querySelector('.sidebar');
  var toggle = document.querySelector('.sidebar-menu-toggle');

  if (!sidebar || !toggle) return;

  toggle.addEventListener('click', function () {
    var isOpen = sidebar.classList.toggle('is-menu-open');
    toggle.setAttribute('aria-expanded', String(isOpen));
    toggle.setAttribute('aria-label', isOpen ? 'Close garage menu' : 'Open garage menu');
  });
})();
