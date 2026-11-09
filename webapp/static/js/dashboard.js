/* Admin dashboard: numbers are calculated from the sample data */

(function () {
  var cars = BOL.cars;
  var inStock = cars.filter(function (c) { return c.status !== 'Sold'; });

  function count(status) {
    return cars.filter(function (c) { return c.status === status; }).length;
  }

  var tiedUp = inStock.reduce(function (sum, c) { return sum + c.bought + c.spent; }, 0);
  var newInquiries = BOL.inquiries.filter(function (i) { return i.status === 'New'; });

  // ----- KPI tiles -----
  var kpis = [
    { label: 'Cars in stock',          value: String(inStock.length), note: count('Available') + ' available to buyers' },
    { label: 'Sold this month',        value: '3',                    note: 'Revenue ₱1,580,000' },
    { label: 'Profit this month',      value: '₱212,000',             note: 'After purchase and expenses' },
    { label: 'Profit all time',        value: '₱1,046,000',           note: 'Since the system started' },
    { label: 'Money tied up in stock', value: peso(tiedUp),           note: 'Buying price plus expenses' },
    { label: 'New inquiries',          value: String(newInquiries.length), note: 'Waiting for a reply' }
  ];
  document.getElementById('kpis').innerHTML = kpis.map(function (k) {
    return '<div class="kpi"><div class="kpi-label">' + k.label + '</div>' +
           '<div class="kpi-value">' + k.value + '</div>' +
           '<div class="kpi-note">' + k.note + '</div></div>';
  }).join('');

  // ----- Cars by status -----
  document.getElementById('stock-note').textContent = inStock.length + ' cars in stock';
  var statuses = ['Incoming', 'Under repair', 'Available', 'Reserved'];
  document.getElementById('status-bar').innerHTML = statuses.map(function (s) {
    return '<div class="seg-' + s.toLowerCase().replace(/\s+/g, '-') + '" style="flex: ' + count(s) + ' 1 0;">' + count(s) + '</div>';
  }).join('');
  document.getElementById('legend').innerHTML = statuses.map(function (s) {
    return '<div><span class="seg-' + s.toLowerCase().replace(/\s+/g, '-') + '"></span>' + s + '</div>';
  }).join('');

  // ----- Profit by month -----
  var max = Math.max.apply(null, BOL.profitByMonth.map(function (p) { return p.value; }));
  document.getElementById('bars').innerHTML = BOL.profitByMonth.map(function (p) {
    var h = Math.round((p.value / max) * 150);
    return '<div class="bar-col"><div class="bar-val">' + p.value + '</div><div class="bar" style="height: ' + h + 'px;"></div></div>';
  }).join('');
  document.getElementById('bar-labels').innerHTML = BOL.profitByMonth.map(function (p) {
    return '<span>' + p.month + '</span>';
  }).join('');

  // ----- Slowest moving -----
  var slow = publicCars().sort(function (a, b) { return b.days - a.days; }).slice(0, 4);
  document.getElementById('slow').innerHTML = slow.map(function (c) {
    return '<a href="admin-car.html" class="list-row">' +
             '<div><div class="title">' + c.name + '</div><div class="sub">Tied up: ' + peso(c.bought + c.spent) + '</div></div>' +
             '<div class="big">' + c.days + ' days</div>' +
           '</a>';
  }).join('');

  // ----- New inquiries -----
  document.getElementById('new-inquiries').innerHTML = BOL.inquiries.slice(0, 4).map(function (i) {
    return '<a href="inquiries.html" class="list-block">' +
             '<div class="top"><strong>' + i.who + '</strong><span class="time">' + i.when + '</span></div>' +
             '<div class="muted" style="font-size: 14px;">' + i.car + ' · ' + i.kind + '</div>' +
           '</a>';
  }).join('');
})();
