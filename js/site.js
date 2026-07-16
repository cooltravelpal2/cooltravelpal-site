/* Cool TravelPal — shared site behavior (no dependencies) */
(function () {
  'use strict';

  /* One-place configuration for this static site's growth integrations. */
  var integrations = {
    googleAnalyticsId: 'G-7CNWGM9QZ9',
    newsletterAction: ''
  };

  // Analytics remains completely off until a real GA4 measurement ID is added.
  if (/^G-[A-Z0-9]+$/.test(integrations.googleAnalyticsId)) {
    window.dataLayer = window.dataLayer || [];
    window.gtag = window.gtag || function () { window.dataLayer.push(arguments); };
    window.gtag('js', new Date());
    window.gtag('config', integrations.googleAnalyticsId, {
      anonymize_ip: true,
      allow_google_signals: false,
      allow_ad_personalization_signals: false
    });
    var analyticsScript = document.createElement('script');
    analyticsScript.async = true;
    analyticsScript.src = 'https://www.googletagmanager.com/gtag/js?id=' +
      encodeURIComponent(integrations.googleAnalyticsId);
    document.head.appendChild(analyticsScript);
  }

  var track = function (eventName, parameters) {
    if (typeof window.gtag === 'function') {
      window.gtag('event', eventName, parameters || {});
    }
  };

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

  // Measure useful outcomes without sending email addresses or form contents.
  document.addEventListener('click', function (event) {
    var link = event.target.closest('a[href]');
    if (!link) return;
    var href = link.getAttribute('href') || '';
    if (href.indexOf('apps.apple.com') !== -1) {
      track('app_store_click', { link_url: link.href, link_text: link.textContent.trim() });
    } else if (href === '/feed.xml') {
      track('rss_click');
    } else if (/^mailto:/.test(href)) {
      track('email_contact_click');
    } else if (/^https?:/.test(href) && link.hostname !== window.location.hostname) {
      track('outbound_click', { link_url: link.href });
    }
  });

  document.querySelectorAll('[data-newsletter-form]').forEach(function (form) {
    if (integrations.newsletterAction) {
      form.action = integrations.newsletterAction;
      form.addEventListener('submit', function () { track('newsletter_signup'); });
    } else {
      form.addEventListener('submit', function (event) {
        event.preventDefault();
        var status = form.querySelector('[data-newsletter-status]');
        if (status) status.textContent = 'Signup is being connected. Please use RSS for now.';
      });
    }
  });
})();
