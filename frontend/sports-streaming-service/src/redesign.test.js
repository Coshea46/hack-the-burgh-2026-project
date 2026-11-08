import { act, fireEvent, render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import axe from 'axe-core';
import App from './App';
import { FEEDS } from './feeds';
import { clearApiCache } from './platformApi';

beforeEach(() => {
  localStorage.clear();
  clearApiCache();
  window.history.replaceState(null, '', '/');
  global.fetch = jest.fn(() => Promise.resolve({ ok: true, json: () => Promise.resolve({ status: 'missing_key' }) }));
});
afterEach(() => {
  clearApiCache();
  delete global.fetch;
  window.history.replaceState(null, '', '/');
});

test('the three navigation links have one active page and preserve every media element', async () => {
  const { container } = render(<App />);
  const navigation = screen.getByRole('navigation', { name: 'Main navigation' });
  expect(within(navigation).getAllByRole('link').map((link) => link.textContent)).toEqual(['Watch', 'Tables', 'News']);
  expect(within(navigation).getByRole('link', { current: 'page' })).toHaveAccessibleName('Watch');
  const videos = [...container.querySelectorAll('video')];
  const video = screen.getByLabelText(`${FEEDS[0].label} video`);
  Object.defineProperty(video, 'readyState', { configurable: true, value: 2 });
  Object.defineProperty(video, 'duration', { configurable: true, value: 1000 });
  fireEvent.loadedMetadata(video); fireEvent.canPlay(video);
  video.currentTime = 137.25; video.playbackRate = 1.25; video.volume = .3;
  fireEvent.rateChange(video); fireEvent.volumeChange(video); fireEvent.pause(video);
  const source = video.getAttribute('src');
  for (const name of ['Tables', 'News', 'Watch']) {
    await act(async () => fireEvent.click(within(navigation).getByRole('link', { name })));
    expect(within(navigation).getAllByRole('link', { current: 'page' })).toHaveLength(1);
    expect(within(navigation).getByRole('link', { current: 'page' })).toHaveAccessibleName(name);
    expect([...container.querySelectorAll('video')]).toEqual(videos);
    expect(video.getAttribute('src')).toBe(source);
    expect(video.currentTime).toBe(137.25);
    expect(video.playbackRate).toBe(1.25); expect(video.volume).toBe(.3);
  }
  expect(videos).toHaveLength(8);
  expect(screen.getByRole('region', { name: 'Other matches' })).toBeVisible();
});

test('Watch groups director and captions beside the player before alternatives, with no heading badges', () => {
  render(<App />);
  const watch = screen.getByRole('region', { name: 'Watch matches' });
  const player = screen.getByLabelText(`${FEEDS[0].label} video`);
  const director = within(watch).getByRole('complementary', { name: 'Auto Director settings' });
  const alternatives = within(watch).getByRole('complementary', { name: 'Match selection' });
  const captions = within(watch).getByRole('region', { name: 'Commentary captions' });
  expect(player.compareDocumentPosition(director) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
  expect(director.compareDocumentPosition(captions) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
  expect(captions.compareDocumentPosition(alternatives) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
  expect(director.parentElement).toBe(captions.parentElement);
  for (const label of ['Prerecorded replay', 'Watching', 'Your selection', 'MatchPulse selected']) {
    expect(within(watch).queryByText(label, { exact: true })).not.toBeInTheDocument();
  }
  expect(within(captions).queryByRole('combobox')).not.toBeInTheDocument();
  expect(within(alternatives).getAllByRole('button')).toHaveLength(7);
});

test.each(['#moments', '#about', '#unknown'])('obsolete or unknown initial route %s safely opens Watch', (hash) => {
  window.history.replaceState(null, '', `/${hash}`);
  const { container } = render(<App />);
  expect(screen.getByRole('link', { name: 'Watch', current: 'page' })).toBeInTheDocument();
  expect(document.getElementById('watch')).toBeVisible();
  expect(container.querySelector('#moments, #about')).toBeNull();
  expect(window.location.hash).toBe('#watch');
});

test('hash changes and browser history never leave a removed route or reset playback', async () => {
  render(<App />);
  const video = screen.getByLabelText(`${FEEDS[0].label} video`);
  video.currentTime = 76.5;
  await act(async () => {
    window.history.replaceState(null, '', '/#news');
    window.dispatchEvent(new Event('hashchange'));
  });
  expect(screen.getByRole('link', { name: 'News', current: 'page' })).toBeInTheDocument();
  await act(async () => {
    window.history.replaceState(null, '', '/#about');
    window.dispatchEvent(new Event('popstate'));
  });
  expect(screen.getByRole('link', { name: 'Watch', current: 'page' })).toBeInTheDocument();
  expect(window.location.hash).toBe('#watch');
  expect(screen.getByLabelText(`${FEEDS[0].label} video`)).toBe(video);
  expect(video.currentTime).toBe(76.5);
});

test('navigation, theme, preview and caption controls remain named and keyboard operable', async () => {
  render(<App />);
  const skip = screen.getByRole('link', { name: 'Skip to content' });
  const routeBeforeSkip = window.location.hash;
  userEvent.tab(); expect(skip).toHaveFocus();
  userEvent.keyboard('{Enter}');
  expect(screen.getByRole('main')).toHaveFocus();
  expect(window.location.hash).toBe(routeBeforeSkip);
  const tables = screen.getByRole('link', { name: 'Tables' });
  tables.focus();
  await act(async () => userEvent.keyboard('{Enter}'));
  expect(tables).toHaveAttribute('aria-current', 'page');
  await act(async () => fireEvent.click(screen.getByRole('link', { name: 'Watch' })));
  expect(screen.getByRole('button', { name: 'Pause previews' })).toHaveAttribute('aria-pressed', 'false');
  const captions = screen.getByRole('region', { name: 'Commentary captions' });
  expect(within(captions).getByRole('button', { name: /Commentary captions On/ })).toHaveAttribute('aria-pressed', 'true');
  expect(within(captions).queryByRole('combobox')).not.toBeInTheDocument();
  const theme = screen.getByRole('button', { name: 'Switch to dark mode' });
  theme.focus(); userEvent.keyboard('{Enter}');
  expect(document.documentElement).toHaveAttribute('data-theme', 'dark');
});

test.each(['light', 'dark'])('%s Watch has no structural accessibility violations', async (theme) => {
  localStorage.setItem('match-switcher-theme', theme);
  const { container } = render(<App />);
  // JSDOM has no rendered colours/layout; contrast needs the separate browser
  // check. axe-core is already installed by the existing application tooling.
  let result;
  await act(async () => {
    result = await axe.run(container, { runOnly: { type: 'tag', values: ['wcag2a', 'wcag2aa', 'wcag21aa'] },
      rules: { 'color-contrast': { enabled: false } } });
  });
  expect(result.violations.map(({ id, nodes }) => ({ id, targets: nodes.map(({ target }) => target) }))).toEqual([]);
});
