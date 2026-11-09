(function () {
  var durations = {
    success: 3000,
    info: 5000,
    warning: 8000,
    error: 8000
  };

  document.querySelectorAll('.site-message').forEach(function (notification) {
    var tags = notification.className.split(/\s+/);
    var type = tags.find(function (tag) {
      return tag.indexOf('site-message-') === 0;
    });
    var duration = durations[type ? type.replace('site-message-', '') : 'info'] || 5000;
    var timeout;

    function dismiss() {
      window.clearTimeout(timeout);
      notification.classList.add('is-dismissing');
      notification.addEventListener('transitionend', function () {
        notification.remove();
      }, { once: true });
      window.setTimeout(function () {
        notification.remove();
      }, 250);
    }

    notification.querySelector('.site-message-dismiss').addEventListener('click', dismiss);
    timeout = window.setTimeout(dismiss, duration);
  });
})();
