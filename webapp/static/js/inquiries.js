/* Admin inquiries: list, filter tabs, detail view and status changes */

(function () {
  var items = BOL.inquiries.map(function (i) { return Object.assign({}, i); });
  var selectedId = 1;
  var tab = 'All';

  var tabsEl = document.getElementById('tabs');
  var inboxEl = document.getElementById('inbox');
  var actionsEl = document.getElementById('actions');

  function selected() {
    return items.filter(function (i) { return i.id === selectedId; })[0] || items[0];
  }

  function countFor(name) {
    if (name === 'All') return items.length;
    return items.filter(function (i) { return i.status === name; }).length;
  }

  function render() {
    // tabs
    tabsEl.innerHTML = ['All', 'New', 'Contacted', 'Closed'].map(function (n) {
      return '<button type="button" class="chip' + (n === tab ? ' is-active' : '') + '" data-tab="' + n + '">' +
             n + ' (' + countFor(n) + ')</button>';
    }).join('');

    // inbox list
    inboxEl.innerHTML = items
      .filter(function (i) { return tab === 'All' || i.status === tab; })
      .map(function (i) {
        return (
          '<button type="button" class="inbox-item' + (i.id === selectedId ? ' is-active' : '') + '" data-id="' + i.id + '">' +
            '<span class="line1"><span>' + i.who + '</span>' + pill(i.status) + '</span>' +
            '<span class="line2">' + i.car + ' · ' + i.kind + '</span>' +
            '<span class="line3">' + i.when + '</span>' +
          '</button>'
        );
      }).join('');

    // reader
    var cur = selected();
    document.getElementById('r-who').textContent = cur.who;
    document.getElementById('r-contact').textContent = cur.contact;
    document.getElementById('r-pill').innerHTML = '<span class="' + pillClass(cur.status) + ' badge-lg">' + cur.status + '</span>';
    document.getElementById('r-car').textContent = cur.car;
    document.getElementById('r-meta').textContent = cur.kind + ' · ' + cur.when;
    document.getElementById('r-message').textContent = cur.message;

    actionsEl.innerHTML = ['New', 'Contacted', 'Closed'].map(function (s) {
      return '<button type="button" class="chip' + (s === cur.status ? ' is-active' : '') + '" data-status="' + s + '">' + s + '</button>';
    }).join('');
  }

  tabsEl.addEventListener('click', function (e) {
    var btn = e.target.closest('[data-tab]');
    if (!btn) return;
    tab = btn.getAttribute('data-tab');
    render();
  });

  inboxEl.addEventListener('click', function (e) {
    var btn = e.target.closest('[data-id]');
    if (!btn) return;
    selectedId = Number(btn.getAttribute('data-id'));
    render();
  });

  actionsEl.addEventListener('click', function (e) {
    var btn = e.target.closest('[data-status]');
    if (!btn) return;
    selected().status = btn.getAttribute('data-status');
    render();
  });

  render();
})();
