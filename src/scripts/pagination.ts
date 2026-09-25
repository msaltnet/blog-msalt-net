const pageSize = 20;
const cards = [...document.querySelectorAll<HTMLElement>('[data-pageable]')];
const totalPages = Math.max(1, Math.ceil(cards.length / pageSize));
const requestedPage = Number(new URL(location.href).searchParams.get('page') || '1');
const page = Number.isInteger(requestedPage) ? Math.min(totalPages, Math.max(1, requestedPage)) : 1;

cards.forEach((card, index) => {
  card.hidden = index < (page - 1) * pageSize || index >= page * pageSize;
});

const pageLabel = document.querySelector<HTMLElement>('[data-page-label]');
if (pageLabel) pageLabel.textContent = `${page} / ${totalPages}`;
document.querySelectorAll<HTMLAnchorElement>('[data-page-link]').forEach((link) => {
  const key = link.dataset.pageLink || '';
  const target = key === 'first' ? 1 : key === 'prev' ? page - 1 : key === 'next' ? page + 1 : key === 'last' ? totalPages : Number(key);
  if (!Number.isInteger(target) || target < 1 || target > totalPages) {
    link.hidden = true;
    return;
  }
  const url = new URL(location.href);
  url.searchParams.set('page', String(target));
  if (target === 1) url.searchParams.delete('page');
  link.href = `${url.pathname}${url.search}`;
});
