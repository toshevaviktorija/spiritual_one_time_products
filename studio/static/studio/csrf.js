const ready = new WeakSet();
const pending = new WeakSet();
for (const form of document.querySelectorAll('form[method="post"]')) {
  const token = form.querySelector('input[name="csrfmiddlewaretoken"]');
  const endpoint = document.body.dataset.csrfTokenUrl;
  if (!token || !endpoint || new URL(form.action).origin !== location.origin) continue;
  let notice;
  form.addEventListener('submit', async event => {
    if (event.defaultPrevented) return;
    if (ready.has(form)) {
      ready.delete(form);
      return;
    }
    event.preventDefault();
    if (pending.has(form)) return;
    pending.add(form);
    const submitter = event.submitter;
    try {
      const response = await fetch(endpoint, {credentials: 'same-origin', cache: 'no-store', signal: AbortSignal.timeout(10000)});
      if (!response.ok) throw new Error('Token refresh failed');
      const data = await response.json();
      if (typeof data.token !== 'string' || !/^[A-Za-z0-9]{64}$/.test(data.token)) throw new Error('Invalid token');
      token.value = data.token;
      if (notice) notice.textContent = '';
      ready.add(form);
      if (submitter) form.requestSubmit(submitter);
      else form.requestSubmit();
      ready.delete(form);
    } catch {
      if (!notice) {
        notice = document.createElement('p');
        notice.className = 'notice';
        notice.setAttribute('role', 'alert');
        form.append(notice);
      }
      notice.textContent = 'We couldn’t prepare your submission. Your details are still here. Check your connection and try again.';
    } finally {
      pending.delete(form);
    }
  });
}
