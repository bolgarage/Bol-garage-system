document.addEventListener('click', function (event) {
  var editPaymentButton = event.target.closest('[data-edit-payment]');
  if (editPaymentButton && paymentEditDialog) {
    paymentEditId.value = editPaymentButton.getAttribute('data-payment-id');
    paymentEditForm.elements['edit-payment-buyer_name'].value = editPaymentButton.getAttribute('data-payment-buyer');
    paymentEditForm.elements['edit-payment-buyer_contact'].value = editPaymentButton.getAttribute('data-payment-contact');
    paymentEditForm.elements['edit-payment-account_name'].value = editPaymentButton.getAttribute('data-payment-account');
    paymentEditForm.elements['edit-payment-payment_type'].value = editPaymentButton.getAttribute('data-payment-type');
    paymentEditForm.elements['edit-payment-amount'].value = editPaymentButton.getAttribute('data-payment-amount');
    paymentEditForm.elements['edit-payment-date_received'].value = editPaymentButton.getAttribute('data-payment-date');
    paymentEditForm.elements['edit-payment-payment_method'].value = editPaymentButton.getAttribute('data-payment-method');
    paymentEditForm.elements['edit-payment-reference_number'].value = editPaymentButton.getAttribute('data-payment-reference');
    paymentEditForm.elements['edit-payment-notes'].value = editPaymentButton.getAttribute('data-payment-notes');
    paymentEditDialog.showModal();
  }

  var editExpenseButton = event.target.closest('[data-edit-expense]');
  if (editExpenseButton && expenseEditDialog) {
    expenseEditId.value = editExpenseButton.getAttribute('data-expense-id');
    expenseEditForm.elements.description.value = editExpenseButton.getAttribute('data-expense-description');
    expenseEditForm.elements.category.value = editExpenseButton.getAttribute('data-expense-category');
    expenseEditForm.elements.date.value = editExpenseButton.getAttribute('data-expense-date');
    expenseEditForm.elements.amount.value = editExpenseButton.getAttribute('data-expense-amount');
    expenseEditTitle.textContent = 'Edit expense: ' + editExpenseButton.getAttribute('data-expense-description');

    var receiptUrl = editExpenseButton.getAttribute('data-expense-receipt-url');
    currentReceipt.hidden = !receiptUrl;
    if (receiptUrl) {
      currentReceiptLink.href = receiptUrl;
    }

    expenseEditDialog.showModal();
  }

  var button = event.target.closest('[data-open-details]');
  if (button) {
    var details = document.getElementById(button.getAttribute('data-open-details'));
    if (details) {
      details.open = true;
      details.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
    }
  }

  var receiptLink = event.target.closest('[data-receipt-preview]');
  if (receiptLink && receiptDialog) {
    event.preventDefault();
    receiptImage.src = receiptLink.href;
    receiptImage.alt = receiptLink.getAttribute('data-receipt-alt');
    receiptDialog.showModal();
  }
});

var receiptDialog = document.getElementById('receipt-preview-dialog');
var receiptImage = document.getElementById('receipt-preview-image');
var expenseEditDialog = document.getElementById('expense-edit-dialog');
var expenseEditForm = document.getElementById('expense-edit-form');
var expenseEditId = document.getElementById('expense-edit-id');
var expenseEditTitle = document.getElementById('expense-edit-title');
var currentReceipt = document.querySelector('[data-current-receipt]');
var currentReceiptLink = document.querySelector('[data-current-receipt-link]');
var paymentEditDialog = document.getElementById('payment-edit-dialog');
var paymentEditForm = document.getElementById('payment-edit-form');
var paymentEditId = document.getElementById('payment-edit-id');

if (expenseEditDialog) {
  expenseEditDialog.addEventListener('click', function (event) {
    if (event.target === expenseEditDialog || event.target.closest('[data-expense-edit-close]')) {
      expenseEditDialog.close();
    }
  });

  if (expenseEditDialog.hasAttribute('data-open-on-load')) {
    expenseEditDialog.showModal();
  }
}

if (paymentEditDialog) {
  paymentEditDialog.addEventListener('click', function (event) {
    if (event.target === paymentEditDialog || event.target.closest('[data-payment-edit-close]')) {
      paymentEditDialog.close();
    }
  });

  if (paymentEditDialog.hasAttribute('data-open-on-load')) {
    paymentEditDialog.showModal();
  }
}

if (receiptDialog) {
  receiptDialog.addEventListener('click', function (event) {
    if (event.target === receiptDialog || event.target.closest('[data-receipt-close]')) {
      receiptDialog.close();
    }
  });

  receiptDialog.addEventListener('close', function () {
    receiptImage.removeAttribute('src');
    receiptImage.alt = '';
  });
}
