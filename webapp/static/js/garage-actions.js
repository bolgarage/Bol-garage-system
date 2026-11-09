var confirmationDialog = document.getElementById('confirmation-dialog');
var pendingConfirmationForm = null;

document.addEventListener('submit', function (event) {
  var form = event.target.closest('[data-confirmation-form]');
  if (!form || !confirmationDialog) return;

  event.preventDefault();
  pendingConfirmationForm = form;
  confirmationDialog.querySelector('#confirmation-dialog-title').textContent =
    form.getAttribute('data-confirmation-title');
  confirmationDialog.querySelector('#confirmation-dialog-message').textContent =
    form.getAttribute('data-confirmation-message');
  confirmationDialog.querySelector('[data-confirmation-submit]').textContent =
    form.getAttribute('data-confirmation-action-label') || 'Confirm';
  confirmationDialog.showModal();
});

if (confirmationDialog) {
  confirmationDialog.addEventListener('click', function (event) {
    if (event.target === confirmationDialog) {
      confirmationDialog.close();
    }
  });

  confirmationDialog.addEventListener('close', function () {
    pendingConfirmationForm = null;
  });

  confirmationDialog.querySelector('[data-confirmation-cancel]').addEventListener('click', function () {
    confirmationDialog.close();
  });

  confirmationDialog.querySelector('[data-confirmation-submit]').addEventListener('click', function () {
    if (pendingConfirmationForm) {
      pendingConfirmationForm.submit();
    }
  });
}
