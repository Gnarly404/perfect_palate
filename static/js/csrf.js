(function () {
  const tokenElement = document.querySelector('meta[name="csrf-token"]');
  if (!tokenElement) return;

  const token = tokenElement.content;
  const originalFetch = window.fetch.bind(window);

  window.fetch = function (input, init) {
    const requestUrl = new URL(input instanceof Request ? input.url : input, window.location.href);
    const method = (init && init.method) || (input instanceof Request && input.method) || 'GET';

    if (requestUrl.origin === window.location.origin && !['GET', 'HEAD', 'OPTIONS'].includes(method.toUpperCase())) {
      const headers = new Headers(input instanceof Request ? input.headers : undefined);
      new Headers(init && init.headers).forEach((value, name) => headers.set(name, value));
      headers.set('X-CSRF-Token', token);
      init = Object.assign({}, init, { headers });
    }

    return originalFetch(input, init);
  };
})();
