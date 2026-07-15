/* Cool TravelPal — shared site behavior (no dependencies) */
(function () {
  'use strict';

  // Mobile menu toggle
  var menuBtn = document.querySelector('.menu-btn');
  var nav = document.getElementById('site-nav');
  if (menuBtn && nav) {
    menuBtn.addEventListener('click', function () {
      var open = nav.classList.toggle('open');
      menuBtn.setAttribute('aria-expanded', open ? 'true' : 'false');
    });
  }

  // Back to top
  var topBtn = document.querySelector('.back-to-top');
  if (topBtn) {
    topBtn.addEventListener('click', function () {
      window.scrollTo({ top: 0, behavior: 'smooth' });
    });
    window.addEventListener('scroll', function () {
      topBtn.classList.toggle('visible', window.scrollY > 300);
    }, { passive: true });
  }

  // FAQ toggles (accordion items marked with .faq-q)
  document.querySelectorAll('.faq-q').forEach(function (q) {
    if (!q.hasAttribute('onclick')) {
      q.setAttribute('role', 'button');
      q.setAttribute('tabindex', '0');
      var toggle = function () { q.parentElement.classList.toggle('open'); };
      q.addEventListener('click', toggle);
      q.addEventListener('keydown', function (e) {
        if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); toggle(); }
      });
    }
  });

  // Guide search: filter [data-searchable] cards by ?q= or live input
  var searchable = document.querySelectorAll('[data-searchable]');
  if (searchable.length) {
    var status = document.getElementById('search-status');
    var filter = function (term) {
      term = term.trim().toLowerCase();
      var shown = 0;
      searchable.forEach(function (el) {
        var match = !term || el.textContent.toLowerCase().indexOf(term) !== -1;
        el.style.display = match ? '' : 'none';
        if (match) shown++;
      });
      if (status) {
        status.textContent = term
          ? shown + ' guide' + (shown === 1 ? '' : 's') + ' matching “' + term + '”'
          : '';
      }
    };
    var params = new URLSearchParams(window.location.search);
    var q = params.get('q') || '';
    var pageSearch = document.getElementById('guide-search');
    if (pageSearch) {
      pageSearch.value = q;
      pageSearch.addEventListener('input', function () { filter(pageSearch.value); });
    }
    if (q) filter(q);
  }
})();
