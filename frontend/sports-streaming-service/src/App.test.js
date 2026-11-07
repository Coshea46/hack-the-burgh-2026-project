import { render, screen, fireEvent, within } from '@testing-library/react';
import App from './App';
import MainPlayer, { boundedTime } from './components/MainPlayer';
import { FEEDS, getVideoUrl, getPreviewUrl } from './feeds';

beforeEach(() => localStorage.clear());

function ready(video) {
  Object.defineProperty(video, 'readyState', { configurable: true, value: 2 });
  Object.defineProperty(video, 'duration', { configurable: true, value: 418.69 });
  fireEvent.loadedMetadata(video);
  fireEvent.canPlay(video);
}

test('opens one S3 main player and six visible lightweight previews', () => {
  render(<App />);
  const main = screen.getByLabelText('Match 1 video');
  expect(main).toHaveAttribute('src', getVideoUrl(FEEDS[0]));
  expect(main).toHaveAttribute('controls');
  const strip = screen.getByRole('region', { name: 'Other matches' });
  expect(within(strip).getAllByRole('button')).toHaveLength(6);
  expect(strip.querySelectorAll('video')).toHaveLength(7);
  strip.querySelectorAll('video').forEach((video) => {
    expect(video).toHaveAttribute('src', getPreviewUrl(FEEDS[0]));
    expect(video.getAttribute('src')).not.toBe(main.getAttribute('src'));
  });
});

test('switching preserves every video DOM node and the shared-source main timestamp', () => {
  const { container } = render(<App />);
  const main = screen.getByLabelText('Match 1 video');
  ready(main);
  main.currentTime = 125;
  fireEvent.timeUpdate(main);
  const videos = Array.from(container.querySelectorAll('video'));
  fireEvent.click(screen.getByRole('button', { name: 'Match 3' }));
  expect(screen.getByLabelText('Match 3 video')).toBe(main);
  expect(main.currentTime).toBe(125);
  Array.from(container.querySelectorAll('video')).forEach((video, index) => expect(video).toBe(videos[index]));
  expect(screen.getByRole('button', { name: 'Match 1' })).toBeInTheDocument();
  expect(screen.getByRole('heading', { name: 'Match 3' })).toHaveFocus();
});

test('a genuinely different main source restores timeline, pause, rate and volume', () => {
  const clock = { current: { time: 0, playing: true, rate: 1, muted: false, volume: 1 } };
  const { rerender } = render(<MainPlayer feed={{ id: 1, label: 'A', mainKey: 'a.mp4' }} clock={clock} />);
  const video = screen.getByLabelText('A video');
  ready(video);
  video.currentTime = 82;
  video.playbackRate = 1.5;
  video.volume = 0.4;
  video.muted = true;
  fireEvent.timeUpdate(video);
  fireEvent.pause(video);
  const play = jest.spyOn(video, 'play');
  play.mockClear();
  rerender(<MainPlayer feed={{ id: 2, label: 'B', mainKey: 'b.mp4' }} clock={clock} />);
  expect(screen.getByLabelText('B video')).toBe(video);
  video.currentTime = 0; // Simulate the browser resetting time for a new resource.
  ready(video);
  expect(video.currentTime).toBe(82);
  expect(video.playbackRate).toBe(1.5);
  expect(video.volume).toBe(0.4);
  expect(video.muted).toBe(true);
  expect(play).not.toHaveBeenCalled();
  play.mockRestore();
});

test('Space and scoped number shortcuts continue to select matches', () => {
  render(<App />);
  fireEvent.keyDown(window, { key: '4' });
  expect(screen.getByLabelText('Match 1 video')).toBeInTheDocument();
  fireEvent.keyDown(screen.getByRole('button', { name: 'Match 2' }), { key: ' ' });
  expect(screen.getByLabelText('Match 2 video')).toBeInTheDocument();
  fireEvent.keyDown(screen.getByRole('heading', { name: 'Match 2' }), { key: '4' });
  expect(screen.getByLabelText('Match 4 video')).toBeInTheDocument();
  fireEvent.keyDown(screen.getByRole('heading', { name: 'Match 4' }), { key: 'Escape' });
  expect(screen.getByRole('button', { name: 'Match 1' })).toHaveFocus();
});

test('pause previews never pauses the main element, and selection keeps previews paused', () => {
  const pause = jest.spyOn(window.HTMLMediaElement.prototype, 'pause');
  render(<App />);
  const main = screen.getByLabelText('Match 1 video');
  pause.mockClear();
  fireEvent.click(screen.getByRole('button', { name: 'Pause previews' }));
  expect(pause).toHaveBeenCalledTimes(7);
  expect(pause.mock.instances).not.toContain(main);
  fireEvent.click(screen.getByRole('button', { name: 'Match 3' }));
  expect(screen.getByRole('button', { name: 'Resume previews' })).toHaveAttribute('aria-pressed', 'true');
  expect(pause.mock.instances).not.toContain(main);
  pause.mockRestore();
});

test('a returning preview seeks to the main timeline without being recreated', () => {
  const { container } = render(<App />);
  const main = screen.getByLabelText('Match 1 video');
  const preview = container.querySelector('[data-feed-id="1"] video');
  ready(main);
  ready(preview);
  main.currentTime = 100;
  fireEvent.timeUpdate(main);
  fireEvent.click(screen.getByRole('button', { name: 'Match 3' }));
  expect(container.querySelector('[data-feed-id="1"] video')).toBe(preview);
  expect(preview.currentTime).toBe(100);
});

test('themes persist without replacing media elements', () => {
  const { unmount } = render(<App />);
  const main = screen.getByLabelText('Match 1 video');
  fireEvent.click(screen.getByRole('button', { name: 'Switch to light mode' }));
  expect(screen.getByLabelText('Match 1 video')).toBe(main);
  expect(localStorage.getItem('match-switcher-theme')).toBe('light');
  unmount();
  render(<App />);
  fireEvent.click(screen.getByRole('button', { name: 'Switch to dark mode' }));
  expect(document.documentElement).toHaveAttribute('data-theme', 'dark');
});

test('main failures expose retry and preview errors never load the full source', () => {
  const { container } = render(<App />);
  fireEvent.error(screen.getByLabelText('Match 1 video'));
  expect(screen.getByRole('button', { name: 'Retry' })).toBeInTheDocument();
  const preview = container.querySelector('[data-feed-id="2"] video');
  fireEvent.error(preview);
  expect(preview).toHaveAttribute('src', getPreviewUrl(FEEDS[1]));
  expect(screen.getByText('Preview unavailable')).toBeInTheDocument();
});

test('seek targets remain within the destination duration', () => {
  expect(boundedTime(500, 100)).toBe(99.9);
  expect(boundedTime(-10, 100)).toBe(0);
  expect(boundedTime(25, NaN)).toBe(25);
});
