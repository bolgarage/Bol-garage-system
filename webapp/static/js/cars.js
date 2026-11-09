/* Available cars page: brand filter */

(function () {
  var brands = ['All', 'Toyota', 'Honda', 'Mitsubishi', 'Nissan', 'Suzuki'];
  var current = 'All';

  var chipsEl = document.getElementById('brand-chips');
  var carsEl = document.getElementById('cars');
  var countEl = document.getElementById('count');

  function render() {
    chipsEl.innerHTML = brands.map(function (b) {
      return '<button type="button" class="chip' + (b === current ? ' is-active' : '') + '" data-brand="' + b + '">' + b + '</button>';
    }).join('');

    var shown = publicCars().filter(function (c) {
      return current === 'All' || c.brand === current;
    });

    carsEl.innerHTML = shown.map(carCardHtml).join('');
    countEl.textContent = 'Showing ' + shown.length + (shown.length === 1 ? ' car' : ' cars');
  }

  chipsEl.addEventListener('click', function (e) {
    var btn = e.target.closest('[data-brand]');
    if (!btn) return;
    current = btn.getAttribute('data-brand');
    render();
  });

  render();
})();
