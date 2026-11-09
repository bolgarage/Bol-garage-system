var inventorySearchForm = document.querySelector('[data-inventory-search]');
var inventorySearchInput = document.getElementById('q');
var inventoryStatusFilter = document.querySelector('[data-submit-on-change]');
var inventoryResults = document.getElementById('inventory-results');
var inventorySearchError = document.getElementById('inventory-search-error');
var inventoryExportLink = inventorySearchForm &&
  inventorySearchForm.querySelector('a[href*="export=pdf"]');

if (
  inventorySearchForm &&
  inventorySearchInput &&
  inventoryStatusFilter &&
  inventoryResults &&
  inventorySearchError &&
  inventoryExportLink
) {
  var activeInventoryRequest;

  function getInventoryUrl(exportPdf) {
    var url = new URL(inventorySearchForm.action, window.location.href);
    url.search = '';
    new FormData(inventorySearchForm).forEach(function (value, key) {
      if (value) {
        url.searchParams.set(key, value);
      }
    });
    if (exportPdf) {
      url.searchParams.set('export', 'pdf');
    }
    return url;
  }

  function updateInventoryExportLink() {
    inventoryExportLink.href = getInventoryUrl(true).toString();
  }

  function searchInventory() {
    if (activeInventoryRequest) {
      activeInventoryRequest.abort();
    }
    activeInventoryRequest = new AbortController();
    var searchUrl = getInventoryUrl(false);

    fetch(searchUrl, {
      headers: { 'X-Requested-With': 'XMLHttpRequest' },
      signal: activeInventoryRequest.signal
    })
      .then(function (response) {
        if (!response.ok) {
          throw new Error('Inventory search failed with status ' + response.status + '.');
        }
        return response.text();
      })
      .then(function (html) {
        var parsedResponse = new DOMParser().parseFromString(
          '<!doctype html><html><body><table>' + html + '</table></body></html>',
          'text/html'
        );
        var updatedResults = parsedResponse.getElementById('inventory-results');
        if (!updatedResults) {
          throw new Error('Inventory search response did not contain results.');
        }

        inventoryResults.replaceWith(updatedResults);
        inventoryResults = updatedResults;
        inventorySearchError.hidden = true;
        inventorySearchError.textContent = '';
        window.history.replaceState(null, '', searchUrl);
        updateInventoryExportLink();
      })
      .catch(function (error) {
        if (error.name !== 'AbortError') {
          inventorySearchError.textContent = 'Could not update inventory. Please try again.';
          inventorySearchError.hidden = false;
          console.error(error);
        }
      });
  }

  inventorySearchForm.addEventListener('submit', function (event) {
    event.preventDefault();
    searchInventory();
  });

  inventorySearchInput.addEventListener('input', function () {
    updateInventoryExportLink();
    searchInventory();
  });

  inventoryStatusFilter.addEventListener('change', function () {
    updateInventoryExportLink();
    searchInventory();
  });
}
