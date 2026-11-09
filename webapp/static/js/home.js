/* Home page: featured cars and recently sold */

(function () {
  var featured = publicCars().slice(0, 3);
  document.getElementById('featured').innerHTML = featured.map(carCardHtml).join('');

  var sold = BOL.cars.filter(function (c) { return c.status === 'Sold'; });
  document.getElementById('sold').innerHTML = sold.map(function (c) {
    return (
      '<div class="sold-card">' +
        '<div class="photo"></div>' +
        '<div>' +
          '<h3>' + c.name + '</h3>' +
          '<p class="car-specs">' + c.year + ' · ' + c.trans + ' · ' + c.fuel + '</p>' +
          pill('Sold') +
        '</div>' +
      '</div>'
    );
  }).join('');
})();
