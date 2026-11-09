/* Admin inventory: status tabs and the car table */

(function () {
  var names = ['All', 'Incoming', 'Under repair', 'Available', 'Reserved', 'Sold'];
  var current = 'All';

  var tabsEl = document.getElementById('tabs');
  var rowsEl = document.getElementById('rows');

  function countFor(name) {
    if (name === 'All') return BOL.cars.length;
    return BOL.cars.filter(function (c) { return c.status === name; }).length;
  }

  function render() {
    tabsEl.innerHTML = names.map(function (n) {
      return '<button type="button" class="chip' + (n === current ? ' is-active' : '') + '" data-tab="' + n + '">' +
             n + ' (' + countFor(n) + ')</button>';
    }).join('');

    var shown = BOL.cars.filter(function (c) { return current === 'All' || c.status === current; });

    rowsEl.innerHTML = shown.map(function (c) {
      return (
        '<a href="admin-car.html" class="trow cols-inventory">' +
          '<div><strong>' + c.name + '</strong><div class="muted" style="font-size: 13px;">' + c.year + '</div></div>' +
          '<div>' + pill(c.status) + '</div>' +
          '<div>' + peso(c.bought) + '</div>' +
          '<div>' + peso(c.spent) + '</div>' +
          '<div><strong>' + peso(c.bought + c.spent) + '</strong></div>' +
          '<div>' + (c.price ? peso(c.price) : 'Not set') + '</div>' +
          '<div>' + c.days + '</div>' +
        '</a>'
      );
    }).join('');
  }

  tabsEl.addEventListener('click', function (e) {
    var btn = e.target.closest('[data-tab]');
    if (!btn) return;
    current = btn.getAttribute('data-tab');
    render();
  });

  render();
})();
