/* Car detail page: photo gallery, specs, inquiry form */

(function () {
  var car = BOL.cars[0]; // Toyota Vios in this mockup
  var photoCount = 5;
  var current = 0;

  var mainEl = document.getElementById('photo-main');
  var thumbsEl = document.getElementById('thumbs');

  function renderGallery() {
    mainEl.textContent = 'Photo ' + (current + 1) + ' of ' + photoCount + ' placeholder';
    var html = '';
    for (var i = 0; i < photoCount; i++) {
      html += '<button type="button" class="thumb' + (i === current ? ' is-active' : '') +
              '" data-index="' + i + '" aria-label="Show photo ' + (i + 1) + '">' + (i + 1) + '</button>';
    }
    thumbsEl.innerHTML = html;
  }

  thumbsEl.addEventListener('click', function (e) {
    var btn = e.target.closest('[data-index]');
    if (!btn) return;
    current = Number(btn.getAttribute('data-index'));
    renderGallery();
  });

  // Specifications
  var specs = [
    ['Year', car.year],
    ['Mileage', car.km.toLocaleString('en-US') + ' km'],
    ['Transmission', car.trans],
    ['Fuel', car.fuel],
    ['Body type', 'Sedan'],
    ['Color', 'Silver'],
    ['Engine', '1.3 L']
  ];
  document.getElementById('specs').innerHTML = specs.map(function (s) {
    return '<div class="spec-row"><span>' + s[0] + '</span><span>' + s[1] + '</span></div>';
  }).join('');

  // Inquiry form -> confirmation message
  function showSent() {
    document.getElementById('inquiry-form').classList.add('hidden');
    document.getElementById('inquiry-sent').classList.remove('hidden');
  }
  document.getElementById('btn-inquire').addEventListener('click', showSent);
  document.getElementById('btn-reserve').addEventListener('click', showSent);

  // Related cars
  var related = publicCars().filter(function (c) { return c.id !== car.id; }).slice(3, 6);
  document.getElementById('related').innerHTML = related.map(function (c) {
    return (
      '<a href="car-detail.html" class="car-card">' +
        '<div class="photo" style="height: 130px;"></div>' +
        '<div class="car-card-body">' +
          '<h3>' + c.name + '</h3>' +
          '<p class="car-specs">' + c.year + ' · ' + c.km.toLocaleString('en-US') + ' km · ' + c.trans + '</p>' +
          '<div class="car-price" style="font-size: 24px;">' + peso(c.price) + '</div>' +
        '</div>' +
      '</a>'
    );
  }).join('');

  renderGallery();
})();
