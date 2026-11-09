/* ==========================================================
   Bol Garage mockup - small helpers used by every page
   ========================================================== */

// 465000 -> "₱465,000"
function peso(n) {
  return '₱' + String(n).replace(/\B(?=(\d{3})+(?!\d))/g, ',');
}

// "Under repair" -> "pill pill-under-repair"
function pillClass(status) {
  return 'pill pill-' + status.toLowerCase().replace(/\s+/g, '-');
}

function pill(status) {
  return '<span class="' + pillClass(status) + '">' + status + '</span>';
}

// Cars the public can see
function publicCars() {
  return BOL.cars.filter(function (c) {
    return c.status === 'Available' || c.status === 'Reserved';
  });
}

function specLine(c) {
  return c.year + ' · ' + c.km.toLocaleString('en-US') + ' km · ' + c.trans + ' · ' + c.fuel;
}

// One public car card (used on Home and Available cars)
function carCardHtml(c) {
  return (
    '<a href="car-detail.html" class="car-card">' +
      '<div class="photo">Photo placeholder</div>' +
      '<div class="car-card-body">' +
        '<div class="car-card-top"><h3>' + c.name + '</h3>' + pill(c.status) + '</div>' +
        '<p class="car-specs">' + specLine(c) + '</p>' +
        '<div class="car-price">' + peso(c.price) + '</div>' +
      '</div>' +
    '</a>'
  );
}
