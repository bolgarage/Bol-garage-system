(function () {
  var header = document.querySelector('.site-header');
  var toggle = document.querySelector('.menu-toggle');
  var navigation = document.getElementById('site-navigation');

  if (!header || !toggle || !navigation) return;

  toggle.addEventListener('click', function () {
    var isOpen = header.classList.toggle('is-menu-open');
    toggle.setAttribute('aria-expanded', String(isOpen));
    toggle.setAttribute('aria-label', isOpen ? 'Close navigation menu' : 'Open navigation menu');
  });
})();
