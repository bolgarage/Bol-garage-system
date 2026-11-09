(function () {
  var dialog = document.querySelector('[data-inquiry-status-dialog]');
  var openButton = document.querySelector('[data-inquiry-status-open]');
  var closeButton = document.querySelector('[data-inquiry-status-close]');
  if (!dialog || !openButton || !closeButton) return;

  openButton.addEventListener('click', function () {
    dialog.showModal();
  });

  closeButton.addEventListener('click', function () {
    dialog.close();
  });

  dialog.addEventListener('click', function (event) {
    if (event.target === dialog) dialog.close();
  });
})();
