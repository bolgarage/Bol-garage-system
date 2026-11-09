(function () {
  document.querySelectorAll('[data-card-carousel]').forEach(function (carousel) {
    var images = Array.from(carousel.querySelectorAll('.car-card-image'));
    var previous = carousel.querySelector('.car-card-previous');
    var next = carousel.querySelector('.car-card-next');
    var counter = carousel.querySelector('.car-card-photo-count');
    var current = 0;

    if (images.length < 2 || !previous || !next) {
      return;
    }

    function showImage(index) {
      current = (index + images.length) % images.length;
      images.forEach(function (image, imageIndex) {
        image.hidden = imageIndex !== current;
      });
      counter.textContent = (current + 1) + ' / ' + images.length;
    }

    previous.addEventListener('click', function () {
      showImage(current - 1);
    });
    next.addEventListener('click', function () {
      showImage(current + 1);
    });
  });
})();
