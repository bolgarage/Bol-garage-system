(function () {
  var avatarInput = document.querySelector('[data-avatar-input]');
  var avatarPreview = document.querySelector('[data-avatar-preview]');
  var avatarInitial = document.querySelector('[data-avatar-initial]');
  var avatarFileName = document.querySelector('[data-avatar-file-name]');
  var clearAvatar = document.querySelector('#id_clear_avatar');

  if (avatarInput && avatarPreview && avatarInitial) {
    var googleAvatar = avatarPreview.dataset.googleAvatar || '';
    var selectedAvatarUrl = '';

    function showAvatar(src) {
      avatarPreview.src = src;
      avatarPreview.hidden = !src;
      avatarInitial.hidden = Boolean(src);
    }

    avatarInput.addEventListener('change', function () {
      var file = avatarInput.files && avatarInput.files[0];
      if (!file) return;

      if (selectedAvatarUrl) URL.revokeObjectURL(selectedAvatarUrl);
      selectedAvatarUrl = URL.createObjectURL(file);
      showAvatar(selectedAvatarUrl);
      if (clearAvatar) clearAvatar.checked = false;
      if (avatarFileName) {
        avatarFileName.textContent = file.name + ' selected. Save profile to apply it.';
        avatarFileName.hidden = false;
      }
    });

    if (clearAvatar) {
      clearAvatar.addEventListener('change', function () {
        if (!clearAvatar.checked) return;
        avatarInput.value = '';
        if (selectedAvatarUrl) {
          URL.revokeObjectURL(selectedAvatarUrl);
          selectedAvatarUrl = '';
        }
        if (avatarFileName) avatarFileName.hidden = true;
        showAvatar(googleAvatar);
      });
    }
  }

  var form = document.querySelector('[data-delete-account-form]');
  if (!form) return;

  var input = form.querySelector('[data-delete-confirmation]');
  var submit = form.querySelector('[data-delete-account-submit]');
  if (!input || !submit) return;

  function updateSubmitState() {
    submit.disabled = input.value !== 'DELETE';
  }

  input.addEventListener('input', updateSubmitState);
  updateSubmitState();
})();
