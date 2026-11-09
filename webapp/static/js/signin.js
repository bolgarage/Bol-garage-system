/* Sign in page: switch between the Sign in and Sign up tabs */

(function () {
  var tabIn = document.getElementById('tab-signin');
  var tabUp = document.getElementById('tab-signup');
  var formIn = document.getElementById('form-signin');
  var formUp = document.getElementById('form-signup');

  function show(signUp) {
    tabIn.classList.toggle('is-active', !signUp);
    tabUp.classList.toggle('is-active', signUp);
    formIn.classList.toggle('hidden', signUp);
    formUp.classList.toggle('hidden', !signUp);
  }

  tabIn.addEventListener('click', function () { show(false); });
  tabUp.addEventListener('click', function () { show(true); });

  // Open directly on the Sign up tab with /signin/#signup
  if (location.hash === '#signup') show(true);
})();
