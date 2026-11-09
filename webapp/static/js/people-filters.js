var peopleSearchForm = document.querySelector('[data-live-search]');
var peopleSearchInput = document.getElementById('people-search');
var peopleResults = document.getElementById('people-results');
var peopleAccountCount = document.getElementById('people-account-count');
var peopleSearchError = document.getElementById('people-search-error');
var peopleExportLink = document.querySelector('[data-people-export]');

if (
  peopleSearchForm &&
  peopleSearchInput &&
  peopleResults &&
  peopleSearchError &&
  peopleExportLink
) {
  var peopleSearchTimer;
  var activeSearchRequest;

  function updateExportLink(search) {
    var exportUrl = new URL(peopleExportLink.href, window.location.href);
    if (search) {
      exportUrl.searchParams.set('q', search);
    } else {
      exportUrl.searchParams.delete('q');
    }
    peopleExportLink.href = exportUrl.toString();
  }

  function searchPeople() {
    if (activeSearchRequest) {
      activeSearchRequest.abort();
    }
    activeSearchRequest = new AbortController();

    var searchUrl = new URL(peopleSearchForm.action, window.location.href);
    new FormData(peopleSearchForm).forEach(function (value, key) {
      if (value) {
        searchUrl.searchParams.set(key, value);
      } else {
        searchUrl.searchParams.delete(key);
      }
    });

    fetch(searchUrl, {
      headers: { 'X-Requested-With': 'XMLHttpRequest' },
      signal: activeSearchRequest.signal
    })
      .then(function (response) {
        if (!response.ok) {
          throw new Error('Search request failed with status ' + response.status + '.');
        }
        return response.text();
      })
      .then(function (html) {
        var parsedResponse = new DOMParser().parseFromString(
          '<!doctype html><html><body><table>' + html + '</table></body></html>',
          'text/html'
        );
        var updatedResults = parsedResponse.getElementById('people-results');
        if (!updatedResults) {
          throw new Error('Search response did not contain account results.');
        }

        peopleResults.replaceWith(updatedResults);
        peopleResults = updatedResults;
        var visibleAccounts = Array.prototype.filter.call(
          updatedResults.querySelectorAll('tr'),
          function (row) { return row.children.length > 1; }
        ).length;
        peopleAccountCount.textContent =
          visibleAccounts + ' account' + (visibleAccounts === 1 ? '' : 's') + ' shown.';
        peopleSearchError.hidden = true;
        peopleSearchError.textContent = '';
        window.history.replaceState(null, '', searchUrl);
        updateExportLink(peopleSearchInput.value.trim());
      })
      .catch(function (error) {
        if (error.name !== 'AbortError') {
          peopleSearchError.textContent = 'Could not update accounts. Please try again.';
          peopleSearchError.hidden = false;
          console.error(error);
        }
      });
  }

  peopleSearchForm.addEventListener('submit', function (event) {
    event.preventDefault();
    window.clearTimeout(peopleSearchTimer);
    searchPeople();
  });

  peopleSearchInput.addEventListener('input', function () {
    window.clearTimeout(peopleSearchTimer);
    peopleSearchTimer = window.setTimeout(searchPeople, 300);
  });
}
