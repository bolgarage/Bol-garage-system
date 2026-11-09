document.querySelectorAll('[data-password-toggle]').forEach(function (toggle) {
  var password = document.getElementById(toggle.getAttribute('aria-controls'));

  toggle.addEventListener('click', function () {
    var isVisible = password.type === 'text';
    password.type = isVisible ? 'password' : 'text';
    toggle.textContent = isVisible ? 'Show' : 'Hide';
    toggle.setAttribute('aria-label', (isVisible ? 'Show' : 'Hide') + ' password');
    toggle.setAttribute('aria-pressed', String(!isVisible));
  });
});
