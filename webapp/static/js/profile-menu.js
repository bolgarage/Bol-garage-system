(function () {
  var menus = document.querySelectorAll('.profile-menu');

  menus.forEach(function (menu) {
    var toggle = menu.querySelector('[data-profile-menu-toggle]');
    var dropdown = menu.querySelector('.profile-dropdown');

    if (!toggle || !dropdown) return;

    function closeMenu(returnFocus) {
      dropdown.hidden = true;
      toggle.setAttribute('aria-expanded', 'false');
      if (returnFocus) toggle.focus();
    }

    toggle.addEventListener('click', function () {
      var isOpen = toggle.getAttribute('aria-expanded') === 'true';
      dropdown.hidden = isOpen;
      toggle.setAttribute('aria-expanded', String(!isOpen));
    });

    document.addEventListener('click', function (event) {
      if (!menu.contains(event.target)) closeMenu(false);
    });

    menu.addEventListener('keydown', function (event) {
      if (event.key === 'Escape' && !dropdown.hidden) {
        event.preventDefault();
        closeMenu(true);
      }

      if (event.key === 'ArrowDown' && event.target === toggle) {
        event.preventDefault();
        dropdown.hidden = false;
        toggle.setAttribute('aria-expanded', 'true');
        dropdown.querySelector('[role="menuitem"]').focus();
      }
    });
  });
})();
